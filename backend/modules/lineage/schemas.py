"""
modules/lineage/schemas.py — 血缘追踪 Pydantic 模型
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════
# 事件 Schema
# ═══════════════════════════════════════════════════════════

class LineageEventOut(BaseModel):
    """血缘事件响应"""
    id: int
    school_id: int
    trace_id: str
    source_type: str
    source_id: Optional[int] = None
    source_batch: Optional[Dict[str, Any]] = None
    target_type: str
    target_id: Optional[int] = None
    transformation: str
    context: Optional[Dict[str, Any]] = None
    triggered_by: Optional[str] = None
    lineage_depth: int
    student_id: Optional[int] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class LineageEventListItem(BaseModel):
    """血缘事件列表项（精简）"""
    id: int
    trace_id: str
    source_type: str
    source_id: Optional[int] = None
    target_type: str
    target_id: Optional[int] = None
    transformation: str
    student_id: Optional[int] = None
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
    context: Optional[Dict[str, Any]] = None
    created_at: datetime


class CausalChain(BaseModel):
    """完整的因果关系链"""
    trace_id: str
    student_id: Optional[int] = None
    nodes: List[CausalNode]
    total_depth: int
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None


# ═══════════════════════════════════════════════════════════
# 查询参数
# ═══════════════════════════════════════════════════════════

class LineageQuery(BaseModel):
    """血缘查询参数"""
    student_id: Optional[int] = Field(None, description="学生ID")
    source_type: Optional[str] = Field(None, description="源实体类型")
    source_id: Optional[int] = Field(None, description="源实体ID")
    target_type: Optional[str] = Field(None, description="目标实体类型")
    target_id: Optional[int] = Field(None, description="目标实体ID")
    transformation: Optional[str] = Field(None, description="转换类型")
    trace_id: Optional[str] = Field(None, description="因果链ID")
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)


class LineageStatsOut(BaseModel):
    """血缘统计概览"""
    total_events: int
    total_traces: int
    by_transformation: Dict[str, int]
    by_source_type: Dict[str, int]
    by_target_type: Dict[str, int]
    recent_events: List[LineageEventListItem]


# ═══════════════════════════════════════════════════════════
# #1193 成绩出生证明 Schema
# ═══════════════════════════════════════════════════════════

class ScoreLogBrief(BaseModel):
    """ScoreLog 简明信息 — 成绩出生证明的核心数据"""
    id: int
    student_id: int
    student_name: Optional[str] = None
    class_name: Optional[str] = None
    dimension: Optional[str] = None
    change_amount: float
    before_score: float
    after_score: float
    reason: str
    source_type: str
    source_id: Optional[int] = None
    policy_tag: Optional[str] = None
    actor_id: Optional[int] = None
    actor_name: Optional[str] = None
    source_ip: Optional[str] = None
    diff_snapshot: Optional[Dict[str, Any]] = None
    created_at: datetime


class ScoreTraceOut(BaseModel):
    """成绩出生证明 — 从 ScoreLog 倒追完整血缘链

    回答家长最关心的问题：
    "我家孩子为什么被扣了 X 分？谁扣的？什么时候？在哪条业务链上？"
    """
    score_log: ScoreLogBrief
    causal_chain: Optional[CausalChain] = Field(
        None, description="关联的血缘因果链（trace_context_id → LineageEvent 全链路）"
    )
    related_events: List[LineageEventListItem] = Field(
        default_factory=list, description="同学生的最近 10 条血缘事件"
    )
    lineage_status: str = Field(
        "untracked", description="血缘追踪状态: tracked(已追踪) | untracked(未追踪) | orphaned(追踪链断裂)"
    )
