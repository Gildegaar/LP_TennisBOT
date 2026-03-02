from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from ..repo import upsert_user

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat and update.effective_chat.type != "private":
        await update.message.reply_text("Scrivimi in DM 🙂")
        return

    user = update.effective_user
    upsert_user(
        telegram_id=user.id,
        first_name=user.first_name or "",
        last_name=user.last_name,
        username=user.username,
    )

    await update.message.reply_text(
        "Ciao! Sono LP_TennisBot.\n\n"
        "Comandi utili:\n"
        "/whoami - mostra il tuo Telegram ID\n"
    )

async def whoami(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user:
        await update.message.reply_text(f"Il tuo Telegram ID è: {update.effective_user.id}")

def get_handlers():
    return [
        CommandHandler("start", start),
        CommandHandler("whoami", whoami),
    ]