from __future__ import annotations

from datetime import datetime, timedelta
import random
import zoneinfo

from telegram import Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from ..config import ADMIN_ID, TZ
from ..states import ADMIN_PENDING_PRICE, ADMIN_EDIT
from ..db import wipe_all_hard

from ..keyboards import (
    kb_price,
    kb_admin_manage,
    kb_edit_dates,
    kb_edit_times,
    kb_edit_durations,
    kb_edit_locations,
    kb_send_proposal,
    kb_student_proposal,
    kb_manage_lessons_entry,
    kb_manage_lessons_list,
)

from ..repo import (
    # lesson requests
    get_request_with_user,
    set_request_status,
    set_request_price_and_confirm,

    # locations
    list_locations,
    get_location_name,

    # edit/cancel
    set_proposal,
    cancel_lesson,
    clear_proposal,

    # users
    get_user_by_username,
    get_user_by_telegram_id,
    list_students,

    # accounting
    create_payment,
    student_totals,
    list_debtors,
    payments_sum_between,

    # lists
    list_pending_requests,
    list_confirmed_on_day,
    list_confirmed_between,
    list_upcoming_confirmed,
)

rome = zoneinfo.ZoneInfo(TZ)
WIPE_TOKENS: dict[int, str] = {}


def _is_admin(update: Update) -> bool:
    return bool(update.effective_user and update.effective_user.id == ADMIN_ID)


