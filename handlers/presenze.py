import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from db import get_pool
from config import GRUPPO_ID
import aiomysql

logger = logging.getLogger(__name__)

# Stati conversazione
TIPO, NOME_PARTITA, DATA_PARTITA = range(12, 15)

TIPI_PARTITA = ["Interna", "Addestramento", "Multiclan"]


# ============================================================
# HELPER
# ============================================================

async def get_utente_da_telegram(telegram_id: int):
    async with get_pool().acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT u.*, g.nome as grado_nome, g.grado_id_formula "
                "FROM utenti u LEFT JOIN gradi g ON u.grado_id = g.id "
                "WHERE u.telegram_id = %s",
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

async def get_sondaggio_presenze(sondaggio_id: int):
    async with get_pool().acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT * FROM sondaggi_presenze WHERE id = %s",
                (sondaggio_id,)
            )
            return await cur.fetchone()

async def get_voti(sondaggio_id: int):
    async with get_pool().acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("""
                SELECT v.*, u.username, u.nome as nome_telegram,
                       g.nome as grado_nome
                FROM voti_presenze v
                JOIN utenti u ON v.utente_id = u.id
                LEFT JOIN gradi g ON u.grado_id = g.id
                WHERE v.sondaggio_id = %s
                ORDER BY v.voto, v.votato_il
            """, (sondaggio_id,))
            return await cur.fetchall()

def nome_utente(voto: dict) -> str:
    return voto["username"] or voto["nome_telegram"] or "Sconosciuto"

def is_ritardo(partita_data_ora: datetime, votato_il: datetime) -> bool:
    soglia = partita_data_ora.replace(hour=18, minute=0, second=0, microsecond=0)
    return votato_il > soglia

def is_scaduto(partita_data_ora: datetime) -> bool:
    scadenza = partita_data_ora.replace(hour=21, minute=0, second=0, microsecond=0)
    return datetime.now() > scadenza

async def genera_testo_lista(sondaggio_id: int, partita_data_ora: datetime) -> str:
    voti = await get_voti(sondaggio_id)

    presenti  = [v for v in voti if v["voto"] == "presente"]
    assenti   = [v for v in voti if v["voto"] == "assente"]
    forse     = [v for v in voti if v["voto"] == "forse"]

    def formatta(v):
        n = nome_utente(v)
        g = v["grado_nome"] or "Recluta"
        r = " [R]" if v["in_ritardo"] else ""
        return f"• {n} ({g}){r}"

    testo = f"📋 Presenze aggiornate al {datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n"

    testo += f"✅ Presenti ({len(presenti)}):\n"
    testo += "\n".join(formatta(v) for v in presenti) if presenti else "—"

    testo += f"\n\n❓ Forse ({len(forse)}):\n"
    testo += "\n".join(formatta(v) for v in forse) if forse else "—"

    testo += f"\n\n❌ Assenti ({len(assenti)}):\n"
    testo += "\n".join(formatta(v) for v in assenti) if assenti else "—"

    return testo


# ============================================================
# /crea — solo admin, solo nel gruppo
# ============================================================

async def cmd_crea(update: Update, context: ContextTypes.DEFAULT_TYPE):
    utente = await get_utente_da_telegram(update.effective_user.id)
    if not utente or not utente["is_admin"]:
        await update.message.reply_text("⛔ Non sei autorizzato.")
        return ConversationHandler.END

    tastiera = InlineKeyboardMarkup([
        [InlineKeyboardButton(t, callback_data=f"tipo_{t}")]
        for t in TIPI_PARTITA
    ])
    await update.message.reply_text("Che tipo di partita è?", reply_markup=tastiera)
    return TIPO

