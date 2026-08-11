"""
tests/ai_native/test_scope_intersection.py — Inv 14: read_class_grade_summary 输出无 PII

RED GATE 测试（Phase E Slice 1）：业务 Tool
    modules/ai_teacher_assistant/tools/read_class_grade_summary
尚未实现，全部测试预期 FAIL（需求未实现导致的正确失败）。

契约（未来实现必须满足）：
    输出仅允许聚合字段：
        class / grade 范围、exam metadata、subject aggregates
        （avg / median / distribution）、trend / comparison、counts、
        summary metadata。

    禁止任何 PII：
        student_id / student_name / student_no / phone / id_card /
        单个学生 score/rank 明细 / 任何可反推单个学生的裸记录。

    检查必须递归（dict 嵌套 + list[dict] 元素 + 序列化 JSON），
    不能只 grep 顶层 key。

    实现形态：ReadClassGradeSummaryOutput 为 Pydantic 模型（extra 默认拒绝
    PII 字段，序列化后递归扫描零命中）。
"""

from __future__ import annotations

import importlib
import json

import pytest
import pydantic

FORBIDDEN_KEYS = {
    "student_id", "student_name", "student_no",
    "phone", "id_card",
}


def _require_tool():
    try:
        return importlib.import_module(
            "modules.ai_teacher_assistant.tools.read_class_grade_summary"
        )
    except ModuleNotFoundError as exc:  # pragma: no cover - RED 分支
        pytest.fail(
            "RED: modules/ai_teacher_assistant/tools/read_class_grade_summary.py "
            f"尚未实现（Slice 1 需求未落地）: {exc}"
        )


def _recursive_scan(obj, path="$", forbidden=FORBIDDEN_KEYS):
    """递归检查所有 dict key（含嵌套 dict / list[dict]）；返回违规键路径列表。"""
    hits = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            key_path = f"{path}.{key}"
            if key in forbidden:
                hits.append(key_path)
            hits.extend(_recursive_scan(value, key_path, forbidden))
    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            hits.extend(_recursive_scan(item, f"{path}[{idx}]", forbidden))
    return hits


def _aggregate_only_output():
    return {
        "class_id": 1,
        "grade_id": 7,
        "exam": {"id": 10, "name": "2025-1 期中", "exam_date": "2025-11-10"},
        "subjects": [
            {
                "code": "math",
                "name": "数学",
                "avg": 82.5,
                "median": 84.0,
                "distribution": {"0-60": 3, "60-80": 10, "80-100": 27},
            },
        ],
        "counts": {"students": 40, "examined": 40},
        "summary": {
            "generated_at": "2026-08-11T20:00:00",
            "tool_version": "0.1.0",
        },
    }


class TestInv14NoPII:
    def test_output_schema_rejects_student_id_at_top_level(self):
        mod = _require_tool()
        with pytest.raises(pydantic.ValidationError):
            mod.ReadClassGradeSummaryOutput(class_id=1, student_id=123)

    def test_output_schema_rejects_student_name_nested(self):
        mod = _require_tool()
        with pytest.raises(pydantic.ValidationError):
            mod.ReadClassGradeSummaryOutput(
                subjects=[{"name": "数学", "student_name": "张三"}]
            )

    def test_serialized_json_has_no_forbidden_keys(self):
        mod = _require_tool()
        output = mod.ReadClassGradeSummaryOutput(**_aggregate_only_output())
        raw = json.loads(output.model_dump_json())
        assert _recursive_scan(raw) == []

    def test_nested_list_items_scanned_recursively(self):
        mod = _require_tool()
        # 聚合输出里任何嵌套位置出现 PII key → 必须被拒绝（递归，非顶层 grep）
        poisoned = _aggregate_only_output()
        poisoned["subjects"][0]["leaderboard"] = [
            {"student_name": "张三", "rank": 1}
        ]
        with pytest.raises(pydantic.ValidationError):
            mod.ReadClassGradeSummaryOutput(**poisoned)

    def test_aggregate_only_output_passes_and_serializes_clean(self):
        mod = _require_tool()
        output = mod.ReadClassGradeSummaryOutput(**_aggregate_only_output())
        assert _recursive_scan(json.loads(output.model_dump_json())) == []
