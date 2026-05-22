import logging
from telegram import Update
from telegram.ext import ContextTypes
from db import get_pool
import aiomysql

logger = logging.getLogger(__name__)


# ============================================================
# HELPER — recupera utente dal DB
# ============================================================

async def get_utente(telegram_id: int):
    async with get_pool().acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT * FROM utenti WHERE telegram_id = %s",
                (telegram_id,)
            )
            return await cur.fetchone()

async def crea_o_aggiorna_utente(telegram_id: int, nome: str, username: str = None):
    async with get_pool().acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            # Controlla se esiste già
            await cur.execute(
                "SELECT id FROM utenti WHERE telegram_id = %s",
                (telegram_id,)
            )
            esistente = await cur.fetchone()

            if esistente:
                # Aggiorna nome e username
                await cur.execute(
                    "UPDATE utenti SET nome = %s, username = %s WHERE telegram_id = %s",
                    (nome, username, telegram_id)
                )
                await conn.commit()
                return esistente["id"], False  # False = non è nuovo
            else:
                # Crea nuovo utente
                await cur.execute(
                    "SELECT id FROM gradi WHERE ordine = 0 LIMIT 1"
                )
                grado_recluta = await cur.fetchone()

                await cur.execute(
                    """
                    INSERT INTO utenti (telegram_id, nome, username, stato, grado_id)
                    VALUES (%s, %s, %s, 'recluta', %s)
                    """,
                    (telegram_id, nome, username, grado_recluta["id"] if grado_recluta else None)
                )

                utente_id = cur.lastrowid

                # Assegna moduli obbligatori
                await cur.execute(
                    "SELECT id FROM moduli WHERE obbligatorio = TRUE AND attivo = TRUE"
                )
                moduli = await cur.fetchall()
                for m in moduli:
                    await cur.execute(
                        "INSERT IGNORE INTO reclute_moduli (utente_id, modulo_id, stato) VALUES (%s, %s, 'non_completato')",
                        (utente_id, m["id"])
                    )

                await conn.commit()
                return utente_id, True  # True = è nuovo


# ============================================================
# /start
# ============================================================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    nome        = update.effective_user.full_name
    username    = update.effective_user.username

    utente_id, is_nuovo = await crea_o_aggiorna_utente(telegram_id, nome, username)

    if is_nuovo:
        await update.message.reply_text(
            f"Benvenuto {nome}!\n\n"
            f"Sei stato registrato come recluta.\n"
            f"Segui le istruzioni degli istruttori per completare i moduli e le partite richieste."
        )
    else:
        utente = await get_utente(telegram_id)
        await update.message.reply_text(
            f"Bentornato {nome}!\n"
            f"Stato: {utente['stato']}\n"
        )


# ============================================================
# Registrazione silenziosa da gruppo
# ============================================================

async def registra_da_gruppo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    nome        = update.effective_user.full_name
    username    = update.effective_user.username

    _, is_nuovo = await crea_o_aggiorna_utente(telegram_id, nome, username)
    if is_nuovo:
        logger.info(f"Nuovo utente registrato da gruppo: {nome} ({telegram_id})")


# ============================================================
# /stato — info personali
# ============================================================

async def cmd_stato(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    utente = await get_utente(telegram_id)

    if not utente:
        await update.message.reply_text(
            "Non sei registrato. Scrivi /start per registrarti."
        )
        return

    async with get_pool().acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:

            # Grado
            await cur.execute(
                "SELECT nome FROM gradi WHERE id = %s",
                (utente["grado_id"],)
            )
            grado = await cur.fetchone()

            if utente["stato"] == "recluta":
                # Conta moduli completati
                await cur.execute("""
                    SELECT
                        COUNT(*) as totale,
                        SUM(CASE WHEN stato = 'completato' THEN 1 ELSE 0 END) as completati
                    FROM reclute_moduli
                    WHERE utente_id = %s
                """, (utente["id"],))
                moduli = await cur.fetchone()

                # Conta presenze
                await cur.execute("""
                    SELECT COUNT(*) as n FROM presenze
                    WHERE utente_id = %s AND presente = TRUE
                """, (utente["id"],))
                presenze = (await cur.fetchone())["n"]

                testo = (
                    f"👤 {utente['nome']}\n"
                    f"Stato: Recluta\n\n"
                    f"Moduli completati: {int(moduli['completati'] or 0)}/{moduli['totale']}\n"
                    f"Partite completate: {presenze}/8\n"
                )

                if utente["pronta_promozione"]:
                    testo += "\n✅ Hai completato tutti i requisiti! Contatta un istruttore."

            else:
                tag = ""
                if utente["tag"] == "promuovibile":
                    tag = "\n▲ Sei candidabile per una promozione."
                elif utente["tag"] == "degradabile":
                    tag = "\n▼ Sei candidabile per una retrocessione."

                testo = (
                    f"👤 {utente['nome']}\n"
                    f"Stato: Effettivo\n"
                    f"Grado: {grado['nome'] if grado else '—'}\n"
                    f"Punteggio: {utente['punteggio']}\n"
                    f"{tag}"
                )

    await update.message.reply_text(testo)
