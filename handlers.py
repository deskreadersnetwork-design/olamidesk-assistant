"""
handlers.py — User-facing handlers.

Covers:
- /start, /help, /services, /contact, /about, /reset, /menu
- Menu button callbacks (services, ads, bot dev, pricing, support, about, menu)
- Free-text messages routed to DeepSeek AI

Important behavior rules from the spec:
- Every AI response is a NEW message (never edits the welcome message).
- /start always sends a fresh welcome message; nothing is deleted.
- /reset clears ONLY the AI conversation memory (not Telegram messages).
"""

import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from config import Settings
from database import get_session
from deepseek import DeepSeekClient
from keyboards import (
    CB_ABOUT,
    CB_BOT_DEV,
    CB_MENU,
    CB_PRICING,
    CB_SERVICES,
    CB_SUPPORT,
    CB_TG_ADS,
    back_to_menu,
    main_menu,
)
from knowledge_base import ABOUT_TEXT, SERVICES
from memory import add_message, clear_history, get_history
from models import ActivityLog, User
from support import start_support_flow
from utils import RateLimiter, clean_text

logger = logging.getLogger(__name__)

# Module-level singletons wired in main.py.
_settings: Settings | None = None
_deepseek: DeepSeekClient | None = None
_rate_limiter: RateLimiter | None = None


def bind(settings: Settings, deepseek: DeepSeekClient) -> None:
    """Called from main.py to inject shared dependencies."""
    global _settings, _deepseek, _rate_limiter
    _settings = settings
    _deepseek = deepseek
    _rate_limiter = RateLimiter(settings.rate_limit_seconds)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

WELCOME_TEXT = (
    "👋 Hello! Welcome to OLAMIDESK!\n\n"
    "I'm Olamidesk Assistant, your smart digital support assistant.\n\n"
    "I can help you learn about our services, Telegram Ads, bot development, "
    "automation and other digital solutions.\n\n"
    "What would you like to know today? 😊\n\n"
    "Tap a button below, or simply type your question."
)


def _register_user(update: Update) -> None:
    """Upsert the user row, update last_seen, and log the action type externally."""
    tg_user = update.effective_user
    if tg_user is None:
        return
    try:
        with get_session() as session:
            user = session.get(User, None)  # placeholder, replaced below
            from sqlalchemy import select
            user = session.execute(
                select(User).where(User.telegram_id == tg_user.id)
            ).scalar_one_or_none()
            if user is None:
                session.add(
                    User(
                        telegram_id=tg_user.id,
                        username=tg_user.username,
                        first_name=tg_user.first_name,
                        is_admin=(tg_user.id == _settings.admin_telegram_id),
                    )
                )
            else:
                user.username = tg_user.username
                user.first_name = tg_user.first_name
                from models import utcnow
                user.last_seen = utcnow()
    except Exception:
        logger.exception("Failed to register user %s", tg_user.id)


def _log_activity(telegram_id: int, action: str, detail: str | None = None) -> None:
    try:
        with get_session() as session:
            session.add(ActivityLog(telegram_id=telegram_id, action=action, detail=detail))
    except Exception:
        logger.exception("Failed to log activity %s for %s", action, telegram_id)


async def _send(update: Update, text: str, with_menu: bool = False) -> None:
    """Send a NEW message (never edit) with optional main menu."""
    kwargs = {"parse_mode": ParseMode.MARKDOWN}
    if with_menu:
        kwargs["reply_markup"] = main_menu()
    await update.effective_chat.send_message(text, **kwargs)


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _register_user(update)
    _log_activity(update.effective_user.id, "start")
    # Always send a NEW welcome message with menu. Never delete earlier messages.
    await _send(update, WELCOME_TEXT, with_menu=True)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _register_user(update)
    _log_activity(update.effective_user.id, "help")
    text = (
        "Here's what I can do:\n\n"
        "• /start — Welcome message and menu\n"
        "• /menu — Show the button menu\n"
        "• /services — Our services\n"
        "• /contact — How to reach us\n"
        "• /about — About Olamidesk\n"
        "• /reset — Clear our conversation memory\n\n"
        "You can also just type any question in normal English."
    )
    await _send(update, text, with_menu=True)


async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _register_user(update)
    _log_activity(update.effective_user.id, "menu")
    await _send(update, "Here's the menu — tap a button or type your question:", with_menu=True)


