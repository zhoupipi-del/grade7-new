"""
统计查询服务层 — 从 bigscreen.py + cockpit.py 中抽离共享查询逻辑

所有函数接受可选的 grade_id 参数：
  - grade_id=None（默认）→ 全校范围查询（ms_admin 大屏）
  - grade_id=指定值 → 年级范围查询（驾驶舱）
"""

from datetime import date, timedelta
from collections import defaultdict
from sqlalchemy import func, text

from models import (
    db, Student, Class, User, Grade,
    DisciplineRecord, RoutineScore, WingsScore,
    Notice, NoticeReceipt, HomeVisit,
    MentalHealthAssessment, RiskRecord,
    Attendance, Score, Exam,
)


def get_basic_stats(grade_id=None, teacher_roles=None):
    """学生/班级/教师计数

    Args:
        grade_id: 年级ID（可选）
        teacher_roles: 教师角色列表（默认含 teacher/class_teacher/grade_leader）

    Returns:
        dict: {total_students, total_classes, total_teachers}
    """
    if teacher_roles is None:
        teacher_roles = ["class_teacher", "teacher", "grade_leader"]

    student_q = Student.query.filter_by(is_active=True)
    class_q = Class.query.filter_by(is_active=True)
    teacher_q = User.query.filter(User.role.in_(teacher_roles))

    if grade_id:
        student_q = student_q.filter(Student.grade_id == grade_id)
        class_q = class_q.filter(Class.grade_id == grade_id)
        teacher_q = teacher_q.filter(User.grade_id == grade_id)

    return {
        "total_students": student_q.count(),
        "total_classes": class_q.count(),
        "total_teachers": teacher_q.count(),
    }


def get_discipline_stats(grade_id=None, since=None):
    """违纪统计 (按类型 + 按分类聚合)

    Args:
        grade_id: 年级ID（可选）
        since: 起始日期（默认30天前）

    Returns:
        dict: {total_count, by_type, by_category}
    """
    if since is None:
        since = date.today() - timedelta(days=30)

    query = DisciplineRecord.query.filter(
        DisciplineRecord.created_at >= since,
    )
    if grade_id:
        query = query.filter(DisciplineRecord.grade_id == grade_id)

    total_count = query.count()

    # 按类型聚合
    type_stats = db.session.query(
        DisciplineRecord.type,
        func.count(DisciplineRecord.id),
    ).filter(
        DisciplineRecord.created_at >= since,
    )
    if grade_id:
        type_stats = type_stats.filter(DisciplineRecord.grade_id == grade_id)
    type_stats = type_stats.group_by(DisciplineRecord.type).all()

    by_type = dict(type_stats)
    # 统一补齐标准等级
    for level in ["warning", "minor", "major", "serious"]:
        if level not in by_type:
            by_type[level] = 0

    # 按分类聚合（如果有 category 字段）
    cat_rows = db.session.query(
        DisciplineRecord.category,
        func.count(DisciplineRecord.id),
    ).filter(
        DisciplineRecord.created_at >= since,
    )
    if grade_id:
        cat_rows = cat_rows.filter(DisciplineRecord.grade_id == grade_id)
    cat_rows = cat_rows.group_by(DisciplineRecord.category).all()

    cat_map = {}
    for cat, cnt in cat_rows:
        cat_key = cat or "未分类"
        cat_map[cat_key] = cat_map.get(cat_key, 0) + cnt
    by_category = [{"name": k, "count": v} for k, v in cat_map.items()]

    return {
        "total_count": total_count,
        "by_type": by_type,
        "by_category": by_category,
    }


def get_attendance_stats(grade_id=None, since=None):
    """考勤按状态聚合

    Args:
        grade_id: 年级ID（可选）
        since: 起始日期（默认30天前）

    Returns:
        dict: {by_status, total, attendance_rate}
    """
    if since is None:
        since = date.today() - timedelta(days=30)

    query = db.session.query(
        Attendance.status,
        func.count(Attendance.id),
    ).filter(
        Attendance.record_date >= since,
    )
    if grade_id:
        query = query.filter(Attendance.grade_id == grade_id)
    rows = query.group_by(Attendance.status).all()

    by_status = dict(rows)
    for key in ["present", "late", "early", "absent", "leave"]:
        if key not in by_status:
            by_status[key] = 0

    total = sum(by_status.values())
    attendance_rate = round(by_status["present"] / total * 100, 1) if total > 0 else 0

    return {
        "by_status": by_status,
        "total": total,
        "attendance_rate": attendance_rate,
    }


def get_wing_stats(grade_id=None):
    """五翼评分均值和各维度分布

    Args:
        grade_id: 年级ID（可选）

    Returns:
        dict: {avg, by_dimension: [{name, score}]}
    """
    dim_q = db.session.query(
        WingsScore.dimension,
        func.avg(WingsScore.score),
    )
    if grade_id:
        dim_q = dim_q.filter(WingsScore.grade_id == grade_id)
    dim_rows = dim_q.group_by(WingsScore.dimension).all()

    avg_q = db.session.query(func.avg(WingsScore.score))
    if grade_id:
        avg_q = avg_q.filter(WingsScore.grade_id == grade_id)
    wing_avg_raw = avg_q.scalar()
    wing_avg = round(float(wing_avg_raw), 1) if wing_avg_raw else 0

    return {
        "avg": wing_avg,
        "by_dimension": [
            {"name": dim, "score": round(float(s), 1)}
            for dim, s in dim_rows
        ],
    }


