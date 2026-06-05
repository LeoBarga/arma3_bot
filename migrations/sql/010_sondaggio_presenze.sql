-- 010_sondaggio_presenze.sql
CREATE TABLE sondaggi_presenze (
    id INT AUTO_INCREMENT PRIMARY KEY,
    partita_id INT NOT NULL,
    topic_id INT NOT NULL,
    messaggio_lista_id INT NOT NULL,
    messaggio_bottoni_id INT NOT NULL,
    aperto BOOLEAN DEFAULT TRUE,
    creato_il DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (partita_id) REFERENCES partite(id)
);

CREATE TABLE voti_presenze (
    id INT AUTO_INCREMENT PRIMARY KEY,
    sondaggio_id INT NOT NULL,
    utente_id INT NOT NULL,
    voto ENUM('presente','assente','forse') NOT NULL,
    in_ritardo BOOLEAN DEFAULT FALSE,
    votato_il DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY unico_voto (sondaggio_id, utente_id),
    FOREIGN KEY (sondaggio_id) REFERENCES sondaggi_presenze(id),
    FOREIGN KEY (utente_id) REFERENCES utenti(id)
);
