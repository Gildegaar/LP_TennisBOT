from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes, CallbackQueryHandler, MessageHandler, filters

from ..states import DRAFTS, STEPS, LessonDraft
from ..keyboards import kb_dates, kb_times, kb_durations, kb_locations, kb_review, kb_main_menu
from ..repo import list_locations, get_user_by_telegram_id, create_lesson_request
from ..config import TZ, ADMIN_ID
from ..keyboards import kb_admin_request
import zoneinfo
from ..repo import list_user_requests, get_location_name
from telegram.ext import CommandHandler

rome = zoneinfo.ZoneInfo(TZ)

def _dm_only(update: Update) -> bool:
    return bool(update.effective_chat and update.effective_chat.type == "private")

async def on_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if not _dm_only(update):
        await q.edit_message_text("Scrivimi in DM 🙂")
        return

    if q.data == "M|HOME":
        STEPS.pop(q.from_user.id, None)
        DRAFTS.pop(q.from_user.id, None)
        await q.edit_message_text("Scegli un’opzione:", reply_markup=kb_main_menu())
        return

    if q.data == "M|REQ":
        DRAFTS[q.from_user.id] = LessonDraft()
        STEPS[q.from_user.id] = "DATE"
        await q.edit_message_text("Seleziona una data:", reply_markup=kb_dates())
        return

    if q.data == "M|MY":
        reqs = list_user_requests(q.from_user.id, limit=10)
        if not reqs:
            await q.edit_message_text("Non hai ancora richieste. Premi 📅 Richiedi lezione.", reply_markup=kb_main_menu())
            return

        lines = ["🗓 Le tue richieste (ultime 10):"]
        for r in reqs:
            when = r.start_dt.astimezone(rome).strftime("%a %d/%m %H:%M")
            loc = get_location_name(r.location_id)
            price = f" — €{(r.price_cents or 0)/100:.2f}" if (r.status == "CONFIRMED" and r.price_cents) else ""
            lines.append(f"- #{r.id} | {r.status} | {when} ({r.duration_min}m) | {loc}{price}")
        await q.edit_message_text("\n".join(lines), reply_markup=kb_main_menu())
        return

async def on_wizard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id

    if not _dm_only(update):
        await q.edit_message_text("Scrivimi in DM 🙂")
        return

    if uid not in DRAFTS:
        DRAFTS[uid] = LessonDraft()

    draft = DRAFTS[uid]
    parts = q.data.split("|")  # W|STEP|VALUE
    step = parts[1]

    if step == "CANCEL":
        STEPS.pop(uid, None)
        DRAFTS.pop(uid, None)
        await q.edit_message_text("Operazione annullata.", reply_markup=kb_main_menu())
        return

    if step == "BACK":
        # MVP: semplice back to specific
        target = parts[2]
        STEPS[uid] = target
        if target == "DATE":
            await q.edit_message_text("Seleziona una data:", reply_markup=kb_dates())
        elif target == "TIME":
            await q.edit_message_text("Seleziona un orario:", reply_markup=kb_times())
        elif target == "DUR":
            await q.edit_message_text("Seleziona una durata:", reply_markup=kb_durations())
        return

    if step == "DATE":
        draft.date = parts[2]
        STEPS[uid] = "TIME"
        await q.edit_message_text("Seleziona un orario:", reply_markup=kb_times())
        return

    if step == "TIME":
        draft.time = parts[2]
        STEPS[uid] = "DUR"
        await q.edit_message_text("Seleziona una durata:", reply_markup=kb_durations())
        return

    if step == "DUR":
        draft.duration = int(parts[2])
        STEPS[uid] = "LOC"
        locs = list_locations(active_only=True)
        if not locs:
            await q.edit_message_text("⚠️ Nessuna location disponibile. Scrivi all’istruttore per configurarle.", reply_markup=kb_main_menu())
            STEPS.pop(uid, None)
            DRAFTS.pop(uid, None)
            return
        await q.edit_message_text("Seleziona una location:", reply_markup=kb_locations(locs))
        return

    if step == "LOC":
        draft.location_id = int(parts[2])
        STEPS[uid] = "REVIEW"
        await q.edit_message_text(_render_review(draft), reply_markup=kb_review())
        return

    if step == "NOTE":
        STEPS[uid] = "NOTES"
        await q.edit_message_text("Scrivi la nota (oppure /skip per saltare).")
        return

    if step == "SEND":
        # validate
        if not (draft.date and draft.time and draft.duration and draft.location_id):
            await q.edit_message_text("Manca qualche campo, riprova.", reply_markup=kb_main_menu())
            return

        user = get_user_by_telegram_id(uid)
        if not user:
            await q.edit_message_text("Errore: utente non registrato. Usa /start.", reply_markup=kb_main_menu())
            return

        dt = datetime.fromisoformat(f"{draft.date}T{draft.time}:00").replace(tzinfo=rome)
        lr = create_lesson_request(
            user_id=user.id,
            start_dt=dt,
            duration_min=draft.duration,
            location_id=draft.location_id,
            notes=draft.notes,
        )

        # notify student
        STEPS.pop(uid, None)
        DRAFTS.pop(uid, None)
        await q.edit_message_text(f"Richiesta inviata ✅ (ID {lr.id})\nTi confermo appena possibile.", reply_markup=kb_main_menu())

        # notify admin
        loc_name = get_location_name(lr.location_id)
        msg = (
            f"🎾 Nuova richiesta (#{lr.id})\n"
            f"Da: {q.from_user.full_name} (@{q.from_user.username or '-'})\n"
            f"Quando: {dt.strftime('%a %d/%m/%Y %H:%M')} ({lr.duration_min} min)\n"
            f"Dove: {loc_name}\n"
            f"Note: {lr.notes or '-'}"
        )
        await context.bot.send_message(chat_id=ADMIN_ID, text=msg, reply_markup=kb_admin_request(lr.id))
        return

def _render_review(draft: LessonDraft) -> str:
    return (
        "📋 Riepilogo richiesta:\n"
        f"- Data: {draft.date}\n"
        f"- Ora: {draft.time}\n"
        f"- Durata: {draft.duration} min\n"
        f"- Location ID: {draft.location_id}\n"
        f"- Note: {draft.notes or '-'}\n\n"
        "Confermi l’invio?"
    )

async def on_notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _dm_only(update):
        return
    u = update.effective_user
    if not u:
        return
    uid = u.id
    if STEPS.get(uid) != "NOTES":
        return

    if uid not in DRAFTS:
        DRAFTS[uid] = LessonDraft()

    text = (update.message.text or "").strip()
    if text.lower() == "/skip":
        DRAFTS[uid].notes = None
    else:
        DRAFTS[uid].notes = text

    STEPS[uid] = "REVIEW"
    await update.message.reply_text(_render_review(DRAFTS[uid]), reply_markup=kb_review())

def get_handlers():
    return [
        CallbackQueryHandler(on_menu, pattern=r"^M\|"),
        CallbackQueryHandler(on_wizard, pattern=r"^W\|"),
        MessageHandler(filters.TEXT & ~filters.COMMAND, on_notes),
        CommandHandler("skip", skip_note),
    ]
    

async def skip_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _dm_only(update):
        return
    u = update.effective_user
    if not u:
        return
    uid = u.id
    if STEPS.get(uid) != "NOTES":
        return
    if uid not in DRAFTS:
        DRAFTS[uid] = LessonDraft()
    DRAFTS[uid].notes = None
    STEPS[uid] = "REVIEW"
    await update.message.reply_text(_render_review(DRAFTS[uid]), reply_markup=kb_review())