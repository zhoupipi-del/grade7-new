"""
modules/lineage/schemas.py — 血缘追踪 Pydantic 模型
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

# ═══════════════════════════════════════════════════════════
# 迁移批次 Schema
# ═══════════════════════════════════════════════════════════


class MigrationBatchCreate(BaseModel):
    """创建迁移批次"""

    batch_id: str = Field(..., description="批次UUID")
    source_type: str = Field(..., description="mysql_legacy/sqlite_dump/excel/csv/api")
    source_desc: str | None = None
    target_table: str = Field(..., description="目标表名")
    total_rows: int = Field(0, ge=0)
    mapping_config: dict[str, Any] | None = None
    transform_script: str | None = None


class MigrationBatchUpdate(BaseModel):
    """更新迁移批次进度"""

    status: str | None = None
    success_rows: int | None = None
    failed_rows: int | None = None
    skipped_rows: int | None = None
    errors_summary: list[dict[str, Any]] | None = None


class MigrationBatchOut(BaseModel):
    """迁移批次响应"""

    id: int
    batch_id: str
    source_type: str
    source_desc: str | None = None
    target_table: str
    status: str
    total_rows: int
    success_rows: int
    failed_rows: int
    skipped_rows: int
    errors_summary: Any | None = None
    mapping_config: Any | None = None
    transform_script: str | None = None
    created_by: int | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class MigrationStatsOut(BaseModel):
    """迁移统计概览"""

    total_batches: int
    active_batches: int
    total_migrated_rows: int
    by_status: dict[str, int]
    by_target_table: dict[str, int]
    recent_batches: list[MigrationBatchOut]


# ═══════════════════════════════════════════════════════════
# 事件 Schema
# ═══════════════════════════════════════════════════════════


class LineageEventOut(BaseModel):
    """血缘事件响应"""

    id: int
    school_id: int
    trace_id: str
    source_type: str
    source_id: int | None = None
    source_batch: dict[str, Any] | None = None
    target_type: str
    target_id: int | None = None
    transformation: str
    context: dict[str, Any] | None = None
    triggered_by: str | None = None
    lineage_depth: int
    student_id: int | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class LineageEventListItem(BaseModel):
    """血缘事件列表项（精简）"""

    id: int
    trace_id: str
    source_type: str
    source_id: int | None = None
    target_type: str
    target_id: int | None = None
    transformation: str
    student_id: int | None = None
    lineage_depth: int
    created_at: datetime

    model_config = {"from_attributes": True}


# ═══════════════════════════════════════════════════════════
# 因果关系链 Schema
# ═══════════════════════════════════════════════════════════


class CausalNode(BaseModel):
    """因果链中的一个节点"""

    id: int
    transformation: str
    source_type: str
    target_type: str
    lineage_depth: int
    context: dict[str, Any] | None = None
    created_at: datetime


class CausalChain(BaseModel):
    """完整的因果关系链"""

    trace_id: str
    student_id: int | None = None
    nodes: list[CausalNode]
    total_depth: int
    started_at: datetime | None = None
    ended_at: datetime | None = None


# ═══════════════════════════════════════════════════════════
# 查询参数
# ═══════════════════════════════════════════════════════════


class LineageQuery(BaseModel):
    """血缘查询参数"""

    student_id: int | None = Field(None, description="学生ID")
    source_type: str | None = Field(None, description="源实体类型")
    source_id: int | None = Field(None, description="源实体ID")
    target_type: str | None = Field(None, description="目标实体类型")
    target_id: int | None = Field(None, description="目标实体ID")
    transformation: str | None = Field(None, description="转换类型")
    trace_id: str | None = Field(None, description="因果链ID")
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)


class LineageStatsOut(BaseModel):
    """血缘统计概览"""

    total_events: int
    total_traces: int
    by_transformation: dict[str, int]
    by_source_type: dict[str, int]
    by_target_type: dict[str, int]
    recent_events: list[LineageEventListItem]


# ═══════════════════════════════════════════════════════════
# #1193 成绩出生证明 Schema
# ═══════════════════════════════════════════════════════════


class ScoreLogBrief(BaseModel):
    """ScoreLog 简明信息 — 成绩出生证明的核心数据"""

    id: int
    student_id: int
    student_name: str | None = None
    class_name: str | None = None
    dimension: str | None = None
    change_amount: float
    before_score: float
    after_score: float
    reason: str
    source_type: str
    source_id: int | None = None
    policy_tag: str | None = None
    actor_id: int | None = None
    actor_name: str | None = None
    source_ip: str | None = None
    diff_snapshot: dict[str, Any] | None = None
    created_at: datetime


class ScoreTraceOut(BaseModel):
    """成绩出生证明 — 从 ScoreLog 倒追完整血缘链

    回答家长最关心的问题：
    "我家孩子为什么被扣了 X 分？谁扣的？什么时候？在哪条业务链上？"
    """

    score_log: ScoreLogBrief
    causal_chain: CausalChain | None = Field(
        None, description="关联的血缘因果链（trace_context_id → LineageEvent 全链路）"
    )
    related_events: list[LineageEventListItem] = Field(
        default_factory=list, description="同学生的最近 10 条血缘事件"
    )
    lineage_status: str = Field(
        "untracked",
        description="血缘追踪状态: tracked(已追踪) | untracked(未追踪) | orphaned(追踪链断裂)",
    )
