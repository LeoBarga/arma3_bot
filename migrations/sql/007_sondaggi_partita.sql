-- 007_sondaggi_partita.sql
ALTER TABLE sondaggi ADD COLUMN partita_id INT NULL AFTER tipo_sondaggio_id;
ALTER TABLE sondaggi ADD FOREIGN KEY (partita_id) REFERENCES partite(id);
