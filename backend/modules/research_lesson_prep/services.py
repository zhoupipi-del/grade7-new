"""
research_lesson_prep/services.py — 集体备课核心业务引擎

核心能力:
  1. 教案 CRUD + 版本控制 (每次保存创建不可变快照)
  2. 状态机流转 (DRAFT → REVIEW → APPROVED → PUBLISHED)
  3. 协同批注 (按教案组件定位, 支持回复链, 可标记解决)
  4. Fork派生 (从已发布教案派生新教案)
  5. 教研看板统计 (按学科/年级/状态聚合)
"""

import logging
import os

import httpx
from core.models import Student, User, get_local_now
from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    STATUS_ADMIN_APPROVE,
    STATUS_COLLECTIVE_REVIEW,
    STATUS_DRAFT,
    STATUS_PUBLISHED,
    VALID_TRANSITIONS,
    ResearchLessonPlan,
    ResearchPlanReview,
    ResearchPlanVersion,
)
from .schemas import (
    LessonContent,
    PlanCreate,
    PlanFork,
    PlanUpdate,
    ReviewCreate,
    ReviewResolve,
    VersionCreate,
)

logger = logging.getLogger(__name__)

# ── DeepSeek 配置 (复用error_funnel模式) ──
_LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
_LLM_API_URL = os.environ.get("LLM_API_URL", "https://api.deepseek.com/v1/chat/completions")
_LLM_MODEL = os.environ.get("LLM_MODEL", "deepseek-chat")


# ═══════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════


async def _get_user_name(db: AsyncSession, user_id: int) -> str:
    """获取用户显示名"""
    result = await db.execute(select(User.display_name).where(User.id == user_id))
    row = result.scalar_one_or_none()
    return row or f"用户{user_id}"


async def _get_user_names_batch(db: AsyncSession, user_ids: list[int]) -> dict[int, str]:
    """批量获取用户名映射"""
    if not user_ids:
        return {}
    result = await db.execute(select(User.id, User.display_name).where(User.id.in_(user_ids)))
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
    db: AsyncSession,
    school_id: int,
    creator_id: int,
    data: PlanCreate,
) -> tuple[ResearchLessonPlan, ResearchPlanVersion]:
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
        content_markdown=data.content_markdown,
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
        content_markdown=data.content_markdown,
        change_log=data.change_log or "初始创建",
        is_major=True,
    )
    db.add(version)
    await db.commit()
    await db.refresh(plan)
    await db.refresh(version)

    return plan, version


async def get_plan(db: AsyncSession, school_id: int, plan_id: int) -> ResearchLessonPlan | None:
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
    db: AsyncSession,
    school_id: int,
    subject_code: str | None = None,
    grade_level: str | None = None,
    status: str | None = None,
    creator_id: int | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[dict], int]:
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
            "id": r.id,
            "school_id": r.school_id,
            "title": r.title,
            "description": r.description,
            "subject_code": r.subject_code,
            "grade_level": r.grade_level,
            "lesson_type": r.lesson_type,
            "duration": r.duration,
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
            "created_at": r.created_at,
            "updated_at": r.updated_at,
        }
        items.append(item)

    return items, total


async def update_plan(
    db: AsyncSession,
    school_id: int,
    plan_id: int,
    data: PlanUpdate,
) -> ResearchLessonPlan | None:
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
    await db.execute(delete(ResearchPlanVersion).where(ResearchPlanVersion.plan_id == plan_id))
    # 删除批注
    await db.execute(delete(ResearchPlanReview).where(ResearchPlanReview.plan_id == plan_id))
    # 删除主案
    await db.delete(plan)
    await db.commit()
    return True


# ═══════════════════════════════════════════════
# 版本控制
# ═══════════════════════════════════════════════


async def create_version(
    db: AsyncSession,
    school_id: int,
    plan_id: int,
    editor_id: int,
    data: VersionCreate,
) -> ResearchPlanVersion | None:
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
        content_markdown=data.content_markdown,
        change_log=data.change_log,
        is_major=data.is_major,
    )
    plan.current_version = new_ver
    plan.updated_at = get_local_now()

    # 如果有新的markdown内容, 同步更新主案
    if data.content_markdown is not None:
        plan.content_markdown = data.content_markdown

    db.add(version)
    await db.commit()
    await db.refresh(version)
    return version


async def get_version(
    db: AsyncSession,
    school_id: int,
    plan_id: int,
    version_number: int,
) -> ResearchPlanVersion | None:
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
    db: AsyncSession,
    school_id: int,
    plan_id: int,
) -> tuple[list[dict], int]:
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
        items.append(
            {
                "id": r.id,
                "plan_id": r.plan_id,
                "version_number": r.version_number,
                "editor_id": r.editor_id,
                "editor_name": name_map.get(r.editor_id, f"用户{r.editor_id}"),
                "content": r.content_json or {},
                "change_log": r.change_log,
                "is_major": r.is_major,
                "created_at": r.created_at,
            }
        )

    return items, len(items)


