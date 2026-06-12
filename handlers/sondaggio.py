import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from db import (
    get_pool, get_sondaggi_attivi, get_sondaggio_by_id,
    crea_sondaggio, chiudi_sondaggio, get_partecipanti_sondaggio,
    get_soggetti_partita, get_votanti_pl, get_domande_sondaggio,
    ha_gia_risposto, crea_risposta, salva_dettaglio, completa_risposta,
    elimina_risposta, get_medie_sondaggio, get_ultime_partite,
    get_conteggio_risposte
)
from handlers.admin import nome_display
import aiomysql

logger = logging.getLogger(__name__)

# Stati conversazione
MODALITA = -1
(NOME, PARTITA, QUANDO_APRE, DATA_APERTURA, ORA_APERTURA, QUANDO_CHIUDE, DATA_CHIUSURA, ORA_CHIUSURA, ORE_CHIUSURA) = range(9)
SCEGLI_SL = 10
RISPONDI  = 11

ORE_DISPONIBILI = ["08:00","10:00","12:00","14:00","16:00","18:00","20:00","22:00"]


# ============================================================
# HELPER
# ============================================================

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

async def get_tipo_sondaggio(tipo_id: int):
    async with get_pool().acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT * FROM tipi_sondaggio WHERE id = %s",
                (tipo_id,)
            )
            return await cur.fetchone()

async def get_tipi_sondaggio_attivi():
    async with get_pool().acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT * FROM tipi_sondaggio WHERE attivo = TRUE ORDER BY nome"
            )
            return await cur.fetchall()

def label_target(target: str) -> str:
    if target == "sl":
        return "SL"
    if target == "pl":
        return "PL"
    return "comandanti"


# ============================================================
# /apri_sondaggio — solo admin
# ============================================================

async def cmd_apri_sondaggio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    utente = await get_utente_completo(update.effective_user.id)
    if not utente or not utente["is_admin"]:
        await update.message.reply_text("⛔ Non sei autorizzato.")
        return ConversationHandler.END

    tastiera = InlineKeyboardMarkup([[
        InlineKeyboardButton("⚡ Standard (Sondaggio SL, chiude in 1h, ultima partita)", callback_data="modalita_standard"),
        InlineKeyboardButton("⚙️ Personalizzato", callback_data="modalita_custom")
    ]])
    await update.message.reply_text("Come vuoi aprire il sondaggio?", reply_markup=tastiera)
    return NOME

async def ricevi_modalita(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "modalita_standard":
        # Prende ultima partita
        partite = await get_ultime_partite(1)
        if not partite:
            await query.edit_message_text("⚠️ Nessuna partita disponibile. Creane una dalla WUI.")
            return ConversationHandler.END

        partita = partite[0]

        # Prende tipo Valutazione SL
        async with get_pool().acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT * FROM tipi_sondaggio WHERE target = 'sl' AND attivo = TRUE LIMIT 1"
                )
                tipo = await cur.fetchone()
                await cur.execute("SELECT id FROM utenti WHERE telegram_id = %s", (query.from_user.id,))
                utente = await cur.fetchone()

        if not tipo:
            await query.edit_message_text("⚠️ Tipo sondaggio SL non trovato.")
            return ConversationHandler.END

        nome_auto    = f"Valutazione SL — {partita['data_ora'].strftime('%d/%m/%Y')}"
        chiusa_il    = datetime.now() + timedelta(hours=1)

        sondaggio_id = await crea_sondaggio(
            tipo_id=tipo["id"],
            nome=nome_auto,
            partita_id=partita["id"],
            schedulata_il=None,
            chiusa_il=chiusa_il,
            creato_da=utente["id"]
        )

        sondaggio = await get_sondaggio_by_id(sondaggio_id)
        await invia_sondaggio_diretto(context.bot, sondaggio_id, sondaggio)

        await query.edit_message_text(
            f"✅ Sondaggio standard aperto.\n"
            f"Partita: {partita['nome']}\n"
            f"Chiusura automatica tra 1 ora."
        )
        return ConversationHandler.END

    else:
        await query.edit_message_text("Che nome dai al sondaggio?")
        return NOME

async def ricevi_nome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["nome_sondaggio"] = update.message.text.strip()

    tipi = await get_tipi_sondaggio_attivi()
    if not tipi:
        await update.message.reply_text("⚠️ Nessun tipo sondaggio disponibile. Creane uno dalla WUI.")
        return ConversationHandler.END

    if len(tipi) == 1:
        context.user_data["tipo"] = tipi[0]
        return await chiedi_partita(update, context)

    tastiera = InlineKeyboardMarkup([
        [InlineKeyboardButton(t["nome"], callback_data=f"tipo_{t['id']}")]
        for t in tipi
    ])
    await update.message.reply_text("Che tipo di sondaggio vuoi aprire?", reply_markup=tastiera)
    return PARTITA

