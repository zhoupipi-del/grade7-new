"""
modules/behavior/routers.py — 违纪行为管理 API

端点:
  POST   /api/v1/behavior/records         创建违纪记录
  GET    /api/v1/behavior/records         分页查询违纪列表
  GET    /api/v1/behavior/records/{id}    查看单条违纪
  PUT    /api/v1/behavior/records/{id}    编辑违纪
  DELETE /api/v1/behavior/records/{id}    删除违纪
  POST   /api/v1/behavior/records/{id}/resolve  标记已解决
  GET    /api/v1/behavior/stats           违纪统计
  GET    /api/v1/behavior/escalation/{student_id}  升级风险评估
  POST   /api/v1/behavior/appeals         提交申诉
  GET    /api/v1/behavior/appeals         申诉列表
  POST   /api/v1/behavior/appeals/{id}/review  审核申诉
"""

from datetime import date

from core.access import get_student_or_403, student_id_scope
from core.models import Student, User, UserRole
from core.routers import (
    get_current_user,
    get_db,
    require_role,
    verify_entity_ownership,
)
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .schemas import (
    AppealCreate,
    AppealOut,
    AppealReview,
    DisciplineCreate,
    DisciplineOut,
    DisciplineUpdate,
    QuickRegisterCreate,
    QuickRegisterOut,
    QuickRegisterStudentOut,
)
from .services import BehaviorService

router = APIRouter(tags=["behavior"])


# ═══════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════


def _resolve_role(role) -> str:
    """自呼吸看守熔断 — 杜绝 str/enum 混合体 AttributeError，始终返回纯字符串"""
    if isinstance(role, UserRole):
        return role.value
    if isinstance(role, str):
        try:
            return UserRole(role).value
        except ValueError:
            return role
    return str(role)


# ═══════════════════════════════════════════════════════════════
# 违纪记录 CRUD
# ═══════════════════════════════════════════════════════════════


@router.post("/records", response_model=DisciplineOut, status_code=201)
async def create_discipline(
    body: DisciplineCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _guard: User = Depends(
        require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER, UserRole.CLASS_TEACHER)
    ),
):
    """创建违纪记录 — 自动触发累计扣分升级检查"""
    # P0 行级归属（2026-08-13 Step ⑦）：班主任/年级组长只能登记
    # 自己可见范围内的学生；跨校→404，本校越权→403。杜绝全校裸列登记。
    await get_student_or_403(db, current_user, body.student_id)
    try:
        record = await BehaviorService.create_record(
            db,
            current_user.school_id,
            body.model_dump(),
            current_user.id,
            creator_role=_resolve_role(current_user.role),
        )
        return _format_record(record)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ═══════════════════════════════════════════════════
# QuickRegister（Step ⑦ 极简可信登记）
# ═══════════════════════════════════════════════════


