# Arma3 Bot — Sistema Gestionale per Comunità Gaming

Sistema completo per la gestione di una comunità gaming su ArmA3: bot Telegram,
pannello di amministrazione web e configuratore squadre.

## Requisiti

- Python 3.12+
- MariaDB 10.6+
- Un bot Telegram (creato via @BotFather)
- Un supergroup Telegram con Forum mode attiva (per i topic delle serate)
- Un gruppo admin Telegram separato (da cui lanciare i comandi)

## Struttura del progetto

```
arma3_bot/
├── handlers/
│   ├── __init__.py
│   ├── admin.py          # /start, /stato, registrazione automatica
│   ├── sondaggio.py      # sondaggi SL/PL, /valuta, /apri_sondaggio, /chiudi_sondaggio
│   └── presenze.py       # /crea serata, gestione voti presenze
├── migrations/
│   ├── run_migrations.py
│   └── sql/              # file SQL numerati progressivamente
├── scripts/
│   └── backup.sh         # script backup automatico
├── wui/
│   ├── app.py            # Flask WUI
│   └── templates/        # HTML templates
├── calcolo.py            # formula punteggio e promozioni reclute
├── config.py             # variabili d'ambiente
├── db.py                 # pool aiomysql, tutte le query async
├── main.py               # avvio bot, registrazione handler
├── scheduler.py          # APScheduler: sondaggi, pulizia serate
├── .env                  # credenziali (non nel repo)
├── .env.example          # template credenziali
├── .gitignore
└── requirements.txt
```

## Setup iniziale

### 1. Clona il repository e crea l'ambiente virtuale
```
git clone <url_repo>
cd arma3_bot
python3 -m venv venv
source venv/bin/activate
```

### 2. Installa le dipendenze
```
pip install -r requirements.txt
```

### 3. Crea il file .env
```
cp .env.example .env
nano .env
```

Contenuto del file .env:
```
BOT_TOKEN=il_tuo_token_da_botfather
DB_HOST=localhost
DB_PORT=3306
DB_NAME=arma3_bot
DB_USER=arma3user
DB_PASSWORD=la_tua_password
GRUPPO_ID=-100xxxxxxxxxx
SECRET_KEY=stringa_casuale_lunga
```

Per generare SECRET_KEY:
```
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Per trovare GRUPPO_ID: aggiungi il bot al gruppo principale, scrivi qualcosa
e cerca nei log la riga "Chat ID: ..." dopo aver aggiunto il log in
registra_da_gruppo, oppure usa @userinfobot nel gruppo.

### 4. Imposta il timezone di sistema
```
sudo timedatectl set-timezone Europe/Rome
sudo systemctl restart mariadb
```

### 5. Crea il database su MariaDB
```
sudo mysql -u root -p

CREATE DATABASE arma3_bot CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'arma3user'@'localhost' IDENTIFIED BY 'la_tua_password';
GRANT ALL PRIVILEGES ON arma3_bot.* TO 'arma3user'@'localhost';
FLUSH PRIVILEGES;
EXIT;
```

### 6. Configura MariaDB per evitare corruzioni InnoDB
```
sudo nano /etc/mysql/mariadb.conf.d/50-server.cnf
```

Aggiungi nella sezione [mysqld]:
```
innodb_flush_log_at_trx_commit = 2
innodb_flush_method = O_DSYNC
```

```
sudo systemctl restart mariadb
```

### 7. Esegui le migrazioni
```
python migrations/run_migrations.py
```

### 8. Inserisci i dati iniziali nel DB
```
mysql -u arma3user -p arma3_bot
```

Utente admin principale:
```
INSERT INTO utenti (telegram_id, nome, username, stato, grado_id)
VALUES (IL_TUO_TELEGRAM_ID, 'Nome', 'NomeInGioco', 'effettivo',
        (SELECT id FROM gradi WHERE nome = 'Soldato'));
SET @uid = LAST_INSERT_ID();
INSERT INTO utenti_permessi (utente_id, permesso) VALUES (@uid, 'admin');
INSERT INTO utenti_permessi (utente_id, permesso) VALUES (@uid, 'istruttore');
```

Tipo sondaggio SL:
```
INSERT INTO tipi_sondaggio (nome, descrizione, target, attivo)
VALUES ('Valutazione SL', 'Valutazione degli Squad Leader', 'sl', TRUE);
```

Tipo sondaggio PL:
```
INSERT INTO tipi_sondaggio (nome, descrizione, target, attivo)
VALUES ('Valutazione PL', 'Valutazione dei Comandanti di Plotone', 'pl', TRUE);
```

Anno di gioco corrente (modifica le date):
```
INSERT INTO anni_gioco (nome, data_inizio, data_fine, attivo)
VALUES ('2025-2026', '2025-09-01', '2026-06-30', TRUE);
```

Info server (modifica i valori dalla WUI dopo il setup):
```
INSERT INTO info_server (chiave, valore, descrizione) VALUES
('Indirizzo ArmA3',     '', 'IP e porta del server ArmA3 (es. 192.168.0.1:2302)'),
('Password ArmA3',      '', 'Password del server ArmA3'),
('Indirizzo TeamSpeak', '', 'IP del server TeamSpeak'),
('Password TeamSpeak',  '', 'Password del server TeamSpeak');

