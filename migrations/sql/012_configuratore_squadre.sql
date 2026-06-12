-- 012_configuratore_squadre.sql
CREATE TABLE configurazioni (
    id INT AUTO_INCREMENT PRIMARY KEY,
    partita_id INT NOT NULL,
    creato_il DATETIME DEFAULT CURRENT_TIMESTAMP,
    aggiornato_il DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (partita_id) REFERENCES partite(id)
);

CREATE TABLE squadre_config (
    id INT AUTO_INCREMENT PRIMARY KEY,
    configurazione_id INT NOT NULL,
    nome VARCHAR(100) NOT NULL,
    callsign VARCHAR(100),
    radio VARCHAR(100),
    mezzo VARCHAR(100),
    note TEXT,
    ordine TINYINT DEFAULT 0,
    FOREIGN KEY (configurazione_id) REFERENCES configurazioni(id)
);

CREATE TABLE squadre_config_membri (
    id INT AUTO_INCREMENT PRIMARY KEY,
    squadra_id INT NOT NULL,
    utente_id INT NOT NULL,
    ruolo_id INT NULL,
    UNIQUE KEY unico_membro (squadra_id, utente_id),
    FOREIGN KEY (squadra_id) REFERENCES squadre_config(id),
    FOREIGN KEY (utente_id) REFERENCES utenti(id),
    FOREIGN KEY (ruolo_id) REFERENCES ruoli(id)
);
