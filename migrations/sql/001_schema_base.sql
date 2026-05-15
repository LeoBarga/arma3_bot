CREATE TABLE gradi (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nome VARCHAR(100) NOT NULL,
    ordine TINYINT NOT NULL UNIQUE,
    grado_id_formula INT NOT NULL UNIQUE,
    is_ufficiale BOOLEAN DEFAULT FALSE,
    punteggio_minimo INT NOT NULL DEFAULT 0
);

CREATE TABLE utenti (
    id INT AUTO_INCREMENT PRIMARY KEY,
    telegram_id BIGINT UNIQUE,
    nome VARCHAR(100) NOT NULL,
    username VARCHAR(100),
    stato ENUM('recluta','effettivo','inattivo') DEFAULT 'recluta',
    grado_id INT NULL,
    autonomia DECIMAL(3,1) DEFAULT 1.0,
    leadership DECIMAL(3,1) DEFAULT 1.0,
    pianificazione DECIMAL(3,1) DEFAULT 1.0,
    punteggio INT DEFAULT 0,
    creato_il DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (grado_id) REFERENCES gradi(id)
);

CREATE TABLE utenti_permessi (
    utente_id INT NOT NULL,
    permesso ENUM('admin','istruttore') NOT NULL,
    PRIMARY KEY (utente_id, permesso),
    FOREIGN KEY (utente_id) REFERENCES utenti(id)
);

CREATE TABLE ruoli (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nome VARCHAR(100) NOT NULL,
    descrizione TEXT,
    grado_minimo_id INT NULL,
    is_sl BOOLEAN DEFAULT FALSE,
    attivo BOOLEAN DEFAULT TRUE,
    FOREIGN KEY (grado_minimo_id) REFERENCES gradi(id)
);

CREATE TABLE utenti_ruoli (
    id INT AUTO_INCREMENT PRIMARY KEY,
    utente_id INT NOT NULL,
    ruolo_id INT NOT NULL,
    stato ENUM('non_acquisito','in_corso','ottenuto') DEFAULT 'non_acquisito',
    aggiornato_da INT NULL,
    aggiornato_il DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY unico_ruolo (utente_id, ruolo_id),
    FOREIGN KEY (utente_id) REFERENCES utenti(id),
    FOREIGN KEY (ruolo_id) REFERENCES ruoli(id),
    FOREIGN KEY (aggiornato_da) REFERENCES utenti(id)
);

CREATE TABLE moduli (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nome VARCHAR(150) NOT NULL,
    descrizione TEXT,
    obbligatorio BOOLEAN DEFAULT TRUE,
    attivo BOOLEAN DEFAULT TRUE
);

CREATE TABLE reclute_moduli (
    id INT AUTO_INCREMENT PRIMARY KEY,
    utente_id INT NOT NULL,
    modulo_id INT NOT NULL,
    stato ENUM('non_completato','completato') DEFAULT 'non_completato',
    completato_il DATETIME NULL,
    aggiornato_da INT NULL,
    UNIQUE KEY unico_modulo (utente_id, modulo_id),
    FOREIGN KEY (utente_id) REFERENCES utenti(id),
    FOREIGN KEY (modulo_id) REFERENCES moduli(id),
    FOREIGN KEY (aggiornato_da) REFERENCES utenti(id)
);

CREATE TABLE anni_gioco (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nome VARCHAR(20) NOT NULL,
    data_inizio DATE NOT NULL,
    data_fine DATE NOT NULL,
    attivo BOOLEAN DEFAULT FALSE
);

CREATE TABLE partite (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nome VARCHAR(150) NOT NULL,
    data_ora DATETIME NOT NULL,
    anno_gioco_id INT NOT NULL,
    is_addestramento BOOLEAN DEFAULT FALSE,
    creato_da INT NULL,
    creato_il DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (anno_gioco_id) REFERENCES anni_gioco(id),
    FOREIGN KEY (creato_da) REFERENCES utenti(id)
);

CREATE TABLE presenze (
    id INT AUTO_INCREMENT PRIMARY KEY,
    partita_id INT NOT NULL,
    utente_id INT NOT NULL,
    presente BOOLEAN DEFAULT FALSE,
    inserito_da INT NULL,
    UNIQUE KEY unica_presenza (partita_id, utente_id),
    FOREIGN KEY (partita_id) REFERENCES partite(id),
    FOREIGN KEY (utente_id) REFERENCES utenti(id),
    FOREIGN KEY (inserito_da) REFERENCES utenti(id)
);

