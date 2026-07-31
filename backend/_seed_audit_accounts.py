"""
W3-BE-RBAC-002 审计合成数据播种器

约束(遵循审计要求):
  1. 只允许在隔离库 wings3_audit_test 上运行,检测到其它库立即中止
  2. 全部为合成数据,无任何真实学生/家长/处分/心理数据
  3. 账号统一 audit_ 前缀 + display_name 带 AUDIT_TEST 标记,便于清理
  4. 随机临时口令,只写入仓库外凭据文件,不打印、不入日志、不进 Git
  5. 支持 --cleanup 一键删除全部合成数据

用法:
  python _seed_audit_accounts.py            # 播种
  python _seed_audit_accounts.py --cleanup  # 清理
"""

import argparse
import asyncio
import json
import os
import pathlib
import secrets
import string
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

CREDS_FILE = pathlib.Path("C:/Users/Administrator/.wings3_audit_accounts.json")
AUDIT_PREFIX = "audit_"
AUDIT_TAG = "AUDIT_TEST"


def _load_dotenv_min():
    """只补齐未定义的环境变量,与 app.py 行为一致"""
    p = pathlib.Path(".env")
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


def _resolve_db_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        _load_dotenv_min()
        url = os.environ.get("DATABASE_URL", "")
    return url


