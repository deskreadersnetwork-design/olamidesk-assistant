"""
main.py — Application entry point.

Boot order:
1. Load and validate settings (fails fast on missing env vars).
2. Initialize the database (create tables if needed).
3. Build the Telegram Application.
4. Wire dependencies into handlers and admin.
5. Register all handlers.
6. Run long polling. Shut down cleanly on SIGTERM/SIGINT.
"""

import asyncio
import logging
import signal
import sys

from telegram import BotCommand
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

import admin
import handlers
from config import ConfigError, load_settings
from database import dispose_engine, init_db
from deepseek import DeepSeekClient
from support import cmd_cancel

logger = logging.getLogger(__name__)


async def _post_init(application: Application) -> None:
    """Set the bot's command list so Telegram shows a menu button."""
    commands = [
        BotCommand("start", "Welcome message and menu"),
        BotCommand("menu", "Show the button menu"),
        BotCommand("help", "What I can do"),
        BotCommand("services", "Our services"),
        BotCommand("contact", "How to reach us"),
        BotCommand("about", "About Olamidesk"),
        BotCommand("reset", "Clear AI conversation memory"),
    ]
    try:
        await application.bot.set_my_commands(commands)
        logger.info("Bot commands registered.")
    except Exception:
        logger.exception("Failed to set bot commands (non-fatal).")


def _register_handlers(application: Application) -> None:
    """Attach all commands, callbacks, and messages to the application."""
    application.add_handler(CommandHandler("start", handlers.cmd_start))
    application.add_handler(CommandHandler("help", handlers.cmd_help))
    application.add_handler(CommandHandler("menu", handlers.cmd_menu))
    application.add_handler(CommandHandler("services", handlers.cmd_services))
    application.add_handler(CommandHandler("contact", handlers.cmd_contact))
    application.add_handler(CommandHandler("about", handlers.cmd_about))
    application.add_handler(CommandHandler("reset", handlers.cmd_reset))
    application.add_handler(CommandHandler("cancel", cmd_cancel))

    # Admin commands
    application.add_handler(CommandHandler("admin", admin.cmd_admin))
    application.add_handler(CommandHandler("stats", admin.cmd_stats))
    application.add_handler(CommandHandler("broadcast", admin.cmd_broadcast))
    application.add_handler(CommandHandler("reply", admin.cmd_reply))

    # Menu buttons
    application.add_handler(CallbackQueryHandler(handlers.on_callback))

    # Any other text → AI
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.on_text))

    # Global error handler
    application.add_error_handler(handlers.on_error)


async def _run() -> None:
    try:
        settings = load_settings()
    except ConfigError as exc:
        # Print and exit — Railway logs will show this clearly.
        logger.error("Configuration error: %s", exc)
        sys.exit(1)

    logger.info("Starting OLAMIDESK ASSISTANT…")

    init_db(settings.database_url)

    deepseek = DeepSeekClient(settings)

    # Inject settings + deepseek into handlers, settings into admin.
    handlers.bind(settings, deepseek)
    admin.bind(settings)

    application = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .post_init(_post_init)
        .build()
    )

    _register_handlers(application)

    # Graceful shutdown: run_polling handles SIGTERM/SIGINT by itself,
    # but we add an explicit "close" hook to dispose the DB engine.
    stop_event = asyncio.Event()

    def _handle_signal(signame: str) -> None:
        logger.info("Received %s, shutting down…", signame)
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _handle_signal, sig.name)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler for all signals; fall back.
            pass

    logger.info("Starting polling…")

    # run_polling blocks until stopped. We wrap it in a task so we can react to stop_event.
    polling_task = asyncio.create_task(
        application.run_polling(
            allowed_updates=["message", "callback_query"],
            drop_pending_updates=False,
            close_loop=False,
        )
    )

    await stop_event.wait()

    # Stop polling and wait for it to finish.
    if application.updater is not None:
        await application.updater.stop()
    await application.stop()
    await application.shutdown()

    dispose_engine()
    logger.info("Shutdown complete.")


def main() -> None:
    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        logger.info("Interrupted.")


if __name__ == "__main__":
    main()