# ═══════════════════════════════════════════════
# 状态机流转
# ═══════════════════════════════════════════════


async def transition_status(
    db: AsyncSession,
    school_id: int,
    plan_id: int,
    target_status: str,
    operator_id: int,
    reject_reason: str | None = None,
) -> tuple[ResearchLessonPlan | None, str | None]:
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
    db: AsyncSession,
    school_id: int,
    reviewer_id: int,
    plan_id: int,
    data: ReviewCreate,
) -> ResearchPlanReview | None:
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
    db: AsyncSession,
    school_id: int,
    plan_id: int,
    version_number: int | None = None,
    unresolved_only: bool = False,
) -> tuple[list[dict], int]:
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
        select(ResearchPlanReview).where(*conditions).order_by(ResearchPlanReview.created_at.asc())
    )
    rows = result.scalars().all()

    reviewer_ids = [r.reviewer_id for r in rows] + [r.resolved_by for r in rows if r.resolved_by]
    name_map = await _get_user_names_batch(db, list(set(reviewer_ids)))

    items = []
    for r in rows:
        items.append(
            {
                "id": r.id,
                "plan_id": r.plan_id,
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
            }
        )

    return items, len(items)


async def resolve_review(
    db: AsyncSession,
    school_id: int,
    plan_id: int,
    review_id: int,
    resolver_id: int,
    data: ReviewResolve,
) -> ResearchPlanReview | None:
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
    db: AsyncSession,
    school_id: int,
    plan_id: int,
    forker_id: int,
    data: PlanFork,
) -> tuple[ResearchLessonPlan, ResearchPlanVersion] | None:
    """从已发布教案Fork派生新教案"""
    source = await get_plan(db, school_id, plan_id)
    if not source or source.status != STATUS_PUBLISHED:
        return None

    # 获取已发布版本内容
    pub_ver = await get_version(
        db, school_id, plan_id, source.published_version or source.current_version
    )
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
    total = (
        await db.execute(
            select(func.count())
            .select_from(ResearchLessonPlan)
            .where(ResearchLessonPlan.school_id == school_id)
        )
    ).scalar() or 0

    # 按状态分组
    status_q = (
        select(ResearchLessonPlan.status, func.count())
        .where(ResearchLessonPlan.school_id == school_id)
        .group_by(ResearchLessonPlan.status)
    )
    status_rows = (await db.execute(status_q)).fetchall()
    status_map = {row[0]: row[1] for row in status_rows}

    # 版本总数
    total_versions = (
        await db.execute(
            select(func.count())
            .select_from(ResearchPlanVersion)
            .where(ResearchPlanVersion.school_id == school_id)
        )
    ).scalar() or 0

    # 批注统计
    total_reviews = (
        await db.execute(
            select(func.count())
            .select_from(ResearchPlanReview)
            .where(ResearchPlanReview.school_id == school_id)
        )
    ).scalar() or 0

    unresolved_reviews = (
        await db.execute(
            select(func.count())
            .select_from(ResearchPlanReview)
            .where(
                and_(
                    ResearchPlanReview.school_id == school_id,
                    ResearchPlanReview.is_resolved == False,
                )
            )
        )
    ).scalar() or 0

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


# ═══════════════════════════════════════════════
# AI学情逆向处方 (Wings 3.1 — 从error_funnel逆向注入)
# ═══════════════════════════════════════════════


