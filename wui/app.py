from flask import Flask, render_template, request, redirect, url_for, flash
import pymysql
import pymysql.cursors
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "cambia_questa_chiave")


# ============================================================
# DB SINCRONO — solo per la WUI
# ============================================================

def get_conn():
    return pymysql.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", 3306)),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False
    )

def db(sql, params=None, fetch=None):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            if fetch == "all":
                return cur.fetchall()
            if fetch == "one":
                return cur.fetchone()
            conn.commit()
            return cur.lastrowid
    finally:
        conn.close()


# ============================================================
# HELPER — chiama funzioni async da Flask
# ============================================================

def run_calcolo(coro_func, *args):
    """Crea un event loop pulito per ogni chiamata a calcolo.py."""
    async def runner():
        from db import init_db, close_db
        await init_db()
        try:
            return await coro_func(*args)
        finally:
            await close_db()
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(runner())
    finally:
        loop.close()


# ============================================================
# INDEX
# ============================================================

@app.route("/")
def index():
    return render_template("index.html")


# ============================================================
# UTENTI
# ============================================================

@app.route("/utenti")
def utenti():
    rows = db(
        "SELECT u.*, g.nome as grado_nome FROM utenti u LEFT JOIN gradi g ON u.grado_id = g.id ORDER BY u.nome",
        fetch="all"
    )
    return render_template("utenti.html", utenti=rows)

@app.route("/utenti/nuovo", methods=["GET","POST"])
def utenti_nuovo():
    gradi = db("SELECT * FROM gradi ORDER BY ordine", fetch="all")
    if request.method == "POST":
        telegram_id = request.form.get("telegram_id", "").strip()
        if telegram_id and not telegram_id.isdigit():
            flash("Errore: il Telegram ID deve essere un numero intero.")
            return render_template("utenti_form.html", utente=None, gradi=gradi)
        db("INSERT INTO utenti (telegram_id, nome, username, stato, grado_id) VALUES (%s,%s,%s,%s,%s)", (
            int(telegram_id) if telegram_id else None,
            request.form["nome"],
            request.form.get("username") or None,
            "recluta",
            request.form.get("grado_id") or None
        ))
        flash("Utente creato.")
        return redirect(url_for("utenti"))
    return render_template("utenti_form.html", utente=None, gradi=gradi)

@app.route("/utenti/<int:id>/modifica", methods=["GET","POST"])
def utenti_modifica(id):
    gradi = db("SELECT * FROM gradi ORDER BY ordine", fetch="all")
    utente = db("SELECT * FROM utenti WHERE id = %s", (id,), fetch="one")
    if request.method == "POST":
        telegram_id = request.form.get("telegram_id", "").strip()
        if telegram_id and not telegram_id.isdigit():
            flash("Errore: il Telegram ID deve essere un numero intero.")
            return render_template("utenti_form.html", utente=utente, gradi=gradi)
        db("UPDATE utenti SET telegram_id=%s, nome=%s, username=%s, stato=%s, grado_id=%s, autonomia=%s, leadership=%s, pianificazione=%s WHERE id=%s", (
            int(telegram_id) if telegram_id else None,
            request.form["nome"],
            request.form.get("username") or None,
            request.form["stato"],
            request.form.get("grado_id") or None,
            request.form["autonomia"],
            request.form["leadership"],
            request.form["pianificazione"],
            id
        ))
        from calcolo import ricalcola_utente, controlla_promozione_recluta
        run_calcolo(ricalcola_utente, id)
        run_calcolo(controlla_promozione_recluta, id)
        flash("Utente aggiornato.")
        return redirect(url_for("utenti"))
    return render_template("utenti_form.html", utente=utente, gradi=gradi)

@app.route("/utenti/<int:id>/elimina", methods=["POST"])
def utenti_elimina(id):
    db("DELETE FROM utenti WHERE id = %s", (id,))
    flash("Utente eliminato.")
    return redirect(url_for("utenti"))