def _fmt_eur(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    cents = abs(int(cents))
    return f"{sign}€{cents/100:.2f}"


def _parse_amount_to_cents(s: str) -> int | None:
    s = (s or "").strip().replace("€", "").replace(" ", "")
    s = s.replace(",", ".")
    try:
        val = float(s)
    except ValueError:
        return None
    if val <= 0:
        return None
    return int(round(val * 100))


def _resolve_student_to_user_id(arg: str) -> int | None:
    if arg.startswith("@"):
        u = get_user_by_username(arg)
        return u.id if u else None
    try:
        tg_id = int(arg)
    except ValueError:
        return None
    u = get_user_by_telegram_id(tg_id)
    return u.id if u else None


def _day_start(d: datetime) -> datetime:
    return d.astimezone(rome).replace(hour=0, minute=0, second=0, microsecond=0)


# -----------------------
# WIPE ALL
# -----------------------
async def wipe_all_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        return
    token = f"WIPE-{random.randint(1000, 9999)}"
    WIPE_TOKENS[ADMIN_ID] = token
    await update.message.reply_text(
        "⚠️ ATTENZIONE: questo comando cancella TUTTO (studenti, lezioni, pagamenti, location) e resetta gli ID.\n\n"
        f"Per confermare, invia:\n/wipe_all_confirm {token}"
    )


async def wipe_all_confirm_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        return
    if not context.args:
        await update.message.reply_text("Uso: /wipe_all_confirm <TOKEN>")
        return

    token = context.args[0].strip()
    expected = WIPE_TOKENS.get(ADMIN_ID)
    if not expected or token != expected:
        await update.message.reply_text("Token non valido o scaduto. Riesegui /wipe_all.")
        return

    wipe_all_hard()
    WIPE_TOKENS.pop(ADMIN_ID, None)
    await update.message.reply_text("💥 Wipe totale completato. Database tornato a tavola bianca.")


# -----------------------
# CALLBACKS: admin actions A|
# -----------------------
async def on_admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if not _is_admin(update):
        await q.edit_message_text("Non autorizzato.")
        return

    parts = q.data.split("|")
    # A|CONF|id / A|REJ|id / A|P|id|euro / A|PO|id / A|PCANCEL|id / A|EDIT|id / A|CANCEL|id
    if len(parts) < 3:
        await q.edit_message_text("Azione non valida.")
        return

    action = parts[1]
    req_id = int(parts[2])

    if action == "CONF":
        ok = set_request_status(req_id, "AWAITING_PRICE")
        if not ok:
            await q.edit_message_text("Richiesta non trovata.")
            return
        await q.edit_message_text(f"✅ Richiesta #{req_id} confermata. Ora imposta il prezzo (obbligatorio).")
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"💶 Prezzo per richiesta #{req_id}:",
            reply_markup=kb_price(req_id),
        )
        return

    if action == "REJ":
        ok = set_request_status(req_id, "REJECTED")
        if not ok:
            await q.edit_message_text("Richiesta non trovata.")
            return
        await q.edit_message_text(f"❌ Rifiutata richiesta #{req_id}")

        ru = get_request_with_user(req_id)
        if ru:
            lr, u = ru
            try:
                await context.bot.send_message(chat_id=u.telegram_id, text="La tua richiesta di lezione è stata rifiutata.")
            except Exception:
                pass
        return

    if action == "P":
        if len(parts) < 4:
            await q.edit_message_text("Prezzo non valido.")
            return

        euro = int(parts[3])
        cents = euro * 100

        ru = get_request_with_user(req_id)
        if not ru:
            await q.edit_message_text("Richiesta non trovata.")
            return
        lr, u = ru

        ok = set_request_price_and_confirm(req_id, cents)
        if not ok:
            await q.edit_message_text("Errore salvataggio prezzo.")
            return

        await q.edit_message_text(f"✅ Prezzo impostato: €{euro} — richiesta #{req_id} confermata.")

        when = lr.start_dt.astimezone(rome).strftime("%a %d/%m/%Y %H:%M")
        loc_name = get_location_name(lr.location_id)
        dur = lr.duration_min
        msg = (
            "🎾 Lezione confermata ✅\n"
            f"Quando: {when}\n"
            f"Durata: {dur} min\n"
            f"Dove: {loc_name}\n"
            f"Prezzo: {_fmt_eur(cents)}"
        )
        try:
            await context.bot.send_message(chat_id=u.telegram_id, text=msg)
        except Exception:
            pass

        await context.bot.send_message(chat_id=ADMIN_ID, text=f"🧾 Gestione lezione #{req_id}", reply_markup=kb_admin_manage(req_id))
        return

    if action == "PO":
        ADMIN_PENDING_PRICE[ADMIN_ID] = req_id
        await q.edit_message_text(f"✍️ Scrivi ora l’importo in euro per la richiesta #{req_id} (es. 25 o 27,50).")
        return

    if action == "PCANCEL":
        set_request_status(req_id, "PENDING")
        ADMIN_PENDING_PRICE.pop(ADMIN_ID, None)
        await q.edit_message_text(f"Operazione annullata. Richiesta #{req_id} tornata in PENDING.")
        return

    if action == "CANCEL":
        await q.edit_message_text(f"🗑 Annullamento lezione #{req_id} in corso...")

        ru = get_request_with_user(req_id)
        if not ru:
            await context.bot.send_message(chat_id=ADMIN_ID, text="Richiesta/lezione non trovata.")
            return
        lr, u = ru

        try:
            ok = cancel_lesson(req_id, reason=None)
        except Exception as e:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"❌ Errore DB durante annullamento: {type(e).__name__}: {e}",
            )
            # rimanda comunque scheda gestione
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"🧾 Gestione lezione #{req_id}", reply_markup=kb_admin_manage(req_id))
            return

        if not ok:
            await context.bot.send_message(chat_id=ADMIN_ID, text="❌ Errore annullamento (ok=False).")
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"🧾 Gestione lezione #{req_id}", reply_markup=kb_admin_manage(req_id))
            return

        # notifica studente
        try:
            await context.bot.send_message(
                chat_id=u.telegram_id,
                text="🗑 La lezione è stata annullata dall’istruttore. Se vuoi, invia una nuova richiesta.",
            )
        except Exception:
            await context.bot.send_message(chat_id=ADMIN_ID, text="⚠️ Non riesco a contattare lo studente in DM.")

        await context.bot.send_message(chat_id=ADMIN_ID, text=f"✅ Lezione #{req_id} annullata.")
        await context.bot.send_message(chat_id=ADMIN_ID, text=f"🧾 Gestione lezione #{req_id}", reply_markup=kb_admin_manage(req_id))
        return

    if action == "EDIT":
        ru = get_request_with_user(req_id)
        if not ru:
            await q.edit_message_text("Richiesta/lezione non trovata.")
            return

        ADMIN_EDIT[ADMIN_ID] = {"req_id": req_id, "date": None, "time": None, "dur": None, "loc_id": None}
        await q.edit_message_text(f"✏️ Modifica lezione #{req_id}: scegli una nuova data.")
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"📅 Nuova data per #{req_id}:",
            reply_markup=kb_edit_dates(req_id),
        )
        return

    await q.edit_message_text("Azione non riconosciuta.")


