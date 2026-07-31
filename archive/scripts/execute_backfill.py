#!/usr/bin/env python3
"""
recovery_state + score_logs 历史补录 — 执行脚本
分三步: (1)数据清洗 (2)补录SQL (3)重算快照
"""
import asyncio
import sys
import os
from datetime import date, datetime, timedelta

# 加载应用环境
sys.path.insert(0, "/root/backend")

# ═══════════════════════════════════
# 配置
# ═══════════════════════════════════
LEVEL_PENALTY = {"WARNING": 5, "SERIOUS_WARNING": 10, "DEMERIT": 20}
LEVEL_SEVERITY = {"WARNING": "warning", "SERIOUS_WARNING": "serious_warning", "DEMERIT": "demerit"}
OBSERVATION_DAYS = {"warning": 7, "serious_warning": 14, "demerit": 30}
SEMESTER = "2025-2026-2"

# 有效补录清单（剔除 #46）
BACKFILL = [
    # ACTIVE (需要正常回血追踪)
    {"id": 47, "student": 3,  "level": "DEMERIT",         "punish_date": "2026-06-23", "revoke_date": None},
    {"id": 49, "student": 154,"level": "DEMERIT",         "punish_date": "2026-06-26", "revoke_date": None},
    {"id": 50, "student": 154,"level": "SERIOUS_WARNING",  "punish_date": "2026-06-26", "revoke_date": None},
    # REVOKED (通道A 100%回血)
    {"id": 45, "student": 1,  "level": "WARNING",         "punish_date": "2026-06-23", "revoke_date": "2026-06-23"},
    {"id": 51, "student": 154,"level": "DEMERIT",         "punish_date": "2026-06-26", "revoke_date": "2026-06-26"},
]

STUDENTS = {1: "陈博裕", 2: "陈虹宇", 3: "陈佳乐", 154: "黎梓萱"}


