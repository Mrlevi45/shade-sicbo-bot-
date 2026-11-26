"""
SHADE Sic Bo Telegram Bot

Commands:
  /start       Show the game menu
  /roll        Roll three dice
  /rules       Show the basic outcomes
  /rollturn    Give the highest-scoring player 10 seconds to roll;
               otherwise the bot rolls automatically
  /rollnow     Claim the active roll turn (selected player only)
  /score       Show the player leaderboard
  /addscore    Admin-only: add points to a player
  /recent      Show recent dice results

This version tracks points and game results only. It does not process
deposits, withdrawals, wagers, or money payouts.
"""

import asyncio
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
logger = logging.getLogger("shade_sicbo")

BOT_TOKEN = os.getenv("BOT_TOKEN")
RECENT_RESULTS = deque(maxlen=10)
PLAYER_SCORES = {}
ACTIVE_TURN = None
TURN_LOCK = asyncio.Lock()


def classify_roll(dice):
    total = sum(dice)
    if dice[0] == dice[1] == dice[2]:
        outcome = "TRIPLE"
    elif 4 <= total <= 10:
        outcome = "SMALL"
    elif 11 <= total <= 17:
        outcome = "BIG"
    else:
        outcome = "SPECIAL"
    return total, outcome


def make_result_text(dice, rolled_by):
    total, outcome = classify_roll(dice)
    RECENT_RESULTS.appendleft(
        f"{dice[0]}-{dice[1]}-{dice[2]} | Total {total} | {outcome}"
    )
    return (
        "🎲 SHADE SIC BO — ROUND RESULT\n\n"
        f"Rolled by: {rolled_by}\n"
        f"🎲 {dice[0]}   🎲 {dice[1]}   🎲 {dice[2]}\n\n"
        f"Total: {total}\n"
        f"Outcome: {outcome}"
    )


async def announce_roll(message, rolled_by):
    dice = [random.randint(1, 6) for _ in range(3)]
    await message.reply_text(make_result_text(dice, rolled_by))


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        "🎲 Welcome to SHADE SIC BO!\n\n"
        "/roll — roll three dice\n"
        "/rollturn — highest-scoring player gets first chance to roll\n"
        "/rollnow — roll when it is your turn\n"
        "/score — view the player leaderboard\n"
        "/rules — view the game outcomes\n"
        "/recent — view recent results"
    )


async def roll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await announce_roll(
        update.effective_message,
        user.full_name if user else "Player",
    )


async def rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        "📜 SHADE SIC BO — BASIC OUTCOMES\n\n"
        "Three six-sided dice are rolled.\n"
        "• SMALL: total 4–10, excluding triples.\n"
        "• BIG: total 11–17, excluding triples.\n"
        "• TRIPLE: all three dice show the same number.\n"
        "• Totals 3 and 18 are triples."
    )