# -----------------------
# CALLBACKS: admin edit wizard E|
# -----------------------
async def on_admin_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if not _is_admin(update):
        await q.edit_message_text("Non autorizzato.")
        return

    parts = q.data.split("|")
    # E|DATE|req|YYYY-MM-DD
    # E|TIME|req|HH:MM
    # E|DUR|req|60
    # E|LOC|req|loc_id
    # E|SEND|req|1
    # E|BACK|req|DATE/TIME/DUR
    # E|ABORT|req
    if len(parts) < 3:
        await q.edit_message_text("Comando edit non valido.")
        return

    action = parts[1]
    req_id = int(parts[2])

    draft = ADMIN_EDIT.get(ADMIN_ID)
    if not draft or draft.get("req_id") != req_id:
        ADMIN_EDIT[ADMIN_ID] = {"req_id": req_id, "date": None, "time": None, "dur": None, "loc_id": None}
        draft = ADMIN_EDIT[ADMIN_ID]

    if action == "ABORT":
        # ripristina eventuale proposta rimasta e rimanda scheda gestione
        try:
            clear_proposal(req_id)
        except Exception:
            pass

        ADMIN_EDIT.pop(ADMIN_ID, None)
        await q.edit_message_text(f"Modifica annullata per #{req_id}.")
        await context.bot.send_message(chat_id=ADMIN_ID, text=f"🧾 Gestione lezione #{req_id}", reply_markup=kb_admin_manage(req_id))
        return

    if action == "BACK":
        target = parts[3] if len(parts) >= 4 else "DATE"
        if target == "DATE":
            await q.edit_message_text("📅 Scegli una nuova data:", reply_markup=kb_edit_dates(req_id))
        elif target == "TIME":
            await q.edit_message_text("🕒 Scegli un nuovo orario:", reply_markup=kb_edit_times(req_id))
        elif target == "DUR":
            await q.edit_message_text("⏱ Scegli una durata:", reply_markup=kb_edit_durations(req_id))
        return

    if action == "DATE":
        draft["date"] = parts[3]
        await q.edit_message_text("🕒 Scegli un nuovo orario:", reply_markup=kb_edit_times(req_id))
        return

    if action == "TIME":
        draft["time"] = parts[3]
        await q.edit_message_text("⏱ Scegli una durata:", reply_markup=kb_edit_durations(req_id))
        return

    if action == "DUR":
        draft["dur"] = int(parts[3])
        locs = list_locations(active_only=True)
        if not locs:
            ADMIN_EDIT.pop(ADMIN_ID, None)
            await q.edit_message_text("⚠️ Nessuna location attiva. Configura le location e riprova.")
            return
        await q.edit_message_text("📍 Scegli una location:", reply_markup=kb_edit_locations(req_id, locs))
        return

    if action == "LOC":
        draft["loc_id"] = int(parts[3])
        await q.edit_message_text("📨 Vuoi inviare la proposta allo studente?", reply_markup=kb_send_proposal(req_id))
        return

    if action == "SEND":
        # ack immediato
        await q.edit_message_text("📨 Invio proposta in corso...")

        if not (draft.get("date") and draft.get("time") and draft.get("dur") and draft.get("loc_id")):
            ADMIN_EDIT.pop(ADMIN_ID, None)
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"❌ Proposta incompleta per #{req_id}. Rifai ✏️ Modifica.")
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"🧾 Gestione lezione #{req_id}", reply_markup=kb_admin_manage(req_id))
            return

        ru = get_request_with_user(req_id)
        if not ru:
            ADMIN_EDIT.pop(ADMIN_ID, None)
            await context.bot.send_message(chat_id=ADMIN_ID, text="❌ Lezione non trovata.")
            return

        lr, u = ru
        dt = datetime.fromisoformat(f"{draft['date']}T{draft['time']}:00").replace(tzinfo=rome)

        ok = set_proposal(req_id, dt, int(draft["dur"]), int(draft["loc_id"]))
        ADMIN_EDIT.pop(ADMIN_ID, None)

        if not ok:
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"❌ Errore nel salvataggio proposta per #{req_id}.")
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"🧾 Gestione lezione #{req_id}", reply_markup=kb_admin_manage(req_id))
            return

        when = dt.astimezone(rome).strftime("%a %d/%m/%Y %H:%M")
        loc_name = get_location_name(int(draft["loc_id"]))
        msg = (
            "✏️ Proposta modifica lezione\n"
            f"Nuovo orario: {when}\n"
            f"Durata: {draft['dur']} min\n"
            f"Dove: {loc_name}\n\n"
            "Accetti la modifica?"
        )

        try:
            await context.bot.send_message(chat_id=u.telegram_id, text=msg, reply_markup=kb_student_proposal(req_id))
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"✅ Proposta inviata allo studente per lezione #{req_id}.")
        except Exception:
            clear_proposal(req_id)
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text="⚠️ Non riesco a contattare lo studente in DM (forse non ha avviato il bot). Proposta annullata.",
            )

        await context.bot.send_message(chat_id=ADMIN_ID, text=f"🧾 Gestione lezione #{req_id}", reply_markup=kb_admin_manage(req_id))
        return

    await q.edit_message_text("Azione edit non riconosciuta.")


