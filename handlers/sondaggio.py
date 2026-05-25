import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from db import (
    get_pool, get_sondaggi_attivi, get_sondaggio_by_id,
    crea_sondaggio, chiudi_sondaggio, get_partecipanti_sondaggio,
    get_sl_partita, get_domande_sondaggio, ha_gia_risposto,
    crea_risposta, salva_dettaglio, completa_risposta,
    elimina_risposta, get_medie_sondaggio, get_ultime_partite,
    get_conteggio_risposte
)
import aiomysql
from handlers.admin import nome_display

logger = logging.getLogger(__name__)

# Stati conversazione apertura sondaggio
(NOME, PARTITA, QUANDO_APRE, DATA_APERTURA, ORA_APERTURA,
 QUANDO_CHIUDE, DATA_CHIUSURA, ORA_CHIUSURA, ORE_CHIUSURA) = range(9)

# Stati conversazione compilazione
SCEGLI_SL = 10
RISPONDI  = 11

ORE_DISPONIBILI = ["08:00","10:00","12:00","14:00","16:00","18:00","20:00","22:00"]


# ============================================================
# HELPER
# ============================================================

def is_admin(utente: dict) -> bool:
    return utente and utente.get("is_admin", False)

async def get_utente_completo(telegram_id: int):
    async with get_pool().acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT * FROM utenti WHERE telegram_id = %s",
                (telegram_id,)
            )
            utente = await cur.fetchone()
            if not utente:
                return None
            await cur.execute(
                "SELECT permesso FROM utenti_permessi WHERE utente_id = %s",
                (utente["id"],)
            )
            permessi = await cur.fetchall()
            utente["is_admin"] = any(p["permesso"] == "admin" for p in permessi)
            return utente


# ============================================================
# /apri_sondaggio — solo admin
# ============================================================

async def cmd_apri_sondaggio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    utente = await get_utente_completo(update.effective_user.id)
    if not utente or not utente["is_admin"]:
        await update.message.reply_text("⛔ Non sei autorizzato.")
        return ConversationHandler.END

    await update.message.reply_text("Che nome dai al sondaggio?")
    return NOME

async def ricevi_nome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["nome_sondaggio"] = update.message.text.strip()

    partite = await get_ultime_partite(10)
    if not partite:
        await update.message.reply_text(
            "⚠️ Nessuna partita disponibile. Creane una prima dalla WUI."
        )
        return ConversationHandler.END

    tastiera = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"{p['nome']} — {p['data_ora'].strftime('%d/%m/%Y')}",
            callback_data=f"partita_{p['id']}"
        )]
        for p in partite
    ])
    await update.message.reply_text("A quale partita si riferisce?", reply_markup=tastiera)
    return PARTITA