def get_mental_health_stats(grade_id=None):
    """心理健康风险分布

    Args:
        grade_id: 年级ID（可选）

    Returns:
        dict: {high, medium, low}
    """
    query = MentalHealthAssessment.query
    if grade_id:
        query = query.filter_by(grade_id=grade_id)

    stats = db.session.query(
        MentalHealthAssessment.risk_level,
        func.count(MentalHealthAssessment.id),
    )
    if grade_id:
        stats = stats.filter_by(grade_id=grade_id)
    stats = stats.group_by(MentalHealthAssessment.risk_level).all()

    risk_map = dict(stats)
    return {
        "high": risk_map.get("high", 0),
        "medium": risk_map.get("medium", 0),
        "low": risk_map.get("low", 0),
    }


def get_notice_read_rate(grade_id=None, total_students=None, since=None):
    """通知阅读率（高效 JOIN 查询）

    Args:
        grade_id: 年级ID（可选）
        total_students: 学生总数（避免重复查询，调用方可传入）
        since: 起始日期（可选，过滤近期通知数，不影响 read_rate 计算）

    Returns:
        dict: {notice_count, read_rate, notice_count_recent(如果传了since)}
    """
    notice_q = Notice.query
    if grade_id:
        notice_q = notice_q.filter_by(grade_id=grade_id)
    total_notices = notice_q.count()

    result = {"notice_count": total_notices, "read_rate": 0}

    if since is not None:
        notice_q_recent = Notice.query
        if grade_id:
            notice_q_recent = notice_q_recent.filter_by(grade_id=grade_id)
        result["notice_count_recent"] = notice_q_recent.filter(Notice.created_at >= since).count()

    if total_notices == 0:
        return result

    # 计算期望签收人次
    if total_students is None:
        student_count = Student.query.filter_by(is_active=True)
        if grade_id:
            student_count = student_count.filter_by(grade_id=grade_id)
        total_students = student_count.count()

    total_receipts_needed = total_notices * max(total_students, 1)

    # 一次 JOIN 替代多次查询
    sql_params = {}
    sql_where = "WHERE n.id IS NOT NULL"
    if grade_id:
        sql_where += " AND n.grade_id = :gid"
        sql_params["gid"] = grade_id

    read_count = db.session.execute(text(f"""
        SELECT COUNT(nr.id)
        FROM notice_receipts nr
        JOIN notices n ON nr.notice_id = n.id
        {sql_where} AND nr.status IN ('read', 'signed')
    """), sql_params).scalar()

    read_rate = round(int(read_count or 0) / total_receipts_needed * 100, 1) if read_count else 0

    result["read_rate"] = read_rate
    return result


def get_visit_stats(grade_id=None, since=None):
    """家访统计

    Args:
        grade_id: 年级ID（可选）
        since: 起始日期（默认30天前）

    Returns:
        dict: {total_count, by_type: [{name, count}]}
    """
    if since is None:
        since = date.today() - timedelta(days=30)

    query = HomeVisit.query.filter(HomeVisit.visit_date >= since)
    if grade_id:
        query = query.filter(HomeVisit.grade_id == grade_id)
    total_count = query.count()

    # 按家访类型聚合
    type_rows = db.session.query(
        HomeVisit.visit_type,
        func.count(HomeVisit.id),
    ).filter(
        HomeVisit.visit_date >= since,
    )
    if grade_id:
        type_rows = type_rows.filter(HomeVisit.grade_id == grade_id)
    type_rows = type_rows.group_by(HomeVisit.visit_type).all()

    return {
        "total_count": total_count,
        "by_type": [
            {"name": vtype, "count": cnt}
            for vtype, cnt in type_rows
        ],
    }


def get_risk_stats(grade_id=None, target_scan_date=None):
    """AI预警统计 — 取最新扫描批次

    Args:
        grade_id: 年级ID（可选）
        target_scan_date: 目标扫描日期（不传则取最新批次）

    Returns:
        dict: {red, yellow, green, scan_date}
    """
    if target_scan_date is None:
        scan_q = db.session.query(func.max(RiskRecord.scan_date))
        if grade_id:
            scan_q = scan_q.filter(RiskRecord.grade_id == grade_id)
        target_scan_date = scan_q.scalar()

    if not target_scan_date:
        return {"red": 0, "yellow": 0, "green": 0, "scan_date": None}

    risk_q = db.session.query(
        RiskRecord.risk_level,
        func.count(RiskRecord.id),
    ).filter(RiskRecord.scan_date == target_scan_date)
    if grade_id:
        risk_q = risk_q.filter(RiskRecord.grade_id == grade_id)
    risk_rows = risk_q.group_by(RiskRecord.risk_level).all()

    risk_map = dict(risk_rows)
    result = {
        "red": risk_map.get("red", 0),
        "yellow": risk_map.get("yellow", 0),
        "green": risk_map.get("green", 0),
        "scan_date": target_scan_date.strftime("%Y-%m-%d") if hasattr(target_scan_date, "strftime") else str(target_scan_date),
    }

    return result