# -----------------------
# TEXT: admin enters custom price (Altro…)
# -----------------------
async def on_admin_price_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        return
    if update.effective_chat and update.effective_chat.type != "private":
        return

    req_id = ADMIN_PENDING_PRICE.get(ADMIN_ID)
    if not req_id:
        return

    cents = _parse_amount_to_cents((update.message.text or "").strip())
    if cents is None:
        await update.message.reply_text("Importo non valido. Scrivi un numero tipo 25 o 27,50.")
        return

    ru = get_request_with_user(req_id)
    if not ru:
        ADMIN_PENDING_PRICE.pop(ADMIN_ID, None)
        await update.message.reply_text("Richiesta non trovata.")
        return

    lr, u = ru
    ok = set_request_price_and_confirm(req_id, cents)
    ADMIN_PENDING_PRICE.pop(ADMIN_ID, None)

    if not ok:
        await update.message.reply_text("Errore salvataggio prezzo.")
        return

    when = lr.start_dt.astimezone(rome).strftime("%a %d/%m/%Y %H:%M")
    loc_name = get_location_name(lr.location_id)
    dur = lr.duration_min
    msg = (
        "🎾 Lezione confermata ✅\n"
        f"Quando: {when}\n"
        f"Durata: {dur} min\n"
        f"Dove: {loc_name}\n"
        f"Prezzo: {_fmt_eur(cents)}"
    )
    try:
        await context.bot.send_message(chat_id=u.telegram_id, text=msg)
    except Exception:
        pass

    await update.message.reply_text(f"✅ Prezzo impostato: {_fmt_eur(cents)} — richiesta #{req_id} confermata.")
    await context.bot.send_message(chat_id=ADMIN_ID, text=f"🧾 Gestione lezione #{req_id}", reply_markup=kb_admin_manage(req_id))