async def cmd_services(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _register_user(update)
    _log_activity(update.effective_user.id, "services")
    lines = ["*Our Services*\n"]
    for svc in SERVICES.values():
        lines.append(f"*{svc['title']}*\n{svc['summary']}\n")
    await update.effective_chat.send_message(
        "\n".join(lines),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=back_to_menu(),
    )


async def cmd_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _register_user(update)
    _log_activity(update.effective_user.id, "contact")
    support = f"@{_settings.support_username}" if _settings.support_username else "our support team"
    text = (
        f"*Contact Olamidesk*\n\n"
        f"You can reach {support} for direct help.\n\n"
        f"Or tap 💬 Talk to Support below and I'll open an enquiry for you."
    )
    await update.effective_chat.send_message(
        text, parse_mode=ParseMode.MARKDOWN, reply_markup=back_to_menu()
    )


async def cmd_about(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _register_user(update)
    _log_activity(update.effective_user.id, "about")
    await update.effective_chat.send_message(
        f"*About Olamidesk*\n\n{ABOUT_TEXT}",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=back_to_menu(),
    )


async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _register_user(update)
    _log_activity(update.effective_user.id, "reset")
    deleted = clear_history(update.effective_user.id)
    await _send(
        update,
        f"🧹 Done — I've cleared our AI conversation memory "
        f"({deleted} stored message{'s' if deleted != 1 else ''}).\n\n"
        f"Your Telegram messages are untouched. You can start fresh now.",
        with_menu=True,
    )


# ---------------------------------------------------------------------------
# Button callbacks
# ---------------------------------------------------------------------------

async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()  # stops the loading spinner
    _register_user(update)
    data = query.data
    _log_activity(update.effective_user.id, f"button:{data}")

    if data == CB_SERVICES:
        lines = ["*Our Services*\n"]
        for svc in SERVICES.values():
            lines.append(f"*{svc['title']}*\n{svc['summary']}\n")
        await query.message.chat.send_message(
            "\n".join(lines), parse_mode=ParseMode.MARKDOWN, reply_markup=back_to_menu()
        )
    elif data == CB_TG_ADS:
        svc = SERVICES["telegram_ads"]
        text = f"*{svc['title']}*\n\n{svc['summary']}\n\nAsk me anything about Telegram Ads, or talk to support for specifics."
        await query.message.chat.send_message(
            text, parse_mode=ParseMode.MARKDOWN, reply_markup=back_to_menu()
        )
    elif data == CB_BOT_DEV:
        svc = SERVICES["bot_development"]
        text = f"*{svc['title']}*\n\n{svc['summary']}\n\nTell me what kind of bot you need and I'll explain how we can help."
        await query.message.chat.send_message(
            text, parse_mode=ParseMode.MARKDOWN, reply_markup=back_to_menu()
        )
    elif data == CB_PRICING:
        text = (
            "*Pricing & Enquiries*\n\n"
            "Pricing depends on the specific project. I don't have confirmed "
            "price figures to share here.\n\n"
            "Tap 💬 Talk to Support and send your question — a human will follow up with details."
        )
        await query.message.chat.send_message(
            text, parse_mode=ParseMode.MARKDOWN, reply_markup=back_to_menu()
        )
    elif data == CB_SUPPORT:
        await start_support_flow(update, context)
    elif data == CB_ABOUT:
        await query.message.chat.send_message(
            f"*About Olamidesk*\n\n{ABOUT_TEXT}",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=back_to_menu(),
        )
    elif data == CB_MENU:
        await query.message.chat.send_message(
            "Here's the menu — tap a button or type your question:",
            reply_markup=main_menu(),
        )


# ---------------------------------------------------------------------------
# Free-text handler → DeepSeek
# ---------------------------------------------------------------------------

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _register_user(update)
    user_id = update.effective_user.id

    # Rate limiting
    allowed, wait = _rate_limiter.is_allowed(user_id)
    if not allowed:
        await _send(update, f"⏳ Please wait {wait} more second(s) before sending another message.")
        return

    text = clean_text(update.message.text or "")
    if not text:
        return

    # If we're in a support flow, capture the enquiry text first.
    if context.user_data.get("awaiting_support_question"):
        from support import handle_support_question
        await handle_support_question(update, context, text)
        return

    _log_activity(user_id, "ai_query", detail=text[:200])
    await update.effective_chat.send_action("typing")

    history = get_history(user_id, _settings.max_history_messages)
    answer = await _deepseek.reply(history, text)

    # Persist both sides of the exchange for future context.
    try:
        add_message(user_id, "user", text, _settings.max_history_messages)
        add_message(user_id, "assistant", answer, _settings.max_history_messages)
    except Exception:
        logger.exception("Failed to persist conversation for user %s", user_id)

    # Always a NEW message. Never edit the welcome or previous messages.
    await update.effective_chat.send_message(answer, reply_markup=back_to_menu())


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Global error handler — logs and replies politely if we have an update."""
    logger.exception("Unhandled error", exc_info=context.error)
    if isinstance(update, Update) and update.effective_chat:
        try:
            await update.effective_chat.send_message(
                "⚠️ Something went wrong on my side. Please try again, or use 💬 Talk to Support."
            )
        except Exception:
            pass
