"""SocialArtzy entry point - the command GitHub Actions runs once a day.

Usage
-----
    python run_bot.py                              # one post per platform
    python run_bot.py --platform instagram         # single platform
    python run_bot.py --max-items 2                # allow up to two per platform
    python run_bot.py --dry-run                    # preview, no credentials needed
    python run_bot.py --check                      # validate the queue only

Exit codes: ``0`` = everything fine (including "queue empty" / "quota used"),
``1`` = at least one platform reported a failure, which turns the Actions run
red so you notice it in the GitHub UI.
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import Dict, List, Optional

from artbot import common, config, queue_manager
from artbot.logging_utils import get_logger, log_banner
from artbot.rate_limiter import DailyCounter
from artbot.runner import run_platform

PLATFORM_ORDER = ("instagram", "pinterest")


def _load_posters() -> Dict[str, callable]:
    # Imported lazily so ``--check`` and ``--dry-run`` never need the
    # Instagram/Pinterest client libraries to be importable.
    import post_instagram
    import post_pinterest

    return {"instagram": post_instagram.post, "pinterest": post_pinterest.post}


def _log_queue_status(logger: logging.Logger, rows: List[dict]) -> None:
    counter = DailyCounter()
    snapshot = counter.snapshot()
    for platform in PLATFORM_ORDER:
        info = snapshot.get(platform, {"count": 0, "limit": 0})
        logger.info(
            "Queue status: %s -> %d pending, %d/%d posts used today",
            platform,
            queue_manager.pending_count(rows, platform),
            info["count"],
            info["limit"],
        )


def _run_check(rows: List[dict], problems: List[str], logger: logging.Logger) -> int:
    if problems:
        logger.error("Queue check found %d problem(s):", len(problems))
        for problem in problems:
            logger.error("  - %s", problem)
        return 1

    logger.info("Queue check passed: %d row(s), all images present", len(rows))
    pending = {platform: queue_manager.pending_count(rows, platform) for platform in PLATFORM_ORDER}
    if not any(pending.values()):
        logger.warning("Nothing is pending - add rows to content/queue.csv to keep posting")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Post the next queued artwork to Instagram and/or Pinterest.")
    parser.add_argument(
        "--platform",
        choices=("all",) + PLATFORM_ORDER,
        default="all",
        help="which platform(s) to run (default: all)",
    )
    parser.add_argument(
        "--max-items",
        type=int,
        default=1,
        help="maximum posts per platform in this run (default: 1, the safest cadence)",
    )
    parser.add_argument("--dry-run", action="store_true", help="preview only: no network calls, no queue changes")
    parser.add_argument("--check", action="store_true", help="validate content/queue.csv and exit")
    args = parser.parse_args(argv)

    config.ensure_directories()
    logger = get_logger("artbot")
    dry_run = bool(args.dry_run or config.DRY_RUN)

    log_banner(logger, "SocialArtzy daily run")
    logger.info(
        "Configuration: IG delay=%s-%ss limit=%d/day, Pinterest delay=%s-%ss limit=%d/day",
        *config.IG_DELAY_RANGE,
        config.IG_DAILY_LIMIT,
        *config.PINTEREST_DELAY_RANGE,
        config.PINTEREST_DAILY_LIMIT,
    )

    try:
        rows = queue_manager.read_queue()
    except FileNotFoundError as exc:
        logger.error("%s", exc)
        return 1

    problems = queue_manager.validate(rows, logger)
    _log_queue_status(logger, rows)

    if args.check:
        return _run_check(rows, problems, logger)

    if problems:
        logger.warning("Queue has %d problem(s); the affected rows may be skipped:", len(problems))
        for problem in problems:
            logger.warning("  - %s", problem)

    if dry_run:
        logger.info("DRY RUN: no credentials are used and content/queue.csv will not change")

    platforms = PLATFORM_ORDER if args.platform == "all" else (args.platform,)
    posters = _load_posters()

    results: List[common.PostResult] = []
    for platform in platforms:
        try:
            results.extend(
                run_platform(
                    platform,
                    posters[platform],
                    logger=logger,
                    max_items=max(1, args.max_items),
                    dry_run=dry_run,
                )
            )
        except Exception:  # noqa: BLE001 - one broken platform must not block the other
            logger.exception("Unexpected error while running the %s step", platform)
            results.append(
                common.PostResult(
                    platform=platform,
                    status=common.FAILED,
                    message="unhandled exception, see traceback above",
                )
            )

    logger.info("Run summary:\n%s", common.format_results(results))
    failures = [result for result in results if result.failed]
    if failures:
        logger.error("%d platform(s) reported a failure - check logs/posting.log above", len(failures))
        return 1

    logger.info("Run finished without errors")
    return 0


if __name__ == "__main__":
    sys.exit(main())