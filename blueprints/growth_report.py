"""
全校学生综合成长周报/月报
整合6个维度：学业表现、行为规范、出勤状态、心理健康、综合素质、活动参与
"""

import json as json_mod
from datetime import timedelta, date
from collections import defaultdict

from flask import Blueprint, render_template, jsonify, request, session, current_app, flash, redirect, url_for
from decorators import login_required, require_role
from models import (
    db, Student, Score, Exam, 
    DisciplineRecord, Attendance, 
    PsychSurvey, QualityScore,
    Activity, ActivityRegistration,
    Class, Grade, LeaveRequest
)
from sqlalchemy import text, func

growth_bp = Blueprint("growth", __name__, template_folder="../templates")

# ════════════════════════════════════════════════════════════
# 工具函数：计算时间范围
# ════════════════════════════════════════════════════════════

def _get_period_range(period_type="week"):
    """返回本周/本月的起止日期"""
    today = date.today()
    if period_type == "week":
        # 本周一 到 本周日
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=6)
    elif period_type == "month":
        # 本月1日 到 本月最后一天
        start = today.replace(day=1)
        next_month = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
        end = next_month - timedelta(days=1)
    else:
        # 本学期
        start = today.replace(month=9, day=1) if today.month >= 9 else today.replace(month=2, day=1)
        end = today
    return start, end


def _calc_grade_trend(sid, exam_id):
    """计算成绩趋势：上升/下降/稳定"""
    rows = db.session.execute(
        text("""
            SELECT exam_id, SUM(score) as total
            FROM scores WHERE student_id = :sid
            GROUP BY exam_id ORDER BY exam_id DESC LIMIT 3
        """),
        {"sid": sid}
    ).fetchall()
    
    if len(rows) < 2:
        return "stable", 0
    
    latest = float(rows[0][1] or 0)
    prev = float(rows[1][1] or 0)
    diff = latest - prev
    
    if diff > 3:
        return "rising", round(diff, 1)
    elif diff < -3:
        return "declining", round(diff, 1)
    else:
        return "stable", round(diff, 1)


def _get_discipline_stats(sid, start_date, end_date):
    """获取违纪统计"""
    records = DisciplineRecord.query.filter(
        DisciplineRecord.student_id == sid,
        DisciplineRecord.created_at >= start_date,
        DisciplineRecord.created_at <= end_date + timedelta(days=1),
    ).all()
    
    stats = {"total": len(records), "major": 0, "serious": 0, "minor": 0, "warning": 0, "records": []}
    for r in records:
        stats[r.type] = stats.get(r.type, 0) + 1
        stats["records"].append({
            "date": r.created_at.strftime("%Y-%m-%d"),
            "type": r.type,
            "reason": r.reason,
            "status": r.status,
        })
    
    return stats


def _get_attendance_stats(sid, start_date, end_date):
    """获取考勤统计"""
    records = Attendance.query.filter(
        Attendance.student_id == sid,
        Attendance.record_date >= start_date,
        Attendance.record_date <= end_date,
    ).all()
    
    stats = {"total": len(records), "present": 0, "absent": 0, "late": 0, "leave": 0}
    for r in records:
        stats[r.status] = stats.get(r.status, 0) + 1
    
    return stats


def _get_psych_stats(sid):
    """获取心理健康统计"""
    survey = PsychSurvey.query.filter_by(
        student_id=sid,
        survey_type="MSSMHS-55",
        is_valid=True
    ).order_by(PsychSurvey.completed_at.desc()).first()
    
    if not survey:
        return {"has_data": False, "risk_level": "unknown", "total_score": 0, "dimensions": {}}
    
    risk_level = "low"
    if survey.total_score >= 160:
        risk_level = "high"
    elif survey.total_score >= 120:
        risk_level = "medium"
    
    dimensions = {}
    if survey.dimensions_json:
        try:
            dimensions = json_mod.loads(survey.dimensions_json)
        except Exception:
            pass
    
    return {
        "has_data": True,
        "risk_level": risk_level,
        "total_score": survey.total_score,
        "dimensions": dimensions,
        "completed_at": survey.completed_at.strftime("%Y-%m-%d"),
    }


