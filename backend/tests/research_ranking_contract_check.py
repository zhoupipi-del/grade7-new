"""
research_ranking_contract_check.py — 教研排行榜 schema 契约验证

不依赖 DB：构造真实 get_ranking 返回结构，喂给 ResearchRankingResponse，
验证新字段(TeacherRankingItem + composite + scores)通过校验；
并额外验证空 items(total=0) 也能通过（无数据时不炸）。

运行: python tests/research_ranking_contract_check.py
"""

import os
import sys

BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_ROOT)

from modules.research_profile.schemas import (  # noqa: E402
    ResearchRankingResponse,
    TeacherRankingItem,
)


def main() -> int:
    # 1) 完整负载：综合分排序 + 四维分数嵌套
    payload = {
        "metric": "composite",
        "total": 2,
        "items": [
            {
                "rank": 1,
                "teacher_id": 10,
                "real_name": "张三",
                "subject_code": "math",
                "composite": 85.5,
                "scores": {"intensity": 90, "social": 80, "rigor": 88, "ai_integration": 70},
            },
            {
                "rank": 2,
                "teacher_id": 11,
                "real_name": "李四",
                "subject_code": "math",
                "composite": 72.0,
                "scores": {"intensity": 70, "social": 60, "rigor": 75, "ai_integration": 50},
            },
        ],
    }
    obj = ResearchRankingResponse(**payload)
    assert obj.total == 2, "total 应为 2"
    assert obj.items[0].rank == 1, "排名第一的 rank 应为 1"
    assert obj.items[0].scores.intensity == 90, "嵌套 scores 应正确解析"
    assert obj.items[0].composite == 85.5, "composite 应保留"
    # 确认返回对象能序列化回 dict（端到端闭环）
    dumped = obj.model_dump()
    assert dumped["metric"] == "composite"
    assert len(dumped["items"]) == 2

    # 2) 空 items：无数据时不应抛错
    empty = ResearchRankingResponse(metric="intensity", total=0, items=[])
    assert empty.total == 0
    assert empty.items == []

    # 3) TeacherRankingItem 单独构造（单项契约）
    item = TeacherRankingItem(
        rank=3,
        teacher_id=12,
        real_name="王五",
        subject_code=None,
        composite=60.0,
        scores={"intensity": 60, "social": 50, "rigor": 55, "ai_integration": 40},
    )
    assert item.subject_code is None
    assert item.scores.ai_integration == 40

    print("RANKING_CONTRACT_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
