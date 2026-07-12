"""
research_observation/routers.py — 听课评课量化追踪 API 网关

端点清单 (15个):
  POST   /                           创建听课记录
  GET    /                           听课列表(分页+多维度筛选)
  GET    /dashboard                  听课统计看板
  GET    /teacher/{teacher_id}       教师被听课历史
  GET    /{obs_id}                   听课详情(含评分矩阵+反馈历史)
  PUT    /{obs_id}                   更新听课记录(仅pending)
  DELETE /{obs_id}                   删除听课记录(仅pending)

  POST   /{obs_id}/rubric            提交多维评分
  GET    /{obs_id}/rubric            获取评分矩阵

  POST   /{obs_id}/confirm           教师确认评课
  POST   /{obs_id}/appeal            教师申诉
  POST   /{obs_id}/resolve           处理申诉(组长/管理员)

  GET    /{obs_id}/appeals           反馈/申诉历史
  GET    /{obs_id}/compare-plan      对比备课教案(预留)
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from core.routers import get_db, get_current_user
from core.models import User
from . import schemas, services
from .models import FEEDBACK_PENDING

router = APIRouter(tags=["听课评课量化追踪"])

ROLE_MS_ADMIN = "MS_ADMIN"
ROLE_GRADE_LEADER = "GRADE_LEADER"
ROLE_CLASS_TEACHER = "CLASS_TEACHER"


# ═══════════════════════════════════════════════
# 权限校验
# ═══════════════════════════════════════════════

def _can_observe(user: User) -> bool:
    """谁能听课 (听课人)"""
    return user.role in (ROLE_MS_ADMIN, ROLE_GRADE_LEADER, ROLE_CLASS_TEACHER)


def _can_manage_observation(user: User, observer_id: int) -> bool:
    """谁能管理听课记录"""
    if user.role == ROLE_MS_ADMIN:
        return True
    if user.role == ROLE_GRADE_LEADER:
        return True
    if user.role == ROLE_CLASS_TEACHER and user.id == observer_id:
        return True
    return False


def _can_resolve(user: User) -> bool:
    """谁能处理申诉"""
    return user.role in (ROLE_MS_ADMIN, ROLE_GRADE_LEADER)


# ═══════════════════════════════════════════════
# 听课记录 CRUD
# ═══════════════════════════════════════════════

@router.post("/", response_model=schemas.ObservationResponse, status_code=201)
async def api_create_observation(
    payload: schemas.ObservationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建听课记录"""
    if not _can_observe(current_user):
        raise HTTPException(403, "无权听课: 需教师/组长/管理员角色")

    # 不能听自己的课
    if payload.teacher_id == current_user.id:
        raise HTTPException(400, "不能听自己的课")

    obs = await services.create_observation(
        db, current_user.school_id, current_user.id, payload,
    )
    name_map = await services._get_user_names_batch(
        db, [obs.observer_id, obs.teacher_id]
    )
    return services._obs_to_dict(obs, name_map)


