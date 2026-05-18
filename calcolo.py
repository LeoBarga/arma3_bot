import asyncio
import math
from db import init_db, close_db, get_pool
import aiomysql
from datetime import date

# ============================================================
# FUNZIONE PRINCIPALE — ricalcola punteggio e tag di un utente
# ============================================================

async def ricalcola_utente(utente_id: int):
    async with get_pool().acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:

            # Dati base utente
            await cur.execute("SELECT * FROM utenti WHERE id = %s", (utente_id,))
            utente = await cur.fetchone()
            if not utente or utente["stato"] == "recluta":
                return

            # Grado corrente
            await cur.execute("SELECT * FROM gradi WHERE id = %s", (utente["grado_id"],))
            grado = await cur.fetchone()
            is_ufficiale = grado["is_ufficiale"] if grado else False

            # --------------------------------------------------------
            # PRESENZE PER ANNO DI GIOCO
            # --------------------------------------------------------
            await cur.execute("""
                SELECT ag.id, ag.nome,
                       COUNT(p.id) as presenze
                FROM anni_gioco ag
                LEFT JOIN partite pt ON pt.anno_gioco_id = ag.id
                LEFT JOIN presenze p ON p.partita_id = pt.id
                                     AND p.utente_id = %s
                                     AND p.presente = TRUE
                GROUP BY ag.id
                ORDER BY ag.data_inizio DESC
                LIMIT 3
            """, (utente_id,))
            anni = await cur.fetchall()

            presenze_anno_attuale = anni[0]["presenze"] if len(anni) > 0 else 0
            presenze_anno_prec    = anni[1]["presenze"] if len(anni) > 1 else 0
            presenze_due_anni_fa  = anni[2]["presenze"] if len(anni) > 2 else 0

            punteggio_presenze = (
                presenze_anno_attuale +
                (presenze_anno_prec * 0.6) +
                (presenze_due_anni_fa * 0.3)
            ) * 0.6

            # --------------------------------------------------------
            # QUALIFICHE (ruoli ottenuti)
            # --------------------------------------------------------
            await cur.execute("""
                SELECT r.is_sl
                FROM utenti_ruoli ur
                JOIN ruoli r ON ur.ruolo_id = r.id
                WHERE ur.utente_id = %s AND ur.stato = 'ottenuto'
            """, (utente_id,))
            ruoli_ottenuti = await cur.fetchall()

            num_qualifiche = len(ruoli_ottenuti)
            is_sl = any(r["is_sl"] for r in ruoli_ottenuti)

            # --------------------------------------------------------
            # PERMESSI (istruttore)
            # --------------------------------------------------------
            await cur.execute("""
                SELECT permesso FROM utenti_permessi
                WHERE utente_id = %s
            """, (utente_id,))
            permessi = [r["permesso"] for r in await cur.fetchall()]
            is_istruttore = "istruttore" in permessi

            # --------------------------------------------------------
            # NOTE MERITO/DEMERITO
            # --------------------------------------------------------
            await cur.execute("""
                SELECT
                    SUM(CASE WHEN tipo = 'merito'   THEN 1 ELSE 0 END) as meriti,
                    SUM(CASE WHEN tipo = 'demerito' THEN 1 ELSE 0 END) as demeriti
                FROM note WHERE utente_id = %s
            """, (utente_id,))
            note = await cur.fetchone()
            meriti   = int(note["meriti"]   or 0)
            demeriti = int(note["demeriti"] or 0)
            delta_note = meriti - demeriti

            # --------------------------------------------------------
            # PARTITE DI ADDESTRAMENTO
            # --------------------------------------------------------
            await cur.execute("""
                SELECT COUNT(p.id) as n
                FROM presenze p
                JOIN partite pt ON p.partita_id = pt.id
                WHERE p.utente_id = %s
                  AND p.presente = TRUE
                  AND pt.is_addestramento = TRUE
            """, (utente_id,))
            row = await cur.fetchone()
            n_addestramento = row["n"] or 0

            # --------------------------------------------------------
            # FORMULA
            # --------------------------------------------------------
            autonomia      = float(utente["autonomia"])
            leadership     = float(utente["leadership"])
            pianificazione = float(utente["pianificazione"])

            grado_id_formula = grado["grado_id_formula"] if grado else 1
            media_valori = (autonomia + leadership + pianificazione) / 3

            if not is_ufficiale:
                bonus_sl         = 30 if is_sl else 0
                bonus_istruttore = 20 if is_istruttore else 0

                punteggio = (
                    (num_qualifiche * 5) +
                    punteggio_presenze +
                    bonus_sl +
                    bonus_istruttore
                ) * media_valori + (
                    delta_note * math.sqrt(grado_id_formula * 2)
                ) + n_addestramento

            else:
                bonus_sl         = 30 if is_sl else 0
                bonus_istruttore = 20 if is_istruttore else 0

                punteggio = (
                    punteggio_presenze +
                    bonus_sl +
                    bonus_istruttore
                ) * media_valori + (
                    delta_note * math.sqrt(grado_id_formula * 2)
                ) + n_addestramento

            punteggio = round(punteggio)

            # --------------------------------------------------------
            # DETERMINA IL TAG
            # --------------------------------------------------------
            await cur.execute("""
                SELECT * FROM gradi
                WHERE punteggio_minimo <= %s
                AND ordine > 0
                ORDER BY punteggio_minimo DESC, ordine DESC
                LIMIT 1
            """, (punteggio,))
            grado_fascia = await cur.fetchone()

            grado_attuale_ordine = grado["ordine"] if grado else 0
            grado_fascia_ordine  = grado_fascia["ordine"] if grado_fascia else 0

            if grado_fascia_ordine > grado_attuale_ordine:
                tag = "promuovibile"
            elif grado_fascia_ordine < grado_attuale_ordine:
                tag = "degradabile"
            else:
                tag = None

            # --------------------------------------------------------
            # AGGIORNA UTENTE — solo punteggio e tag, NON il grado
            # --------------------------------------------------------
            await cur.execute("""
                UPDATE utenti
                SET punteggio = %s, tag = %s
                WHERE id = %s
            """, (punteggio, tag, utente_id))
            await conn.commit()

            return {
                "utente_id": utente_id,
                "punteggio": punteggio,
                "tag":       tag,
                "grado":     grado["nome"] if grado else None
            }


