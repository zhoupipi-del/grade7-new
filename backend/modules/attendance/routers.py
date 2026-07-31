"""
modules/attendance/routers.py — 考勤管理 API 路由 (V2)

注册路径: /api/v1/attendance/*
V2 扩展: 仪表盘 / 班级排行 / 日历热力图 / 全局视图 / 数据导出 / 通知

#725 重构要点:
  - Pydantic 模型已抽离至 schemas.py（标准六件套）
  - 角色→范围映射已下沉至 services.resolve_scope()
  - 权限校验统一走 services.check_access() + 领域异常
  - 业务校验（日期顺序等）已沉入 Service 层
  - HTTP 长臂管辖已斩断 — Router 只做协议翻译
"""

from datetime import date

from core.models import User, UserRole
from core.routers import get_current_user, get_db, require_role
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from .schemas import (
    BatchRecordRequest,
    LeaveApproveRequest,
    LeaveBatchApproveRequest,
    LeaveSubmitRequest,
)
from .services import AttendanceService

router = APIRouter(tags=["attendance"])


# ═══════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════


def _resolve_role(role) -> UserRole:
    """统一解析角色枚举"""
    if isinstance(role, UserRole):
        return role
    if isinstance(role, str):
        return UserRole(role)
    return role


def _apply_scope(user: User, grade_id: int | None = None, class_id: int | None = None):
    """
    应用 resolve_scope 的自动限定，配合可选的 query param 覆盖。
    返回 (grade_id, class_id, student_id)
    """
    scope = AttendanceService.resolve_scope(user)
    return (
        grade_id or scope["grade_id"],
        class_id or scope["class_id"],
        scope["student_id"],
    )


# ═══════════════════════════════════════════════════════════════
#  考勤录入
# ═══════════════════════════════════════════════════════════════


@router.post("/records/batch")
async def batch_record_attendance(
    body: BatchRecordRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _guard: User = Depends(require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER, UserRole.CLASS_TEACHER)),
):
    """
    批量录入班级考勤数据。
    仅班主任、年级组长、德育处管理员可操作。
    V2: 返回缺勤/迟到学生信息供前端通知。
    """
    AttendanceService.check_access("batch_record", current_user)

    count, notifications = await AttendanceService.batch_record(
        db=db,
        school_id=current_user.school_id,
        class_id=body.class_id,
        grade_id=body.grade_id,
        record_date=body.record_date,
        records=[r.model_dump() for r in body.records],
        created_by=current_user.id,
        creator_role=_resolve_role(current_user.role).value,
    )
    return {
        "message": "考勤录入成功",
        "count": count,
        "record_date": body.record_date.isoformat(),
        "notifications": notifications,
    }


# ═══════════════════════════════════════════════════════════════
#  考勤查询
# ═══════════════════════════════════════════════════════════════


@router.get("/records/class/{class_id}")
async def get_class_attendance(
    class_id: int,
    record_date: date | None = Query(None, description="单日查询日期 YYYY-MM-DD"),
    start_date: date | None = Query(None, description="日期范围起始 YYYY-MM-DD"),
    end_date: date | None = Query(None, description="日期范围结束 YYYY-MM-DD"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _guard: User = Depends(require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER, UserRole.CLASS_TEACHER)),
):
    """
    查询某班级考勤详情。

    支持两种模式:
    ① 单日: 仅传 record_date
    ② 历史: 传 start_date + end_date（补齐旧 Flask attendance_history 功能）
    """
    records = await AttendanceService.get_class_attendance(
        db=db,
        school_id=current_user.school_id,
        class_id=class_id,
        record_date=record_date,
        start_date=start_date,
        end_date=end_date,
    )

    # 日期范围模式 → 返回扁平列表（不标注单日）
    if start_date and end_date:
        return {
            "class_id": class_id,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "records": records,
            "count": len(records),
        }
    else:
        return {
            "class_id": class_id,
            "record_date": (record_date or date.today()).isoformat(),
            "records": records,
            "count": len(records),
        }