async def ricevi_partita(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    partita_id = int(query.data.split("_")[1])
    context.user_data["partita_id"] = partita_id

    tastiera = InlineKeyboardMarkup([[
        InlineKeyboardButton("Adesso", callback_data="apre_adesso"),
        InlineKeyboardButton("Schedulato", callback_data="apre_schedulato")
    ]])
    await query.edit_message_text("Quando si apre il sondaggio?", reply_markup=tastiera)
    return QUANDO_APRE

async def ricevi_quando_apre(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "apre_adesso":
        context.user_data["schedulata_il"] = None
        await query.edit_message_text("Quando si chiude?\n\nScrivi la data (GG/MM/YYYY), oppure scegli:")
        tastiera = InlineKeyboardMarkup([[
            InlineKeyboardButton("Manualmente", callback_data="chiude_manuale"),
            InlineKeyboardButton("Tra N ore", callback_data="chiude_ore"),
            InlineKeyboardButton("Data e ora", callback_data="chiude_data")
        ]])
        await query.edit_message_text("Quando si chiude?", reply_markup=tastiera)
        return QUANDO_CHIUDE
    else:
        await query.edit_message_text("Che giorno si apre? (formato GG/MM/YYYY)")
        return DATA_APERTURA

async def ricevi_data_apertura(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        data = datetime.strptime(update.message.text.strip(), "%d/%m/%Y")
        context.user_data["data_apertura"] = data
    except ValueError:
        await update.message.reply_text("Formato non valido. Usa GG/MM/YYYY")
        return DATA_APERTURA

    tastiera = InlineKeyboardMarkup([
        [InlineKeyboardButton(ora, callback_data=f"ora_apertura_{ora}") for ora in ORE_DISPONIBILI[:4]],
        [InlineKeyboardButton(ora, callback_data=f"ora_apertura_{ora}") for ora in ORE_DISPONIBILI[4:]]
    ])
    await update.message.reply_text("A che ora si apre?", reply_markup=tastiera)
    return ORA_APERTURA

async def ricevi_ora_apertura(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    ora_str = query.data.replace("ora_apertura_", "")
    data    = context.user_data["data_apertura"]
    ora     = datetime.strptime(ora_str, "%H:%M")
    schedulata_il = data.replace(hour=ora.hour, minute=ora.minute)
    context.user_data["schedulata_il"] = schedulata_il

    tastiera = InlineKeyboardMarkup([[
        InlineKeyboardButton("Manualmente", callback_data="chiude_manuale"),
        InlineKeyboardButton("Tra N ore",   callback_data="chiude_ore"),
        InlineKeyboardButton("Data e ora",  callback_data="chiude_data")
    ]])
    await query.edit_message_text("Quando si chiude?", reply_markup=tastiera)
    return QUANDO_CHIUDE

async def ricevi_quando_chiude(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "chiude_manuale":
        context.user_data["chiusura_tipo"] = "manuale"
        await query.edit_message_text("Scrivi quante ore dopo l'apertura deve chiudersi, oppure 0 per chiusura manuale.\n\nConfermi chiusura manuale?")
        return await conferma_crea_sondaggio(update, context)

    elif query.data == "chiude_ore":
        context.user_data["chiusura_tipo"] = "ore"
        await query.edit_message_text("Quante ore dopo l'apertura deve chiudersi?")
        return ORE_CHIUSURA

    else:
        context.user_data["chiusura_tipo"] = "data"
        await query.edit_message_text("Che giorno si chiude? (formato GG/MM/YYYY)")
        return DATA_CHIUSURA

async def ricevi_ore_chiusura(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        ore = int(update.message.text.strip())
        context.user_data["ore_chiusura"] = ore
    except ValueError:
        await update.message.reply_text("Inserisci un numero intero.")
        return ORE_CHIUSURA
    return await conferma_crea_sondaggio(update, context)

async def ricevi_data_chiusura(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        data = datetime.strptime(update.message.text.strip(), "%d/%m/%Y")
        context.user_data["data_chiusura"] = data
    except ValueError:
        await update.message.reply_text("Formato non valido. Usa GG/MM/YYYY")
        return DATA_CHIUSURA

    tastiera = InlineKeyboardMarkup([
        [InlineKeyboardButton(ora, callback_data=f"ora_chiusura_{ora}") for ora in ORE_DISPONIBILI[:4]],
        [InlineKeyboardButton(ora, callback_data=f"ora_chiusura_{ora}") for ora in ORE_DISPONIBILI[4:]]
    ])
    await update.message.reply_text("A che ora si chiude?", reply_markup=tastiera)
    return ORA_CHIUSURA

async def ricevi_ora_chiusura(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    ora_str = query.data.replace("ora_chiusura_", "")
    data    = context.user_data["data_chiusura"]
    ora     = datetime.strptime(ora_str, "%H:%M")
    context.user_data["chiusa_il"] = data.replace(hour=ora.hour, minute=ora.minute)
    return await conferma_crea_sondaggio(update, context)

async def conferma_crea_sondaggio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    d = context.user_data

    # Calcola chiusa_il
    schedulata_il = d.get("schedulata_il")
    chiusura_tipo = d.get("chiusura_tipo")

    if chiusura_tipo == "manuale":
        chiusa_il = None
    elif chiusura_tipo == "ore":
        base = schedulata_il or datetime.now()
        chiusa_il = base + timedelta(hours=d["ore_chiusura"])
    else:
        chiusa_il = d.get("chiusa_il")

    # Recupera utente
    telegram_id = update.effective_user.id if update.effective_user else update.callback_query.from_user.id
    async with get_pool().acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT id FROM utenti WHERE telegram_id = %s", (telegram_id,))
            utente = await cur.fetchone()
            await cur.execute("SELECT id FROM tipi_sondaggio WHERE nome = 'Valutazione SL' LIMIT 1")
            tipo = await cur.fetchone()

    sondaggio_id = await crea_sondaggio(
        tipo_id=tipo["id"],
        nome=d["nome_sondaggio"],
        partita_id=d["partita_id"],
        schedulata_il=schedulata_il,
        chiusa_il=chiusa_il,
        creato_da=utente["id"]
    )

    # Se apre adesso, invia subito il sondaggio
    if schedulata_il is None:
    	sondaggio = await get_sondaggio_by_id(sondaggio_id)
    	await invia_sondaggio(
            update.effective_message or update.callback_query.message,
            context,
            sondaggio_id,
            sondaggio
        )

    apertura_str  = "Adesso" if not schedulata_il else schedulata_il.strftime("%d/%m/%Y alle %H:%M")
    chiusura_str  = "Manuale" if not chiusa_il else chiusa_il.strftime("%d/%m/%Y alle %H:%M")

    msg = (
        f"✅ Sondaggio '{d['nome_sondaggio']}' creato.\n"
        f"Apertura: {apertura_str}\n"
        f"Chiusura: {chiusura_str}"
    )

    if hasattr(update, "callback_query") and update.callback_query:
        await update.callback_query.edit_message_text(msg)
    else:
        await update.message.reply_text(msg)

    context.user_data.clear()
    return ConversationHandler.END


# ============================================================
# INVIO SONDAGGIO AI PARTECIPANTI
# ============================================================

async def invia_sondaggio(message, context, sondaggio_id: int, sondaggio: dict = None):
    if sondaggio is None:
    	sondaggio = await get_sondaggio_by_id(sondaggio_id)
    sl_list = await get_sl_partita(sondaggio["partita_id"])

    if not sl_list:
        await message.reply_text("⚠️ Nessun SL presente alla partita.")
        return

    inviati = 0
    for sl in sl_list:
        partecipanti = await get_partecipanti_sondaggio(sondaggio["partita_id"], sl["id"])
        for p in partecipanti:
            try:
                await context.bot.send_message(
                    chat_id=p["telegram_id"],
                    text=(
                        f"📋 È aperto il sondaggio: {sondaggio['nome']}\n\n"
                        f"Scrivi /valuta per compilarlo."
                    )
                )
                inviati += 1
            except Exception as e:
                logger.warning(f"Impossibile inviare a {p['telegram_id']}: {e}")

    await message.reply_text(f"Notifiche inviate a {inviati} giocatori.")


# ============================================================
# /sondaggi — lista sondaggi attivi
# ============================================================

async def cmd_sondaggi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    utente = await get_utente_completo(update.effective_user.id)
    if not utente or not utente["is_admin"]:
        await update.message.reply_text("⛔ Non sei autorizzato.")
        return

    attivi = await get_sondaggi_attivi()
    if not attivi:
        await update.message.reply_text("📭 Nessun sondaggio attivo.")
        return

    testo = "📊 Sondaggi attivi:\n\n"
    for s in attivi:
        n = await get_conteggio_risposte(s["id"])
        apertura = s["aperta_il"].strftime("%d/%m/%Y %H:%M") if s["aperta_il"] else "schedulato"
        chiusura = s["chiusa_il"].strftime("%d/%m/%Y %H:%M") if s["chiusa_il"] else "manuale"
        testo += (
            f"• {s['nome']} (ID: {s['id']})\n"
            f"  Partita: {s['partita_nome']}\n"
            f"  Aperto: {apertura}\n"
            f"  Chiusura: {chiusura}\n"
            f"  Risposte: {n}\n\n"
        )

    await update.message.reply_text(testo)


# ============================================================
# /chiudi_sondaggio
# ============================================================

async def cmd_chiudi_sondaggio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    utente = await get_utente_completo(update.effective_user.id)
    if not utente or not utente["is_admin"]:
        await update.message.reply_text("⛔ Non sei autorizzato.")
        return

    attivi = await get_sondaggi_attivi()
    if not attivi:
        await update.message.reply_text("⚠️ Nessun sondaggio attivo.")
        return

    tastiera = InlineKeyboardMarkup([
        [InlineKeyboardButton(s["nome"], callback_data=f"chiudi_{s['id']}")]
        for s in attivi
    ] + [[InlineKeyboardButton("❌ Annulla", callback_data="chiudi_annulla")]])

    await update.message.reply_text("Quale sondaggio vuoi chiudere?", reply_markup=tastiera)

async def callback_chiudi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "chiudi_annulla":
        await query.edit_message_text("Annullato.")
        return

    sondaggio_id = int(query.data.split("_")[1])
    sondaggio    = await get_sondaggio_by_id(sondaggio_id)

    if not sondaggio:
        await query.edit_message_text("⚠️ Sondaggio non trovato o già chiuso.")
        return

    await chiudi_sondaggio(sondaggio_id)
    await invia_risultati(context, sondaggio_id, sondaggio["nome"])
    await query.edit_message_text(
        f"🔒 Sondaggio '{sondaggio['nome']}' chiuso. Risultati inviati agli SL."
    )


# ============================================================
# INVIO RISULTATI AGLI SL
# ============================================================

async def invia_risultati(context, sondaggio_id: int, nome_sondaggio: str):
    medie = await get_medie_sondaggio(sondaggio_id)
    if not medie:
        logger.info("Nessun risultato da inviare.")
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
            await context.bot.send_message(chat_id=dati["telegram_id"], text=testo)
        except Exception as e:
            logger.warning(f"Impossibile inviare risultati a {sl_nome}: {e}")


# ============================================================
# /valuta — compilazione sondaggio
# ============================================================

async def cmd_valuta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    utente = await get_utente_completo(update.effective_user.id)

    if not utente:
        await update.message.reply_text("Non sei registrato. Scrivi /start.")
        return ConversationHandler.END

    if utente["stato"] != "effettivo":
        await update.message.reply_text("Solo gli effettivi possono compilare i sondaggi.")
        return ConversationHandler.END

    attivi = await get_sondaggi_attivi()
    if not attivi:
        await update.message.reply_text("📭 Nessun sondaggio attivo al momento.")
        return ConversationHandler.END

    context.user_data["utente"] = utente

    if len(attivi) == 1:
        context.user_data["sondaggio"] = attivi[0]
        return await mostra_sl(update, context)

    tastiera = InlineKeyboardMarkup([
        [InlineKeyboardButton(s["nome"], callback_data=f"sondaggio_{s['id']}")]
        for s in attivi
    ])
    await update.message.reply_text("Quale sondaggio vuoi compilare?", reply_markup=tastiera)
    return SCEGLI_SL

async def scegli_sondaggio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    sondaggio_id = int(query.data.split("_")[1])
    sondaggio    = await get_sondaggio_by_id(sondaggio_id)
    context.user_data["sondaggio"] = sondaggio
    return await mostra_sl(update, context)

async def mostra_sl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sondaggio = context.user_data["sondaggio"]
    utente    = context.user_data["utente"]

    sl_list = await get_sl_partita(sondaggio["partita_id"])

    # Filtra SL già votati e se stesso
    sl_disponibili = []
    for sl in sl_list:
        if sl["id"] == utente["id"]:
            continue
        if await ha_gia_risposto(sondaggio["id"], utente["id"], sl["id"]):
            continue
        sl_disponibili.append(sl)

    if not sl_disponibili:
        msg = "Hai già valutato tutti gli SL disponibili per questo sondaggio."
        if update.callback_query:
            await update.callback_query.edit_message_text(msg)
        else:
            await update.message.reply_text(msg)
        return ConversationHandler.END

    tastiera = InlineKeyboardMarkup([
        [InlineKeyboardButton(sl["username"] or sl["nome"], callback_data=f"sl_{sl['id']}")]
        for sl in sl_disponibili
    ])
    msg = f"📋 {sondaggio['nome']}\n\nQuale SL vuoi valutare?"
    if update.callback_query:
        await update.callback_query.edit_message_text(msg, reply_markup=tastiera)
    else:
        await update.message.reply_text(msg, reply_markup=tastiera)
    return SCEGLI_SL

async def scegli_sl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    logger.info(f"scegli_sl chiamata con data: {query.data}")

    sl_id     = int(query.data.split("_")[1])
    sondaggio = context.user_data["sondaggio"]
    utente    = context.user_data["utente"]

    risposta_id = await crea_risposta(sondaggio["id"], utente["id"], sl_id)
    domande     = await get_domande_sondaggio(sondaggio["tipo_sondaggio_id"])

    context.user_data["sl_id"]       = sl_id
    context.user_data["risposta_id"] = risposta_id
    context.user_data["domande"]     = domande
    context.user_data["domanda_idx"] = 0

    await query.edit_message_text(
        f"Risponderai a {len(domande)} domande con un voto da 1 a 10.\n"
        f"Scrivi /annulla per interrompere."
    )
    await manda_domanda(query.message, context)
    return RISPONDI

async def rispondi_domanda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    valore  = int(query.data)
    idx     = context.user_data["domanda_idx"]
    domande = context.user_data["domande"]

    await salva_dettaglio(
        risposta_id=context.user_data["risposta_id"],
        domanda_id=domande[idx]["id"],
        valore=valore
    )

    idx += 1
    context.user_data["domanda_idx"] = idx

    if idx < len(domande):
        await manda_domanda(query.message, context)
        return RISPONDI
    else:
        await completa_risposta(context.user_data["risposta_id"])
        await query.message.reply_text(
            "✅ Valutazione completata. Grazie!\n\n"
            "Puoi valutare un altro SL con /valuta."
        )
        context.user_data.clear()
        return ConversationHandler.END

async def annulla(update: Update, context: ContextTypes.DEFAULT_TYPE):
    risposta_id = context.user_data.get("risposta_id")
    if risposta_id:
        await elimina_risposta(risposta_id)
    context.user_data.clear()
    await update.message.reply_text("❌ Operazione annullata.")
    return ConversationHandler.END

async def manda_domanda(message, context):
    idx     = context.user_data["domanda_idx"]
    domande = context.user_data["domande"]
    domanda = domande[idx]
    totale  = len(domande)

    tastiera = InlineKeyboardMarkup([
        [InlineKeyboardButton(str(i), callback_data=str(i)) for i in range(1, 6)],
        [InlineKeyboardButton(str(i), callback_data=str(i)) for i in range(6, 11)],
    ])
    await message.reply_text(
        f"Domanda {idx + 1}/{totale}\n\n{domanda['testo']}",
        reply_markup=tastiera
    )
