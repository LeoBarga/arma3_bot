import logging
import asyncio
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters
)

from config import BOT_TOKEN
from db import init_db, close_db
from handlers.admin import (
    cmd_start,
    registra_da_gruppo,
    cmd_stato
)

# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("bot.log", encoding="utf-8")
    ]
)
logger = logging.getLogger(__name__)


# ============================================================
# LIFECYCLE
# ============================================================

async def on_startup(app):
    await init_db()
    logger.info("Connessione DB inizializzata.")

async def on_shutdown(app):
    await close_db()
    logger.info("Connessione DB chiusa.")


# ============================================================
# MAIN
# ============================================================

def main():
    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .post_init(on_startup)
        .post_shutdown(on_shutdown)
        .build()
    )

    # --- Handler base ---
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("stato", cmd_stato))

    # --- Registrazione automatica da gruppo ---
    app.add_handler(MessageHandler(
        filters.TEXT & filters.ChatType.GROUPS,
        registra_da_gruppo
    ))

    logger.info("Bot avviato.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
