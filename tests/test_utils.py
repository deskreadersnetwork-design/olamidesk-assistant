"""
Tests for utils.py — pure functions, no DB or network needed.
"""

import time

from utils import MAX_INPUT_LENGTH, RateLimiter, clean_text, generate_reference


def test_clean_text_trims_whitespace():
    assert clean_text("   hello   ") == "hello"


def test_clean_text_collapses_blank_lines():
    assert clean_text("a\n\n\n\nb") == "a\n\nb"


def test_clean_text_caps_length():
    long = "x" * (MAX_INPUT_LENGTH + 500)
    out = clean_text(long)
    assert len(out) <= MAX_INPUT_LENGTH + 1  # +1 for the ellipsis character
    assert out.endswith("…")


def test_clean_text_empty():
    assert clean_text("") == ""
    assert clean_text(None) == ""


def test_generate_reference_format():
    ref = generate_reference()
    parts = ref.split("-")
    assert len(parts) == 3
    assert parts[0] == "OLA"
    assert parts[1].isdigit() and len(parts[1]) == 4
    assert parts[2].isdigit() and len(parts[2]) == 4


def test_rate_limiter_first_call_allowed():
    limiter = RateLimiter(min_seconds=2)
    allowed, wait = limiter.is_allowed(user_id=1)
    assert allowed is True
    assert wait == 0


def test_rate_limiter_blocks_immediate_second_call():
    limiter = RateLimiter(min_seconds=2)
    limiter.is_allowed(user_id=1)
    allowed, wait = limiter.is_allowed(user_id=1)
    assert allowed is False
    assert wait >= 1


def test_rate_limiter_independent_users():
    limiter = RateLimiter(min_seconds=2)
    limiter.is_allowed(user_id=1)
    allowed_user2, _ = limiter.is_allowed(user_id=2)
    assert allowed_user2 is True


def test_rate_limiter_zero_disables():
    limiter = RateLimiter(min_seconds=0)
    assert limiter.is_allowed(1) == (True, 0)
    assert limiter.is_allowed(1) == (True, 0)
