import logging
import asyncio
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
    ContextTypes
)

from config import BOT_TOKEN
from db import init_db, close_db
from handlers.admin import cmd_start, registra_da_gruppo, cmd_stato, cmd_indirizzi
from handlers.sondaggio import (
    cmd_apri_sondaggio, ricevi_modalita, ricevi_tipo, ricevi_nome, ricevi_partita,
    ricevi_quando_apre, ricevi_data_apertura, ricevi_ora_apertura,
    ricevi_quando_chiude, ricevi_ore_chiusura, ricevi_data_chiusura,
    ricevi_ora_chiusura, cmd_sondaggi, cmd_chiudi_sondaggio,
    callback_chiudi, cmd_valuta, inizia_valutazione, scegli_sondaggio, scegli_sl,
    rispondi_domanda, annulla,
    NOME, PARTITA, QUANDO_APRE, DATA_APERTURA, ORA_APERTURA,
    QUANDO_CHIUDE, DATA_CHIUSURA, ORA_CHIUSURA, ORE_CHIUSURA,
    SCEGLI_SL, RISPONDI
)
from handlers.presenze import (
    cmd_crea, ricevi_tipo_partita, ricevi_nome_partita,
    ricevi_data_partita, conferma_crea_partita, gestisci_voto,
    TIPO, NOME_PARTITA, DATA_PARTITA
)
from scheduler import avvia_scheduler, ferma_scheduler


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
    avvia_scheduler(app.bot)
    logger.info("Connessione DB inizializzata.")

async def on_shutdown(app):
    ferma_scheduler()
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

    # --- Compilazione sondaggio (PRIMA di tutto) ---
    conv_valuta = ConversationHandler(
        entry_points=[CommandHandler("valuta", cmd_valuta, filters=filters.ChatType.PRIVATE), CallbackQueryHandler(inizia_valutazione, pattern="^inizia_")],
        states={
            SCEGLI_SL: [
                CallbackQueryHandler(scegli_sondaggio, pattern="^sondaggio_"),
                CallbackQueryHandler(scegli_sl, pattern="^sl_"),
            ],
            RISPONDI: [CallbackQueryHandler(rispondi_domanda, pattern="^[0-9]+$")],
        },
        fallbacks=[CommandHandler("annulla", annulla)],
        per_user=True,
        per_chat=False
    )
    app.add_handler(conv_valuta)

    # --- Apertura sondaggio ---
    conv_apri = ConversationHandler(
        entry_points=[CommandHandler("apri_sondaggio", cmd_apri_sondaggio, filters=filters.ChatType.GROUPS)],
        states={
            NOME:          [CallbackQueryHandler(ricevi_modalita, pattern="^modalita_"), MessageHandler(filters.TEXT & ~filters.COMMAND, ricevi_nome)],
            PARTITA:       [CallbackQueryHandler(ricevi_tipo, pattern="^tipo_"), CallbackQueryHandler(ricevi_partita, pattern="^partita_")],
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
        per_chat=False
    )
    app.add_handler(conv_apri)

    # --- Crea partita ---
    conv_crea = ConversationHandler(
        entry_points=[CommandHandler("crea", cmd_crea, filters=filters.ChatType.GROUPS)],
        states={
            TIPO:         [CallbackQueryHandler(ricevi_tipo_partita, pattern="^tipo_")],
            NOME_PARTITA: [MessageHandler(filters.TEXT & ~filters.COMMAND, ricevi_nome_partita)],
            DATA_PARTITA: [
                CallbackQueryHandler(ricevi_data_partita, pattern="^data_"),
                CallbackQueryHandler(conferma_crea_partita, pattern="^(conferma_crea|annulla_crea)$"),
            ],
        },
        fallbacks=[CommandHandler("annulla", annulla)],
        per_user=True,
        per_chat=False
    )
    app.add_handler(conv_crea)

    # --- Voti presenze ---
    app.add_handler(CallbackQueryHandler(gestisci_voto, pattern="^voto_"))

    # --- Handler admin ---
    app.add_handler(CommandHandler("start", cmd_start, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("stato", cmd_stato, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("sondaggi", cmd_sondaggi, filters=filters.ChatType.GROUPS))
    app.add_handler(CommandHandler("chiudi_sondaggio", cmd_chiudi_sondaggio, filters=filters.ChatType.GROUPS))
    app.add_handler(CallbackQueryHandler(callback_chiudi, pattern="^chiudi_"))

    # --- Avviso comandi privati nel gruppo ---
    async def avviso_privato(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "🔒 Funzione privata — per usare questo comando scrivilo al bot in una chat privata."
        )
    app.add_handler(CommandHandler(
        ["start", "stato", "valuta"],
        avviso_privato,
        filters=filters.ChatType.GROUPS
    ))

    # --- Handler comando indirizzi ---
    app.add_handler(CommandHandler("indirizzi", cmd_indirizzi))

    # --- Registrazione automatica da gruppo ---
    app.add_handler(MessageHandler(
        filters.TEXT & filters.ChatType.GROUPS,
        registra_da_gruppo
    ))

    logger.info("Bot avviato.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()


