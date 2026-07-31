"""
research_lesson_prep/routers.py — 集体备课协同编辑 API 网关

端点清单 (16个):
  POST   /                          创建教案
  GET    /                          教案列表(分页+筛选)
  GET    /{plan_id}                 教案详情(含最新版本内容)
  PUT    /{plan_id}                 更新教案元信息
  DELETE /{plan_id}                 删除教案(draft/review/approved可删)

  POST   /{plan_id}/versions        创建新版本快照
  GET    /{plan_id}/versions        版本历史
  GET    /{plan_id}/versions/{ver}  获取特定版本

  POST   /{plan_id}/reviews         添加批注
  GET    /{plan_id}/reviews         批注列表
  PUT    /{plan_id}/reviews/{rid}   标记批注已解决

  POST   /{plan_id}/submit          提交评议 (DRAFT→REVIEW)
  POST   /{plan_id}/approve         审核通过 (REVIEW→APPROVED)
  POST   /{plan_id}/publish         发布 (APPROVED→PUBLISHED)
  POST   /{plan_id}/reject          打回 (→DRAFT)

  POST   /{plan_id}/fork            Fork派生新教案
  GET    /dashboard                 教研看板统计
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from core.routers import get_db, get_current_user
from core.models import User
from . import schemas, services
from .models import (
    STATUS_DRAFT, STATUS_COLLECTIVE_REVIEW,
    STATUS_ADMIN_APPROVE, STATUS_PUBLISHED,
)

router = APIRouter(tags=["集体备课协同编辑"])

# 角色常量
ROLE_MS_ADMIN = "MS_ADMIN"
ROLE_GRADE_LEADER = "GRADE_LEADER"
ROLE_CLASS_TEACHER = "CLASS_TEACHER"


# ═══════════════════════════════════════════════
# 权限校验
# ═══════════════════════════════════════════════

def _can_create(user: User) -> bool:
    """谁能创建教案"""
    role = user.role.upper() if isinstance(user.role, str) else str(user.role).upper()
    return role in (ROLE_MS_ADMIN, ROLE_GRADE_LEADER, ROLE_CLASS_TEACHER)


def _can_manage_plan(user: User, plan_creator_id: int) -> bool:
    """谁能管理教案 (创建者本人 或 管理员/组长)"""
    role = user.role.upper() if isinstance(user.role, str) else str(user.role).upper()
    if role == ROLE_MS_ADMIN:
        return True
    if role == ROLE_GRADE_LEADER:
        return True
    if role == ROLE_CLASS_TEACHER and user.id == plan_creator_id:
        return True
    return False


def _can_review(user: User) -> bool:
    """谁能批注/审核/发布"""
    role = user.role.upper() if isinstance(user.role, str) else str(user.role).upper()
    return role in (ROLE_MS_ADMIN, ROLE_GRADE_LEADER)


# ═══════════════════════════════════════════════
# 教案 CRUD
# ═══════════════════════════════════════════════

@router.post("/", response_model=schemas.PlanDetailResponse, status_code=201)
async def api_create_plan(
    payload: schemas.PlanCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建备课主案 (含V1初始版本)"""
    if not _can_create(current_user):
        raise HTTPException(403, "无权创建教案: 需教师/组长/管理员角色")

    plan, version = await services.create_plan(
        db, current_user.school_id, current_user.id, payload,
    )

    # 构造详情响应
    return {
        **_plan_to_dict(plan, current_user.display_name),
        "latest_content": version.content_json,
        "latest_version_number": version.version_number,
        "unresolved_review_count": 0,
    }


