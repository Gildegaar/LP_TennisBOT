import logging
from fastapi import FastAPI, Request
from telegram.ext import Application
from telegram import Update

from .config import BOT_TOKEN, BASE_URL, WEBHOOK_PATH
from .models import Base
from .db import engine
from .handlers.start import get_handlers
from .handlers.errors import on_error

from .config import BOT_TOKEN, DATABASE_URL, BASE_URL, WEBHOOK_PATH
from .handlers.locations import get_handlers as get_location_handlers

if not BOT_TOKEN:
    raise RuntimeError("Missing env var BOT_TOKEN")
if not DATABASE_URL:
    raise RuntimeError("Missing env var DATABASE_URL")

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("lp_tennisbot")

# Create tables (MVP). In V2 passiamo ad Alembic.
Base.metadata.create_all(bind=engine)

app = FastAPI()
tg_app = Application.builder().token(BOT_TOKEN).build()

for h in get_handlers():
    tg_app.add_handler(h)
    
for h in get_location_handlers():
tg_app.add_handler(h)

tg_app.add_error_handler(on_error)

@app.on_event("startup")
async def startup():
    await tg_app.initialize()
    await tg_app.start()

    # In locale spesso BASE_URL è vuoto, quindi niente webhook.
    if BASE_URL:
        webhook_url = f"{BASE_URL}{WEBHOOK_PATH}"
        await tg_app.bot.set_webhook(url=webhook_url)
        log.info(f"Webhook set to {webhook_url}")
    else:
        log.info("BASE_URL not set: webhook not configured (local mode)")

@app.on_event("shutdown")
async def shutdown():
    await tg_app.stop()
    await tg_app.shutdown()

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.post(WEBHOOK_PATH)
async def telegram_webhook(req: Request):
    data = await req.json()
    update = Update.de_json(data, tg_app.bot)
    await tg_app.process_update(update)
    return {"ok": True}