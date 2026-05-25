import aiomysql
from config import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD

_pool = None

async def init_db():
    global _pool
    _pool = await aiomysql.create_pool(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        db=DB_NAME,
        autocommit=False,
        minsize=2,
        maxsize=10,
        charset="utf8mb4"
    )

async def close_db():
    global _pool
    if _pool:
        _pool.close()
        await _pool.wait_closed()
        _pool = None

def get_pool():
    if _pool is None:
        raise RuntimeError("DB non inizializzato — chiama init_db() prima.")
    return _pool

# ============================================================
# SONDAGGI
# ============================================================

async def get_sondaggi_attivi():
    async with get_pool().acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("""
                SELECT s.*, ts.nome as tipo_nome,
                       p.nome as partita_nome, p.data_ora as partita_data
                FROM sondaggi s
                JOIN tipi_sondaggio ts ON s.tipo_sondaggio_id = ts.id
                LEFT JOIN partite p ON s.partita_id = p.id
                WHERE s.attiva = TRUE
                ORDER BY s.aperta_il DESC
            """)
            return await cur.fetchall()

async def get_sondaggio_by_id(sondaggio_id: int):
    async with get_pool().acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT * FROM sondaggi WHERE id = %s",
                (sondaggio_id,)
            )
            return await cur.fetchone()

async def crea_sondaggio(tipo_id: int, nome: str, partita_id: int,
                          schedulata_il, chiusa_il, creato_da: int):
    async with get_pool().acquire() as conn:
        async with conn.cursor() as cur:
            aperta_il = None
            attiva    = False

            if schedulata_il is None:
                from datetime import datetime
                aperta_il = datetime.now()
                attiva    = True

            await cur.execute("""
                INSERT INTO sondaggi
                (tipo_sondaggio_id, nome, partita_id, schedulata_il,
                 aperta_il, chiusa_il, attiva, creato_da)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            """, (tipo_id, nome, partita_id, schedulata_il,
                  aperta_il, chiusa_il, attiva, creato_da))
            await conn.commit()
            return cur.lastrowid

async def chiudi_sondaggio(sondaggio_id: int):
    async with get_pool().acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                UPDATE sondaggi
                SET attiva = FALSE, chiusa_il = NOW()
                WHERE id = %s
            """, (sondaggio_id,))
            await conn.commit()

async def get_partecipanti_sondaggio(partita_id: int, sl_id: int):
    """Effettivi presenti alla partita, escluso lo SL che viene valutato."""
    async with get_pool().acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("""
                SELECT u.id, u.telegram_id, u.nome
                FROM presenze p
                JOIN utenti u ON p.utente_id = u.id
                WHERE p.partita_id = %s
                  AND p.presente = TRUE
                  AND u.stato = 'effettivo'
                  AND u.id != %s
                  AND u.telegram_id IS NOT NULL
            """, (partita_id, sl_id))
            return await cur.fetchall()

async def get_sl_partita(partita_id: int):
    """SL presenti alla partita."""
    async with get_pool().acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("""
                SELECT u.id, u.nome, u.username, u.telegram_id
                FROM presenze p
                JOIN utenti u ON p.utente_id = u.id
                JOIN utenti_ruoli ur ON ur.utente_id = u.id
                JOIN ruoli r ON ur.ruolo_id = r.id
                WHERE p.partita_id = %s
                  AND p.presente = TRUE
                  AND u.stato = 'effettivo'
                  AND r.is_sl = TRUE
                  AND ur.stato = 'ottenuto'
            """, (partita_id,))
            return await cur.fetchall()

async def get_domande_sondaggio(tipo_sondaggio_id: int):
    async with get_pool().acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("""
                SELECT * FROM domande
                WHERE tipo_sondaggio_id = %s AND attiva = TRUE
                ORDER BY ordine
            """, (tipo_sondaggio_id,))
            return await cur.fetchall()

async def ha_gia_risposto(sondaggio_id: int, votante_id: int, soggetto_id: int):
    async with get_pool().acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                SELECT id FROM risposte
                WHERE sondaggio_id = %s
                  AND votante_id = %s
                  AND soggetto_id = %s
            """, (sondaggio_id, votante_id, soggetto_id))
            return await cur.fetchone() is not None

async def crea_risposta(sondaggio_id: int, votante_id: int, soggetto_id: int):
    async with get_pool().acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                INSERT INTO risposte (sondaggio_id, votante_id, soggetto_id)
                VALUES (%s, %s, %s)
            """, (sondaggio_id, votante_id, soggetto_id))
            await conn.commit()
            return cur.lastrowid

async def salva_dettaglio(risposta_id: int, domanda_id: int, valore: int):
    async with get_pool().acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                INSERT INTO risposte_dettaglio
                (risposta_id, domanda_id, valore_scala)
                VALUES (%s, %s, %s)
            """, (risposta_id, domanda_id, valore))
            await conn.commit()

async def completa_risposta(risposta_id: int):
    async with get_pool().acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE risposte SET completata = TRUE WHERE id = %s",
                (risposta_id,)
            )
            await conn.commit()

async def elimina_risposta(risposta_id: int):
    async with get_pool().acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "DELETE FROM risposte_dettaglio WHERE risposta_id = %s",
                (risposta_id,)
            )
            await cur.execute(
                "DELETE FROM risposte WHERE id = %s",
                (risposta_id,)
            )
            await conn.commit()

async def get_medie_sondaggio(sondaggio_id: int):
    async with get_pool().acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("""
                SELECT
                    u.nome as sl_nome,
                    u.telegram_id as sl_telegram_id,
                    d.testo as domanda,
                    d.ordine,
                    ROUND(AVG(rd.valore_scala), 1) as media,
                    COUNT(DISTINCT r.votante_id) as votanti
                FROM risposte_dettaglio rd
                JOIN risposte r ON rd.risposta_id = r.id
                JOIN domande d ON rd.domanda_id = d.id
                JOIN utenti u ON r.soggetto_id = u.id
                WHERE r.sondaggio_id = %s AND r.completata = TRUE
                GROUP BY u.id, d.id
                ORDER BY u.nome, d.ordine
            """, (sondaggio_id,))
            return await cur.fetchall()

async def get_ultime_partite(limit: int = 10):
    async with get_pool().acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("""
                SELECT * FROM partite
                ORDER BY data_ora DESC
                LIMIT %s
            """, (limit,))
            return await cur.fetchall()

async def get_conteggio_risposte(sondaggio_id: int):
    async with get_pool().acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("""
                SELECT COUNT(DISTINCT votante_id) as n
                FROM risposte
                WHERE sondaggio_id = %s AND completata = TRUE
            """, (sondaggio_id,))
            return (await cur.fetchone())["n"]
