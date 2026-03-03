from telegram import Update
from telegram.ext import ContextTypes, CallbackQueryHandler
from ..config import ADMIN_ID
from ..repo import set_request_status, get_request

def _is_admin(update: Update) -> bool:
    return bool(update.effective_user and update.effective_user.id == ADMIN_ID)

async def on_admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if not _is_admin(update):
        await q.edit_message_text("Non autorizzato.")
        return

    # A|CONF|123
    _, action, req_id_s = q.data.split("|")
    req_id = int(req_id_s)

    lr = get_request(req_id)
    if not lr:
        await q.edit_message_text("Richiesta non trovata.")
        return

    if action == "CONF":
        set_request_status(req_id, "CONFIRMED")
        await q.edit_message_text(f"✅ Confermata richiesta #{req_id}")
        # TODO: notify student (Step 4: serve user telegram_id; lo aggiungiamo con join su users)
        return

    if action == "REJ":
        set_request_status(req_id, "REJECTED")
        await q.edit_message_text(f"❌ Rifiutata richiesta #{req_id}")
        # TODO: notify student
        return

def get_handlers():
    return [
        CallbackQueryHandler(on_admin_action, pattern=r"^A\|"),
    ]