@app.route("/utenti/<int:id>")
def utenti_dettaglio(id):
    utente = db("SELECT u.*, g.nome as grado_nome FROM utenti u LEFT JOIN gradi g ON u.grado_id = g.id WHERE u.id = %s", (id,), fetch="one")
    if not utente:
        flash("Utente non trovato.")
        return redirect(url_for("utenti"))

    ruoli_utente = db("""
        SELECT ur.*, r.nome as ruolo_nome
        FROM utenti_ruoli ur
        JOIN ruoli r ON ur.ruolo_id = r.id
        WHERE ur.utente_id = %s
        ORDER BY r.nome
    """, (id,), fetch="all")

    ruoli_disponibili = db("""
        SELECT * FROM ruoli
        WHERE attivo = TRUE
        AND id NOT IN (
            SELECT ruolo_id FROM utenti_ruoli WHERE utente_id = %s
        )
        ORDER BY nome
    """, (id,), fetch="all")

    note_utente = db("""
        SELECT n.*, u.nome as inserito_da_nome
        FROM note n
        LEFT JOIN utenti u ON n.inserito_da = u.id
        WHERE n.utente_id = %s
        ORDER BY n.inserito_il DESC
    """, (id,), fetch="all")

    return render_template("utenti_dettaglio.html",
        utente=utente,
        ruoli_utente=ruoli_utente,
        ruoli_disponibili=ruoli_disponibili,
        note_utente=note_utente
    )

@app.route("/utenti/<int:id>/ruolo/aggiungi", methods=["POST"])
def utenti_ruolo_aggiungi(id):
    ruolo_id = request.form.get("ruolo_id")
    if ruolo_id:
        db("INSERT IGNORE INTO utenti_ruoli (utente_id, ruolo_id, stato) VALUES (%s,%s,'non_acquisito')", (id, ruolo_id))
    return redirect(url_for("utenti_dettaglio", id=id))

@app.route("/utenti/<int:id>/ruolo/<int:ruolo_id>/stato", methods=["POST"])
def utenti_ruolo_stato(id, ruolo_id):
    stato = request.form.get("stato")
    if stato in ("non_acquisito", "in_corso", "ottenuto"):
        db("UPDATE utenti_ruoli SET stato = %s WHERE utente_id = %s AND ruolo_id = %s", (stato, id, ruolo_id))
        from calcolo import ricalcola_utente
        run_calcolo(ricalcola_utente, id)
    return redirect(url_for("utenti_dettaglio", id=id))

@app.route("/utenti/<int:id>/ruolo/<int:ruolo_id>/elimina", methods=["POST"])
def utenti_ruolo_elimina(id, ruolo_id):
    db("DELETE FROM utenti_ruoli WHERE utente_id = %s AND ruolo_id = %s", (id, ruolo_id))
    from calcolo import ricalcola_utente
    run_calcolo(ricalcola_utente, id)
    return redirect(url_for("utenti_dettaglio", id=id))

@app.route("/utenti/<int:id>/nota/aggiungi", methods=["POST"])
def utenti_nota_aggiungi(id):
    tipo  = request.form.get("tipo")
    testo = request.form.get("testo", "").strip()
    if tipo in ("merito", "demerito") and testo:
        db("INSERT INTO note (utente_id, tipo, testo) VALUES (%s,%s,%s)", (id, tipo, testo))
        from calcolo import ricalcola_utente
        run_calcolo(ricalcola_utente, id)
    return redirect(url_for("utenti_dettaglio", id=id))

@app.route("/utenti/<int:id>/nota/<int:nota_id>/elimina", methods=["POST"])
def utenti_nota_elimina(id, nota_id):
    db("DELETE FROM note WHERE id = %s AND utente_id = %s", (nota_id, id))
    from calcolo import ricalcola_utente
    run_calcolo(ricalcola_utente, id)
    return redirect(url_for("utenti_dettaglio", id=id))


# ============================================================
# GRADI
# ============================================================

@app.route("/gradi")
def gradi():
    rows = db("SELECT * FROM gradi ORDER BY ordine", fetch="all")
    return render_template("gradi.html", gradi=rows)

