"""
keyboards.py — Button layouts.

Every InlineKeyboardButton carries a `callback_data` string.
Those strings are handled in handlers.py (user buttons) and admin.py (admin buttons).
Keep the strings in sync — this module is the single source of truth.
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

# Callback data constants (avoids typos across files).
CB_SERVICES = "cb_services"
CB_TG_ADS = "cb_tg_ads"
CB_BOT_DEV = "cb_bot_dev"
CB_PRICING = "cb_pricing"
CB_SUPPORT = "cb_support"
CB_ABOUT = "cb_about"
CB_MENU = "cb_menu"


def main_menu() -> InlineKeyboardMarkup:
    """
    Main interactive menu shown on /start, /menu, and /help.
    2 columns for the first four buttons, full-width for the last two.
    """
    keyboard = [
        [
            InlineKeyboardButton("🏢 Our Services", callback_data=CB_SERVICES),
            InlineKeyboardButton("📢 Telegram Ads", callback_data=CB_TG_ADS),
        ],
        [
            InlineKeyboardButton("🤖 Bot Development", callback_data=CB_BOT_DEV),
            InlineKeyboardButton("💰 Pricing & Enquiries", callback_data=CB_PRICING),
        ],
        [
            InlineKeyboardButton("💬 Talk to Support", callback_data=CB_SUPPORT),
        ],
        [
            InlineKeyboardButton("ℹ️ About Olamidesk", callback_data=CB_ABOUT),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def back_to_menu() -> InlineKeyboardMarkup:
    """A single button to return to the main menu (used after detail replies)."""
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to Menu", callback_data=CB_MENU)]])