async def main():
    from app import AsyncSessionLocal

    # 注册所有模型的 Mapper（必须在 ORM 操作前加载）
    import modules.attendance.models  # noqa: F401
    import modules.behavior.models    # noqa: F401
    import modules.red_flag.models      # noqa: F401
    import modules.evaluation.models     # noqa: F401
    import modules.discipline.models    # noqa: F401
    import modules.reports.models      # noqa: F401
    import modules.ai_prescription.models  # noqa: F401
    import modules.notifications.models   # noqa: F401
    import modules.dashboard.models        # noqa: F401
    import modules.growth.models          # noqa: F401
    import modules.risk_models.models  # noqa: F401

    from modules.evaluation.services import EvaluationService

    NOW = datetime.now()

    print("=" * 70)
    print("  recovery_state + score_logs 补录 — 执行模式")
    print(f"  开始时间: {NOW.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    try:
        async with AsyncSessionLocal() as db:
            # ═══════════════════════════════════
            # 步骤一: 数据清洗 — 清洗 #46
            # ═══════════════════════════════════
            print("\n── 步骤一: 数据清洗 — 将 #46 (陈虹宇) 强制 REVOKED ──")
            from sqlalchemy import text
            from sqlalchemy import update as sa_update
            from modules.discipline.models import DisciplineSanction, DisciplineStatus

            result = await db.execute(
                sa_update(DisciplineSanction)
                .where(DisciplineSanction.id == 46)
                .values(
                    status=DisciplineStatus.REVOKED,
                    revoke_date=date.today(),
                    revoke_reason="[补录清洗] 历史测试数据脏清洗: reason含REJECTED + createdAt=NULL",
                    updated_at=NOW,
                )
            )
            rowcount = result.rowcount
            print(f"  OK: UPDATE discipline_sanctions: {rowcount} 行受影响 (id=46 → REVOKED)")

            # 验证
            verify = await db.execute(
                text("SELECT id, status, revoke_date FROM discipline_sanctions WHERE id=46")
            )
            row = verify.fetchone()
            print(f"  验证: id={row[0]} status={row[1]} revoke_date={row[2]}")

            # ═══════════════════════════════════
            # 步骤二: 补录 recovery_state (5条)
            # ═══════════════════════════════════
            print("\n── 步骤二: 补录 recovery_state (5条) ──")
            from modules.evaluation.models import RecoveryState

            recovery_count = 0
            for s in BACKFILL:
                sid = s["id"]
                student_id = s["student"]
                name = STUDENTS[student_id]
                level = s["level"]
                severity = LEVEL_SEVERITY[level]
                penalty = LEVEL_PENALTY[level]
                obs_days = OBSERVATION_DAYS[severity]
                p_date = datetime.strptime(s["punish_date"], "%Y-%m-%d").date()
                is_revoked = s["revoke_date"] is not None

                if is_revoked:
                    r_date = datetime.strptime(s["revoke_date"], "%Y-%m-%d").date()
                    recovery = RecoveryState(
                        school_id=1, student_id=student_id, source_type="discipline",
                        source_id=sid, severity=severity,
                        original_penalty=float(penalty),
                        recovered_amount=float(penalty),
                        remaining_penalty=0.0, recovery_ratio=1.0,
                        policy_tag="recovered",
                        observation_start=r_date, observation_end=r_date,
                        last_computed_at=NOW, is_active=False,
                    )
                    tag = "recovered (100%)"
                else:
                    r_date = p_date + timedelta(days=obs_days)
                    recovery = RecoveryState(
                        school_id=1, student_id=student_id, source_type="discipline",
                        source_id=sid, severity=severity,
                        original_penalty=float(penalty),
                        recovered_amount=0.0, remaining_penalty=float(penalty),
                        recovery_ratio=0.0, policy_tag="repairable",
                        observation_start=p_date, observation_end=r_date,
                        last_computed_at=NOW, is_active=True,
                    )
                    tag = "repairable (active)"

                db.add(recovery)
                recovery_count += 1
                print(f"  OK #{sid} {name}(id={student_id}) {level} → {severity} | "
                      f"penalty={penalty} | obs={p_date}~{r_date} | {tag}")

            await db.flush()
            print(f"  已插入 {recovery_count} 条 recovery_state 记录")

            # ═══════════════════════════════════
            # 步骤三: 补录 score_logs (5条)
            # ═══════════════════════════════════
            print("\n── 步骤三: 补录 score_logs (5条) ──")

            from modules.evaluation.models import StudentScore, ScoreLog
            from sqlalchemy import select as sa_select

            result = await db.execute(
                sa_select(StudentScore).where(
                    StudentScore.student_id.in_([s["student"] for s in BACKFILL]),
                    StudentScore.semester == SEMESTER,
                )
            )
            snapshots = {s.student_id: s for s in result.scalars().all()}

            log_count = 0
            for s in BACKFILL:
                sid = s["id"]
                student_id = s["student"]
                name = STUDENTS[student_id]
                level = s["level"]
                penalty = LEVEL_PENALTY[level]
                is_revoked = s["revoke_date"] is not None
                r_or_p_date = s["revoke_date"] if is_revoked else s["punish_date"]
                log_date = datetime.strptime(r_or_p_date, "%Y-%m-%d")

                ss = snapshots.get(student_id)
                current_before = ss.total_score if ss else 0.0

                source_label = "[历史补录] 处分生效时未记录扣分"
                if is_revoked:
                    source_label += " | 已撤销通道A 100%回血"
                else:
                    source_label += f" | {level}: -{penalty}分"

                log = ScoreLog(
                    student_id=student_id, school_id=1, dimension="moral",
                    change_amount=float(-penalty),
                    before_score=current_before, after_score=current_before,
                    reason=f"{source_label} (处分#{sid})",
                    source_type="discipline", source_id=sid,
                    created_by=1,
                    policy_tag="recovered" if is_revoked else "repairable",
                    created_at=log_date,
                )
                db.add(log)
                log_count += 1
                print(f"  OK #{sid} {name} {level} | before={current_before} | change={-penalty} | "
                      f"tag={'recovered' if is_revoked else 'repairable'}")

            await db.flush()
            print(f"  已插入 {log_count} 条 score_logs 记录")

            # ═══════════════════════════════════
            # 步骤四: 重算快照 (4名学生)
            # ═══════════════════════════════════
            print("\n── 步骤四: 重算快照 (3名学生) ──")
            affected_students = sorted(set(s["student"] for s in BACKFILL))
            print(f"  受影响学生: {[STUDENTS[s] for s in affected_students]}")

            for student_id in affected_students:
                name = STUDENTS[student_id]
                result = await db.execute(
                    sa_select(StudentScore).where(
                        StudentScore.student_id == student_id,
                        StudentScore.semester == SEMESTER,
                    )
                )
                old_snapshot = result.scalar_one_or_none()
                old_total = old_snapshot.total_score if old_snapshot else 0
                old_moral = old_snapshot.moral_score if old_snapshot else 0

                new_snapshot = await EvaluationService.recalculate_snapshot(
                    db, student_id, 1, SEMESTER
                )
                if new_snapshot:
                    delta = round(new_snapshot.total_score - old_total, 1)
                    print(f"  OK {name}(id={student_id}) | "
                          f"moral: {old_moral} → {new_snapshot.moral_score} "
                          f"| total: {old_total} → {new_snapshot.total_score} "
                          f"| Δ = {delta}")

                    await db.execute(
                        text(
                            "UPDATE score_logs SET after_score = :after "
                            "WHERE student_id = :sid AND source_type = 'discipline' "
                            "AND reason LIKE :p "
                        ),
                        {"after": new_snapshot.total_score, "sid": student_id, "p": "%历史补录%"},
                    )
                else:
                    print(f"  WARN {name}(id={student_id}): recalculate_snapshot 返回 None")

            # ═══════════════════════════════════
            # 步骤五: 最终验证
            # ═══════════════════════════════════
            print("\n── 步骤五: 最终验证 ──")

            rs_result = await db.execute(text("SELECT COUNT(*) FROM recovery_state"))
            print(f"  recovery_state: {rs_result.scalar()} 条 (预期 5)")

            sl_result = await db.execute(
                text("SELECT COUNT(*) FROM score_logs WHERE source_type='discipline'")
            )
            print(f"  score_logs (discipline): {sl_result.scalar()} 条 (预期 5)")

            print(f"\n  {'学生':<10} {'moral':<10} {'total':<10} {'处分':<10}")
            print(f"  {'-'*42}")
            for student_id in affected_students:
                result = await db.execute(
                    sa_select(StudentScore).where(
                        StudentScore.student_id == student_id,
                        StudentScore.semester == SEMESTER,
                    )
                )
                ss = result.scalar_one_or_none()
                if ss:
                    from modules.evaluation.services import EvaluationService as ES2
                    from modules.discipline.models import (
                        DisciplineSanction as DS,
                        DisciplineStatus as DSt,
                    )
                    sanc_result = await db.execute(
                        sa_select(DS).where(
                            DS.student_id == student_id, DS.status == DSt.ACTIVE
                        )
                    )
                    active_sancs = list(sanc_result.scalars().all())
                    pt, _, _ = ES2.compute_discipline_penalty(active_sancs)
                    print(f"  {STUDENTS[student_id]:<10} {ss.moral_score:<10} {ss.total_score:<10} {pt:<10}")

            await db.commit()
            print(f"\n{'='*70}")
            print(f"  OK 补录完成。所有变更已提交。")
            print(f"{'='*70}")

    except Exception as e:
        print(f"\n  FAIL: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
