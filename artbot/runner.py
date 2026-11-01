"""The posting loop shared by both platform scripts.

``run_platform`` is intentionally small and platform agnostic: it enforces the
daily quota, picks the first pending JSON content item for ``platform``,
calls the platform poster and only marks the item as posted on that platform
when the platform confirms success.

Overall ``posted: true`` is set only when every applicable platform for an
item has succeeded.
"""

from __future__ import annotations

import logging
from typing import Callable, List, Optional

from . import common, config, queue_manager
from .rate_limiter import DailyCounter

# A poster takes (item, logger, dry_run) and returns a PostResult.
Poster = Callable[..., common.PostResult]


def _describe_item(item: dict) -> str:
    """Compact one-line description of a content item for the log."""
    return (
        f"slug={item.get('slug', '?')} "
        f"platforms={','.join(queue_manager.platforms_for(item))} "
        f"image={item.get('image', '?')}"
    )


def run_platform(
    platform: str,
    poster: Poster,
    *,
    logger: logging.Logger,
    max_items: int = 1,
    dry_run: bool = False,
    counter: Optional[DailyCounter] = None,
) -> List[common.PostResult]:
    """Post up to ``max_items`` queued items to ``platform``.

    Stops early when the daily quota is reached, no pending items remain,
    or a post fails (so a broken credential never triggers a burst of retries).
    """
    counter = counter or DailyCounter()
    results: List[common.PostResult] = []
    limit = counter.limit(platform)

    logger.info(
        "%s: %d/%d posts already used today (daily limit %d)",
        platform,
        counter.count(platform),
        limit,
        limit,
    )

    items = queue_manager.scan_content()

    for _ in range(max(1, int(max_items))):
        if not counter.can_post(platform):
            message = (
                f"daily {platform} limit reached ({counter.count(platform)}/{limit}); "
                "skipping to avoid an account flag"
            )
            logger.warning(message)
            results.append(common.PostResult(platform=platform, status=common.SKIPPED, message=message))
            break

        item = queue_manager.find_next(items, platform)
        if item is None:
            message = f"no pending {platform} items in content/sketches/ or content/artworks/"
            logger.info("%s: %s", platform, message)
            results.append(common.PostResult(platform=platform, status=common.SKIPPED, message=message))
            break

        logger.info("Selected %s item: %s", platform, _describe_item(item))
        result = poster(item, logger=logger, dry_run=dry_run)
        results.append(result)

        if result.posted:
            if queue_manager.mark_platform_posted_in_file(item, platform):
                count = counter.record(platform, row_id=item.get("slug", ""), detail=result.url or "")
                logger.info(
                    "Marked item %s as posted to %s (%d/%d today)",
                    item.get("slug"),
                    platform,
                    count,
                    limit,
                )
                # Re-scan so the next iteration sees the updated posted flags
                items = queue_manager.scan_content()
            else:
                logger.error(
                    "Posted item %s to %s but could not update its JSON file - "
                    "mark it manually to avoid a duplicate post",
                    item.get("slug"),
                    platform,
                )
        elif result.failed:
            logger.error("%s posting failed, stopping this platform for now: %s", platform, result.message)
            break

        if dry_run:
            break  # one preview per platform is enough

    return results