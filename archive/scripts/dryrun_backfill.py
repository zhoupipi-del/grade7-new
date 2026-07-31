#!/usr/bin/env python3
"""
recovery_state + score_logs 历史数据补录 — Dry-Run
只生成 SQL，不执行任何写入操作。
执行方式: ssh root@8.137.180.152 'python3 /dev/stdin' < dryrun_backfill.py
"""

import sys
from datetime import date, datetime, timedelta

# ── 处分等级 → 扣分映射（与 discipline/services.py LEVEL_PENALTY_MAP 对齐）──
LEVEL_PENALTY = {
    "WARNING": 5,
    "SERIOUS_WARNING": 10,
    "DEMERIT": 20,
    "PROBATION": 99,    # 一票否决，不在此次补录范围
    "EXPULSION": 99,
}

# ── 处分等级 → 观察期天数 ──
OBSERVATION_DAYS = {
    "warning": 7,
    "serious_warning": 14,
    "demerit": 30,
}

# ── 处分等级 → severity（与 policy.yaml per_severity 对齐）──
LEVEL_SEVERITY = {
    "WARNING": "warning",
    "SERIOUS_WARNING": "serious_warning",
    "DEMERIT": "demerit",
    "PROBATION": "probation",
    "EXPULSION": "expulsion",
}

# ── 模拟数据（从生产 DB 读取）──
SANCTIONS_ACTIVE = [
    {"id": 46, "student_id": 2,  "school_id": 1, "level": "WARNING",         "punish_date": "2026-06-23", "reason": "测试处分"},
    {"id": 47, "student_id": 3,  "school_id": 1, "level": "DEMERIT",         "punish_date": "2026-06-23", "reason": "BUGFIX验证处分"},
    {"id": 49, "student_id": 154,"school_id": 1, "level": "DEMERIT",         "punish_date": "2026-06-26", "reason": "D3桥接测试-记过处分"},
    {"id": 50, "student_id": 154,"school_id": 1, "level": "SERIOUS_WARNING",  "punish_date": "2026-06-26", "reason": "[自动升级] 黎梓萱 本学期累计2次处分"},
]

SANCTIONS_REVOKED = [
    {"id": 45, "student_id": 1,  "school_id": 1, "level": "WARNING",         "punish_date": "2026-06-23", "revoke_date": "2026-06-23"},
    {"id": 51, "student_id": 154,"school_id": 1, "level": "DEMERIT",         "punish_date": "2026-06-26", "revoke_date": "2026-06-26"},
]

