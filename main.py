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
from handlers.admin import cmd_start, registra_da_gruppo, cmd_stato
from handlers.sondaggio import (
    cmd_apri_sondaggio, ricevi_nome, ricevi_partita,
    ricevi_quando_apre, ricevi_data_apertura, ricevi_ora_apertura,
    ricevi_quando_chiude, ricevi_ore_chiusura, ricevi_data_chiusura,
    ricevi_ora_chiusura, cmd_sondaggi, cmd_chiudi_sondaggio,
    callback_chiudi, cmd_valuta, scegli_sondaggio, scegli_sl,
    rispondi_domanda, annulla,
    NOME, PARTITA, QUANDO_APRE, DATA_APERTURA, ORA_APERTURA,
    QUANDO_CHIUDE, DATA_CHIUSURA, ORA_CHIUSURA, ORE_CHIUSURA,
    SCEGLI_SL, RISPONDI
)

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("bot.log", encoding="utf-8")
    ]
)
logger = logging.getLogger(__name__)

async def on_startup(app):
    await init_db()
    logger.info("Connessione DB inizializzata.")

async def on_shutdown(app):
    await close_db()
    logger.info("Connessione DB chiusa.")

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
    app.add_handler(CommandHandler("sondaggi", cmd_sondaggi))

    # --- Apertura sondaggio (conversazione admin) ---
    conv_apri = ConversationHandler(
        entry_points=[CommandHandler("apri_sondaggio", cmd_apri_sondaggio)],
        states={
            NOME:          [MessageHandler(filters.TEXT & ~filters.COMMAND, ricevi_nome)],
            PARTITA:       [CallbackQueryHandler(ricevi_partita, pattern="^partita_")],
            QUANDO_APRE:   [CallbackQueryHandler(ricevi_quando_apre, pattern="^apre_")],
            DATA_APERTURA: [MessageHandler(filters.TEXT & ~filters.COMMAND, ricevi_data_apertura)],
            ORA_APERTURA:  [CallbackQueryHandler(ricevi_ora_apertura, pattern="^ora_apertura_")],
            QUANDO_CHIUDE: [CallbackQueryHandler(ricevi_quando_chiude, pattern="^chiude_")],
            ORE_CHIUSURA:  [MessageHandler(filters.TEXT & ~filters.COMMAND, ricevi_ore_chiusura)],
            DATA_CHIUSURA: [MessageHandler(filters.TEXT & ~filters.COMMAND, ricevi_data_chiusura)],
            ORA_CHIUSURA:  [CallbackQueryHandler(ricevi_ora_chiusura, pattern="^ora_chiusura_")],
        },
        fallbacks=[CommandHandler("annulla", annulla)],
        per_user=True,
        per_chat=True
    )
    app.add_handler(conv_apri)

    # --- Chiusura sondaggio ---
    app.add_handler(CommandHandler("chiudi_sondaggio", cmd_chiudi_sondaggio))
    app.add_handler(CallbackQueryHandler(callback_chiudi, pattern="^chiudi_"))

    # --- Compilazione sondaggio ---
    conv_valuta = ConversationHandler(
        entry_points=[CommandHandler("valuta", cmd_valuta)],
        states={
            SCEGLI_SL: [
                CallbackQueryHandler(scegli_sondaggio, pattern="^sondaggio_"),
                CallbackQueryHandler(scegli_sl, pattern="^sl_"),
            ],
            RISPONDI: [CallbackQueryHandler(rispondi_domanda, pattern="^[0-9]+$")],
        },
        fallbacks=[CommandHandler("annulla", annulla)],
        per_user=True,
        per_chat=True
    )
    app.add_handler(conv_valuta)

    # --- Registrazione automatica da gruppo ---
    app.add_handler(MessageHandler(
        filters.TEXT & filters.ChatType.GROUPS,
        registra_da_gruppo
    ))

    logger.info("Bot avviato.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
