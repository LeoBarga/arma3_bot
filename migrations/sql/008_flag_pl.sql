-- 008_flag_pl.sql
ALTER TABLE ruoli ADD COLUMN is_pl BOOLEAN DEFAULT FALSE;
UPDATE ruoli SET is_pl = TRUE WHERE nome = 'Comandante di Plotone';