def get_trend_data(grade_id=None, days=7):
    """多维度趋势数据 (违纪/常规评分/考勤) — 优化: 批量 GROUP BY 替代逐日查询

    Args:
        grade_id: 年级ID（可选）
        days: 天数

    Returns:
        list[dict]: [{date, discipline, routine, attendance}]
    """
    from utils import get_local_now
    today = get_local_now().date()
    trend_dates = [(today - timedelta(days=i)) for i in range(days - 1, -1, -1)]
    d0, d6 = trend_dates[0], trend_dates[-1]

    # 违纪趋势
    disc_q = db.session.query(
        func.date(DisciplineRecord.created_at),
        func.count(DisciplineRecord.id),
    ).filter(
        func.date(DisciplineRecord.created_at) >= d0,
        func.date(DisciplineRecord.created_at) <= d6,
    )
    if grade_id:
        disc_q = disc_q.filter(DisciplineRecord.grade_id == grade_id)
    disc_trend_map = dict(disc_q.group_by(func.date(DisciplineRecord.created_at)).all())

    # 常规评分趋势
    rout_q = db.session.query(
        RoutineScore.record_date,
        func.avg(RoutineScore.score),
    ).filter(
        RoutineScore.record_date >= d0,
        RoutineScore.record_date <= d6,
    )
    if grade_id:
        rout_q = rout_q.filter(RoutineScore.grade_id == grade_id)
    rout_trend_map = dict(rout_q.group_by(RoutineScore.record_date).all())

    # 考勤趋势
    att_q = db.session.query(
        Attendance.record_date,
        Attendance.status,
        func.count(Attendance.id),
    ).filter(
        Attendance.record_date >= d0,
        Attendance.record_date <= d6,
    )
    if grade_id:
        att_q = att_q.filter(Attendance.grade_id == grade_id)
    att_rows = att_q.group_by(Attendance.record_date, Attendance.status).all()

    att_by_day = {}
    for d, s, c in att_rows:
        if d not in att_by_day:
            att_by_day[d] = {"present": 0, "total": 0}
        att_by_day[d][s] = c
        att_by_day[d]["total"] += c

    trend = []
    for day in trend_dates:
        t = att_by_day.get(day, {"present": 0, "total": 0})
        day_att_rate = round(t["present"] / t["total"] * 100, 1) if t["total"] > 0 else 100
        trend.append({
            "date": day.strftime("%m-%d"),
            "discipline": disc_trend_map.get(day, 0),
            "routine": float(rout_trend_map.get(day, 0)) if rout_trend_map.get(day) else 0,
            "attendance": day_att_rate,
        })

    return trend


def get_class_score_ranking(grade_id=None, limit=10):
    """班级常规评分排行

    Args:
        grade_id: 年级ID（可选）
        limit: 返回数量

    Returns:
        list[dict]: [{class_id, name, score}]
    """
    q = db.session.query(
        Class.id, Class.name,
        func.avg(RoutineScore.score).label("avg_score"),
    ).join(RoutineScore, RoutineScore.class_id == Class.id).filter(
        Class.is_active == True,
    )
    if grade_id:
        q = q.filter(Class.grade_id == grade_id)
    rows = q.group_by(Class.id, Class.name).order_by(
        func.avg(RoutineScore.score).desc()
    ).limit(limit).all()

    return [
        {
            "id": cid,
            "name": name,
            "score": round(float(score) if score else 0, 1),
        }
        for cid, name, score in rows
    ]


def get_score_overview(grade_id=None, exam_id=None):
    """考试概览（最近一次考试的平均分/及格率）

    Args:
        grade_id: 年级ID（可选）
        exam_id: 指定考试ID（可选，不传则取最近一次）

    Returns:
        dict: {exam_name, avg_score, pass_rate}
    """
    latest_exam = None
    if exam_id:
        latest_exam = Exam.query.get(exam_id)
    else:
        q = Exam.query
        if grade_id:
            q = q.filter_by(grade_id=grade_id)
        latest_exam = q.order_by(Exam.exam_date.desc()).first()

    if not latest_exam:
        return {"exam_name": "暂无考试", "avg_score": 0, "pass_rate": 0}

    score_q = Score.query.filter(Score.exam_id == latest_exam.id)
    if grade_id:
        score_q = score_q.filter(Score.grade_id == grade_id)

    total_scores = db.session.query(func.avg(Score.score)).filter(
        Score.exam_id == latest_exam.id,
    )
    if grade_id:
        total_scores = total_scores.filter(Score.grade_id == grade_id)
    avg_raw = total_scores.scalar()

    pass_count = score_q.filter(Score.score >= 60).count()
    total_count = score_q.count()

    return {
        "exam_name": latest_exam.name,
        "avg_score": round(float(avg_raw), 1) if avg_raw else 0,
        "pass_rate": round(pass_count / total_count * 100, 1) if total_count > 0 else 0,
    }