# -----------------------
# COMMAND: /setprice fallback
# -----------------------
async def setprice_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        return

    if len(context.args) < 2:
        await update.message.reply_text("Uso: /setprice <lesson_id> <importo>")
        return

    try:
        req_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("lesson_id non valido.")
        return

    cents = _parse_amount_to_cents(context.args[1])
    if cents is None:
        await update.message.reply_text("Importo non valido. Esempio: /setprice 1 15")
        return

    ru = get_request_with_user(req_id)
    if not ru:
        await update.message.reply_text("Richiesta non trovata.")
        return

    lr, u = ru
    ok = set_request_price_and_confirm(req_id, cents)
    if not ok:
        await update.message.reply_text("Errore salvataggio prezzo.")
        return

    when = lr.start_dt.astimezone(rome).strftime("%a %d/%m/%Y %H:%M")
    loc_name = get_location_name(lr.location_id)
    dur = lr.duration_min
    msg = (
        "🎾 Lezione confermata ✅\n"
        f"Quando: {when}\n"
        f"Durata: {dur} min\n"
        f"Dove: {loc_name}\n"
        f"Prezzo: {_fmt_eur(cents)}"
    )

    await update.message.reply_text(f"✅ Prezzo impostato: {_fmt_eur(cents)} — richiesta #{req_id} confermata.")
    try:
        await context.bot.send_message(chat_id=u.telegram_id, text=msg)
    except Exception:
        pass
    await context.bot.send_message(chat_id=ADMIN_ID, text=f"🧾 Gestione lezione #{req_id}", reply_markup=kb_admin_manage(req_id))


# -----------------------
# COMMANDS: students list
# -----------------------
async def studenti_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        return

    students = list_students()
    if not students:
        await update.message.reply_text("Nessuno studente registrato ancora.")
        return

    lines = ["👥 Studenti registrati:"]
    for u in students:
        uname = f"@{u.username}" if u.username else "-"
        full = f"{u.first_name} {u.last_name or ''}".strip()
        lines.append(f"- {full} | {uname} | tg_id: {u.telegram_id}")
    await update.message.reply_text("\n".join(lines))


# -----------------------
# COMMANDS: payments / accounting
# -----------------------
async def paid_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        return

    if len(context.args) < 2:
        await update.message.reply_text("Uso: /paid <@username|telegram_id> <importo> [nota]")
        return

    student_key = context.args[0]
    amount_s = context.args[1]
    note = " ".join(context.args[2:]).strip() or None

    user_id = _resolve_student_to_user_id(student_key)
    if not user_id:
        await update.message.reply_text("Studente non trovato. Usa @username oppure telegram_id.")
        return

    cents = _parse_amount_to_cents(amount_s)
    if cents is None:
        await update.message.reply_text("Importo non valido. Esempio: /paid @mario 25")
        return

    _, _, bal_before = student_totals(user_id)
    create_payment(user_id=user_id, amount_cents=cents, note=note)
    _, _, bal_after = student_totals(user_id)

    await update.message.reply_text(
        f"💶 Pagamento registrato: {_fmt_eur(cents)}\n"
        f"Saldo prima: {_fmt_eur(bal_before)}\n"
        f"Saldo ora: {_fmt_eur(bal_after)}"
    )


async def paidall_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        return

    if len(context.args) < 1:
        await update.message.reply_text("Uso: /paidall <@username|telegram_id> [nota]")
        return

    student_key = context.args[0]
    note = " ".join(context.args[1:]).strip() or None

    user_id = _resolve_student_to_user_id(student_key)
    if not user_id:
        await update.message.reply_text("Studente non trovato. Usa @username oppure telegram_id.")
        return

    _, _, bal = student_totals(user_id)
    if bal <= 0:
        await update.message.reply_text(f"Saldo già a posto: {_fmt_eur(bal)}")
        return

    create_payment(user_id=user_id, amount_cents=bal, note=note)
    await update.message.reply_text(f"✅ Saldo estinto con pagamento {_fmt_eur(bal)}. Nuovo saldo: €0.00")


async def crediti_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        return

    debtors = list_debtors()
    if not debtors:
        await update.message.reply_text("Nessun credito aperto ✅")
        return

    lines = ["📌 Crediti aperti (studenti che devono pagare):"]
    for u, bal in debtors:
        full = f"{u.first_name} {u.last_name or ''}".strip()
        uname = f" (@{u.username})" if u.username else ""
        lines.append(f"- {full}{uname}: {_fmt_eur(bal)} | tg_id: {u.telegram_id}")
    await update.message.reply_text("\n".join(lines))


