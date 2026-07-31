"""
modules/lineage/routers.py — 血缘追踪 API 端点

全部端点仅 MS_ADMIN 可访问（数据敏感）。
"""

import logging
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from core.routers import get_db, get_current_user, verify_entity_ownership
from core.models import User
from modules.lineage.services import LineageService
from modules.lineage.schemas import (
    CausalChain,
    LineageStatsOut,
    LineageQuery,
    ScoreTraceOut,
    MigrationBatchCreate,
    MigrationBatchUpdate,
    MigrationBatchOut,
    MigrationStatsOut,
)
from modules.evaluation.models import ScoreLog

logger = logging.getLogger("lineage.routers")
router = APIRouter()


@router.get("/traces/{trace_id}", response_model=CausalChain)
async def get_trace_chain(
    trace_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    查询一条完整的因果关系链
    示例: /api/v1/lineage/traces/abc-123-def
    """
    chain = await LineageService.get_trace_chain(db, trace_id)
    if not chain:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="因果链不存在")
    return chain


@router.get("/students/{student_id}")
async def get_student_lineage(
    student_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """查询学生全链路血缘"""
    return await LineageService.get_student_lineage(db, student_id, page, page_size)


@router.get("/sources/{source_type}/{source_id}")
async def get_source_descendants(
    source_type: str,
    source_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    查询某个源实体的全部下游影响
    示例: /api/v1/lineage/sources/discipline_record/42
    """
    chains = await LineageService.get_source_descendants(db, source_type, source_id)
    return {"source_type": source_type, "source_id": source_id, "chains": [c.model_dump() for c in chains]}


@router.get("/stats", response_model=LineageStatsOut)
async def get_lineage_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """血缘统计概览 — 仪表盘用"""
    return await LineageService.get_stats(db, current_user.school_id)


@router.get("/search")
async def search_lineage(
    student_id: int = Query(None),
    source_type: str = Query(None),
    source_id: int = Query(None),
    target_type: str = Query(None),
    target_id: int = Query(None),
    transformation: str = Query(None),
    trace_id: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """灵活多条件血缘查询"""
    return await LineageService.search_lineage(
        db=db,
        school_id=current_user.school_id,
        student_id=student_id,
        source_type=source_type,
        source_id=source_id,
        target_type=target_type,
        target_id=target_id,
        transformation=transformation,
        trace_id=trace_id,
        page=page,
        page_size=page_size,
    )


# ═══════════════════════════════════════════════════════════
# #1193 成绩出生证明
# ═══════════════════════════════════════════════════════════

@router.get("/trace/{score_log_id}", response_model=ScoreTraceOut)
async def get_score_trace(
    score_log_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    成绩出生证明 — 从 ScoreLog 倒追完整血缘链。

    回答核心问题：
      "这条扣分记录是谁、在什么时间、通过什么业务链产生的？"
      "从源事件 → 中间转换 → 最终快照，完整链路是怎样的？"

    返回值结构:
      - score_log:         评分流水本身的完整信息（操作者/学生/班级/IP/变更前后快照）
      - causal_chain:      关联的血缘因果链（如果 trace_context_id 有值）
      - related_events:    同学生的最近 10 条血缘事件
      - lineage_status:    追踪状态（tracked/untracked/orphaned）

    权限控制：多租户隔离 + MS_ADMIN/GRADE_LEADER/CLASS_TEACHER
    """
    # 多租户隔离 — 先查出 ScoreLog 验证 school_id
    result = await db.execute(
        select(ScoreLog).where(ScoreLog.id == score_log_id)
    )
    score_log = result.scalar_one_or_none()
    await verify_entity_ownership(score_log, current_user, "ScoreLog")

    trace = await LineageService.get_score_trace(db, score_log_id)
    if not trace:
        raise HTTPException(status_code=404, detail="评分流水不存在")

    return trace


# ═══════════════════════════════════════════════════════════
# 数据迁移批次追踪
# ═══════════════════════════════════════════════════════════

@router.post("/migration/batches", status_code=201, response_model=MigrationBatchOut)
async def create_migration_batch(
    body: MigrationBatchCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    创建数据迁移批次记录。
    用于旧数据迁移流程的第一步: 开工前先注册批次UUID,
    后续逐行写入时携带此 batch_id 关联 sync_batch。
    """
    return await LineageService.create_migration_batch(
        db=db, data=body, school_id=current_user.school_id,
        created_by=current_user.id,
    )


@router.put("/migration/batches/{batch_id}", response_model=MigrationBatchOut)
async def update_migration_batch(
    batch_id: str,
    body: MigrationBatchUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    更新迁移批次进度:
    - 迁移开始: status="processing"
    - 迁移完成: status="completed"/"completed_with_errors"/"failed"
    - 增量更新: success_rows/failed_rows/skipped_rows
    """
    result = await LineageService.update_migration_batch(db, batch_id, body)
    if not result:
        raise HTTPException(status_code=404, detail="批次不存在")
    return result


@router.get("/migration/batches/{batch_id}", response_model=MigrationBatchOut)
async def get_migration_batch(
    batch_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """查询单个迁移批次详情"""
    result = await LineageService.get_migration_batch(db, batch_id)
    if not result:
        raise HTTPException(status_code=404, detail="批次不存在")
    return result


@router.get("/migration/batches")
async def list_migration_batches(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    target_table: str = Query(None),
    status: str = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """列出数据迁移批次（分页+筛选）"""
    return await LineageService.list_migration_batches(
        db=db, school_id=current_user.school_id,
        page=page, page_size=page_size,
        target_table=target_table, status=status,
    )


@router.get("/migration/stats", response_model=MigrationStatsOut)
async def get_migration_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """数据迁移统计概览"""
    return await LineageService.get_migration_stats(
        db=db, school_id=current_user.school_id,
    )
