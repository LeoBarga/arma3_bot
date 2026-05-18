-- 003_aggiungi_tag_utente.sql
ALTER TABLE utenti ADD COLUMN tag ENUM('promuovibile','degradabile') NULL DEFAULT NULL;
