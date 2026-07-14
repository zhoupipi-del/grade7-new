#!/usr/bin/env python3
"""Execute DDL for homework_mgmt and error_funnel modules"""

import pymysql
from core.db_utils import require_db_url

_DB_URL = require_db_url()
# 解析 DATABASE_URL: mysql+aiomysql://user:password@host:port/db
_url_clean = _DB_URL.replace("mysql+aiomysql://", "").replace("mysql+pymysql://", "")
_creds, _rest = _url_clean.rsplit("@", 1) if "@" in _url_clean else ("grade7:", _url_clean)
_user, _pass = _creds.split(":", 1) if ":" in _creds else ("grade7", "")
_host_port, _db = _rest.split("/", 1) if "/" in _rest else (_rest, "wings3")
_host, _port = _host_port.split(":", 1) if ":" in _host_port else (_host_port, "3307")

conn = pymysql.connect(
    host=_host,
    port=int(_port),
    user=_user,
    password=_pass,
    database=_db.split("?")[0],
    charset="utf8mb4",
)
cur = conn.cursor()


def execute_sql_file(filepath):
    """Execute a SQL file, properly handling comments and multi-line statements"""
    with open(filepath) as f:
        content = f.read()

    # Remove comment lines (-- ...) but keep the actual SQL
    lines = content.split("\n")
    sql_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("--"):
            continue
        sql_lines.append(line)

    sql = "\n".join(sql_lines)

    # Split by semicolon and execute each non-empty statement
    for stmt in sql.split(";"):
        s = stmt.strip()
        if s:
            cur.execute(s)
            print(f"  executed: {s[:80]}...")

    conn.commit()


# ── homework_mgmt DDL ──
print("=== homework_mgmt DDL ===")
execute_sql_file("modules/homework_mgmt/homework_mgmt_ddl.sql")
print("homework_mgmt DDL OK")

# ── error_funnel DDL ──
print("\n=== error_funnel DDL ===")
execute_sql_file("modules/error_funnel/error_funnel_ddl.sql")
print("error_funnel DDL OK")

# ── school_modules ──
cur.execute(
    "INSERT INTO school_modules (school_id, module_code, enabled) "
    "VALUES (1,%s,1),(1,%s,1) ON DUPLICATE KEY UPDATE enabled=1",
    ("homework_mgmt", "error_funnel"),
)
conn.commit()
print("school_modules OK")

# ── verify ──
cur.execute("SHOW TABLES")
all_tables = [r[0] for r in cur.fetchall()]
hw = [t for t in all_tables if t.startswith("hw_")]
kp = [t for t in all_tables if t.startswith("knowledge_")]
eb = [t for t in all_tables if t.startswith("error_book")]
print(f"\nhw tables: {hw}")
print(f"knowledge tables: {kp}")
print(f"error_book tables: {eb}")
print(f"total tables: {len(all_tables)}")

cur.execute(
    "SELECT module_code, enabled FROM school_modules WHERE module_code IN ('homework_mgmt','error_funnel')"
)
for r in cur.fetchall():
    print(f"  module: {r[0]} enabled={r[1]}")

conn.close()
print("\nALL DONE")
