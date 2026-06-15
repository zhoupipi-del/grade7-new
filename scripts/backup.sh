#!/bin/bash
# ── grade7-new 数据库自动备份脚本 ──
# 调用: /opt/grade7-new/backup.sh
# Cron: 0 3 * * * /opt/grade7-new/backup.sh >> /var/log/grade7-backup.log 2>&1

BACKUP_DIR=/opt/grade7-new/backups
DB_NAME=grade7_new
DB_USER=grade7
DB_PASS="waOPKoyFf4ByQD1h"
DB_PORT=3307
RETENTION_DAYS=7
DATE=$(date +%Y%m%d_%H%M)

mkdir -p "$BACKUP_DIR/monthly"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting backup of $DB_NAME..."

mysqldump -h 127.0.0.1 -P $DB_PORT -u$DB_USER -p"$DB_PASS" \
    --single-transaction --routines --triggers $DB_NAME 2>/tmp/mysqldump_err.log \
    | gzip > "$BACKUP_DIR/${DB_NAME}_${DATE}.sql.gz"

if [ ${PIPESTATUS[0]} -eq 0 ]; then
    SIZE=$(du -h "$BACKUP_DIR/${DB_NAME}_${DATE}.sql.gz" | cut -f1)
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Backup OK: ${DB_NAME}_${DATE}.sql.gz ($SIZE)"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Backup FAILED! See /tmp/mysqldump_err.log"
    cat /tmp/mysqldump_err.log 2>/dev/null
    exit 1
fi

# 每月1号保留月备
if [ "$(date +%d)" = "01" ]; then
    cp "$BACKUP_DIR/${DB_NAME}_${DATE}.sql.gz" "$BACKUP_DIR/monthly/${DB_NAME}_$(date +%Y%m).sql.gz"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Monthly backup saved"
fi

# 清理超过 RETENTION_DAYS 天的旧备份
DELETED=$(find "$BACKUP_DIR" -name "${DB_NAME}_*.sql.gz" -mtime +$RETENTION_DAYS -print -delete 2>/dev/null | wc -l)
if [ "$DELETED" -gt 0 ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Cleaned $DELETED old backup(s)"
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Done."
