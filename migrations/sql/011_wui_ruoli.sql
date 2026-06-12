-- 011_wui_ruoli.sql
ALTER TABLE wui_utenti ADD COLUMN ruolo ENUM('admin','config') DEFAULT 'admin';
