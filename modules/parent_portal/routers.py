"""
modules/parent_portal/routers.py — 家长门户 FastAPI 路由

7 个端点 (1:1 映射前端 parent_portal.ts):
  GET    /parent_portal/dashboard              — 家长仪表盘（聚合）
  GET    /parent_portal/child/overview         — 孩子概览（五维+考勤+违纪+风险）
  POST   /parent_portal/feedbacks              — 提交反馈
  GET    /parent_portal/feedbacks              — 反馈列表
  GET    /parent_portal/feedbacks/{id}         — 反馈详情
  POST   /parent_portal/feedbacks/{id}/reply   — 处理反馈
  POST   /parent_portal/appeals/proxy          — 申诉代理

越权铁闸:
  - 所有端点必须校验 parent_id → bound_student_id 绑定关系
  - PARENT 角色限定（仪表盘/概览/提交反馈/申诉代理）
  - 教师角色可访问反馈列表/详情/处理反馈（闭环双向）
"""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.routers import get_current_user, get_db, require_role
from core.models import User, UserRole

from .schemas import (
    FeedbackTypeEnum, FeedbackStatusEnum, AppealTargetModuleEnum,
    FeedbackItem, FeedbackListResponse, ChildOverview, ParentDashboard,
    AppealProxyResult, FeedbackCreatePayload, FeedbackReplyPayload,
    AppealProxyPayload, fill_labels,
)
from .services import (
    ParentPortalService, FeedbackService, AppealProxyService,
    verify_parent_binding,
)

logger = logging.getLogger("parent_portal")

router = APIRouter(tags=["parent_portal"])


# ═══════════════════════════════════════════════════════════════
# 越权铁闸依赖注入 — parent_id → bound_student_id 绑定校验
# ═══════════════════════════════════════════════════════════════

