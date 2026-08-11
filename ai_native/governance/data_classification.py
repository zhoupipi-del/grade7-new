"""
ai_native.governance.data_classification — DataClassification + TaintLogic（Inv 13）
=====================================================================================

固定四级（小写，严格递增序）：
    public < internal < student_pii < psych_sensitive

★ DataClassification 必须是 `str, Enum`（string enum）：Runtime 可安全执行
  `model.data_classification = DataClassification.internal`，而不是到处手写
  `.value` 或产生序列化差异。

TaintLogic.classify(current, actual) -> effective：
    - actual 等级更高 → 升级（返回 actual）
    - 同级 或 actual 更低 → 保持 current（绝不降级）
    - ★ 本模块不提供任何 downgrade API

对应测试：tests/ai_native/test_tool_descriptor_contract.py::TestInv13MonotonicTaint
"""

from __future__ import annotations

import enum

CLASSIFICATION_ORDER = ["public", "internal", "student_pii", "psych_sensitive"]


class DataClassification(str, enum.Enum):
    public = "public"
    internal = "internal"
    student_pii = "student_pii"
    psych_sensitive = "psych_sensitive"


def _rank(value: DataClassification) -> int:
    if not isinstance(value, DataClassification):
        raise TypeError(f"期望 DataClassification，得到 {type(value).__name__}")
    return CLASSIFICATION_ORDER.index(value.value)


class TaintLogic:
    """单调不降的 classification 演化（Inv 13）。"""

    @staticmethod
    def classify(current: DataClassification, actual: DataClassification) -> DataClassification:
        """
        返回 effective classification：
          actual > current → 升级（返回 actual）
          其他（同级或更低）→ 保持 current，绝不降级
        """
        if _rank(actual) > _rank(current):
            return actual
        return current
