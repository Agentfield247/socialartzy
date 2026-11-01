"""Persistent per-platform daily post counters.

Why this exists: a broken queue or a re-run of the workflow could easily publish
five items in a minute. Instagram and Pinterest both treat that as bot
behaviour, so every script asks this module for permission *before* posting.

State lives in ``state/daily_count.json`` and is committed back by the workflow,
which means the counter survives across Actions runs:

    {"date": "2026-01-11", "counts": {"instagram": 1, "pinterest": 2},
     "history": [{"at": "...", "platform": "instagram", "row_id": "1"}]}
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

from . import config

_HISTORY_LIMIT = 60


class DailyCounter:
    """Counts how many posts went out today, per platform."""

    def __init__(self, path: Optional[Path] = None, today: Optional[str] = None) -> None:
        self.path = Path(path or config.DAILY_COUNTER_FILE)
        self.today = today or config.utc_today()

    # -- persistence ------------------------------------------------------
    def _load(self) -> Dict:
        data: Dict = {}
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                loaded = json.load(handle)
            if isinstance(loaded, dict):
                data = loaded
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            data = {}

        if data.get("date") != self.today:
            # New day (UTC): reset the counters but keep a short audit trail.
            history = data.get("history") if isinstance(data.get("history"), list) else []
            data = {"date": self.today, "counts": {}, "history": history[-_HISTORY_LIMIT:]}

        if not isinstance(data.get("counts"), dict):
            data["counts"] = {}
        if not isinstance(data.get("history"), list):
            data["history"] = []
        return data

    def _save(self, data: Dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle_fd, tmp_name = tempfile.mkstemp(
            dir=str(self.path.parent), prefix=".counter-", suffix=".json", text=True
        )
        try:
            with os.fdopen(handle_fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2, sort_keys=True)
                handle.write("\n")
            os.replace(tmp_name, self.path)
        except BaseException:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
            raise

    # -- queries ----------------------------------------------------------
    def limit(self, platform: str) -> int:
        return config.platform_limits().get(platform, 1)

    def count(self, platform: str) -> int:
        try:
            return int(self._load()["counts"].get(platform, 0))
        except (TypeError, ValueError):
            return 0

    def remaining(self, platform: str) -> int:
        return max(0, self.limit(platform) - self.count(platform))

    def can_post(self, platform: str) -> bool:
        return self.remaining(platform) > 0

    # -- mutations --------------------------------------------------------
    def record(self, platform: str, row_id: str = "", detail: str = "") -> int:
        """Register one successful post and return the new count for today."""
        data = self._load()
        new_count = int(data["counts"].get(platform, 0)) + 1
        data["counts"][platform] = new_count
        data["history"].append(
            {
                "at": config.utc_now(),
                "platform": platform,
                "row_id": str(row_id),
                "detail": detail,
            }
        )
        data["history"] = data["history"][-_HISTORY_LIMIT:]
        self._save(data)
        return new_count

    def snapshot(self) -> Dict[str, Dict[str, int]]:
        """``{"instagram": {"count": 1, "limit": 2}, ...}`` for logging."""
        result: Dict[str, Dict[str, int]] = {}
        counts = self._load()["counts"]
        for platform in config.platform_limits():
            try:
                used = int(counts.get(platform, 0))
            except (TypeError, ValueError):
                used = 0
            result[platform] = {"count": used, "limit": self.limit(platform)}
        return result