@router.get("/")
async def api_list_observations(
    observer_id: Optional[int] = Query(None),
    teacher_id: Optional[int] = Query(None),
    class_id: Optional[int] = Query(None),
    subject_code: Optional[str] = Query(None),
    feedback_status: Optional[str] = Query(None),
    observation_type: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """听课列表 (分页+多维度筛选)"""
    items, total = await services.list_observations(
        db, current_user.school_id,
        observer_id=observer_id,
        teacher_id=teacher_id,
        class_id=class_id,
        subject_code=subject_code,
        feedback_status=feedback_status,
        observation_type=observation_type,
        page=page, page_size=page_size,
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/dashboard", response_model=schemas.DashboardStats)
async def api_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """听课统计看板"""
    stats = await services.get_dashboard_stats(db, current_user.school_id)
    return stats


@router.get("/teacher/{teacher_id}")
async def api_teacher_history(
    teacher_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """教师被听课历史"""
    # 教师本人或管理员/组长可查
    if current_user.id != teacher_id and current_user.role not in (ROLE_MS_ADMIN, ROLE_GRADE_LEADER):
        raise HTTPException(403, "无权查看他人听课历史")

    items, total = await services.get_teacher_history(
        db, current_user.school_id, teacher_id, page, page_size,
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/{obs_id}", response_model=schemas.ObservationDetailResponse)
async def api_get_observation(
    obs_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """听课详情 (含评分矩阵+反馈历史)"""
    obs = await services.get_observation(db, current_user.school_id, obs_id)
    if not obs:
        raise HTTPException(404, "听课记录不存在")

    name_map = await services._get_user_names_batch(
        db, [obs.observer_id, obs.teacher_id]
    )

    # 获取评分
    rubric = await services.get_rubric(db, current_user.school_id, obs_id)
    rubric_dict = None
    if rubric:
        scorer_name = await services._get_user_name(db, rubric.scorer_id)
        rubric_dict = {
            "id": rubric.id, "observation_id": rubric.observation_id,
            "template_name": rubric.template_name,
            "rubric_metrics": rubric.rubric_metrics or [],
            "total_score": rubric.total_score,
            "max_score": rubric.max_score,
            "percentage": rubric.percentage,
            "scorer_id": rubric.scorer_id, "scorer_name": scorer_name,
            "created_at": rubric.created_at,
        }

    # 获取反馈历史
    appeals, _ = await services.list_appeals(db, current_user.school_id, obs_id)

    base = services._obs_to_dict(obs, name_map)
    return {
        **base,
        "rubric": rubric_dict,
        "appeals": appeals,
        "plan_title": None,  # 预留: 从lesson_plan获取
        "plan_status": None,
    }


@router.put("/{obs_id}", response_model=schemas.ObservationResponse)
async def api_update_observation(
    obs_id: int,
    payload: schemas.ObservationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新听课记录 (仅pending状态可改)"""
    obs = await services.get_observation(db, current_user.school_id, obs_id)
    if not obs:
        raise HTTPException(404, "听课记录不存在")

    if not _can_manage_observation(current_user, obs.observer_id):
        raise HTTPException(403, "无权修改他人听课记录")

    updated = await services.update_observation(
        db, current_user.school_id, obs_id, payload,
    )
    if not updated:
        raise HTTPException(400, "更新失败: 记录不存在或当前状态不允许修改")

    name_map = await services._get_user_names_batch(
        db, [updated.observer_id, updated.teacher_id]
    )
    return services._obs_to_dict(updated, name_map)


@router.delete("/{obs_id}")
async def api_delete_observation(
    obs_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除听课记录 (仅pending状态可删)"""
    obs = await services.get_observation(db, current_user.school_id, obs_id)
    if not obs:
        raise HTTPException(404, "听课记录不存在")

    if not _can_manage_observation(current_user, obs.observer_id):
        raise HTTPException(403, "无权删除他人听课记录")

    ok = await services.delete_observation(db, current_user.school_id, obs_id)
    if not ok:
        raise HTTPException(400, "删除失败: 记录不存在或当前状态不允许删除")
    return {"message": "已删除"}


# ═══════════════════════════════════════════════
# 多维量化评分
# ═══════════════════════════════════════════════

@router.post("/{obs_id}/rubric", response_model=schemas.RubricResponse, status_code=201)
async def api_submit_rubric(
    obs_id: int,
    payload: schemas.RubricSubmit,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """提交多维评分"""
    obs = await services.get_observation(db, current_user.school_id, obs_id)
    if not obs:
        raise HTTPException(404, "听课记录不存在")

    if not _can_manage_observation(current_user, obs.observer_id):
        raise HTTPException(403, "无权评分: 仅听课人本人或组长/管理员")

    result = await services.submit_rubric(
        db, current_user.school_id, obs_id, current_user.id, payload,
    )
    if not result:
        raise HTTPException(500, "评分提交失败")

    rubric, _ = result
    scorer_name = await services._get_user_name(db, rubric.scorer_id)
    return {
        "id": rubric.id, "observation_id": rubric.observation_id,
        "template_name": rubric.template_name,
        "rubric_metrics": rubric.rubric_metrics or [],
        "total_score": rubric.total_score,
        "max_score": rubric.max_score,
        "percentage": rubric.percentage,
        "scorer_id": rubric.scorer_id, "scorer_name": scorer_name,
        "created_at": rubric.created_at,
    }


@router.get("/{obs_id}/rubric", response_model=schemas.RubricResponse)
async def api_get_rubric(
    obs_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取评分矩阵"""
    obs = await services.get_observation(db, current_user.school_id, obs_id)
    if not obs:
        raise HTTPException(404, "听课记录不存在")

    rubric = await services.get_rubric(db, current_user.school_id, obs_id)
    if not rubric:
        raise HTTPException(404, "评分不存在")

    scorer_name = await services._get_user_name(db, rubric.scorer_id)
    return {
        "id": rubric.id, "observation_id": rubric.observation_id,
        "template_name": rubric.template_name,
        "rubric_metrics": rubric.rubric_metrics or [],
        "total_score": rubric.total_score,
        "max_score": rubric.max_score,
        "percentage": rubric.percentage,
        "scorer_id": rubric.scorer_id, "scorer_name": scorer_name,
        "created_at": rubric.created_at,
    }


# ═══════════════════════════════════════════════
# 教师确认/申诉状态机
# ═══════════════════════════════════════════════

@router.post("/{obs_id}/confirm", response_model=schemas.ObservationResponse)
async def api_teacher_confirm(
    obs_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """教师确认评课结果 (PENDING → CONFIRMED)"""
    obs = await services.teacher_confirm(
        db, current_user.school_id, obs_id, current_user.id,
    )
    if not obs:
        raise HTTPException(400, "确认失败: 记录不存在、非本人或当前状态不允许确认")

    name_map = await services._get_user_names_batch(
        db, [obs.observer_id, obs.teacher_id]
    )
    return services._obs_to_dict(obs, name_map)


@router.post("/{obs_id}/appeal", response_model=schemas.ObservationResponse)
async def api_teacher_appeal(
    obs_id: int,
    payload: schemas.TeacherAppeal,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """教师申诉 (PENDING → APPEALED)"""
    obs = await services.teacher_appeal(
        db, current_user.school_id, obs_id, current_user.id, payload,
    )
    if not obs:
        raise HTTPException(400, "申诉失败: 记录不存在、非本人或当前状态不允许申诉")

    name_map = await services._get_user_names_batch(
        db, [obs.observer_id, obs.teacher_id]
    )
    return services._obs_to_dict(obs, name_map)


@router.post("/{obs_id}/resolve", response_model=schemas.ObservationResponse)
async def api_resolve_appeal(
    obs_id: int,
    payload: schemas.AppealResolve,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """处理申诉 (APPEALED → RESOLVED)"""
    if not _can_resolve(current_user):
        raise HTTPException(403, "无权处理申诉: 需组长/管理员角色")

    obs = await services.resolve_appeal(
        db, current_user.school_id, obs_id, current_user.id, payload,
    )
    if not obs:
        raise HTTPException(400, "处理失败: 记录不存在或当前状态不允许处理")

    name_map = await services._get_user_names_batch(
        db, [obs.observer_id, obs.teacher_id]
    )
    return services._obs_to_dict(obs, name_map)


@router.get("/{obs_id}/appeals")
async def api_list_appeals(
    obs_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """反馈/申诉历史"""
    obs = await services.get_observation(db, current_user.school_id, obs_id)
    if not obs:
        raise HTTPException(404, "听课记录不存在")

    items, total = await services.list_appeals(db, current_user.school_id, obs_id)
    return {"items": items, "total": total}