async def generate_ai_bias(
    db: AsyncSession,
    school_id: int,
    plan_id: int,
    grade_id: int | None = None,
    class_id: int | None = None,
) -> tuple[str | None, str | None]:
    """
    AI学情逆向处方 — 从error_funnel拉取断层数据 → 聚合 → DeepSeek → 写入教案

    流程:
      1. 获取教案信息 + 最新版本内容
      2. 拉取目标班级/年级的knowledge_gaps (gap_level in critical/warning)
      3. 按知识点聚合断层统计
      4. 调用DeepSeek生成Markdown格式教学偏方
      5. 写入plan.ai_bias_prescription + ai_prescription_generated_at

    返回: (prescription_text, error_msg)
    """
    plan = await get_plan(db, school_id, plan_id)
    if not plan:
        return None, "教案不存在"

    # 获取教案最新版本内容
    versions, _ = await list_versions(db, school_id, plan_id)
    if not versions:
        return None, "教案无版本内容"
    latest_version = versions[0]
    content = latest_version.get("content", {})

    # ── 拉取目标学生ID列表 ──
    from modules.error_funnel.models import GAP_ACTIVE, GAP_CRITICAL, GAP_WARNING, KnowledgeGap

    student_ids: list[int] = []
    if class_id:
        result = await db.execute(
            select(Student.id).where(
                Student.class_id == class_id,
                Student.school_id == school_id,
            )
        )
        student_ids = [r[0] for r in result.fetchall()]
    elif grade_id:
        result = await db.execute(
            select(Student.id).where(
                Student.grade_id == grade_id,
                Student.school_id == school_id,
            )
        )
        student_ids = [r[0] for r in result.fetchall()]

    if not student_ids:
        return None, "未找到目标学生数据，无法生成学情处方"

    # ── 查询断层 ──
    gap_q = (
        select(
            KnowledgeGap.knowledge_point_name,
            KnowledgeGap.gap_level,
            func.count().label("student_count"),
            func.avg(KnowledgeGap.error_count).label("avg_errors"),
            func.max(KnowledgeGap.consecutive_errors).label("max_consecutive"),
        )
        .where(
            and_(
                KnowledgeGap.school_id == school_id,
                KnowledgeGap.student_id.in_(student_ids),
                KnowledgeGap.gap_level.in_([GAP_WARNING, GAP_CRITICAL]),
                KnowledgeGap.gap_status == GAP_ACTIVE,
            )
        )
        .group_by(KnowledgeGap.knowledge_point_name, KnowledgeGap.gap_level)
        .order_by(func.count().desc())
        .limit(20)
    )
    gap_rows = (await db.execute(gap_q)).fetchall()

    if not gap_rows:
        return None, "目标学生暂无断层数据，无需生成学情处方"

    # ── 构建断层数据摘要 ──
    gap_summary_lines = []
    for row in gap_rows:
        kp_name = row[0] or "未知知识点"
        level = row[1]
        count = row[2]
        avg_err = round(float(row[3]), 1) if row[3] else 0
        max_consec = row[4] or 0
        level_cn = "严重" if level == GAP_CRITICAL else "预警"
        gap_summary_lines.append(
            f"- {kp_name} [{level_cn}]: {count}人存在断层, "
            f"平均错误{avg_err}次, 最大连续错误{max_consec}次"
        )
    gap_summary = "\n".join(gap_summary_lines)

    # ── 构建DeepSeek prompt ──
    system_prompt = (
        "你是一位资深教研专家和学情诊断师。你的任务是根据学生的错题断层数据，"
        "为教师撰写一份针对性的教学偏方(AI学情逆向处方)，"
        "帮助教师在备课中精准应对学生的知识薄弱点。\n\n"
        "输出要求：\n"
        "1. 使用Markdown格式\n"
        "2. 包含以下部分：\n"
        "   ## 学情诊断\n   简要分析学生群体的知识薄弱分布\n"
        "   ## 教学偏方\n   针对每个薄弱知识点，给出具体的教学建议"
        "（如何讲解、如何设计练习、如何分层教学）\n"
        "   ## 课堂策略\n   建议的课堂教学策略和注意事项\n"
        "3. 语言精炼、实操性强，不要空话套话\n"
        "4. 总字数控制在800-1200字"
    )

    user_prompt = (
        f"教案标题: {plan.title}\n"
        f"学科: {plan.subject_code}\n"
        f"年级: {plan.grade_level}\n"
        f"课型: {plan.lesson_type}\n\n"
        f"教案内容摘要:\n"
        f"  教学目标: {', '.join(content.get('teaching_objectives', []))}\n"
        f"  教学重点: {', '.join(content.get('key_points', []))}\n"
        f"  教学难点: {', '.join(content.get('difficulties', []))}\n\n"
        f"学生学情断层数据 (按严重程度排序):\n{gap_summary}\n\n"
        f"请基于以上学情数据，为这份教案生成针对性的教学偏方。"
    )

    # ── 调用DeepSeek ──
    try:
        prescription = await _call_deepseek_text(user_prompt, system_prompt, timeout=45.0)
    except Exception as e:
        logger.error(f"AI逆向处方生成失败: plan_id={plan_id}, error={e}")
        return None, f"AI生成失败: {str(e)}"

    # ── 写入教案 ──
    plan.ai_bias_prescription = prescription
    plan.ai_prescription_generated_at = get_local_now()
    await db.commit()

    return prescription, None


async def _call_deepseek_text(prompt: str, system_prompt: str, timeout: float = 45.0) -> str:
    """调用DeepSeek API, 返回纯文本 (非JSON模式)"""
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            _LLM_API_URL,
            headers={
                "Authorization": f"Bearer {_LLM_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": _LLM_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.4,
                "max_tokens": 2048,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]
