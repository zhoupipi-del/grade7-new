"""
ai_native/runtime/planner.py — V2 Domain-Aware Bounded Planner

V2 变更（2026-08-12）：
- 按领域拆分关键词（GRADE/ATTENDANCE/BEHAVIOR/RISK/COMPREHENSIVE）
- 删除"分析""关注"等通用词从成绩关键词
- 消除 fallback=默认成绩的设计 → 未知意图返回 needs_input
- comprehensive intent 触发多工具调用
"""

from __future__ import annotations

import os
import re
from typing import Any

from pydantic import BaseModel, Field


AllowedTool = str  # V2: 放宽到 str，由 registry 校验


class PlanStep(BaseModel):
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    reason: str


class AgentPlan(BaseModel):
    goal: str
    steps: list[PlanStep]
    max_steps: int = 5  # V2: 提升到 5（综合查询需要多工具）


# ── Domain Keywords ──

GRADE_KEYWORDS = {
    "成绩", "考试", "分数", "学科", "平均分", "及格率",
    "学情", "排名", "得分", "满分", "试卷",
}

ATTENDANCE_KEYWORDS = {
    "考勤", "迟到", "早退", "缺勤", "请假",
    "出勤", "旷课",
}

BEHAVIOR_KEYWORDS = {
    "行为", "违纪", "纪律", "德育", "扣分",
    "处分", "违规", "打架", "吸烟",
}

RISK_KEYWORDS = {
    "风险", "预警", "异常", "高风险",
}

# FT-015 test-only：写工具测试意图（HTTP E2E 触发入口；验证后随工具一并移除）
WRITE_MARKER_KEYWORDS = {
    "写测试标记", "写入测试标记", "写标记", "write marker",
}

# FT-016 test-only：受控失败测试意图（failure evidence 验证入口）
FAIL_MARKER_KEYWORDS = {
    "失败测试", "故障测试", "fail test",
}

COMPREHENSIVE_KEYWORDS = {
    "重点关注", "整体情况", "综合分析", "综合评估",
    "本周重点", "最近有什么问题", "需要关注什么",
    "全面分析", "管理简报", "年级管理",
    # V2 补强：覆盖"最近值得关注的问题"等自然问法
    "值得关注", "关注的问题", "有什么问题", "最近有什么",
    "重点关注的问题", "值得重点关注", "整体情况如何",
}


