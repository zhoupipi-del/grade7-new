"""
modules/ai_teacher_assistant/routers.py — API 端点

POST /api/v1/ai-teacher-assistant/class-grade-summary
    班级/年级成绩摘要（AI 分析）。
    权限：需要登录，RBAC 由 services 内 access.py 承担。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from core.models import User
from core.routers import get_current_user, get_db
from sqlalchemy.ext.asyncio import AsyncSession

from .schemas import (
    ClassGradeSummaryRequest, ClassGradeSummaryResponse,
    CopilotRunRequest, CopilotRunResponse,
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
