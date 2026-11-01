"""Post the next queued artwork to Instagram using instagrapi.

Credentials (GitHub Secrets -> env vars)
---------------------------------------
IG_USERNAME / IG_PASSWORD   required
IG_SESSIONID                optional; a browser session id. When set it is used
                            instead of a password login, which avoids most of
                            Instagram's challenge/captcha prompts on cloud IPs.

Safety rails
------------
* ``IG_DELAY_RANGE`` (default 15-45s) is passed to instagrapi as its global
  ``delay_range`` *and* used for an extra pause before the upload, so every
  request is paced like a human.
* ``IG_DAILY_LIMIT`` (default 2) is enforced by the caller (see runner.py) via
  the persisted counter in state/daily_count.json. Instagram technically allows
  ~100 posts per 24h, but 1-3 posts/day keeps an art account in the safe range.

Alt text
--------
Instagram stores alt text in the ``custom_accessibility_caption`` configure
parameter (max 1,000 characters). instagrapi 2.x exposes it as an explicit
``photo_upload`` keyword; 3.x forwards ``extra_data`` into the same configure
payload, so this module supports both without pinning you to one version.
"""

from __future__ import annotations

import argparse
import inspect
import logging
import sys
from pathlib import Path
from typing import Optional

from artbot import common, config
from artbot.logging_utils import get_logger, log_banner
from artbot.runner import run_platform

PLATFORM = "instagram"


def _build_client(logger: logging.Logger):
    """Create an instagrapi client with human-like request pacing."""
    from instagrapi import Client

    client = Client(delay_range=list(config.IG_DELAY_RANGE))
    logger.info(
        "instagrapi client ready (pausing %ss-%ss between requests)", *config.IG_DELAY_RANGE
    )
    return client


def _fresh_login(client, logger: logging.Logger):
    if config.IG_SESSIONID:
        logger.info("Logging in to Instagram with IG_SESSIONID")
        client.login_by_sessionid(config.IG_SESSIONID)
    else:
        logger.info("Logging in to Instagram as %s", config.IG_USERNAME)
        client.login(config.IG_USERNAME, config.IG_PASSWORD)
    return client


def _login(logger: logging.Logger):
    """Log in, reusing (and refreshing) a cached session when possible."""
    if not config.IG_SESSIONID and not (config.IG_USERNAME and config.IG_PASSWORD):
        raise RuntimeError(
            "Instagram credentials are missing: set the IG_USERNAME and IG_PASSWORD "
            "repository secrets (or IG_SESSIONID)."
        )

    client = _build_client(logger)
    used_cache = False

    if config.IG_SESSION_FILE.exists() and not config.IG_SESSIONID:
        try:
            client.load_settings(config.IG_SESSION_FILE)
            used_cache = True
            logger.info("Loaded cached Instagram session from %s", config.IG_SESSION_FILE)
        except Exception as exc:
            logger.warning("Cached Instagram session could not be loaded (%s); doing a full login", exc)

    _fresh_login(client, logger)

    if used_cache:
        try:
            client.get_timeline_feed()  # cheap session validation
            logger.info("Cached Instagram session is still valid")
        except Exception as exc:
            logger.warning(
                "Cached Instagram session was rejected (%s); retrying with a clean login", exc
            )
            client = _fresh_login(_build_client(logger), logger)

    try:
        config.STATE_DIR.mkdir(parents=True, exist_ok=True)
        client.dump_settings(config.IG_SESSION_FILE)
        logger.info("Saved refreshed Instagram session to %s", config.IG_SESSION_FILE)
    except Exception as exc:  # never fail a post because caching failed
        logger.warning("Could not cache the Instagram session: %s", exc)

    return client


def _upload_photo(client, image_path: Path, caption: str, alt_text: str, logger: logging.Logger):
    """Upload one photo, attaching alt text in a version-tolerant way."""
    params = inspect.signature(client.photo_upload).parameters

    if not alt_text:
        logger.info("No alt text for this row; uploading without a custom accessibility caption")
        return client.photo_upload(image_path, caption)

    if "custom_accessibility_caption" in params:
        logger.info("Attaching %d characters of alt text via custom_accessibility_caption", len(alt_text))
        return client.photo_upload(
            image_path, caption, custom_accessibility_caption=alt_text
        )

    # instagrapi >= 3.0: extra_data is merged into the media/configure/ payload,
    # which is where Instagram expects custom_accessibility_caption.
    logger.info(
        "Attaching %d characters of alt text via extra_data['custom_accessibility_caption']", len(alt_text)
    )
    return client.photo_upload(
        image_path, caption, extra_data={"custom_accessibility_caption": alt_text}
    )


