from datetime import datetime
import zoneinfo

from telegram import Update
from telegram.ext import ContextTypes, CallbackQueryHandler, MessageHandler, filters, CommandHandler

from ..config import ADMIN_ID, TZ
from ..states import ADMIN_PENDING_PRICE
from ..keyboards import kb_price
from ..repo import (
    get_request_with_user,
    set_request_status,
    set_request_price_and_confirm,
    get_user_by_username,
    get_user_by_telegram_id,
    create_payment,
    student_totals,
    list_debtors,
    payments_sum_between,
)

rome = zoneinfo.ZoneInfo(TZ)

def _is_admin(update: Update) -> bool:
    return bool(update.effective_user and update.effective_user.id == ADMIN_ID)

def _fmt_eur(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}€{cents/100:.2f}"

def _parse_amount_to_cents(s: str) -> int | None:
    s = s.strip().replace("€", "").replace(" ", "")
    s = s.replace(",", ".")
    try:
        val = float(s)
    except ValueError:
        return None
    if val <= 0:
        return None
    return int(round(val * 100))

async def on_admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if not _is_admin(update):
        await q.edit_message_text("Non autorizzato.")
        return

    parts = q.data.split("|")
    # A|CONF|id  / A|REJ|id / A|P|id|euro / A|PO|id / A|PCANCEL|id
    action = parts[1]
    req_id = int(parts[2])

    if action == "CONF":
        # passiamo in stato intermedio e chiediamo prezzo
        ok = set_request_status(req_id, "AWAITING_PRICE")
        if not ok:
            await q.edit_message_text("Richiesta non trovata.")
            return

        await q.edit_message_text(f"✅ Richiesta #{req_id} confermata. Ora imposta il prezzo (obbligatorio):")
        await context.bot.send_message(chat_id=ADMIN_ID, text=f"💶 Prezzo per richiesta #{req_id}:", reply_markup=kb_price(req_id))
        return

    if action == "REJ":
        ok = set_request_status(req_id, "REJECTED")
        if ok:
            await q.edit_message_text(f"❌ Rifiutata richiesta #{req_id}")
            # notifichiamo studente
            ru = get_request_with_user(req_id)
            if ru:
                lr, u = ru
                try:
                    await context.bot.send_message(chat_id=u.telegram_id, text="La tua richiesta di lezione è stata rifiutata.")
                except Exception:
                    pass
        else:
            await q.edit_message_text("Richiesta non trovata.")
        return

    if action == "P":
        euro = int(parts[3])
        cents = euro * 100
        ru = get_request_with_user(req_id)
        if not ru:
            await q.edit_message_text("Richiesta non trovata.")
            return
        lr, u = ru

        set_request_price_and_confirm(req_id, cents)
        await q.edit_message_text(f"✅ Prezzo impostato: €{euro} — richiesta #{req_id} confermata definitivamente.")

        # notifica studente
        when = lr.start_dt.astimezone(rome).strftime("%a %d/%m/%Y %H:%M")
        msg = f"🎾 Lezione confermata ✅\nQuando: {when}\nPrezzo: €{euro}"
        await context.bot.send_message(chat_id=u.telegram_id, text=msg)
        return

    if action == "PO":
        # altro: attiviamo modalità input testo per admin
        ADMIN_PENDING_PRICE[ADMIN_ID] = req_id
        await q.edit_message_text(f"✍️ Scrivi ora l’importo in euro per la richiesta #{req_id} (es. 25 o 27,50).")
        return

    if action == "PCANCEL":
        # annulla conferma se non vuoi inserire prezzo
        set_request_status(req_id, "PENDING")
        ADMIN_PENDING_PRICE.pop(ADMIN_ID, None)
        await q.edit_message_text(f"Operazione annullata. Richiesta #{req_id} tornata in PENDING.")
        return

async def on_admin_price_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        return
    if update.effective_chat and update.effective_chat.type != "private":
        return

    req_id = ADMIN_PENDING_PRICE.get(ADMIN_ID)
    if not req_id:
        return  # non stiamo aspettando prezzo

    text = (update.message.text or "").strip()
    cents = _parse_amount_to_cents(text)
    if cents is None:
        await update.message.reply_text("Importo non valido. Scrivi un numero tipo 25 o 27,50.")
        return

    ru = get_request_with_user(req_id)
    if not ru:
        ADMIN_PENDING_PRICE.pop(ADMIN_ID, None)
        await update.message.reply_text("Richiesta non trovata.")
        return

    lr, u = ru
    set_request_price_and_confirm(req_id, cents)
    ADMIN_PENDING_PRICE.pop(ADMIN_ID, None)

    when = lr.start_dt.astimezone(rome).strftime("%a %d/%m/%Y %H:%M")
    await update.message.reply_text(f"✅ Prezzo impostato: {_fmt_eur(cents)} — richiesta #{req_id} confermata.")
    await context.bot.send_message(chat_id=u.telegram_id, text=f"🎾 Lezione confermata ✅\nQuando: {when}\nPrezzo: {_fmt_eur(cents)}")

