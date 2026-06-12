-- 013_colori_configuratore.sql
ALTER TABLE squadre_config ADD COLUMN colore VARCHAR(20) DEFAULT 'bianco';
ALTER TABLE squadre_config_membri ADD COLUMN colore VARCHAR(20) DEFAULT 'bianco';
ALTER TABLE squadre_config_membri ADD COLUMN ordine INT DEFAULT 0;
