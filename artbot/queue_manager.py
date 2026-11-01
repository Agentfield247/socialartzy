"""JSON content queue handling.

The bot now scans "content/sketches/*.json" and "content/artworks/*.json"
instead of "content/queue.csv". Each JSON item describes one artwork and
carries flags maintained by the bot:

* "posted" (bool)       - overall: true when every applicable platform is done
* "posted_at" (str)     - UTC ISO-8601 timestamp of the last platform post
* "posted_instagram" (bool) - Instagram-specific (bot-maintained)
* "posted_pinterest" (bool) - Pinterest-specific (bot-maintained)

Writes are atomic (temp file + "os.replace") because GitHub Actions may kill
the job at any moment.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

from . import common, config

PLATFORMS = ("instagram", "pinterest")


def _read_json_file(path: Path) -> Optional[Dict]:
    """Read and parse a single JSON content file."""
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None
    return None


def scan_content() -> List[Dict]:
    """Scan all JSON content directories and return item dicts.

    Each returned dict includes every field from the JSON file plus:
    * "filepath" - absolute path to the source JSON file
    * "slug" - filename without extension
    """
    items: List[Dict] = []
    for content_dir in config.CONTENT_DIRS:
        if not content_dir.is_dir():
            continue
        for json_file in sorted(content_dir.glob("*.json")):
            data = _read_json_file(json_file)
            if data is None:
                continue
            data["filepath"] = str(json_file)
            data["slug"] = json_file.stem
            # Ensure bot-maintained fields exist with safe defaults
            data.setdefault("posted", False)
            data.setdefault("posted_at", None)
            data.setdefault("posted_instagram", False)
            data.setdefault("posted_pinterest", False)
            items.append(data)
    return items


def platforms_for(item: Dict) -> List[str]:
    """Determine which platforms this item should be posted to.

    Instagram:  only if "post_to_instagram" is not explicitly False
    Pinterest:  only if "pinterest_board" is a non-empty string
    """
    targets: List[str] = []

    post_to_ig = item.get("post_to_instagram")
    if post_to_ig is not False:
        targets.append("instagram")

    board = (item.get("pinterest_board") or "").strip()
    if board:
        targets.append("pinterest")

    return targets


def is_posted(item: Dict) -> bool:
    """True when the item's "posted" flag is truthy."""
    return bool(item.get("posted"))


def is_platform_posted(item: Dict, platform: str) -> bool:
    """True when this item was already published on "platform"."""
    return bool(item.get(f"posted_{platform}", False))


def is_pending_for(item: Dict, platform: str) -> bool:
    """True when the item still needs to be posted to "platform"."""
    return (
        not is_posted(item)
        and platform in platforms_for(item)
        and not is_platform_posted(item, platform)
    )


def find_next(items: List[Dict], platform: str) -> Optional[Dict]:
    """Return the first item that still needs to be posted to "platform"."""
    for item in items:
        if is_pending_for(item, platform):
            return item
    return None


def pending_count(items: List[Dict], platform: str) -> int:
    return sum(1 for item in items if is_pending_for(item, platform))


def mark_platform_posted_in_file(
    item: Dict,
    platform: str,
    timestamp: Optional[str] = None,
) -> bool:
    """Mark "item" as posted on "platform" in its JSON file.

    Also sets "posted_at". Sets the overall "posted" flag to true only
    when every applicable platform has been posted.

    Returns "True" when the file was found and updated.
    """
    filepath = item.get("filepath")
    if not filepath or not Path(filepath).is_file():
        return False

    ts = timestamp or config.utc_now()

    try:
        with Path(filepath).open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return False

    data[f"posted_{platform}"] = True
    data["posted_at"] = ts

    # Determine if all applicable platforms are done
    applicable = platforms_for(data)
    all_done = all(data.get(f"posted_{p}", False) for p in applicable)
    if all_done:
        data["posted"] = True

    # Write atomically
    handle_fd, tmp_name = tempfile.mkstemp(
        dir=str(Path(filepath).parent), prefix=".item-", suffix=".json", text=True
    )
    try:
        with os.fdopen(handle_fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.write("\\n")
        os.replace(tmp_name, filepath)
    except BaseException:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
        raise

    # Update the in-memory item too
    item[f"posted_{platform}"] = True
    item["posted_at"] = ts
    if all_done:
        item["posted"] = True

    return True


def validate(items: List[Dict], logger: Optional[logging.Logger] = None) -> List[str]:
    """Return a list of human readable problems found in the content items."""
    problems: List[str] = []

    for item in items:
        slug = item.get("slug", "?")
        filepath = item.get("filepath", "")
        label = f"{filepath} (slug={slug})"

        if not (item.get("caption") or "").strip():
            problems.append(f"{label}: caption is empty")

        if not (item.get("alt_text") or "").strip():
            problems.append(f"{label}: alt_text is required")

        try:
            common.resolve_item_image(item.get("image", ""))
        except (ValueError, FileNotFoundError) as exc:
            problems.append(f"{label}: {exc}")

        applicable = platforms_for(item)
        if not applicable:
            problems.append(
                f"{label}: no target platforms (post_to_instagram=false and "
                f"no pinterest_board)"
            )

    if not problems and logger:
        logger.info("Content validation passed for %d item(s)", len(items))
    return problems
