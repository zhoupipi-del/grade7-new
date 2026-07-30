"""W3-BE-RBAC-002 补丁后"同租户不误杀"验证数据播种

R2-b 给 detect_escalation_trigger 加了 school_id 硬过滤。必须证明:
  - 跨租户读取被挡住(已由 _probe_xt_http.py 覆盖)
  - 【同租户】的正常滑窗判定不受影响, 仍能命中 3次/30天 红线

本脚本给 school_id=1 的既有合成学生补 3 条 30 天内严重违纪, 打 AUDIT_TEST_ST 标记,
--cleanup 一键删除。只允许在隔离库 wings3_audit_test 运行。

用法:
  python _probe_same_tenant_seed.py <student_id>
  python _probe_same_tenant_seed.py --cleanup
"""

import argparse
import asyncio
import importlib
import os
import pathlib
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ST_TAG = "AUDIT_TEST_ST"


def _load_dotenv_min():
    p = pathlib.Path(".env")
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("student_id", nargs="?", type=int)
    parser.add_argument("--cleanup", action="store_true")
    args = parser.parse_args()

    url = os.environ.get("DATABASE_URL", "")
    if not url:
        _load_dotenv_min()
        url = os.environ.get("DATABASE_URL", "")

    # ── 安全闸门 ──
    if not url.endswith("/wings3_audit_test"):
        print("FATAL: DATABASE_URL 未指向隔离库 wings3_audit_test,拒绝执行", file=sys.stderr)
        sys.exit(2)

    from sqlalchemy import delete, select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    modules_dir = pathlib.Path("modules")
    for sub in sorted(modules_dir.iterdir()):
        if sub.is_dir() and (sub / "models.py").exists():
            try:
                importlib.import_module(f"modules.{sub.name}.models")
            except Exception:  # noqa: BLE001
                pass

    from core.models import Student, User
    from modules.behavior.models import DisciplineRecord
    from modules.discipline.models import DisciplineSanction, DisciplineStatus

    engine = create_async_engine(url, echo=False, pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as db:
        if args.cleanup:
            # 顺序要求: discipline_sanctions.behavior_record_id 外键引用 discipline_records,
            # 必须先删草稿再删违纪记录, 否则 MySQL 1451。
            # 1) Hook 孵化出的自动草稿(仅 DRAFT_PENDING + auto_generated + 滑窗事由)
            res2 = await db.execute(
                delete(DisciplineSanction).where(
                    DisciplineSanction.auto_generated == True,  # noqa: E712
                    DisciplineSanction.status == DisciplineStatus.DRAFT_PENDING,
                    DisciplineSanction.reason.like("%30天滑窗自动触发%"),
                )
            )
            removed_drafts = res2.rowcount or 0

            # 2) 本轮播种的严重违纪(ST) + Hook 链路回归违纪(HOOK)
            # 含 BehaviorService._check_escalation 派生出的"累计扣分自动升级"记录
            res = await db.execute(
                delete(DisciplineRecord).where(
                    DisciplineRecord.description.like(f"{ST_TAG}%")
                    | DisciplineRecord.description.like("AUDIT_TEST_HOOK%")
                    | DisciplineRecord.description.like("[累计扣分自动升级]%")
                )
            )
            removed_records = res.rowcount or 0
            await db.commit()
            print(f"ST_CLEANUP_DONE records={removed_records} auto_drafts={removed_drafts}")
            await engine.dispose()
            return

        await db.execute(
            delete(DisciplineRecord).where(DisciplineRecord.description.like(f"{ST_TAG}%"))
        )
        await db.commit()

        if not args.student_id:
            print("FATAL: 需提供 student_id", file=sys.stderr)
            sys.exit(3)

        student = await db.scalar(select(Student).where(Student.id == args.student_id))
        if student is None:
            print(f"FATAL: student_id={args.student_id} 不存在", file=sys.stderr)
            sys.exit(4)

        creator = (
            await db.execute(select(User).where(User.username == "audit_ms_admin"))
        ).scalar_one_or_none()
        if creator is None:
            print("FATAL: 未找到 audit_ms_admin", file=sys.stderr)
            sys.exit(5)

        today = date.today()
        for i, delta in enumerate([1, 7, 15]):
            db.add(
                DisciplineRecord(
                    school_id=student.school_id,
                    student_id=student.id,
                    class_id=student.class_id,
                    grade_id=student.grade_id,
                    type="serious",
                    category="合成类别",
                    description=f"{ST_TAG}_本校严重违纪_{i + 1}",
                    points=10,
                    status="active",
                    verify_status="VERIFIED",
                    created_by=creator.id,
                    incident_date=today - timedelta(days=delta),
                )
            )
        await db.commit()
        print(f"ST_SEED_OK school_id={student.school_id} student_id={student.id} records=3")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