async def ricevi_tipo_partita(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    context.user_data["tipo_partita"] = query.data.replace("tipo_", "")
    await query.edit_message_text("Che nome dai alla partita?")
    return NOME_PARTITA

async def ricevi_nome_partita(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["nome_partita"] = update.message.text.strip()
    await mostra_selezione_data(update, context, offset=0)
    return DATA_PARTITA

async def mostra_selezione_data(update, context, offset: int = 0):
    context.user_data["data_offset"] = offset
    oggi = datetime.now().date()

    giorni = [oggi + timedelta(days=i + offset) for i in range(3)]

    bottoni = [
        [InlineKeyboardButton(
            g.strftime("%A %d/%m/%Y").capitalize(),
            callback_data=f"data_{g.isoformat()}"
        )]
        for g in giorni
    ]

    nav = []
    if offset > 0:
        nav.append(InlineKeyboardButton("◀ Precedenti", callback_data="data_nav_indietro"))
    nav.append(InlineKeyboardButton("Avanti ▶", callback_data="data_nav_avanti"))
    bottoni.append(nav)

    markup = InlineKeyboardMarkup(bottoni)

    if update.callback_query:
        await update.callback_query.edit_message_text("Che giorno si gioca?", reply_markup=markup)
    else:
        await update.message.reply_text("Che giorno si gioca?", reply_markup=markup)

async def ricevi_data_partita(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "data_nav_avanti":
        offset = context.user_data.get("data_offset", 0) + 3
        await mostra_selezione_data(update, context, offset)
        return DATA_PARTITA

    if query.data == "data_nav_indietro":
        offset = max(0, context.user_data.get("data_offset", 0) - 3)
        await mostra_selezione_data(update, context, offset)
        return DATA_PARTITA

    data_str = query.data.replace("data_", "")
    data     = datetime.fromisoformat(data_str)
    context.user_data["data_partita"] = data

    await query.edit_message_text(
        f"Riepilogo:\n"
        f"Tipo: {context.user_data['tipo_partita']}\n"
        f"Nome: {context.user_data['nome_partita']}\n"
        f"Data: {data.strftime('%d/%m/%Y')}\n\n"
        f"Confermo?"
    )

    tastiera = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Conferma", callback_data="conferma_crea"),
        InlineKeyboardButton("❌ Annulla",  callback_data="annulla_crea")
    ]])
    await query.edit_message_text(
        f"Riepilogo:\n"
        f"Tipo: {context.user_data['tipo_partita']}\n"
        f"Nome: {context.user_data['nome_partita']}\n"
        f"Data: {data.strftime('%d/%m/%Y')}\n\n"
        f"Confermo?",
        reply_markup=tastiera
    )
    return DATA_PARTITA

async def conferma_crea_partita(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "annulla_crea":
        await query.edit_message_text("Annullato.")
        context.user_data.clear()
        return ConversationHandler.END

    d             = context.user_data
    nome          = d["nome_partita"]
    tipo          = d["tipo_partita"]
    data_partita  = d["data_partita"]
    is_addestr    = tipo == "Addestramento"
    data_ora      = data_partita.replace(hour=20, minute=0)  # ora default

    utente = await get_utente_da_telegram(query.from_user.id)

    async with get_pool().acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:

            # Trova anno di gioco attivo
            await cur.execute(
                "SELECT id FROM anni_gioco WHERE attivo = TRUE LIMIT 1"
            )
            anno = await cur.fetchone()
            if not anno:
                await query.edit_message_text("⚠️ Nessun anno di gioco attivo. Configuralo dalla WUI.")
                return ConversationHandler.END

            # Crea la partita
            await cur.execute("""
                INSERT INTO partite (nome, data_ora, anno_gioco_id, is_addestramento, creato_da)
                VALUES (%s, %s, %s, %s, %s)
            """, (f"[{tipo}] {nome}", data_ora, anno["id"], is_addestr, utente["id"]))
            await conn.commit()
            partita_id = cur.lastrowid

            # Crea il topic nel gruppo
            topic = await query.get_bot().create_forum_topic(
                chat_id=GRUPPO_ID,
                name=f"{'🔵' if tipo == 'Interna' else '🟢' if tipo == 'Addestramento' else '🟡'} {nome} — {data_partita.strftime('%d/%m/%Y')}"
            )
            topic_id = topic.message_thread_id

            # Manda il messaggio lista (placeholder)
            msg_lista = await query.get_bot().send_message(
                chat_id=GRUPPO_ID,
                message_thread_id=topic_id,
                text="📋 Presenze aggiornate:\n\nNessun voto ancora."
            )

            # Manda il messaggio bottoni
            tastiera_voto = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Presente",                    callback_data=f"voto_presente"),
                InlineKeyboardButton("❌ Assente",                     callback_data=f"voto_assente"),
                InlineKeyboardButton("❓ Forse (confermo entro le 18)", callback_data=f"voto_forse"),
            ]])
            msg_bottoni = await query.get_bot().send_message(
                chat_id=GRUPPO_ID,
                message_thread_id=topic_id,
                text=f"📅 {nome} — {data_partita.strftime('%d/%m/%Y')}\n\nVota la tua presenza:",
                reply_markup=tastiera_voto
            )

            # Salva il sondaggio presenze nel DB
            await cur.execute("""
                INSERT INTO sondaggi_presenze
                (partita_id, topic_id, messaggio_lista_id, messaggio_bottoni_id)
                VALUES (%s, %s, %s, %s)
            """, (partita_id, topic_id, msg_lista.message_id, msg_bottoni.message_id))
            await conn.commit()
            sondaggio_id = cur.lastrowid

    await query.edit_message_text(
        f"✅ Partita '{nome}' creata.\n"
        f"Topic aperto nel gruppo."
    )
    context.user_data.clear()
    return ConversationHandler.END