@router.get("/")
async def api_list_plans(
    subject_code: Optional[str] = Query(None),
    grade_level: Optional[str] = Query(None),
    plan_status: Optional[str] = Query(None, alias="status"),
    creator_id: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """教案列表 (分页+筛选)"""
    items, total = await services.list_plans(
        db, current_user.school_id,
        subject_code=subject_code,
        grade_level=grade_level,
        status=plan_status,
        creator_id=creator_id,
        page=page, page_size=page_size,
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/dashboard", response_model=schemas.DashboardStats)
async def api_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """教研看板统计"""
    stats = await services.get_dashboard_stats(db, current_user.school_id)
    return stats


@router.get("/{plan_id}", response_model=schemas.PlanDetailResponse)
async def api_get_plan(
    plan_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """教案详情 (含最新版本内容)"""
    plan = await services.get_plan(db, current_user.school_id, plan_id)
    if not plan:
        raise HTTPException(404, "教案不存在")

    # 获取最新版本
    versions, _ = await services.list_versions(db, current_user.school_id, plan_id)
    latest = versions[0] if versions else None

    # 获取未解决批注数
    _, unresolved_count = await services.list_reviews(
        db, current_user.school_id, plan_id, unresolved_only=True,
    )

    creator_name = await services._get_user_name(db, plan.creator_id)

    return {
        **_plan_to_dict(plan, creator_name),
        "latest_content": latest["content"] if latest else None,
        "latest_version_number": latest["version_number"] if latest else None,
        "unresolved_review_count": unresolved_count,
    }


@router.put("/{plan_id}", response_model=schemas.PlanResponse)
async def api_update_plan(
    plan_id: int,
    payload: schemas.PlanUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新教案元信息"""
    plan = await services.get_plan(db, current_user.school_id, plan_id)
    if not plan:
        raise HTTPException(404, "教案不存在")

    if not _can_manage_plan(current_user, plan.creator_id):
        raise HTTPException(403, "无权修改他人教案")

    updated = await services.update_plan(db, current_user.school_id, plan_id, payload)
    creator_name = await services._get_user_name(db, updated.creator_id)
    return _plan_to_dict(updated, creator_name)


@router.delete("/{plan_id}")
async def api_delete_plan(
    plan_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除教案 (已发布的不允许删除)"""
    plan = await services.get_plan(db, current_user.school_id, plan_id)
    if not plan:
        raise HTTPException(404, "教案不存在")

    if not _can_manage_plan(current_user, plan.creator_id):
        raise HTTPException(403, "无权删除他人教案")

    if plan.status == STATUS_PUBLISHED:
        raise HTTPException(400, "已发布的教案不允许删除, 请联系管理员下线")

    ok = await services.delete_plan(db, current_user.school_id, plan_id)
    if not ok:
        raise HTTPException(500, "删除失败")
    return {"message": "已删除"}


# ═══════════════════════════════════════════════
# 版本控制
# ═══════════════════════════════════════════════

@router.post("/{plan_id}/versions", response_model=schemas.VersionResponse, status_code=201)
async def api_create_version(
    plan_id: int,
    payload: schemas.VersionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建新版本快照 (保存内容)"""
    plan = await services.get_plan(db, current_user.school_id, plan_id)
    if not plan:
        raise HTTPException(404, "教案不存在")

    if not _can_manage_plan(current_user, plan.creator_id):
        raise HTTPException(403, "无权编辑他人教案")

    if plan.status not in (STATUS_DRAFT, STATUS_COLLECTIVE_REVIEW):
        raise HTTPException(400, f"当前状态({plan.status})不允许编辑, 请先打回草稿")

    version = await services.create_version(
        db, current_user.school_id, plan_id, current_user.id, payload,
    )
    if not version:
        raise HTTPException(500, "版本创建失败")

    editor_name = await services._get_user_name(db, version.editor_id)
    return {
        "id": version.id, "plan_id": version.plan_id,
        "version_number": version.version_number,
        "editor_id": version.editor_id, "editor_name": editor_name,
        "content": version.content_json,
        "change_log": version.change_log,
        "is_major": version.is_major,
        "created_at": version.created_at,
    }


@router.get("/{plan_id}/versions")
async def api_list_versions(
    plan_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """版本历史"""
    plan = await services.get_plan(db, current_user.school_id, plan_id)
    if not plan:
        raise HTTPException(404, "教案不存在")

    items, total = await services.list_versions(db, current_user.school_id, plan_id)
    return {"items": items, "total": total}


@router.get("/{plan_id}/versions/{version_number}", response_model=schemas.VersionResponse)
async def api_get_version(
    plan_id: int,
    version_number: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取特定版本"""
    version = await services.get_version(
        db, current_user.school_id, plan_id, version_number,
    )
    if not version:
        raise HTTPException(404, "版本不存在")

    editor_name = await services._get_user_name(db, version.editor_id)
    return {
        "id": version.id, "plan_id": version.plan_id,
        "version_number": version.version_number,
        "editor_id": version.editor_id, "editor_name": editor_name,
        "content": version.content_json,
        "change_log": version.change_log,
        "is_major": version.is_major,
        "created_at": version.created_at,
    }


# ═══════════════════════════════════════════════
# 协同批注
# ═══════════════════════════════════════════════

@router.post("/{plan_id}/reviews", response_model=schemas.ReviewResponse, status_code=201)
async def api_create_review(
    plan_id: int,
    payload: schemas.ReviewCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """添加批注 (仅REVIEW状态可批注)"""
    if not _can_review(current_user):
        raise HTTPException(403, "无权批注: 需组长/管理员角色")

    review = await services.create_review(
        db, current_user.school_id, current_user.id, plan_id, payload,
    )
    if not review:
        raise HTTPException(400, "批注失败: 教案不存在或当前状态不允许批注")

    reviewer_name = await services._get_user_name(db, review.reviewer_id)
    return {
        "id": review.id, "plan_id": review.plan_id,
        "version_number": review.version_number,
        "reviewer_id": review.reviewer_id, "reviewer_name": reviewer_name,
        "target_section": review.target_section,
        "target_anchor": review.target_anchor,
        "comment": review.comment, "severity": review.severity,
        "is_resolved": review.is_resolved,
        "resolved_by": review.resolved_by, "resolved_at": review.resolved_at,
        "resolution_note": review.resolution_note,
        "parent_review_id": review.parent_review_id,
        "created_at": review.created_at,
    }


@router.get("/{plan_id}/reviews")
async def api_list_reviews(
    plan_id: int,
    version_number: Optional[int] = Query(None),
    unresolved_only: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """批注列表"""
    items, total = await services.list_reviews(
        db, current_user.school_id, plan_id,
        version_number=version_number,
        unresolved_only=unresolved_only,
    )
    return {"items": items, "total": total}


@router.put("/{plan_id}/reviews/{review_id}", response_model=schemas.ReviewResponse)
async def api_resolve_review(
    plan_id: int,
    review_id: int,
    payload: schemas.ReviewResolve,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """标记批注已解决"""
    if not _can_review(current_user):
        raise HTTPException(403, "无权操作: 需组长/管理员角色")

    review = await services.resolve_review(
        db, current_user.school_id, plan_id, review_id,
        current_user.id, payload,
    )
    if not review:
        raise HTTPException(404, "批注不存在")

    reviewer_name = await services._get_user_name(db, review.reviewer_id)
    return {
        "id": review.id, "plan_id": review.plan_id,
        "version_number": review.version_number,
        "reviewer_id": review.reviewer_id, "reviewer_name": reviewer_name,
        "target_section": review.target_section,
        "target_anchor": review.target_anchor,
        "comment": review.comment, "severity": review.severity,
        "is_resolved": review.is_resolved,
        "resolved_by": review.resolved_by, "resolved_at": review.resolved_at,
        "resolution_note": review.resolution_note,
        "parent_review_id": review.parent_review_id,
        "created_at": review.created_at,
    }


# ═══════════════════════════════════════════════
# 状态机流转
# ═══════════════════════════════════════════════

@router.post("/{plan_id}/submit", response_model=schemas.PlanResponse)
async def api_submit_plan(
    plan_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """提交进入集体评议 (DRAFT → REVIEW)"""
    plan = await services.get_plan(db, current_user.school_id, plan_id)
    if not plan:
        raise HTTPException(404, "教案不存在")

    if not _can_manage_plan(current_user, plan.creator_id):
        raise HTTPException(403, "无权操作他人教案")

    plan, err = await services.transition_status(
        db, current_user.school_id, plan_id,
        STATUS_COLLECTIVE_REVIEW, current_user.id,
    )
    if err:
        raise HTTPException(400, err)

    creator_name = await services._get_user_name(db, plan.creator_id)
    return _plan_to_dict(plan, creator_name)


@router.post("/{plan_id}/approve", response_model=schemas.PlanResponse)
async def api_approve_plan(
    plan_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """组长审核通过 (REVIEW → APPROVED)"""
    if not _can_review(current_user):
        raise HTTPException(403, "无权审核: 需组长/管理员角色")

    plan, err = await services.transition_status(
        db, current_user.school_id, plan_id,
        STATUS_ADMIN_APPROVE, current_user.id,
    )
    if err:
        raise HTTPException(400, err)

    creator_name = await services._get_user_name(db, plan.creator_id)
    return _plan_to_dict(plan, creator_name)


@router.post("/{plan_id}/publish", response_model=schemas.PlanResponse)
async def api_publish_plan(
    plan_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """发布 (APPROVED → PUBLISHED), 锁定当前版本"""
    if not _can_review(current_user):
        raise HTTPException(403, "无权发布: 需组长/管理员角色")

    plan, err = await services.transition_status(
        db, current_user.school_id, plan_id,
        STATUS_PUBLISHED, current_user.id,
    )
    if err:
        raise HTTPException(400, err)

    creator_name = await services._get_user_name(db, plan.creator_id)
    return _plan_to_dict(plan, creator_name)


@router.post("/{plan_id}/reject", response_model=schemas.PlanResponse)
async def api_reject_plan(
    plan_id: int,
    payload: schemas.StatusTransition,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """打回草稿 (REVIEW/APPROVED → DRAFT)"""
    if not _can_review(current_user):
        raise HTTPException(403, "无权打回: 需组长/管理员角色")

    plan, err = await services.transition_status(
        db, current_user.school_id, plan_id,
        STATUS_DRAFT, current_user.id,
        reject_reason=payload.reject_reason,
    )
    if err:
        raise HTTPException(400, err)

    creator_name = await services._get_user_name(db, plan.creator_id)
    return _plan_to_dict(plan, creator_name)


# ═══════════════════════════════════════════════
# Fork派生
# ═══════════════════════════════════════════════

@router.post("/{plan_id}/fork", response_model=schemas.PlanDetailResponse, status_code=201)
async def api_fork_plan(
    plan_id: int,
    payload: schemas.PlanFork,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """从已发布教案Fork派生新教案"""
    if not _can_create(current_user):
        raise HTTPException(403, "无权创建教案")

    result = await services.fork_plan(
        db, current_user.school_id, plan_id, current_user.id, payload,
    )
    if not result:
        raise HTTPException(400, "Fork失败: 教案不存在或未发布")

    plan, version = result
    forker_name = await services._get_user_name(db, plan.creator_id)
    return {
        **_plan_to_dict(plan, forker_name),
        "latest_content": version.content_json,
        "latest_version_number": version.version_number,
        "unresolved_review_count": 0,
    }


# ═══════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════

def _plan_to_dict(plan, creator_name: str = None) -> dict:
    """ORM → dict"""
    return {
        "id": plan.id, "school_id": plan.school_id,
        "title": plan.title, "description": plan.description,
        "subject_code": plan.subject_code, "grade_level": plan.grade_level,
        "lesson_type": plan.lesson_type, "duration": plan.duration,
        "tags": plan.tags or [],
        "status": plan.status,
        "status_updated_at": plan.status_updated_at,
        "current_version": plan.current_version,
        "published_version": plan.published_version,
        "reference_count": plan.reference_count or 0,
        "fork_count": plan.fork_count or 0,
        "creator_id": plan.creator_id,
        "creator_name": creator_name or f"用户{plan.creator_id}",
        "grade_leader_id": plan.grade_leader_id,
        "forked_from_id": plan.forked_from_id,
        "content_markdown": getattr(plan, "content_markdown", None),
        "ai_bias_prescription": getattr(plan, "ai_bias_prescription", None),
        "ai_prescription_generated_at": getattr(plan, "ai_prescription_generated_at", None),
        "created_at": plan.created_at, "updated_at": plan.updated_at,
    }


# ═══════════════════════════════════════════════
# AI学情逆向处方 (Wings 3.1 — 从error_funnel逆向注入)
# ═══════════════════════════════════════════════

@router.post("/{plan_id}/generate-ai-bias")
async def api_generate_ai_bias(
    plan_id: int,
    payload: schemas.AIBiasGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    AI学情逆向处方 — 从error_funnel拉取断层数据 → 聚合 → DeepSeek → 写入教案

    流程:
      1. 查询目标班级/年级的knowledge_gaps (critical/warning)
      2. 按知识点聚合断层统计
      3. 调用DeepSeek生成Markdown格式教学偏方
      4. 写入plan.ai_bias_prescription

    需教师/组长/管理员角色
    """
    if not _can_create(current_user):
        raise HTTPException(403, "无权生成AI处方: 需教师/组长/管理员角色")

    plan = await services.get_plan(db, current_user.school_id, plan_id)
    if not plan:
        raise HTTPException(404, "教案不存在")

    if not _can_manage_plan(current_user, plan.creator_id):
        raise HTTPException(403, "无权操作他人教案")

    prescription, err = await services.generate_ai_bias(
        db, current_user.school_id, plan_id,
        grade_id=payload.grade_id,
        class_id=payload.class_id,
    )

    if err:
        raise HTTPException(400, err)

    return {
        "plan_id": plan_id,
        "ai_bias_prescription": prescription,
        "generated_at": plan.ai_prescription_generated_at,
    }
