"""
memory.py — Per-user conversation history for AI context.

Every function is scoped to a single telegram_id so users never see
each other's history. History is stored in the `messages` table and
trimmed to settings.max_history_messages to control API cost.
"""

import logging
from typing import List, Dict

from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError

from database import get_session
from models import Message

logger = logging.getLogger(__name__)


def add_message(telegram_id: int, role: str, content: str, max_messages: int) -> None:
    """
    Save one message (role='user' or 'assistant') and trim old history.

    Trimming keeps the most recent `max_messages` rows per user so the
    DeepSeek prompt does not grow without bound.
    """
    if role not in ("user", "assistant"):
        raise ValueError(f"Invalid role: {role!r}")
    content = (content or "").strip()
    if not content:
        return

    try:
        with get_session() as session:
            session.add(Message(telegram_id=telegram_id, role=role, content=content))
            session.flush()  # ensures the new row exists before we count

            # Find IDs beyond the allowed window (oldest first) and delete them.
            rows = session.execute(
                select(Message.id)
                .where(Message.telegram_id == telegram_id)
                .order_by(Message.created_at.asc(), Message.id.asc())
            ).scalars().all()

            if len(rows) > max_messages:
                cutoff = len(rows) - max_messages
                ids_to_delete = rows[:cutoff]
                session.execute(delete(Message).where(Message.id.in_(ids_to_delete)))
    except SQLAlchemyError:
        logger.exception("Failed to save message for user %s", telegram_id)
        raise


def get_history(telegram_id: int, max_messages: int) -> List[Dict[str, str]]:
    """
    Return the most recent `max_messages` messages for this user,
    in chronological order, formatted for the DeepSeek chat API:
        [{"role": "user", "content": "..."}, ...]
    """
    try:
        with get_session() as session:
            rows = session.execute(
                select(Message)
                .where(Message.telegram_id == telegram_id)
                .order_by(Message.created_at.desc(), Message.id.desc())
                .limit(max_messages)
            ).scalars().all()
    except SQLAlchemyError:
        logger.exception("Failed to load history for user %s", telegram_id)
        return []

    rows.reverse()  # now chronological
    return [{"role": r.role, "content": r.content} for r in rows]


def clear_history(telegram_id: int) -> int:
    """
    Delete ALL stored messages for this user (used by /reset).
    Returns the number of rows deleted.
    Does NOT touch Telegram messages — only the bot's AI memory.
    """
    try:
        with get_session() as session:
            result = session.execute(delete(Message).where(Message.telegram_id == telegram_id))
            deleted = result.rowcount or 0
        logger.info("Cleared %s history rows for user %s", deleted, telegram_id)
        return deleted
    except SQLAlchemyError:
        logger.exception("Failed to clear history for user %s", telegram_id)
        raise
