ALTER TABLE tipi_sondaggio ADD COLUMN target ENUM('sl','pl','tutti') DEFAULT 'tutti';
UPDATE tipi_sondaggio SET target = 'sl' WHERE nome = 'Valutazione SL';
INSERT INTO tipi_sondaggio (nome, descrizione, target, attivo) 
VALUES ('Valutazione PL', 'Valutazione dei Comandanti di Plotone', 'pl', TRUE);