@router.get("/records/student/{student_id}")
async def get_student_attendance(
    student_id: int,
    days: int = Query(30, ge=1, le=365, description="查询天数"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _guard: User = Depends(require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER, UserRole.CLASS_TEACHER)),
):
    """查询某学生的考勤历史"""
    records = await AttendanceService.get_student_history(
        db=db,
        school_id=current_user.school_id,
        student_id=student_id,
        days=days,
    )
    return {"student_id": student_id, "days": days, "records": records, "count": len(records)}


# ═══════════════════════════════════════════════════════════════
#  V2 新增: 学生日历热力图
# ═══════════════════════════════════════════════════════════════


@router.get("/calendar/{student_id}")
async def get_student_calendar(
    student_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _guard: User = Depends(require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER, UserRole.CLASS_TEACHER)),
):
    """
    学生考勤日历热力图:
    - 35天日历网格 (4周+本周)
    - 90天历史记录
    - 状态颜色映射
    """
    calendar = await AttendanceService.get_student_calendar(
        db=db,
        school_id=current_user.school_id,
        student_id=student_id,
    )
    return calendar


# ═══════════════════════════════════════════════════════════════
#  考勤统计
# ═══════════════════════════════════════════════════════════════


@router.get("/stats")
async def get_attendance_stats(
    grade_id: int = Query(..., description="年级 ID"),
    start_date: date = Query(..., description="开始日期"),
    end_date: date = Query(..., description="结束日期"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _guard: User = Depends(require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER)),
):
    """年级考勤统计概览（按班级汇总）"""
    stats = await AttendanceService.get_grade_summary(
        db=db,
        school_id=current_user.school_id,
        grade_id=grade_id,
        start_date=start_date,
        end_date=end_date,
    )
    return stats


@router.get("/anomalies")
async def get_anomaly_alerts(
    days: int = Query(7, ge=1, le=60, description="监测天数（≤60）"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _guard: User = Depends(require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER)),
):
    """
    异常预警 V2: 三类规则
    ① 连续缺勤 ≥ 3 天
    ② 本周迟到 ≥ 3 次
    ③ 本月缺勤 ≥ 5 次
    """
    alerts = await AttendanceService.get_anomaly_alerts(
        db=db,
        school_id=current_user.school_id,
        days=days,
    )
    return {"alerts": alerts, "count": len(alerts), "period_days": days}


# ═══════════════════════════════════════════════════════════════
#  V2 新增: 仪表盘聚合
# ═══════════════════════════════════════════════════════════════


@router.get("/dashboard")
async def get_dashboard(
    period: str = Query(
        "week", description="today|week|month|semester（未传 start_date/end_date 时生效）"
    ),
    start_date: date | None = Query(
        None, description="自定义起始日期（与 end_date 同时提供时覆盖 period）"
    ),
    end_date: date | None = Query(None, description="自定义结束日期"),
    grade_id: int | None = Query(None, description="年级过滤"),
    class_id: int | None = Query(None, description="班级过滤"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _guard: User = Depends(require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER, UserRole.CLASS_TEACHER, UserRole.PARENT)),
):
    """
    考勤仪表盘聚合数据:
    - 概览卡片 (出勤/迟到/缺勤/请假)
    - 按日趋势 (柱状图)
    - 分布饼图

    时间范围:
    ① 自定义: 同时提供 start_date + end_date（补齐旧 Flask /daily 任意日期范围）
    ② 周期:  仅提供 period (today/week/month/semester)
    """
    scope = AttendanceService.resolve_scope(current_user)
    AttendanceService._ensure_not_student(scope)

    # 家长 → 仅看自己绑定学生
    if scope["is_parent"]:
        data = await AttendanceService.get_dashboard(
            db=db,
            school_id=current_user.school_id,
            student_id=scope["student_id"],
            period=period,
            start_date=start_date,
            end_date=end_date,
        )
        return data

    _gid, _cid, _ = _apply_scope(current_user, grade_id, class_id)
    data = await AttendanceService.get_dashboard(
        db=db,
        school_id=current_user.school_id,
        grade_id=_gid,
        class_id=_cid,
        period=period,
        start_date=start_date,
        end_date=end_date,
    )
    return data


# ═══════════════════════════════════════════════════════════════
#  V2 新增: 班级横向对比排行
# ═══════════════════════════════════════════════════════════════