async def require_parent_with_binding(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    家长角色 + 绑定校验铁闸。

    规则:
      1. 必须是 PARENT 角色
      2. bound_student_id 不能为 NULL
      3. 返回 User 对象（后续端点通过 user.bound_student_id 获取 student_id）

    此依赖注入用于: dashboard / child/overview / feedbacks POST / appeals/proxy
    """
    user_role = current_user.role
    if isinstance(user_role, str):
        user_role = UserRole(user_role)

    if user_role != UserRole.PARENT:
        raise HTTPException(status_code=403, detail="仅家长角色可访问此端点")

    if current_user.bound_student_id is None:
        raise HTTPException(status_code=403, detail="家长账号未绑定学生，请联系管理员")

    return current_user


async def require_teacher_or_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    教师/德育处角色守卫 — 用于反馈列表/详情/处理反馈端点。

    允许: MS_ADMIN / GRADE_LEADER / CLASS_TEACHER
    这些角色可查看全校反馈列表并处理反馈（闭环双向）。
    """
    user_role = current_user.role
    if isinstance(user_role, str):
        user_role = UserRole(user_role)

    allowed = {UserRole.MS_ADMIN, UserRole.GRADE_LEADER, UserRole.CLASS_TEACHER, UserRole.PARENT}
    if user_role not in allowed:
        raise HTTPException(status_code=403, detail="仅教师/德育处/家长角色可访问此端点")

    return current_user


# ═══════════════════════════════════════════════════════════════
# 端点 1: GET /dashboard — 家长仪表盘
# ═══════════════════════════════════════════════════════════════

@router.get("/dashboard", response_model=ParentDashboard)
async def get_dashboard(
    db: AsyncSession = Depends(get_db),
    parent_user: User = Depends(require_parent_with_binding),
):
    """
    家长仪表盘 — 聚合孩子概览 + 未读通知 + 待处理反馈 + 最近反馈。

    越权铁闸: require_parent_with_binding 确保家长角色 + bound_student_id 绑定。
    数据范围: 仅返回当前家长绑定孩子的数据。
    """
    return await ParentPortalService.get_dashboard(db, parent_user)


# ═══════════════════════════════════════════════════════════════
# 端点 2: GET /child/overview — 孩子概览
# ═══════════════════════════════════════════════════════════════

@router.get("/child/overview", response_model=ChildOverview)
async def get_child_overview(
    db: AsyncSession = Depends(get_db),
    parent_user: User = Depends(require_parent_with_binding),
):
    """
    孩子概览 — 五维分数 + 考勤统计 + 违纪记录 + 时间轴 + 风险等级。

    越权铁闸: 仅返回 bound_student_id 对应学生的数据。
    聚合源: evaluation + attendance + behavior + risk_models + growth
    """
    student = await verify_parent_binding(db, parent_user, parent_user.bound_student_id)
    return await ParentPortalService.get_child_overview(db, student, parent_user.school_id)


# ═══════════════════════════════════════════════════════════════
# 端点 3: POST /feedbacks — 提交反馈
# ═══════════════════════════════════════════════════════════════

@router.post("/feedbacks", response_model=FeedbackItem, status_code=201)
async def create_feedback(
    body: FeedbackCreatePayload,
    db: AsyncSession = Depends(get_db),
    parent_user: User = Depends(require_parent_with_binding),
):
    """
    家长提交反馈 — 血缘追踪 + 自动通知班主任。

    越权铁闸: body.student_id 必须等于 parent_user.bound_student_id。
    闭环: 提交 → 通知班主任 → 班主任处理 → 通知家长。
    """
    # 越权铁闸: 校验 student_id 与绑定一致
    if body.student_id != parent_user.bound_student_id:
        raise HTTPException(
            status_code=403,
            detail=f"越权拦截: 请求学生ID {body.student_id} 与绑定学生ID {parent_user.bound_student_id} 不一致",
        )

    payload_data = body.model_dump()
    feedback = await FeedbackService.create_feedback(db, parent_user, payload_data)
    await db.commit()
    return fill_labels(FeedbackItem.model_validate(feedback))


# ═══════════════════════════════════════════════════════════════
# 端点 4: GET /feedbacks — 反馈列表
# ═══════════════════════════════════════════════════════════════

@router.get("/feedbacks", response_model=FeedbackListResponse)
async def list_feedbacks(
    status: Optional[FeedbackStatusEnum] = None,
    feedback_type: Optional[FeedbackTypeEnum] = None,
    offset: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
):
    """
    反馈列表 — 双角色视图:
      - PARENT: 只看自己的反馈
      - 教师/德育处: 看全校反馈
    """
    return await FeedbackService.list_feedbacks(
        db, current_user,
        status_filter=status.value if status else None,
        feedback_type_filter=feedback_type.value if feedback_type else None,
        offset=offset, limit=limit,
    )


# ═══════════════════════════════════════════════════════════════
# 端点 5: GET /feedbacks/{id} — 反馈详情
# ═══════════════════════════════════════════════════════════════

@router.get("/feedbacks/{feedback_id}", response_model=FeedbackItem)
async def get_feedback_detail(
    feedback_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
):
    """
    反馈详情 — PARENT 只能看自己的，教师可看全校。
    """
    return await FeedbackService.get_feedback_detail(db, feedback_id, current_user)


# ═══════════════════════════════════════════════════════════════
# 端点 6: POST /feedbacks/{id}/reply — 处理反馈
# ═══════════════════════════════════════════════════════════════

@router.post("/feedbacks/{feedback_id}/reply", response_model=FeedbackItem)
async def reply_feedback(
    feedback_id: int,
    body: FeedbackReplyPayload,
    db: AsyncSession = Depends(get_db),
    handler: User = Depends(require_role(UserRole.CLASS_TEACHER, UserRole.GRADE_LEADER, UserRole.MS_ADMIN)),
):
    """
    班主任/德育处处理反馈 — 双向闭环。

    闭环: 处理后自动通知家长"您的反馈已被处理"。
    角色限定: CLASS_TEACHER / GRADE_LEADER / MS_ADMIN
    """
    reply_data = body.model_dump()
    feedback = await FeedbackService.reply_feedback(db, feedback_id, handler, reply_data)
    await db.commit()
    return fill_labels(FeedbackItem.model_validate(feedback))


# ═══════════════════════════════════════════════════════════════
# 端点 7: POST /appeals/proxy — 申诉代理
# ═══════════════════════════════════════════════════════════════

@router.post("/appeals/proxy", response_model=AppealProxyResult)
async def proxy_appeal(
    body: AppealProxyPayload,
    db: AsyncSession = Depends(get_db),
    parent_user: User = Depends(require_parent_with_binding),
):
    """
    申诉代理 — Facade 模式路由到 discipline/behavior 已有审批流。

    越权铁闸: body.student_id 必须等于 parent_user.bound_student_id。
    路由规则:
      - discipline → 处分申诉（路由到 approval 模块创建 discipline_appeal 工单）
      - behavior → 违纪申诉（路由到 approval 模块创建 behavior_appeal 工单）
    """
    # 越权铁闸: 校验 student_id 与绑定一致
    if body.student_id != parent_user.bound_student_id:
        raise HTTPException(
            status_code=403,
            detail=f"越权拦截: 请求学生ID {body.student_id} 与绑定学生ID {parent_user.bound_student_id} 不一致",
        )

    payload_data = body.model_dump()
    result = await AppealProxyService.proxy_appeal(db, parent_user, payload_data)
    await db.commit()
    return result
