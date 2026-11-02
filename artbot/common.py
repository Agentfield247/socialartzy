"""Shared helpers used by both platforms."""

from __future__ import annotations

import logging
import random
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Sequence

from . import config

POSTED = "posted"
SKIPPED = "skipped"
FAILED = "failed"
DRY_RUN = "dry_run"


@dataclass
class PostResult:
    """Outcome of a single posting attempt."""

    platform: str
    status: str
    message: str = ""
    row_id: str = ""
    url: Optional[str] = None

    @property
    def posted(self) -> bool:
        """True only when something really went live on the platform."""
        return self.status == POSTED

    @property
    def failed(self) -> bool:
        return self.status == FAILED


def human_delay(
    delay_range: Sequence[int],
    *,
    logger: logging.Logger,
    reason: str = "the next action",
    dry_run: bool = False,
) -> float:
    """Sleep for a random number of seconds inside ``delay_range``."""
    low, high = int(delay_range[0]), int(delay_range[1])
    seconds = round(random.uniform(low, high), 1)

    if dry_run:
        logger.info("[dry-run] Would wait %.1fs before %s", seconds, reason)
        return 0.0

    logger.info("Waiting %.1fs before %s (human-like pacing)", seconds, reason)
    time.sleep(seconds)
    return seconds


def truncate(text: str, limit: int) -> str:
    """Trim ``text`` to at most ``limit`` characters on a word boundary."""
    text = (text or "").strip()
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    if limit <= 3:
        return text[:limit]
    clipped = text[: limit - 3]
    if " " in clipped:
        clipped = clipped.rsplit(" ", 1)[0]
    return clipped.rstrip(" ,;:-") + "..."


def normalize_hashtags(raw: str) -> str:
    """Turn ``"art, #painting  #DailyArt"`` into ``"#art #painting #DailyArt"``."""
    tokens = []
    seen = set()
    for token in re.split(r"[\s,]+", (raw or "").strip()):
        token = token.strip().lstrip("#")
        if not token:
            continue
        key = token.lower()
        if key in seen:
            continue
        seen.add(key)
        tokens.append("#" + token)
    return " ".join(tokens)


def build_caption(caption: str, hashtags: str, *, limit: int, logger: logging.Logger) -> str:
    """Combine the queue ``caption`` and ``hashtags`` into the final caption."""
    body = (caption or "").strip()
    tags = normalize_hashtags(hashtags)
    text = f"{body}\n\n{tags}".strip() if tags else body

    if len(text) > limit:
        logger.warning("Caption is %d characters, trimming to the %d character platform limit", len(text), limit)
        text = truncate(text, limit)
    return text


def derive_title(caption: str, *, limit: int, soft_limit: Optional[int] = None) -> str:
    """Derive a short, readable title from the first line/sentence of a caption."""
    first_line = (caption or "").strip().splitlines()[0] if (caption or "").strip() else ""
    parts = re.split(r"(?<=[.!?])\s+", first_line.strip())
    title = parts[0].strip() if parts and parts[0].strip() else "New artwork"
    title = title.rstrip(" .!?,;:-") or "New artwork"

    if soft_limit and len(title) > soft_limit:
        clauses = re.split(r"\s+[-–—]\s+|[,;:]\s+", title)
        if clauses and 15 <= len(clauses[0].strip()) <= soft_limit:
            title = clauses[0].strip()

    return truncate(title, limit)


def resolve_image(image_filename: str, *, art_dir: Optional[Path] = None) -> Path:
    """Return the absolute path of an image inside ``art/``."""
    base = Path(art_dir or config.ART_DIR).resolve()
    raw_name = (image_filename or "").strip()
    if not raw_name:
        raise ValueError("Queue row has an empty image_filename")

    candidate = (base / raw_name).resolve()
    if not candidate.is_relative_to(base):
        raise ValueError(f"image_filename escapes the art/ folder: {image_filename!r}")
    if not candidate.is_file():
        raise FileNotFoundError(
            f"Artwork not found: {candidate}. Add the file to art/ (and commit it) or fix image_filename in content/queue.csv."
        )
    return candidate


def resolve_item_image(item_or_image) -> Path:
    """Resolve a JSON item's ``image`` field to a file under ``public/art/``.
    Accepts either the whole item dictionary or just the image string.
    """
    # 1. If a dictionary is passed, extract the 'image' field
    if isinstance(item_or_image, dict):
        image_field = item_or_image.get("image", "")
    else:
        image_field = item_or_image

    # 2. If the image_field is a dict (TinaCMS format), extract 'src'
    if isinstance(image_field, dict):
        image_field = image_field.get("src", "")

    raw = (image_field or "").strip()
    if not raw:
        raise ValueError("Item has an empty image field")

    # Strip leading "art/" or "/art/" so we always work with a bare filename
    name = raw
    if name.startswith("/"):
        name = name[1:]
    if name.startswith("art/"):
        name = name[4:]
    if name.startswith("./"):
        name = name[2:]
    
    from pathlib import PurePosixPath
    name = str(PurePosixPath(name).name)
    if not name:
        raise ValueError(f"image field resolved to an empty filename: {image_field!r}")

    candidate = (config.PUBLIC_ART_DIR / name).resolve()
    if not candidate.is_relative_to(config.PUBLIC_ART_DIR.resolve()):
        raise ValueError(f"image field escapes public/art/: {image_field!r}")
    if not candidate.is_file():
        raise FileNotFoundError(
            f"Artwork not found: {candidate}. Upload the image to public/art/ "
            f"(TinaCMS media root) or fix the image field in the JSON item."
        )
    return candidate


def describe_row(row: dict) -> str:
    """Compact one-line description of a queue row for the log."""
    return (
        f"id={row.get('id', '?')} platform={row.get('platform', '?')} "
        f"image={row.get('image_filename', '?')}"
    )


def format_results(results: Iterable[PostResult]) -> str:
    """Render a small table of results for the end of a run."""
    lines = []
    for result in results:
        target = f" -> {result.url}" if result.url else ""
        lines.append(
            f"{result.platform:<9} {result.status:<7} row={result.row_id or '-':<4} {result.message}{target}"
        )
    return "\n".join(lines) if lines else "(nothing to do)"
