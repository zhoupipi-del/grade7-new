#!/usr/bin/env python3
"""
semester_replayer.py — WINGS 学期回放器（开学前闭环验证工具）

═══════════════════════════════════════════════════════════════════════════
目标
  在不污染生产数据（school_id=1，1169 名真实学生）的前提下，用合成事件跑通
  “RDI 扫描 → RiskWarning 落库 → 危机看板从 0 变真”的全链路闭环，
  确保 9 月开学前这条旗舰数据链路经过了真实验收。

隔离与回滚（铁律：稳定 > 先进，能不动就别动）
  - 全部数据落在独立测试校 TEST_SCHOOL_ID = 9999
  - 测试校下自建 grade / class / student / user，互不干扰生产租户
  - cleanup 子命令按 school_id=9999 / 测试 id 单条删除，一次还原，零残留
  - 绝不触碰 school_id=1 的任何表行

真实管线（非 mock）
  - 复用 backend 的 RiskDeviationIndexCalculator + RiskWarningService
  - 合成源数据（违纪/考勤/成绩/心理）落入真实表，由真实 RDI 数学算出预警
  - 因此验证的是“真计算器 + 真落库 + 真查询 API”的端到端闭环

用法（在服务器 backend/ 目录下、用 backend 的 venv 运行）
  python semester_replayer.py run                         # 建测试校 + 合成事件 + 跑扫描
  python semester_replayer.py run --students 500 --high-risk-rate 0.12
  python semester_replayer.py report                       # 统计测试校预警/告警数量
  python semester_replayer.py cleanup                      # 删除测试校全部数据（回滚）
  python semester_replayer.py --db-url mysql+aiomysql://... run

注意: 需要能连到 WINGS 的 MySQL（本机 127.0.0.1:3307 / DATABASE_URL 环境变量），
      且 Python 环境已装 aiomysql 与 backend 包可 import（通常在服务器 backend venv 内执行）。
═══════════════════════════════════════════════════════════════════════════
"""

import argparse
import asyncio
import json
import logging
import os
import random
import sys
from datetime import date, timedelta

