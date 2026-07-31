"""
W3-BE-RBAC-002 审计隔离库 schema 初始化。

背景:
  alembic baseline(2d8813121d03) 是针对已有 Wings 3.1 库的 autogenerate 增量
  (首条 DDL 即 DROP INDEX ... ON workload_logs)，在空库上无法执行。
  生产实践同样是 create_all + alembic stamp head。

本脚本:
  1. 关闭 FOREIGN_KEY_CHECKS(仅本连接)，规避 growth_timeline_events.student_id(Integer)
     与 students.id(BigInteger) 的类型不兼容缺陷 —— 该缺陷单独登记，本脚本不改代码。
  2. Base.metadata.create_all 建全部 108 张表。
  3. 打印表数量供核对。

不打印任何凭据。
"""

import asyncio
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_DIR))

if not os.environ.get("DATABASE_URL"):
    sys.exit("[FATAL] 必须显式设置 DATABASE_URL（指向隔离库）")

db_name = os.environ["DATABASE_URL"].rsplit("/", 1)[-1]
if db_name != "wings3_audit_test":
    sys.exit(f"[ABORT] 安全闸: 目标库必须是 wings3_audit_test，当前={db_name}")

import importlib  # noqa: E402

from core.models import Base  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402

# 与 alembic/env.py 完全一致的模块 model 加载方式
_modules_dir = BACKEND_DIR / "modules"
_loaded, _skipped = 0, []
for module_dir in sorted(_modules_dir.iterdir()):
    if not (module_dir / "models.py").is_file():
        continue
    try:
        importlib.import_module(f"modules.{module_dir.name}.models")
        _loaded += 1
    except Exception as e:  # noqa: BLE001
        _skipped.append((module_dir.name, str(e)))
print(f"[schema] 已加载 {_loaded} 个模块 models, 跳过 {len(_skipped)}")
for m, e in _skipped:
    print(f"  [SKIP] {m}: {e}")


def strip_mismatched_fks() -> list[str]:
    """
    剥离“列类型与被引用列类型不一致”的外键约束（仅作用于内存中的 metadata，
    不修改任何源码）。MySQL errno 3780 在 FOREIGN_KEY_CHECKS=0 下仍会报错，
    因此必须在 DDL 生成前处理。返回不匹配清单，作为独立 Finding 的证据。
    """
    report: list[str] = []
    for table in Base.metadata.tables.values():
        for fkc in list(table.foreign_key_constraints):
            bad = []
            for el in fkc.elements:
                local, target = el.parent, el.column
                lt, tt = type(local.type).__name__, type(target.type).__name__
                if lt != tt:
                    bad.append(
                        f"{table.name}.{local.name}({lt}) -> {target.table.name}.{target.name}({tt})"
                    )
            if bad:
                report.extend(bad)
                table.constraints.discard(fkc)
                for el in fkc.elements:
                    el.parent.foreign_keys.discard(el)
    return report


async def main() -> None:
    print(f"[schema] Base.metadata 表数: {len(Base.metadata.tables)}")
    mismatches = strip_mismatched_fks()
    print(f"[schema] 类型不匹配外键数: {len(mismatches)}  (已在本次建表中剥离, 源码未改)")
    for m in mismatches:
        print(f"  [FK-MISMATCH] {m}")
    engine = create_async_engine(os.environ["DATABASE_URL"], echo=False)
    async with engine.begin() as conn:
        await conn.execute(text("SET FOREIGN_KEY_CHECKS=0"))
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("SET FOREIGN_KEY_CHECKS=1"))
    async with engine.connect() as conn:
        res = await conn.execute(
            text("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = :s"),
            {"s": db_name},
        )
        print(f"[schema] {db_name} 实际建表数: {res.scalar()}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
