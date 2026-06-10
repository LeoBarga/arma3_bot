import asyncio
import logging
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from db import get_pool, chiudi_sondaggio, get_medie_sondaggio
from handlers.presenze import pulizia_serate_vecchie
import aiomysql

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()

async def controlla_sondaggi(bot):
    """Controlla sondaggi scaduti e li chiude, e sondaggi schedulati e li apre."""
    async with get_pool().acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:

            # Chiudi sondaggi scaduti
            await cur.execute("""
                SELECT * FROM sondaggi
                WHERE attiva = TRUE
                  AND chiusa_il IS NOT NULL
                  AND chiusa_il <= NOW()
            """)
            scaduti = await cur.fetchall()

            for s in scaduti:
                logger.info(f"Chiudo sondaggio scaduto: {s['nome']} (ID {s['id']})")
                await chiudi_sondaggio(s["id"])
                await invia_risultati_scheduler(bot, s["id"], s["nome"])

            # Apri sondaggi schedulati
            await cur.execute("""
                SELECT * FROM sondaggi
                WHERE attiva = FALSE
                  AND schedulata_il IS NOT NULL
                  AND schedulata_il <= NOW()
                  AND aperta_il IS NULL
                  AND archiviata = FALSE
            """)
            da_aprire = await cur.fetchall()

            for s in da_aprire:
                logger.info(f"Apro sondaggio schedulato: {s['nome']} (ID {s['id']})")
                await cur.execute("""
                    UPDATE sondaggi
                    SET attiva = TRUE, aperta_il = NOW()
                    WHERE id = %s
                """, (s["id"],))
                await conn.commit()

                # Notifica i partecipanti
                await notifica_apertura(bot, s)


async def invia_risultati_scheduler(bot, sondaggio_id: int, nome_sondaggio: str):
    medie = await get_medie_sondaggio(sondaggio_id)
    if not medie:
        logger.info(f"Nessun risultato per sondaggio {sondaggio_id}")
        return

    per_sl = {}
    for riga in medie:
        nome = riga["sl_nome"]
        if nome not in per_sl:
            per_sl[nome] = {
                "telegram_id": riga["sl_telegram_id"],
                "votanti":     riga["votanti"],
                "domande":     []
            }
        per_sl[nome]["domande"].append({
            "testo": riga["domanda"],
            "media": riga["media"]
        })

    for sl_nome, dati in per_sl.items():
        testo = (
            f"📊 SL {sl_nome}\n"
            f"Risultati: {nome_sondaggio}\n"
            f"Votanti: {dati['votanti']}\n\n"
        )
        for d in dati["domande"]:
            testo += f"• {d['testo']}\n  → Media: {d['media']}/10\n\n"

        try:
            await bot.send_message(chat_id=dati["telegram_id"], text=testo)
            logger.info(f"Risultati inviati a {sl_nome}")
        except Exception as e:
            logger.warning(f"Impossibile inviare risultati a {sl_nome}: {e}")


async def notifica_apertura(bot, sondaggio: dict):
    async with get_pool().acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("""
                SELECT u.telegram_id, u.nome
                FROM presenze p
                JOIN utenti u ON p.utente_id = u.id
                WHERE p.partita_id = %s
                  AND p.presente = TRUE
                  AND u.stato = 'effettivo'
                  AND u.telegram_id IS NOT NULL
            """, (sondaggio["partita_id"],))
            partecipanti = await cur.fetchall()

    for p in partecipanti:
        try:
            await bot.send_message(
                chat_id=p["telegram_id"],
                text=(
                    f"📋 È aperto il sondaggio: {sondaggio['nome']}\n\n"
                    f"Scrivi /valuta per compilarlo."
                )
            )
        except Exception as e:
            logger.warning(f"Impossibile notificare {p['telegram_id']}: {e}")


def avvia_scheduler(bot):
    scheduler.add_job(
        controlla_sondaggi,
        trigger="interval",
        minutes=1,
        args=[bot],
        id="controlla_sondaggi"
    )
    scheduler.add_job(
        pulizia_serate_vecchie,
        trigger="cron",
        hour=3,
        minute=0,
        id="pulizia_serate"
    )
    scheduler.start()
    logger.info("Scheduler avviato.")

def ferma_scheduler():
    scheduler.shutdown()
    logger.info("Scheduler fermato.")
