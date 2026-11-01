"""CSV queue handling.

``content/queue.csv`` is the single source of truth for what still needs to be
posted. Each row carries per-platform flags (``posted_instagram`` /
``posted_pinterest``) so a row with ``platform=both`` can be published to
Instagram first and Pinterest later without being posted twice.

Writes are atomic (temp file + ``os.replace``) because GitHub Actions may kill
the job at any moment; a half written queue would be committed back to the repo.
"""

from __future__ import annotations

import csv
import logging
import os
import tempfile
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from . import common, config

# Columns that describe the content
BASE_FIELDS = [
    "id",
    "platform",
    "image_filename",
    "caption",
    "alt_text",
    "hashtags",
    "pinterest_board",
]
# Columns the bot maintains to prevent double posting
FLAG_FIELDS = ["posted_instagram", "posted_pinterest", "posted", "posted_at"]
FIELD_NAMES = BASE_FIELDS + FLAG_FIELDS

PLATFORMS = ("instagram", "pinterest")

_PLATFORM_ALIASES = {
    "both": "both",
    "all": "both",
    "everywhere": "both",
    "instagram": "instagram",
    "ig": "instagram",
    "insta": "instagram",
    "pinterest": "pinterest",
    "pin": "pinterest",
    "pins": "pinterest",
}

_TRUTHY = {"1", "true", "yes", "y", "x", "done", "posted"}


def normalize_platform(value: str) -> str:
    """Map loose platform spellings (``ig``, ``pins``...) to canonical names."""
    key = (value or "").strip().lower()
    return _PLATFORM_ALIASES.get(key, key)


def is_truthy(value: str) -> bool:
    return (value or "").strip().lower() in _TRUTHY


def read_queue(path: Optional[Path] = None) -> List[Dict[str, str]]:
    """Read the queue into a list of normalised dictionaries."""
    queue_path = Path(path or config.QUEUE_FILE)
    if not queue_path.is_file():
        raise FileNotFoundError(f"Queue file not found: {queue_path}")

    with queue_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows: List[Dict[str, str]] = []
        for raw in reader:
            if not any((value or "").strip() for value in raw.values()):
                continue  # skip blank lines
            rows.append({field: (raw.get(field) or "").strip() for field in FIELD_NAMES})
    return rows


def write_queue(rows: Iterable[Dict[str, str]], path: Optional[Path] = None) -> None:
    """Write the queue back atomically, preserving all known columns."""
    queue_path = Path(path or config.QUEUE_FILE)
    queue_path.parent.mkdir(parents=True, exist_ok=True)

    handle_fd, tmp_name = tempfile.mkstemp(
        dir=str(queue_path.parent), prefix=".queue-", suffix=".csv", text=True
    )
    try:
        with os.fdopen(handle_fd, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=FIELD_NAMES,
                extrasaction="ignore",
                lineterminator="\n",
            )
            writer.writeheader()
            for row in rows:
                writer.writerow({field: row.get(field, "") for field in FIELD_NAMES})
        os.replace(tmp_name, queue_path)
    except BaseException:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
        raise


def platforms_for(row: Dict[str, str]) -> List[str]:
    """Which platforms this row must be published to."""
    platform = normalize_platform(row.get("platform", ""))
    if platform == "both":
        return list(PLATFORMS)
    if platform in PLATFORMS:
        return [platform]
    return []


def is_posted(row: Dict[str, str], platform: str) -> bool:
    """True when this row was already published on ``platform``."""
    if is_truthy(row.get(f"posted_{platform}", "")):
        return True
    # ``posted`` is the manual kill switch: true means "never touch this row".
    return is_truthy(row.get("posted", ""))


def is_pending(row: Dict[str, str], platform: str) -> bool:
    return platform in platforms_for(row) and not is_posted(row, platform)


def find_next(rows: Iterable[Dict[str, str]], platform: str) -> Optional[Dict[str, str]]:
    """Return the first row that still needs to be posted to ``platform``."""
    for row in rows:
        if is_pending(row, platform):
            return row
    return None


def pending_count(rows: Iterable[Dict[str, str]], platform: str) -> int:
    return sum(1 for row in rows if is_pending(row, platform))


def mark_posted(
    row: Dict[str, str], platform: str, timestamp: Optional[str] = None
) -> Dict[str, str]:
    """Flag ``row`` as posted on ``platform`` (mutates and returns the row)."""
    row[f"posted_{platform}"] = "true"
    done_everywhere = all(is_truthy(row.get(f"posted_{name}", "")) for name in platforms_for(row))
    row["posted"] = "true" if done_everywhere else "false"
    row["posted_at"] = timestamp or config.utc_now()
    return row


def mark_posted_in_file(
    row_id: str,
    platform: str,
    path: Optional[Path] = None,
    timestamp: Optional[str] = None,
) -> bool:
    """Mark a row as posted by id, re-reading the file first (safe merging).

    Returns ``True`` when the row was found and updated.
    """
    rows = read_queue(path)
    for row in rows:
        if row.get("id", "").strip() == str(row_id).strip():
            mark_posted(row, platform, timestamp)
            write_queue(rows, path)
            return True
    return False


def validate(rows: List[Dict[str, str]], logger: Optional[logging.Logger] = None) -> List[str]:
    """Return a list of human readable problems found in the queue."""
    problems: List[str] = []
    seen_ids = set()

    for index, row in enumerate(rows, start=2):  # start=2: line 1 is the header
        row_id = row.get("id", "").strip()
        label = f"line {index} (id={row_id or 'missing'})"

        if not row_id:
            problems.append(f"{label}: id is required")
        elif row_id in seen_ids:
            problems.append(f"{label}: duplicate id")
        seen_ids.add(row_id)

        if not platforms_for(row):
            problems.append(
                f"{label}: platform must be 'both', 'instagram' or 'pinterest' "
                f"(got {row.get('platform')!r})"
            )

        if not (row.get("caption") or "").strip():
            problems.append(f"{label}: caption is empty")

        try:
            common.resolve_image(row.get("image_filename", ""))
        except (ValueError, FileNotFoundError) as exc:
            problems.append(f"{label}: {exc}")

        if "pinterest" in platforms_for(row) and not (
            (row.get("pinterest_board") or "").strip() or config.PINTEREST_DEFAULT_BOARD
        ):
            problems.append(f"{label}: pinterest_board is empty and no default board is configured")

    if not problems and logger:
        logger.info("Queue validation passed for %d row(s)", len(seen_ids))
    return problems