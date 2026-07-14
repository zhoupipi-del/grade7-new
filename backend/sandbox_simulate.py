#!/usr/bin/env python3
"""
PolicyEngine 沙箱仿真 — 幂律回血曲线 + 分类 + 路由

运行：
  cd /root/backend
  .venv/bin/python3 sandbox_simulate.py
"""

from __future__ import annotations

import sys

sys.path.insert(0, "/root/backend")

from modules.policy_engine import PolicyEngine


def simulate_recovery_curve():
    """仿真回血曲线（4 种场景）"""
    pe = PolicyEngine.from_yaml("/root/backend/policy.yaml")

    scenarios = [
        ("学生A·打架(serious_warning)", "serious_warning", 15.0, 90),
        ("学生B·吸烟(serious_warning)", "serious_warning", 10.0, 90),
        ("学生C·作弊(demerit)", "demerit", 20.0, 90),
        ("学生D·警告(warning)", "warning", 5.0, 60),
    ]

    print("=" * 60)
    print("PolicyEngine 沙箱仿真 — 幂律回血曲线")
    print("=" * 60)

    for label, severity, penalty, max_days in scenarios:
        curve = pe.preview_recovery(
            penalty_amount=penalty,
            severity=severity,
            max_days=max_days,
        )
        k = pe.config.recovery_model.parameters.k
        sev_cfg = pe.config.recovery_model.per_severity.get(severity, None)
        k_actual = sev_cfg.k_override if sev_cfg and sev_cfg.k_override else k

        print(f"\n── {label} ─── penalty={penalty}, severity={severity}, k={k_actual}")
        print(f"  {'t':>4s} | {'recovered':>10s} | {'remaining':>10s} | {'ratio':>6s}")
        print(f"  {'─' * 4}-+-{'─' * 12}-+-{'─' * 12}-+-{'─' * 8}")
        for d, ratio, rem in curve:
            if d % 7 == 0 or d == 1 or d == max_days:
                rec = ratio * penalty
                print(f"  {d:>4d} | {rec:>10.2f} | {rem:>10.2f} | {ratio:>5.1%}")


def simulate_classification():
    """仿真事件分类"""
    pe = PolicyEngine.from_yaml("/root/backend/policy.yaml")

    print("\n")
    print("=" * 60)
    print("事件分类仿真")
    print("=" * 60)

    for bt, label in [
        ("fighting", "打架"),
        ("smoking", "吸烟"),
        ("cheating", "作弊"),
        ("lateness", "迟到"),
        ("absence", "缺勤"),
        ("good_job", "表扬"),
    ]:
        r = pe.classify(bt)
        print(
            f"  {label:<6s} → severity={r.severity:<10s} dim={r.dimension_code:<15s} penalty={r.base_penalty}"
        )


def simulate_approval_chain():
    """仿真审批链"""
    pe = PolicyEngine.from_yaml("/root/backend/policy.yaml")

    print("\n")
    print("=" * 60)
    print("审批链仿真")
    print("=" * 60)

    for bt, label in [("fighting", "打架"), ("cheating", "作弊"), ("lateness", "迟到")]:
        chain = pe.route(bt, "class_teacher")
        print(f"\n  {label} → mode={chain.mode}")
        for i, node in enumerate(chain.nodes, 1):
            print(f"    节点{i}: {node.role} ({node.label}) timeout={node.timeout_hours}h")
        print(f"  总超时: {chain.total_timeout_hours}h")


if __name__ == "__main__":
    simulate_recovery_curve()
    simulate_classification()
    simulate_approval_chain()
    print("\n\n✅ 沙箱仿真完成！")