# ============================================================
# GESTIONE VOTI
# ============================================================

async def gestisci_voto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    utente = await get_utente_da_telegram(query.from_user.id)
    if not utente:
        await query.answer("Non sei registrato. Scrivi /start al bot in privato.", show_alert=True)
        return

    voto         = query.data.replace("voto_", "")
    message_id   = query.message.message_id
    thread_id    = query.message.message_thread_id

    async with get_pool().acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:

            # Trova il sondaggio dal messaggio bottoni
            await cur.execute("""
                SELECT sp.*, p.data_ora
                FROM sondaggi_presenze sp
                JOIN partite p ON sp.partita_id = p.id
                WHERE sp.messaggio_bottoni_id = %s AND sp.topic_id = %s
            """, (message_id, thread_id))
            sondaggio = await cur.fetchone()

            if not sondaggio:
                await query.answer("Sondaggio non trovato.", show_alert=True)
                return

            if not sondaggio["aperto"]:
                await query.answer("⏰ Il sondaggio è chiuso. Non è più possibile votare.", show_alert=True)
                return

            if is_scaduto(sondaggio["data_ora"]):
                # Chiudi il sondaggio
                await cur.execute(
                    "UPDATE sondaggi_presenze SET aperto = FALSE WHERE id = %s",
                    (sondaggio["id"],)
                )
                await conn.commit()
                await query.answer("⏰ Il sondaggio è chiuso. Non è più possibile votare.", show_alert=True)
                return

            # Controlla se è ritardo
            in_ritardo = is_ritardo(sondaggio["data_ora"], datetime.now())

            # Salva o aggiorna il voto
            await cur.execute("""
                INSERT INTO voti_presenze (sondaggio_id, utente_id, voto, in_ritardo, votato_il)
                VALUES (%s, %s, %s, %s, NOW())
                ON DUPLICATE KEY UPDATE
                    voto = VALUES(voto),
                    in_ritardo = VALUES(in_ritardo),
                    votato_il = NOW()
            """, (sondaggio["id"], utente["id"], voto, in_ritardo))
            await conn.commit()

    # Aggiorna la lista in tempo reale
    async with get_pool().acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("""
                SELECT sp.*, p.data_ora
                FROM sondaggi_presenze sp
                JOIN partite p ON sp.partita_id = p.id
                WHERE sp.messaggio_bottoni_id = %s AND sp.topic_id = %s
            """, (message_id, thread_id))
            sondaggio = await cur.fetchone()

    testo_lista = await genera_testo_lista(sondaggio["id"], sondaggio["data_ora"])

    try:
        await query.get_bot().edit_message_text(
            chat_id=GRUPPO_ID,
            message_id=sondaggio["messaggio_lista_id"],
            text=testo_lista
        )
    except Exception as e:
        logger.warning(f"Impossibile aggiornare lista presenze: {e}")

    await query.answer(f"Voto registrato: {voto}")