def _get_quality_stats(sid, start_date, end_date):
    """获取综合素质评价统计"""
    from models import QualityScore
    records = QualityScore.query.filter(
        QualityScore.student_id == sid,
        QualityScore.created_at >= start_date,
        QualityScore.created_at <= end_date + timedelta(days=1),
    ).all()
    
    stats = {}
    for r in records:
        if r.dimension not in stats:
            stats[r.dimension] = {"total": 0, "count": 0, "records": []}
        stats[r.dimension]["total"] += r.score
        stats[r.dimension]["count"] += 1
        stats[r.dimension]["records"].append({
            "score": r.score,
            "comment": r.comment,
            "date": r.created_at.strftime("%Y-%m-%d"),
        })
    
    # 计算平均分
    for dim in stats:
        stats[dim]["average"] = round(stats[dim]["total"] / stats[dim]["count"], 1) if stats[dim]["count"] > 0 else 0
    
    return stats


def _get_activity_stats(sid, start_date, end_date):
    """获取活动参与统计"""
    participations = ActivityRegistration.query.filter(
        ActivityRegistration.student_id == sid,
        ActivityRegistration.registered_at >= start_date,
        ActivityRegistration.registered_at <= end_date + timedelta(days=1),
    ).all()

    # 批量预加载活动（消除 Activity.query.get N+1）
    act_ids = list({p.activity_id for p in participations})
    act_map = {a.id: a for a in Activity.query.filter(Activity.id.in_(act_ids)).all()} if act_ids else {}

    stats = {"total": len(participations), "activities": []}
    for p in participations:
        activity = act_map.get(p.activity_id)
        if activity:
            stats["activities"].append({
                "name": activity.name,
                "type": activity.type,
                "date": activity.start_time.strftime("%Y-%m-%d") if activity.start_time else "",
                "status": p.status,
            })

    return stats


def _calculate_overall_score(report_data):
    """
    计算综合成长评分（0-100分）
    权重：学业30% + 行为20% + 出勤15% + 心理20% + 综合素质10% + 活动5%
    """
    score = 0
    details = {}
    
    # 1. 学业表现 (0-30分)
    grade_trend = report_data.get("grade_trend", "stable")
    grade_score = 30 if grade_trend == "rising" else (20 if grade_trend == "stable" else 10)
    details["grade"] = {"score": grade_score, "weight": 0.3, "trend": grade_trend}
    score += grade_score * 0.3
    
    # 2. 行为规范 (0-20分)
    discipline = report_data.get("discipline", {})
    discipline_total = discipline.get("total", 0)
    if discipline_total == 0:
        discipline_score = 20
    elif discipline_total <= 1:
        discipline_score = 15
    elif discipline_total <= 3:
        discipline_score = 10
    else:
        discipline_score = 0
    details["discipline"] = {"score": discipline_score, "weight": 0.2, "total": discipline_total}
    score += discipline_score * 0.2
    
    # 3. 出勤状态 (0-15分)
    attendance = report_data.get("attendance", {})
    absent_count = attendance.get("absent", 0)
    late_count = attendance.get("late", 0)
    if absent_count == 0 and late_count <= 1:
        attendance_score = 15
    elif absent_count <= 1 and late_count <= 3:
        attendance_score = 10
    elif absent_count <= 3:
        attendance_score = 5
    else:
        attendance_score = 0
    details["attendance"] = {"score": attendance_score, "weight": 0.15, "absent": absent_count, "late": late_count}
    score += attendance_score * 0.15
    
    # 4. 心理健康 (0-20分)
    psych = report_data.get("psych", {})
    psych_risk = psych.get("risk_level", "unknown")
    if psych_risk == "low":
        psych_score = 20
    elif psych_risk == "medium":
        psych_score = 10
    elif psych_risk == "high":
        psych_score = 0
    else:
        psych_score = 15  # 无数据
    details["psych"] = {"score": psych_score, "weight": 0.2, "risk_level": psych_risk}
    score += psych_score * 0.2
    
    # 5. 综合素质 (0-10分)
    quality = report_data.get("quality", {})
    if not quality:
        quality_score = 5
    else:
        avg_scores = [v["average"] for v in quality.values()]
        overall_avg = sum(avg_scores) / len(avg_scores) if avg_scores else 0
        quality_score = min(10, overall_avg / 10)  # 假设满分100，除以10得到0-10分
    details["quality"] = {"score": quality_score, "weight": 0.1}
    score += quality_score * 0.1
    
    # 6. 活动参与 (0-5分)
    activity = report_data.get("activity", {})
    activity_count = activity.get("total", 0)
    if activity_count >= 3:
        activity_score = 5
    elif activity_count >= 1:
        activity_score = 3
    else:
        activity_score = 0
    details["activity"] = {"score": activity_score, "weight": 0.05, "count": activity_count}
    score += activity_score * 0.05
    
    return round(score, 1), details


