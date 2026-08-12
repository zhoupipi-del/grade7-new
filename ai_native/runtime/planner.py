"""
ai_native/runtime/planner.py — V1 Bounded Planner

V1 确定性 bounded planner。不做无限 ReAct，不引入 LangGraph。
- max_steps <= 3
- 工具白名单
- 不会让 LLM 自己编 Tool
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


AllowedTool = Literal[
    "read_class_grade_summary",
    "compare_exam_performance",
]


class PlanStep(BaseModel):
    tool: AllowedTool
    args: dict[str, Any] = Field(default_factory=dict)
    reason: str


class AgentPlan(BaseModel):
    goal: str
    steps: list[PlanStep]
    max_steps: int = 3


class BoundedPlanner:
    """V1 确定性有界规划器。

    目标：
    - 自然语言 → Tool plan
    - 不允许模型发明 Tool
    - max_steps <= 3
    - 不无限循环
    """

    MAX_STEPS = 3

    def plan(
        self,
        *,
        goal: str,
        grade_id: int,
        class_id: int | None = None,
        exam_id: int | None = None,
        compare_exam_ids: list[int] | None = None,
    ) -> AgentPlan:
        text = goal.strip().lower()
        steps: list[PlanStep] = []

        base_args = {
            "grade_id": grade_id,
            "class_id": class_id,
            "exam_id": exam_id,
        }

        # 所有成绩类任务至少先读取当前成绩摘要
        if any(k in text for k in ("成绩", "考试", "学情", "表现", "分析", "关注", "默认")):
            steps.append(
                PlanStep(
                    tool="read_class_grade_summary",
                    args={k: v for k, v in base_args.items() if v is not None},
                    reason="读取当前授权范围内的成绩聚合事实",
                )
            )

        # 有明显趋势/比较意图才调用 compare
        wants_compare = any(
            k in text
            for k in (
                "趋势",
                "变化",
                "退步",
                "进步",
                "最近",
                "上次",
                "对比",
                "比较",
                "波动",
            )
        )

        if wants_compare or compare_exam_ids:
            args: dict[str, Any] = {
                "grade_id": grade_id,
                "class_id": class_id,
            }
            if compare_exam_ids:
                args["exam_ids"] = compare_exam_ids

            steps.append(
                PlanStep(
                    tool="compare_exam_performance",
                    args={k: v for k, v in args.items() if v is not None},
                    reason="比较考试间的科目表现和变化趋势",
                )
            )

        # 没命中关键词也不给空 plan
        if not steps:
            steps.append(
                PlanStep(
                    tool="read_class_grade_summary",
                    args={k: v for k, v in base_args.items() if v is not None},
                    reason="默认执行授权范围内的成绩分析",
                )
            )

        # 去重 + bounded
        deduped: list[PlanStep] = []
        seen: set[str] = set()

        for step in steps:
            if step.tool in seen:
                continue
            seen.add(step.tool)
            deduped.append(step)

        return AgentPlan(
            goal=goal,
            steps=deduped[: self.MAX_STEPS],
            max_steps=self.MAX_STEPS,
        )