CREATE TABLE squadre (
    id INT AUTO_INCREMENT PRIMARY KEY,
    partita_id INT NOT NULL,
    nome VARCHAR(100) NOT NULL,
    FOREIGN KEY (partita_id) REFERENCES partite(id)
);

CREATE TABLE squadre_membri (
    id INT AUTO_INCREMENT PRIMARY KEY,
    squadra_id INT NOT NULL,
    utente_id INT NOT NULL,
    ruolo_id INT NULL,
    UNIQUE KEY unico_membro (squadra_id, utente_id),
    FOREIGN KEY (squadra_id) REFERENCES squadre(id),
    FOREIGN KEY (utente_id) REFERENCES utenti(id),
    FOREIGN KEY (ruolo_id) REFERENCES ruoli(id)
);

CREATE TABLE note (
    id INT AUTO_INCREMENT PRIMARY KEY,
    utente_id INT NOT NULL,
    tipo ENUM('merito','demerito') NOT NULL,
    testo TEXT NOT NULL,
    inserito_da INT NULL,
    inserito_il DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (utente_id) REFERENCES utenti(id),
    FOREIGN KEY (inserito_da) REFERENCES utenti(id)
);

CREATE TABLE tipi_sondaggio (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nome VARCHAR(100) NOT NULL,
    descrizione TEXT,
    attivo BOOLEAN DEFAULT TRUE
);

CREATE TABLE domande (
    id INT AUTO_INCREMENT PRIMARY KEY,
    tipo_sondaggio_id INT NOT NULL,
    testo TEXT NOT NULL,
    ordine TINYINT NOT NULL,
    tipo_risposta ENUM('scala','testo','booleano') DEFAULT 'scala',
    scala_min TINYINT DEFAULT 1,
    scala_max TINYINT DEFAULT 10,
    attiva BOOLEAN DEFAULT TRUE,
    FOREIGN KEY (tipo_sondaggio_id) REFERENCES tipi_sondaggio(id)
);

CREATE TABLE sondaggi (
    id INT AUTO_INCREMENT PRIMARY KEY,
    tipo_sondaggio_id INT NOT NULL,
    nome VARCHAR(150) NOT NULL,
    schedulata_il DATETIME NULL,
    aperta_il DATETIME NULL,
    chiusa_il DATETIME NULL,
    attiva BOOLEAN DEFAULT FALSE,
    archiviata BOOLEAN DEFAULT FALSE,
    archiviata_il DATETIME NULL,
    creato_da INT NULL,
    FOREIGN KEY (tipo_sondaggio_id) REFERENCES tipi_sondaggio(id),
    FOREIGN KEY (creato_da) REFERENCES utenti(id)
);

CREATE TABLE risposte (
    id INT AUTO_INCREMENT PRIMARY KEY,
    sondaggio_id INT NOT NULL,
    votante_id INT NOT NULL,
    soggetto_id INT NULL,
    completata BOOLEAN DEFAULT FALSE,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY unico_voto (sondaggio_id, votante_id, soggetto_id),
    FOREIGN KEY (sondaggio_id) REFERENCES sondaggi(id),
    FOREIGN KEY (votante_id) REFERENCES utenti(id),
    FOREIGN KEY (soggetto_id) REFERENCES utenti(id)
);

CREATE TABLE risposte_dettaglio (
    id INT AUTO_INCREMENT PRIMARY KEY,
    risposta_id INT NOT NULL,
    domanda_id INT NOT NULL,
    valore_scala TINYINT NULL,
    valore_testo TEXT NULL,
    FOREIGN KEY (risposta_id) REFERENCES risposte(id),
    FOREIGN KEY (domanda_id) REFERENCES domande(id)
);

CREATE TABLE log_eventi (
    id INT AUTO_INCREMENT PRIMARY KEY,
    tipo VARCHAR(50) NOT NULL,
    utente_id INT NULL,
    dettaglio TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (utente_id) REFERENCES utenti(id)
);