# ---- Commands: /paid /paidall /crediti /saldo /incassi ----

def _resolve_student(arg: str) -> int | None:
    # returns user_id (DB), not telegram_id
    # arg can be @username or telegram_id
    if arg.startswith("@"):
        u = get_user_by_username(arg)
        return u.id if u else None
    # numeric -> telegram_id
    try:
        tg_id = int(arg)
    except ValueError:
        return None
    u = get_user_by_telegram_id(tg_id)
    return u.id if u else None

async def paid_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        return

    if len(context.args) < 2:
        await update.message.reply_text("Uso: /paid <@username|telegram_id> <importo> [nota]")
        return

    student_key = context.args[0]
    amount_s = context.args[1]
    note = " ".join(context.args[2:]).strip() or None

    user_id = _resolve_student(student_key)
    if not user_id:
        await update.message.reply_text("Studente non trovato. Usa @username oppure telegram_id.")
        return

    cents = _parse_amount_to_cents(amount_s)
    if cents is None:
        await update.message.reply_text("Importo non valido. Esempio: /paid @mario 25")
        return

    lt, pt, bal_before = student_totals(user_id)
    create_payment(user_id=user_id, amount_cents=cents, note=note)
    lt2, pt2, bal_after = student_totals(user_id)

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

    user_id = _resolve_student(student_key)
    if not user_id:
        await update.message.reply_text("Studente non trovato. Usa @username oppure telegram_id.")
        return

    lt, pt, bal = student_totals(user_id)
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
        label = u.first_name
        if u.username:
            label += f" (@{u.username})"
        lines.append(f"- {label}: {_fmt_eur(bal)}")
    await update.message.reply_text("\n".join(lines))

async def saldo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        return

    if len(context.args) < 1:
        await update.message.reply_text("Uso: /saldo <@username|telegram_id>")
        return

    student_key = context.args[0]
    user_id = _resolve_student(student_key)
    if not user_id:
        await update.message.reply_text("Studente non trovato.")
        return

    lt, pt, bal = student_totals(user_id)
    await update.message.reply_text(
        f"📒 Saldo studente\n"
        f"Totale lezioni (CONFIRMED): {_fmt_eur(lt)}\n"
        f"Totale pagamenti: {_fmt_eur(pt)}\n"
        f"Saldo (ti deve): {_fmt_eur(bal)}"
    )

def _period_range(period: str) -> tuple[datetime, datetime] | None:
    now = datetime.now(tz=rome)
    if period == "oggi":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start.replace(day=start.day)  # placeholder
        end = start + __import__("datetime").timedelta(days=1)
        return start, end
    if period == "settimana":
        # monday start
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start = start - __import__("datetime").timedelta(days=start.weekday())
        end = start + __import__("datetime").timedelta(days=7)
        return start, end
    if period == "mese":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        # next month
        if start.month == 12:
            end = start.replace(year=start.year + 1, month=1)
        else:
            end = start.replace(month=start.month + 1)
        return start, end
    if period == "anno":
        start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        end = start.replace(year=start.year + 1)
        return start, end
    return None

async def incassi_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        return

    if len(context.args) < 1:
        await update.message.reply_text("Uso: /incassi oggi|settimana|mese|anno")
        return

    period = context.args[0].lower()
    rng = _period_range(period)
    if not rng:
        await update.message.reply_text("Periodo non valido. Usa: oggi|settimana|mese|anno")
        return

    dt_from, dt_to = rng
    total = payments_sum_between(dt_from, dt_to)
    await update.message.reply_text(f"💰 Incassi {period}: {_fmt_eur(total)}")

def get_handlers():
    return [
        CallbackQueryHandler(on_admin_action, pattern=r"^A\|"),
        MessageHandler(filters.TEXT & ~filters.COMMAND, on_admin_price_text),
        CommandHandler("paid", paid_cmd),
        CommandHandler("paidall", paidall_cmd),
        CommandHandler("crediti", crediti_cmd),
        CommandHandler("saldo", saldo_cmd),
        CommandHandler("incassi", incassi_cmd),
    ]