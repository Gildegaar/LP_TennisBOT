from datetime import date, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def kb_main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 Richiedi lezione", callback_data="M|REQ")],
        [InlineKeyboardButton("🗓 Le mie richieste", callback_data="M|MY")],
    ])

def kb_dates(days: int = 14):
    rows = []
    today = date.today()
    for i in range(days):
        d = today + timedelta(days=i)
        label = d.strftime("%a %d/%m")
        rows.append([InlineKeyboardButton(label, callback_data=f"W|DATE|{d.isoformat()}")])
    rows.append([InlineKeyboardButton("↩️ Menu", callback_data="M|HOME")])
    return InlineKeyboardMarkup(rows)

def kb_times():
    # MVP: slot fissi, poi li rendiamo configurabili
    times = ["09:00","10:00","11:00","12:00","15:00","16:00","17:00","18:00","19:00"]
    rows = [[InlineKeyboardButton(t, callback_data=f"W|TIME|{t}")] for t in times]
    rows.append([InlineKeyboardButton("↩️ Indietro", callback_data="W|BACK|DATE")])
    return InlineKeyboardMarkup(rows)

def kb_durations():
    rows = [
        [InlineKeyboardButton("60 min", callback_data="W|DUR|60")],
        [InlineKeyboardButton("90 min", callback_data="W|DUR|90")],
    ]
    rows.append([InlineKeyboardButton("↩️ Indietro", callback_data="W|BACK|TIME")])
    return InlineKeyboardMarkup(rows)

def kb_locations(locs):
    rows = [[InlineKeyboardButton(l.name, callback_data=f"W|LOC|{l.id}")] for l in locs]
    rows.append([InlineKeyboardButton("↩️ Indietro", callback_data="W|BACK|DUR")])
    return InlineKeyboardMarkup(rows)

def kb_review():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Invia richiesta", callback_data="W|SEND|1")],
        [InlineKeyboardButton("✏️ Aggiungi nota", callback_data="W|NOTE|1")],
        [InlineKeyboardButton("↩️ Annulla", callback_data="W|CANCEL|1")],
    ])

def kb_admin_request(req_id: int):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Conferma", callback_data=f"A|CONF|{req_id}"),
            InlineKeyboardButton("❌ Rifiuta", callback_data=f"A|REJ|{req_id}")
        ]
    ])
    

def kb_price(req_id: int):
    # preset in euro
    presets = [20, 25, 30, 35, 40]
    rows = []
    for p in presets:
        rows.append([InlineKeyboardButton(f"€{p}", callback_data=f"A|P|{req_id}|{p}")])
    rows.append([InlineKeyboardButton("✍️ Altro…", callback_data=f"A|PO|{req_id}")])
    rows.append([InlineKeyboardButton("↩️ Annulla", callback_data=f"A|PCANCEL|{req_id}")])
    return InlineKeyboardMarkup(rows)
    

def kb_admin_manage(req_id: int):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✏️ Modifica", callback_data=f"A|EDIT|{req_id}"),
            InlineKeyboardButton("🗑 Annulla", callback_data=f"A|CANCEL|{req_id}")
        ]
    ])

def kb_edit_dates(req_id: int, days: int = 14):
    rows = []
    today = date.today()
    for i in range(days):
        d = today + timedelta(days=i)
        label = d.strftime("%a %d/%m")
        rows.append([InlineKeyboardButton(label, callback_data=f"E|DATE|{req_id}|{d.isoformat()}")])
    rows.append([InlineKeyboardButton("↩️ Annulla", callback_data=f"E|ABORT|{req_id}")])
    return InlineKeyboardMarkup(rows)

def kb_edit_times(req_id: int):
    times = ["09:00","10:00","11:00","12:00","15:00","16:00","17:00","18:00","19:00"]
    rows = [[InlineKeyboardButton(t, callback_data=f"E|TIME|{req_id}|{t}")] for t in times]
    rows.append([InlineKeyboardButton("↩️ Indietro", callback_data=f"E|BACK|{req_id}|DATE")])
    rows.append([InlineKeyboardButton("↩️ Annulla", callback_data=f"E|ABORT|{req_id}")])
    return InlineKeyboardMarkup(rows)

def kb_edit_durations(req_id: int):
    rows = [
        [InlineKeyboardButton("60 min", callback_data=f"E|DUR|{req_id}|60")],
        [InlineKeyboardButton("90 min", callback_data=f"E|DUR|{req_id}|90")],
    ]
    rows.append([InlineKeyboardButton("↩️ Indietro", callback_data=f"E|BACK|{req_id}|TIME")])
    rows.append([InlineKeyboardButton("↩️ Annulla", callback_data=f"E|ABORT|{req_id}")])
    return InlineKeyboardMarkup(rows)

def kb_edit_locations(req_id: int, locs):
    rows = [[InlineKeyboardButton(l.name, callback_data=f"E|LOC|{req_id}|{l.id}")] for l in locs]
    rows.append([InlineKeyboardButton("↩️ Indietro", callback_data=f"E|BACK|{req_id}|DUR")])
    rows.append([InlineKeyboardButton("↩️ Annulla", callback_data=f"E|ABORT|{req_id}")])
    return InlineKeyboardMarkup(rows)

def kb_send_proposal(req_id: int):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📨 Invia proposta", callback_data=f"E|SEND|{req_id}|1")],
        [InlineKeyboardButton("↩️ Annulla", callback_data=f"E|ABORT|{req_id}")],
    ])

def kb_student_proposal(req_id: int):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Accetto", callback_data=f"S|ACC|{req_id}"),
            InlineKeyboardButton("❌ Rifiuto", callback_data=f"S|DEC|{req_id}")
        ]
    ])