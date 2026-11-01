"""Central configuration for the SocialArtzy bot.

Everything is driven by environment variables so that the very same code runs
locally (``--dry-run``, no credentials needed) and inside GitHub Actions (real
posting, credentials injected from repository secrets).

All paths are resolved relative to the repository root, which is also the
working directory GitHub Actions uses.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Tuple

# ---------------------------------------------------------------------------
# Filesystem layout
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent

ART_DIR = ROOT / "art"
CONTENT_DIR = ROOT / "content"
SKETCHES_DIR = CONTENT_DIR / "sketches"
ARTWORKS_DIR = CONTENT_DIR / "artworks"
PUBLIC_ART_DIR = ROOT / "public" / "art"
LOG_DIR = ROOT / "logs"
STATE_DIR = ROOT / "state"

LOG_FILE = LOG_DIR / "posting.log"
DAILY_COUNTER_FILE = STATE_DIR / "daily_count.json"
IG_SESSION_FILE = STATE_DIR / "instagram_session.json"
PINTEREST_CRED_ROOT = STATE_DIR / "pinterest"

# Content directories the bot scans for pending items
CONTENT_DIRS = (SKETCHES_DIR, ARTWORKS_DIR)


# ---------------------------------------------------------------------------
# Small env helpers (never raise: a bad override falls back to the default)
# ---------------------------------------------------------------------------
def _env_str(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _env_int(name: str, default: int) -> int:
    raw = _env_str(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool = False) -> bool:
    raw = _env_str(name).lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "y", "on"}


def _env_range(name: str, default: Tuple[int, int]) -> Tuple[int, int]:
    """Parse ``"15,45"`` or ``"15-45"`` into ``(15, 45)``."""
    raw = _env_str(name)
    if not raw:
        return default
    parts = raw.replace("-", ",").split(",")
    try:
        low, high = int(parts[0]), int(parts[1])
    except (ValueError, IndexError):
        return default
    return (min(low, high), max(low, high))


# ---------------------------------------------------------------------------
# Credentials (GitHub Secrets -> environment variables)
# ---------------------------------------------------------------------------
IG_USERNAME = _env_str("IG_USERNAME")
IG_PASSWORD = _env_str("IG_PASSWORD")
# Optional: a browser session id. When present it is used instead of a
# username/password login, which avoids most instagrapi challenge/captcha flows.
IG_SESSIONID = _env_str("IG_SESSIONID")

PINTEREST_EMAIL = _env_str("PINTEREST_EMAIL")
PINTEREST_PASSWORD = _env_str("PINTEREST_PASSWORD")
# Optional: the handle from your Pinterest profile URL (pinterest.com/<handle>).
# py3-pinterest needs it to list your boards. It is also accepted as the
# PINTEREST_USERNAME repository secret.
PINTEREST_USERNAME = _env_str("PINTEREST_USERNAME")
# Optional: official Pinterest API v5 access token. When set together with
# PINTEREST_REFRESH_TOKEN the bot uses the documented API instead of
# py3-pinterest (kept for backward compatibility).
PINTEREST_ACCESS_TOKEN = _env_str("PINTEREST_ACCESS_TOKEN")
# Pinterest API v5 OAuth credentials. When both PINTEREST_CLIENT_ID and
# PINTEREST_REFRESH_TOKEN are set, the bot exchanges the refresh token for an
# access token at run time and uses the official API v5.
PINTEREST_CLIENT_ID = _env_str("PINTEREST_CLIENT_ID")
PINTEREST_CLIENT_SECRET = _env_str("PINTEREST_CLIENT_SECRET")
PINTEREST_REFRESH_TOKEN = _env_str("PINTEREST_REFRESH_TOKEN")
# Used when a queue row leaves pinterest_board empty.
PINTEREST_DEFAULT_BOARD = _env_str("PINTEREST_DEFAULT_BOARD", "Art")


# ---------------------------------------------------------------------------
# Rate limiting and human-like pacing
# ---------------------------------------------------------------------------
# Instagram allows roughly 100 posts / 24h but 1-3 posts/day is the safe,
# "human" range for an art account. Instagram's request pacing (delay_range)
# is handled inside instagrapi for *every* request.
IG_DELAY_RANGE = _env_range("IG_DELAY_RANGE", (15, 45))
IG_DAILY_LIMIT = max(1, _env_int("IG_DAILY_LIMIT", 2))

# Pinterest is stricter about new accounts: 1-5 pins/day is conservative.
PINTEREST_DELAY_RANGE = _env_range("PINTEREST_DELAY_RANGE", (20, 60))
PINTEREST_DAILY_LIMIT = max(1, _env_int("PINTEREST_DAILY_LIMIT", 3))

# Platform hard limits (used for safe truncation before upload)
IG_CAPTION_LIMIT = 2200
IG_ALT_TEXT_LIMIT = 1000  # Instagram accepts up to 1,000 characters of alt text
PINTEREST_TITLE_LIMIT = 100
PINTEREST_DESCRIPTION_LIMIT = 800
PINTEREST_ALT_TEXT_LIMIT = 500

# When true every script only logs what it *would* do (no network, no writes)
DRY_RUN = _env_bool("DRY_RUN", False)


def utc_today() -> str:
    """Current UTC date as ``YYYY-MM-DD`` (GitHub Actions runs on UTC)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def utc_now() -> str:
    """Current UTC timestamp, ISO-8601 with a ``Z`` suffix."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def platform_limits() -> dict:
    return {"instagram": IG_DAILY_LIMIT, "pinterest": PINTEREST_DAILY_LIMIT}


def ensure_directories() -> None:
    """Create the working folders; safe to call repeatedly."""
    for directory in (ART_DIR, CONTENT_DIR, LOG_DIR, STATE_DIR):
        directory.mkdir(parents=True, exist_ok=True)