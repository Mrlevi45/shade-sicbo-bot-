"""
SHADE Sic Bo Telegram Bot — non-wagering prototype

Features:
- /start: explains the bot
- /roll: rolls three dice and reports the Sic Bo result
- /rules: explains the basic dice outcomes
- /recent: shows recent results in this running session

This prototype does NOT accept bets, hold funds, maintain balances,
or make payouts. It is intended for a non-monetary game prototype.
"""

import logging
import os
import random
from collections import deque

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
RECENT_RESULTS = deque(maxlen=10)


def classify_roll(dice):
    total = sum(dice)

    # In standard Sic Bo, triples are neither Big nor Small.
    if dice[0] == dice[1] == dice[2]:
        return total, "TRIPLE"
    if 4 <= total <= 10:
        return total, "SMALL"
    if 11 <= total <= 17:
        return total, "BIG"
    return total, "SPECIAL"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = (
        "🎲 Welcome to SHADE SIC BO!\n\n"
        "This is the SHADE three-dice game bot.\n\n"
        "Use /roll to roll three dice.\n"
        "Use /rules to see the basic outcomes.\n"
        "Use /recent to see recent rolls.\n\n"
        "This prototype uses no real-money bets or payouts."
    )
    await update.effective_message.reply_text(message)


async def roll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    dice = [random.randint(1, 6) for _ in range(3)]
    total, outcome = classify_roll(dice)

    dice_display = "  ".join(f"🎲 {value}" for value in dice)
    result_text = (
        "🎲 SHADE SIC BO — RESULT\n\n"
        f"{dice_display}\n\n"
        f"Total: {total}\n"
        f"Outcome: {outcome}"
    )

    RECENT_RESULTS.appendleft(
        f"{dice[0]}-{dice[1]}-{dice[2]} | Total {total} | {outcome}"
    )
    await update.effective_message.reply_text(result_text)


async def rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = (
        "📜 SHADE SIC BO — BASIC RULES\n\n"
        "Three six-sided dice are rolled.\n\n"
        "• SMALL: total of 4–10, excluding triples.\n"
        "• BIG: total of 11–17, excluding triples.\n"
        "• TRIPLE: all three dice show the same number.\n"
        "• Totals 3 and 18 are always triples.\n\n"
        "Use /roll to generate a result."
    )
    await update.effective_message.reply_text(message)


async def recent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not RECENT_RESULTS:
        await update.effective_message.reply_text(
            "There are no rolls yet. Use /roll to start."
        )
        return

    lines = "\n".join(
        f"{index}. {result}"
        for index, result in enumerate(RECENT_RESULTS, start=1)
    )
    await update.effective_message.reply_text(
        f"🕘 RECENT SHADE SIC BO RESULTS\n\n{lines}"
    )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.exception("An error occurred while handling an update:", exc_info=context.error)


def main():
    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN is missing. Set it as an environment variable "
            "in your hosting provider's secret/environment settings."
        )

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("roll", roll))
    app.add_handler(CommandHandler("rules", rules))
    app.add_handler(CommandHandler("recent", recent))
    app.add_error_handler(error_handler)

    logger.info("SHADE Sic Bo bot is starting.")
    app.run_polling()


if __name__ == "__main__":
    main()
