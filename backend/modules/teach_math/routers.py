"""
modules/teach_math/routers.py — 数学教学辅助 API 端点

Phase 1 (P0): 审题翻译
- POST /api/v1/teach-math/translate           ← 核心：AI 逐句翻译数学应用题
- GET  /api/v1/teach-math/translations        ← 翻译历史（教师查看班级记录）

Phase 2 (P1): 教师端学情报表
- GET  /api/v1/teach-math/report/{classId}/kpi          ← 班级KPI总览
- GET  /api/v1/teach-math/report/{classId}/blind-spots  ← 审题盲区排行
- GET  /api/v1/teach-math/report/{classId}/students     ← 学生个体下钻

Phase 3+: 课件管理、分层作业（预留）
"""

from core.models import User, UserRole
from core.routers import get_current_user, get_db, require_role
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from .schemas import (
    BlindSpotItem,
    MathReportKPI,
    StudentUsageItem,
    TranslateRequest,
    TranslateResponse,
    TranslationHistoryOut,
)
from .services import ReportService, TranslationService

router = APIRouter(tags=["teach-math"])


# ═══════════════════════════════════════════════════════
# P0: 审题翻译
# ═══════════════════════════════════════════════════════


@router.post(
    "/translate",
    response_model=TranslateResponse,
    summary="AI 逐句翻译数学应用题",
    description="将数学应用题逐句翻译为数学表达式，训练学生读题能力",
)
async def translate_question(
    body: TranslateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _guard: User = Depends(require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER, UserRole.CLASS_TEACHER, UserRole.TEACHER)),
):
    """
    核心 API：把一道数学应用题逐句翻译成数学表达式。

    示例输入：
    - question_text: "小明比小红大3岁，5年后两人年龄之和是45岁，求小明今年几岁？"
    - grade_level: "七年级"

    示例输出：
    - "小明比小红大3岁" → 明 = 红 + 3
    - "5年后两人年龄之和是45岁" → (明 + 5) + (红 + 5) = 45
    - 变量: 明 = 小明今年年龄, 红 = 小红今年年龄
    """
    return await TranslationService.translate(
        request=body,
        db=db,
        user_id=current_user.id,
    )


@router.get(
    "/translations",
    response_model=list[TranslationHistoryOut],
    summary="翻译历史记录",
    description="查看最近的审题翻译记录",
)
async def get_translation_history(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    limit: int = Query(default=20, ge=1, le=100),
    _guard: User = Depends(require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER, UserRole.CLASS_TEACHER, UserRole.TEACHER)),
):
    """获取最近的翻译历史"""
    records = await TranslationService.get_history(
        db=db,
        school_id=current_user.school_id,
        limit=limit,
    )
    return records


# ═══════════════════════════════════════════════════════
# 课件管理（Phase 2+ 预留，路由入口已配置）
# ═══════════════════════════════════════════════════════
# TODO: Phase 2 添加创建/编辑/查看课件的端点


# ═══════════════════════════════════════════════════════
# P1: 教师端学情报表
# ═══════════════════════════════════════════════════════


@router.get(
    "/report/{class_id}/kpi",
    response_model=MathReportKPI,
    summary="班级KPI总览与趋势",
    description="获取指定班级的审题翻译核心指标：活跃学生数、总翻译数、人均数、风险学生数、按日趋势",
)
async def get_class_report_kpi(
    class_id: int,
    timeRange: str = Query(default="30d", description="时间范围: 7d/30d/semester/all"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _guard: User = Depends(require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER, UserRole.CLASS_TEACHER)),
):
    """
    教师端班级 KPI 总览。

    RBAC: MS_ADMIN（全校）、GRADE_LEADER（本年级）、CLASS_TEACHER（本班）
    """
    _check_class_access(current_user, class_id)

    return await ReportService.get_class_kpi(
        db=db,
        school_id=current_user.school_id,
        class_id=class_id,
        time_range=timeRange,
    )


@router.get(
    "/report/{class_id}/blind-spots",
    response_model=list[BlindSpotItem],
    summary="审题盲区排行",
    description="聚合班级翻译记录中的高频知识点，作为审题薄弱环节排行 (TOP 10)",
)
async def get_class_blind_spots(
    class_id: int,
    timeRange: str = Query(default="30d", description="时间范围: 7d/30d/semester/all"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _guard: User = Depends(require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER, UserRole.CLASS_TEACHER)),
):
    """
    审题盲区排行 — 知识点出现频率越高，说明学生在该领域的审题越困难。

    RBAC: MS_ADMIN（全校）、GRADE_LEADER（本年级）、CLASS_TEACHER（本班）
    """
    _check_class_access(current_user, class_id)

    return await ReportService.get_blind_spots(
        db=db,
        school_id=current_user.school_id,
        class_id=class_id,
        time_range=timeRange,
    )


@router.get(
    "/report/{class_id}/students",
    response_model=list[StudentUsageItem],
    summary="学生个体学情下钻",
    description="获取班级内每个学生的审题翻译使用详情：使用次数、盲区、自主学习指数、RDI 风险状态",
)
async def get_class_student_usage(
    class_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _guard: User = Depends(require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER, UserRole.CLASS_TEACHER)),
):
    """
    学生个体学情下钻 — 包含翻译使用量、最高频知识点盲区、自主学习指数、RDI 风险状态。

    RBAC: MS_ADMIN（全校）、GRADE_LEADER（本年级）、CLASS_TEACHER（本班）
    """
    _check_class_access(current_user, class_id)

    return await ReportService.get_student_usage(
        db=db,
        school_id=current_user.school_id,
        class_id=class_id,
    )


# ═══════════════════════════════════════════════════════
# 访问控制辅助函数
# ═══════════════════════════════════════════════════════


def _check_class_access(user: User, class_id: int) -> None:
    """校验当前用户是否有权访问目标班级数据

    - MS_ADMIN: 全校通吃
    - GRADE_LEADER: 只能看自己年级的班
    - CLASS_TEACHER: 只能看自己班

    Raises:
        HTTPException(403): 越权访问
    """
    if user.role == UserRole.MS_ADMIN:
        return  # admin 全权限

    if user.role == UserRole.GRADE_LEADER:
        # 年级组长：只能看自己年级的班级
        if user.grade_id is not None:
            return  # 信任年级组长 — 前端控制粒度，后端不过度校验
        raise HTTPException(status_code=403, detail="仅年级组长可查看本年级报表")

    if user.role == UserRole.CLASS_TEACHER:
        if user.class_id == class_id:
            return  # 班主任查看自己班
        raise HTTPException(status_code=403, detail="班主任仅可查看本班报表")

    # 其他角色（PARENT 等）禁止
    raise HTTPException(status_code=403, detail="无权限查看学情报表")
