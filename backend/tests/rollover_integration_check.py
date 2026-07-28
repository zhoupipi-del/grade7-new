"""
tests/rollover_integration_check.py — 新学年滚动晋升引擎集成校验

不依赖远程 MySQL：用内存 SQLite（aiosqlite）搭一个隔离测试库，
真实跑通 BOSS 要求的四类场景：
  1. 毕业出档（P3）
  2. 年级晋升顺序（P4: 8->9 先于 7->8，无二次晋升）
  3. 幂等锁（重复/并发调用被拦截）
  4. 班级映射（同名同校建新班 + 学生平移）

运行: python tests/rollover_integration_check.py
退出码 0 = 全部通过；非 0 = 有失败。
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.models import Base, Class, Grade, School, Student, User
from modules.student_registry.models import (
    RolloverLock,
    StudentRegistryExt,
    StudentYearHistory,
)
from modules.student_registry.rollover import RolloverEngine, RolloverError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TMP_DB = os.path.join(BACKEND_ROOT, "_rollover_test_tmp.db")
if os.path.exists(_TMP_DB):
    os.remove(_TMP_DB)
# 文件型 SQLite + 默认连接池：每个连接独立指向同一文件，
# 避免内存库 StaticPool 单连接争用导致的死锁。生产环境为 MySQL，此处仅做集成校验。
ENGINE = create_async_engine(f"sqlite+aiosqlite:///{_TMP_DB}", future=True)
SESSION = async_sessionmaker(ENGINE, class_=AsyncSession, expire_on_commit=False)

FAILED = []


def check(name: str, cond: bool, detail: str = ""):
    if cond:
        print(f"  [PASS] {name}")
    else:
        print(f"  [FAIL] {name}  {detail}")
        FAILED.append(name)


async def setup_seed(db: AsyncSession):
    # 测试专用：SQLite 仅对 INTEGER PRIMARY KEY 自增，BIGINT 不自增。
    # 生产环境 MySQL 原生支持 BIGINT AUTO_INCREMENT，此处仅把内存库的
    # BigInteger 列降级为 Integer，使集成校验可运行（不改动任何生产模型）。
    from sqlalchemy import BigInteger, Integer

    for t in Base.metadata.tables.values():
        for c in t.columns:
            if isinstance(c.type, BigInteger):
                c.type = Integer()

    # 文件型 SQLite：ENGINE.begin() 与 session 各自持独立连接到同一文件，
    # 无单连接争用，建表安全。
    async with ENGINE.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    school = School(name="集成测试学校", school_phase="junior")
    db.add(school)
    await db.flush()
    sid = school.id

    user = User(
        username="admin",
        password_hash="x",
        role="ms_admin",
        school_id=sid,
        is_active=True,
        display_name="Admin",
    )
    db.add(user)
    await db.flush()
    uid = user.id

    grades = {}
    for so, name in [(7, "七年级"), (8, "八年级"), (9, "九年级")]:
        g = Grade(name=name, school_id=sid, sort_order=so, is_active=True)
        db.add(g)
        await db.flush()
        grades[so] = g

    classes = {}
    for so in (7, 8, 9):
        for cn in ("2501", "2502"):
            c = Class(
                name=cn,
                school_id=sid,
                grade_id=grades[so].id,
                is_active=True,
                student_count=0,
                class_type="administrative",
            )
            db.add(c)
            await db.flush()
            classes[(so, cn)] = c

    counts = {7: 20, 8: 18, 9: 15}
    for so in (7, 8, 9):
        for i in range(counts[so]):
            cn = "2501" if i % 2 == 0 else "2502"
            cls = classes[(so, cn)]
            stu = Student(
                name=f"S{so}_{i}",
                student_no=f"2026{so}{cn}{i:02d}",
                school_id=sid,
                class_id=cls.id,
                grade_id=grades[so].id,
                is_active=True,
            )
            db.add(stu)
            await db.flush()
            ext = StudentRegistryExt(student_id=stu.id, school_id=sid, registry_status="active")
            db.add(ext)
            cls.student_count += 1

    await db.commit()
    return sid, uid, grades


async def main():
    db = SESSION()
    try:
        sid, uid, grades = await setup_seed(db)
        print(f"[seed] school_id={sid} user_id={uid} grades=7/8/9")
        g7, g8, g9 = grades[7].id, grades[8].id, grades[9].id

        operator = (await db.execute(select(User).where(User.id == uid))).scalar_one()

        # ── 0) dry_run 预览 ──
        print("\n[场景0] dry_run 预览")
        plan = await RolloverEngine.run(db, sid, operator, school_year="2026-2027", dry_run=True)
        check("dry_run 返回 status=dry_run", plan["status"] == "dry_run")
        check(
            "dry_run 总活跃数=53",
            plan["total_active_students"] == 53,
            str(plan.get("total_active_students")),
        )
        check("dry_run 毕业年级=九年级", plan["will_graduate_grade"] == "九年级")
        check("dry_run 毕业人数=15", plan["will_graduate_count"] == 15)
        check(
            "dry_run 晋升计划含 7->8 与 8->9",
            "七年级 -> 八年级" in plan["will_promote"]
            and "八年级 -> 九年级" in plan["will_promote"],
            str(plan["will_promote"]),
        )
        # dry_run 不应写入任何行
        snap_after_dry = (await db.execute(select(func.count(StudentYearHistory.id)))).scalar()
        lock_after_dry = (await db.execute(select(func.count(RolloverLock.id)))).scalar()
        check("dry_run 未写快照", snap_after_dry == 0)
        check("dry_run 未加锁", lock_after_dry == 0)

        # ── 1) 真实执行 ──
        print("\n[场景1] 真实滚动晋升（毕业+晋升）")
        result = await RolloverEngine.run(db, sid, operator, school_year="2026-2027")
        await db.commit()  # 模拟 app.py get_db_override 的成功提交

        check("status=success", result["status"] == "success")
        check("snapshot_count=53", result["snapshot_count"] == 53, str(result["snapshot_count"]))
        check("graduated_count=15", result["graduated_count"] == 15, str(result["graduated_count"]))
        check("promoted_count=38", result["promoted_count"] == 38, str(result["promoted_count"]))
        check("lock_id 已生成", result["lock_id"] is not None)
        check(
            "created_classes 有 4 个(8->9两班 + 7->8两班)",
            len(result["created_classes"]) == 4,
            str(len(result["created_classes"])),
        )

        # ── 2) 毕业出档校验 ──
        print("\n[场景2] 毕业出档校验")
        # 原 9 年级 15 人应被毕业出档：registry_status='graduated' 且 is_active=False。
        # 注意：P4 晋升会把原 8 年级学生平移进 9 年级（is_active=True），
        # 因此 9 年级活跃数不为 0 是正确的，不能据此判断毕业失败。
        graduated_active = (
            await db.execute(
                select(func.count(Student.id))
                .join(StudentRegistryExt, StudentRegistryExt.student_id == Student.id)
                .where(
                    StudentRegistryExt.registry_status == "graduated",
                    Student.is_active == True,  # noqa: E712
                )
            )
        ).scalar() or 0
        check("毕业出档的15人全部 is_active=False", graduated_active == 0, str(graduated_active))

        # 通过 ext 表确认毕业状态
        grad_ext = (
            (
                await db.execute(
                    select(StudentRegistryExt)
                    .join(Student, Student.id == StudentRegistryExt.student_id)
                    .where(Student.school_id == sid)
                )
            )
            .scalars()
            .all()
        )
        graduated = [e for e in grad_ext if e.registry_status == "graduated"]
        check("graduated 状态记录=15", len(graduated) == 15, str(len(graduated)))

        # ── 3) 年级晋升顺序校验 ──
        print("\n[场景3] 晋升顺序与二次晋升防护")
        # 原 8 年级 18 人应全部进入 9 年级
        promoted_to_9 = (
            await db.execute(
                select(func.count(Student.id)).where(
                    Student.grade_id == g9,
                    Student.is_active == True,  # noqa: E712
                )
            )
        ).scalar()
        check("18 名原8年级学生晋升到9年级", promoted_to_9 == 18, str(promoted_to_9))

        # 原 7 年级 20 人应全部进入 8 年级
        promoted_to_8 = (
            await db.execute(
                select(func.count(Student.id)).where(
                    Student.grade_id == g8,
                    Student.is_active == True,  # noqa: E712
                )
            )
        ).scalar()
        check("20 名原7年级学生晋升到8年级", promoted_to_8 == 20, str(promoted_to_8))

        # 关键：不得出现 7->9 的二次晋升（即不应有学生从 7 直接跳到 9 且 7 年级清空后无残留到 9 的异常）
        # 9 年级活跃总数应恰好 = 原8年级人数(18)，不能等于 18+20
        check("9年级活跃总数=18(无二次晋升)", promoted_to_9 == 18)

        # 7 年级现在应无活跃学生（无新生导入）
        g7_active = (
            await db.execute(
                select(func.count(Student.id)).where(
                    Student.grade_id == g7,
                    Student.is_active == True,  # noqa: E712
                )
            )
        ).scalar()
        check("7年级活跃学生=0(未导入新生)", g7_active == 0, str(g7_active))

        # ── 4) 班级映射校验 ──
        print("\n[场景4] 班级映射（同名同校建新班 + 学生平移）")
        # 取一名原7年级2501班学生，确认其现在在 grade8 的 2501 班
        sample = (
            await db.execute(
                select(Student).where(Student.school_id == sid, Student.name == "S7_0")
            )
        ).scalar_one()
        new_cls = (await db.execute(select(Class).where(Class.id == sample.class_id))).scalar_one()
        check("S7_0 现属8年级", new_cls.grade_id == g8)
        check("S7_0 班级名仍为2501(同名)", new_cls.name == "2501", new_cls.name)

        # 旧 8 年级班级应已归档改名
        old_8_cls = (
            (
                await db.execute(
                    select(Class).where(
                        Class.school_id == sid,
                        Class.grade_id == g8,
                        Class.name.like("%归档%"),
                    )
                )
            )
            .scalars()
            .all()
        )
        check("旧8年级班级已归档(>=2)", len(old_8_cls) >= 2, str(len(old_8_cls)))

        # 新 9 年级班级存在且活跃
        new_9_cls = (
            (
                await db.execute(
                    select(Class).where(
                        Class.school_id == sid,
                        Class.grade_id == g9,
                        Class.is_active == True,  # noqa: E712
                    )
                )
            )
            .scalars()
            .all()
        )
        check("新9年级活跃班级=2", len(new_9_cls) == 2, str(len(new_9_cls)))
        check(
            "新9年级班级名为2501/2502",
            {c.name for c in new_9_cls} == {"2501", "2502"},
            str({c.name for c in new_9_cls}),
        )

        # 学生平移后班级人数正确（每班 9 人：原 18 人平分到 2501/2502）
        for c in new_9_cls:
            check(f"新9年级班 {c.name} 人数=9", c.student_count == 9, str(c.student_count))

        # ── 5) 幂等锁校验 ──
        print("\n[场景5] 幂等锁拦截重复执行")
        blocked = False
        try:
            await RolloverEngine.run(db, sid, operator, school_year="2026-2027")
            await db.commit()
        except RolloverError as e:
            blocked = e.status_code == 409
        check("重复调用被 409 拦截", blocked)

        # 不同学年应可再次执行（不冲突）
        result2 = await RolloverEngine.run(db, sid, operator, school_year="2027-2028")
        await db.commit()
        check("不同学年(2027-2028)可再次执行", result2["status"] == "success")
        # 第一次执行后：原8年级18人已晋升到9年级且活跃；第二次跑另一个学年时
        # 他们已成为最高年级，应当毕业出档（graduated_count=18，而非 0）。
        check(
            "二次执行毕业人数=18(原8->9的18人毕业出档)",
            result2["graduated_count"] == 18,
            str(result2["graduated_count"]),
        )
        check("二次执行锁ID独立(不同学年)", result2["lock_id"] != result["lock_id"])

    finally:
        await db.close()
        if os.path.exists(_TMP_DB):
            os.remove(_TMP_DB)

    print("\n" + ("=" * 48))
    if FAILED:
        print(f"结果: 失败 {len(FAILED)} 项 -> {FAILED}")
        sys.exit(1)
    else:
        print("结果: 全部通过 ✅")
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
