from telegram import Update
from telegram.ext import ContextTypes, CommandHandler

from ..config import ADMIN_ID
from ..repo import add_location, list_locations, deactivate_location
from ..repo import activate_location, purge_location, deactivate_all_locations

def _is_admin(update: Update) -> bool:
    return bool(update.effective_user and update.effective_user.id == ADMIN_ID)

async def loc_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat and update.effective_chat.type != "private":
        await update.message.reply_text("Scrivimi in DM 🙂")
        return
    if not _is_admin(update):
        await update.message.reply_text("Comando riservato all’admin.")
        return

    if not context.args:
        await update.message.reply_text('Uso: /loc_add Nome Location')
        return

    name = " ".join(context.args).strip()
    try:
        loc = add_location(name)
        await update.message.reply_text(f"Location aggiunta ✅\nID: {loc.id}\nNome: {loc.name}")
    except Exception:
        # unique constraint ecc.
        await update.message.reply_text("Errore: forse esiste già una location con lo stesso nome.")

async def loc_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat and update.effective_chat.type != "private":
        await update.message.reply_text("Scrivimi in DM 🙂")
        return
    if not _is_admin(update):
        await update.message.reply_text("Comando riservato all’admin.")
        return

    locs = list_locations(active_only=False)
    if not locs:
        await update.message.reply_text("Nessuna location ancora. Usa /loc_add Nome")
        return

    lines = ["📍 Location:"]
    for l in locs:
        status = "✅" if l.active else "🚫"
        lines.append(f"{status} {l.id} — {l.name}")
    await update.message.reply_text("\n".join(lines))

async def loc_del(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat and update.effective_chat.type != "private":
        await update.message.reply_text("Scrivimi in DM 🙂")
        return
    if not _is_admin(update):
        await update.message.reply_text("Comando riservato all’admin.")
        return

    if not context.args:
        await update.message.reply_text("Uso: /loc_del <id>")
        return

    try:
        loc_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("ID non valido. Esempio: /loc_del 3")
        return

    ok = deactivate_location(loc_id)
    if ok:
        await update.message.reply_text(f"Location {loc_id} disattivata ✅")
    else:
        await update.message.reply_text("Location non trovata.")
    
async def loc_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat and update.effective_chat.type != "private":
        await update.message.reply_text("Scrivimi in DM 🙂")
        return
    if not _is_admin(update):
        await update.message.reply_text("Comando riservato all’admin.")
        return
    if not context.args:
        await update.message.reply_text("Uso: /loc_on <id>")
        return
    try:
        loc_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("ID non valido.")
        return

    ok = activate_location(loc_id)
    await update.message.reply_text("Location riattivata ✅" if ok else "Location non trovata.")

async def loc_purge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat and update.effective_chat.type != "private":
        await update.message.reply_text("Scrivimi in DM 🙂")
        return
    if not _is_admin(update):
        await update.message.reply_text("Comando riservato all’admin.")
        return
    if not context.args:
        await update.message.reply_text("Uso: /loc_purge <id>")
        return
    try:
        loc_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("ID non valido.")
        return

    try:
        ok = purge_location(loc_id)
    except Exception:
        await update.message.reply_text(
            "Non posso cancellarla definitivamente perché è collegata a lezioni già salvate.\n"
            "Usa /loc_del per disattivarla."
        )
        return

    await update.message.reply_text("Location eliminata definitivamente ✅" if ok else "Location non trovata.")

async def loc_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat and update.effective_chat.type != "private":
        await update.message.reply_text("Scrivimi in DM 🙂")
        return
    if not _is_admin(update):
        await update.message.reply_text("Comando riservato all’admin.")
        return

    n = deactivate_all_locations()
    await update.message.reply_text(f"Reset completato ✅ Location disattivate: {n}")
    

def get_handlers():
    return [
        CommandHandler("loc_add", loc_add),
        CommandHandler("loc_list", loc_list),
        CommandHandler("loc_del", loc_del),
        CommandHandler("loc_on", loc_on),
    CommandHandler("loc_purge", loc_purge),
    CommandHandler("loc_reset", loc_reset),
    ]