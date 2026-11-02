"""SocialArtzy entry point - the command GitHub Actions runs once a day."""

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
    import post_instagram
    import post_pinterest
    return {"instagram": post_instagram.post, "pinterest": post_pinterest.post}


def _log_queue_status(logger: logging.Logger, items: List[dict]) -> None:
    counter = DailyCounter()
    snapshot = counter.snapshot()
    for platform in PLATFORM_ORDER:
        info = snapshot.get(platform, {"count": 0, "limit": 0})
        pending = 0
        for item in items:
            if platform in queue_manager.platforms_for(item):
                pending += 1
                
        logger.info(
            "Queue status: %s -> %d pending, %d/%d posts used today",
            platform, pending, info["count"], info["limit"],
        )


def _run_check(items: List[dict], problems: List[str], logger: logging.Logger) -> int:
    if problems:
        logger.error("Queue check found %d problem(s):", len(problems))
        for problem in problems:
            logger.error("  - %s", problem)
        return 1

    logger.info("Queue check passed: %d item(s), all images present", len(items))
    
    pending = {}
    for platform in PLATFORM_ORDER:
        pending[platform] = sum(1 for item in items if platform in queue_manager.platforms_for(item))
            
    if not any(pending.values()):
        logger.warning("Nothing is pending - add items to content/ via TinaCMS to keep posting")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Post the next queued artwork to Instagram and/or Pinterest.")
    parser.add_argument("--platform", choices=("all",) + PLATFORM_ORDER, default="all")
    parser.add_argument("--max-items", type=int, default=1)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    config.ensure_directories()
    logger = get_logger("artbot")
    dry_run = bool(args.dry_run or config.DRY_RUN)

    log_banner(logger, "SocialArtzy daily run")
    logger.info(
        "Configuration: IG delay=%s-%ss limit=%d/day, Pinterest delay=%s-%ss limit=%d/day",
        *config.IG_DELAY_RANGE, config.IG_DAILY_LIMIT,
        *config.PINTEREST_DELAY_RANGE, config.PINTEREST_DAILY_LIMIT,
    )

    try:
        # THE FIX IS HERE: Using scan_content() instead of read_queue()
        items = queue_manager.scan_content()
    except Exception as exc:
        logger.error("Failed to scan content: %s", exc)
        return 1

    problems = queue_manager.validate(items, logger)
    _log_queue_status(logger, items)

    if args.check:
        return _run_check(items, problems, logger)

    if problems:
        logger.warning("Queue has %d problem(s); the affected items may be skipped:", len(problems))
        for problem in problems:
            logger.warning("  - %s", problem)

    if dry_run:
        logger.info("DRY RUN: no credentials are used and content files will not change")

    platforms = PLATFORM_ORDER if args.platform == "all" else (args.platform,)
    posters = _load_posters()

    results: List[common.PostResult] = []
    for platform in platforms:
        try:
            results.extend(
                run_platform(
                    platform, posters[platform], logger=logger,
                    max_items=max(1, args.max_items), dry_run=dry_run,
                )
            )
        except Exception: 
            logger.exception("Unexpected error while running the %s step", platform)
            results.append(
                common.PostResult(
                    platform=platform, status=common.FAILED,
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
