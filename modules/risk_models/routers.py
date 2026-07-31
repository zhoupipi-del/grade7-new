"""
modules/risk_models/routers.py — 风险预警雷达 API 路由

端点:
  - POST /api/v1/risk_models/calculate — 计算学生 RDI
  - GET  /api/v1/risk_models/dashboard — 风险看板
  - GET  /api/v1/risk_models/monitor-panel — 监控面板 (黄/红预警)
  - GET  /api/v1/risk_models/warnings — 预警列表
  - POST /api/v1/risk_models/warnings/{id}/handle — 处置预警
  - GET  /api/v1/risk_models/baselines — 基线查询
  - POST /api/v1/risk_models/baselines/warmup — 冷启动批量预热 ⬅ NEW
  - POST /api/v1/risk_models/explain — 判罚透明化解释 (三段式)
"""

import logging

from core.models import Class, Student, User, UserRole, get_local_now
from core.routers import get_current_user, get_db
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .explainer import ExplainerService
from .models import RiskWarning
from .schemas import (
    AsyncCalculateRequest,
    AsyncScanClassRequest,
    AsyncScanSchoolRequest,
    MonitorPanelOut,
    PenaltyExplanationRequest,
    PenaltyExplanationResponse,
    RDICalculateRequest,
    RDICalculateResponse,
    RiskDashboardOut,
    RiskWarningOut,
    TaskDispatchResponse,
)
from .services import RiskDeviationIndexCalculator, RiskMonitorService, RiskWarningService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["风险预警雷达"])

# ── RDI 计算 ──


