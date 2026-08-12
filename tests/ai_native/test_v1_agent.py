"""V1 Agent tests — planner + critic + cross-school + provenance."""

import pytest
from ai_native.runtime.planner import BoundedPlanner
from ai_native.runtime.critic import EvidenceCritic


class TestPlanner:
    def test_planner_summary_only(self):
        plan = BoundedPlanner().plan(
            goal="分析七年级本次考试",
            grade_id=7,
            exam_id=57,
        )
        tools = [x.tool for x in plan.steps]
        assert tools == ["read_class_grade_summary"]

    def test_planner_compare(self):
        plan = BoundedPlanner().plan(
            goal="分析七年级最近成绩变化趋势",
            grade_id=7,
            compare_exam_ids=[56, 57],
        )
        tools = [x.tool for x in plan.steps]
        assert "read_class_grade_summary" in tools
        assert "compare_exam_performance" in tools
        assert len(tools) <= 3

    def test_planner_unknown_keyword_returns_default(self):
        plan = BoundedPlanner().plan(
            goal="你好",
            grade_id=7,
        )
        assert len(plan.steps) == 1
        assert plan.steps[0].tool == "read_class_grade_summary"

    def test_planner_no_duplicate_tools(self):
        plan = BoundedPlanner().plan(
            goal="分析成绩趋势变化",
            grade_id=7,
            compare_exam_ids=[1, 2],
        )
        tools = [x.tool for x in plan.steps]
        assert len(tools) == len(set(tools))


class TestCritic:
    def test_rejects_nested_pii_in_findings(self):
        critic = EvidenceCritic()
        result = critic.review(
            plan=type("Plan", (), {"steps": []})(),
            tool_results=[{"tool": "x", "status": "EXECUTED"}],
            final_output={"findings": [{"student_name": "张三"}]},
        )
        assert result.passed is False
        assert any("forbidden" in i.lower() for i in result.issues)

    def test_rejects_pii_in_overview(self):
        critic = EvidenceCritic()
        result = critic.review(
            plan=type("Plan", (), {"steps": []})(),
            tool_results=[{"tool": "x", "status": "EXECUTED"}],
            final_output={"overview": {"student_id": 1}},
        )
        assert result.passed is False

    def test_passes_clean_output(self):
        critic = EvidenceCritic()
        result = critic.review(
            plan=type("Plan", (), {"steps": []})(),
            tool_results=[{"tool": "x", "status": "EXECUTED"}],
            final_output={"findings": ["数学平均分下降 3.2 分"]},
        )
        assert result.passed is True

    def test_rejects_missing_tool_coverage(self):
        critic = EvidenceCritic()
        plan = type("Plan", (), {"steps": [type("Step", (), {"tool": "read_class_grade_summary"})()]})()
        result = critic.review(
            plan=plan,
            tool_results=[],
            final_output={"findings": ["ok"]},
        )
        assert result.passed is False
