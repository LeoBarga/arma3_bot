#!/bin/bash

# Configurazione
DB_USER="arma3user"
DB_PASSWORD="la_tua_password"
DB_NAME="arma3_bot"
BACKUP_DIR="/home/mailtest/arma3_bot/backups"
RETENTION_DAYS=30

# Crea la cartella se non esiste
mkdir -p "$BACKUP_DIR"

# Nome file con data e ora
FILENAME="$BACKUP_DIR/backup_$(date +%Y%m%d_%H%M).sql.gz"

# Esegui il dump e comprimi
mysqldump -u "$DB_USER" -p"$DB_PASSWORD" \
    --single-transaction \
    --quick \
    --lock-tables=false \
    "$DB_NAME" | gzip > "$FILENAME"

# Verifica che il backup sia andato a buon fine
if [ $? -eq 0 ]; then
    echo "$(date): Backup completato — $FILENAME"
else
    echo "$(date): ERRORE nel backup"
    exit 1
fi

# Elimina i backup più vecchi di 30 giorni
find "$BACKUP_DIR" -name "backup_*.sql.gz" -mtime +$RETENTION_DAYS -delete
echo "$(date): Pulizia backup vecchi completata"
