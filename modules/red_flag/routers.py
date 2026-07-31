"""
modules/red_flag/routers.py — 流动红旗 API 端点

12 个端点覆盖完整业务流：
  数据录入 → 生成草稿 → 审核发布 → 排行榜 → 归档 → 历史趋势
"""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.routers import get_current_user, require_role, get_db, verify_entity_ownership
from core.models import User, UserRole, Class as SchoolClass
from .models import RoutineScore
from .schemas import (
    RoutineScoreCreate,
    RoutineScoreBatch,
    RoutineScoreOut,
    RoutineScoreListOut,
    FlagGenerateRequest,
    FlagEvaluationOut,
    FlagLeaderboardOut,
    FlagDraftListOut,
    PublishResult,
    ArchiveResult,
    ArchiveHistoryOut,
    TrendResult,
)
from .services import FlagService

router = APIRouter(tags=["流动红旗"])


# ═══════════════════════════════════════════════════════════════
#  数据录入 — RoutineScore CRUD
# ═══════════════════════════════════════════════════════════════

@router.post("/routines", status_code=201)
async def add_routine(
    body: RoutineScoreCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """录入一条常规评分（班主任/年级组/德育处均可按角色录入）"""
    result = await FlagService.add_routine(
        db=db,
        class_id=body.class_id,
        grade_id=body.grade_id,
        category=body.category,
        score=body.score,
        scorer_type=body.scorer_type,
        record_date=body.record_date,
        school_id=user.school_id,
        inspector=body.inspector or user.display_name,
        note=body.note,
    )
    return result


@router.post("/routines/batch", status_code=201)
async def add_routine_batch(
    body: RoutineScoreBatch,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """批量录入常规评分"""
    scores = [
        {
            "class_id": s.class_id,
            "grade_id": s.grade_id,
            "category": s.category,
            "score": s.score,
            "scorer_type": s.scorer_type,
            "record_date": s.record_date,
            "inspector": s.inspector or user.display_name,
            "note": s.note,
        }
        for s in body.scores
    ]
    return await FlagService.add_routine_batch(db, scores, user.school_id)


@router.get("/routines")
async def list_routines(
    grade_id: Optional[int] = Query(None),
    class_id: Optional[int] = Query(None),
    scorer_type: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """查询常规评分列表（支持多条件筛选 + 分页）"""
    result = await FlagService.list_routines(
        db=db,
        school_id=user.school_id,
        grade_id=grade_id or user.grade_id,
        class_id=class_id or user.class_id,
        scorer_type=scorer_type,
        category=category,
        start_date=start_date,
        end_date=end_date,
        offset=offset,
        limit=limit,
    )
    return RoutineScoreListOut(
        total=result["total"],
        items=[RoutineScoreOut.model_validate(r) for r in result["items"]],
    )


@router.delete("/routines/{routine_id}")
async def delete_routine(
    routine_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """删除一条常规评分"""
    # P0 多租户隔离：校验评分记录是否属于当前用户学校
    await verify_entity_ownership(db, RoutineScore, routine_id, user, '评分记录不存在')
    ok = await FlagService.delete_routine(db, routine_id, user.school_id)
    if not ok:
        raise HTTPException(404, "评分记录不存在")
    return {"message": "已删除"}


# ═══════════════════════════════════════════════════════════════
#  评价生成 → 发布 → 归档
# ═══════════════════════════════════════════════════════════════

@router.post("/evaluations/generate", status_code=201)
async def generate_evaluations(
    body: FlagGenerateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.MS_ADMIN)),
):
    """
    生成流动红旗评价草稿（仅德育处管理员）。

    自动跨模块聚合:
      - RoutineScore 三维度均分 → 权重重分配 → 加权底分
      - discipline_records 违纪总分 → 扣分
      - attendance_records 异常次数 → 扣分
      - 最终得分 = max(0, 加权底分 - 违纪扣分 - 考勤扣分)
    """
    result = await FlagService.generate_evaluations(
        db=db,
        school_id=user.school_id,
        grade_id=body.grade_id,
        period_type=body.period_type,
        period_label=body.period_label,
        start_date=body.start_date,
        end_date=body.end_date,
    )
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


@router.get("/evaluations/drafts")
async def view_drafts(
    grade_id: Optional[int] = Query(None),
    period_type: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    查看待发布草稿。

    德育处 → 查看全年级草稿（需传 grade_id）
    年级组/班主任 → 按 user.grade_id/user.class_id 自动限定
    """
    items = await FlagService.get_drafts(
        db=db,
        school_id=user.school_id,
        grade_id=grade_id or user.grade_id,
        period_type=period_type,
    )
    return FlagDraftListOut(
        total=len(items),
        drafts=[FlagEvaluationOut(**it) for it in items],
    )


@router.post("/evaluations/publish", status_code=201)
async def publish_evaluations(
    grade_id: int = Query(..., ge=1),
    period_type: str = Query(..., min_length=1),
    period_label: str = Query(..., min_length=1),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.MS_ADMIN)),
):
    """
    发布草稿 → 按 final_score 降序排列 → 分配 rank → 状态=published（仅德育处）
    """
    result = await FlagService.publish_evaluations(
        db=db,
        school_id=user.school_id,
        grade_id=grade_id,
        period_type=period_type,
        period_label=period_label,
    )
    if "error" in result:
        raise HTTPException(400, result["error"])
    return PublishResult(**result)


# ═══════════════════════════════════════════════════════════════
#  排行榜
# ═══════════════════════════════════════════════════════════════

@router.get("/evaluations/leaderboard")
async def get_leaderboard(
    grade_id: Optional[int] = Query(None),
    period_type: Optional[str] = Query(None),
    period_label: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """查看已发布的流动红旗排行榜（所有角色可查看）"""
    items = await FlagService.get_leaderboard(
        db=db,
        school_id=user.school_id,
        grade_id=grade_id or user.grade_id,
        period_type=period_type,
        period_label=period_label,
    )
    return [FlagEvaluationOut(**it) for it in items]


# ═══════════════════════════════════════════════════════════════
#  归档
# ═══════════════════════════════════════════════════════════════

@router.post("/evaluations/archive", status_code=201)
async def archive_evaluations(
    grade_id: int = Query(..., ge=1),
    period_type: str = Query(..., min_length=1),
    period_label: str = Query(..., min_length=1),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.MS_ADMIN)),
):
    """
    归档已发布评价 → FlagArchiveReport 物理快照（仅德育处）

    幂等防护：同周期重复归档返回 409 Conflict
    物理快照：存储完整三维明细+扣分详情，杜绝历史回溯篡改
    前 2 名自动标记 has_flag=True（获得流动红旗）
    """
    result = await FlagService.archive_evaluations(
        db=db,
        school_id=user.school_id,
        grade_id=grade_id,
        period_type=period_type,
        period_label=period_label,
        archived_by=user.id,
    )
    if result.get("already_archived"):
        raise HTTPException(409, result["error"])
    if "error" in result:
        raise HTTPException(400, result["error"])
    return ArchiveResult(**result)


@router.get("/evaluations/history")
async def get_archive_history(
    grade_id: Optional[int] = Query(None),
    class_id: Optional[int] = Query(None),
    period_type: Optional[str] = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """查询归档历史"""
    result = await FlagService.get_archive_history(
        db=db,
        school_id=user.school_id,
        grade_id=grade_id or user.grade_id,
        class_id=class_id or user.class_id,
        period_type=period_type,
        offset=offset,
        limit=limit,
    )
    return ArchiveHistoryOut(
        total=result["total"],
        items=result["items"],
    )


# ═══════════════════════════════════════════════════════════════
#  历史趋势
# ═══════════════════════════════════════════════════════════════

@router.get("/evaluations/trends/{class_id}")
async def get_class_trends(
    class_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    获取班级历史趋势（归档数据）。

    返回: periods[], scores[], ranks[], total_flags_won
    用于前端 ECharts 折线图展示排名走势
    """
    # P0 多租户隔离：校验 class_id 是否属于当前用户学校
    await verify_entity_ownership(db, SchoolClass, class_id, user, '班级不存在')

    trends = await FlagService.get_class_trends(
        db=db,
        school_id=user.school_id,
        class_id=class_id,
    )
    return TrendResult(
        status="success",
        class_id=trends["class_id"],
        class_name=trends["class_name"],
        trends=trends,
    )
