"""Post the next queued artwork to Pinterest.

Credentials (GitHub Secrets -> env vars)
---------------------------------------
PINTEREST_EMAIL / PINTEREST_PASSWORD   required for the free, unofficial route
PINTEREST_USERNAME                     optional but recommended: your handle
                                       (the part after pinterest.com/) so the bot
                                       can look your boards up by name
PINTEREST_ACCESS_TOKEN                 optional: an official API v5 token. When
                                       present the bot uses the documented API
                                       instead of py3-pinterest

How it posts
------------
``py3-pinterest`` logs in with a headless Chrome window (Pinterest uses
reCAPTCHA on its login form), caches the resulting cookies in
``state/pinterest/`` and then speaks to the normal Pinterest web endpoints - no
API key and no paid service required. ``state/pinterest/`` is git-ignored and
restored through the Actions cache, so Chrome usually only runs when the
~15 day cookie lifetime expires.

Safety rails
------------
* ``PINTEREST_DELAY_RANGE`` (default 20-60s) pauses before/after each pin.
* ``PINTEREST_DAILY_LIMIT`` (default 3) is enforced by runner.py through the
  persisted daily counter - new Pinterest accounts get flagged fast above 5.
"""

from __future__ import annotations

import argparse
import base64
import logging
import mimetypes
import sys
from pathlib import Path
from typing import Optional

from artbot import common, config
from artbot.logging_utils import get_logger, log_banner
from artbot.runner import run_platform

PLATFORM = "pinterest"
API_BASE = "https://api.pinterest.com/v5"
OAUTH_TOKEN_URL = "https://api.pinterest.com/v5/oauth/token"

_AUTH_ERROR_MARKERS = ("401", "403", "unauthor", "forbidden", "not logged in", "login")


def _use_v5() -> bool:
    """Return True when Pinterest API v5 OAuth credentials are configured."""
    return bool(config.PINTEREST_CLIENT_ID and config.PINTEREST_REFRESH_TOKEN)


def _v5_access_token(logger) -> str:
    """Exchange the refresh token for a Pinterest API v5 access token."""
    if not config.PINTEREST_CLIENT_SECRET:
        raise RuntimeError(
            "PINTEREST_CLIENT_SECRET is required for Pinterest API v5 OAuth"
        )
    data = {
        "grant_type": "refresh_token",
        "refresh_token": config.PINTEREST_REFRESH_TOKEN,
        "client_id": config.PINTEREST_CLIENT_ID,
        "client_secret": config.PINTEREST_CLIENT_SECRET,
    }
    response = requests.post(OAUTH_TOKEN_URL, data=data, timeout=30)
    response.raise_for_status()
    token = response.json().get("access_token")
    if not token:
        raise RuntimeError("Pinterest OAuth did not return an access_token")
    logger.info("Obtained Pinterest API v5 access token via refresh token")
    return token


def _v5_headers(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}


