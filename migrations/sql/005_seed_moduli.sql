-- 005_seed_moduli.sql
INSERT INTO moduli (nome, descrizione, obbligatorio, attivo) VALUES
('Corso Base',                          'Requisito base, introduzione ad ArmA3 e alla Brigata', TRUE, TRUE),
('Modulo Topografia Base',              'Utilizzo della mappa e di altri strumenti in dotazione come bussola e binocolo', TRUE, TRUE),
('Modulo Movimento Tattico',            'Introduzione alle formazioni e al movimento di squadra con coperture, ritmi di movimento e attraversamenti pericolosi', TRUE, TRUE),
('Modulo Primo Soccorso',               'Primo soccorso su se stessi e sugli altri per fucilieri base', TRUE, TRUE),
('Modulo Comunicazioni',                'Principi di impiego, utilizzo corretto e parole di procedure per le comunicazioni via radio', TRUE, TRUE),
('Modulo Maneggio Armi',                'Utilizzo dei fucili ARX-160 e 200, della Minimi, della MG, del lanciatore M136 e delle cariche a disposizione del fuciliere', TRUE, TRUE),
('Modulo Riconoscimento e Impiego Mezzi', 'Comandi base sui veicoli, il loro utilizzo corretto in vari contesti e riconoscimento mezzi', TRUE, TRUE);
