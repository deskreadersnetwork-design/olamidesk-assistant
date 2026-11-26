"""
support.py — Human-support flow.

Flow:
1. start_support_flow() — ask user to type their question, set state flag.
2. handle_support_question() — create enquiry, forward to admin, confirm to user.
3. deliver_admin_reply() — send admin's reply back to the customer (called from admin.py).
"""

import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from config import load_settings
from database import get_session
from models import Enquiry, utcnow
from utils import clean_text, generate_reference

logger = logging.getLogger(__name__)

_state_flag_key = "awaiting_support_question"


async def start_support_flow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Prompt the user to type their enquiry and mark the state."""
    context.user_data[_state_flag_key] = True
    chat = update.effective_chat or (update.callback_query.message.chat if update.callback_query else None)
    if chat is None:
        return
    await chat.send_message(
        "💬 Please type your question or enquiry in one message, "
        "and I'll forward it to our support team.\n\n"
        "Send /cancel to cancel."
    )


async def handle_support_question(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    """Create the enquiry, forward to admin, confirm to user."""
    context.user_data.pop(_state_flag_key, None)
    user = update.effective_user
    chat = update.effective_chat

    cleaned = clean_text(text)
    if not cleaned:
        await chat.send_message("Please type a longer message so our team can help.")
        context.user_data[_state_flag_key] = True
        return

    settings = load_settings()

    # Create the enquiry with a unique reference (retry a few times on collision).
    enquiry = None
    for attempt in range(5):
        reference = generate_reference()
        try:
            with get_session() as session:
                enquiry = Enquiry(
                    reference=reference,
                    telegram_id=user.id,
                    question=cleaned,
                    status="open",
                )
                session.add(enquiry)
                session.flush()
                # Detach the needed attributes before the session closes.
                ref_value = enquiry.reference
                q_value = enquiry.question
            break
        except IntegrityError:
            logger.warning("Reference collision on %s (attempt %s)", reference, attempt + 1)
            continue
        except SQLAlchemyError:
            logger.exception("DB error while creating enquiry for %s", user.id)
            await chat.send_message(
                "Sorry — I couldn't save your enquiry right now. Please try again in a moment."
            )
            return
    else:
        await chat.send_message(
            "Sorry — I couldn't create an enquiry reference right now. Please try again later."
        )
        return

    # Confirm to the user immediately.
    await chat.send_message(
        f"✅ Thanks! Your enquiry has been sent.\n\n"
        f"Reference: `{ref_value}`\n\n"
        f"Our team will reply here as soon as possible.",
        parse_mode=ParseMode.MARKDOWN,
    )

    # Forward to the admin.
    admin_text = (
        "🔔 *New Support Enquiry*\n\n"
        f"Reference: `{ref_value}`\n"
        f"Telegram ID: `{user.id}`\n"
        f"Username: @{user.username or 'n/a'}\n"
        f"Name: {user.first_name or 'n/a'}\n\n"
        f"Question:\n{q_value}\n\n"
        f"Reply with:\n`/reply {ref_value} your answer here`"
    )
    try:
        await context.bot.send_message(
            chat_id=settings.admin_telegram_id,
            text=admin_text,
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception:
        logger.exception("Failed to notify admin of enquiry %s", ref_value)


async def deliver_admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE, enquiry: Enquiry, reply_text: str) -> bool:
    """
    Send the admin's reply to the customer. Returns True on success.
    Marks the enquiry as replied.
    """
    from telegram.error import TelegramError

    try:
        await context.bot.send_message(
            chat_id=enquiry.telegram_id,
            text=(
                f"📨 Reply from Olamidesk support (Ref: `{enquiry.reference}`):\n\n"
                f"{reply_text}"
            ),
            parse_mode=ParseMode.MARKDOWN,
        )
    except TelegramError:
        logger.exception("Failed to deliver reply for enquiry %s", enquiry.reference)
        return False

    try:
        with get_session() as session:
            row = session.execute(
                select(Enquiry).where(Enquiry.reference == enquiry.reference)
            ).scalar_one_or_none()
            if row is not None:
                row.status = "replied"
                row.admin_reply = reply_text
                row.replied_at = utcnow()
    except SQLAlchemyError:
        logger.exception("Failed to mark enquiry %s replied", enquiry.reference)
        # The reply WAS delivered; failure to update status is non-fatal.
    return True


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Cancel an in-progress support question."""
    if context.user_data.pop(_state_flag_key, None):
        await update.effective_chat.send_message("Cancelled. You can keep chatting or tap the menu.")
    else:
        await update.effective_chat.send_message("Nothing to cancel.")
