"""The posting loop shared by both platform scripts.

``run_platform`` is intentionally small and platform agnostic: it enforces the
daily quota, picks the first pending queue row, calls the platform poster and
only marks the row as posted when the platform confirms success.
"""

from __future__ import annotations

import logging
from typing import Callable, List, Optional

from . import common, queue_manager
from .rate_limiter import DailyCounter

# A poster takes (row, logger, dry_run) and returns a PostResult.
Poster = Callable[..., common.PostResult]


def run_platform(
    platform: str,
    poster: Poster,
    *,
    logger: logging.Logger,
    max_items: int = 1,
    dry_run: bool = False,
    counter: Optional[DailyCounter] = None,
) -> List[common.PostResult]:
    """Post up to ``max_items`` queued rows to ``platform``.

    Stops early when the daily quota is reached, the queue has nothing pending,
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

    for _ in range(max(1, int(max_items))):
        if not counter.can_post(platform):
            message = (
                f"daily {platform} limit reached ({counter.count(platform)}/{limit}); "
                "skipping to avoid an account flag"
            )
            logger.warning(message)
            results.append(common.PostResult(platform=platform, status=common.SKIPPED, message=message))
            break

        rows = queue_manager.read_queue()
        row = queue_manager.find_next(rows, platform)
        if row is None:
            message = "no pending rows in content/queue.csv"
            logger.info("%s: %s", platform, message)
            results.append(common.PostResult(platform=platform, status=common.SKIPPED, message=message))
            break

        logger.info("Selected %s row: %s", platform, common.describe_row(row))
        result = poster(row, logger=logger, dry_run=dry_run)
        results.append(result)

        if result.posted:
            if queue_manager.mark_posted_in_file(row.get("id", ""), platform):
                count = counter.record(platform, row_id=row.get("id", ""), detail=result.url or "")
                logger.info(
                    "Marked row %s as posted to %s (%d/%d today)",
                    row.get("id"),
                    platform,
                    count,
                    limit,
                )
            else:
                logger.error(
                    "Posted row %s to %s but could not update content/queue.csv - "
                    "mark it manually to avoid a duplicate post",
                    row.get("id"),
                    platform,
                )
        elif result.failed:
            logger.error("%s posting failed, stopping this platform for now: %s", platform, result.message)
            break

        if dry_run:
            break  # one preview per platform is enough

    return results