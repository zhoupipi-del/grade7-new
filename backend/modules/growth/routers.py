"""
modules/growth/routers.py — 成长时间轴 API 路由

注册路径: /api/v1/growth/*

═══════════════════════════════════════════════════════════════
  防越权铁壁（Anti-Leak Defense）
═══════════════════════════════════════════════════════════════

家长端极易遭受「ID 遍历攻击」——
  攻击者将 URL 中 student_id=154 篡改为 155，试图偷窥其他学生档案。

本模块 RBAC 守卫策略:
  1. Parent Token:
      强制比对 current_user.bound_student_id == path_student_id
      不匹配 → 403 Forbidden（硬核熔断）

  2. Class Teacher Token:
      查询 student.class_id == current_user.class_id
      非本班 → 403

  3. Grade Leader Token:
      查询 student.grade_id == current_user.grade_id
      非本年级 → 403

  4. MS Admin Token:
      全量通行（多租户隔离仍生效：school_id 必须匹配）

所有端点统一经过 `_verify_student_access()` 守卫工厂。
"""

from core.models import Student, User, UserRole
from core.routers import get_current_user, get_db
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from .schemas import GrowthTimelineResponse
from .services import get_growth_timeline as build_growth_timeline

router = APIRouter(tags=["growth"])


# ═══════════════════════════════════════════════════════════════
#   RBAC 守卫工厂：防 ID 遍历越权
# ═══════════════════════════════════════════════════════════════


async def _verify_student_access(
    student_id: int,
    current_user: User,
    db: AsyncSession,
) -> Student:
    """
    防越权 ID 遍历守卫 —— 返回已验证的学生 ORM 对象。

    逻辑:
      - Parent:    bound_student_id 必须精确匹配，否则 403
      - ClassTeacher: 学生必须在本班，否则 403
      - GradeLeader: 学生必须在本年级，否则 403
      - MS Admin:   全量通行（school_id 隔离仍生效）

    返回: Student ORM 对象（已加载 class_ 关系）
    异常: 404（学生不存在）/ 403（越权）/ 400（家长未绑定学生）
    """
    # ── 1. 查询学生基本信息（含 class_ 关系）────────────────────
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    result = await db.execute(
        select(Student)
        .options(selectinload(Student.class_))
        .where(
            Student.id == student_id,
            Student.school_id == current_user.school_id,
        )
    )
    student = result.scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="学生不存在或无访问权限")

    role = current_user.role
    if isinstance(role, str):
        role = UserRole(role)

    # ── 2. Parent 铁壁 ─────────────────────────────────────────
    if role == UserRole.PARENT:
        if not current_user.bound_student_id:
            raise HTTPException(
                status_code=400, detail="当前账号未绑定学生，请联系班主任绑定后查看成长记录"
            )
        if current_user.bound_student_id != student_id:
            # 记录越权尝试日志（可接 ELK/Sentry）
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(
                f"[越权尝试] Parent user_id={current_user.id} "
                f"尝试访问非绑定学生 student_id={student_id} "
                f"(绑定: {current_user.bound_student_id})"
            )
            raise HTTPException(status_code=403, detail="无权查看该学生的成长记录")

    # ── 3. Class Teacher 守卫 ─────────────────────────────────
    elif role == UserRole.CLASS_TEACHER:
        if not current_user.class_id:
            raise HTTPException(status_code=403, detail="班主任账号未配置班级")
        if student.class_id != current_user.class_id:
            raise HTTPException(status_code=403, detail="无权查看其他班级学生的成长记录")

    # ── 4. Grade Leader 守卫 ───────────────────────────────────
    elif role == UserRole.GRADE_LEADER:
        if not current_user.grade_id:
            raise HTTPException(status_code=403, detail="年级组长账号未配置年级")
        if student.grade_id != current_user.grade_id:
            raise HTTPException(status_code=403, detail="无权查看其他年级学生的成长记录")

    # ── 5. MS Admin / Teacher / Student: 全量通行 ─────────────
    # （多租户隔离已由 school_id 过滤保证）

    return student


