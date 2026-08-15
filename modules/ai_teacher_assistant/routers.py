"""
modules/ai_teacher_assistant/routers.py — API 端点

POST /api/v1/ai-teacher-assistant/class-grade-summary
    班级/年级成绩摘要（AI 分析）。
    权限：需要登录，RBAC 由 services 内 access.py 承担。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from core.models import User, UserRole
from core.routers import get_current_user, get_db, require_role
from sqlalchemy.ext.asyncio import AsyncSession
from ai_native.runtime.approval_gate import ApprovalGate, ApprovalGateError

from .schemas import (
    ClassGradeSummaryRequest, ClassGradeSummaryResponse,
    CopilotRunRequest, CopilotRunResponse,
    AvailableScopesResponse,
)
from .services import ClassGradeSummaryService
from .agent_service import AgentCopilotService

router = APIRouter(tags=["AI 教师助手"])


@router.post(
    "/class-grade-summary",
    response_model=ClassGradeSummaryResponse,
    summary="班级/年级成绩 AI 分析",
)
async def class_grade_summary(
    body: ClassGradeSummaryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ClassGradeSummaryResponse:
    """读取班级/年级成绩统计数据，调用 AI 生成分析摘要。

    输出不含学生个人信息（student_id / student_name / 单生分数明细）。
    """
    if current_user.school_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="未绑定学校")

    try:
        svc = ClassGradeSummaryService(db, current_user)
        output = await svc.generate_summary(
            class_id=body.class_id,
            grade_id=body.grade_id,
            exam_id=body.exam_id,
        )
        return ClassGradeSummaryResponse(
            status="completed",
            output=output.model_dump() if hasattr(output, "model_dump") else output,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AI 分析失败: {exc}",
        )


@router.post(
    "/agent/run",
    response_model=CopilotRunResponse,
    summary="AI Agent 自动分析（多工具编排）",
)
async def run_copilot(
    payload: CopilotRunRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CopilotRunResponse:
    """自然语言输入 → Planner 分配 Tool → 执行 → Synthesizer → Critic → 返回。

    输出不含学生个人信息（student_id / student_name / 单生分数明细）。
    """
    if current_user.school_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="未绑定学校")

    service = AgentCopilotService(db=db, user=current_user)
    result = await service.run(
        goal=payload.goal,
        grade_id=payload.grade_id,
        class_id=payload.class_id,
        exam_id=payload.exam_id,
        compare_exam_ids=payload.compare_exam_ids,
    )
    return CopilotRunResponse(**result)


@router.get(
    "/available-scopes",
    response_model=AvailableScopesResponse,
    summary="AI 助手可分析范围（学校/年级）",
)
async def available_scopes(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AvailableScopesResponse:
    """返回当前用户 AI 助手可分析的学校与年级范围（server-side 授权）。

    不暴露全校 grades 表；只返回已授权范围。最终执行仍由
    PermissionChecker + _assert_same_school 兜底。
    """
    if current_user.school_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="未绑定学校")

    service = AgentCopilotService(db=db, user=current_user)
    data = await service.resolve_available_scopes()
    return AvailableScopesResponse(**data)


# ═══════════════════════════════════════════════════════════════
# FT-015：AI 受控动作审批 API（approval gate）
# 权限：ms_admin / grade_leader（复用现有明确管理权限，第一版不做多人会签）
# 校验：已登录 + 同 school + envelope PENDING + 未过期（ApprovalGate fail-closed）
# ═══════════════════════════════════════════════════════════════

@router.post(
    "/approvals/{approval_id}/approve",
    summary="批准 AI 受控动作（approval gate）",
    dependencies=[Depends(require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER))],
)
async def approve_approval(
    approval_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """人工批准：仅 PENDING 且未过期的 approval 可批；tenant 必须匹配当前用户学校。

    FT-015 HTTP 闭环：批准后 resume SAME run（不新建 run），
    ToolExecutor 做最终 approval/hash 校验 → execute exactly once → COMPLETED。
    """
    if current_user.school_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="未绑定学校")
    try:
        gate = ApprovalGate(db, current_user.school_id)
        await gate.approve(approval_id=approval_id,
                           approver_id=current_user.id,
                           school_id=current_user.school_id)
        await db.flush()

        # resume SAME run（approval 已 APPROVED；executor 最终校验 fail-closed）
        service = AgentCopilotService(db=db, user=current_user)
        resume_result = await service.resume_after_approval(approval_id=approval_id)
        await db.commit()
        return {"status": "APPROVED", "approval_id": approval_id, **resume_result}
    except ApprovalGateError as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post(
    "/approvals/{approval_id}/reject",
    summary="拒绝 AI 受控动作（approval gate）",
    dependencies=[Depends(require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER))],
)
async def reject_approval(
    approval_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """人工拒绝：PENDING → REJECTED；SAME run → CANCELLED（completed_at 落库）；永不执行。"""
    if current_user.school_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="未绑定学校")
    try:
        gate = ApprovalGate(db, current_user.school_id)
        await gate.reject(approval_id=approval_id,
                          approver_id=current_user.id,
                          school_id=current_user.school_id)
        await db.flush()

        # cancel SAME run（CANCELLED 终态；tool_call → DENIED）
        service = AgentCopilotService(db=db, user=current_user)
        cancel_result = await service.cancel_after_reject(approval_id=approval_id)
        await db.commit()
        return {"status": "REJECTED", "approval_id": approval_id, **cancel_result}
    except ApprovalGateError as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