def _v5_board_id(access_token: str, board_value: str, logger) -> str:
    """Resolve a board name to a board_id via Pinterest API v5."""
    if board_value.isdigit():
        return board_value

    params = {"page_size": 100}
    for _ in range(10):
        response = requests.get(
            f"{API_BASE}/boards",
            headers=_v5_headers(access_token),
            params=params,
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        for board in payload.get("items", []):
            if str(board.get("name") or "").strip().casefold() == board_value.casefold():
                logger.info("Resolved board '%s' to id %s via API v5", board_value, board.get("id"))
                return str(board["id"])
        bookmark = payload.get("bookmark")
        if not bookmark:
            break
        params["bookmark"] = bookmark

    raise RuntimeError(
        f"Pinterest board '{board_value}' was not found through API v5. Check the board name "
        "and that the token carries the boards:read and pins:write scopes."
    )


def _v5_create_pin(
    access_token: str,
    board_value: str,
    image_path,
    title: str,
    description: str,
    alt_text: str,
    logger,
) -> str:
    """Create a pin via Pinterest API v5 (image sent as base64)."""
    board_id = _v5_board_id(access_token, board_value, logger)
    content_type = mimetypes.guess_type(str(image_path))[0] or "image/png"
    payload = {
        "board_id": board_id,
        "title": title,
        "description": description,
        "alt_text": alt_text,
        "media_source": {
            "source_type": "image_base64",
            "content_type": content_type,
            "data": base64.b64encode(image_path.read_bytes()).decode("ascii"),
        },
    }
    response = requests.post(
        f"{API_BASE}/pins",
        headers=_v5_headers(access_token),
        json=payload,
        timeout=60,
    )
    response.raise_for_status()
    pin_id = response.json().get("id")
    logger.info("Pin created through API v5")
    return f"https://www.pinterest.com/pin/{pin_id}/" if pin_id else None


def _board_value(row: dict) -> str:
    return (row.get("pinterest_board") or "").strip() or config.PINTEREST_DEFAULT_BOARD


# ---------------------------------------------------------------------------
# Unofficial route (py3-pinterest)
# ---------------------------------------------------------------------------
def _session(logger: logging.Logger, force_login: bool = False):
    """Return a logged-in py3-pinterest client, reusing cached cookies."""
    from py3pin.Pinterest import Pinterest

    if not (config.PINTEREST_EMAIL and config.PINTEREST_PASSWORD):
        raise RuntimeError(
            "Pinterest credentials are missing: set the PINTEREST_EMAIL and "
            "PINTEREST_PASSWORD repository secrets (or PINTEREST_ACCESS_TOKEN)."
        )

    config.PINTEREST_CRED_ROOT.mkdir(parents=True, exist_ok=True)
    pinterest = Pinterest(
        email=config.PINTEREST_EMAIL,
        password=config.PINTEREST_PASSWORD,
        cred_root=str(config.PINTEREST_CRED_ROOT),
    )
    if config.PINTEREST_USERNAME:
        # py3-pinterest uses ``username`` when listing boards for the account.
        pinterest.username = config.PINTEREST_USERNAME

    cached_cookies = pinterest.http.cookies.get_dict() if hasattr(pinterest, "http") else {}
    if cached_cookies and not force_login:
        logger.info(
            "Reusing %d cached Pinterest cookie(s) from %s (no Chrome login needed)",
            len(cached_cookies),
            config.PINTEREST_CRED_ROOT,
        )
        return pinterest

    logger.info(
        "Launching headless Chrome to log in to Pinterest as %s (this can take a minute)",
        config.PINTEREST_EMAIL,
    )
    pinterest.login(headless=True, wait_time=45)

    if not pinterest.http.cookies.get_dict():
        raise RuntimeError(
            "Pinterest login did not return any cookies. Pinterest may be showing a "
            "captcha or asking for email verification - log in once in a normal "
            "browser, or switch to PINTEREST_ACCESS_TOKEN (official API v5)."
        )
    logger.info("Pinterest login successful; cookies cached for future runs")
    return pinterest


def _list_boards(pinterest, username: str, max_pages: int = 5) -> list:
    """Collect the account's boards (the endpoint is paginated)."""
    boards, seen = [], set()
    for _ in range(max_pages):
        batch = pinterest.boards(username=username or None, page_size=100)
        if not batch:
            break
        added = 0
        for board in batch:
            board_id = str(board.get("id") or "")
            if board_id and board_id not in seen:
                seen.add(board_id)
                boards.append(board)
                added += 1
        if len(batch) < 100 or not added:
            break
    return boards


def _resolve_username(pinterest, logger: logging.Logger) -> str:
    """Find the logged-in handle so boards can be listed by name."""
    if config.PINTEREST_USERNAME:
        pinterest.username = config.PINTEREST_USERNAME
        return config.PINTEREST_USERNAME

    try:
        overview = pinterest.get_user_overview()
        username = str(overview.get("username") or "")
    except Exception as exc:  # noqa: BLE001 - fall through to the warning below
        logger.debug("Could not read the Pinterest profile: %s", exc)
        username = ""

    if username:
        pinterest.username = username
        logger.info("Detected Pinterest username '%s' from the logged-in session", username)
    else:
        logger.warning(
            "PINTEREST_USERNAME is not set - boards can only be found if you put a "
            "numeric board id in content/queue.csv"
        )
    return username


def _resolve_board_id(pinterest, board_value: str, logger: logging.Logger) -> str:
    """Turn ``pinterest_board`` (a name, or a raw id) into a board id."""
    if board_value.isdigit():
        logger.info("Using Pinterest board id %s straight from the queue", board_value)
        return board_value

    try:
        boards = _list_boards(pinterest, _resolve_username(pinterest, logger))
    except Exception as exc:  # noqa: BLE001 - re-raised with actionable advice
        raise RuntimeError(
            f"Could not list Pinterest boards ({exc}). Set the PINTEREST_USERNAME secret "
            f"to your Pinterest handle (the part after pinterest.com/) so the board "
            f"'{board_value}' can be found, or put a numeric board id in the queue."
        ) from exc

    for board in boards:
        if str(board.get("name") or "").strip().casefold() == board_value.casefold():
            logger.info("Resolved board '%s' to id %s", board.get("name"), board.get("id"))
            return str(board.get("id"))
        url = str(board.get("url") or "").rstrip("/")
        if url and url.endswith("/" + board_value):
            logger.info("Resolved board url %s to id %s", url, board.get("id"))
            return str(board.get("id"))

    available = ", ".join(sorted(str(board.get("name")) for board in boards)) or "none returned"
    raise RuntimeError(
        f"Pinterest board '{board_value}' was not found. Boards visible to this account: {available}"
    )


def _upload_pin(pinterest, board_value, image_path, title, description, alt_text, logger):
    board_id = _resolve_board_id(pinterest, board_value, logger)
    logger.info("Creating pin on board id %s with %s", board_id, image_path.name)
    return pinterest.upload_pin(
        board_id=board_id,
        image_file=str(image_path),
        description=description,
        title=title,
        alt_text=alt_text,
    )


def _pin_url(response, logger: logging.Logger) -> Optional[str]:
    """Best-effort extraction of the new pin's URL from py3-pinterest's response."""
    data = response if isinstance(response, dict) else None
    if data is None:
        try:
            data = response.json()
        except Exception:  # noqa: BLE001 - the pin may still have been created
            data = None

    if isinstance(data, dict):
        payload = data.get("resource_response", {}).get("data")
        pin_id = payload.get("id") if isinstance(payload, dict) else payload
        if isinstance(pin_id, str) and pin_id:
            return f"https://www.pinterest.com/pin/{pin_id}/"

    logger.info("Pin was created but Pinterest did not return a pin id in a known shape")
    return None


def _looks_like_auth_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in _AUTH_ERROR_MARKERS)