STUDENTS = {1: "陈博裕", 2: "陈虹宇", 3: "陈佳乐", 154: "黎梓萱"}
NOW = datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def render():
    print("=" * 70)
    print("  DRY-RUN: recovery_state + score_logs 历史补录 SQL")
    print("  生成时间:", NOW)
    print("  模式: 只读预览，不执行任何写入")
    print("=" * 70)

    # ════════════════════════════════════════════
    # Part A: ACTIVE 处分 → recovery_state + score_logs
    # ════════════════════════════════════════════
    print("\n\n" + "─" * 70)
    print("  Part A: ACTIVE 处分补录 (4 条)")
    print("─" * 70)

    for s in SANCTIONS_ACTIVE:
        sid = s["id"]
        student_id = s["student_id"]
        name = STUDENTS.get(student_id, f"UNKNOWN")
        level = s["level"]
        severity = LEVEL_SEVERITY.get(level, "serious_warning")
        penalty = LEVEL_PENALTY.get(level, 0)
        obs_days = OBSERVATION_DAYS.get(severity, 14)
        p_date = datetime.strptime(s["punish_date"], "%Y-%m-%d").date()
        obs_start = p_date
        obs_end = p_date + timedelta(days=obs_days)

        print(f"\n── 处分 #{sid}: {name}(student_id={student_id}) {level} │ 扣 {penalty} 分 │ 观察期 {obs_days} 天 ──")

        # A1: recovery_state INSERT
        print(f"\n  -- [A1] recovery_state INSERT")
        print(f"  INSERT INTO recovery_state "
              f"(school_id, student_id, source_type, source_id, severity, "
              f"original_penalty, recovered_amount, remaining_penalty, "
              f"recovery_ratio, policy_tag, observation_start, observation_end, "
              f"last_computed_at, is_active, created_at, updated_at) "
              f"VALUES ("
              f"\n    1, {student_id}, 'discipline', {sid}, '{severity}', "
              f"\n    {penalty}.0, 0.0, {penalty}.0, "
              f"\n    0.0, 'repairable', '{obs_start}', '{obs_end}', "
              f"\n    '{NOW}', 1, '{NOW}', '{NOW}'"
              f"\n  );")

        # A2: score_logs INSERT
        print(f"\n  -- [A2] score_logs INSERT (处分扣分 = -{penalty})")
        print(f"  INSERT INTO score_logs "
              f"(student_id, school_id, source_type, source_id, "
              f"change_amount, policy_tag, created_at) "
              f"VALUES ("
              f"\n    {student_id}, 1, 'discipline', {sid}, "
              f"\n    -{penalty}, 'repairable', '{NOW}'"
              f"\n  );")

    # ════════════════════════════════════════════
    # Part B: REVOKED 处分 → recovery_state (100% 回血) + score_logs
    # ════════════════════════════════════════════
    print("\n\n" + "─" * 70)
    print("  Part B: REVOKED 处分补录 (2 条) — 通道A 100%回血")
    print("─" * 70)

    for s in SANCTIONS_REVOKED:
        sid = s["id"]
        student_id = s["student_id"]
        name = STUDENTS.get(student_id, f"UNKNOWN")
        level = s["level"]
        severity = LEVEL_SEVERITY.get(level, "serious_warning")
        penalty = LEVEL_PENALTY.get(level, 0)
        p_date = datetime.strptime(s["punish_date"], "%Y-%m-%d").date()
        r_date = datetime.strptime(s["revoke_date"], "%Y-%m-%d").date()
        obs_end = r_date  # 撤销日即观察期结束

        print(f"\n── 处分 #{sid}: {name}(student_id={student_id}) {level} │ 已撤销 │ 扣 {penalty} 分 → 100%回血 ──")

        # B1: recovery_state INSERT (已回血完成)
        print(f"\n  -- [B1] recovery_state INSERT (通道A 100%回血)")
        print(f"  INSERT INTO recovery_state "
              f"(school_id, student_id, source_type, source_id, severity, "
              f"original_penalty, recovered_amount, remaining_penalty, "
              f"recovery_ratio, policy_tag, observation_start, observation_end, "
              f"last_computed_at, is_active, created_at, updated_at) "
              f"VALUES ("
              f"\n    1, {student_id}, 'discipline', {sid}, '{severity}', "
              f"\n    {penalty}.0, {penalty}.0, 0.0, "
              f"\n    1.0, 'recovered', '{r_date}', '{r_date}', "
              f"\n    '{NOW}', 0, '{NOW}', '{NOW}'"
              f"\n  );")

        # B2: score_logs INSERT
        print(f"\n  -- [B2] score_logs INSERT (处分扣分 = -{penalty})")
        print(f"  INSERT INTO score_logs "
              f"(student_id, school_id, source_type, source_id, "
              f"change_amount, policy_tag, created_at) "
              f"VALUES ("
              f"\n    {student_id}, 1, 'discipline', {sid}, "
              f"\n    -{penalty}, 'repairable', '{r_date}'"
              f"\n  );")

    # ════════════════════════════════════════════
    # Part C: 受影响学生清单 & 扣分汇总
    # ════════════════════════════════════════════
    print("\n\n" + "─" * 70)
    print("  Part C: 受影响学生 & 扣分汇总")
    print("─" * 70)

    # 按学生聚合 ACTIVE 扣分
    student_penalties = {}
    for s in SANCTIONS_ACTIVE:
        sid_val = s["student_id"]
        if sid_val not in student_penalties:
            student_penalties[sid_val] = 0
        student_penalties[sid_val] += LEVEL_PENALTY.get(s["level"], 0)

    # REVOKED 处分也计一次扣分（虽然已撤销，但 score_logs 需要体现完整生命周期）
    for s in SANCTIONS_REVOKED:
        sid_val = s["student_id"]
        if sid_val not in student_penalties:
            student_penalties[sid_val] = 0
        student_penalties[sid_val] += LEVEL_PENALTY.get(s["level"], 0)

    print(f"\n  {'学生':<10} {'总处分扣分':<12} {'当前moral_score':<16} {'补录后估算':<14}")
    print(f"  {'-'*50}")
    # 当前 moral_score（从生产 DB 读取的静态值）
    current_moral = {1: 8.4, 2: 24.9, 3: 29.6, 154: 11.3}
    for sid_val, total_deduct in sorted(student_penalties.items()):
        name = STUDENTS.get(sid_val, "?")
        cur = current_moral.get(sid_val, 0)
        est = cur - total_deduct
        print(f"  {name:<10} -{total_deduct:<11} {cur:<16} ~{est:<13}")

    # ════════════════════════════════════════════
    # Part D: 风险评估
    # ════════════════════════════════════════════
    print("\n\n" + "─" * 70)
    print("  Part D: 风险评估 & 校验清单")
    print("─" * 70)
    print(f"""
  ✅ policy.yaml 覆盖检查:
     WARNING        → per_severity.warning          (k=0.5, obs=7d)   ✅
     SERIOUS_WARNING → per_severity.serious_warning   (k=0.7, obs=14d)  ✅
     DEMERIT        → per_severity.demerit           (k=1.0, obs=30d)  ✅

  ✅ score_logs 扣分映射:
     WARNING → -5  |  SERIOUS_WARNING → -10  |  DEMERIT → -20

  ⚠️  注意:
     - 处分 #50 为自动升级处分（SERIOUS_WARNING），与学生 #49 的 DEMERIT 叠加
     - 学生 黎梓萱(154) 同时有 2 条 ACTIVE 处分，扣分将叠加 (-30)
     - 学生 陈博裕(1) 的处分 #45 已撤销，通道A 100%回血
     - 补录完成后需对 4 名学生触发 recalculate_snapshot()

  🔴 高风险项:
     - 处分 #46 (student_id=2, WARNING): reason 含乱码 "REJECTED测试处分"，
       疑似原本为 REJECTED 状态后手动改为 ACTIVE。建议人工确认该条是否应保持 ACTIVE。
  """)

    print("=" * 70)
    print("  DRY-RUN 完成。请人工审查以上 SQL，确认无误后执行补录。")
    print("=" * 70)


if __name__ == "__main__":
    render()
