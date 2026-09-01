"""Tiny per-day character counter, persisted to JSON.

Keeps us honest against the government service's daily quota
(~1000 字/日 anonymous, 10000 字/日 with a logged-in cookie).
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from threading import Lock

_LOCK = Lock()


class UsageTracker:
    def __init__(self, path: str | Path, daily_limit: int) -> None:
        self.path = Path(path)
        self.daily_limit = daily_limit

    def _load(self) -> dict:
        try:
            data = json.loads(self.path.read_text("utf-8"))
        except (OSError, ValueError):
            data = {}
        today = date.today().isoformat()
        if data.get("date") != today:
            data = {"date": today, "chars": 0}
        return data

    def _save(self, data: dict) -> None:
        try:
            self.path.write_text(json.dumps(data), "utf-8")
        except OSError:
            pass

    def peek(self) -> tuple[int, int]:
        """Return (used_today, daily_limit)."""
        with _LOCK:
            return self._load()["chars"], self.daily_limit

    def try_add(self, n_chars: int) -> tuple[bool, int]:
        """Reserve n_chars against today's budget.

        Returns (allowed, used_after). If not allowed, nothing is written.
        """
        with _LOCK:
            data = self._load()
            if data["chars"] + n_chars > self.daily_limit:
                return False, data["chars"]
            data["chars"] += n_chars
            self._save(data)
            return True, data["chars"]
