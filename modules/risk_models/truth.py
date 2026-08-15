"""
modules/risk_models/truth.py — Current-risk truth model (DATA-GOV-001 Phase 1)

定义"当前有效预警"的 canonical 语义，供晨报/统计/API 统一复用。

三层 canonical 语义（Closure A 拆分，未过期 ≠ 可处置）：

CURRENT_UNEXPIRED
    = status 是 current（active）
    AND 未过期 (expires_at IS NULL OR expires_at >= NOW())
    AND 未处置 (handled_by IS NULL)

CURRENT_ACTIONABLE
    = CURRENT_UNEXPIRED
    AND 事件/来源锚点有效 (trigger_event_id > 0)

CURRENT_REQUIRES_VERIFICATION
    = CURRENT_UNEXPIRED
    AND 无事件锚点 (trigger_event_id IS NULL OR = 0)
    （governance_status 为 UNANCHORED / DATA_QUALITY_DEGRADED 的行归入此类）

设计纪律：
    - 未过期 ≠ 可处置：CURRENT_ACTIONABLE 必须同时满足事件锚定。
    - 无锚点的 CURRENT_UNEXPIRED 一律 REQUIRES_VERIFICATION，不得与有锚点同权重。
    - expires_at < NOW 且 status='active' 的记录，在当前风险查询中必须为 0（硬 invariant）。
    - 原始行数 total_records 永远是审计数字，绝不参与风险强度/班级排序。

设计纪律：
    - expires_at < NOW 且 status='active' 的记录，在当前风险查询中必须为 0（硬 invariant）。
    - 原始行数 total_records 永远是审计数字，绝不参与风险强度/班级排序。
"""

from __future__ import annotations

# 当前有效状态集合（status 语义：active=当前，handled/false_positive/expired=终态）
CURRENT_STATUSES = ("active",)

# 治理打标枚举
GOV_VALID_CURRENT = "VALID_CURRENT"
GOV_EXPIRED = "EXPIRED"
GOV_DUPLICATE = "DUPLICATE"
GOV_SUPERSEDED = "SUPERSEDED"
GOV_UNANCHORED = "UNANCHORED"
GOV_DATA_QUALITY_DEGRADED = "DATA_QUALITY_DEGRADED"


def current_unexpired_where(alias: str = "r") -> str:
    """CURRENT_UNEXPIRED：active + 未过期 + 未处置（不判断锚点）。"""
    a = alias
    return (
        f"{a}.status IN ('active') "
        f"AND ({a}.expires_at IS NULL OR {a}.expires_at >= NOW()) "
        f"AND {a}.handled_by IS NULL"
    )


def current_actionable_where(alias: str = "r") -> str:
    """CURRENT_ACTIONABLE：CURRENT_UNEXPIRED AND 事件锚点有效 (trigger_event_id > 0)。"""
    a = alias
    return (
        f"{a}.status IN ('active') "
        f"AND ({a}.expires_at IS NULL OR {a}.expires_at >= NOW()) "
        f"AND {a}.handled_by IS NULL "
        f"AND {a}.trigger_event_id IS NOT NULL AND {a}.trigger_event_id > 0"
    )


def current_requires_verification_where(alias: str = "r") -> str:
    """CURRENT_REQUIRES_VERIFICATION：CURRENT_UNEXPIRED AND 无事件锚点。"""
    a = alias
    return (
        f"{a}.status IN ('active') "
        f"AND ({a}.expires_at IS NULL OR {a}.expires_at >= NOW()) "
        f"AND {a}.handled_by IS NULL "
        f"AND ({a}.trigger_event_id IS NULL OR {a}.trigger_event_id = 0)"
    )


def data_quality_sql(alias: str = "r") -> str:
    """生成 data_quality / actionability 标注 SQL 片段（SELECT 列表用）。"""
    a = alias
    return (
        f"CASE WHEN {a}.trigger_event_id IS NOT NULL AND {a}.trigger_event_id > 0 "
        f"THEN 'QUALITY_OK' ELSE 'DEGRADED' END AS data_quality, "
        f"CASE WHEN {a}.trigger_event_id IS NOT NULL AND {a}.trigger_event_id > 0 "
        f"THEN 'ACTIONABLE' ELSE 'REQUIRES_VERIFICATION' END AS actionability"
    )


def is_event_anchored(row) -> bool:
    """行级判断：预警是否有事件锚点。"""
    ev = getattr(row, "trigger_event_id", None) if not isinstance(row, dict) else row.get("trigger_event_id")
    return ev is not None and int(ev) > 0


def classify_governance(*, expired: bool, unanchored: bool,
                        duplicate: bool = False, superseded: bool = False) -> str:
    """reconciliation 治理打标优先级：EXPIRED > DUPLICATE > SUPERSEDED > UNANCHORED > VALID_CURRENT。

    注：UNANCHORED 与 DATA_QUALITY_DEGRADED 语义等价（无事件锚点即质量降级），
    分类输出统一用 UNANCHORED 主标签；明细查询可同时看 DEGRADED 质量标注。
    """
    if expired:
        return GOV_EXPIRED
    if duplicate:
        return GOV_DUPLICATE
    if superseded:
        return GOV_SUPERSEDED
    if unanchored:
        return GOV_UNANCHORED
    return GOV_VALID_CURRENT