async def ricevi_tipo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    tipo_id = int(query.data.split("_")[1])
    tipo    = await get_tipo_sondaggio(tipo_id)
    context.user_data["tipo"] = tipo
    return await chiedi_partita(update, context)

async def chiedi_partita(update, context):
    partite = await get_ultime_partite(10)
    if not partite:
        msg = "⚠️ Nessuna partita disponibile. Creane una dalla WUI."
        if update.callback_query:
            await update.callback_query.edit_message_text(msg)
        else:
            await update.message.reply_text(msg)
        return ConversationHandler.END

    tastiera = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"{p['nome']} — {p['data_ora'].strftime('%d/%m/%Y')}",
            callback_data=f"partita_{p['id']}"
        )]
        for p in partite
    ])
    if update.callback_query:
        await update.callback_query.edit_message_text("A quale partita si riferisce?", reply_markup=tastiera)
    else:
        await update.message.reply_text("A quale partita si riferisce?", reply_markup=tastiera)
    return PARTITA

async def ricevi_partita(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data.startswith("tipo_"):
        return await ricevi_tipo(update, context)

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
        tastiera = InlineKeyboardMarkup([[
            InlineKeyboardButton("Manualmente", callback_data="chiude_manuale"),
            InlineKeyboardButton("Tra N ore",   callback_data="chiude_ore"),
            InlineKeyboardButton("Data e ora",  callback_data="chiude_data")
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
    context.user_data["schedulata_il"] = data.replace(hour=ora.hour, minute=ora.minute)

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

    context.user_data["chiusura_tipo"] = query.data.replace("chiude_", "")

    if query.data == "chiude_manuale":
        return await conferma_crea_sondaggio(update, context)
    elif query.data == "chiude_ore":
        await query.edit_message_text("Quante ore dopo l'apertura deve chiudersi?")
        return ORE_CHIUSURA
    else:
        await query.edit_message_text("Che giorno si chiude? (formato GG/MM/YYYY)")
        return DATA_CHIUSURA

async def ricevi_ore_chiusura(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["ore_chiusura"] = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("Inserisci un numero intero.")
        return ORE_CHIUSURA
    return await conferma_crea_sondaggio(update, context)

async def ricevi_data_chiusura(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["data_chiusura"] = datetime.strptime(update.message.text.strip(), "%d/%m/%Y")
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

    schedulata_il = d.get("schedulata_il")
    chiusura_tipo = d.get("chiusura_tipo")

    if chiusura_tipo == "manuale":
        chiusa_il = None
    elif chiusura_tipo == "ore":
        base = schedulata_il or datetime.now()
        chiusa_il = base + timedelta(hours=d["ore_chiusura"])
    else:
        chiusa_il = d.get("chiusa_il")

    telegram_id = (update.effective_user or update.callback_query.from_user).id
    async with get_pool().acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT id FROM utenti WHERE telegram_id = %s", (telegram_id,))
            utente = await cur.fetchone()

    tipo = d["tipo"]

    sondaggio_id = await crea_sondaggio(
        tipo_id=tipo["id"],
        nome=d["nome_sondaggio"],
        partita_id=d["partita_id"],
        schedulata_il=schedulata_il,
        chiusa_il=chiusa_il,
        creato_da=utente["id"]
    )

    if schedulata_il is None:
        sondaggio = await get_sondaggio_by_id(sondaggio_id)
        msg = update.effective_message or update.callback_query.message
        await invia_sondaggio_diretto(context.bot, sondaggio_id, sondaggio)

    apertura_str = "Adesso" if not schedulata_il else schedulata_il.strftime("%d/%m/%Y alle %H:%M")
    chiusura_str = "Manuale" if not chiusa_il else chiusa_il.strftime("%d/%m/%Y alle %H:%M")
    label        = label_target(tipo.get("target", "tutti"))

    msg_testo = (
        f"✅ Sondaggio '{d['nome_sondaggio']}' creato.\n"
        f"Tipo: Valutazione {label}\n"
        f"Apertura: {apertura_str}\n"
        f"Chiusura: {chiusura_str}"
    )

    if update.callback_query:
        await update.callback_query.edit_message_text(msg_testo)
    else:
        await update.message.reply_text(msg_testo)

    context.user_data.clear()
    return ConversationHandler.END


# ============================================================
# INVIO SONDAGGIO AI PARTECIPANTI
# ============================================================

async def invia_sondaggio_diretto(bot, sondaggio_id: int, sondaggio: dict = None):
    if sondaggio is None:
        sondaggio = await get_sondaggio_by_id(sondaggio_id)

    tipo    = await get_tipo_sondaggio(sondaggio["tipo_sondaggio_id"])
    target  = tipo.get("target", "sl")
    label   = label_target(target)
    soggetti = await get_soggetti_partita(sondaggio["partita_id"], target)

    if not soggetti:
        logger.info(f"Nessun {label} trovato per il sondaggio {sondaggio_id}")
        return

    partecipanti_map = {}  # telegram_id -> info utente
    for soggetto in soggetti:
        if target == "pl":
            partecipanti = await get_votanti_pl(sondaggio["partita_id"], soggetto["id"])
        else:
            partecipanti = await get_partecipanti_sondaggio(sondaggio["partita_id"], soggetto["id"])

        for p in partecipanti:
            if p["id"] == soggetto["id"]:
                continue
            if p["telegram_id"] not in partecipanti_map:
                partecipanti_map[p["telegram_id"]] = p

    # Manda un unico messaggio per partecipante con tutti i bottoni
    tastiera = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"▶ Valuta {label} {soggetto['username'] or soggetto['nome']}",
            callback_data=f"inizia_{sondaggio_id}_{soggetto['id']}"
        )]
        for soggetto in soggetti
    ])

    for telegram_id, p in partecipanti_map.items():
        try:
            await bot.send_message(
                chat_id=telegram_id,
                text=f"📋 {sondaggio['nome']}\n\nSeleziona chi vuoi valutare:",
                reply_markup=tastiera
            )
        except Exception as e:
            logger.warning(f"Impossibile inviare a {telegram_id}: {e}")


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
        n        = await get_conteggio_risposte(s["id"])
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
        f"🔒 Sondaggio '{sondaggio['nome']}' chiuso. Risultati inviati."
    )


# ============================================================
# INVIO RISULTATI
# ============================================================

async def invia_risultati(context, sondaggio_id: int, nome_sondaggio: str):
    medie = await get_medie_sondaggio(sondaggio_id)
    if not medie:
        logger.info("Nessun risultato da inviare.")
        return

    sondaggio = await get_sondaggio_by_id(sondaggio_id)
    tipo      = await get_tipo_sondaggio(sondaggio["tipo_sondaggio_id"])
    label     = label_target(tipo.get("target", "sl"))

    per_soggetto = {}
    for riga in medie:
        nome = riga["sl_nome"]
        if nome not in per_soggetto:
            per_soggetto[nome] = {
                "telegram_id": riga["sl_telegram_id"],
                "votanti":     riga["votanti"],
                "domande":     []
            }
        per_soggetto[nome]["domande"].append({
            "testo": riga["domanda"],
            "media": riga["media"]
        })

    for soggetto_nome, dati in per_soggetto.items():
        testo = (
            f"📊 {label} {soggetto_nome}\n"
            f"Risultati: {nome_sondaggio}\n"
            f"Votanti: {dati['votanti']}\n\n"
        )
        for d in dati["domande"]:
            testo += f"• {d['testo']}\n  → Media: {d['media']}/10\n\n"

        try:
            await context.bot.send_message(chat_id=dati["telegram_id"], text=testo)
        except Exception as e:
            logger.warning(f"Impossibile inviare risultati a {soggetto_nome}: {e}")


# ============================================================
# /valuta — compilazione sondaggio
# ============================================================

async def inizia_valutazione(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    parts       = query.data.split("_")
    sondaggio_id = int(parts[1])
    soggetto_id  = int(parts[2])

    utente = await get_utente_completo(query.from_user.id)
    if not utente or utente["stato"] != "effettivo":
        await query.edit_message_text("⛔ Non puoi compilare questo sondaggio.")
        return

    sondaggio = await get_sondaggio_by_id(sondaggio_id)
    if not sondaggio or not sondaggio["attiva"]:
        await query.edit_message_text("⚠️ Questo sondaggio è già chiuso.")
        return

    if utente["id"] == soggetto_id:
        await query.edit_message_text("⛔ Non puoi valutare te stesso.")
        return

    if await ha_gia_risposto(sondaggio_id, utente["id"], soggetto_id):
        await query.edit_message_text("Hai già compilato questa valutazione.")
        return

    risposta_id = await crea_risposta(sondaggio_id, utente["id"], soggetto_id)
    domande     = await get_domande_sondaggio(sondaggio["tipo_sondaggio_id"])

    tipo  = await get_tipo_sondaggio(sondaggio["tipo_sondaggio_id"])
    label = label_target(tipo.get("target", "sl"))

    context.user_data["sondaggio"]   = sondaggio
    context.user_data["utente"]      = utente
    context.user_data["soggetto_id"] = soggetto_id
    context.user_data["risposta_id"] = risposta_id
    context.user_data["domande"]     = domande
    context.user_data["domanda_idx"] = 0

    await query.edit_message_text(
        f"Stai valutando un {label}.\n"
        f"Risponderai a {len(domande)} domande con un voto da 1 a 10."
    )
    await manda_domanda(query.message, context)
    return RISPONDI

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

    # Filtra solo i sondaggi in cui l'utente può votare
    sondaggi_disponibili = []
    for s in attivi:
        tipo   = await get_tipo_sondaggio(s["tipo_sondaggio_id"])
        target = tipo.get("target", "sl")

        if target == "pl":
            # Solo gli SL possono votare i PL
            votanti = await get_votanti_pl(s["partita_id"], 0)
            ids     = [v["id"] for v in votanti]
            if utente["id"] not in ids:
                continue
        else:
            partecipanti = await get_partecipanti_sondaggio(s["partita_id"], 0)
            ids          = [p["id"] for p in partecipanti]
            if utente["id"] not in ids:
                continue

        sondaggi_disponibili.append(s)

    if not sondaggi_disponibili:
        await update.message.reply_text("📭 Non ci sono sondaggi disponibili per te al momento.")
        return ConversationHandler.END

    context.user_data["utente"] = utente

    if len(sondaggi_disponibili) == 1:
        context.user_data["sondaggio"] = sondaggi_disponibili[0]
        return await mostra_soggetti(update, context)

    tastiera = InlineKeyboardMarkup([
        [InlineKeyboardButton(s["nome"], callback_data=f"sondaggio_{s['id']}")]
        for s in sondaggi_disponibili
    ])
    await update.message.reply_text("Quale sondaggio vuoi compilare?", reply_markup=tastiera)
    return SCEGLI_SL

async def scegli_sondaggio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    sondaggio_id = int(query.data.split("_")[1])
    sondaggio    = await get_sondaggio_by_id(sondaggio_id)
    context.user_data["sondaggio"] = sondaggio
    return await mostra_soggetti(update, context)

async def mostra_soggetti(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sondaggio = context.user_data["sondaggio"]
    utente    = context.user_data["utente"]

    tipo   = await get_tipo_sondaggio(sondaggio["tipo_sondaggio_id"])
    target = tipo.get("target", "sl")
    label  = label_target(target)

    soggetti = await get_soggetti_partita(sondaggio["partita_id"], target)

    # Filtra già votati e se stesso
    soggetti_disponibili = []
    for s in soggetti:
        if s["id"] == utente["id"]:
            continue
        if await ha_gia_risposto(sondaggio["id"], utente["id"], s["id"]):
            continue
        soggetti_disponibili.append(s)

    if not soggetti_disponibili:
        msg = f"Hai già valutato tutti gli {label} disponibili per questo sondaggio."
        if update.callback_query:
            await update.callback_query.edit_message_text(msg)
        else:
            await update.message.reply_text(msg)
        return ConversationHandler.END

    tastiera = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            s["username"] or s["nome"],
            callback_data=f"sl_{s['id']}"
        )]
        for s in soggetti_disponibili
    ])
    msg = f"📋 {sondaggio['nome']}\n\nQuale {label} vuoi valutare?"
    if update.callback_query:
        await update.callback_query.edit_message_text(msg, reply_markup=tastiera)
    else:
        await update.message.reply_text(msg, reply_markup=tastiera)
    return SCEGLI_SL

async def scegli_sl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    soggetto_id = int(query.data.split("_")[1])
    sondaggio   = context.user_data["sondaggio"]
    utente      = context.user_data["utente"]

    risposta_id = await crea_risposta(sondaggio["id"], utente["id"], soggetto_id)
    domande     = await get_domande_sondaggio(sondaggio["tipo_sondaggio_id"])

    context.user_data["soggetto_id"]  = soggetto_id
    context.user_data["risposta_id"]  = risposta_id
    context.user_data["domande"]      = domande
    context.user_data["domanda_idx"]  = 0

    tipo  = await get_tipo_sondaggio(sondaggio["tipo_sondaggio_id"])
    label = label_target(tipo.get("target", "sl"))

    await query.edit_message_text(
        f"Stai valutando un {label}.\n"
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
            "Puoi fare un'altra valutazione con /valuta."
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
