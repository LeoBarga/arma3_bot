from flask import Flask, render_template, request, redirect, url_for, flash
import pymysql
import pymysql.cursors
import asyncio
import sys
import os
import bcrypt

from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

import hashlib
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "cambia_questa_chiave")

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

limiter = Limiter(get_remote_address, app=app, default_limits=[], storage_uri="memory://")

class WuiUtente(UserMixin):
    def __init__(self, id, username):
        self.id = id
        self.username = username

@login_manager.user_loader
def load_user(user_id):
    row = db("SELECT * FROM wui_utenti WHERE id = %s", (user_id,), fetch="one")
    if row:
        return WuiUtente(row["id"], row["username"])
    return None

@app.before_request
def controlla_auth():
    percorsi_pubblici = ["login", "static"]
    if not current_user.is_authenticated and request.endpoint not in percorsi_pubblici:
        return redirect(url_for("login"))

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
# LOGIN - LOGOUT
# ============================================================

@app.route("/login", methods=["GET","POST"])
@limiter.limit("10 per minute")
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        row = db("SELECT * FROM wui_utenti WHERE username = %s", (username,), fetch="one")
        if row and bcrypt.checkpw(password.encode(), row["password_hash"].encode()):
    	    login_user(WuiUtente(row["id"], row["username"]))
    	    return redirect(url_for("index"))

        flash("Credenziali non valide.")
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


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
    if request.method == "POST":
        telegram_id = request.form.get("telegram_id", "").strip()
        if telegram_id and not telegram_id.isdigit():
            flash("Errore: il Telegram ID deve essere un numero intero.")
            return render_template("utenti_form.html", utente=None, gradi=[])

        grado_recluta = db("SELECT id FROM gradi WHERE ordine = 0", fetch="one")

        utente_id = db(
            "INSERT INTO utenti (telegram_id, nome, username, stato, grado_id) VALUES (%s,%s,%s,%s,%s)",
            (
                int(telegram_id) if telegram_id else None,
                request.form["nome"],
                request.form.get("username") or None,
                "recluta",
                grado_recluta["id"] if grado_recluta else None
            )
        )

        # Assegna automaticamente tutti i moduli obbligatori
        moduli_obbligatori = db(
            "SELECT id FROM moduli WHERE obbligatorio = TRUE AND attivo = TRUE",
            fetch="all"
        )
        for m in moduli_obbligatori:
            db(
                "INSERT IGNORE INTO reclute_moduli (utente_id, modulo_id, stato) VALUES (%s,%s,'non_completato')",
                (utente_id, m["id"])
            )

        flash("Utente creato.")
        return redirect(url_for("utenti"))

    return render_template("utenti_form.html", utente=None, gradi=[])

@app.route("/utenti/<int:id>/modifica", methods=["GET","POST"])
def utenti_modifica(id):
    gradi = db("SELECT * FROM gradi ORDER BY ordine", fetch="all")
    utente = db("SELECT * FROM utenti WHERE id = %s", (id,), fetch="one")
    permessi = db("SELECT permesso FROM utenti_permessi WHERE utente_id = %s", (id,), fetch="all")
    is_istruttore = any(p["permesso"] == "istruttore" for p in permessi)
    is_admin = any(p["permesso"] == "admin" for p in permessi)

    if request.method == "POST":
        telegram_id = request.form.get("telegram_id", "").strip()
        if telegram_id and not telegram_id.isdigit():
            flash("Errore: il Telegram ID deve essere un numero intero.")
            return render_template("utenti_form.html", utente=utente, gradi=gradi, is_istruttore=is_istruttore)
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

        if request.form.get("is_istruttore"):
            db("INSERT IGNORE INTO utenti_permessi (utente_id, permesso) VALUES (%s, 'istruttore')", (id,))
        else:
            db("DELETE FROM utenti_permessi WHERE utente_id = %s AND permesso = 'istruttore'", (id,))

        if request.form.get("is_admin"):
            db("INSERT IGNORE INTO utenti_permessi (utente_id, permesso) VALUES (%s, 'admin')", (id,))
        else:
            db("DELETE FROM utenti_permessi WHERE utente_id = %s AND permesso = 'admin'", (id,))

        from calcolo import ricalcola_utente, controlla_promozione_recluta
        run_calcolo(ricalcola_utente, id)
        run_calcolo(controlla_promozione_recluta, id)
        flash("Utente aggiornato.")
        return redirect(url_for("utenti"))
    return render_template("utenti_form.html", utente=utente, gradi=gradi, is_istruttore=is_istruttore, is_admin=is_admin)

