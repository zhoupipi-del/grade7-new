"""
tests/risk_dashboard_contract_check.py — RiskDashboardOut schema 契约收口验证

不依赖 DB：直接构造 get_dashboard 真实返回结构，喂给 RiskDashboardOut，
并额外验证"仅旧 6 字段"payload 仍通过（向后兼容，旧前端不炸）。

运行: python tests/risk_dashboard_contract_check.py
退出码 0 = 双通过；非 0 = 有失败。
"""

import os
import sys

BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_ROOT)

from modules.risk_models.schemas import RiskDashboardOut

FAILED = []


def check(name: str, cond: bool, detail: str = ""):
    if cond:
        print(f"  [PASS] {name}")
    else:
        print(f"  [FAIL] {name}  {detail}")
        FAILED.append(name)


def main():
    # 完整负载（get_dashboard 真实返回结构；嵌套列表为空以绕过 RiskWarningOut 构建）
    full = {
        "total_students": 393,
        "at_risk_count": 13,
        "by_risk_level": {"normal": 300, "attention": 80, "intervention": 13},
        "recent_warnings": [],
        "escalating_cases": [],
        "class_risk_ranking": [
            {"class_id": 1, "class_name": "2501", "at_risk_count": 5},
        ],
        "pending_warnings": 7,
        "high_risk_count": 13,
        "handled_count": 3,
        "handled_rate": 30.0,
        "dimensions": {"behavior": 5, "attendance": 2, "score": 3, "psych": 3},
    }
    try:
        obj = RiskDashboardOut(**full)
        check(
            "完整负载通过",
            obj.handled_rate == 30.0 and obj.pending_warnings == 7,
            f"handled_rate={obj.handled_rate} pending={obj.pending_warnings}",
        )
    except Exception as e:
        check("完整负载通过", False, str(e))

    # 向后兼容：仅旧 6 字段（嵌套列表为空），新字段靠默认值
    legacy = {
        "total_students": 393,
        "at_risk_count": 13,
        "by_risk_level": {"normal": 300, "attention": 80, "intervention": 13},
        "recent_warnings": [],
        "escalating_cases": [],
        "class_risk_ranking": [],
    }
    try:
        obj2 = RiskDashboardOut(**legacy)
        check(
            "旧6字段向后兼容",
            obj2.pending_warnings == 0 and obj2.handled_rate == 0.0 and obj2.dimensions == {},
            f"pending={obj2.pending_warnings} rate={obj2.handled_rate} dims={obj2.dimensions}",
        )
    except Exception as e:
        check("旧6字段向后兼容", False, str(e))

    print("=" * 40)
    if FAILED:
        print(f"结果: 失败 {len(FAILED)} 项 ❌ {FAILED}")
        sys.exit(1)
    print("结果: 契约验证双通过 ✅")


if __name__ == "__main__":
    main()