# ════════════════════════════════════════════════════════════
# 路由：报告列表
# ════════════════════════════════════════════════════════════

@growth_bp.route("/")
@login_required
@require_role("ms_admin", "grade_leader", "class_teacher", "parent")
def report_list():
    """成长报告列表页"""
    role = session.get("role", "")
    today = date.today()
    
    # 获取时间范围参数
    period_type = request.args.get("period", "week")  # week/month/semester
    start_date, end_date = _get_period_range(period_type)
    
    # 根据角色确定查询范围
    if role == "ms_admin":
        # 德育处：看到全校
        students = Student.query.all()
        page_title = "全校学生综合成长报告"
    elif role == "grade_leader":
        # 年级组：看到本年级
        grade_id = session.get("grade_id")
        students = Student.query.filter_by(grade_id=grade_id).all()
        page_title = f"年级学生综合成长报告"
    elif role == "class_teacher":
        # 班主任：看到本班
        class_id = session.get("class_id")
        students = Student.query.filter_by(class_id=class_id).all()
        page_title = "班级学生综合成长报告"
    elif role == "parent":
        # 家长：看到自己孩子
        student_id = session.get("student_id")
        students = [Student.query.get(student_id)] if student_id else []
        page_title = "孩子成长报告"
    else:
        students = []
        page_title = "成长报告"
    
    # 为每个学生生成报告摘要（批量预加载消除 N+1）
    student_ids = [s.id for s in students if s]

    # 批量统计违纪
    disc_map = dict(db.session.query(
        DisciplineRecord.student_id, func.count(DisciplineRecord.id)
    ).filter(
        DisciplineRecord.student_id.in_(student_ids),
        DisciplineRecord.created_at >= start_date,
    ).group_by(DisciplineRecord.student_id).all()) if student_ids else {}

    # 批量统计出勤问题
    att_map = dict(db.session.query(
        Attendance.student_id, func.count(Attendance.id)
    ).filter(
        Attendance.student_id.in_(student_ids),
        Attendance.record_date >= start_date,
        Attendance.status.in_(["absent", "late"]),
    ).group_by(Attendance.student_id).all()) if student_ids else {}

    # 批量预加载班级
    stu_class_map = {}
    if student_ids:
        cls_ids = list({s.class_id for s in students if s and s.class_id})
        if cls_ids:
            cls_map = {c.id: c for c in Class.query.filter(Class.id.in_(cls_ids)).all()}
            for s in students:
                if s and s.class_id:
                    stu_class_map[s.id] = cls_map.get(s.class_id)

    reports = []
    for stu in students:
        if not stu:
            continue

        discipline_count = disc_map.get(stu.id, 0)
        attendance_issues = att_map.get(stu.id, 0)

        # 计算综合评分
        report_data = {
            "grade_trend": _calc_grade_trend(stu.id, None)[0],
            "discipline": {"total": discipline_count},
            "attendance": {"absent": attendance_issues, "late": 0},
            "psych": _get_psych_stats(stu.id),
            "quality": {},
            "activity": {"total": 0},
        }
        overall_score, details = _calculate_overall_score(report_data)

        reports.append({
            "student_id": stu.id,
            "student_name": stu.name,
            "class_name": stu_class_map.get(stu.id).name if stu_class_map.get(stu.id) else "",
            "overall_score": overall_score,
            "risk_level": "high" if overall_score < 40 else ("medium" if overall_score < 70 else "low"),
            "details": details,
        })
    
    # 按综合评分排序（低风险排前面）
    reports.sort(key=lambda x: x["overall_score"], reverse=True)
    
    return render_template(
        "growth/report_list.html",
        page_title=page_title,
        reports=reports,
        period_type=period_type,
        start_date=start_date,
        end_date=end_date,
    )


