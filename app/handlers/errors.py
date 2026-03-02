import logging
from telegram import Update
from telegram.ext import ContextTypes

log = logging.getLogger(__name__)

async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    log.exception("Unhandled error", exc_info=context.error)