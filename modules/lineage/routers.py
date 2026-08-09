"""
modules/lineage/routers.py — 血缘追踪 API 端点

全部端点仅 MS_ADMIN 可访问（数据敏感）。
"""

import logging

from core.models import User, UserRole
from core.routers import get_current_user, get_db, require_role, verify_entity_ownership
from fastapi import APIRouter, Depends, HTTPException, Query
from modules.evaluation.models import ScoreLog
from modules.lineage.schemas import (
    CausalChain,
    LineageStatsOut,
    MigrationBatchCreate,
    MigrationBatchOut,
    MigrationBatchUpdate,
    MigrationStatsOut,
    ScoreTraceOut,
)
from modules.lineage.services import LineageService
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("lineage.routers")
router = APIRouter(
    dependencies=[Depends(require_role(UserRole.MS_ADMIN))],
)


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
    # P0 修复: 多租户隔离 — 验证因果链归属
    from modules.lineage.models import CausalChain as CausalChainModel

    chain = await LineageService.get_trace_chain(db, trace_id)
    if not chain:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="因果链不存在")
    # 校验 school_id 归属（CausalChain 如有 school_id 列）
    if hasattr(chain, "school_id") and chain.school_id is not None:
        accessible_ids = await __get_accessible_ids(current_user, db)
        if chain.school_id not in accessible_ids:
            raise HTTPException(status_code=403, detail="无权访问其他学校的数据")
    return chain


async def __get_accessible_ids(current_user: User, db: AsyncSession) -> list[int]:
    """内部辅助：获取当前用户的 access_scope（避免循环导入）"""
    from core.tenant_context import get_accessible_school_ids

    return await get_accessible_school_ids(current_user, db)


@router.get("/students/{student_id}")
async def get_student_lineage(
    student_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """查询学生全链路血缘"""
    # P0 修复: 多租户隔离 — 验证学生归属
    from core.models import Student

    await verify_entity_ownership(db, Student, student_id, current_user, "学生不存在")
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
    # P0 修复: 多租户隔离 — lineage_events 按 school_id 过滤
    # source_id 本身是外键引用，通过 WHERE school_id 隔离
    accessible_ids = await __get_accessible_ids(current_user, db)
    chains = await LineageService.get_source_descendants(db, source_type, source_id)
    # 过滤出当前用户有权访问的链（基于源实体的 school_id）
    filtered = [c for c in chains if getattr(c, "school_id", None) in accessible_ids or c.school_id is None]
    return {
        "source_type": source_type,
        "source_id": source_id,
        "chains": [c.model_dump() for c in filtered],
    }


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
    # P0 修复: 多租户隔离 — 使用正确的 verify_entity_ownership 签名
    # （原调用参数顺序错误：传了 entity 对象而非 db/model_class/entity_id）
    await verify_entity_ownership(db, ScoreLog, score_log_id, current_user, "评分流水不存在")

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
        db=db,
        data=body,
        school_id=current_user.school_id,
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
    # P0 修复: 多租户隔离 — 验证批次归属
    result = await LineageService.get_migration_batch(db, batch_id)
    if not result:
        raise HTTPException(status_code=404, detail="批次不存在")
    accessible_ids = await __get_accessible_ids(current_user, db)
    if getattr(result, "school_id", None) is not None and result.school_id not in accessible_ids:
        raise HTTPException(status_code=403, detail="无权访问其他学校的数据")
    # 重新获取以更新（上面已校验过权限）
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
    # P0 修复: 多租户隔离 — 验证批次归属
    result = await LineageService.get_migration_batch(db, batch_id)
    if not result:
        raise HTTPException(status_code=404, detail="批次不存在")
    accessible_ids = await __get_accessible_ids(current_user, db)
    if getattr(result, "school_id", None) is not None and result.school_id not in accessible_ids:
        raise HTTPException(status_code=403, detail="无权访问其他学校的数据")
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
        db=db,
        school_id=current_user.school_id,
        page=page,
        page_size=page_size,
        target_table=target_table,
        status=status,
    )


@router.get("/migration/stats", response_model=MigrationStatsOut)
async def get_migration_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """数据迁移统计概览"""
    return await LineageService.get_migration_stats(
        db=db,
        school_id=current_user.school_id,
    )