# ════════════════════════════════════════════════════════════
# 路由：报告详情
# ════════════════════════════════════════════════════════════

@growth_bp.route("/detail/<int:sid>")
@login_required
@require_role("ms_admin", "grade_leader", "class_teacher", "parent")
def report_detail(sid):
    """成长报告详情页"""
    student = Student.query.get_or_404(sid)
    role = session.get("role", "")
    
    # 权限检查
    if role == "grade_leader" and student.grade_id != session.get("grade_id"):
        flash("无权查看该学生报告", "danger")
        return redirect(url_for("growth.report_list"))
    elif role in ("class_teacher", "teacher") and student.class_id != session.get("class_id"):
        flash("无权查看该学生报告", "danger")
        return redirect(url_for("growth.report_list"))
    elif role == "parent" and session.get("student_id") != sid:
        flash("无权查看该学生报告", "danger")
        return redirect(url_for("growth.report_list"))
    
    # 获取时间范围
    period_type = request.args.get("period", "week")
    start_date, end_date = _get_period_range(period_type)
    
    # 收集6个维度的数据
    report_data = {
        "grade_trend": _calc_grade_trend(sid, None),
        "discipline": _get_discipline_stats(sid, start_date, end_date),
        "attendance": _get_attendance_stats(sid, start_date, end_date),
        "psych": _get_psych_stats(sid),
        "quality": _get_quality_stats(sid, start_date, end_date),
        "activity": _get_activity_stats(sid, start_date, end_date),
    }
    
    # 计算综合评分
    overall_score, score_details = _calculate_overall_score(report_data)
    
    # 生成建议
    suggestions = []
    if report_data["psych"]["risk_level"] == "high":
        suggestions.append("建议安排心理老师个别访谈")
    if report_data["discipline"]["total"] >= 2:
        suggestions.append("建议德育处介入，制定行为干预方案")
    if report_data["attendance"]["absent"] >= 3:
        suggestions.append("建议联系家长，了解缺勤原因")
    if not suggestions:
        suggestions.append("学生表现良好，建议继续保持")
    
    return render_template(
        "growth/report_detail.html",
        student=student,
        report_data=report_data,
        overall_score=overall_score,
        score_details=score_details,
        suggestions=suggestions,
        period_type=period_type,
        start_date=start_date,
        end_date=end_date,
    )


# ════════════════════════════════════════════════════════════
# 路由：导出PDF
# ════════════════════════════════════════════════════════════

@growth_bp.route("/export/pdf/<int:sid>")
@login_required
@require_role("ms_admin", "grade_leader", "class_teacher", "parent")
def export_pdf(sid):
    """导出成长报告为PDF"""
    # TODO: 实现PDF导出功能
    flash("PDF导出功能开发中...", "info")
    return redirect(url_for("growth.report_detail", sid=sid))


# ════════════════════════════════════════════════════════════
# 路由：导出Excel
# ════════════════════════════════════════════════════════════

@growth_bp.route("/export/excel")
@login_required
@require_role("ms_admin", "grade_leader", "class_teacher")
def export_excel():
    """导出成长报告列表为Excel"""
    # TODO: 实现Excel导出功能
    flash("Excel导出功能开发中...", "info")
    return redirect(url_for("growth.report_list"))
