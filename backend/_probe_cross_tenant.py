"""
W3-BE-RBAC-002 追加取证 — R2-b 跨租户越权动态验证

目的:
  静态审查发现 DisciplineService.detect_escalation_trigger(db, student_id) 的
  SQL WHERE 子句只按 student_id 过滤,完全没有 school_id 条件,
  违反项目既定"多租户双保险"约定。本脚本在隔离库中构造一个
  【属于另一所学校】的合成学生 + 3 条严重违纪记录,
  用于验证 school_id=1 的低权限账号能否读到该外校学生的铁证快照。

约束(与主播种器一致):
  1. 只允许在隔离库 wings3_audit_test 上运行
  2. 全部合成数据,AUDIT_TEST 前缀标记
  3. --cleanup 一键删除本脚本创建的全部对象(含外校)

用法:
  python _probe_cross_tenant.py           # 播种外校数据,打印 student_id
  python _probe_cross_tenant.py --cleanup # 删除外校数据
"""

import argparse
import asyncio
import importlib
import os
import pathlib
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

XT_TAG = "AUDIT_TEST_XT"  # cross-tenant 专用标记,便于与主合成数据区分


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

    from core.models import Class, Grade, School, Student, User
    from modules.behavior.models import DisciplineRecord

    engine = create_async_engine(url, echo=False, pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as db:
        # ═══════════ 清理路径(播种前也复用) ═══════════
        sres = await db.execute(select(Student).where(Student.name.like(f"{XT_TAG}%")))
        xt_students = [s.id for s in sres.scalars().all()]
        if xt_students:
            await db.execute(
                delete(DisciplineRecord).where(DisciplineRecord.student_id.in_(xt_students))
            )
            await db.execute(delete(Student).where(Student.id.in_(xt_students)))
        await db.execute(delete(Class).where(Class.name.like(f"{XT_TAG}%")))
        await db.execute(delete(Grade).where(Grade.name.like(f"{XT_TAG}%")))
        await db.execute(delete(School).where(School.name.like(f"{XT_TAG}%")))
        await db.commit()

        if args.cleanup:
            print(f"XT_CLEANUP_DONE: students={len(xt_students)}")
            await engine.dispose()
            return

        # ═══════════ 播种外校 ═══════════
        creator = (
            await db.execute(select(User).where(User.username == "audit_ms_admin"))
        ).scalar_one_or_none()
        if creator is None:
            print("FATAL: 未找到 audit_ms_admin,请先运行 _seed_audit_accounts.py", file=sys.stderr)
            sys.exit(3)

        xt_school = School(name=f"{XT_TAG}_外校", school_phase="junior", is_active=True)
        db.add(xt_school)
        await db.flush()

        xt_grade = Grade(name=f"{XT_TAG}_外校年级", school_id=xt_school.id, sort_order=990)
        db.add(xt_grade)
        await db.flush()

        xt_class = Class(name=f"{XT_TAG}_外校班", school_id=xt_school.id, grade_id=xt_grade.id)
        db.add(xt_class)
        await db.flush()

        xt_student = Student(
            name=f"{XT_TAG}_外校学生",
            student_no=f"{XT_TAG}-001",
            school_id=xt_school.id,
            class_id=xt_class.id,
            grade_id=xt_grade.id,
        )
        db.add(xt_student)
        await db.flush()

        # 3 条 30 天内严重违纪 → 恰好触发升级红线
        today = date.today()
        for i, delta in enumerate([2, 9, 20]):
            db.add(
                DisciplineRecord(
                    school_id=xt_school.id,
                    student_id=xt_student.id,
                    class_id=xt_class.id,
                    grade_id=xt_grade.id,
                    type="serious",
                    category="合成类别",
                    description=f"{XT_TAG}_外校敏感违纪明细_{i + 1}",
                    points=10,
                    status="active",
                    verify_status="VERIFIED",
                    created_by=creator.id,
                    incident_date=today - timedelta(days=delta),
                )
            )
        await db.commit()

        print(f"XT_SEED_OK school_id={xt_school.id} student_id={xt_student.id}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