# ============================================================
# CONTROLLO STATUS RECLUTA
# ============================================================

async def controlla_promozione_recluta(utente_id: int):
    async with get_pool().acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:

            await cur.execute(
                "SELECT * FROM utenti WHERE id = %s AND stato = 'recluta'",
                (utente_id,)
            )
            utente = await cur.fetchone()
            if not utente:
                return False

            # Conta presenze totali
            await cur.execute("""
                SELECT COUNT(*) as n FROM presenze
                WHERE utente_id = %s AND presente = TRUE
            """, (utente_id,))
            presenze = (await cur.fetchone())["n"]

            # Controlla moduli obbligatori
            await cur.execute("""
                SELECT COUNT(*) as totale FROM moduli
                WHERE obbligatorio = TRUE AND attivo = TRUE
            """)
            totale_moduli = (await cur.fetchone())["totale"]

            await cur.execute("""
                SELECT COUNT(*) as completati FROM reclute_moduli
                WHERE utente_id = %s AND stato = 'completato'
            """, (utente_id,))
            moduli_completati = (await cur.fetchone())["completati"]

            pronta = presenze >= 8 and moduli_completati >= totale_moduli

            await cur.execute("""
                UPDATE utenti SET pronta_promozione = %s WHERE id = %s
            """, (1 if pronta else 0, utente_id))
            await conn.commit()

            return pronta


# ============================================================
# RICALCOLA TUTTI
# ============================================================

async def ricalcola_tutti():
    async with get_pool().acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT id FROM utenti WHERE stato = 'effettivo'"
            )
            utenti = await cur.fetchall()

    for u in utenti:
        await ricalcola_utente(u["id"])


# ============================================================
# ESECUZIONE DIRETTA — per test da terminale
# ============================================================

async def main():
    await init_db()
    await ricalcola_tutti()
    await close_db()

if __name__ == "__main__":
    asyncio.run(main())