@app.route("/gradi/nuovo", methods=["GET","POST"])
def gradi_nuovo():
    if request.method == "POST":
        db("INSERT INTO gradi (nome, ordine, grado_id_formula, is_ufficiale, punteggio_minimo) VALUES (%s,%s,%s,%s,%s)", (
            request.form["nome"],
            request.form["ordine"],
            request.form["grado_id_formula"],
            1 if request.form.get("is_ufficiale") else 0,
            request.form["punteggio_minimo"]
        ))
        flash("Grado creato.")
        return redirect(url_for("gradi"))
    return render_template("gradi_form.html", grado=None)

@app.route("/gradi/<int:id>/modifica", methods=["GET","POST"])
def gradi_modifica(id):
    grado = db("SELECT * FROM gradi WHERE id = %s", (id,), fetch="one")
    if request.method == "POST":
        db("UPDATE gradi SET nome=%s, ordine=%s, grado_id_formula=%s, is_ufficiale=%s, punteggio_minimo=%s WHERE id=%s", (
            request.form["nome"],
            request.form["ordine"],
            request.form["grado_id_formula"],
            1 if request.form.get("is_ufficiale") else 0,
            request.form["punteggio_minimo"],
            id
        ))
        from calcolo import ricalcola_tutti
        run_calcolo(ricalcola_tutti)
        flash("Grado aggiornato.")
        return redirect(url_for("gradi"))
    return render_template("gradi_form.html", grado=grado)

@app.route("/gradi/<int:id>/elimina", methods=["POST"])
def gradi_elimina(id):
    db("DELETE FROM gradi WHERE id = %s", (id,))
    flash("Grado eliminato.")
    return redirect(url_for("gradi"))


# ============================================================
# RUOLI
# ============================================================

@app.route("/ruoli")
def ruoli():
    rows = db(
        "SELECT r.*, g.nome as grado_nome FROM ruoli r LEFT JOIN gradi g ON r.grado_minimo_id = g.id ORDER BY r.nome",
        fetch="all"
    )
    return render_template("ruoli.html", ruoli=rows)

@app.route("/ruoli/nuovo", methods=["GET","POST"])
def ruoli_nuovo():
    gradi = db("SELECT * FROM gradi ORDER BY ordine", fetch="all")
    if request.method == "POST":
        db("INSERT INTO ruoli (nome, descrizione, grado_minimo_id, is_sl) VALUES (%s,%s,%s,%s)", (
            request.form["nome"],
            request.form.get("descrizione") or None,
            request.form.get("grado_minimo_id") or None,
            1 if request.form.get("is_sl") else 0
        ))
        flash("Ruolo creato.")
        return redirect(url_for("ruoli"))
    return render_template("ruoli_form.html", ruolo=None, gradi=gradi)

@app.route("/ruoli/<int:id>/modifica", methods=["GET","POST"])
def ruoli_modifica(id):
    gradi = db("SELECT * FROM gradi ORDER BY ordine", fetch="all")
    ruolo = db("SELECT * FROM ruoli WHERE id = %s", (id,), fetch="one")
    if request.method == "POST":
        db("UPDATE ruoli SET nome=%s, descrizione=%s, grado_minimo_id=%s, is_sl=%s, attivo=%s WHERE id=%s", (
            request.form["nome"],
            request.form.get("descrizione") or None,
            request.form.get("grado_minimo_id") or None,
            1 if request.form.get("is_sl") else 0,
            1 if request.form.get("attivo") else 0,
            id
        ))
        flash("Ruolo aggiornato.")
        return redirect(url_for("ruoli"))
    return render_template("ruoli_form.html", ruolo=ruolo, gradi=gradi)

@app.route("/ruoli/<int:id>/elimina", methods=["POST"])
def ruoli_elimina(id):
    db("DELETE FROM ruoli WHERE id = %s", (id,))
    flash("Ruolo eliminato.")
    return redirect(url_for("ruoli"))


# ============================================================
# AVVIO
# ============================================================

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
