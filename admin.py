"""
admin.py — Administrator commands.

All handlers check `update.effective_user.id == settings.admin_telegram_id`.
Commands:
- /admin      — quick admin panel summary
- /stats      — users, messages, enquiries, open enquiries
- /broadcast  — send a message to all known users
- /reply      — reply to a specific enquiry by reference

Usage of /reply:
    /reply OLA-2025-1234 Your reply text goes here
"""

import asyncio
import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from sqlalchemy import func, select

from config import Settings
from database import get_session
from models import ActivityLog, Enquiry, Message, User
from support import deliver_admin_reply

logger = logging.getLogger(__name__)

_settings: Settings | None = None


def bind(settings: Settings) -> None:
    global _settings
    _settings = settings


def _is_admin(update: Update) -> bool:
    user = update.effective_user
    return bool(user and user.id == _settings.admin_telegram_id)


async def _deny(update: Update) -> None:
    await update.effective_chat.send_message("⛔ Not authorized.")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update):
        await _deny(update)
        return
    await update.effective_chat.send_message(
        "*Admin Panel*\n\n"
        "/stats — usage statistics\n"
        "/broadcast <message> — send to all users\n"
        "/reply <reference> <message> — reply to an enquiry\n\n"
        "Enquiries open: use /stats to see the count.",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update):
        await _deny(update)
        return
    try:
        with get_session() as session:
            user_count = session.execute(select(func.count(User.id))).scalar_one()
            msg_count = session.execute(select(func.count(Message.id))).scalar_one()
            enq_total = session.execute(select(func.count(Enquiry.id))).scalar_one()
            enq_open = session.execute(
                select(func.count(Enquiry.id)).where(Enquiry.status == "open")
            ).scalar_one()
            log_count = session.execute(select(func.count(ActivityLog.id))).scalar_one()
    except Exception:
        logger.exception("Failed to compute stats")
        await update.effective_chat.send_message("⚠️ Could not load stats. Check Railway logs.")
        return

    text = (
        "*Olamidesk Stats*\n\n"
        f"👥 Users: {user_count}\n"
        f"💬 Stored messages: {msg_count}\n"
        f"📨 Enquiries total: {enq_total}\n"
        f"🟡 Enquiries open: {enq_open}\n"
        f"📊 Activity log entries: {log_count}"
    )
    await update.effective_chat.send_message(text, parse_mode=ParseMode.MARKDOWN)


async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update):
        await _deny(update)
        return

    if not context.args:
        await update.effective_chat.send_message(
            "Usage: `/broadcast Your message here`", parse_mode=ParseMode.MARKDOWN
        )
        return

    message = " ".join(context.args).strip()
    if not message:
        await update.effective_chat.send_message("Broadcast message is empty.")
        return

    try:
        with get_session() as session:
            ids = session.execute(select(User.telegram_id)).scalars().all()
    except Exception:
        logger.exception("Failed to load users for broadcast")
        await update.effective_chat.send_message("⚠️ Could not load user list.")
        return

    await update.effective_chat.send_message(f"Sending to {len(ids)} users…")

    sent, failed = 0, 0
    for tg_id in ids:
        try:
            await context.bot.send_message(
                chat_id=tg_id,
                text=f"📣 *Announcement from Olamidesk*\n\n{message}",
                parse_mode=ParseMode.MARKDOWN,
            )
            sent += 1
        except Exception as exc:
            failed += 1
            logger.debug("Broadcast fail for %s: %s", tg_id, type(exc).__name__)
        await asyncio.sleep(0.05)  # be gentle with Telegram rate limits

    await update.effective_chat.send_message(f"✅ Broadcast complete. Sent: {sent}, Failed: {failed}")


async def cmd_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update):
        await _deny(update)
        return

    if len(context.args) < 2:
        await update.effective_chat.send_message(
            "Usage: `/reply OLA-2025-1234 Your reply text here`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    reference = context.args[0].strip()
    reply_text = " ".join(context.args[1:]).strip()
    if not reply_text:
        await update.effective_chat.send_message("Reply text is empty.")
        return

    try:
        with get_session() as session:
            enquiry = session.execute(
                select(Enquiry).where(Enquiry.reference == reference)
            ).scalar_one_or_none()
    except Exception:
        logger.exception("DB error looking up enquiry %s", reference)
        await update.effective_chat.send_message("⚠️ Database error while looking up enquiry.")
        return

    if enquiry is None:
        await update.effective_chat.send_message(f"❓ No enquiry found with reference `{reference}`.",
                                                parse_mode=ParseMode.MARKDOWN)
        return

    ok = await deliver_admin_reply(update, context, enquiry, reply_text)
    if ok:
        await update.effective_chat.send_message(
            f"✅ Reply sent to user `{enquiry.telegram_id}` for ref `{reference}`.",
            parse_mode=ParseMode.MARKDOWN,
        )
    else:
        await update.effective_chat.send_message(
            "⚠️ Could not deliver reply (user may have blocked the bot). "
            "The enquiry was NOT marked as replied."
        )
