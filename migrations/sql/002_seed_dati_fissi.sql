-- 002_seed_dati_fissi.sql

-- GRADI
INSERT INTO gradi (nome, ordine, grado_id_formula, is_ufficiale, punteggio_minimo) VALUES
('Recluta',                0,  0,  FALSE, 0),
('Soldato',                1,  1,  FALSE, 0),
('Caporale',               2,  2,  FALSE, 0),
('Caporal Maggiore',       3,  3,  FALSE, 0),
('Graduato',               4,  4,  FALSE, 0),
('Graduato Capo',          5,  6,  FALSE, 0),
('Graduato Aiutante',      6,  8,  FALSE, 0),
('Sergente',               7,  9,  TRUE,  0),
('Sergente Maggiore Capo', 8,  11, TRUE,  0),
('Maresciallo',            9,  13, TRUE,  0),
('Primo Maresciallo',      10, 16, TRUE,  0),
('Tenente',                11, 20, TRUE,  0),
('Capitano',               12, 21, TRUE,  0),
('Tenente Colonnello',     13, 24, TRUE,  0),
('Colonnello',             14, 26, TRUE,  0);

-- RUOLI
-- grado_minimo_id: Soldato ha ordine 1, sarà id=2 dopo l'insert dei gradi
-- Sergente ha ordine 7, sarà id=8
-- Usiamo subquery per non dipendere dagli id fisici

INSERT INTO ruoli (nome, is_sl, grado_minimo_id, attivo) VALUES
('Geniere',                         FALSE, (SELECT id FROM gradi WHERE nome = 'Soldato'), TRUE),
('Fuciliere AT/AA',                 FALSE, (SELECT id FROM gradi WHERE nome = 'Soldato'), TRUE),
('Soccorritore Militare',           FALSE, (SELECT id FROM gradi WHERE nome = 'Soldato'), TRUE),
('Medico',                          FALSE, (SELECT id FROM gradi WHERE nome = 'Soldato'), TRUE),
('Operatore UAV (quadrirotore)',     FALSE, (SELECT id FROM gradi WHERE nome = 'Soldato'), TRUE),
('Operatore UAV (ala fissa)',        FALSE, (SELECT id FROM gradi WHERE nome = 'Soldato'), TRUE),
('Carrista',                        FALSE, (SELECT id FROM gradi WHERE nome = 'Soldato'), TRUE),
('Mortaista',                       FALSE, (SELECT id FROM gradi WHERE nome = 'Soldato'), TRUE),
('Radiofonista',                    FALSE, (SELECT id FROM gradi WHERE nome = 'Soldato'), TRUE),
('Brevetto Aviotrasporto',          FALSE, (SELECT id FROM gradi WHERE nome = 'Soldato'), TRUE),
('Brevetto SCUBA',                  FALSE, (SELECT id FROM gradi WHERE nome = 'Soldato'), TRUE),
('Brevetto Pattugliatore Scelto',   FALSE, (SELECT id FROM gradi WHERE nome = 'Soldato'), TRUE),
('JTAC',                            FALSE, (SELECT id FROM gradi WHERE nome = 'Soldato'), TRUE),
('Pilota ala rotante da trasporto', FALSE, (SELECT id FROM gradi WHERE nome = 'Soldato'), TRUE),
('Pilota ala rotante da attacco',   FALSE, (SELECT id FROM gradi WHERE nome = 'Soldato'), TRUE),
('Tiratore Scelto',                 FALSE, (SELECT id FROM gradi WHERE nome = 'Soldato'), TRUE),
('Pilota ala fissa',                FALSE, (SELECT id FROM gradi WHERE nome = 'Soldato'), TRUE),
('Comandante di Squadra',           TRUE,  (SELECT id FROM gradi WHERE nome = 'Sergente'), TRUE),
('Comandante di Plotone',           FALSE, (SELECT id FROM gradi WHERE nome = 'Sergente'), TRUE);
