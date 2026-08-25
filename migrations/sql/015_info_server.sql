-- 015_info_server.sql
CREATE TABLE info_server (
    id INT AUTO_INCREMENT PRIMARY KEY,
    chiave VARCHAR(100) NOT NULL UNIQUE,
    valore TEXT NOT NULL DEFAULT '',
    descrizione VARCHAR(200)
);

INSERT INTO info_server (chiave, valore, descrizione) VALUES
('Indirizzo', '', 'IP e porta del server (es. 192.168.0.1:2302)'),
('Password',  '', 'Password del server');