# ═══════════════════════════════════════════════════════════════
#   核心端点：成长时间轴
# ═══════════════════════════════════════════════════════════════


@router.get(
    "/timeline/{student_id}",
    response_model=GrowthTimelineResponse,
    summary="查询学生成长时间轴",
    description=(
        "成长时间轴核心 API：7 路数据源并行融合（违纪/处分/考勤/评分流水/回血进展/RDI 风险预警/素质评价）。\n\n"
        "⚠️ 防越权：家长 Token 只能访问自己绑定的学生 ID；"
        "班主任/年级组长 Token 按角色范围自动过滤。"
    ),
)
async def read_growth_timeline(
    student_id: int,
    semester: str | None = Query(
        None, description="学期过滤，格式: 2025-2026-1（上学期）/ 2025-2026-2（下学期）"
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    成长时间轴聚合端点 — Phase 2 七路数据源融合。

    Phase 1（核心行为数据，硬失败熔断）:
      - discipline_records     日常行为记录，已柔化文案
      - discipline_sanctions   行政处分记录，含撤销
      - attendance_records     考勤异常记录

    Phase 2（扩展数据源，软失败降级为 []）:
      - score_logs             评分流水变动（30 天窗口 + LIMIT 50 + 投影查询）
      - recovery_states        回血进展里程碑（仅展示 recovery_ratio > 0）
      - risk_warnings          RDI 风险预警里程碑（risk_level >= attention）
      - evaluation_scores      素质评价指标数据

    时间轴按 occurred_at DESC 排序。
    """
    # ── 防越权守卫（硬核熔断）──────────────────────────────────
    await _verify_student_access(student_id, current_user, db)

    # ── 调用融合服务 ─────────────────────────────────────────────
    timeline = await build_growth_timeline(
        db=db,
        school_id=current_user.school_id,
        student_id=student_id,
        semester=semester,
    )

    return timeline


# ═══════════════════════════════════════════════════════════════
#   便捷端点：当前家长绑定学生的成长时间轴（无需传 student_id）
# ═══════════════════════════════════════════════════════════════


@router.get(
    "/my-timeline",
    response_model=GrowthTimelineResponse,
    summary="查询当前家长绑定学生的成长时间轴（便捷端点）",
    description=(
        "家长登录后直接访问，无需指定 student_id。\n自动使用 Token 中绑定的 bound_student_id。"
    ),
)
async def get_my_timeline(
    semester: str | None = Query(None, description="学期过滤"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    便捷端点：家长查看自己孩子的成长时间轴。

    自动从 JWT Token 中提取 bound_student_id，无需手动传参。
    7 路数据源并行融合，Phase 2 扩展源故障时自动降级不阻塞核心数据。
    非家长角色访问此端点返回 403。
    """
    role = current_user.role
    if isinstance(role, str):
        role = UserRole(role)

    if role != UserRole.PARENT:
        raise HTTPException(status_code=403, detail="此端点仅限家长使用")

    if not current_user.bound_student_id:
        raise HTTPException(status_code=400, detail="当前账号未绑定学生，请联系班主任完成绑定")

    timeline = await build_growth_timeline(
        db=db,
        school_id=current_user.school_id,
        student_id=current_user.bound_student_id,
        semester=semester,
    )

    return timeline


# ═══════════════════════════════════════════════════════════════
#  P0 新增：成长事件管理 + 快照引擎 + 全息画像
# ═══════════════════════════════════════════════════════════════

from . import services as growth_svc
from .schemas import (
    AlertResolveRequest,
    AlertResolveResponse,
    CompositeAlertDetail,
    SnapshotGenerateRequest,
    TeacherCommentUpdate,
    TimelineEventCreate,
)

MGMT_ROLES = [UserRole.MS_ADMIN, UserRole.GRADE_LEADER, UserRole.CLASS_TEACHER]


@router.get("/dashboard", summary="成长档案看板")
async def growth_dashboard(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """成长档案看板统计"""
    data = await growth_svc.get_growth_dashboard(db, user.school_id)
    return data


@router.post("/events", status_code=201, summary="创建成长事件")
async def create_event(
    data: TimelineEventCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """手动注入成长事件（教师/管理员）"""
    await _verify_student_access(data.student_id, user, db)
    event = await growth_svc.add_timeline_event(
        db,
        user.school_id,
        data,
        reporter_id=user.id,
    )
    return {"id": event.id, "title": event.title, "dimension": event.dimension}


@router.get("/events", summary="列出成长事件")
async def list_events(
    student_id: int | None = Query(None),
    dimension: str | None = Query(None),
    severity: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """列出成长事件，支持维度/级别筛选"""
    filter_student_id = student_id
    if user.role.upper() == "PARENT":
        filter_student_id = user.bound_student_id
        if not filter_student_id:
            raise HTTPException(403, "未绑定学生")

    items, total = await growth_svc.list_timeline_events(
        db,
        user.school_id,
        student_id=filter_student_id,
        dimension=dimension,
        severity=severity,
        page=page,
        page_size=page_size,
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/profile/{student_id}", summary="学生全息成长画像")
async def holistic_profile(
    student_id: int,
    semester_label: str | None = Query(
        None, description="学期标签，如 2025-2026-2（不传则自动计算当前学期）"
    ),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    全息成长画像 — 自动生成当期快照 + 历史趋势 + 近期事件 + 7路融合时间轴

    请求触发时自动调用 GrowthAggregationPipeline.run_semester_snapshot()
    归一化五维数据，确保 current_snapshot 始终为最新。
    """
    await _verify_student_access(student_id, user, db)
    profile = await growth_svc.get_holistic_profile(
        db,
        user.school_id,
        student_id,
        semester_label=semester_label,
    )
    if not profile:
        raise HTTPException(404, "学生不存在")
    return profile


@router.post("/snapshots/generate", summary="生成周期快照")
async def generate_snapshot(
    data: SnapshotGenerateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """生成月度/学期成长快照（五维归一化引擎）"""
    await _verify_student_access(data.student_id, user, db)
    snap = await growth_svc.generate_snapshot(
        db,
        user.school_id,
        data.student_id,
        data.snapshot_type,
        data.period_label,
    )
    return growth_svc._snapshot_to_response(snap)


@router.get("/snapshots", summary="列出成长快照")
async def list_snapshots(
    student_id: int | None = Query(None),
    snapshot_type: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """列出周期性成长快照"""
    filter_student_id = student_id
    if user.role.upper() == "PARENT":
        filter_student_id = user.bound_student_id
        if not filter_student_id:
            raise HTTPException(403, "未绑定学生")

    from sqlalchemy import and_ as sa_and
    from sqlalchemy import desc as sa_desc
    from sqlalchemy import func as sa_func
    from sqlalchemy import select as sa_select

    from .models import GrowthPeriodicalSnapshot

    conditions = [GrowthPeriodicalSnapshot.school_id == user.school_id]
    if filter_student_id:
        conditions.append(GrowthPeriodicalSnapshot.student_id == filter_student_id)
    if snapshot_type:
        conditions.append(GrowthPeriodicalSnapshot.snapshot_type == snapshot_type)

    where_clause = sa_and(*conditions)
    count_result = await db.execute(
        sa_select(sa_func.count(GrowthPeriodicalSnapshot.id)).where(where_clause)
    )
    total = count_result.scalar() or 0

    result = await db.execute(
        sa_select(GrowthPeriodicalSnapshot)
        .where(where_clause)
        .order_by(sa_desc(GrowthPeriodicalSnapshot.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    snaps = result.scalars().all()
    items = [growth_svc._snapshot_to_response(s) for s in snaps]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.put("/snapshots/{snapshot_id}/comment", summary="更新班主任评语")
async def update_comment(
    snapshot_id: int,
    data: TeacherCommentUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """班主任录入期末评语"""
    snap = await growth_svc.update_teacher_comment(
        db,
        user.school_id,
        snapshot_id,
        data.teacher_comment,
    )
    if not snap:
        raise HTTPException(404, "快照不存在")
    return {"id": snap.id, "teacher_comment": snap.teacher_comment}


# ═══════════════════════════════════════════════════════════════
#   动态五维雷达 + 德育量化工单
# ═══════════════════════════════════════════════════════════════

from .analytics import DynamicGrowthEngine


@router.get(
    "/radar/{student_id}",
    summary="动态五维成长雷达 — 13路降维 + 时间衰减",
    description=(
        "实时计算学生五维雷达得分（道德品行/学业发展/身心健康/行为习惯/综合实践）。\n\n"
        "数据源: 考勤 + 违纪 + 处分 + 学业趋势 + 错题断层 + 作业 + 心理风险 + 时光轴 + 快照 + 活动。\n"
        "算法: Time-Decay(λ=0.05) → 降维映射矩阵 → Sigmoid归一化。\n"
        "附: 分值跌破警戒线时自动挂牌德育工单。"
    ),
)
async def five_dimension_radar(
    student_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    动态五维雷达 — 13路全息事件流 → 5维 Sigmoid 归一化得分。

    返回结构:
      scores:    {moral, academic, psych, habit, practice}  0-100
      penalties: 各维度原始扣分（调试用）
      sources:   各路数据采集摘要
      alerts:    本次触发的德育工单列表
    """
    await _verify_student_access(student_id, user, db)
    result = await DynamicGrowthEngine.compute_five_dimensions(
        db=db,
        student_id=student_id,
        school_id=user.school_id,
    )
    return result


@router.get(
    "/moral-ledger",
    summary="德育量化工单列表",
    description="查询德育闭环自动挂牌的工单记录，支持按学生/未解除筛选。",
)
async def list_moral_ledger(
    student_id: int | None = Query(None, description="按学生筛选"),
    unresolved_only: bool = Query(False, description="仅显示未解除工单"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """德育工单列表 — 班主任/年级组长/德育处可用"""
    role = user.role
    if isinstance(role, str):
        role = UserRole(role)

    # 家长只能看自己孩子的
    filter_student_id = student_id
    if role == UserRole.PARENT:
        if not user.bound_student_id:
            raise HTTPException(403, "未绑定学生")
        filter_student_id = user.bound_student_id
    elif role == UserRole.CLASS_TEACHER and not student_id:
        # 班主任不指定 student_id 时看全量（后续可加 class_id 过滤）
        pass

    result = await DynamicGrowthEngine.get_ledger_entries(
        db=db,
        school_id=user.school_id,
        student_id=filter_student_id,
        unresolved_only=unresolved_only,
        page=page,
        page_size=page_size,
    )
    return result


@router.put(
    "/moral-ledger/{ledger_id}/resolve",
    summary="解除德育工单挂牌",
    description="班主任/年级组长/德育处执行干预后，解除学生的德育量化工单。",
)
async def resolve_moral_ledger(
    ledger_id: int,
    note: str | None = Query(None, description="干预说明"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """解除挂牌 — 标记工单为已解决，记录干预说明"""
    role = user.role
    if isinstance(role, str):
        role = UserRole(role)

    if role not in (UserRole.MS_ADMIN, UserRole.GRADE_LEADER, UserRole.CLASS_TEACHER):
        raise HTTPException(403, "仅管理角色可解除工单")

    entry = await DynamicGrowthEngine.resolve_ledger_entry(
        db=db,
        ledger_id=ledger_id,
        school_id=user.school_id,
        resolved_by=user.id,
        note=note or "",
    )
    if not entry:
        raise HTTPException(404, "工单不存在或无权操作")
    return {
        "id": entry.id,
        "is_resolved": entry.is_resolved,
        "resolved_at": entry.resolved_at,
        "resolved_by": entry.resolved_by,
        "resolution_note": entry.resolution_note,
    }


# ═══════════════════════════════════════════════════════════════
#   CEP 复合预警 Alert API — 前端沙箱消费
# ═══════════════════════════════════════════════════════════════

from core.models import get_local_now
from sqlalchemy import select as sa_select

from .models import ActiveCompositeAlert


@router.get(
    "/alerts/{alert_id}",
    response_model=CompositeAlertDetail,
    summary="获取复合预警详情（含AI处方）",
    description=(
        "前端沙箱消费端点：查询 ActiveCompositeAlert 完整详情，\n"
        "包含 V3 AI 引擎生成的靶向处方（Markdown 格式），\n"
        "供前端打字机动画渲染 + 人工微调 textarea。\n\n"
        "RBAC: MS_ADMIN / GRADE_LEADER / CLASS_TEACHER 可查看本校预警；"
        "班主任仅能查看本班学生的预警。"
    ),
)
async def get_composite_alert(
    alert_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    获取复合预警详情 — 前端沙箱核心数据源

    1. 查询 alert 并校验 school_id（多租户红线）
    2. 班主任额外校验: 该学生必须在本班
    3. 已 resolved 的预警仍可查看（历史回溯）
    """
    result = await db.execute(
        sa_select(ActiveCompositeAlert).where(ActiveCompositeAlert.id == alert_id)
    )
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(404, "预警不存在")

    # 多租户红线
    if alert.school_id != user.school_id:
        raise HTTPException(403, "无权查看其他学校的预警数据")

    # 班主任铁闸 — 只能看本班学生的预警
    role = user.role
    if isinstance(role, str):
        role = UserRole(role)
    if role == UserRole.CLASS_TEACHER:
        # 查询学生所在班级
        student_result = await db.execute(sa_select(Student).where(Student.id == alert.student_id))
        student = student_result.scalar_one_or_none()
        if not student or student.class_id != user.class_id:
            raise HTTPException(403, "无权查看其他班级学生的预警")

    return alert


@router.post(
    "/alerts/{alert_id}/resolve",
    response_model=AlertResolveResponse,
    summary="签署复合预警处方归档",
    description=(
        "Human-in-the-Loop 微调沙箱的最终出口：\n\n"
        "教师对 V3 AI 处方进行人工修正后，一键签署归档。\n"
        "final_prescription: 修正后的最终处方（必填）\n"
        "resolution_note: 处置备注（可选）\n\n"
        "签署后: is_resolved=True, 冷却锁继续生效防止重复触发。"
    ),
)
async def resolve_composite_alert(
    alert_id: int,
    body: AlertResolveRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    签署处方归档 — 人工微调 → 一键签署

    RBAC: 仅 MS_ADMIN / GRADE_LEADER / CLASS_TEACHER 可签署
    多租户: alert.school_id 必须匹配 user.school_id
    重复签署: 已 resolved 的预警返回 409
    """
    # ── RBAC 角色铁闸 ──
    role = user.role
    if isinstance(role, str):
        role = UserRole(role)
    if role not in (UserRole.MS_ADMIN, UserRole.GRADE_LEADER, UserRole.CLASS_TEACHER):
        raise HTTPException(403, "仅管理角色可签署预警处方")

    # ── 查询 alert ──
    result = await db.execute(
        sa_select(ActiveCompositeAlert).where(ActiveCompositeAlert.id == alert_id)
    )
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(404, "预警不存在")

    # 多租户红线
    if alert.school_id != user.school_id:
        raise HTTPException(403, "无权操作其他学校的预警数据")

    # 重复签署防护
    if alert.is_resolved:
        raise HTTPException(409, "该预警已被签署归档，不可重复操作")

    # ── 班主任铁闸 ──
    if role == UserRole.CLASS_TEACHER:
        student_result = await db.execute(sa_select(Student).where(Student.id == alert.student_id))
        student = student_result.scalar_one_or_none()
        if not student or student.class_id != user.class_id:
            raise HTTPException(403, "无权操作其他班级学生的预警")

    # ── 写入 Human-in-the-Loop 微调数据 ──
    alert.is_resolved = True
    alert.resolved_at = get_local_now()
    alert.resolved_by = user.id
    alert.final_prescription = body.final_prescription
    alert.resolution_note = body.resolution_note

    await db.commit()
    await db.refresh(alert)

    return AlertResolveResponse(
        id=alert.id,
        is_resolved=alert.is_resolved,
        resolved_at=alert.resolved_at,
        resolved_by=alert.resolved_by,
        resolution_note=alert.resolution_note,
        final_prescription=alert.final_prescription,
    )