def _gen_password() -> str:
    """生成满足强度策略的随机临时口令(>=16位, 4类字符)"""
    alpha = string.ascii_lowercase
    upper = string.ascii_uppercase
    digit = string.digits
    sym = "!@#$%^&*-_=+"
    pool = alpha + upper + digit + sym
    while True:
        pw = "".join(secrets.choice(pool) for _ in range(18))
        if (
            any(c in alpha for c in pw)
            and any(c in upper for c in pw)
            and any(c in digit for c in pw)
            and any(c in sym for c in pw)
        ):
            return pw


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cleanup", action="store_true", help="删除全部合成数据")
    args = parser.parse_args()

    db_url = _resolve_db_url()
    # ── 安全闸门 ──
    if not db_url.endswith("/wings3_audit_test"):
        print("FATAL: DATABASE_URL 未指向隔离库 wings3_audit_test,拒绝执行", file=sys.stderr)
        print(f"       当前目标库尾段: ...{db_url.rsplit('/', 1)[-1] if '/' in db_url else '?'}")
        sys.exit(2)

    # 先注册全部模块 ORM 映射(与 alembic/env.py 一致),否则跨模块 relationship 解析失败
    import importlib

    from sqlalchemy import delete, select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    modules_dir = pathlib.Path("modules")
    for sub in sorted(modules_dir.iterdir()):
        if sub.is_dir() and (sub / "models.py").exists():
            try:
                importlib.import_module(f"modules.{sub.name}.models")
            except Exception:  # noqa: BLE001 — 缺失依赖的模块跳过,不影响本次播种
                pass

    from core.models import Branch, Class, Grade, Organization, School, Student, User
    from core.services import AuthService
    from modules.discipline.models import DisciplineLevel, DisciplineSanction, DisciplineStatus

    engine = create_async_engine(db_url, echo=False, pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as db:
        # ═══════════ 清理路径 ═══════════
        if args.cleanup:
            sres = await db.execute(select(Student).where(Student.name.like(f"{AUDIT_TAG}%")))
            student_ids = [s.id for s in sres.scalars().all()]
            if student_ids:
                await db.execute(
                    delete(DisciplineSanction).where(DisciplineSanction.student_id.in_(student_ids))
                )
            await db.execute(delete(User).where(User.username.like(f"{AUDIT_PREFIX}%")))
            if student_ids:
                await db.execute(delete(Student).where(Student.id.in_(student_ids)))
            await db.execute(delete(Class).where(Class.name.like(f"{AUDIT_TAG}%")))
            await db.execute(delete(Grade).where(Grade.name.like(f"{AUDIT_TAG}%")))
            await db.commit()
            if CREDS_FILE.exists():
                CREDS_FILE.unlink()
            print(
                f"CLEANUP_DONE: 已删除合成账号/学生/班级/年级/处分记录 (students={len(student_ids)})"
            )
            await engine.dispose()
            return

        # ═══════════ 播种路径(先幂等清理) ═══════════
        sres = await db.execute(select(Student).where(Student.name.like(f"{AUDIT_TAG}%")))
        old_ids = [s.id for s in sres.scalars().all()]
        if old_ids:
            await db.execute(
                delete(DisciplineSanction).where(DisciplineSanction.student_id.in_(old_ids))
            )
        await db.execute(delete(User).where(User.username.like(f"{AUDIT_PREFIX}%")))
        if old_ids:
            await db.execute(delete(Student).where(Student.id.in_(old_ids)))
        await db.execute(delete(Class).where(Class.name.like(f"{AUDIT_TAG}%")))
        await db.execute(delete(Grade).where(Grade.name.like(f"{AUDIT_TAG}%")))
        await db.commit()

        # ── 组织架构(复用 bootstrap 创建的集团/片区/学校) ──
        school = (await db.execute(select(School).order_by(School.id))).scalars().first()
        if school is None:
            print("FATAL: 隔离库中无学校记录,请先启动一次后端完成 bootstrap", file=sys.stderr)
            sys.exit(3)
        org = (await db.execute(select(Organization).order_by(Organization.id))).scalars().first()
        branch = (await db.execute(select(Branch).order_by(Branch.id))).scalars().first()

        # ── 年级 A / B ──
        grade_a = Grade(name=f"{AUDIT_TAG}_年级A", school_id=school.id, sort_order=901)
        grade_b = Grade(name=f"{AUDIT_TAG}_年级B", school_id=school.id, sort_order=902)
        db.add_all([grade_a, grade_b])
        await db.flush()

        # ── 班级 A1 / A2(同属年级A) / B1(属年级B) ──
        cls_a1 = Class(name=f"{AUDIT_TAG}_班A1", school_id=school.id, grade_id=grade_a.id)
        cls_a2 = Class(name=f"{AUDIT_TAG}_班A2", school_id=school.id, grade_id=grade_a.id)
        cls_b1 = Class(name=f"{AUDIT_TAG}_班B1", school_id=school.id, grade_id=grade_b.id)
        db.add_all([cls_a1, cls_a2, cls_b1])
        await db.flush()

        # ── 学生 ──
        stu_a1 = Student(
            name=f"{AUDIT_TAG}_学生A1",
            student_no=f"{AUDIT_TAG}-A1",
            school_id=school.id,
            class_id=cls_a1.id,
            grade_id=grade_a.id,
        )
        stu_a2 = Student(
            name=f"{AUDIT_TAG}_学生A2",
            student_no=f"{AUDIT_TAG}-A2",
            school_id=school.id,
            class_id=cls_a2.id,
            grade_id=grade_a.id,
        )
        stu_b1 = Student(
            name=f"{AUDIT_TAG}_学生B1",
            student_no=f"{AUDIT_TAG}-B1",
            school_id=school.id,
            class_id=cls_b1.id,
            grade_id=grade_b.id,
        )
        db.add_all([stu_a1, stu_a2, stu_b1])
        await db.flush()

        # ── 9 角色 + 跨域对照账号 ──
        specs = [
            ("ms_admin", "ms_admin", {}),
            ("group_admin", "group_admin", {"org_id": org.id if org else None}),
            (
                "branch_admin",
                "branch_admin",
                {"org_id": org.id if org else None, "branch_id": branch.id if branch else None},
            ),
            ("grade_leader", "grade_leader", {"grade_id": grade_a.id}),
            ("grade_leader_b", "grade_leader", {"grade_id": grade_b.id}),
            ("class_teacher", "class_teacher", {"class_id": cls_a1.id, "grade_id": grade_a.id}),
            ("class_teacher_b", "class_teacher", {"class_id": cls_a2.id, "grade_id": grade_a.id}),
            ("teacher", "teacher", {}),
            ("counselor", "counselor", {}),
            ("parent", "parent", {"bound_student_id": stu_a1.id}),
            ("parent_b", "parent", {"bound_student_id": stu_a2.id}),
            ("student", "student", {"bound_student_id": stu_a1.id, "class_id": cls_a1.id}),
        ]

        creds = {}
        created = []
        for key, role, extra in specs:
            username = AUDIT_PREFIX + key
            pw = _gen_password()
            err = AuthService.validate_password_strength(pw, username)
            if err:
                print(f"FATAL: 生成口令未通过强度策略: {err}", file=sys.stderr)
                sys.exit(4)
            u = User(
                username=username,
                password_hash=AuthService.hash_password(pw),
                display_name=f"{AUDIT_TAG}_{key}",
                role=role,
                school_id=school.id,
                is_active=True,
                password_change_required=False,
                **extra,
            )
            db.add(u)
            creds[key] = {"username": username, "password": pw, "role": role}
            created.append((key, role))
        await db.flush()

        # 班主任回填到班级 head_teacher
        ct = (
            await db.execute(select(User).where(User.username == AUDIT_PREFIX + "class_teacher"))
        ).scalar_one()
        ct_b = (
            await db.execute(select(User).where(User.username == AUDIT_PREFIX + "class_teacher_b"))
        ).scalar_one()
        cls_a1.head_teacher_id = ct.id
        cls_a2.head_teacher_id = ct_b.id

        # ── 处分记录: 3 条 ACTIVE(公开) + 1 条 DRAFT_PENDING(内部草稿) ──
        sanctions = [
            DisciplineSanction(
                school_id=school.id,
                student_id=stu_a1.id,
                class_id=cls_a1.id,
                grade_id=grade_a.id,
                level=DisciplineLevel.WARNING,
                status=DisciplineStatus.ACTIVE,
                reason=f"{AUDIT_TAG} 合成处分-A1-公开",
                punish_date=date(2026, 3, 1),
                creator_id=ct.id,
            ),
            DisciplineSanction(
                school_id=school.id,
                student_id=stu_a2.id,
                class_id=cls_a2.id,
                grade_id=grade_a.id,
                level=DisciplineLevel.DEMERIT,
                status=DisciplineStatus.ACTIVE,
                reason=f"{AUDIT_TAG} 合成处分-A2-公开",
                punish_date=date(2026, 3, 2),
                creator_id=ct_b.id,
            ),
            DisciplineSanction(
                school_id=school.id,
                student_id=stu_b1.id,
                class_id=cls_b1.id,
                grade_id=grade_b.id,
                level=DisciplineLevel.SERIOUS_WARNING,
                status=DisciplineStatus.ACTIVE,
                reason=f"{AUDIT_TAG} 合成处分-B1-公开",
                punish_date=date(2026, 3, 3),
            ),
            DisciplineSanction(
                school_id=school.id,
                student_id=stu_a1.id,
                class_id=cls_a1.id,
                grade_id=grade_a.id,
                level=DisciplineLevel.PROBATION,
                status=DisciplineStatus.DRAFT_PENDING,
                reason=f"{AUDIT_TAG} 合成处分-A1-内部草稿(家长不可见)",
                punish_date=date(2026, 3, 4),
                creator_id=ct.id,
            ),
        ]
        db.add_all(sanctions)
        await db.commit()

        # ── 拓扑元数据(供测试脚本做数量断言,不含口令) ──
        topology = {
            "school_id": school.id,
            "org_id": org.id if org else None,
            "branch_id": branch.id if branch else None,
            "grade_a_id": grade_a.id,
            "grade_b_id": grade_b.id,
            "class_a1_id": cls_a1.id,
            "class_a2_id": cls_a2.id,
            "class_b1_id": cls_b1.id,
            "student_a1_id": stu_a1.id,
            "student_a2_id": stu_a2.id,
            "student_b1_id": stu_b1.id,
            "expect": {
                "ms_admin_total": 4,
                "grade_leader_a_total": 3,
                "grade_leader_b_total": 1,
                "class_teacher_a1_total": 2,
                "class_teacher_a2_total": 1,
                "parent_a_visible_records": 1,
            },
        }

        CREDS_FILE.write_text(
            json.dumps({"accounts": creds, "topology": topology}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        print("SEED_DONE — 合成数据已建立(口令仅写入仓库外凭据文件,未打印)")
        print(f"  凭据文件: {CREDS_FILE}")
        print(f"  账号数: {len(created)}  角色: {sorted({r for _, r in created})}")
        print(
            f"  年级A={grade_a.id} 年级B={grade_b.id} | "
            f"班A1={cls_a1.id} 班A2={cls_a2.id} 班B1={cls_b1.id}"
        )
        print(f"  学生A1={stu_a1.id} 学生A2={stu_a2.id} 学生B1={stu_b1.id}")
        print("  处分: 3条 ACTIVE + 1条 DRAFT_PENDING(内部草稿)")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