@router.post("/calculate", response_model=RDICalculateResponse)
async def calculate_rdi(
    request: RDICalculateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    计算学生 RDI 风险偏离指数

    权限: class_teacher / grade_leader / ms_admin
    用途: 实时计算并返回 RDI，前端决定是否生成预警
    """
    # 权限检查
    if current_user.role not in [UserRole.CLASS_TEACHER, UserRole.GRADE_LEADER, UserRole.MS_ADMIN]:
        raise HTTPException(status_code=403, detail="权限不足")

    calculator = RiskDeviationIndexCalculator(db, current_user.school_id)
    result = await calculator.calculate_rdi(
        student_id=request.student_id,
        window_short=request.window_short,
        window_medium=request.window_medium,
        window_long=request.window_long,
        include_trend=request.include_trend,
        suppress_low_rdi=request.suppress_low_rdi,
    )

    return RDICalculateResponse(**result)


# ── 风险看板 ──


@router.get("/dashboard", response_model=RiskDashboardOut)
async def get_risk_dashboard(
    class_id: int | None = Query(None, description="班级ID (班主任自动限制本班)"),
    grade_id: int | None = Query(None, description="年级ID (级组长自动限制本年级)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    获取风险看板数据 (v3.2 — 真实多租户聚合)

    权限:
      - class_teacher: 自动限制本班
      - grade_leader: 自动限制本年级
      - ms_admin: 看全校
    """
    # 权限守卫
    if current_user.role not in [UserRole.CLASS_TEACHER, UserRole.GRADE_LEADER, UserRole.MS_ADMIN]:
        raise HTTPException(status_code=403, detail="权限不足")

    # 权限联动: 角色自动收敛管辖范围 (对接第二步动态身份解析)
    if current_user.role == UserRole.CLASS_TEACHER:
        if not class_id:
            class_id = getattr(current_user, "class_id", None)
        if not class_id:
            raise HTTPException(status_code=400, detail="班主任缺少班级信息")
    elif current_user.role == UserRole.GRADE_LEADER:
        if not grade_id:
            grade_id = getattr(current_user, "grade_id", None)
    # ms_admin 不限制

    dashboard = await RiskWarningService.get_dashboard(
        db, current_user.school_id, class_id, grade_id
    )

    return RiskDashboardOut(**dashboard)


# ── 四维风险看板聚合 (dashboard-metrics) ──


def _band_of(rdi_score: float, psych_veto: bool) -> str:
    """将学生风险状态映射到 σ 区间 (veto/watch/warning/normal)"""
    if psych_veto or rdi_score >= 3.0:
        return "veto"
    if rdi_score >= 2.0:
        return "warning"
    if rdi_score >= 1.0:
        return "watch"
    return "normal"


async def _aggregate_dashboard_metrics(
    db: AsyncSession,
    school_id: int,
    class_id: int | None,
    grade_id: int | None,
    limit_events: int,
) -> dict:
    """
    聚合四维风险看板 (dashboard-metrics) 数据。

    数据源: risk_warnings(active) + Student + Class。
    每个学生在 scope 内只取最新一条活跃预警, 避免重复计数。
    """
    stmt = (
        select(
            RiskWarning,
            Student.name.label("student_name"),
            Student.student_no,
            Class.name.label("class_name"),
        )
        .join(Student, RiskWarning.student_id == Student.id)
        .outerjoin(Class, RiskWarning.class_id == Class.id)
        .where(RiskWarning.school_id == school_id)
        .where(RiskWarning.status == "active")
    )
    if class_id is not None:
        stmt = stmt.where(RiskWarning.class_id == class_id)
    if grade_id is not None:
        stmt = stmt.where(RiskWarning.grade_id == grade_id)
    stmt = stmt.order_by(RiskWarning.warned_at.desc())
    rows = (await db.execute(stmt)).all()

    # 每学生取最新一条预警 (rows 已按 warned_at desc)
    students: dict[int, dict] = {}
    for rw, s_name, s_no, c_name in rows:
        if rw.student_id in students:
            continue
        students[rw.student_id] = {
            "student_id": rw.student_id,
            "student_name": s_name or f"学生{rw.student_id}",
            "student_no": s_no,
            "class_id": rw.class_id,
            "class_name": c_name,
            "rdi_score": float(rw.rdi_score),
            "risk_level": rw.risk_level,
            "behavior_deviation": float(rw.behavior_deviation or 0.0),
            "attendance_deviation": float(rw.attendance_deviation or 0.0),
            "score_deviation": float(rw.score_deviation or 0.0),
            "psych_deviation": float(getattr(rw, "psych_deviation", 0.0) or 0.0),
            "psych_veto_triggered": bool(getattr(rw, "psych_veto_triggered", False) or False),
            "veto_dimension": getattr(rw, "veto_dimension", None),
            "is_escalating": bool(rw.is_escalating or False),
            "trigger_event_type": rw.trigger_event_type,
            "warned_at": rw.warned_at,
            "top_dimension": RiskMonitorService._determine_top_dimension(
                rw.behavior_deviation or 0.0,
                rw.attendance_deviation or 0.0,
                rw.score_deviation or 0.0,
                getattr(rw, "psych_deviation", 0.0) or 0.0,
            ),
        }

    # σ 漏斗 + 风险等级分布
    sigma_funnel = {"normal": 0, "watch": 0, "warning": 0, "veto": 0}
    by_risk_level = {"normal": 0, "attention": 0, "intervention": 0}
    for s in students.values():
        sigma_funnel[_band_of(s["rdi_score"], s["psych_veto_triggered"])] += 1
        if s["risk_level"] in by_risk_level:
            by_risk_level[s["risk_level"]] += 1

    # 雷达 avg/max (四维度偏离)
    dims = ["behavior", "attendance", "score", "psych"]
    dev_keys = ["behavior_deviation", "attendance_deviation", "score_deviation", "psych_deviation"]
    sums = [0.0] * 4
    mx = [0.0] * 4
    n = len(students)
    for s in students.values():
        for i, k in enumerate(dev_keys):
            v = abs(s[k])
            sums[i] += v
            if v > mx[i]:
                mx[i] = v
    avg = [round(sums[i] / n, 2) if n else 0.0 for i in range(4)]
    mx = [round(mx[i], 2) for i in range(4)]

    # top 风险学生 (按 rdi desc, 取前 10)
    top = sorted(students.values(), key=lambda x: x["rdi_score"], reverse=True)[:10]
    top_risk_students = [
        {
            "student_id": s["student_id"],
            "student_name": s["student_name"],
            "student_no": s["student_no"],
            "class_name": s["class_name"] or "",
            "rdi_score": round(s["rdi_score"], 2),
            "risk_level": s["risk_level"],
            "behavior_deviation": round(s["behavior_deviation"], 2),
            "attendance_deviation": round(s["attendance_deviation"], 2),
            "score_deviation": round(s["score_deviation"], 2),
            "psych_deviation": round(s["psych_deviation"], 2),
            "top_dimension": s["top_dimension"],
            "psych_veto_triggered": s["psych_veto_triggered"],
            "veto_dimension": s["veto_dimension"],
            "is_escalating": s["is_escalating"],
        }
        for s in top
    ]

    # 事件流 (每学生最新预警, 按 warned_at desc, 限制条数)
    event_stream = []
    for s in sorted(students.values(), key=lambda x: x["warned_at"] or "", reverse=True)[
        :limit_events
    ]:
        if s["psych_veto_triggered"]:
            risk_color = "black"
            rec_action = "psych_intervention"
        elif s["rdi_score"] >= 2.0:
            risk_color = "red"
            rec_action = "intervention_plan"
        elif s["rdi_score"] >= 1.5:
            risk_color = "orange"
            rec_action = "monitor"
        elif s["rdi_score"] >= 1.0:
            risk_color = "yellow"
            rec_action = "monitor"
        else:
            risk_color = "green"
            rec_action = "monitor"
        if s["is_escalating"] and risk_color not in ("black", "red"):
            rec_action = "heart_to_heart"
        event_stream.append(
            {
                "student_id": s["student_id"],
                "student_name": s["student_name"],
                "student_no": s["student_no"],
                "class_name": s["class_name"] or "",
                "rdi_score": round(s["rdi_score"], 2),
                "risk_level": s["risk_level"],
                "risk_color": risk_color,
                "psych_deviation": round(s["psych_deviation"], 2),
                "psych_veto_triggered": s["psych_veto_triggered"],
                "veto_dimension": s["veto_dimension"],
                "trigger_factor": s["trigger_event_type"] or "manual",
                "warned_at": s["warned_at"].isoformat() if s["warned_at"] else None,
                "recommended_action": rec_action,
            }
        )

    # 班级热力图
    class_heatmap = await _aggregate_class_heatmap(db, school_id, class_id, grade_id, students)

    # 在读学生总数 (按范围)
    total_q = select(func.count(Student.id)).where(Student.school_id == school_id)
    if class_id is not None:
        total_q = total_q.where(Student.class_id == class_id)
    if grade_id is not None:
        total_q = total_q.where(Student.grade_id == grade_id)
    total_students = (await db.execute(total_q)).scalar() or 0

    return {
        "radar": {"dimensions": dims, "avg": avg, "max": mx},
        "sigma_funnel": sigma_funnel,
        "event_stream": event_stream,
        "top_risk_students": top_risk_students,
        "class_heatmap": class_heatmap,
        "summary": {
            "total_students": total_students,
            "at_risk_count": len(students),
            "by_risk_level": by_risk_level,
        },
        "generated_at": get_local_now().isoformat(),
    }


async def _aggregate_class_heatmap(
    db: AsyncSession,
    school_id: int,
    class_id: int | None,
    grade_id: int | None,
    students: dict[int, dict],
) -> list[dict]:
    """各班学生总数 + σ 区间分布 (normal = 总数 - 非 normal 预警学生数)"""
    total_q = (
        select(Class.id, Class.name, func.count(Student.id).label("cnt"))
        .join(Student, Student.class_id == Class.id)
        .where(Student.school_id == school_id)
    )
    if class_id is not None:
        total_q = total_q.where(Student.class_id == class_id)
    if grade_id is not None:
        total_q = total_q.where(Student.grade_id == grade_id)
    total_q = total_q.group_by(Class.id, Class.name)
    class_totals = (await db.execute(total_q)).all()

    band_by_class: dict[int, dict] = {}
    for s in students.values():
        cid = s["class_id"]
        if cid not in band_by_class:
            band_by_class[cid] = {"watch": 0, "warning": 0, "veto": 0}
        band = _band_of(s["rdi_score"], s["psych_veto_triggered"])
        if band in ("watch", "warning", "veto"):
            band_by_class[cid][band] += 1

    heatmap = []
    for cid, cname, cnt in class_totals:
        bands = band_by_class.get(cid, {"watch": 0, "warning": 0, "veto": 0})
        non_normal = bands["watch"] + bands["warning"] + bands["veto"]
        heatmap.append(
            {
                "class_id": cid,
                "class_name": cname or f"班级{cid}",
                "total": cnt,
                "normal": max(cnt - non_normal, 0),
                "watch": bands["watch"],
                "warning": bands["warning"],
                "veto": bands["veto"],
            }
        )
    heatmap.sort(key=lambda x: x["class_id"])
    return heatmap


@router.get("/dashboard-metrics")
async def get_dashboard_metrics(
    class_id: int | None = Query(None, description="班级ID (班主任自动限制本班)"),
    grade_id: int | None = Query(None, description="年级ID (级组长自动限制本年级)"),
    limit_events: int = Query(20, description="事件流返回条数"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    获取四维风险看板聚合数据 (dashboard-metrics)

    供 RDI 风险看板页 (RdiDashboard.vue) 使用。聚合 risk_warnings(active) + Student + Class。

    权限:
      - class_teacher: 自动限制本班
      - grade_leader: 自动限制本年级
      - ms_admin: 看全校
    """
    if current_user.role not in [UserRole.CLASS_TEACHER, UserRole.GRADE_LEADER, UserRole.MS_ADMIN]:
        raise HTTPException(status_code=403, detail="权限不足")

    if current_user.role == UserRole.CLASS_TEACHER:
        if not class_id:
            class_id = getattr(current_user, "class_id", None)
        if not class_id:
            raise HTTPException(status_code=400, detail="班主任缺少班级信息")
    elif current_user.role == UserRole.GRADE_LEADER:
        if not grade_id:
            grade_id = getattr(current_user, "grade_id", None)

    metrics = await _aggregate_dashboard_metrics(
        db, current_user.school_id, class_id, grade_id, limit_events
    )
    return metrics


# ── 风险监控面板 ──


@router.get("/monitor-panel", response_model=MonitorPanelOut)
async def get_monitor_panel(
    class_id: int | None = Query(None, description="班级ID (班主任只看本班)"),
    grade_id: int | None = Query(None, description="年级ID (级组长看全年级)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    获取风险监控面板 — 仅展示黄/红预警学生 (RDI > 1.0)

    权限:
      - class_teacher: 自动限制本班 (class_id 从 user 获取)
      - grade_leader: 看全年级
      - ms_admin: 看全校

    返回:
      - 黄灯 (attention): RDI 1.0-2.0
      - 红灯 (intervention): RDI >= 2.0
      - 按 RDI 降序排列
      - 班级分布统计
    """
    # 权限自动范围限制
    if current_user.role == UserRole.CLASS_TEACHER:
        if not class_id:
            class_id = getattr(current_user, "class_id", None)
        if not class_id:
            raise HTTPException(status_code=400, detail="班主任缺少班级信息")
    elif current_user.role == UserRole.GRADE_LEADER:
        if not grade_id:
            grade_id = getattr(current_user, "grade_id", None)
    # ms_admin 不限制

    panel = await RiskMonitorService.get_monitor_panel(
        db, current_user.school_id, class_id=class_id, grade_id=grade_id
    )

    return MonitorPanelOut(**panel)


# ── 预警列表 ──


@router.get("/warnings", response_model=list[RiskWarningOut])
async def list_warnings(
    status: str | None = Query(None, description="active/handled/false_positive/expired"),
    risk_level: str | None = Query(None, description="normal/attention/intervention"),
    days: int = Query(7, description="最近N天的预警"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    查询风险预警列表

    默认返回最近7天的活跃预警
    """
    # 默认查活跃预警; 班主任/级组长按归属范围自动收缩
    if status is None:
        status = "active"
    warnings = await RiskWarningService.list_warnings(
        db, current_user.school_id, current_user, status, risk_level, days
    )
    return [RiskWarningOut(**w) for w in warnings]


# ── 处置预警 ──


@router.post("/warnings/{warning_id}/handle")
async def handle_warning(
    warning_id: int,
    action: str = Query(..., description="heart_to_heart/talk_to_parent/intervention_plan/dismiss"),
    note: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    处置风险预警

    权限: class_teacher / grade_leader
    动作:
      - heart_to_heart: 谈心 (🟡关注)
      - talk_to_parent: 家访/电话 (🟡关注)
      - intervention_plan: 行为矫正方案 (🔴干预)
      - dismiss: 误报 (标记为 false_positive)
    """
    if current_user.role not in [UserRole.CLASS_TEACHER, UserRole.GRADE_LEADER]:
        raise HTTPException(status_code=403, detail="权限不足")

    try:
        result = await RiskWarningService.handle_warning(
            db, current_user.school_id, current_user, warning_id, action, note
        )
        await db.commit()
        return result
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        await db.rollback()
        raise HTTPException(status_code=403, detail=str(e))


# ── 基线查询 ──


@router.get("/baselines")
async def get_baselines(
    student_id: int,
    baseline_type: str = Query(..., description="behavior/attendance/score"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    查询学生行为基线 (调试用)

    返回: 均值、标准差、样本量、EWMA值
    """
    baseline = await RiskWarningService.get_baseline(
        db, current_user.school_id, student_id, baseline_type
    )
    return baseline


@router.post("/baselines/warmup")
async def warmup_baselines(
    window_days: int = Query(30, description="滑动窗口天数 (默认30天)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    冷启动批量预热 — 为全校学生计算并存储风险基线

    权限: ms_admin / grade_leader

    触发场景:
      1. 系统首次上线，risk_baselines 表为空
      2. 新学期开始，需要重新计算基线
      3. 大量新学生入学后补充基线

    注意: _get_or_create_baseline() 已内置冷启动自动检测，
          首次 RDI 计算时会自动触发预热。此端点供管理员手动触发。
    """
    if current_user.role not in [UserRole.MS_ADMIN, UserRole.GRADE_LEADER]:
        raise HTTPException(status_code=403, detail="权限不足：仅德育处或年级组长可操作")

    try:
        result = await RiskDeviationIndexCalculator.warmup_all_baselines(
            db, current_user.school_id, window_days
        )
        await db.commit()
        return {
            "status": "success",
            "message": f"基线预热完成: 计算 {result['computed']} 人, 跳过 {result['skipped']} 人, 错误 {result['errors']} 人",
            "details": result,
        }
    except Exception as e:
        await db.rollback()
        logger.error(f"基线预热失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"基线预热失败: {e}")


# ── 判罚透明化解释 ──


@router.post("/explain", response_model=PenaltyExplanationResponse)
async def explain_penalty(
    request: PenaltyExplanationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    生成判罚透明化解释 — 三段式表达 (Fact → Rule → Growth)

    权限: class_teacher / grade_leader / ms_admin

    流程:
      1. 可选 RDI 自动计算 (request.include_rdi=True 且无预存 rdi_score)
      2. 调用 ExplainerService.explain_event() 生成三段式解释
      3. 返回包含事实陈述、校规映射、建设性引导的完整解释

    示例请求:
      POST /api/v1/risk-models/explain
      {
        "student_id": 123,
        "event_type": "fighting",
        "event_id": null,
        "include_rdi": true
      }
    """
    # 权限检查
    if current_user.role not in [UserRole.CLASS_TEACHER, UserRole.GRADE_LEADER, UserRole.MS_ADMIN]:
        raise HTTPException(status_code=403, detail="权限不足")

    # ── Step 1: 可选的 RDI 计算 ──
    rdi_result = None
    if request.include_rdi and request.rdi_score is None:
        # 需要自动计算 RDI
        calculator = RiskDeviationIndexCalculator(db, current_user.school_id)
        rdi_result = await calculator.calculate_rdi(
            student_id=request.student_id,
        )
    elif request.rdi_score is not None:
        # 使用请求中预存的 RDI 值 (避免重复计算)
        rdi_result = {
            "rdi_score": request.rdi_score,
            "risk_level": request.risk_level or "normal",
            "is_escalating": request.is_escalating or False,
            "warning_suppressed": request.warning_suppressed or False,
        }

    # ── Step 2: 生成三段式解释 ──
    try:
        result = await ExplainerService.explain_event(
            db=db,
            school_id=current_user.school_id,
            student_id=request.student_id,
            event_type=request.event_type,
            event_id=request.event_id,
            rdi_result=rdi_result,
        )
        return PenaltyExplanationResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(
            f"Failed to generate penalty explanation: "
            f"student_id={request.student_id}, event_type={request.event_type} | {e}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="判罚解释生成失败，请联系管理员")


# ═══════════════════════════════════════════════════════════════
# 异步投递端点 (Phase 2B — fire-and-forget)
# ═══════════════════════════════════════════════════════════════


@router.post("/calculate/async", response_model=TaskDispatchResponse)
async def calculate_rdi_async(
    request: AsyncCalculateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    异步计算学生 RDI 并生成预警 (fire-and-forget)

    权限: class_teacher / grade_leader / ms_admin
    用途: 将 RDI 计算投递到 Celery maintenance 队列，立即返回 task_id。

    适用场景:
      - 批量学生导入后触发单生 RDI 重算
      - 处分事件后实时触发风险扫描
      - 前端轮询 task_id 获取结果 (Celery result_backend)

    与同步 /calculate 的区别:
      - 同步: 阻塞等待 300-800ms → 返回完整 RDI JSON
      - 异步: 立即返回 task_id → Celery 后台算完存库 → 前端轮询
    """
    if current_user.role not in [UserRole.CLASS_TEACHER, UserRole.GRADE_LEADER, UserRole.MS_ADMIN]:
        raise HTTPException(status_code=403, detail="权限不足")

    # 同步计算 RDI + 可选存库 (单生计算 300-800ms, 无需 Celery)
    try:
        from .services import RiskDeviationIndexCalculator, RiskWarningService

        calculator = RiskDeviationIndexCalculator(db, current_user.school_id)
        rdi_result = await calculator.calculate_rdi(
            student_id=request.student_id,
            window_short=request.window_short,
            window_medium=request.window_medium,
            window_long=request.window_long,
            include_trend=request.include_trend,
            suppress_low_rdi=True,
        )

        if request.generate_warning and not rdi_result["warning_suppressed"]:
            await RiskWarningService.create_warning(
                db,
                current_user.school_id,
                rdi_result,
                trigger_event_type="async_manual",
            )
            await db.commit()

        task_id = (
            str(rdi_result.get("calculated_at", "").timestamp())
            if rdi_result.get("calculated_at")
            else "unknown"
        )

        return TaskDispatchResponse(
            status="completed",
            task_id=task_id,
            message=(
                f"学生 {request.student_id} RDI={rdi_result['rdi_score']:.2f} "
                f"({rdi_result['risk_level']})"
            ),
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"异步 RDI 计算失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"RDI 计算失败: {e}")


@router.post("/scan/class/{class_id}", response_model=TaskDispatchResponse)
async def trigger_class_scan(
    class_id: int,
    request: AsyncScanClassRequest = AsyncScanClassRequest(),
    current_user: User = Depends(get_current_user),
):
    """
    触发班级级 RDI 风险扫描 (异步 — maintenance 队列)

    权限: ms_admin / grade_leader

    流程:
      1. 权限校验 (级组长只能扫描本年级班级)
      2. 投递 rdi_scan_class.delay() 到 maintenance 队列
      3. 立即返回 task_id
      4. Celery worker 后台遍历班级学生 → 计算 RDI → 生成预警

    task_id 可用于:
      - 监控面板轮询进度
      - result_backend 获取执行结果 (Redis DB 3)
    """
    if current_user.role not in [UserRole.MS_ADMIN, UserRole.GRADE_LEADER]:
        raise HTTPException(status_code=403, detail="权限不足：仅德育处或年级组长可操作")

    from .tasks import rdi_scan_class

    async_task = rdi_scan_class.delay(
        school_id=current_user.school_id,
        class_id=class_id,
        semester=request.semester,
    )

    return TaskDispatchResponse(
        status="dispatched",
        task_id=async_task.id,
        message=f"班级 {class_id} RDI 扫描已投递到 maintenance 队列",
    )


@router.post("/scan/school", response_model=TaskDispatchResponse)
async def trigger_school_scan(
    request: AsyncScanSchoolRequest = AsyncScanSchoolRequest(),
    current_user: User = Depends(get_current_user),
):
    """
    触发全校 RDI 风险扫描 (异步 — maintenance 队列)

    权限: ms_admin

    流程:
      1. 权限校验 (仅 ms_admin)
      2. 投递 rdi_scan_school.delay() 到 maintenance 队列
      3. 立即返回 task_id
      4. Celery worker 查询全校班级 → 逐班 dispatch rdi_scan_class
      5. 每个班级独立扫描，互不阻塞

    注意: 全校 393 学生预计总耗时 8-15 分钟 (取决于数据量)
    """
    if current_user.role != UserRole.MS_ADMIN:
        raise HTTPException(status_code=403, detail="权限不足：仅德育处管理员可操作")

    from .tasks import rdi_scan_school

    async_task = rdi_scan_school.delay(
        school_id=current_user.school_id,
        semester=request.semester,
    )

    return TaskDispatchResponse(
        status="dispatched",
        task_id=async_task.id,
        message=f"全校 RDI 扫描已投递到 maintenance 队列 (task_id={async_task.id})",
    )
