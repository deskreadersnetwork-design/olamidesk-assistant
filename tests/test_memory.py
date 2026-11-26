"""
Tests for memory.py — uses the memory_db fixture (in-memory SQLite).
Also inserts a User row because messages reference users.telegram_id.
"""

from memory import add_message, clear_history, get_history
from database import get_session
from models import User


def _create_user(telegram_id: int, name: str = "Test") -> None:
    with get_session() as session:
        session.add(User(telegram_id=telegram_id, first_name=name))


def test_add_and_get_history(memory_db):
    _create_user(1)
    add_message(1, "user", "hello", max_messages=20)
    add_message(1, "assistant", "hi there", max_messages=20)

    history = get_history(1, max_messages=20)
    assert len(history) == 2
    assert history[0] == {"role": "user", "content": "hello"}
    assert history[1] == {"role": "assistant", "content": "hi there"}


def test_history_isolation_between_users(memory_db):
    _create_user(1)
    _create_user(2)
    add_message(1, "user", "from user 1", max_messages=20)
    add_message(2, "user", "from user 2", max_messages=20)

    h1 = get_history(1, max_messages=20)
    h2 = get_history(2, max_messages=20)
    assert len(h1) == 1 and h1[0]["content"] == "from user 1"
    assert len(h2) == 1 and h2[0]["content"] == "from user 2"


def test_history_trimming_keeps_most_recent(memory_db):
    _create_user(1)
    for i in range(10):
        add_message(1, "user", f"msg {i}", max_messages=5)

    history = get_history(1, max_messages=5)
    assert len(history) == 5
    # The five kept messages should be msg 5..msg 9.
    contents = [m["content"] for m in history]
    assert contents == ["msg 5", "msg 6", "msg 7", "msg 8", "msg 9"]


def test_clear_history_only_affects_one_user(memory_db):
    _create_user(1)
    _create_user(2)
    add_message(1, "user", "user1", max_messages=20)
    add_message(2, "user", "user2", max_messages=20)

    deleted = clear_history(1)
    assert deleted == 1
    assert get_history(1, 20) == []
    assert len(get_history(2, 20)) == 1


def test_empty_content_ignored(memory_db):
    _create_user(1)
    add_message(1, "user", "   ", max_messages=20)
    assert get_history(1, 20) == []
