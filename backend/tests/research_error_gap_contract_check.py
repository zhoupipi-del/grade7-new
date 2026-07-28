"""
research_error_gap_contract_check.py — 错题断层归因 schema 契约验证

不依赖 DB：构造真实 get_teacher_error_gap 返回结构，喂给 TeacherErrorGapResponse，
验证独立子维度(dim5 诊断维度)契约通过；并验证空/默认/三种 attribution 场景不炸。

运行: python tests/research_error_gap_contract_check.py
"""

import os
import sys

BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_ROOT)

from modules.research_profile.schemas import (  # noqa: E402
    ErrorGapBreakdown,
    KnowledgeGapBreakdown,
    TeacherErrorGapResponse,
)


def main() -> int:
    # 1) 完整负载：精确桥归因 + 错题/断层明细 + 关注度评分
    payload = {
        "teacher_id": 10,
        "attributed_students": 45,
        "attribution": "precise",
        "error_book": {
            "total": 18,
            "unresolved": 12,
            "by_error_type": {"conceptual": 7, "procedural": 5, "careless": 4, "unknown": 2},
        },
        "knowledge_gap": {
            "total": 9,
            "critical": 3,
            "active": 6,
            "resolved": 1,
        },
        "score": 38,
    }
    obj = TeacherErrorGapResponse(**payload)
    assert obj.teacher_id == 10
    assert obj.attribution == "precise"
    assert obj.error_book.total == 18
    assert obj.error_book.by_error_type["conceptual"] == 7
    assert obj.knowledge_gap.critical == 3
    assert obj.score == 38
    dumped = obj.model_dump()
    assert dumped["attributed_students"] == 45
    assert "error_book" in dumped and "knowledge_gap" in dumped

    # 2) 回退桥场景（teacher_subjects 年级学科组）
    fb = TeacherErrorGapResponse(
        teacher_id=11,
        attributed_students=120,
        attribution="fallback",
        error_book=ErrorGapBreakdown(total=5, unresolved=3),
        knowledge_gap=KnowledgeGapBreakdown(total=2, critical=0, active=2, resolved=0),
        score=4,
    )
    assert fb.attribution == "fallback"
    assert fb.error_book.unresolved == 3

    # 3) 空/默认场景：无任教映射（attribution=none），嵌套结构应取默认
    none_obj = TeacherErrorGapResponse(teacher_id=99, attribution="none")
    assert none_obj.attributed_students == 0
    assert none_obj.score == 0
    assert none_obj.error_book.total == 0
    assert none_obj.knowledge_gap.resolved == 0

    # 4) 嵌套结构单独构造
    eb = ErrorGapBreakdown(total=1, unresolved=1, by_error_type={"careless": 1})
    kg = KnowledgeGapBreakdown(total=1, critical=1, active=1, resolved=0)
    assert eb.by_error_type["careless"] == 1
    assert kg.critical == 1

    print("ERROR_GAP_CONTRACT_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