@router.get("/quick-register/students", response_model=list[QuickRegisterStudentOut])
async def quick_register_students(
    grade_id: int | None = None,
    class_id: int | None = None,
    keyword: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    QuickRegister 学生选择器 —— 严格按角色可见范围返回，绝不全校裸列。
      ms_admin / counselor 等全校角色 → 本校全部（可再按 grade/class 过滤）
      grade_leader                → 授权年级学生
      class_teacher              → 负责班级学生
    零可见（未绑定/无授权）      → 返回空列表（fail-closed）
    """
    scope = await student_id_scope(db, current_user)
    conditions = [Student.school_id == current_user.school_id]
    if scope is not None:
        if not scope:
            return []  # 零可见，直接返回空（不退化成全校）
        conditions.append(Student.id.in_(scope))
    if grade_id:
        conditions.append(Student.grade_id == grade_id)
    if class_id:
        conditions.append(Student.class_id == class_id)
    if keyword:
        conditions.append(Student.name.like(f"%{keyword}%"))

    stmt = (
        select(Student)
        .options(selectinload(Student.class_))
        .where(*conditions)
        .order_by(Student.class_id, Student.student_no)
        .limit(2000)
    )
    students = (await db.execute(stmt)).scalars().all()
    return [_fmt_quick_student(s) for s in students]


@router.post("/quick-register", response_model=QuickRegisterOut, status_code=201)
async def quick_register(
    body: QuickRegisterCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _guard: User = Depends(
        require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER, UserRole.CLASS_TEACHER)
    ),
):
    """
    极简可信登记（Step ⑦）。

    服务端锁死：
      school_id      = 当前用户（外层 get_student_or_403 已确认 student 同校）
      created_by     = 当前用户
      class/grade    = 从 student 反查
      source         = teacher_manual（前端不可传）
      incident_date  = 当前时间
      type/points    = 由 severity 服务端规则计算
    权限：班主任只能登记自己班级学生；年级组长只能登记授权年级；管理员可切 Scope。
    """
    # 1) 学生归属校验（跨校→404；本校越权→403）
    student = await get_student_or_403(db, current_user, body.student_id)
    try:
        record, monthly = await BehaviorService.quick_register(
            db,
            current_user.school_id,
            student,
            current_user.id,
            body.event_type,
            body.severity,
            body.description,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _format_quick(record, monthly)


@router.get("/records")
async def list_discipline(
    class_id: int | None = None,
    grade_id: int | None = None,
    student_id: int | None = None,
    type: str | None = None,
    status: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """分页查询违纪记录列表"""
    # P0 行级范围过滤（2026-08-09 开学前审计）：
    # 原实现只按 school_id 过滤 —— 班主任可读全校各班违纪明细（含学生真实姓名
    # 与违纪描述），家长同样可读。语义见 core.access.student_id_scope。
    scope = await student_id_scope(db, current_user)
    offset = (page - 1) * per_page
    records, total = await BehaviorService.list_records(
        db,
        current_user.school_id,
        class_id=class_id,
        grade_id=grade_id,
        student_id=student_id,
        type=type,
        status=status,
        start_date=start_date,
        end_date=end_date,
        limit=per_page,
        offset=offset,
        student_ids=scope,
    )
    pages = (total + per_page - 1) // per_page if total > 0 else 0
    return {
        "items": [_format_record(r) for r in records],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
    }


@router.get("/records/{record_id}")
async def get_discipline(
    record_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # P0 修复: 多租户隔离
    from .models import DisciplineRecord

    await verify_entity_ownership(db, DisciplineRecord, record_id, current_user, "违纪记录不存在")
    record = await BehaviorService.get_record(db, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="违纪记录不存在")
    return _format_record(record)


@router.put("/records/{record_id}", response_model=DisciplineOut)
async def update_discipline(
    record_id: int,
    body: DisciplineUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """编辑违纪记录"""
    # P0 修复: 多租户隔离
    from .models import DisciplineRecord

    await verify_entity_ownership(db, DisciplineRecord, record_id, current_user, "违纪记录不存在")
    record = await BehaviorService.update_record(db, record_id, body.model_dump(exclude_none=True))
    if not record:
        raise HTTPException(status_code=404, detail="违纪记录不存在")
    return _format_record(record)


@router.delete("/records/{record_id}")
async def delete_discipline(
    record_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _guard: User = Depends(require_role(UserRole.MS_ADMIN)),
):
    """删除违纪记录 — 仅德育处管理员"""
    # P0 修复: 多租户隔离
    from .models import DisciplineRecord

    await verify_entity_ownership(db, DisciplineRecord, record_id, current_user, "违纪记录不存在")
    ok = await BehaviorService.delete_record(db, record_id)
    if not ok:
        raise HTTPException(status_code=404, detail="违纪记录不存在")
    return {"message": "已删除"}


@router.post("/records/{record_id}/resolve", response_model=DisciplineOut)
async def resolve_discipline(
    record_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """标记违纪已解决"""
    # P0 修复: 多租户隔离
    from .models import DisciplineRecord

    await verify_entity_ownership(db, DisciplineRecord, record_id, current_user, "违纪记录不存在")
    record = await BehaviorService.resolve_record(db, record_id)
    if not record:
        raise HTTPException(status_code=400, detail="无法解决该违纪记录（可能已解决或不存在）")
    return _format_record(record)


# ═══════════════════════════════════════════════════════════════
# 统计 & 风险评估
# ═══════════════════════════════════════════════════════════════


@router.get("/stats")
async def discipline_stats(
    grade_id: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """违纪统计概览（按类型/分类/班级/月份分组）"""
    # P0 修复（2026-08-09 开学前审计）：聚合端点同样是越权口子
    # 铁律「修 list 必须同步修 stats」——否则家长/班主任仍能看到全校各班违纪数
    scope = await student_id_scope(db, current_user)
    return await BehaviorService.get_stats(
        db,
        current_user.school_id,
        grade_id=grade_id,
        start_date=start_date,
        end_date=end_date,
        student_ids=scope,
    )


@router.get("/escalation/{student_id}")
async def escalation_risk(
    student_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """查询学生的累计扣分升级风险"""
    # P0+P1-D 修复: 多租户隔离 + 防止跨校信息泄露
    from core.models import Student

    await verify_entity_ownership(db, Student, student_id, current_user, "学生不存在")
    # P0 行级归属（2026-08-09 开学前审计）：补齐同校跨班拦截
    await get_student_or_403(db, current_user, student_id)
    return await BehaviorService.get_escalation_risk(db, student_id)


# ═══════════════════════════════════════════════════════════════
# 申诉
# ═══════════════════════════════════════════════════════════════


@router.post("/appeals", response_model=AppealOut, status_code=201)
async def create_appeal(
    body: AppealCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """提交违纪申诉（家长端）"""
    try:
        appeal = await BehaviorService.create_appeal(
            db,
            current_user.school_id,
            body.model_dump(),
            current_user.id,
            current_user.bound_student_id or 0,
            current_user.class_id or 0,
            current_user.grade_id or 0,
        )
        return _format_appeal(appeal)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/appeals")
async def list_appeals(
    status: str | None = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    appeals, total = await BehaviorService.list_appeals(
        db,
        current_user.school_id,
        status=status,
        limit=per_page,
        offset=(page - 1) * per_page,
    )
    pages = (total + per_page - 1) // per_page if total > 0 else 0
    return {
        "items": [_format_appeal(a) for a in appeals],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
    }


@router.post("/appeals/{appeal_id}/review", response_model=AppealOut)
async def review_appeal(
    appeal_id: int,
    body: AppealReview,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _guard: User = Depends(require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER, UserRole.CLASS_TEACHER)),
):
    """审核申诉（仅德育处/年级组长/班主任）"""
    # P0 修复: 多租户隔离
    from .models import DisciplineAppeal

    await verify_entity_ownership(db, DisciplineAppeal, appeal_id, current_user, "申诉不存在")
    appeal = await BehaviorService.review_appeal(
        db,
        appeal_id,
        body.status,
        body.review_comment or "",
        current_user.id,
    )
    if not appeal:
        raise HTTPException(status_code=400, detail="申诉不存在或已处理")
    return _format_appeal(appeal)


# ═══════════════════════════════════════════════════════════════
# 格式化辅助
# ═══════════════════════════════════════════════════════════════


def _format_record(r) -> dict:
    """安全格式化违纪记录，容错关系未加载"""
    try:
        student_name = r.student.name if r.student else None
        student_no = r.student.student_no if r.student else None
        class_name = (
            r.student.class_.name if r.student and getattr(r.student, "class_", None) else None
        )
        creator_name = r.creator.display_name if r.creator else None
    except Exception:
        student_name = student_no = class_name = creator_name = None
    return {
        "id": r.id,
        "student_id": r.student_id,
        "student_name": student_name,
        "student_no": student_no,
        "class_id": r.class_id,
        "class_name": class_name,
        "grade_id": r.grade_id,
        "type": r.type,
        "category": r.category,
        "description": r.description,
        "action_taken": r.action_taken,
        "points": r.points,
        "status": r.status,
        "verify_status": r.verify_status,
        "incident_date": r.incident_date.isoformat() if r.incident_date else None,
        "created_by": r.created_by,
        "creator_name": creator_name,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "resolved_at": r.resolved_at.isoformat() if r.resolved_at else None,
    }


def _fmt_quick_student(s) -> dict:
    """QuickRegister 学生选择器输出，容错 class 关系未加载"""
    try:
        class_name = s.class_.name if s.class_ else None
    except Exception:
        class_name = None
    return {
        "id": s.id,
        "name": s.name,
        "student_no": s.student_no,
        "class_id": s.class_id,
        "class_name": class_name,
        "grade_id": s.grade_id,
    }


def _format_quick(r, monthly: int) -> dict:
    """QuickRegister 成功响应 —— 携带本月可信次数与展示字段"""
    try:
        student_name = r.student.name if r.student else None
        class_name = (
            r.student.class_.name if r.student and getattr(r.student, "class_", None) else None
        )
    except Exception:
        student_name = class_name = None
    # 程度标签由 type 反推，供前端直接展示「课堂纪律 · 一般」
    severity_label = {"warning": "light", "minor": "normal", "major": "serious", "serious": "serious"}.get(
        r.type, "normal"
    )
    return {
        "id": r.id,
        "student_id": r.student_id,
        "student_name": student_name,
        "class_name": class_name,
        "event_type": r.category or "",
        "category": r.category,
        "type": r.type,
        "severity": severity_label,
        "description": r.description,
        "points": r.points,
        "incident_date": r.incident_date.isoformat() if r.incident_date else None,
        "source": r.source,
        "created_by": r.created_by,
        "monthly_trusted_count": monthly,
    }


def _format_appeal(a) -> dict:
    """安全格式化申诉，容错关系未加载 (避免异步上下文 MissingGreenlet 触发 500)"""
    try:
        student_name = a.student.name if a.student else None
        reviewer_name = a.reviewer.display_name if a.reviewer else None
    except Exception:
        student_name = reviewer_name = None
    return {
        "id": a.id,
        "discipline_id": a.discipline_id,
        "student_id": a.student_id,
        "student_name": student_name,
        "reason": a.reason,
        "status": a.status,
        "review_comment": a.review_comment,
        "reviewer_name": reviewer_name,
        "reviewed_at": a.reviewed_at.isoformat() if a.reviewed_at else None,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }
