#!/usr/bin/env python3
"""
补录后修复: 对 3 名受损学生重新运行 recalculate_snapshot()
现在 Fallback 已就位 — 无 EvaluationScore 的学生将得到 base_score=100 基准而非 0。
"""

import asyncio
import sys
sys.path.insert(0, "/root/backend")

from sqlalchemy import select, text

# 显式触发所有模型注册（与 app.py 一致）
import modules.attendance.models  # noqa: F401
import modules.behavior.models    # noqa: F401
import modules.red_flag.models    # noqa: F401
import modules.evaluation.models  # noqa: F401
import modules.discipline.models  # noqa: F401
import modules.reports.models    # noqa: F401
import modules.ai_prescription.models  # noqa: F401
import modules.notifications.models   # noqa: F401
import modules.dashboard.models       # noqa: F401
import modules.growth.models          # noqa: F401
import modules.risk_models.models     # noqa: F401

from app import AsyncSessionLocal
from modules.evaluation.services import EvaluationService
from modules.evaluation.models import StudentScore

SEMESTER = "2025-2026-2"
AFFECTED = {
    1: "陈博裕",
    3: "陈佳乐",
    154: "黎梓萱",
}


async def main():
    print("=" * 70)
    print("  🩺 快照修复 — 对受损学生重算 (Fallback 已就位)")
    print("=" * 70)

    async with AsyncSessionLocal() as db:
        for student_id, name in AFFECTED.items():
            # 查旧快照
            result = await db.execute(
                select(StudentScore).where(
                    StudentScore.student_id == student_id,
                    StudentScore.semester == SEMESTER,
                )
            )
            old = result.scalar_one_or_none()
            old_moral = old.moral_score if old else "N/A"
            old_total = old.total_score if old else "N/A"

            # 重算
            new = await EvaluationService.recalculate_snapshot(
                db, student_id, 1, SEMESTER
            )

            if new:
                print(f"  ✅ {name}(id={student_id}) | "
                      f"moral: {old_moral} → {new.moral_score} | "
                      f"total: {old_total} → {new.total_score}")
            else:
                print(f"  ⚠️  {name}(id={student_id}): 重算返回 None")

        await db.commit()

    # 验证
    print("\n── 验证最终快照 ──")
    async with AsyncSessionLocal() as db:
        for student_id, name in AFFECTED.items():
            result = await db.execute(
                select(StudentScore).where(
                    StudentScore.student_id == student_id,
                    StudentScore.semester == SEMESTER,
                )
            )
            ss = result.scalar_one_or_none()
            if ss:
                print(f"  {name:<10} moral={ss.moral_score:<8} "
                      f"academic={ss.academic_score:<8} "
                      f"health={ss.health_score:<8} "
                      f"art={ss.art_score:<8} "
                      f"social={ss.social_score:<8} "
                      f"total={ss.total_score}")

        # 验证 recovery_state
        rs = await db.execute(text("SELECT student_id, recovery_ratio, policy_tag, is_active FROM recovery_state WHERE student_id IN (1,3,154) ORDER BY student_id"))
        print("\n── recovery_state 验证 ──")
        for row in rs:
            print(f"  student_id={row[0]} ratio={row[1]} tag={row[2]} active={row[3]}")

        # 验证 score_logs (discipline)
        sl = await db.execute(text(
            "SELECT student_id, change_amount, policy_tag, source_id FROM score_logs "
            "WHERE source_type='discipline' AND student_id IN (1,3,154) ORDER BY student_id"
        ))
        print("\n── score_logs (discipline) 验证 ──")
        for row in sl:
            print(f"  student_id={row[0]} change={row[1]} tag={row[2]} source_id={row[3]}")

    print(f"\n{'=' * 70}")
    print("  ✅ 修复完成")


asyncio.run(main())