# ── 引导 backend 包可 import（脚本置于 backend/ 时脚本目录即包根）──
_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from core.models import Class, Grade, School, Student, User, UserRole, get_local_now
from modules.attendance.models import AttendanceRecord
from modules.behavior.models import DisciplineRecord
from modules.evaluation.models import StudentScore
from modules.risk_models.models import PsychSurvey, RiskBaseline, RiskWarning
from modules.risk_models.services import (
    RiskDeviationIndexCalculator,
    RiskWarningService,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [Replayer] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("Replayer")

TEST_SCHOOL_ID = 9999
TEST_SCHOOL_NAME = "回放测试校(REPLAYER)"
SEMESTER = "2026-2027-1"


# ═══════════════════════════════════════════════════════════════════════════
# 工具
# ═══════════════════════════════════════════════════════════════════════════


def _psych_dims(base: float, spread: float, rng: random.Random) -> dict:
    """生成 10 维心理标准分（围绕 base 波动）。"""
    keys = [
        "obsessive_compulsive_score",
        "paranoid_score",
        "hostility_score",
        "interpersonal_sensitivity_score",
        "depression_score",
        "anxiety_score",
        "learning_pressure_score",
        "maladjustment_score",
        "emotional_imbalance_score",
        "psychological_imbalance_score",
    ]
    return {k: round(rng.gauss(base, spread), 1) for k in keys}


# ═══════════════════════════════════════════════════════════════════════════
# 1. 引导测试校 + 合成事件
# ═══════════════════════════════════════════════════════════════════════════


async def bootstrap(
    db: AsyncSession,
    n_students: int,
    high_risk_rate: float,
    seed: int,
) -> dict:
    """创建测试校 / 年级 / 班级 / 学生，并插入基线 + 合成源数据。"""
    rng = random.Random(seed)
    today = date.today()
    short_start = today - timedelta(days=7)

    # --- 学校（幂等：已存在则复用）---
    school = (
        await db.execute(select(School).where(School.id == TEST_SCHOOL_ID))
    ).scalar_one_or_none()
    if school is None:
        school = School(id=TEST_SCHOOL_ID, name=TEST_SCHOOL_NAME, school_phase="junior")
        db.add(school)
        await db.flush()
    logger.info(f"测试校就绪: id={TEST_SCHOOL_ID} name={TEST_SCHOOL_NAME}")

    # --- 测试操作用户（违纪记录 created_by 外键需要）---
    test_user = (
        await db.execute(
            select(User).where(User.username == "replayer_bot", User.school_id == TEST_SCHOOL_ID)
        )
    ).scalar_one_or_none()
    if test_user is None:
        test_user = User(
            username="replayer_bot",
            display_name="回放机器人",
            password_hash="__REPLAYER__",
            role=UserRole.MS_ADMIN,
            school_id=TEST_SCHOOL_ID,
        )
        db.add(test_user)
        await db.flush()
    created_by = test_user.id

    # --- 年级（初一 / 初二）---
    grades = []
    for g_name in ["初一(回放)", "初二(回放)"]:
        g = (
            await db.execute(
                select(Grade).where(Grade.name == g_name, Grade.school_id == TEST_SCHOOL_ID)
            )
        ).scalar_one_or_none()
        if g is None:
            g = Grade(name=g_name, school_id=TEST_SCHOOL_ID, is_active=True)
            db.add(g)
            await db.flush()
        grades.append(g)
    logger.info(f"年级就绪: {[g.name for g in grades]}")

    # --- 班级：每年级 5 班 ---
    classes = []
    for g in grades:
        for ci in range(1, 6):
            c_name = f"{g.name.split('(')[0]}{ci}班"
            c = (
                await db.execute(
                    select(Class).where(Class.name == c_name, Class.school_id == TEST_SCHOOL_ID)
                )
            ).scalar_one_or_none()
            if c is None:
                c = Class(name=c_name, school_id=TEST_SCHOOL_ID, grade_id=g.id, is_active=True)
                db.add(c)
                await db.flush()
            classes.append(c)
    logger.info(f"班级就绪: 共 {len(classes)} 个")

    # --- 学生：均匀分到各班 ---
    per_class = max(1, n_students // len(classes))
    students = []
    idx = 0
    for c in classes:
        for _ in range(per_class):
            idx += 1
            st = Student(
                name=f"回放生{idx:03d}",
                student_no=f"RP{idx:05d}",
                school_id=TEST_SCHOOL_ID,
                class_id=c.id,
                grade_id=c.grade_id,
                gender=rng.choice(["男", "女"]),
                is_active=True,
            )
            db.add(st)
            students.append(st)
    await db.flush()
    logger.info(f"学生就绪: 共 {len(students)} 名")

    # --- 合成源数据 ---
    baseline_rows, discipline_rows, attendance_rows, score_rows, psych_rows = [], [], [], [], []
    high_risk_ids = []

    for st in students:
        is_hr = rng.random() < high_risk_rate
        if is_hr:
            high_risk_ids.append(st.id)

        cid, gid = st.class_id, st.grade_id

        # 基线（window_days=30，与计算器默认对齐，使其直接采用而非重算）
        if is_hr:
            b_beh = (6.0, 1.0)  # 均值高 → 但实测会更高
            b_att = (0.05, 0.05)
            b_score = (85.0, 5.0)
            b_psych = (2.5, 1.0)
        else:
            b_beh = (0.5, 0.5)
            b_att = (0.05, 0.05)
            b_score = (85.0, 5.0)
            b_psych = (0.0, 1.0)
        for btype, (mean, std) in [
            ("behavior", b_beh),
            ("attendance", b_att),
            ("score", b_score),
            ("psych", b_psych),
        ]:
            baseline_rows.append(
                RiskBaseline(
                    school_id=TEST_SCHOOL_ID,
                    student_id=st.id,
                    class_id=cid,
                    baseline_type=btype,
                    window_days=30,
                    mean_value=mean,
                    std_value=std,
                    sample_size=30,
                )
            )

        # 违纪：高危 6 次 / 普通 0 次（近 7 天）
        n_disc = 6 if is_hr else 0
        for _ in range(n_disc):
            ddate = short_start + timedelta(days=rng.randint(0, 6))
            discipline_rows.append(
                DisciplineRecord(
                    school_id=TEST_SCHOOL_ID,
                    student_id=st.id,
                    class_id=cid,
                    grade_id=gid,
                    type=rng.choice(["warning", "minor"]),
                    category=rng.choice(["迟到", "课堂", "仪容"]),
                    description="回放器合成违纪记录",
                    status="active",
                    created_by=created_by,
                    incident_date=ddate,
                )
            )

        # 考勤：高危 ~14 条中 10 条缺勤/迟到；普通 20 条全勤
        if is_hr:
            n_att, n_bad = 14, 10
        else:
            n_att, n_bad = 20, 0
        for k in range(n_att):
            adate = short_start + timedelta(days=rng.randint(0, 6))
            status = "absent" if k < n_bad else "present"
            attendance_rows.append(
                AttendanceRecord(
                    school_id=TEST_SCHOOL_ID,
                    student_id=st.id,
                    class_id=cid,
                    grade_id=gid,
                    status=status,
                    record_date=adate,
                )
            )

        # 成绩快照：高危 50 / 普通 85
        total = 50.0 if is_hr else 85.0
        score_rows.append(
            StudentScore(
                school_id=TEST_SCHOOL_ID,
                student_id=st.id,
                class_id=cid,
                grade_id=gid,
                semester=SEMESTER,
                total_score=total,
                base_score=100.0,
                updated_at=get_local_now(),
            )
        )

        # 心理问卷：高危高分 / 普通中性
        if is_hr:
            dims = _psych_dims(78.0, 8.0, rng)
            ptotal = 780.0
        else:
            dims = _psych_dims(50.0, 6.0, rng)
            ptotal = 500.0
        psych_rows.append(
            PsychSurvey(
                school_id=TEST_SCHOOL_ID,
                student_id=st.id,
                class_id=cid,
                grade_id=gid,
                survey_type="MSSMHS-55",
                total_score=ptotal,
                dimension_scores=dims,
                is_valid=True,
            )
        )

    db.add_all(baseline_rows)
    db.add_all(discipline_rows)
    db.add_all(attendance_rows)
    db.add_all(score_rows)
    db.add_all(psych_rows)
    await db.commit()

    logger.info(
        f"合成数据完成: 基线 {len(baseline_rows)} / 违纪 {len(discipline_rows)} / "
        f"考勤 {len(attendance_rows)} / 成绩 {len(score_rows)} / 心理 {len(psych_rows)}"
    )
    return {
        "students": len(students),
        "high_risk": len(high_risk_ids),
        "high_risk_ids": high_risk_ids,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 2. 跑真实 RDI 扫描（复用 RiskDeviationIndexCalculator + RiskWarningService）
# ═══════════════════════════════════════════════════════════════════════════


async def run_scan(db: AsyncSession, high_risk_ids: list[int]) -> dict:
    """对每个班级跑真实 RDI 扫描，落 RiskWarning。"""
    calc = RiskDeviationIndexCalculator(db, TEST_SCHOOL_ID)
    svc = RiskWarningService()

    classes = (
        (await db.execute(select(Class).where(Class.school_id == TEST_SCHOOL_ID))).scalars().all()
    )

    total_scanned = 0
    total_warnings = 0
    by_level = {"attention": 0, "intervention": 0, "normal": 0}
    hit_high_risk = 0

    for cls in classes:
        students = (
            (
                await db.execute(
                    select(Student).where(
                        Student.school_id == TEST_SCHOOL_ID,
                        Student.class_id == cls.id,
                        Student.is_active == True,  # noqa: E712
                    )
                )
            )
            .scalars()
            .all()
        )

        for st in students:
            total_scanned += 1
            try:
                rdi = await calc.calculate_rdi(st.id, suppress_low_rdi=True)
            except ValueError:
                # 数据不足（无源记录），跳过
                continue
            by_level[rdi["risk_level"]] = by_level.get(rdi["risk_level"], 0) + 1
            if not rdi["warning_suppressed"] and rdi["rdi_score"] >= calc.min_rdi_to_warn:
                await svc.create_warning(
                    db, TEST_SCHOOL_ID, rdi, trigger_event_type="semester_replayer"
                )
                total_warnings += 1
                if st.id in high_risk_ids:
                    hit_high_risk += 1
        await db.commit()

    logger.info(
        f"RDI 扫描完成: 扫描 {total_scanned} 人 / 生成预警 {total_warnings} 人 / "
        f"高危命中 {hit_high_risk}/{len(high_risk_ids)}"
    )
    return {
        "scanned": total_scanned,
        "warnings": total_warnings,
        "by_level": by_level,
        "high_risk_hit": hit_high_risk,
        "high_risk_total": len(high_risk_ids),
    }


# ═══════════════════════════════════════════════════════════════════════════
# 3. CEP 复合预警演示（直接落 ActiveCompositeAlert，school_id=9999 可清理）
# ═══════════════════════════════════════════════════════════════════════════


async def seed_cep(db: AsyncSession, high_risk_ids: list[int]) -> int:
    """为部分高危学生直接落 CEP 复合预警记录，演示 SSE/看板 CEP 路径有数据。"""
    try:
        from modules.growth.models import ActiveCompositeAlert
    except Exception as e:  # pragma: no cover
        logger.warning(f"CEP 表不可用，跳过: {e}")
        return 0

    # 取前若干名高危学生做演示
    demo_ids = high_risk_ids[: min(8, len(high_risk_ids))]
    rows = []
    for sid in demo_ids:
        rows.append(
            ActiveCompositeAlert(
                school_id=TEST_SCHOOL_ID,
                student_id=sid,
                alert_type="CRITICAL_COMPOSITE",
                title="复合预警(回放器演示): 连续缺勤 + 成绩断层",
                reason_meta=json.dumps(
                    {"attendance": {"consecutive": 3}, "error_funnel": {"level": "critical"}},
                    ensure_ascii=False,
                ),
                ai_prescription="（回放器合成）建议班主任约谈并联动家长。",
                is_resolved=False,
            )
        )
    if rows:
        db.add_all(rows)
        await db.commit()
    logger.info(f"CEP 复合预警演示数据: {len(rows)} 条")
    return len(rows)


# ═══════════════════════════════════════════════════════════════════════════
# 4. 报告 / 清理
# ═══════════════════════════════════════════════════════════════════════════


async def report(db: AsyncSession) -> dict:
    rw = (
        await db.execute(
            select(func.count(RiskWarning.id)).where(RiskWarning.school_id == TEST_SCHOOL_ID)
        )
    ).scalar() or 0
    stu = (
        await db.execute(select(func.count(Student.id)).where(Student.school_id == TEST_SCHOOL_ID))
    ).scalar() or 0
    try:
        from modules.growth.models import ActiveCompositeAlert

        cep = (
            await db.execute(
                select(func.count(ActiveCompositeAlert.id)).where(
                    ActiveCompositeAlert.school_id == TEST_SCHOOL_ID
                )
            )
        ).scalar() or 0
    except Exception:
        cep = "n/a"
    logger.info(f"[报告] 测试校 学生={stu} 风险预警={rw} CEP复合预警={cep}")
    return {"students": stu, "risk_warnings": rw, "cep_alerts": cep}


async def cleanup(db: AsyncSession) -> None:
    """按依赖顺序删除测试校全部数据（FK 安全）。"""
    # 1. 预警相关
    await db.execute(RiskWarning.__table__.delete().where(RiskWarning.school_id == TEST_SCHOOL_ID))
    try:
        from modules.growth.models import ActiveCompositeAlert

        await db.execute(
            ActiveCompositeAlert.__table__.delete().where(
                ActiveCompositeAlert.school_id == TEST_SCHOOL_ID
            )
        )
    except Exception:
        pass
    # 2. 源数据
    await db.execute(PsychSurvey.__table__.delete().where(PsychSurvey.school_id == TEST_SCHOOL_ID))
    await db.execute(
        AttendanceRecord.__table__.delete().where(AttendanceRecord.school_id == TEST_SCHOOL_ID)
    )
    await db.execute(
        DisciplineRecord.__table__.delete().where(DisciplineRecord.school_id == TEST_SCHOOL_ID)
    )
    await db.execute(
        StudentScore.__table__.delete().where(StudentScore.school_id == TEST_SCHOOL_ID)
    )
    await db.execute(
        RiskBaseline.__table__.delete().where(RiskBaseline.school_id == TEST_SCHOOL_ID)
    )
    # 3. 主体
    await db.execute(Student.__table__.delete().where(Student.school_id == TEST_SCHOOL_ID))
    await db.execute(Class.__table__.delete().where(Class.school_id == TEST_SCHOOL_ID))
    await db.execute(Grade.__table__.delete().where(Grade.school_id == TEST_SCHOOL_ID))
    await db.execute(User.__table__.delete().where(User.school_id == TEST_SCHOOL_ID))
    await db.execute(School.__table__.delete().where(School.id == TEST_SCHOOL_ID))
    await db.commit()
    logger.info("清理完成：测试校全部数据已删除（回滚到开学前状态）")


# ═══════════════════════════════════════════════════════════════════════════
# 引擎 / CLI
# ═══════════════════════════════════════════════════════════════════════════


def make_engine(db_url: str):
    return create_async_engine(db_url, echo=False, pool_pre_ping=True)


async def _connectivity_check(engine):
    async with engine.connect() as conn:
        await conn.execute(select(1))
    logger.info("数据库连接正常")


async def main():
    parser = argparse.ArgumentParser(description="WINGS 学期回放器（开学前闭环验证）")
    parser.add_argument(
        "--db-url",
        default=os.environ.get("DATABASE_URL"),
        help="MySQL async URL；缺省读环境变量 DATABASE_URL",
    )
    parser.add_argument("--students", type=int, default=500)
    parser.add_argument("--high-risk-rate", type=float, default=0.12)
    parser.add_argument("--seed", type=int, default=20260721)
    parser.add_argument("--no-cep", action="store_true", help="不生成 CEP 复合预警演示数据")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run")
    sub.add_parser("report")
    sub.add_parser("cleanup")
    args = parser.parse_args()

    if not args.db_url:
        parser.error("未提供 DATABASE_URL：请设置环境变量或在 --db-url 传入")

    engine = make_engine(args.db_url)
    try:
        await _connectivity_check(engine)
    except Exception as e:
        logger.error(
            "无法连接数据库。请在能访问 WINGS MySQL 的环境中运行本脚本"
            "（通常为部署服务器 backend/ 目录、使用 backend venv）：%s",
            e,
        )
        return

    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with maker() as db:
        if args.cmd == "run":
            boot = await bootstrap(db, args.students, args.high_risk_rate, args.seed)
            scan = await run_scan(db, boot["high_risk_ids"])
            cep_n = 0 if args.no_cep else await seed_cep(db, boot["high_risk_ids"])
            rep = await report(db)
            print("\n══════════════ 学期回放器 · 验收报告 ══════════════")
            print(f"  测试校           : {TEST_SCHOOL_ID} ({TEST_SCHOOL_NAME})")
            print(f"  合成学生         : {boot['students']} 名（高危标记 {boot['high_risk']} 名）")
            print(f"  RDI 扫描         : 扫描 {scan['scanned']} 人")
            print(f"    风险分布       : {scan['by_level']}")
            print(f"    生成预警       : {scan['warnings']} 条")
            print(f"    高危命中率     : {scan['high_risk_hit']}/{scan['high_risk_total']}")
            print(f"  CEP 复合预警     : {cep_n} 条（演示数据）")
            print(f"  危机看板现状     : 风险预警 {rep['risk_warnings']} 条")
            print("═══════════════════════════════════════════════════════")
            print("  ⇒ 现在用班主任/级组长账号打开“危机学生”看板，应能看到真实预警。")
            print("  ⇒ 验证完毕执行: python semester_replayer.py cleanup  （一键回滚）")
        elif args.cmd == "report":
            await report(db)
        elif args.cmd == "cleanup":
            await cleanup(db)


if __name__ == "__main__":
    asyncio.run(main())
