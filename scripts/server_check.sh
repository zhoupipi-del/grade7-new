#!/bin/bash
echo "=== GUNICORN CONFIG ==="
cat /etc/systemd/system/grade7-new.service
echo ""
echo "=== CONNECTION POOL ==="
grep -n 'pool_pre_ping\|pool_recycle\|pool_size\|SQLALCHEMY_ENGINE' /opt/grade7-new/config.py
echo ""
echo "=== MYSQL STATUS ==="
mysql -h 127.0.0.1 -P 3307 -ugrade7 -p'waOPKoyFf4ByQD1h' grade7_new -e "
SHOW STATUS LIKE 'Slow_queries';
SHOW STATUS LIKE 'Questions';
SHOW STATUS LIKE 'Threads_connected';
"
echo ""
echo "=== MEMORY ==="
free -h
echo ""
echo "=== TOP PROCESSES ==="
ps aux --sort=-%mem | head -6