# ---------------------------------------------------------------------------
# Official route (Pinterest API v5) - opt-in via PINTEREST_ACCESS_TOKEN
# ---------------------------------------------------------------------------
def _v5_headers() -> dict:
    return {"Authorization": f"Bearer {config.PINTEREST_ACCESS_TOKEN}"}


def _v5_board_id(board_value: str, logger: logging.Logger) -> str:
    import requests

    if board_value.isdigit():
        return board_value

    params = {"page_size": 100}
    for _ in range(10):
        response = requests.get(
            f"{API_BASE}/boards", headers=_v5_headers(), params=params, timeout=30
        )
        response.raise_for_status()
        payload = response.json()
        for board in payload.get("items", []):
            if str(board.get("name") or "").strip().casefold() == board_value.casefold():
                logger.info("Resolved board '%s' to id %s via API v5", board_value, board.get("id"))
                return str(board["id"])
        bookmark = payload.get("bookmark")
        if not bookmark:
            break
        params["bookmark"] = bookmark

    raise RuntimeError(
        f"Pinterest board '{board_value}' was not found through API v5. Check the board name "
        "and that the token carries the boards:read and pins:write scopes."
    )


def _v5_create_pin(board_value, image_path, title, description, alt_text, logger) -> Optional[str]:
    """Create a pin with the documented API (image is sent as base64)."""
    import requests

    board_id = _v5_board_id(board_value, logger)
    content_type = mimetypes.guess_type(str(image_path))[0] or "image/png"
    payload = {
        "board_id": board_id,
        "title": title,
        "description": description,
        "alt_text": alt_text,
        "media_source": {
            "source_type": "image_base64",
            "content_type": content_type,
            "data": base64.b64encode(image_path.read_bytes()).decode("ascii"),
        },
    }
    headers = {**_v5_headers(), "Content-Type": "application/json"}
    response = requests.post(f"{API_BASE}/pins", headers=headers, json=payload, timeout=60)
    response.raise_for_status()
    pin_id = response.json().get("id")
    logger.info("Pin created through API v5")
    return f"https://www.pinterest.com/pin/{pin_id}/" if pin_id else None


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------
def post(row: dict, logger: Optional[logging.Logger] = None, dry_run: bool = False) -> common.PostResult:
    """Publish a single queue row to Pinterest. Never raises."""
    logger = logger or get_logger("pinterest")
    row_id = str(row.get("id", ""))

    try:
        image_path = common.resolve_item_image(row)
        board_value = _board_value(row)
        title = common.derive_title(
            row.get("caption", ""), limit=config.PINTEREST_TITLE_LIMIT, soft_limit=60
        )
        description = common.build_caption(
            row.get("caption", ""),
            row.get("hashtags", ""),
            limit=config.PINTEREST_DESCRIPTION_LIMIT,
            logger=logger,
        )
        alt_text = common.truncate(row.get("alt_text", ""), config.PINTEREST_ALT_TEXT_LIMIT)

        logger.info(
            "Pinterest plan: board=%s image=%s title=%r (%d description chars)",
            board_value,
            image_path.name,
            title,
            len(description),
        )

        if dry_run:
            logger.info("[dry-run] Description that would be posted:\n%s", description)
            logger.info("[dry-run] No Pinterest request was made and the queue was not modified")
            return common.PostResult(
                platform=PLATFORM,
                status=common.DRY_RUN,
                message=f"preview of {image_path.name}",
                row_id=row_id,
            )

        if config.PINTEREST_ACCESS_TOKEN:
            logger.info("Using the official Pinterest API v5 (PINTEREST_ACCESS_TOKEN is set)")
            common.human_delay(config.PINTEREST_DELAY_RANGE, logger=logger, reason="the Pinterest pin")
            url = _v5_create_pin(board_value, image_path, title, description, alt_text, logger)
        else:
            common.human_delay(config.PINTEREST_DELAY_RANGE, logger=logger, reason="the Pinterest pin")
            session = _session(logger)
            try:
                response = _upload_pin(
                    session, board_value, image_path, title, description, alt_text, logger
                )
            except Exception as exc:  # noqa: BLE001 - retry once with a fresh login
                if not _looks_like_auth_error(exc):
                    raise
                logger.warning(
                    "Pinterest rejected the cached session (%s); logging in again via Chrome", exc
                )
                session = _session(logger, force_login=True)
                response = _upload_pin(
                    session, board_value, image_path, title, description, alt_text, logger
                )
            url = _pin_url(response, logger)

        common.human_delay(config.PINTEREST_DELAY_RANGE, logger=logger, reason="finishing the run")
        logger.info("Pinterest pin published: %s", url or "(no pin url returned)")
        return common.PostResult(
            platform=PLATFORM, status=common.POSTED, message="published", row_id=row_id, url=url
        )

    except Exception as exc:  # noqa: BLE001 - a failed pin must never crash the workflow
        hint = ""
        text = str(exc).lower()
        if "captcha" in text:
            hint = " | Pinterest is showing a captcha: log in once manually or use PINTEREST_ACCESS_TOKEN."
        elif "board" in text and "not found" in text:
            hint = " | Check pinterest_board in content/queue.csv and the PINTEREST_USERNAME secret."
        elif "429" in text or "rate" in text:
            hint = " | Pinterest is throttling: lower PINTEREST_DAILY_LIMIT and retry tomorrow."
        logger.exception("Pinterest posting failed for row %s", row_id or "?")
        return common.PostResult(
            platform=PLATFORM,
            status=common.FAILED,
            message=f"{type(exc).__name__}: {exc}{hint}",
            row_id=row_id,
        )


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="Post the next queued artwork to Pinterest.")
    parser.add_argument("--dry-run", action="store_true", help="preview only, no Pinterest request")
    parser.add_argument(
        "--max-items", type=int, default=1, help="how many queued rows to pin in this run (default 1)"
    )
    args = parser.parse_args(argv)

    config.ensure_directories()
    logger = get_logger("pinterest")
    dry_run = bool(args.dry_run or config.DRY_RUN)

    log_banner(logger, "SocialArtzy - Pinterest run")
    if dry_run:
        logger.info("DRY RUN: nothing will be pinned and the queue stays untouched")

    results = run_platform(
        PLATFORM,
        post,
        logger=logger,
        max_items=max(1, args.max_items),
        dry_run=dry_run,
    )

    logger.info("Pinterest summary:\n%s", common.format_results(results))
    return 1 if any(result.failed for result in results) else 0


if __name__ == "__main__":
    sys.exit(main())
