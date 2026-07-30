#!/usr/bin/env bash
# W3-BE-RBAC-002 审计专用实例启动器
# 约束: 只用隔离库 wings3_audit_test + 隔离 Redis(6380); 任何密钥不打印
set -u
cd "$(dirname "$0")"

SECRETS_FILE="C:/Users/Administrator/.wings3_audit_secrets.env"
if [ ! -f "$SECRETS_FILE" ]; then
  echo "FATAL: 审计密钥文件缺失: $SECRETS_FILE" >&2
  exit 1
fi

export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8
export APP_ENV=audit_test

# 隔离数据库 — 绝不使用 Flask 旧库 grade7_new
export DATABASE_URL="$(grep '^DATABASE_URL=' .env | cut -d= -f2- | sed 's|/grade7_new|/wings3_audit_test|')"
case "$DATABASE_URL" in
  */wings3_audit_test) ;;
  *) echo "FATAL: DATABASE_URL 未指向隔离库，拒绝启动" >&2; exit 2 ;;
esac

# 审计密钥(仓库外注入，不回显)
export WEBHOOK_SECRET="$(grep '^WEBHOOK_SECRET=' "$SECRETS_FILE" | cut -d= -f2-)"
export REDIS_PASSWORD="$(grep '^REDIS_PASSWORD=' "$SECRETS_FILE" | cut -d= -f2-)"

# 隔离 Redis 7 容器(Windows 本机 Redis 3.0.504 不支持 RESP3 HELLO)
export REDIS_HOST=127.0.0.1
export REDIS_PORT=6380
export REDIS_EVENT_DB=1

exec ./.venv/Scripts/python.exe -m uvicorn app:app --host 127.0.0.1 --port 8000 --log-level info