async def saldo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        return

    if len(context.args) < 1:
        await update.message.reply_text("Uso: /saldo <@username|telegram_id>")
        return

    student_key = context.args[0]
    user_id = _resolve_student_to_user_id(student_key)
    if not user_id:
        await update.message.reply_text("Studente non trovato.")
        return

    lt, pt, bal = student_totals(user_id)
    await update.message.reply_text(
        "📒 Saldo studente\n"
        f"Totale lezioni (CONFIRMED): {_fmt_eur(lt)}\n"
        f"Totale pagamenti: {_fmt_eur(pt)}\n"
        f"Saldo (ti deve): {_fmt_eur(bal)}"
    )


def _period_range(period: str) -> tuple[datetime, datetime] | None:
    now = datetime.now(tz=rome)
    if period == "oggi":
        start = _day_start(now)
        return start, start + timedelta(days=1)
    if period == "settimana":
        start = _day_start(now) - timedelta(days=now.weekday())
        return start, start + timedelta(days=7)
    if period == "mese":
        start = _day_start(now).replace(day=1)
        end = start.replace(year=start.year + 1, month=1) if start.month == 12 else start.replace(month=start.month + 1)
        return start, end
    if period == "anno":
        start = _day_start(now).replace(month=1, day=1)
        return start, start.replace(year=start.year + 1)
    return None


async def incassi_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        return

    if len(context.args) < 1:
        await update.message.reply_text("Uso: /incassi oggi|settimana|mese|anno")
        return

    rng = _period_range(context.args[0].lower())
    if not rng:
        await update.message.reply_text("Periodo non valido. Usa: oggi|settimana|mese|anno")
        return

    dt_from, dt_to = rng
    total = payments_sum_between(dt_from, dt_to)
    await update.message.reply_text(f"💰 Incassi {context.args[0].lower()}: {_fmt_eur(total)}")


# -----------------------
# COMMANDS: lists
# -----------------------
async def pending_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        return

    rows = list_pending_requests(limit=30)
    if not rows:
        await update.message.reply_text("✅ Nessuna richiesta in attesa.")
        return

    lines = ["⏳ Richieste in attesa:"]
    for lr, u in rows:
        when = lr.start_dt.astimezone(rome).strftime("%a %d/%m %H:%M")
        uname = f"@{u.username}" if u.username else "-"
        full = f"{u.first_name} {u.last_name or ''}".strip()
        lines.append(f"- #{lr.id} | {lr.status} | {when} ({lr.duration_min}m) | {full} ({uname})")
    await update.message.reply_text("\n".join(lines))


async def oggi_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        return

    now = datetime.now(tz=rome)
    rows = list_confirmed_on_day(now)
    if not rows:
        await update.message.reply_text("🎾 Oggi: nessuna lezione confermata.")
        return

    lines = ["🎾 Lezioni confermate di oggi:"]
    for lr, u in rows:
        when = lr.start_dt.astimezone(rome).strftime("%H:%M")
        loc = get_location_name(lr.location_id)
        full = f"{u.first_name} {u.last_name or ''}".strip()
        price = _fmt_eur(lr.price_cents or 0)
        lines.append(f"- {when} | #{lr.id} | {full} | {loc} | {lr.duration_min}m | {price}")
    await update.message.reply_text("\n".join(lines))


