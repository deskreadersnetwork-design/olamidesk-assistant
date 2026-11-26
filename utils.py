"""
utils.py — Shared helpers used across the bot.

- RateLimiter: prevents a single user from spamming the bot.
- clean_text: trims and length-caps user input.
- generate_reference: produces human-friendly enquiry codes like OLA-2025-0001.
"""

import re
import time
import random
import threading
from datetime import datetime, timezone
from typing import Dict, Tuple

# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------

class RateLimiter:
    """
    In-memory per-user rate limiter.
    Tracks the last timestamp each user was seen and blocks requests that
    come faster than `min_seconds` apart.
    Thread-safe because python-telegram-bot may handle updates concurrently.
    """

    def __init__(self, min_seconds: int) -> None:
        self.min_seconds = max(0, min_seconds)
        self._last_seen: Dict[int, float] = {}
        self._lock = threading.Lock()

    def is_allowed(self, user_id: int) -> Tuple[bool, int]:
        """
        Returns (allowed, seconds_to_wait).
        If blocked, seconds_to_wait is how long until the user may retry.
        """
        if self.min_seconds <= 0:
            return True, 0
        now = time.monotonic()
        with self._lock:
            last = self._last_seen.get(user_id)
            if last is not None:
                elapsed = now - last
                if elapsed < self.min_seconds:
                    wait = int(round(self.min_seconds - elapsed))
                    return False, max(1, wait)
            self._last_seen[user_id] = now
            return True, 0


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

MAX_INPUT_LENGTH = 2000  # Telegram message cap is 4096; we keep a safe margin.


def clean_text(text: str) -> str:
    """Strip whitespace, collapse repeated blank lines, and cap length."""
    if not text:
        return ""
    cleaned = text.strip()
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    if len(cleaned) > MAX_INPUT_LENGTH:
        cleaned = cleaned[:MAX_INPUT_LENGTH] + "…"
    return cleaned


# ---------------------------------------------------------------------------
# Reference generator
# ---------------------------------------------------------------------------

def generate_reference() -> str:
    """
    Build a human-friendly enquiry reference like OLA-2025-4821.
    Collision chance is extremely low; the DB enforces uniqueness on the column
    and the caller retries on IntegrityError if needed.
    """
    year = datetime.now(timezone.utc).year
    number = random.randint(1000, 9999)
    return f"OLA-{year}-{number}"