async def score(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not PLAYER_SCORES:
        await update.effective_message.reply_text(
            "There are no player points recorded yet."
        )
        return

    ranked = sorted(
        PLAYER_SCORES.values(),
        key=lambda item: item["score"],
        reverse=True,
    )[:10]
    lines = [
        f"{index}. {item['name']} — {item['score']} points"
        for index, item in enumerate(ranked, start=1)
    ]
    await update.effective_message.reply_text(
        "🏆 SHADE SIC BO LEADERBOARD\n\n" + "\n".join(lines)
    )


async def addscore(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user

    if not chat or chat.type not in ("group", "supergroup") or not user:
        await update.effective_message.reply_text(
            "Use this command in the group."
        )
        return

    member = await context.bot.get_chat_member(chat.id, user.id)
    if member.status not in ("administrator", "creator"):
        await update.effective_message.reply_text(
            "Only group administrators can add points."
        )
        return

    replied = update.effective_message.reply_to_message
    if not replied or not replied.from_user:
        await update.effective_message.reply_text(
            "Reply to a player's message with /addscore 10."
        )
        return

    if len(context.args) != 1:
        await update.effective_message.reply_text(
            "Usage: reply to a player's message with /addscore 10."
        )
        return

    try:
        points = int(context.args[0])
        if not 1 <= points <= 1000:
            raise ValueError
    except ValueError:
        await update.effective_message.reply_text(
            "Enter a points amount from 1 to 1000."
        )
        return

    target = replied.from_user
    record = PLAYER_SCORES.setdefault(
        target.id,
        {"name": target.full_name, "score": 0},
    )
    record["name"] = target.full_name
    record["score"] += points

    await update.effective_message.reply_text(
        f"🏅 Added {points} points to {target.full_name}."
    )


async def rollturn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global ACTIVE_TURN

    chat = update.effective_chat
    if not chat:
        return

    async with TURN_LOCK:
        if ACTIVE_TURN is not None:
            await update.effective_message.reply_text(
                "A roll turn is already in progress. Please wait."
            )
            return

        if not PLAYER_SCORES:
            await update.effective_message.reply_text(
                "There are no player scores yet. A group admin can add "
                "points by replying to a player's message with /addscore 10."
            )
            return

        top_score = max(item["score"] for item in PLAYER_SCORES.values())
        leaders = [
            (uid, item)
            for uid, item in PLAYER_SCORES.items()
            if item["score"] == top_score
        ]
        # If scores are tied, choose randomly among the tied leaders.
        selected_id, selected = random.choice(leaders)
        ACTIVE_TURN = {"user_id": selected_id, "chat_id": chat.id}

    await update.effective_message.reply_text(
        f"🎲 {selected['name']} has the highest score "
        f"({selected['score']} points) and gets the first roll.\n\n"
        "They have 10 seconds to send /rollnow. "
        "If they don't, SHADE will roll automatically."
    )
    context.application.create_task(
        auto_roll_after_timeout(context, chat.id, selected_id)
    )


async def rollnow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global ACTIVE_TURN
    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat:
        return

    async with TURN_LOCK:
        if (
            ACTIVE_TURN is None
            or ACTIVE_TURN["user_id"] != user.id
            or ACTIVE_TURN["chat_id"] != chat.id
        ):
            await update.effective_message.reply_text(
                "It's not your active roll turn."
            )
            return
        ACTIVE_TURN = None

    await announce_roll(update.effective_message, user.full_name)


async def auto_roll_after_timeout(context, chat_id, selected_id):
    global ACTIVE_TURN
    await asyncio.sleep(10)

    async with TURN_LOCK:
        if (
            ACTIVE_TURN is None
            or ACTIVE_TURN["user_id"] != selected_id
            or ACTIVE_TURN["chat_id"] != chat_id
        ):
            return
        ACTIVE_TURN = None

    dice = [random.randint(1, 6) for _ in range(3)]
    await context.bot.send_message(
        chat_id=chat_id,
        text="⏱️ Time is up! SHADE is rolling automatically.\n\n"
        + make_result_text(dice, "SHADE Bot (automatic roll)"),
    )


async def recent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not RECENT_RESULTS:
        await update.effective_message.reply_text(
            "No results yet. Use /roll to begin."
        )
        return

    lines = "\n".join(
        f"{index}. {item}"
        for index, item in enumerate(RECENT_RESULTS, start=1)
    )
    await update.effective_message.reply_text(
        "🕘 RECENT SHADE SIC BO RESULTS\n\n" + lines
    )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Unhandled bot error: %s", context.error)


def main():
    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN is missing. Add it as a secret/environment variable "
            "in your hosting service. Never put the token in this file."
        )

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("roll", roll))
    app.add_handler(CommandHandler("rules", rules))
    app.add_handler(CommandHandler("score", score))
    app.add_handler(CommandHandler("addscore", addscore))
    app.add_handler(CommandHandler("rollturn", rollturn))
    app.add_handler(CommandHandler("rollnow", rollnow))
    app.add_handler(CommandHandler("recent", recent))
    app.add_error_handler(error_handler)

    logger.info("SHADE Sic Bo bot starting.")
    app.run_polling()


if __name__ == "__main__":
    main()
