"""
research_lesson_prep/services.py — 集体备课核心业务引擎

核心能力:
  1. 教案 CRUD + 版本控制 (每次保存创建不可变快照)
  2. 状态机流转 (DRAFT → REVIEW → APPROVED → PUBLISHED)
  3. 协同批注 (按教案组件定位, 支持回复链, 可标记解决)
  4. Fork派生 (从已发布教案派生新教案)
  5. 教研看板统计 (按学科/年级/状态聚合)
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update, delete, and_
from sqlalchemy.orm import selectinload
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import json

from core.models import get_local_now
from core.models import User
from .models import (
    ResearchLessonPlan, ResearchPlanVersion, ResearchPlanReview,
    STATUS_DRAFT, STATUS_COLLECTIVE_REVIEW, STATUS_ADMIN_APPROVE, STATUS_PUBLISHED,
    VALID_TRANSITIONS,
)
from .schemas import (
    LessonContent, PlanCreate, PlanUpdate, VersionCreate,
    ReviewCreate, ReviewResolve, PlanFork,
)


# ═══════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════

async def _get_user_name(db: AsyncSession, user_id: int) -> str:
    """获取用户显示名"""
    result = await db.execute(
        select(User.display_name).where(User.id == user_id)
    )
    row = result.scalar_one_or_none()
    return row or f"用户{user_id}"


async def _get_user_names_batch(db: AsyncSession, user_ids: List[int]) -> Dict[int, str]:
    """批量获取用户名映射"""
    if not user_ids:
        return {}
    result = await db.execute(
        select(User.id, User.display_name).where(User.id.in_(user_ids))
    )
    return {row[0]: row[1] for row in result.fetchall()}


def _content_to_dict(content: LessonContent) -> dict:
    """LessonContent → dict for JSON storage"""
    if isinstance(content, dict):
        return content
    return content.model_dump()


def _dict_to_content(d: dict) -> LessonContent:
    """dict → LessonContent"""
    if isinstance(d, LessonContent):
        return d
    return LessonContent(**(d or {}))


def _validate_transition(current: str, target: str) -> bool:
    """校验状态机流转合法性"""
    allowed = VALID_TRANSITIONS.get(current, [])
    return target in allowed


# ═══════════════════════════════════════════════
# 教案 CRUD
# ═══════════════════════════════════════════════

async def create_plan(
    db: AsyncSession, school_id: int, creator_id: int, data: PlanCreate,
) -> Tuple[ResearchLessonPlan, ResearchPlanVersion]:
    """创建教案 + 初始V1版本快照"""
    now = get_local_now()

    # 创建主案
    plan = ResearchLessonPlan(
        school_id=school_id,
        title=data.title,
        description=data.description,
        subject_code=data.subject_code,
        grade_level=data.grade_level,
        lesson_type=data.lesson_type,
        duration=data.duration,
        tags=data.tags,
        status=STATUS_DRAFT,
        status_updated_at=now,
        status_updated_by=creator_id,
        current_version=1,
        creator_id=creator_id,
    )
    db.add(plan)
    await db.flush()  # 获取 plan.id

    # 创建V1版本快照
    version = ResearchPlanVersion(
        school_id=school_id,
        plan_id=plan.id,
        version_number=1,
        editor_id=creator_id,
        content_json=_content_to_dict(data.content),
        change_log=data.change_log or "初始创建",
        is_major=True,
    )
    db.add(version)
    await db.commit()
    await db.refresh(plan)
    await db.refresh(version)

    return plan, version


async def get_plan(db: AsyncSession, school_id: int, plan_id: int) -> Optional[ResearchLessonPlan]:
    """获取教案 (含多租户隔离)"""
    result = await db.execute(
        select(ResearchLessonPlan).where(
            and_(
                ResearchLessonPlan.id == plan_id,
                ResearchLessonPlan.school_id == school_id,
            )
        )
    )
    return result.scalar_one_or_none()


async def list_plans(
    db: AsyncSession, school_id: int,
    subject_code: Optional[str] = None,
    grade_level: Optional[str] = None,
    status: Optional[str] = None,
    creator_id: Optional[int] = None,
    page: int = 1, page_size: int = 20,
) -> Tuple[List[dict], int]:
    """教案列表 (分页+筛选)"""
    conditions = [ResearchLessonPlan.school_id == school_id]
    if subject_code:
        conditions.append(ResearchLessonPlan.subject_code == subject_code)
    if grade_level:
        conditions.append(ResearchLessonPlan.grade_level == grade_level)
    if status:
        conditions.append(ResearchLessonPlan.status == status)
    if creator_id:
        conditions.append(ResearchLessonPlan.creator_id == creator_id)

    # 总数
    count_q = select(func.count()).select_from(ResearchLessonPlan).where(*conditions)
    total = (await db.execute(count_q)).scalar() or 0

    # 分页
    offset = (page - 1) * page_size
    list_q = (
        select(ResearchLessonPlan)
        .where(*conditions)
        .order_by(ResearchLessonPlan.updated_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    rows = (await db.execute(list_q)).scalars().all()

    # 批量获取创建者名
    creator_ids = [r.creator_id for r in rows if r.creator_id]
    name_map = await _get_user_names_batch(db, creator_ids)

    items = []
    for r in rows:
        item = {
            "id": r.id, "school_id": r.school_id,
            "title": r.title, "description": r.description,
            "subject_code": r.subject_code, "grade_level": r.grade_level,
            "lesson_type": r.lesson_type, "duration": r.duration,
            "tags": r.tags or [],
            "status": r.status,
            "status_updated_at": r.status_updated_at,
            "current_version": r.current_version,
            "published_version": r.published_version,
            "reference_count": r.reference_count,
            "fork_count": r.fork_count,
            "creator_id": r.creator_id,
            "creator_name": name_map.get(r.creator_id, f"用户{r.creator_id}"),
            "grade_leader_id": r.grade_leader_id,
            "forked_from_id": r.forked_from_id,
            "created_at": r.created_at, "updated_at": r.updated_at,
        }
        items.append(item)

    return items, total


async def update_plan(
    db: AsyncSession, school_id: int, plan_id: int, data: PlanUpdate,
) -> Optional[ResearchLessonPlan]:
    """更新教案元信息 (不动内容)"""
    plan = await get_plan(db, school_id, plan_id)
    if not plan:
        return None

    if data.title is not None:
        plan.title = data.title
    if data.description is not None:
        plan.description = data.description
    if data.lesson_type is not None:
        plan.lesson_type = data.lesson_type
    if data.duration is not None:
        plan.duration = data.duration
    if data.tags is not None:
        plan.tags = data.tags

    await db.commit()
    await db.refresh(plan)
    return plan


async def delete_plan(db: AsyncSession, school_id: int, plan_id: int) -> bool:
    """删除教案 + 关联版本 + 批注 (级联)"""
    plan = await get_plan(db, school_id, plan_id)
    if not plan:
        return False

    # 已发布的教案不允许删除
    if plan.status == STATUS_PUBLISHED:
        return False

    # 删除版本
    await db.execute(
        delete(ResearchPlanVersion).where(ResearchPlanVersion.plan_id == plan_id)
    )
    # 删除批注
    await db.execute(
        delete(ResearchPlanReview).where(ResearchPlanReview.plan_id == plan_id)
    )
    # 删除主案
    await db.delete(plan)
    await db.commit()
    return True


# ═══════════════════════════════════════════════
# 版本控制
# ═══════════════════════════════════════════════

async def create_version(
    db: AsyncSession, school_id: int, plan_id: int, editor_id: int, data: VersionCreate,
) -> Optional[ResearchPlanVersion]:
    """创建新版本快照 — 每次保存内容时调用"""
    plan = await get_plan(db, school_id, plan_id)
    if not plan:
        return None

    # 只有 draft 或 review 状态可编辑
    if plan.status not in (STATUS_DRAFT, STATUS_COLLECTIVE_REVIEW):
        return None

    new_ver = plan.current_version + 1
    version = ResearchPlanVersion(
        school_id=school_id,
        plan_id=plan_id,
        version_number=new_ver,
        editor_id=editor_id,
        content_json=_content_to_dict(data.content),
        change_log=data.change_log,
        is_major=data.is_major,
    )
    plan.current_version = new_ver
    plan.updated_at = get_local_now()

    db.add(version)
    await db.commit()
    await db.refresh(version)
    return version


async def get_version(
    db: AsyncSession, school_id: int, plan_id: int, version_number: int,
) -> Optional[ResearchPlanVersion]:
    """获取特定版本"""
    result = await db.execute(
        select(ResearchPlanVersion).where(
            and_(
                ResearchPlanVersion.plan_id == plan_id,
                ResearchPlanVersion.version_number == version_number,
                ResearchPlanVersion.school_id == school_id,
            )
        )
    )
    return result.scalar_one_or_none()


async def list_versions(
    db: AsyncSession, school_id: int, plan_id: int,
) -> Tuple[List[dict], int]:
    """版本历史列表"""
    result = await db.execute(
        select(ResearchPlanVersion)
        .where(
            and_(
                ResearchPlanVersion.plan_id == plan_id,
                ResearchPlanVersion.school_id == school_id,
            )
        )
        .order_by(ResearchPlanVersion.version_number.desc())
    )
    rows = result.scalars().all()

    editor_ids = [r.editor_id for r in rows]
    name_map = await _get_user_names_batch(db, editor_ids)

    items = []
    for r in rows:
        items.append({
            "id": r.id, "plan_id": r.plan_id,
            "version_number": r.version_number,
            "editor_id": r.editor_id,
            "editor_name": name_map.get(r.editor_id, f"用户{r.editor_id}"),
            "content": r.content_json or {},
            "change_log": r.change_log,
            "is_major": r.is_major,
            "created_at": r.created_at,
        })

    return items, len(items)


# ═══════════════════════════════════════════════
# 状态机流转
# ═══════════════════════════════════════════════

async def transition_status(
    db: AsyncSession, school_id: int, plan_id: int,
    target_status: str, operator_id: int,
    reject_reason: Optional[str] = None,
) -> Tuple[Optional[ResearchLessonPlan], Optional[str]]:
    """
    状态机流转, 返回 (plan, error_msg)
    流转: DRAFT→REVIEW→APPROVED→PUBLISHED, 非PUBLISHED可回退DRAFT
    """
    plan = await get_plan(db, school_id, plan_id)
    if not plan:
        return None, "教案不存在"

    current = plan.status
    if not _validate_transition(current, target_status):
        return None, f"非法状态流转: {current} → {target_status}"

    # 回退需记录原因
    if target_status == STATUS_DRAFT and current != STATUS_DRAFT:
        plan.reject_reason = reject_reason or "未说明原因"

    # 发布时锁定版本
    if target_status == STATUS_PUBLISHED:
        plan.published_version = plan.current_version

    plan.status = target_status
    plan.status_updated_at = get_local_now()
    plan.status_updated_by = operator_id

    await db.commit()
    await db.refresh(plan)
    return plan, None


# ═══════════════════════════════════════════════
# 协同批注
# ═══════════════════════════════════════════════

async def create_review(
    db: AsyncSession, school_id: int, reviewer_id: int,
    plan_id: int, data: ReviewCreate,
) -> Optional[ResearchPlanReview]:
    """添加批注"""
    plan = await get_plan(db, school_id, plan_id)
    if not plan:
        return None

    # 只能对 review 状态的教案批注
    if plan.status != STATUS_COLLECTIVE_REVIEW:
        return None

    # 校验版本存在
    ver = await get_version(db, school_id, plan_id, data.version_number)
    if not ver:
        return None

    review = ResearchPlanReview(
        school_id=school_id,
        plan_id=plan_id,
        version_number=data.version_number,
        reviewer_id=reviewer_id,
        target_section=data.target_section,
        target_anchor=data.target_anchor,
        comment=data.comment,
        severity=data.severity,
        parent_review_id=data.parent_review_id,
    )
    db.add(review)
    await db.commit()
    await db.refresh(review)
    return review


async def list_reviews(
    db: AsyncSession, school_id: int, plan_id: int,
    version_number: Optional[int] = None,
    unresolved_only: bool = False,
) -> Tuple[List[dict], int]:
    """批注列表"""
    conditions = [
        ResearchPlanReview.plan_id == plan_id,
        ResearchPlanReview.school_id == school_id,
    ]
    if version_number:
        conditions.append(ResearchPlanReview.version_number == version_number)
    if unresolved_only:
        conditions.append(ResearchPlanReview.is_resolved == False)

    result = await db.execute(
        select(ResearchPlanReview)
        .where(*conditions)
        .order_by(ResearchPlanReview.created_at.asc())
    )
    rows = result.scalars().all()

    reviewer_ids = [r.reviewer_id for r in rows] + [
        r.resolved_by for r in rows if r.resolved_by
    ]
    name_map = await _get_user_names_batch(db, list(set(reviewer_ids)))

    items = []
    for r in rows:
        items.append({
            "id": r.id, "plan_id": r.plan_id,
            "version_number": r.version_number,
            "reviewer_id": r.reviewer_id,
            "reviewer_name": name_map.get(r.reviewer_id, f"用户{r.reviewer_id}"),
            "target_section": r.target_section,
            "target_anchor": r.target_anchor,
            "comment": r.comment,
            "severity": r.severity,
            "is_resolved": r.is_resolved,
            "resolved_by": r.resolved_by,
            "resolved_at": r.resolved_at,
            "resolution_note": r.resolution_note,
            "parent_review_id": r.parent_review_id,
            "created_at": r.created_at,
        })

    return items, len(items)


async def resolve_review(
    db: AsyncSession, school_id: int, plan_id: int, review_id: int,
    resolver_id: int, data: ReviewResolve,
) -> Optional[ResearchPlanReview]:
    """标记批注已解决"""
    result = await db.execute(
        select(ResearchPlanReview).where(
            and_(
                ResearchPlanReview.id == review_id,
                ResearchPlanReview.plan_id == plan_id,
                ResearchPlanReview.school_id == school_id,
            )
        )
    )
    review = result.scalar_one_or_none()
    if not review:
        return None

    review.is_resolved = True
    review.resolved_by = resolver_id
    review.resolved_at = get_local_now()
    review.resolution_note = data.resolution_note

    await db.commit()
    await db.refresh(review)
    return review


# ═══════════════════════════════════════════════
# Fork派生
# ═══════════════════════════════════════════════

async def fork_plan(
    db: AsyncSession, school_id: int, plan_id: int,
    forker_id: int, data: PlanFork,
) -> Optional[Tuple[ResearchLessonPlan, ResearchPlanVersion]]:
    """从已发布教案Fork派生新教案"""
    source = await get_plan(db, school_id, plan_id)
    if not source or source.status != STATUS_PUBLISHED:
        return None

    # 获取已发布版本内容
    pub_ver = await get_version(db, school_id, plan_id, source.published_version or source.current_version)
    if not pub_ver:
        return None

    now = get_local_now()
    new_plan = ResearchLessonPlan(
        school_id=school_id,
        title=data.title,
        description=f"Fork自: {source.title}",
        subject_code=source.subject_code,
        grade_level=source.grade_level,
        lesson_type=source.lesson_type,
        duration=source.duration,
        tags=source.tags or [],
        status=STATUS_DRAFT,
        status_updated_at=now,
        status_updated_by=forker_id,
        current_version=1,
        creator_id=forker_id,
        forked_from_id=plan_id,
    )
    db.add(new_plan)
    await db.flush()

    new_version = ResearchPlanVersion(
        school_id=school_id,
        plan_id=new_plan.id,
        version_number=1,
        editor_id=forker_id,
        content_json=pub_ver.content_json,
        change_log=f"Fork自教案#{plan_id} V{source.published_version}",
        is_major=True,
    )
    db.add(new_version)

    # 源教案 fork_count +1
    source.fork_count = (source.fork_count or 0) + 1

    await db.commit()
    await db.refresh(new_plan)
    await db.refresh(new_version)
    return new_plan, new_version


# ═══════════════════════════════════════════════
# 教研看板统计
# ═══════════════════════════════════════════════

async def get_dashboard_stats(db: AsyncSession, school_id: int) -> dict:
    """教研看板统计"""
    # 总数
    total = (await db.execute(
        select(func.count()).select_from(ResearchLessonPlan)
        .where(ResearchLessonPlan.school_id == school_id)
    )).scalar() or 0

    # 按状态分组
    status_q = (
        select(ResearchLessonPlan.status, func.count())
        .where(ResearchLessonPlan.school_id == school_id)
        .group_by(ResearchLessonPlan.status)
    )
    status_rows = (await db.execute(status_q)).fetchall()
    status_map = {row[0]: row[1] for row in status_rows}

    # 版本总数
    total_versions = (await db.execute(
        select(func.count()).select_from(ResearchPlanVersion)
        .where(ResearchPlanVersion.school_id == school_id)
    )).scalar() or 0

    # 批注统计
    total_reviews = (await db.execute(
        select(func.count()).select_from(ResearchPlanReview)
        .where(ResearchPlanReview.school_id == school_id)
    )).scalar() or 0

    unresolved_reviews = (await db.execute(
        select(func.count()).select_from(ResearchPlanReview)
        .where(
            and_(
                ResearchPlanReview.school_id == school_id,
                ResearchPlanReview.is_resolved == False,
            )
        )
    )).scalar() or 0

    # 按学科分组
    subject_q = (
        select(ResearchLessonPlan.subject_code, func.count())
        .where(ResearchLessonPlan.school_id == school_id)
        .group_by(ResearchLessonPlan.subject_code)
    )
    subject_rows = (await db.execute(subject_q)).fetchall()
    by_subject = {row[0]: row[1] for row in subject_rows}

    # 按年级分组
    grade_q = (
        select(ResearchLessonPlan.grade_level, func.count())
        .where(ResearchLessonPlan.school_id == school_id)
        .group_by(ResearchLessonPlan.grade_level)
    )
    grade_rows = (await db.execute(grade_q)).fetchall()
    by_grade = {row[0]: row[1] for row in grade_rows}

    # Top创建者 (Top 5)
    creator_q = (
        select(
            ResearchLessonPlan.creator_id,
            func.count().label("plan_count"),
        )
        .where(ResearchLessonPlan.school_id == school_id)
        .group_by(ResearchLessonPlan.creator_id)
        .order_by(func.count().desc())
        .limit(5)
    )
    creator_rows = (await db.execute(creator_q)).fetchall()
    creator_ids = [row[0] for row in creator_rows]
    name_map = await _get_user_names_batch(db, creator_ids)
    top_creators = [
        {"user_id": row[0], "name": name_map.get(row[0], f"用户{row[0]}"), "plan_count": row[1]}
        for row in creator_rows
    ]

    return {
        "total_plans": total,
        "draft_count": status_map.get(STATUS_DRAFT, 0),
        "review_count": status_map.get(STATUS_COLLECTIVE_REVIEW, 0),
        "approved_count": status_map.get(STATUS_ADMIN_APPROVE, 0),
        "published_count": status_map.get(STATUS_PUBLISHED, 0),
        "total_versions": total_versions,
        "total_reviews": total_reviews,
        "unresolved_reviews": unresolved_reviews,
        "by_subject": by_subject,
        "by_grade": by_grade,
        "top_creators": top_creators,
    }
