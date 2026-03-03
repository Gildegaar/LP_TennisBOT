from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from ..repo import upsert_user
from ..keyboards import kb_main_menu
from telegram.constants import ParseMode
from ..config import ADMIN_ID
from ..text import STUDENT_HELP, ADMIN_HELP

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
        STUDENT_HELP,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb_main_menu(),
    )

    if user.id == ADMIN_ID:
        await update.message.reply_text(ADMIN_HELP, parse_mode=ParseMode.MARKDOWN)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat and update.effective_chat.type != "private":
        await update.message.reply_text("Scrivimi in DM 🙂")
        return

    user = update.effective_user
    await update.message.reply_text(
        STUDENT_HELP,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb_main_menu(),
    )

    if user and user.id == ADMIN_ID:
        await update.message.reply_text(ADMIN_HELP, parse_mode=ParseMode.MARKDOWN)

async def whoami(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user:
        await update.message.reply_text(f"Il tuo Telegram ID è: {update.effective_user.id}")

def get_handlers():
    return [
        CommandHandler("start", start),
        CommandHandler("help", help_cmd),
        CommandHandler("whoami", whoami),
    ]
    