@router.get("/ranking")
async def get_class_ranking(
    record_date: date | None = Query(None, description="对比日期，默认今天"),
    grade_id: int | None = Query(None, description="年级过滤"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _guard: User = Depends(require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER)),
):
    """
    班级横向对比排行: 按缺勤率降序排序
    仅德育处管理员和年级组长可查看。
    """
    AttendanceService.check_access("view_ranking", current_user)

    # 年级组长自动限定为本年级
    _gid, _, _ = _apply_scope(current_user, grade_id)

    ranking = await AttendanceService.get_class_ranking(
        db=db,
        school_id=current_user.school_id,
        grade_id=_gid,
        record_date=record_date,
    )
    return {
        "ranking": ranking,
        "record_date": (record_date or date.today()).isoformat(),
        "count": len(ranking),
    }


# ═══════════════════════════════════════════════════════════════
#  V2 新增: 德育处全局视图
# ═══════════════════════════════════════════════════════════════


@router.get("/overview")
async def get_overview(
    start_date: date = Query(..., description="开始日期"),
    end_date: date = Query(..., description="结束日期"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _guard: User = Depends(require_role(UserRole.MS_ADMIN)),
):
    """
    德育处全局考勤视图: 所有年级/班级汇总。
    仅 ms_admin 可查看。
    """
    AttendanceService.check_access("view_overview", current_user)

    overview = await AttendanceService.get_overview(
        db=db,
        school_id=current_user.school_id,
        start_date=start_date,
        end_date=end_date,
    )
    return overview


# ═══════════════════════════════════════════════════════════════
#  V2 新增: 数据导出
# ═══════════════════════════════════════════════════════════════


@router.get("/export")
async def export_attendance(
    grade_id: int = Query(..., description="年级 ID"),
    start_date: date = Query(..., description="开始日期"),
    end_date: date = Query(..., description="结束日期"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _guard: User = Depends(require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER)),
):
    """
    导出考勤数据: 返回扁平化记录数组，前端可转为 Excel/CSV。
    仅 ms_admin / grade_leader 可用。
    """
    AttendanceService.check_access("export_data", current_user)

    rows = await AttendanceService.export_attendance(
        db=db,
        school_id=current_user.school_id,
        grade_id=grade_id,
        start_date=start_date,
        end_date=end_date,
    )
    return {
        "grade_id": grade_id,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "rows": rows,
        "count": len(rows),
    }


# ═══════════════════════════════════════════════════════════════
#  请假管理
# ═══════════════════════════════════════════════════════════════


@router.post("/leaves", status_code=201)
async def submit_leave_request(
    body: LeaveSubmitRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _guard: User = Depends(require_role(UserRole.PARENT, UserRole.CLASS_TEACHER, UserRole.MS_ADMIN, UserRole.GRADE_LEADER)),
):
    """家长提交请假申请"""
    AttendanceService.check_access("submit_leave", current_user)

    leave = await AttendanceService.submit_leave(
        db=db,
        school_id=current_user.school_id,
        student_id=body.student_id,
        class_id=body.class_id,
        grade_id=body.grade_id,
        start_date=body.start_date,
        end_date=body.end_date,
        reason=body.reason,
        submitted_by=current_user.id,
    )
    return {
        "message": "请假申请已提交",
        "leave_id": leave.id,
        "status": leave.status,
    }


@router.post("/leaves/approve")
async def approve_leave_request(
    body: LeaveApproveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _guard: User = Depends(require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER, UserRole.CLASS_TEACHER)),
):
    """班主任/年级组长审批请假"""
    AttendanceService.check_access("approve_leave", current_user)

    leave = await AttendanceService.approve_leave(
        db=db,
        leave_id=body.leave_id,
        approver_id=current_user.id,
        approver_role=_resolve_role(current_user.role).value,
    )
    return {
        "message": "审批完成",
        "leave_id": leave.id,
        "status": leave.status,
        "corrected_count": getattr(leave, "_corrected_count", 0),
    }


# ═══════════════════════════════════════════════════════════════
#  请假列表 (GAP-3 补齐 — 旧 Flask class_/grade/parent leaves 路由)
# ═══════════════════════════════════════════════════════════════


