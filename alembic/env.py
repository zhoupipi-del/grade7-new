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

# ═══════════════════════════════════════════════════════════════
#  AI Native Control Plane — ai_native/models/*.py 单独扫描
#  （ai_native 在仓库根，不在 modules/ 下；§0-E/B0 §6：绿地包）
#  ★ B1 FAIL-CLOSE：AI Native 是 frozen N Models，任何 import 失败 /
#    数量 ≠ N 必须 STOP，不允许像旧 modules/* 那样 skip 后继续。
#  ★ 冻结基线更新（CF-05 Batch A，2026-08-16）：
#    frozen 9 → frozen 10 —— 新增 AIProvenanceRecord（ai_provenance_records，
#    CF-05 AI 业务产物溯源 Registry）。这是合法受控新增，非残缺 schema。
# ═══════════════════════════════════════════════════════════════
_AI_NATIVE_FROZEN_MODELS = 10  # CF-05 Batch A: 9 -> 10
_ai_native_models_dir = BACKEND_ROOT / "ai_native" / "models"
_ai_native_loaded = 0
if not _ai_native_models_dir.is_dir():
    raise RuntimeError(
        "[B1 FAIL-CLOSE] ai_native/models/ 目录缺失；frozen 10 Models 必须存在"
    )

_ai_native_errors: list[tuple[str, str]] = []
try:
    # 先 import ai_native 根包（确保子包路径可解析）
    importlib.import_module("ai_native")
    for models_file in sorted(_ai_native_models_dir.glob("*.py")):
        if models_file.name == "__init__.py":
            continue
        module_name = f"ai_native.models.{models_file.stem}"
        try:
            importlib.import_module(module_name)
            _ai_native_loaded += 1
        except Exception as e:
            _ai_native_errors.append((module_name, str(e)))
except Exception as e:
    _ai_native_errors.append(("ai_native", str(e)))

if _ai_native_errors:
    raise RuntimeError(
        "[B1 FAIL-CLOSE] ai_native.models 导入失败，必须 STOP：\n"
        + "\n".join(f"  {mod}: {err}" for mod, err in _ai_native_errors)
    )
if _ai_native_loaded != _AI_NATIVE_FROZEN_MODELS:
    raise RuntimeError(
        f"[B1 FAIL-CLOSE] AI Native frozen {_AI_NATIVE_FROZEN_MODELS} Models，实际加载 {_ai_native_loaded} 个；"
        f"必须 {_AI_NATIVE_FROZEN_MODELS}/{_AI_NATIVE_FROZEN_MODELS}，禁止带残缺 schema 迁移"
    )

print(
    f"[alembic-env] 已加载 {_loaded_count} 个业务模块的 models"
    + f" + {_ai_native_loaded} 个 ai_native 模型"
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