async def lezioni_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        return

    args = context.args
    now = datetime.now(tz=rome)

    try:
        if not args:
            dt_from = now
            dt_to = now + timedelta(days=7)
        elif len(args) == 1 and args[0].isdigit():
            days = int(args[0])
            if days <= 0 or days > 60:
                await update.message.reply_text("Giorni non valido. Usa un numero tra 1 e 60.")
                return
            dt_from = now
            dt_to = now + timedelta(days=days)
        elif len(args) == 1:
            d = datetime.fromisoformat(args[0]).replace(tzinfo=rome)
            dt_from = _day_start(d)
            dt_to = dt_from + timedelta(days=1)
        else:
            d1 = datetime.fromisoformat(args[0]).replace(tzinfo=rome)
            d2 = datetime.fromisoformat(args[1]).replace(tzinfo=rome)
            dt_from = _day_start(d1)
            dt_to = _day_start(d2) + timedelta(days=1)
            if dt_to <= dt_from:
                await update.message.reply_text("Range non valido: la seconda data deve essere >= prima data.")
                return
    except ValueError:
        await update.message.reply_text("Formato data non valido. Usa YYYY-MM-DD (es. 2026-03-07).")
        return

    rows = list_confirmed_between(dt_from, dt_to)
    if not rows:
        await update.message.reply_text("📭 Nessuna lezione confermata nel periodo selezionato.")
        return

    lines = []
    total_cents = 0
    current_day = None

    for lr, u in rows:
        dt = lr.start_dt.astimezone(rome)
        day_key = dt.strftime("%Y-%m-%d")
        if day_key != current_day:
            current_day = day_key
            lines.append(f"\n📅 {dt.strftime('%a %d/%m/%Y')}")
        when = dt.strftime("%H:%M")
        loc = get_location_name(lr.location_id)
        full = f"{u.first_name} {u.last_name or ''}".strip()
        price_c = int(lr.price_cents or 0)
        total_cents += price_c
        lines.append(f"- {when} | #{lr.id} | {full} | {loc} | {lr.duration_min}m | {_fmt_eur(price_c)}")

    lines.append(f"\nΣ Totale periodo: {_fmt_eur(total_cents)}")
    await update.message.reply_text("\n".join(lines).strip(), reply_markup=kb_manage_lessons_entry(14))

async def on_manage_lessons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if not _is_admin(update):
        await q.edit_message_text("Non autorizzato.")
        return

    parts = q.data.split("|")
    # G|OPEN|days
    # G|SEL|id
    # G|CLOSE|1
    action = parts[1]

    if action == "CLOSE":
        await q.edit_message_reply_markup(reply_markup=None)
        return

    if action == "OPEN":
        days = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 14
        rows = list_upcoming_confirmed(days=days, limit=30)
        if not rows:
            await q.edit_message_text("📭 Nessuna lezione confermata nel periodo selezionato.")
            return

        items = []
        for lr, u in rows:
            dt = lr.start_dt.astimezone(rome)
            when = dt.strftime("%a %d/%m %H:%M")
            loc = get_location_name(lr.location_id)
            full = f"{u.first_name} {u.last_name or ''}".strip()
            items.append({"id": lr.id, "label": f"{when} — {full} — {loc}"})

        await q.edit_message_text("Seleziona una lezione da gestire:", reply_markup=kb_manage_lessons_list(items))
        return

    if action == "SEL":
        req_id = int(parts[2])
        # manda scheda gestione (riusa il sistema esistente)
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"🧾 Gestione lezione #{req_id}",
            reply_markup=kb_admin_manage(req_id),
        )
        return


def get_handlers():
    return [
        CallbackQueryHandler(on_admin_action, pattern=r"^A\|"),
        CallbackQueryHandler(on_admin_edit, pattern=r"^E\|"),
        CallbackQueryHandler(on_manage_lessons, pattern=r"^G\|"),
        MessageHandler(filters.TEXT & ~filters.COMMAND, on_admin_price_text),

        CommandHandler("setprice", setprice_cmd),

        CommandHandler("studenti", studenti_cmd),

        CommandHandler("paid", paid_cmd),
        CommandHandler("paidall", paidall_cmd),
        CommandHandler("crediti", crediti_cmd),
        CommandHandler("saldo", saldo_cmd),
        CommandHandler("incassi", incassi_cmd),

        CommandHandler("pending", pending_cmd),
        CommandHandler("oggi", oggi_cmd),
        CommandHandler("lezioni", lezioni_cmd),

        CommandHandler("wipe_all", wipe_all_cmd),
        CommandHandler("wipe_all_confirm", wipe_all_confirm_cmd),
        
    ]