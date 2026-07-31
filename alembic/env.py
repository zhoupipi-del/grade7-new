"""
Alembic 迁移环境配置 — Wings 3.2

核心设计:
  1. 从 DATABASE_URL 环境变量读取数据库连接 (复用 db_utils.py 安全策略)
  2. 动态加载所有 33 个模块的 models.py，确保 autogenerate 能检测全部表结构
  3. 支持 online (命令行) 和 offline (SQL 生成) 两种迁移模式
"""

import importlib
import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# ═══════════════════════════════════════════════════════════════
#  路径准备 — 将 backend/ 加入 sys.path
# ═══════════════════════════════════════════════════════════════

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

# ═══════════════════════════════════════════════════════════════
#  Alembic 配置
# ═══════════════════════════════════════════════════════════════

config = context.config

# 日志配置
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ═══════════════════════════════════════════════════════════════
#  数据库 URL — 从环境变量注入 (安全策略: 禁止硬编码)
# ═══════════════════════════════════════════════════════════════

db_url = os.environ.get("DATABASE_URL")
if not db_url:
    # Alembic 使用同步驱动，将 aiomysql 替换为 pymysql
    print(
        "\n[FATAL] DATABASE_URL 环境变量未设置",
        "\n请在 .env 文件或 shell 环境中配置:",
        '\n  export DATABASE_URL="mysql+aiomysql://user:password@host:port/dbname"',
        "\n",
        file=sys.stderr,
    )
    sys.exit(1)

# Alembic 使用同步引擎，将 aiomysql → pymysql
sync_url = db_url.replace("mysql+aiomysql://", "mysql+pymysql://")
config.set_main_option("sqlalchemy.url", sync_url)

# ═══════════════════════════════════════════════════════════════
#  动态加载所有模块的 Model — 确保 Base.metadata 包含全部表
# ═══════════════════════════════════════════════════════════════

from core.models import Base  # noqa: E402

target_metadata = Base.metadata

# 自动扫描 modules/*/models.py 并导入
_modules_dir = BACKEND_ROOT / "modules"
_loaded_count = 0
_skipped = []

for module_dir in sorted(_modules_dir.iterdir()):
    models_file = module_dir / "models.py"
    if not models_file.is_file():
        continue
    module_name = f"modules.{module_dir.name}.models"
    try:
        importlib.import_module(module_name)
        _loaded_count += 1
    except Exception as e:
        _skipped.append((module_name, str(e)))

print(
    f"[alembic-env] 已加载 {_loaded_count} 个模块的 models"
    + (f", 跳过 {len(_skipped)} 个有错误的模块" if _skipped else "")
)

for mod, err in _skipped:
    print(f"  [SKIP] {mod}: {err}")

# 确认 metadata 中的表数量
table_count = len(target_metadata.tables)
print(f"[alembic-env] Base.metadata 包含 {table_count} 张表")


# ═══════════════════════════════════════════════════════════════
#  迁移函数
# ═══════════════════════════════════════════════════════════════


def run_migrations_offline() -> None:
    """离线模式: 生成 SQL 脚本而不连接数据库"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式: 连接数据库执行迁移"""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
