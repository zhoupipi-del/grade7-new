#!/bin/bash
# 梨江中学德育系统 - 数据库备份脚本
# 备份 grade7_new (旧Flask) + wings3 (新FastAPI)

BACKUP_DIR=/root/backend/backups
DB_PORT=3307
RETENTION_DAYS=7
DATE=$(date +%Y%m%d_%H%M)

# Source .env for DB credentials
set -a
source /root/backend/.env 2>/dev/null
set +a

# Extract password from DATABASE_URL
DB_PASS=$(echo "$DATABASE_URL" | sed -n 's|.*://grade7:\([^@]*\)@.*|\1|p')

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting backup..."

# Backup grade7_new (old Flask DB)
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Backing up grade7_new..."
mysqldump -h 127.0.0.1 -P $DB_PORT -ugrade7 -p"$DB_PASS" --single-transaction --routines --triggers grade7_new | gzip > "$BACKUP_DIR/grade7_new_${DATE}.sql.gz"
if [ $? -eq 0 ]; then
    SIZE=$(du -h "$BACKUP_DIR/grade7_new_${DATE}.sql.gz" | cut -f1)
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] grade7_new OK: grade7_new_${DATE}.sql.gz ($SIZE)"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] grade7_new FAILED!"
fi

# Backup wings3 (new FastAPI DB)
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Backing up wings3..."
mysqldump -h 127.0.0.1 -P $DB_PORT -ugrade7 -p"$DB_PASS" --single-transaction --routines --triggers wings3 | gzip > "$BACKUP_DIR/wings3_${DATE}.sql.gz"
if [ $? -eq 0 ]; then
    SIZE=$(du -h "$BACKUP_DIR/wings3_${DATE}.sql.gz" | cut -f1)
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] wings3 OK: wings3_${DATE}.sql.gz ($SIZE)"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] wings3 FAILED!"
fi

# Cleanup old backups
find "$BACKUP_DIR" -name "*.sql.gz" -mtime +$RETENTION_DAYS -delete 2>/dev/null

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Done."