def post(item: dict, logger: Optional[logging.Logger] = None, dry_run: bool = False) -> common.PostResult:
    """Publish a single content item to Instagram. Never raises."""
    logger = logger or get_logger("instagram")
    row_id = str(item.get("slug", ""))

    try:
        image_path = common.resolve_item_image(item.get("image", ""))
        caption = common.build_caption(
            item.get("caption", ""),
            item.get("hashtags", ""),
            limit=config.IG_CAPTION_LIMIT,
            logger=logger,
        )
        alt_text = common.truncate(item.get("alt_text", ""), config.IG_ALT_TEXT_LIMIT)

        logger.info(
            "Instagram plan: image=%s (%d caption chars, %d alt chars)",
            image_path.name,
            len(caption),
            len(alt_text),
        )

        if dry_run:
            logger.info("[dry-run] Caption that would be posted:\n%s", caption)
            logger.info("[dry-run] No Instagram request was made and the item was not modified")
            return common.PostResult(
                platform=PLATFORM,
                status=common.DRY_RUN,
                message=f"preview of {image_path.name}",
                row_id=row_id,
            )

        common.human_delay(config.IG_DELAY_RANGE, logger=logger, reason="the Instagram upload")
        client = _login(logger)
        media = _upload_photo(client, image_path, caption, alt_text, logger)
        common.human_delay(config.IG_DELAY_RANGE, logger=logger, reason="refreshing the feed after posting")

        code = getattr(media, "code", None)
        url = f"https://www.instagram.com/p/{code}/" if code else None
        logger.info(
            "Instagram post published: %s", url or f"(media pk {getattr(media, 'pk', 'unknown')})"
        )
        return common.PostResult(
            platform=PLATFORM, status=common.POSTED, message="published", row_id=row_id, url=url
        )

    except Exception as exc:  # noqa: BLE001 - a failed post must never crash the workflow
        hint = ""
        text = str(exc).lower()
        if "challenge" in text or "checkpoint" in text:
            hint = (
                " | Instagram wants a verification challenge. Open the app, approve the login, "
                "or set the IG_SESSIONID secret."
            )
        elif "two-factor" in text or "2fa" in text or "totp" in text:
            hint = " | Two-factor auth is enabled: set IG_SESSIONID or provide a TOTP-enabled flow."
        elif "login_required" in text or "login required" in text:
            hint = " | Session rejected: delete state/instagram_session.json or set IG_SESSIONID."
        elif "rate" in text or "429" in text:
            hint = " | Instagram is throttling requests: lower IG_DAILY_LIMIT and retry tomorrow."
        logger.exception("Instagram posting failed for item %s", row_id or "?")
        return common.PostResult(
            platform=PLATFORM,
            status=common.FAILED,
            message=f"{type(exc).__name__}: {exc}{hint}",
            row_id=row_id,
        )


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="Post the next queued artwork to Instagram.")
    parser.add_argument("--dry-run", action="store_true", help="preview only, no Instagram request")
    parser.add_argument(
        "--max-items", type=int, default=1, help="how many queued rows to post in this run (default 1)"
    )
    args = parser.parse_args(argv)

    config.ensure_directories()
    logger = get_logger("instagram")
    dry_run = bool(args.dry_run or config.DRY_RUN)

    log_banner(logger, "SocialArtzy - Instagram run")
    if dry_run:
        logger.info("DRY RUN: nothing will be posted and the queue stays untouched")

    results = run_platform(
        PLATFORM,
        post,
        logger=logger,
        max_items=max(1, args.max_items),
        dry_run=dry_run,
    )

    logger.info("Instagram summary:\n%s", common.format_results(results))
    return 1 if any(result.failed for result in results) else 0


if __name__ == "__main__":
    sys.exit(main())