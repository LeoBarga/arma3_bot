# Arma3 Bot

Bot Telegram per la gestione della comunità: sondaggi, presenze, ruoli e progressione dei giocatori.

---

# Requisiti

- Python 3.12+
- MariaDB 10.6+
- Un bot Telegram creato tramite `@BotFather`

---

# Struttura del progetto

```text
arma3_bot/
├── handlers/
│   ├── __init__.py
│   ├── admin.py
│   ├── sondaggio.py
│   └── risultati.py
├── migrations/
│   ├── run_migrations.py
│   └── sql/
│       └── 001_schema_base.sql
├── .env
├── .env.example
├── .gitignore
├── config.py
├── db.py
├── main.py
├── scheduler.py
└── README.md
```

---

# Setup

## 1. Clona il repository e crea l'ambiente virtuale

```bash
git clone <url_repo>
cd arma3_bot

python3 -m venv venv
source venv/bin/activate
```

---

## 2. Installa le dipendenze

```bash
pip install python-telegram-bot aiomysql apscheduler python-dotenv
```

---

## 3. Crea il file `.env`

Copia il file di esempio e compilalo:

```bash
cp .env.example .env
nano .env
```

Contenuto del file `.env`:

```env
BOT_TOKEN=il_tuo_token_telegram

DB_HOST=localhost
DB_PORT=3306
DB_NAME=arma3_bot
DB_USER=arma3user
DB_PASSWORD=la_tua_password
```

---

## 4. Crea il database su MariaDB

Accedi a MariaDB come root:

```bash
sudo mysql -u root -p
```

Esegui questi comandi:

```sql
CREATE DATABASE arma3_bot
CHARACTER SET utf8mb4
COLLATE utf8mb4_unicode_ci;

CREATE USER 'arma3user'@'localhost'
IDENTIFIED BY 'la_tua_password';

GRANT ALL PRIVILEGES
ON arma3_bot.*
TO 'arma3user'@'localhost';

FLUSH PRIVILEGES;
EXIT;
```

---

## 5. Imposta il timezone di sistema

```bash
sudo timedatectl set-timezone Europe/Rome
sudo systemctl restart mariadb
```

---

## 6. Esegui le migrazioni

```bash
python migrations/run_migrations.py
```

Lo script:

- legge i file SQL in ordine dalla cartella `migrations/sql/`
- tiene traccia delle migrazioni già applicate
- esegue solo quelle mancanti

Per aggiungere modifiche future al database, crea un nuovo file SQL numerato:

```text
002_nuova_feature.sql
```

Poi riesegui lo script.

---

## 7. Inserisci i dati iniziali

Accedi al database e inserisci il tuo utente admin.

Il `telegram_id` lo trovi scrivendo `/start` al bot `@userinfobot` su Telegram.

Connessione al database:

```bash
mysql -u arma3user -p arma3_bot
```

Inserimento dati:

```sql
INSERT INTO utenti (telegram_id, nome, stato)
VALUES (IL_TUO_TELEGRAM_ID, 'Admin', 'effettivo');

SET @uid = LAST_INSERT_ID();

INSERT INTO utenti_permessi (utente_id, permesso)
VALUES (@uid, 'admin');
```

---

## 8. Avvia il bot

```bash
python main.py
```

---

# Aggiungere una migrazione

Per ogni modifica al database crea un nuovo file nella cartella:

```text
migrations/sql/
```

Esempio:

```bash
nano migrations/sql/002_nome_feature.sql
```

Successivamente esegui:

```bash
python migrations/run_migrations.py
```

Lo script applica automaticamente solo le migrazioni non ancora eseguite, in ordine progressivo.