@router.get("/leaves")
async def list_leaves(
    status: str | None = Query(None, description="pending|class_approved|grade_approved|rejected"),
    grade_id: int | None = Query(None, description="年级过滤"),
    class_id: int | None = Query(None, description="班级过滤"),
    student_id: int | None = Query(None, description="学生过滤"),
    limit: int = Query(50, ge=1, le=200, description="每页条数"),
    offset: int = Query(0, ge=0, description="偏移量"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _guard: User = Depends(require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER, UserRole.CLASS_TEACHER, UserRole.PARENT)),
):
    """
    请假列表查询，支持角色自动范围限定:

    - parent:      仅看自己绑定学生
    - class_teacher: 仅看本班
    - grade_leader:  仅看本年级
    - ms_admin:    全校

    补齐旧 Flask 三个蓝图的 leave list 路由:
      class_.py /leaves, grade.py /leaves, parent_portal.py /leaves
    """
    AttendanceService.check_access("list_leaves", current_user)

    # 角色自动范围限定（query param 可覆盖）
    _gid, _cid, _sid = _apply_scope(current_user, grade_id, class_id)

    data = await AttendanceService.list_leaves(
        db=db,
        school_id=current_user.school_id,
        grade_id=_gid,
        class_id=_cid,
        student_id=student_id or _sid,
        status=status,
        limit=limit,
        offset=offset,
    )
    return data


# ═══════════════════════════════════════════════════════════════
#  批量审批 (GAP-4 补齐 — 旧 Flask grade.py /leaves/batch-approve)
# ═══════════════════════════════════════════════════════════════


@router.post("/leaves/batch-approve")
async def batch_approve_leaves(
    body: LeaveBatchApproveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _guard: User = Depends(require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER)),
):
    """
    批量审批/拒绝请假申请（年级组长专用）。

    补齐旧 Flask grade.py 的 batch_approve_leaves() 功能。
    - approve → 通过 + 自动创建考勤记录
    - reject  → 拒绝
    """
    AttendanceService.check_access("batch_process_leaves", current_user)

    # ms_admin 以年级组长身份批量审批
    role_value = _resolve_role(current_user.role).value
    if role_value == "ms_admin":
        role_value = "grade_leader"

    results = await AttendanceService.batch_process_leaves(
        db=db,
        leave_ids=body.leave_ids,
        action=body.action,
        approver_id=current_user.id,
        approver_role=role_value,
    )

    success_count = sum(1 for r in results if r.get("success"))
    fail_count = len(results) - success_count

    return {
        "message": f"批量处理完成: {success_count} 成功, {fail_count} 失败",
        "action": body.action,
        "results": results,
        "total": len(results),
        "success_count": success_count,
        "fail_count": fail_count,
    }


# ═══════════════════════════════════════════════════════════════
#  班级考勤历史聚合矩阵 (GAP-1 & GAP-2 闭合)
#  CASE WHEN 单次扫描按天归总, 供前端 ECharts 折线大盘消费
# ═══════════════════════════════════════════════════════════════


@router.get("/history/{class_id}")
async def get_class_attendance_history(
    class_id: int,
    start_date: date = Query(..., description="起始日期 YYYY-MM-DD"),
    end_date: date = Query(..., description="结束日期 YYYY-MM-DD"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _guard: User = Depends(require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER, UserRole.CLASS_TEACHER)),
):
    """
    班级考勤历史聚合 — 按天多态状态矩阵

    返回每天的出勤/缺勤/迟到早退/请假人数汇总,
    一次 SQL CASE WHEN 扫描完成, 支撑前端折线趋势图。

    响应示例:
    [
      {"date": "2026-07-01", "total_students": 45, "present_count": 42,
       "absent_critical_count": 1, "warning_count": 1, "leave_count": 1},
      ...
    ]
    """
    history = await AttendanceService.get_class_attendance_history(
        db=db,
        school_id=current_user.school_id,
        class_id=class_id,
        start_date=start_date,
        end_date=end_date,
    )

    return {
        "class_id": class_id,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "days": len(history),
        "history": history,
    }