class BoundedPlanner:
    """V2 领域感知有界规划器。

    升级：
    - 领域关键词路由（不再是"一切→成绩"）
    - 综合意图 → 多工具并行
    - 未知意图 → 不默认成绩
    """

    MAX_STEPS = 5

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
        clean_args = {k: v for k, v in base_args.items() if v is not None}

        # ── Intent detection ──

        wants_grade = any(k in text for k in GRADE_KEYWORDS)
        wants_attendance = any(k in text for k in ATTENDANCE_KEYWORDS)
        wants_behavior = any(k in text for k in BEHAVIOR_KEYWORDS)
        wants_risk = any(k in text for k in RISK_KEYWORDS)
        # FT-015 test-only：仅 AI_APPROVAL_TEST_TOOL=1 时识别写工具意图（生产不暴露）
        wants_write_marker = (
            os.environ.get("AI_APPROVAL_TEST_TOOL") == "1"
            and any(k in text for k in WRITE_MARKER_KEYWORDS)
        )
        wants_fail_marker = (
            os.environ.get("AI_FAILURE_TEST_TOOL") == "1"
            and any(k in text for k in FAIL_MARKER_KEYWORDS)
        )
        wants_comprehensive = any(k in text for k in COMPREHENSIVE_KEYWORDS)

        wants_compare = any(
            k in text for k in (
                "趋势", "变化", "退步", "进步",
                "最近", "上次", "对比", "比较", "波动",
            )
        )

        # ── Step assembly ──

        # REAL EVENT #1：德育晨报意图——(考勤 AND 行为 AND 风险) 也走多工具综合
        # （德育主任"今日重点关注"= 考勤+行为+已有预警，通常不查成绩）
        wants_moral_morning = (
            wants_attendance and wants_behavior and wants_risk
        )
        if wants_comprehensive or (wants_grade and wants_attendance and wants_behavior) \
                or wants_moral_morning:
            # 综合查询：全工具
            steps.append(PlanStep(
                tool="read_class_grade_summary",
                args=clean_args,
                reason="综合审查：读取学业数据",
            ))
            if wants_compare or compare_exam_ids:
                cmp_args = {k: v for k, v in base_args.items() if v is not None}
                if compare_exam_ids:
                    cmp_args["exam_ids"] = compare_exam_ids
                steps.append(PlanStep(
                    tool="compare_exam_performance",
                    args={k: v for k, v in cmp_args.items() if v is not None},
                    reason="综合审查：比较考试变化趋势",
                ))
            steps.append(PlanStep(
                tool="read_attendance_summary",
                args=clean_args,
                reason="综合审查：读取考勤数据",
            ))
            steps.append(PlanStep(
                tool="read_behavior_summary",
                args=clean_args,
                reason="综合审查：读取行为纪律数据",
            ))
            steps.append(PlanStep(
                tool="read_risk_warning_summary",
                args=clean_args,
                reason="综合审查：读取风险预警数据",
            ))
        elif wants_grade:
            # 成绩领域
            steps.append(PlanStep(
                tool="read_class_grade_summary",
                args=clean_args,
                reason="读取当前授权范围内的成绩聚合事实",
            ))
            if wants_compare or compare_exam_ids:
                cmp_args = {k: v for k, v in base_args.items() if v is not None}
                if compare_exam_ids:
                    cmp_args["exam_ids"] = compare_exam_ids
                steps.append(PlanStep(
                    tool="compare_exam_performance",
                    args={k: v for k, v in cmp_args.items() if v is not None},
                    reason="比较考试间的科目表现和变化趋势",
                ))
        elif wants_attendance:
            steps.append(PlanStep(
                tool="read_attendance_summary",
                args=clean_args,
                reason="查询考勤数据",
            ))
        elif wants_behavior:
            steps.append(PlanStep(
                tool="read_behavior_summary",
                args=clean_args,
                reason="查询行为纪律数据",
            ))
        elif wants_risk:
            steps.append(PlanStep(
                tool="read_risk_warning_summary",
                args=clean_args,
                reason="查询风险预警数据",
            ))

        # ── FT-016 test-only：失败测试 → fail_test_marker 单 step ──
        #   「可恢复」→ fail_until=1/recoverable=true（attempt1 FAIL→attempt2 PASS）
        #   默认（不可恢复）→ fail_until=9999/recoverable=false（run FAILED）
        if wants_fail_marker:
            recoverable = "可恢复" in text
            m = re.search(r"(?:失败|故障)测试\s+([\w-]+)?", text)
            marker = m.group(1) if m and m.group(1) else "ft016"
            steps.append(PlanStep(
                tool="fail_test_marker",
                args={
                    "marker": marker,
                    "fail_until": 1 if recoverable else 9999,
                    "recoverable": recoverable,
                },
                reason="FT-016 HTTP E2E：受控失败证据链",
            ))

        # ── FT-015 test-only：写测试标记 → write_test_marker 单 step ──
        if wants_write_marker:
            m = re.search(r"写(?:入)?(?:测试)?标记\s+([\w-]+)(?:\s+(\w+))?", text)
            marker = m.group(1) if m else "e2e"
            value = m.group(2) if m and m.group(2) else "1"
            steps.append(PlanStep(
                tool="write_test_marker",
                args={"marker": marker, "value": value},
                reason="FT-015 HTTP E2E：写入隔离测试标记",
            ))

        # ── Fallback: 未知意图 → needs_input（不默认成绩）──
        if not steps:
            # 返回空 plan，由 agent_service 标记 needs_input
            return AgentPlan(
                goal=goal,
                steps=[],
                max_steps=self.MAX_STEPS,
            )

        return AgentPlan(
            goal=goal,
            steps=steps[:self.MAX_STEPS],
            max_steps=self.MAX_STEPS,
        )