@app.route("/utenti/<int:id>/promuovi", methods=["POST"])
def utenti_promuovi(id):
    utente = db("SELECT * FROM utenti WHERE id = %s AND stato = 'recluta'", (id,), fetch="one")
    if not utente or not utente["pronta_promozione"]:
        flash("Utente non idoneo alla promozione.")
        return redirect(url_for("utenti_dettaglio", id=id))

    grado_soldato = db("""
        SELECT id FROM gradi
        WHERE is_ufficiale = FALSE AND ordine > 0
        ORDER BY ordine ASC LIMIT 1
    """, fetch="one")

    db("UPDATE utenti SET stato = 'effettivo', grado_id = %s, pronta_promozione = FALSE WHERE id = %s",
       (grado_soldato["id"], id))

    from calcolo import ricalcola_utente
    run_calcolo(ricalcola_utente, id)

    flash(f"Utente promosso a effettivo con grado Soldato.")
    return redirect(url_for("utenti_dettaglio", id=id))

@app.route("/utenti/<int:id>/elimina", methods=["POST"])
def utenti_elimina(id):
    db("DELETE FROM reclute_moduli WHERE utente_id = %s", (id,))
    db("DELETE FROM utenti_ruoli WHERE utente_id = %s", (id,))
    db("DELETE FROM utenti_permessi WHERE utente_id = %s", (id,))
    db("DELETE FROM presenze WHERE utente_id = %s", (id,))
    db("DELETE FROM note WHERE utente_id = %s", (id,))
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

    moduli_utente = db("""
        SELECT rm.*, m.nome as modulo_nome, m.obbligatorio
        FROM reclute_moduli rm
        JOIN moduli m ON rm.modulo_id = m.id
        WHERE rm.utente_id = %s
        ORDER BY m.nome
    """, (id,), fetch="all")

    moduli_disponibili = db("""
        SELECT * FROM moduli
        WHERE attivo = TRUE
        AND id NOT IN (
            SELECT modulo_id FROM reclute_moduli WHERE utente_id = %s
        )
        ORDER BY nome
    """, (id,), fetch="all")


    return render_template("utenti_dettaglio.html",
        utente=utente,
        ruoli_utente=ruoli_utente,
        ruoli_disponibili=ruoli_disponibili,
        note_utente=note_utente,
	moduli_utente=moduli_utente,
	moduli_disponibili=moduli_disponibili
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

@app.route("/utenti/<int:id>/modulo/<int:modulo_id>/stato", methods=["POST"])
def utenti_modulo_stato(id, modulo_id):
    stato = request.form.get("stato")
    if stato in ("non_completato", "completato"):
        if stato == "completato":
            db("UPDATE reclute_moduli SET stato = %s, completato_il = NOW() WHERE utente_id = %s AND modulo_id = %s",
               (stato, id, modulo_id))
        else:
            db("UPDATE reclute_moduli SET stato = %s, completato_il = NULL WHERE utente_id = %s AND modulo_id = %s",
               (stato, id, modulo_id))
        from calcolo import controlla_promozione_recluta
        run_calcolo(controlla_promozione_recluta, id)
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
# ANNI DI GIOCO
# ============================================================

@app.route("/anni")
def anni():
    rows = db("SELECT * FROM anni_gioco ORDER BY data_inizio DESC", fetch="all")
    return render_template("anni.html", anni=rows)

@app.route("/anni/nuovo", methods=["GET","POST"])
def anni_nuovo():
    if request.method == "POST":
        db("INSERT INTO anni_gioco (nome, data_inizio, data_fine, attivo) VALUES (%s,%s,%s,%s)", (
            request.form["nome"],
            request.form["data_inizio"],
            request.form["data_fine"],
            1 if request.form.get("attivo") else 0
        ))
        flash("Anno di gioco creato.")
        return redirect(url_for("anni"))
    return render_template("anni_form.html", anno=None)

@app.route("/anni/<int:id>/modifica", methods=["GET","POST"])
def anni_modifica(id):
    anno = db("SELECT * FROM anni_gioco WHERE id = %s", (id,), fetch="one")
    if request.method == "POST":
        db("UPDATE anni_gioco SET nome=%s, data_inizio=%s, data_fine=%s, attivo=%s WHERE id=%s", (
            request.form["nome"],
            request.form["data_inizio"],
            request.form["data_fine"],
            1 if request.form.get("attivo") else 0,
            id
        ))
        flash("Anno di gioco aggiornato.")
        return redirect(url_for("anni"))
    return render_template("anni_form.html", anno=anno)

@app.route("/anni/<int:id>/elimina", methods=["POST"])
def anni_elimina(id):
    # Elimina in cascata: presenze → partite → anno
    partite_anno = db("SELECT id FROM partite WHERE anno_gioco_id = %s", (id,), fetch="all")
    for p in partite_anno:
        db("DELETE FROM presenze WHERE partita_id = %s", (p["id"],))
    db("DELETE FROM partite WHERE anno_gioco_id = %s", (id,))
    db("DELETE FROM anni_gioco WHERE id = %s", (id,))
    flash("Anno eliminato.")
    return redirect(url_for("anni"))


# ============================================================
# PARTITE
# ============================================================

@app.route("/partite")
def partite():
    rows = db("""
        SELECT p.*, a.nome as anno_nome
        FROM partite p
        JOIN anni_gioco a ON p.anno_gioco_id = a.id
        ORDER BY p.data_ora DESC
    """, fetch="all")
    return render_template("partite.html", partite=rows)

@app.route("/partite/nuova", methods=["GET","POST"])
def partite_nuova():
    anni = db("SELECT * FROM anni_gioco ORDER BY data_inizio DESC", fetch="all")
    if request.method == "POST":
        db("INSERT INTO partite (nome, data_ora, anno_gioco_id, is_addestramento) VALUES (%s,%s,%s,%s)", (
            request.form["nome"],
            request.form["data_ora"],
            request.form["anno_gioco_id"],
            1 if request.form.get("is_addestramento") else 0
        ))
        flash("Partita creata.")
        return redirect(url_for("partite"))
    return render_template("partite_form.html", partita=None, anni=anni)

@app.route("/partite/<int:id>/modifica", methods=["GET","POST"])
def partite_modifica(id):
    anni   = db("SELECT * FROM anni_gioco ORDER BY data_inizio DESC", fetch="all")
    partita = db("SELECT * FROM partite WHERE id = %s", (id,), fetch="one")
    if request.method == "POST":
        db("UPDATE partite SET nome=%s, data_ora=%s, anno_gioco_id=%s, is_addestramento=%s WHERE id=%s", (
            request.form["nome"],
            request.form["data_ora"],
            request.form["anno_gioco_id"],
            1 if request.form.get("is_addestramento") else 0,
            id
        ))
        flash("Partita aggiornata.")
        return redirect(url_for("partite"))
    return render_template("partite_form.html", partita=partita, anni=anni)

@app.route("/partite/<int:id>/elimina", methods=["POST"])
def partite_elimina(id):
    db("DELETE FROM presenze WHERE partita_id = %s", (id,))
    db("DELETE FROM partite WHERE id = %s", (id,))
    flash("Partita eliminata.")
    return redirect(url_for("partite"))


# ============================================================
# PRESENZE
# ============================================================

@app.route("/partite/<int:id>/presenze")
def partite_presenze(id):
    partita = db("SELECT * FROM partite WHERE id = %s", (id,), fetch="one")
    if not partita:
        flash("Partita non trovata.")
        return redirect(url_for("partite"))

    presenze = db("""
        SELECT u.id, u.nome, u.username,
               COALESCE(p.presente, FALSE) as presente
        FROM utenti u
        LEFT JOIN presenze p ON p.utente_id = u.id AND p.partita_id = %s
        WHERE u.stato = 'effettivo' OR u.stato = 'recluta'
        ORDER BY u.nome
    """, (id,), fetch="all")

    return render_template("partite_presenze.html", partita=partita, presenze=presenze)

@app.route("/partite/<int:id>/presenze/salva", methods=["POST"])
def partite_presenze_salva(id):
    effettivi = db("SELECT id FROM utenti WHERE stato IN ('effettivo', 'recluta')", fetch="all")
    presenti  = request.form.getlist("presenti")

    for u in effettivi:
        uid      = u["id"]
        presente = 1 if str(uid) in presenti else 0
        db("""
            INSERT INTO presenze (partita_id, utente_id, presente)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE presente = VALUES(presente)
        """, (id, uid, presente))

    from calcolo import ricalcola_utente, controlla_promozione_recluta
    for u in effettivi:
        utente = db("SELECT stato FROM utenti WHERE id = %s", (u["id"],), fetch="one")
        if utente["stato"] == "recluta":
            run_calcolo(controlla_promozione_recluta, u["id"])
        else:
            run_calcolo(ricalcola_utente, u["id"])

    flash("Presenze salvate.")
    return redirect(url_for("partite_presenze", id=id))

# ============================================================
# TIPI SONDAGGIO E DOMANDE
# ============================================================

@app.route("/sondaggi")
def sondaggi():
    rows = db("SELECT * FROM tipi_sondaggio ORDER BY nome", fetch="all")
    return render_template("sondaggi.html", tipi=rows)

@app.route("/sondaggi/nuovo", methods=["GET","POST"])
def sondaggi_nuovo():
    if request.method == "POST":
        db("INSERT INTO tipi_sondaggio (nome, descrizione) VALUES (%s,%s)", (
            request.form["nome"],
            request.form.get("descrizione") or None
        ))
        flash("Tipo sondaggio creato.")
        return redirect(url_for("sondaggi"))
    return render_template("sondaggi_form.html", tipo=None)

@app.route("/sondaggi/<int:id>/elimina", methods=["POST"])
def sondaggi_elimina(id):
    db("DELETE FROM domande WHERE tipo_sondaggio_id = %s", (id,))
    db("DELETE FROM tipi_sondaggio WHERE id = %s", (id,))
    flash("Tipo sondaggio eliminato.")
    return redirect(url_for("sondaggi"))

@app.route("/sondaggi/<int:id>/domande")
def sondaggi_domande(id):
    tipo   = db("SELECT * FROM tipi_sondaggio WHERE id = %s", (id,), fetch="one")
    domande = db("SELECT * FROM domande WHERE tipo_sondaggio_id = %s ORDER BY ordine", (id,), fetch="all")
    return render_template("sondaggi_domande.html", tipo=tipo, domande=domande)

@app.route("/sondaggi/<int:id>/domande/nuova", methods=["POST"])
def domande_nuova(id):
    testo = request.form.get("testo", "").strip()
    if testo:
        ultima = db("SELECT MAX(ordine) as m FROM domande WHERE tipo_sondaggio_id = %s", (id,), fetch="one")
        ordine = (ultima["m"] or 0) + 1
        db("INSERT INTO domande (tipo_sondaggio_id, testo, ordine, attiva) VALUES (%s,%s,%s,TRUE)", (id, testo, ordine))
        flash("Domanda aggiunta.")
    return redirect(url_for("sondaggi_domande", id=id))

@app.route("/sondaggi/<int:id>/domande/<int:domanda_id>/elimina", methods=["POST"])
def domande_elimina(id, domanda_id):
    db("DELETE FROM domande WHERE id = %s AND tipo_sondaggio_id = %s", (domanda_id, id))
    flash("Domanda eliminata.")
    return redirect(url_for("sondaggi_domande", id=id))

@app.route("/sondaggi/<int:id>/domande/<int:domanda_id>/toggle", methods=["POST"])
def domande_toggle(id, domanda_id):
    domanda = db("SELECT attiva FROM domande WHERE id = %s", (domanda_id,), fetch="one")
    nuovo_stato = 0 if domanda["attiva"] else 1
    db("UPDATE domande SET attiva = %s WHERE id = %s", (nuovo_stato, domanda_id))
    return redirect(url_for("sondaggi_domande", id=id))


# ============================================================
# AVVIO
# ============================================================

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
