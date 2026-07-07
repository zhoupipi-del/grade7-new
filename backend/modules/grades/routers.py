"""
modules/grades/routers.py — 成绩管理 API 端点（12 个端点）

端点清单:
  科目 CRUD (4):
    POST   /subjects              — 创建科目 (MS_ADMIN)
    GET    /subjects              — 科目列表 (MS_ADMIN)
    PUT    /subjects/{id}         — 更新科目 (MS_ADMIN)
    PATCH  /subjects/{id}/toggle  — 启停科目 (MS_ADMIN)

  考试 CRUD (4):
    POST   /exams                 — 创建考试 (MS_ADMIN)
    GET    /exams                 — 考试列表 (MS_ADMIN)
    PUT    /exams/{id}            — 更新考试 (MS_ADMIN)
    PATCH  /exams/{id}/status     — 状态变更 (MS_ADMIN)

  成绩管理 (3):
    POST   /scores/upload         — 批量录入 (MS_ADMIN)
    GET    /scores/results        — 成绩查询分页 (认证用户)
    GET    /scores/{exam_id}/student/{student_id} — 单人成绩 (认证用户)

  审计日志 (1):
    GET    /audit-logs            — 审计日志分页 (MS_ADMIN)
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import User, UserRole
from core.routers import get_db, get_current_user, require_role
from .services import SubjectService, ExamService, ScoreService, AuditService
from .schemas import (
    SubjectCreate, SubjectUpdate, SubjectOut, SubjectItem,
    ExamCreate, ExamUpdate, ExamOut, ExamItem,
    ScoreUploadRequest, ScoreUploadResult,
    ExamResultQuery, ExamResultPage, StudentExamResult,
    AuditLogQuery, AuditLogOut,
)

router = APIRouter(tags=["grades"])


# ═══════════════════════════════════════════════════════════════
# 科目 CRUD (4)
# ═══════════════════════════════════════════════════════════════

@router.post(
    "/subjects",
    response_model=SubjectOut,
    summary="创建科目",
    description="注册新考试科目（语文/数学/英语...），需 MS_ADMIN 权限",
)
async def create_subject(
    body: SubjectCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_role(UserRole.MS_ADMIN)),
):
    """创建一个新科目。code 在同一学校内必须唯一。"""
    try:
        subject = await SubjectService.create_subject(
            db=db,
            school_id=current_user.school_id,
            data=body,
        )
        return subject
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/subjects",
    response_model=list[SubjectItem],
    summary="科目列表",
    description="获取学校所有科目，可选仅返回已启用科目",
)
async def list_subjects(
    active_only: bool = Query(default=False, description="仅返回已启用科目"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_role(UserRole.MS_ADMIN)),
):
    """列出当前学校的所有科目，按 sort_order 排序。"""
    subjects = await SubjectService.list_subjects(
        db=db,
        school_id=current_user.school_id,
        active_only=active_only,
    )
    return subjects


@router.put(
    "/subjects/{subject_id}",
    response_model=SubjectOut,
    summary="更新科目",
    description="更新科目信息（部分更新，只传需要修改的字段）",
)
async def update_subject(
    subject_id: int,
    body: SubjectUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_role(UserRole.MS_ADMIN)),
):
    """更新科目信息，字段为空表示不修改。"""
    try:
        subject = await SubjectService.update_subject(
            db=db,
            school_id=current_user.school_id,
            subject_id=subject_id,
            data=body,
        )
        return subject
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch(
    "/subjects/{subject_id}/toggle",
    response_model=SubjectOut,
    summary="启停科目",
    description="翻转科目的启用/禁用状态",
)
async def toggle_subject(
    subject_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_role(UserRole.MS_ADMIN)),
):
    """切换科目的 is_active 状态（启用/禁用翻转）。"""
    try:
        subject = await SubjectService.toggle_subject_active(
            db=db,
            school_id=current_user.school_id,
            subject_id=subject_id,
        )
        return subject
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ═══════════════════════════════════════════════════════════════
# 考试 CRUD (4)
# ═══════════════════════════════════════════════════════════════

@router.post(
    "/exams",
    response_model=ExamOut,
    summary="创建考试",
    description="创建一次新考试（月考/期中/期末），需 MS_ADMIN 权限",
)
async def create_exam(
    body: ExamCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_role(UserRole.MS_ADMIN)),
):
    """创建考试。创建后状态默认为 draft。"""
    try:
        exam = await ExamService.create_exam(
            db=db,
            school_id=current_user.school_id,
            data=body,
            user_id=current_user.id,
        )
        return exam
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/exams",
    response_model=list[ExamItem],
    summary="考试列表",
    description="获取学校所有考试，可按年级/学期/状态过滤",
)
async def list_exams(
    grade_id: Optional[int] = Query(default=None, description="年级 ID"),
    semester: Optional[str] = Query(default=None, description="学期标识"),
    status: Optional[str] = Query(default=None, description="考试状态: draft/published/archived"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_role(UserRole.MS_ADMIN)),
):
    """列出当前学校的所有考试，支持多维度过滤。"""
    exams = await ExamService.list_exams(
        db=db,
        school_id=current_user.school_id,
        grade_id=grade_id,
        semester=semester,
        status=status,
    )
    return exams


@router.put(
    "/exams/{exam_id}",
    response_model=ExamOut,
    summary="更新考试",
    description="更新考试信息（部分更新）",
)
async def update_exam(
    exam_id: int,
    body: ExamUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_role(UserRole.MS_ADMIN)),
):
    """更新考试元信息，字段为空表示不修改。"""
    try:
        exam = await ExamService.update_exam(
            db=db,
            school_id=current_user.school_id,
            exam_id=exam_id,
            data=body,
        )
        return exam
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch(
    "/exams/{exam_id}/status",
    response_model=ExamOut,
    summary="变更考试状态",
    description="修改考试状态: draft → published → archived",
)
async def change_exam_status(
    exam_id: int,
    new_status: str = Query(..., description="新状态: draft / published / archived"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_role(UserRole.MS_ADMIN)),
):
    """变更考试状态（draft→published→archived）。三种状态的流转由前端控制。"""
    try:
        exam = await ExamService.change_exam_status(
            db=db,
            school_id=current_user.school_id,
            exam_id=exam_id,
            new_status=new_status,
        )
        return exam
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ═══════════════════════════════════════════════════════════════
# 成绩管理 (3)
# ═══════════════════════════════════════════════════════════════

@router.post(
    "/scores/upload",
    response_model=ScoreUploadResult,
    summary="批量录入成绩",
    description="批量 upsert 成绩（新增或覆盖），完成后自动计算排名",
)
async def upload_scores(
    body: ScoreUploadRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_role(UserRole.MS_ADMIN)),
):
    """
    批量成绩录入 — 两趟扫描模式：

    扫描 1: 逐条 upsert（新增或覆盖已有记录），记录变更审计
    扫描 2: 使用 SQL 窗口函数统一计算班级排名和年级排名（DENSE_RANK 语义）

    返回成功/失败计数及错误详情。
    """
    result = await ScoreService.upload_scores(
        db=db,
        school_id=current_user.school_id,
        data=body,
        operator_id=current_user.id,
        operator_name=current_user.name,
    )
    return result


@router.get(
    "/scores/results",
    response_model=ExamResultPage,
    summary="考试成绩查询",
    description="按考试 ID 查询成绩，支持按班级/姓名过滤、分页、排名",
)
async def get_exam_results(
    exam_id: int = Query(..., description="考试 ID"),
    class_id: Optional[int] = Query(default=None, description="班级 ID（可选，按班级过滤）"),
    student_name: Optional[str] = Query(default=None, description="学生姓名模糊搜索"),
    sort_by: str = Query(default="total_score_desc", description="排序: total_score_desc / total_score_asc"),
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=50, ge=1, le=200, description="每页条数"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    查询某次考试的所有成绩：

    - 返回每位学生的全科明细、总分、均分、班级排名、年级排名
    - 附带班级汇总统计（均分/最高/最低/及格率/优秀率/单科统计）
    - 支持按班级过滤和学生姓名模糊搜索
    """
    query = ExamResultQuery(
        exam_id=exam_id,
        class_id=class_id,
        student_name=student_name,
        sort_by=sort_by,
        page=page,
        page_size=page_size,
    )
    try:
        return await ScoreService.get_exam_results(
            db=db,
            school_id=current_user.school_id,
            query=query,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get(
    "/scores/{exam_id}/student/{student_id}",
    response_model=StudentExamResult,
    summary="单人成绩查询",
    description="查询某学生在某次考试中的全科成绩及排名",
)
async def get_student_result(
    exam_id: int,
    student_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取单个学生在指定考试中的全科成绩、总分、均分、班级/年级排名。"""
    result = await ScoreService.get_student_result(
        db=db,
        school_id=current_user.school_id,
        exam_id=exam_id,
        student_id=student_id,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="未找到该学生的成绩记录")
    return result


# ═══════════════════════════════════════════════════════════════
# 审计日志 (1)
# ═══════════════════════════════════════════════════════════════

@router.get(
    "/audit-logs",
    summary="审计日志查询",
    description="分页查询成绩变更审计日志，需 MS_ADMIN 权限",
)
async def get_audit_logs(
    exam_id: Optional[int] = Query(default=None, description="按考试 ID 过滤"),
    student_id: Optional[int] = Query(default=None, description="按学生 ID 过滤"),
    action: Optional[str] = Query(default=None, description="操作类型: upsert / delete"),
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=50, ge=1, le=200, description="每页条数"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_role(UserRole.MS_ADMIN)),
):
    """
    查询成绩变更审计日志。

    每条日志记录：谁在何时、修改了哪个学生的哪科成绩、旧分→新分。
    仅 MS_ADMIN 可访问。
    """
    query = AuditLogQuery(
        exam_id=exam_id,
        student_id=student_id,
        action=action,
        page=page,
        page_size=page_size,
    )
    logs, total = await AuditService.query_logs(
        db=db,
        school_id=current_user.school_id,
        query=query,
    )
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "logs": [AuditLogOut.model_validate(log) for log in logs],
    }