EXIT;
```

### 9. Crea gli utenti WUI

Utente admin WUI:
```
python3 -c "
import bcrypt
password = input('Password per admin_wui: ').encode()
hash = bcrypt.hashpw(password, bcrypt.gensalt()).decode()
print(f\"INSERT INTO wui_utenti (username, password_hash, ruolo) VALUES ('admin_wui', '{hash}', 'admin');\")
"
```

Utente configuratore WUI:
```
python3 -c "
import bcrypt
password = input('Password per config_wui: ').encode()
hash = bcrypt.hashpw(password, bcrypt.gensalt()).decode()
print(f\"INSERT INTO wui_utenti (username, password_hash, ruolo) VALUES ('config_wui', '{hash}', 'config');\")
"
```

Esegui gli INSERT generati nel DB.

### 10. Configura BotFather

Vai su @BotFather e imposta i comandi con /setcommands:
```
start - Registrati o controlla il tuo stato
stato - Visualizza le tue informazioni
valuta - Compila un sondaggio di valutazione
indirizzi - Info per connettersi al server
apri_sondaggio - [ADMIN] Apri un nuovo sondaggio
chiudi_sondaggio - [ADMIN] Chiudi un sondaggio attivo
sondaggi - [ADMIN] Visualizza i sondaggi attivi
crea - [ADMIN] Crea una nuova serata nel gruppo
indirizzi - Info server TeamSpeak/ArmA
annulla - Annulla l'operazione in corso
```

### 11. Configura i gruppi Telegram

Gruppo principale (supergroup con Forum mode):
- Aggiungi il bot come amministratore
- Assicurati che abbia i permessi per gestire i topic

Gruppo admin:
- Aggiungi il bot come amministratore
- Il bot deve essere admin per leggere i messaggi (disabilita privacy mode da BotFather)
- Da questo gruppo vengono lanciati tutti i comandi admin

Eventuali altri gruppi (es. gruppo reclute):
- Aggiungi il bot come amministratore
- La registrazione automatica avviene per chiunque scriva nel gruppo

## Avvio

### Bot Telegram
```
cd arma3_bot
source venv/bin/activate
python main.py
```

### WUI (pannello admin)
```
cd arma3_bot
source venv/bin/activate
python wui/app.py
```

La WUI è accessibile su http://IP_SERVER:5000

## Utilizzo

### WUI — utente admin

Accesso completo a tutte le sezioni:

UTENTI
- Lista utenti con grado, punteggio e tag (promuovibile/degradabile)
- Dettaglio utente: modifica dati, assegna ruoli, inserisci note merito/demerito
- Per le reclute: gestione moduli, banner promozione quando i requisiti sono soddisfatti
- Promozione manuale da recluta a effettivo quando tutti i requisiti sono soddisfatti
- Campi: Nome Telegram (automatico), Nome in gioco (da modificare manualmente),
  Autonomia/Leadership/Pianificazione (1.0-1.5), flag Istruttore, flag Admin bot

GRADI
- Gestione gradi con punteggio minimo modificabile
- Il grado viene assegnato manualmente — il sistema calcola solo il punteggio e il tag

RUOLI
- Gestione ruoli con grado minimo richiesto
- Flag is_sl (bonus 30pt nel calcolo) e is_pl

MODULI
- Gestione moduli reclute (obbligatori e facoltativi)

ANNI DI GIOCO
- Gestione anni settembre-giugno, uno solo attivo per volta

PARTITE
- Gestione partite con flag addestramento
- Sezione presenze per segnare chi era effettivamente presente
  (separata dai voti Telegram)

SONDAGGI
- Gestione tipi sondaggio e relative domande

SERVER
- Modifica indirizzo e password di ArmA3 e TeamSpeak
- I valori aggiornati vengono mostrati agli utenti tramite /indirizzi

CONFIGURATORE SQUADRE
- Accessibile anche dall'utente config
- Seleziona una partita con sondaggio presenze aperto
- Crea squadre con: nome, callsign, radio, mezzo, note, colore
- Aggiungi membri tra i giocatori che hanno votato "presente" nel sondaggio Telegram
- Assegna ruolo e sottoruolo (R/RI/C/TL/SL/TL/C/SL/C) per ogni membro
- Riordina i membri con drag&drop
- Barra comandabilità colorata basata sulla media dei grado_id_formula
- Genera riepilogo testuale con emoji colorate da copiare nel gruppo

### Bot Telegram — comandi admin (dal gruppo admin)

/apri_sondaggio
  Flusso: scelta Standard (SL, 1h, ultima partita) o Personalizzato
  Personalizzato: tipo sondaggio → partita → apertura (adesso/schedulata) →
  chiusura (manuale/N ore/data e ora)
  Il sondaggio viene inviato automaticamente a tutti gli effettivi presenti
  alla partita selezionata.

/chiudi_sondaggio
  Mostra lista sondaggi attivi come bottoni, chiude quello selezionato
  e invia i risultati agli SL/PL valutati.

/sondaggi
  Lista sondaggi attivi con partita, orari apertura/chiusura e numero risposte.

/crea
  Crea una nuova serata:
  1. Tipo: Interna / Addestramento / Multiclan
  2. Nome della serata
  3. Data (bottoni con navigazione per giorni successivi)
  4. Conferma
  Crea automaticamente un topic nel gruppo principale con formato:
  "GG/MM/YYYY - Serata [Tipo] - [Nome]"
  Nel topic appaiono: lista presenze aggiornata in tempo reale + bottoni voto

### Bot Telegram — comandi privati (in chat privata con il bot)

/start
  Registrazione automatica come recluta.
  Assegna automaticamente tutti i moduli obbligatori.

/stato
  Recluta: moduli completati e partite effettuate, banner se pronto per promozione
  Effettivo: grado attuale

/valuta
  Disponibile solo per gli effettivi presenti alla partita del sondaggio attivo.
  Mostra un messaggio con bottoni per ogni SL/PL da valutare.
  Gli SL non possono votare se stessi.
  Per i sondaggi PL, solo gli SL possono votare.

/indirizzi
  Mostra indirizzo e password di ArmA3 e TeamSpeak.
  Disponibile in qualsiasi chat dove il bot è presente.

### Sondaggio presenze (topic nel gruppo principale)

- Tre bottoni: Presente / Forse / Assente
- La lista si aggiorna in tempo reale ad ogni voto
- Flag [R] accanto al nome per chi vota dopo le 18:00 del giorno della partita
- Voto bloccato dopo le 21:00 del giorno della partita
- Lista mostra: grado in monospace + nome in gioco, flag ritardo
- Ordinamento per grado decrescente all'interno di ogni categoria

## Manutenzione

### Aggiungere una migrazione DB
```
nano migrations/sql/XXX_nome_migrazione.sql
python migrations/run_migrations.py
```

### Backup manuale
```
mysqldump -u arma3user -p --single-transaction arma3_bot > backup_$(date +%Y%m%d).sql
```

### Backup automatico

Lo script `scripts/backup.sh` esegue il backup ogni notte, comprime il file e
rimuove i backup più vecchi di 30 giorni. Per attivarlo aggiungi il cron:
```
crontab -e
```

Aggiungi questa riga:
```
0 2 * * * /home/mailtest/arma3_bot/scripts/backup.sh >> /home/mailtest/arma3_bot/scripts/backup.log 2>&1
```

Per testare lo script manualmente:
```
~/arma3_bot/scripts/backup.sh
ls ~/arma3_bot/backups/
```

### Cambio password WUI
```
python3 -c "
import bcrypt
password = input('Nuova password: ').encode()
hash = bcrypt.hashpw(password, bcrypt.gensalt()).decode()
print(f\"UPDATE wui_utenti SET password_hash='{hash}' WHERE username='admin_wui';\")
"
```

Esegui l'UPDATE nel DB.

### Se MariaDB non si avvia (corruzione InnoDB)
```
sudo nano /etc/mysql/mariadb.conf.d/50-server.cnf
```

Aggiungi nella sezione [mysqld] (aumenta il valore fino a 6 se necessario):
```
innodb_force_recovery = 1
```

```
sudo systemctl start mariadb
```

Fai subito il backup:
```
mysqldump -u arma3user -p --single-transaction --quick --lock-tables=false arma3_bot > backup_recovery_$(date +%Y%m%d).sql
```

Poi rimuovi `innodb_force_recovery` e riavvia MariaDB.

## Prossimi sviluppi pianificati

1. Nginx + HTTPS per esporre la WUI su dominio pubblico tramite reverse proxy,
   con certificato SSL tramite Let's Encrypt. Il server usa già nginx con SSL
   attivo per il sito WordPress esistente.

2. Import dati storici da Excel (punteggi, presenze, gradi pregressi dei giocatori
   esistenti prima dell'adozione del sistema).

3. Avvio automatico tramite systemd — creare due service unit (bot e WUI) per
   garantire il riavvio automatico dopo un reboot del server.

## File .gitignore

```
venv/
.venv/
.env
__pycache__/
*.py[cod]
*.pyo
*.log
.vscode/
.idea/
*.swp
*.swo
.DS_Store
Thumbs.db
backups/
```

## File .env.example

```
BOT_TOKEN=
DB_HOST=localhost
DB_PORT=3306
DB_NAME=arma3_bot
DB_USER=
DB_PASSWORD=
GRUPPO_ID=
SECRET_KEY=
```
