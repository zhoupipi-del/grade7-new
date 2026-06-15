"""德育处工作台 — 规则配置/任务下发/问题学生建档/全校总览"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from models import db, Student, Class, Grade, User, Task, TaskFeedback
from models import DisciplineRecord, DisciplineAppeal, RoutineScore, ProblemStudent, ProblemTrack, ROLES, Subject, FlagEvaluation
from models import Attendance, LeaveRequest
from models import Message
from blueprints.discipline_utils import check_escalation, send_discipline_notifications, send_appeal_notifications, deduct_quality_score
from decorators import login_required, require_role, scope_query, require_permission
from utils.db_utils import safe_commit
from utils import get_local_now
from datetime import date, datetime, timedelta
from sqlalchemy import func

ms_bp = Blueprint("ms", __name__)


# ── 工作台首页 ──
@ms_bp.route("/")
@require_role("ms_admin")
def dashboard():
    stats = {
        "student_count": Student.query.filter_by(is_active=True).count(),
        "class_count": Class.query.filter_by(is_active=True).count(),
        "discipline_count": DisciplineRecord.query.filter_by(status="active").count(),
        "problem_count": ProblemStudent.query.filter_by(status="active").count(),
        "pending_tasks": Task.query.filter_by(status="pending").count(),
    }
    grades = Grade.query.order_by(Grade.sort_order).all()
    recent_disciplines = DisciplineRecord.query.order_by(
        DisciplineRecord.created_at.desc()
    ).limit(10).all()
    return render_template("ms/dashboard.html", stats=stats, grades=grades,
                           recent_disciplines=recent_disciplines)


# ── 任务管理 ──
@ms_bp.route("/tasks")
@require_role("ms_admin")
def task_list():
    status = request.args.get("status", "")
    q = Task.query.filter_by(from_user_id=session.get("user_id"))
    if status:
        q = q.filter_by(status=status)
    tasks = q.order_by(Task.created_at.desc()).all()
    grades = Grade.query.order_by(Grade.sort_order).all()
    classes = Class.query.filter_by(is_active=True).order_by(Class.name).all()
    # 统计各状态数量
    status_counts = {
        "pending": Task.query.filter_by(from_user_id=session.get("user_id"), status="pending").count(),
        "assigned": Task.query.filter_by(from_user_id=session.get("user_id"), status="assigned").count(),
        "done": Task.query.filter_by(from_user_id=session.get("user_id"), status="done").count(),
        "closed": Task.query.filter_by(from_user_id=session.get("user_id"), status="closed").count(),
    }
    return render_template("ms/tasks.html", tasks=tasks, grades=grades, classes=classes,
                           status=status, status_counts=status_counts)


@ms_bp.route("/tasks/create", methods=["POST"])
@require_role("ms_admin")
def create_task():
    target_type = request.form["target_type"]
    # 解析截止日期
    deadline_str = request.form.get("deadline")
    deadline = date.fromisoformat(deadline_str) if deadline_str else None
    if target_type == "grade":
        # 多发：每个选中的年级一条任务
        grade_ids = request.form.getlist("target_ids")
        if not grade_ids:
            flash("请选择目标年级", "danger")
            return redirect(url_for("ms.task_list"))
        for gid in grade_ids:
            task = Task(
                title=request.form["title"],
                content=request.form.get("content", ""),
                from_role="ms_admin",
                from_user_id=session.get("user_id"),
                target_type="grade",
                target_id=int(gid),
                deadline=deadline,
            )
            db.session.add(task)
    elif target_type == "class":
        class_ids = request.form.getlist("target_ids")
        if not class_ids:
            flash("请选择目标班级", "danger")
            return redirect(url_for("ms.task_list"))
        for cid in class_ids:
            task = Task(
                title=request.form["title"],
                content=request.form.get("content", ""),
                from_role="ms_admin",
                from_user_id=session.get("user_id"),
                target_type="class",
                target_id=int(cid),
                deadline=deadline,
            )
            db.session.add(task)
    else:
        flash("无效的目标类型", "danger")
        return redirect(url_for("ms.task_list"))
    safe_commit()
    flash(f"任务已下发", "success")
    return redirect(url_for("ms.task_list"))


@ms_bp.route("/tasks/<int:tid>")
@require_role("ms_admin")
def task_detail(tid):
    task = Task.query.get_or_404(tid)
    feedbacks = (TaskFeedback.query.filter_by(task_id=tid)
                 .order_by(TaskFeedback.created_at.asc()).all())
    # 目标名称
    target_label = "全部"
    if task.target_type == "grade":
        g = Grade.query.get(task.target_id)
        target_label = f"年级：{g.name}" if g else f"年级ID:{task.target_id}"
    elif task.target_type == "class":
        c = Class.query.get(task.target_id)
        target_label = f"班级：{c.name}" if c else f"班级ID:{task.target_id}"
    return render_template("ms/task_detail.html", task=task, feedbacks=feedbacks,
                           target_label=target_label)


@ms_bp.route("/tasks/<int:tid>/close", methods=["POST"])
@require_role("ms_admin")
def close_task(tid):
    task = Task.query.get_or_404(tid)
    task.status = "closed"
    task.finished_at = get_local_now()
    safe_commit()
    flash("任务已关闭", "success")
    return redirect(url_for("ms.task_list"))


# ── 纪律管理 — 全校视图 ──
@ms_bp.route("/discipline")
@require_role("ms_admin")
@require_permission("view_discipline")  # ← 新增：细粒度权限检查
def discipline_list():
    page = request.args.get("page", 1, type=int)
    grade_filter = request.args.get("grade_id", type=int)
    from sqlalchemy.orm import joinedload
    q = DisciplineRecord.query
    if grade_filter:
        q = q.filter_by(grade_id=grade_filter)
    records = q.options(
        joinedload(DisciplineRecord.student).joinedload(Student.class_)
    ).order_by(DisciplineRecord.created_at.desc()).paginate(
        page=page, per_page=20)
    grades = Grade.query.all()
    students = Student.query.filter_by(is_active=True).options(
        joinedload(Student.class_)
    ).order_by(Student.grade_id, Student.class_id, Student.student_no).all()
    return render_template("ms/discipline.html", records=records, grades=grades,
                           students=students, grade_filter=grade_filter)


@ms_bp.route("/discipline/add", methods=["POST"])
@require_role("ms_admin")
@require_permission("manage_discipline")  # ← 新增：细粒度权限检查
def add_discipline():
    from utils.db_utils import safe_commit
    student_id = request.form.get("student_id", type=int)
    student = Student.query.get(student_id)
    if not student:
        flash("学生不存在", "danger")
        return redirect(url_for("ms.discipline_list"))
    record = DisciplineRecord(
        student_id=student.id,
        class_id=student.class_id,
        grade_id=student.grade_id,
        type=request.form["type"],
        category=request.form.get("category", ""),
        description=request.form["description"],
        action_taken=request.form.get("action_taken", ""),
        points=request.form.get("points", 0, type=int),
        created_by=session.get("user_id"),
    )
    db.session.add(record)
    # 积分累计自动升级 + 自动推送通知（与违纪记录同一个事务）
    check_escalation(student, session.get("user_id"))
    send_discipline_notifications(record, student)
    deduct_quality_score(record, student, session.get("user_id"))

    safe_commit()
    flash(f"已记录 {student.name} 违纪", "success")

    # ── MLOps 自进化: 违纪记录变更触发模型自动重训 ──
    try:
        from utils.model_retrain import trigger_auto_retrain
        trigger_auto_retrain(current_app._get_current_object(), grade_id=student.grade_id)
    except Exception:
        pass  # 重训失败不影响违纪记录

    return redirect(url_for("ms.discipline_list"))


@ms_bp.route("/discipline/<int:rid>/delete", methods=["POST"])
@require_role("ms_admin")
def delete_discipline(rid):
    record = DisciplineRecord.query.get_or_404(rid)
    db.session.delete(record)
    safe_commit()
    flash("违纪记录已删除", "success")
    return redirect(url_for("ms.discipline_list"))


@ms_bp.route("/discipline/stats")
@require_role("ms_admin")
def discipline_stats():
    import json
    grades = Grade.query.all()
    # 按年级统计 — 单次 GROUP BY 替代 N×3 次 COUNT
    grade_raw = db.session.query(
        DisciplineRecord.grade_id,
        func.count().label("total"),
        func.sum(func.if_(DisciplineRecord.status == "active", 1, 0)).label("active"),
        func.sum(func.if_(DisciplineRecord.status == "resolved", 1, 0)).label("resolved"),
    ).group_by(DisciplineRecord.grade_id).all()
    grade_map = {}
    for row in grade_raw:
        grade_map[row[0]] = {"total": int(row[1]), "active": int(row[2] or 0), "resolved": int(row[3] or 0)}
    grade_stats = []
    for g in grades:
        s = grade_map.get(g.id, {"total": 0, "active": 0, "resolved": 0})
        grade_stats.append({"name": g.name, "total": s["total"], "active": s["active"], "resolved": s["resolved"]})

    # 按类型统计 + 中文标签
    type_labels_map = {"warning": "警告", "minor": "轻微", "major": "重大", "serious": "严重"}
    type_stats = db.session.query(
        DisciplineRecord.type, func.count().label("cnt")
    ).group_by(DisciplineRecord.type).all()
    type_stats = [{"type": type_labels_map.get(t[0], t[0]), "cnt": t[1]} for t in type_stats]

    # 按类别统计
    category_stats = db.session.query(
        DisciplineRecord.category,
        func.count().label("cnt"),
        func.sum(DisciplineRecord.points).label("points_sum")
    ).group_by(DisciplineRecord.category).all()
    category_stats = [{"category": c[0] or "未分类", "cnt": int(c[1]), "points_sum": float(c[2]) if c[2] else 0} for c in category_stats]

    # 按班级统计（柱状图数据）
    class_stats = db.session.query(
        Class.name, func.count().label("cnt")
    ).join(DisciplineRecord, DisciplineRecord.class_id == Class.id).group_by(
        DisciplineRecord.class_id, Class.name
    ).order_by(Class.grade_id, Class.name).all()
    class_stats = [{"name": c[0], "cnt": c[1]} for c in class_stats]

    # 转为JSON供Chart.js使用
    chart_data = {
        "typeLabels": json.dumps([t["type"] for t in type_stats]),
        "typeCounts": json.dumps([t["cnt"] for t in type_stats]),
        "categoryLabels": json.dumps([c["category"] for c in category_stats]),
        "categoryCounts": json.dumps([c["cnt"] for c in category_stats]),
        "categoryPoints": json.dumps([c["points_sum"] for c in category_stats]),
        "classLabels": json.dumps([c["name"] for c in class_stats]),
        "classCounts": json.dumps([c["cnt"] for c in class_stats]),
    }

    return render_template("ms/discipline_stats.html",
                           grade_stats=grade_stats,
                           type_stats=type_stats,
                           category_stats=category_stats,
                           class_stats=class_stats,
                           chart_data=chart_data)


@ms_bp.route("/discipline/<int:rid>/resolve", methods=["POST"])
@require_role("ms_admin")
def discipline_resolve(rid):
    record = DisciplineRecord.query.get_or_404(rid)
    record.status = "resolved"
    record.resolved_at = get_local_now()
    safe_commit()
    flash("已标记为已解决", "success")
    return redirect(url_for("ms.discipline_list"))


# ── 纪律申诉复核 ──────────────────────────────────────────────────
@ms_bp.route("/appeals")
@require_role("ms_admin")
def appeal_list():
    """申诉列表"""
    status_filter = request.args.get("status", "")
    page = request.args.get("page", 1, type=int)

    q = DisciplineAppeal.query
    if status_filter:
        q = q.filter_by(status=status_filter)
    q = q.order_by(DisciplineAppeal.status == "pending",
                   DisciplineAppeal.created_at.desc() if status_filter != "pending" else DisciplineAppeal.created_at.asc())

    pagination = q.paginate(page=page, per_page=20, error_out=False)
    appeals = pagination.items

    # 统计数据
    pending_count = DisciplineAppeal.query.filter_by(status="pending").count()
    approved_count = DisciplineAppeal.query.filter_by(status="approved").count()
    rejected_count = DisciplineAppeal.query.filter_by(status="rejected").count()

    return render_template("ms/appeals.html",
                           appeals=appeals,
                           pagination=pagination,
                           status_filter=status_filter,
                           pending_count=pending_count,
                           approved_count=approved_count,
                           rejected_count=rejected_count)


@ms_bp.route("/appeals/<int:aid>", methods=["GET", "POST"])
@require_role("ms_admin")
def appeal_review(aid):
    """申诉复核"""
    appeal = DisciplineAppeal.query.get_or_404(aid)

    if request.method == "POST":
        action = request.form.get("action", "")
        review_comment = request.form.get("review_comment", "").strip()

        if action == "approve":
            appeal.status = "approved"
            # 撤销原始违纪记录
            record = appeal.discipline
            if record:
                record.status = "resolved"
                record.resolved_at = get_local_now()
            flash("申诉已通过，原违纪记录已撤销", "success")
        elif action == "reject":
            appeal.status = "rejected"
            # 恢复违纪记录状态
            record = appeal.discipline
            if record and record.status == "appealed":
                record.status = "active"
            flash("申诉已驳回", "warning")
        else:
            flash("无效操作", "danger")
            return redirect(url_for("ms.appeal_review", aid=aid))

        appeal.review_comment = review_comment or ("同意申诉" if action == "approve" else "申诉理由不成立")
        appeal.reviewed_by = session.get("user_id")
        appeal.reviewed_at = get_local_now()
        safe_commit()

        send_appeal_notifications(appeal, appeal.student, appeal.discipline)
        safe_commit()

        return redirect(url_for("ms.appeal_list"))

    # 获取该学生的违纪记录历史
    discipline_history = DisciplineRecord.query.filter_by(
        student_id=appeal.student_id
    ).order_by(DisciplineRecord.created_at.desc()).limit(10).all()

    return render_template("ms/appeal_review.html",
                           appeal=appeal,
                           discipline_history=discipline_history)


# ── 常规评分总览 ──
@ms_bp.route("/routine")
@require_role("ms_admin")
def routine_overview():
    grade_id = request.args.get("grade_id", type=int)
    page = request.args.get("page", 1, type=int)
    category = request.args.get("category", type=str)
    per_page = 50

    scores = RoutineScore.query
    if grade_id:
        scores = scores.filter_by(grade_id=grade_id)
    if category:
        scores = scores.filter_by(category=category)
    scores = scores.order_by(RoutineScore.record_date.desc()).paginate(page=page, per_page=per_page, error_out=False)
    grades = Grade.query.all()
    classes = Class.query.filter_by(is_active=True).all()
    classes_by_id = {c.id: c for c in classes}
    return render_template("ms/routine.html", scores=scores, grades=grades,
                           classes=classes, classes_by_id=classes_by_id,
                           today=date.today(), grade_filter=grade_id,
                           category_filter=category)


@ms_bp.route("/routine/add", methods=["POST"])
@require_role("ms_admin")
def add_routine():
    class_id = request.form.get("class_id", type=int)
    cls = Class.query.get(class_id)
    if not cls:
        flash("班级不存在", "danger")
        return redirect(url_for("ms.routine_overview"))
    record_date = request.form.get("record_date", str(date.today()))
    score = RoutineScore(
        class_id=class_id,
        grade_id=cls.grade_id,
        category=request.form["category"],
        score=request.form.get("score", 0, type=int),
        note=request.form.get("note", ""),
        inspector=request.form.get("inspector", session.get("display_name", "")),
        scorer_type="ms_admin",
        record_date=date.fromisoformat(record_date) if record_date else date.today(),
    )
    db.session.add(score)
    safe_commit()
    flash("评分已录入", "success")
    return redirect(url_for("ms.routine_overview"))


@ms_bp.route("/routine/<int:sid>/delete", methods=["POST"])
@require_role("ms_admin")
def delete_routine(sid):
    s = RoutineScore.query.get_or_404(sid)
    db.session.delete(s)
    safe_commit()
    flash("评分已删除", "success")
    return redirect(url_for("ms.routine_overview"))


# ── 班级流动红旗（三维度加权评价）──

def _calc_flag_weights(self_score, grade_score, ms_score):
    """
    根据三维度数据是否可用，计算实际权重。
    标准权重: 班主任0.2 + 年级组0.3 + 德育处0.5
    某维度缺失时，其余维度按比例瓜分该权重。
    """
    BASE_W = [0.2, 0.3, 0.5]
    scores = [self_score, grade_score, ms_score]
    available = [s is not None for s in scores]

    if not any(available):
        return BASE_W, 0.0

    if all(available):
        return BASE_W, (self_score * 0.2 + grade_score * 0.3 + ms_score * 0.5)

    # 缺失维度权重按比例重分配
    missing_weight = sum(w for w, a in zip(BASE_W, available) if not a)
    avail_indices = [i for i, a in enumerate(available) if a]
    avail_total_w = sum(BASE_W[i] for i in avail_indices)

    weights = list(BASE_W)
    for i in avail_indices:
        weights[i] = BASE_W[i] + missing_weight * (BASE_W[i] / avail_total_w)
    for i in range(3):
        if not available[i]:
            weights[i] = 0.0

    final = sum(s * w for s, w in zip(scores, weights) if s is not None)
    return weights, round(final, 2)


@ms_bp.route("/leaderboard")
@require_role("ms_admin")
def leaderboard():
    """流动红旗评价 — 支持 Tab 切换周评/月评/期末"""
    grade_id = request.args.get("grade_id", type=int)
    period_type = request.args.get("period_type", "week")
    period_label = request.args.get("period_label", "")

    grades = Grade.query.all()

    # 计算可选的期间列表
    now = get_local_now()
    period_labels = _build_period_labels(now)

    # 如果没选期间，默认选第一个
    if not period_label and period_labels.get(period_type):
        period_label = period_labels[period_type][0]["value"]

    # 查询已发布的评价记录
    q = FlagEvaluation.query.filter_by(
        period_type=period_type,
        status="published"
    )
    if grade_id:
        q = q.filter_by(grade_id=grade_id)
    if period_label:
        q = q.filter_by(period_label=period_label)

    evals = q.order_by(FlagEvaluation.rank.asc()).all()
    # 按年级分组
    evals_by_grade = {}
    for ev in evals:
        evals_by_grade.setdefault(ev.grade_id, []).append(ev)

    return render_template("ms/leaderboard.html",
                           grades=grades, grade_filter=grade_id,
                           period_type=period_type, period_label=period_label,
                           period_labels=period_labels,
                           evals_by_grade=evals_by_grade)


def _build_period_labels(now):
    """生成当前可用的周/月/期末期间列表"""
    import calendar

    # 周列表：最近8周（按周一）
    week_labels = []
    # 找到本周一
    weekday = now.weekday()
    this_monday = now.date() - timedelta(days=weekday)
    for i in range(7, -1, -1):
        mon = this_monday - timedelta(weeks=i)
        sun = mon + timedelta(days=6)
        week_num = mon.isocalendar()[1]
        week_labels.append({
            "value": mon.isoformat(),
            "label": f"第{week_num}周 ({mon.strftime('%m/%d')}~{sun.strftime('%m/%d')})",
            "start": mon,
            "end": sun,
        })

    # 月列表：最近6个月（纯标准库实现）
    month_labels = []
    for i in range(5, -1, -1):
        # 用整数月份算术代替 dateutil
        y, m = now.year, now.month
        m = m - i
        while m <= 0:
            m += 12
            y -= 1
        d = date(y, m, 1)
        _, last_day = calendar.monthrange(d.year, d.month)
        month_labels.append({
            "value": d.isoformat(),
            "label": f"{d.year}年{d.month}月",
            "start": d,
            "end": date(d.year, d.month, last_day),
        })

    # 期末标签
    term_labels = [{"value": "2025-2026-2", "label": "2025-2026学年第二学期"}]

    return {
        "week": week_labels,
        "month": month_labels,
        "term": term_labels,
    }


@ms_bp.route("/leaderboard/generate", methods=["POST"])
@require_role("ms_admin")
def generate_evaluation():
    """生成评价草稿 — 根据选定期间和年级，计算三维度加权得分"""
    grade_id = request.form.get("grade_id", type=int)
    period_type = request.form.get("period_type")
    period_label = request.form.get("period_label")

    if not period_type or not period_label:
        flash("请选择评价周期", "danger")
        return redirect(url_for("ms.leaderboard"))

    # 解析期间日期范围
    start_date, end_date = _parse_period_range(period_type, period_label)
    if not start_date or not end_date:
        flash("无法解析评价周期", "danger")
        return redirect(url_for("ms.leaderboard"))

    # 获取目标班级列表
    if grade_id:
        classes = Class.query.filter_by(grade_id=grade_id, is_active=True).all()
        grades = Grade.query.filter_by(id=grade_id).all()
    else:
        classes = Class.query.filter_by(is_active=True).all()
        grades = Grade.query.all()

    if not classes:
        flash("没有找到班级", "danger")
        return redirect(url_for("ms.leaderboard"))

    # 批量查询该期间内所有常规评分（按 scorer_type 分组）
    all_scores = RoutineScore.query.filter(
        RoutineScore.record_date >= start_date,
        RoutineScore.record_date <= end_date,
        RoutineScore.class_id.in_([c.id for c in classes])
    ).all()

    # 按班级+scorer_type聚合均分
    from collections import defaultdict
    agg = defaultdict(lambda: defaultdict(list))
    for s in all_scores:
        agg[s.class_id][s.scorer_type].append(s.score)

    # 删除该期间的旧草稿
    FlagEvaluation.query.filter_by(
        period_type=period_type, period_label=period_label, status="draft"
    ).filter(
        FlagEvaluation.class_id.in_([c.id for c in classes])
    ).delete(synchronize_session="fetch")
    safe_commit()

    # 生成新草稿
    created = 0
    for cls in classes:
        self_scores = agg.get(cls.id, {}).get("class_teacher", [])
        grade_scores = agg.get(cls.id, {}).get("grade_leader", [])
        ms_scores = agg.get(cls.id, {}).get("ms_admin", [])

        self_avg = sum(self_scores) / len(self_scores) if self_scores else None
        grade_avg = sum(grade_scores) / len(grade_scores) if grade_scores else None
        ms_avg = sum(ms_scores) / len(ms_scores) if ms_scores else None

        weights, base = _calc_flag_weights(self_avg, grade_avg, ms_avg)

        # ── 违纪+考勤合流扣分 ──
        # 1. 违纪扣分（周期内该班级所有违纪记录的points总和 × 0.1）
        discipline_points = db.session.query(
            func.sum(DisciplineRecord.points)
        ).filter(
            DisciplineRecord.class_id == cls.id,
            DisciplineRecord.created_at >= start_date,
            DisciplineRecord.created_at <= end_date
        ).scalar() or 0.0

        # 2. 考勤异常扣分（迟到/缺勤/早退/请假 次数 × 0.05）
        attendance_exceptions = Attendance.query.filter(
            Attendance.class_id == cls.id,
            Attendance.status.in_(["late", "absent", "early", "leave"]),
            Attendance.record_date >= start_date,
            Attendance.record_date <= end_date
        ).count()

        discipline_deduction = round(discipline_points * 0.1, 2)
        attendance_deduction = round(attendance_exceptions * 0.05, 2)

        final = round(base - discipline_deduction - attendance_deduction, 2)
        final = max(0.0, final)  # 防止扣成负数

        ev = FlagEvaluation(
            period_type=period_type,
            period_label=period_label,
            grade_id=cls.grade_id,
            class_id=cls.id,
            self_score=self_avg,
            grade_score=grade_avg,
            ms_score=ms_avg,
            self_weight=weights[0],
            grade_weight=weights[1],
            ms_weight=weights[2],
            base_score=base,
            discipline_points=discipline_points,
            discipline_deduction=discipline_deduction,
            attendance_exceptions=attendance_exceptions,
            attendance_deduction=attendance_deduction,
            final_score=final,
            status="draft",
        )
        db.session.add(ev)
        created += 1

    safe_commit()
    flash(f"已生成 {created} 个班级的评价草稿，请审核后发布", "success")

    return redirect(url_for("ms.leaderboard", period_type=period_type, period_label=period_label,
                             grade_id=grade_id))


@ms_bp.route("/leaderboard/publish", methods=["POST"])
@require_role("ms_admin")
def publish_evaluation():
    """发布评价 — 计算排名并标记为已发布"""
    grade_id = request.form.get("grade_id", type=int)
    period_type = request.form.get("period_type")
    period_label = request.form.get("period_label")

    if not period_type or not period_label:
        flash("请选择评价周期", "danger")
        return redirect(url_for("ms.leaderboard"))

    # 查找草稿
    q = FlagEvaluation.query.filter_by(
        period_type=period_type, period_label=period_label, status="draft"
    )
    if grade_id:
        q = q.filter_by(grade_id=grade_id)

    drafts = q.all()
    if not drafts:
        flash("没有找到待发布的草稿", "danger")
        return redirect(url_for("ms.leaderboard"))

    # 按年级分组计算排名
    from itertools import groupby
    drafts.sort(key=lambda x: (x.grade_id, -x.final_score))
    for g_id, group in groupby(drafts, key=lambda x: x.grade_id):
        group_list = list(group)
        for rank, ev in enumerate(group_list, 1):
            ev.rank = rank
            ev.status = "published"
            ev.published_at = get_local_now()

    safe_commit()
    flash(f"已发布 {len(drafts)} 个班级的评价结果", "success")
    return redirect(url_for("ms.leaderboard", period_type=period_type, period_label=period_label,
                             grade_id=grade_id))


@ms_bp.route("/leaderboard/drafts")
@require_role("ms_admin")
def view_drafts():
    """查看待发布的草稿"""
    grade_id = request.args.get("grade_id", type=int)
    period_type = request.args.get("period_type", "week")
    period_label = request.args.get("period_label", "")

    grades = Grade.query.all()
    period_labels = _build_period_labels(get_local_now())

    if not period_label and period_labels.get(period_type):
        period_label = period_labels[period_type][0]["value"]

    q = FlagEvaluation.query.filter_by(
        period_type=period_type, period_label=period_label, status="draft"
    )
    if grade_id:
        q = q.filter_by(grade_id=grade_id)

    drafts = q.order_by(FlagEvaluation.final_score.desc()).all()
    evals_by_grade = {}
    for ev in drafts:
        evals_by_grade.setdefault(ev.grade_id, []).append(ev)

    return render_template("ms/leaderboard_drafts.html",
                           grades=grades, grade_filter=grade_id,
                           period_type=period_type, period_label=period_label,
                           period_labels=period_labels,
                           evals_by_grade=evals_by_grade)


@ms_bp.route("/leaderboard/api/periods")
@require_role("ms_admin")
def api_periods():
    """返回可选期间列表（AJAX用）"""
    return jsonify(_build_period_labels(get_local_now()))


def _parse_period_range(period_type, period_label):
    """解析期间标签为日期范围 (start_date, end_date)"""
    import calendar
    try:
        if period_type == "term":
            # 期末评价覆盖整个学期，返回一个极宽范围
            return date(2026, 2, 16), date(2026, 7, 10)

        elif period_type == "week":
            # period_label 是周一的 ISO 日期
            start = date.fromisoformat(period_label)
            end = start + timedelta(days=6)
            return start, end

        elif period_type == "month":
            # period_label 是月初的 ISO 日期
            start = date.fromisoformat(period_label)
            import calendar
            _, last_day = calendar.monthrange(start.year, start.month)
            end = date(start.year, start.month, last_day)
            return start, end
    except (ValueError, TypeError):
        return None, None


# ── 问题学生管理 — 全校建档 ──
@ms_bp.route("/problem-students")
@require_role("ms_admin")
def problem_list():
    page = request.args.get("page", 1, type=int)
    grade_filter = request.args.get("grade_id", type=int)
    level_filter = request.args.get("level", "")
    q = ProblemStudent.query
    if grade_filter:
        q = q.filter_by(grade_id=grade_filter)
    if level_filter:
        q = q.filter_by(level=level_filter)
    records = q.order_by(ProblemStudent.updated_at.desc()).paginate(page=page, per_page=20)
    grades = Grade.query.all()
    return render_template("ms/problem_list.html", records=records, grades=grades)


@ms_bp.route("/problem-students/create", methods=["GET", "POST"])
@require_role("ms_admin")
def create_problem():
    if request.method == "POST":
        student = Student.query.get(request.form["student_id"])
        if not student:
            flash("学生不存在", "danger")
            return redirect(url_for("ms.create_problem"))
        ps = ProblemStudent(
            student_id=student.id,
            class_id=student.class_id,
            grade_id=student.grade_id,
            category=request.form["category"],
            level=request.form["level"],
            description=request.form["description"],
            intervention=request.form.get("intervention", ""),
            created_by=session.get("user_id"),
        )
        db.session.add(ps)
        safe_commit()
        flash("问题学生已建档", "success")
        return redirect(url_for("ms.problem_list"))
    classes = Class.query.all()
    return render_template("ms/problem_create.html", classes=classes)


@ms_bp.route("/problem-students/<int:pid>")
@require_role("ms_admin")
def problem_detail(pid):
    ps = ProblemStudent.query.get_or_404(pid)
    tracks = ProblemTrack.query.filter_by(problem_id=pid).order_by(
        ProblemTrack.created_at.desc()).all()
    return render_template("ms/problem_detail.html", problem=ps, tracks=tracks)


@ms_bp.route("/problem-students/<int:pid>/track", methods=["POST"])
@require_role("ms_admin")
def add_track(pid):
    track = ProblemTrack(
        problem_id=pid,
        content=request.form["content"],
        created_by=session.get("user_id"),
    )
    db.session.add(track)
    safe_commit()
    flash("跟踪记录已添加", "success")
    return redirect(url_for("ms.problem_detail", pid=pid))


# ── 学生搜索 API ──
@ms_bp.route("/api/students/search")
@require_role("ms_admin", "grade_leader", "class_teacher")
def search_students():
    q = request.args.get("q", "")
    class_id = request.args.get("class_id", type=int)
    query = Student.query.filter(Student.name.contains(q))
    if class_id:
        query = query.filter_by(class_id=class_id)
    students = query.limit(20).all()
    return jsonify([{"id": s.id, "name": s.name, "class": s.class_.name if s.class_ else ""}
                    for s in students])


# ────────────────────────────────────────────
# 年级管理
# ────────────────────────────────────────────
@ms_bp.route("/grades")
@require_role("ms_admin")
def grade_manage():
    grades = Grade.query.order_by(Grade.sort_order).all()
    return render_template("ms/grade_manage.html", grades=grades)


@ms_bp.route("/grades/create", methods=["GET", "POST"])
@require_role("ms_admin")
def grade_create():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        sort_order = request.form.get("sort_order", 0, type=int)
        if not name:
            flash("年级名称不能为空", "warning")
            return redirect(url_for("ms.grade_manage"))
        if Grade.query.filter_by(name=name).first():
            flash("该年级已存在", "warning")
            return redirect(url_for("ms.grade_manage"))
        g = Grade(name=name, sort_order=sort_order)
        db.session.add(g)
        safe_commit()
        flash("年级已创建", "success")
        return redirect(url_for("ms.grade_manage"))
    return render_template("ms/grade_form.html", grade=None)


@ms_bp.route("/grades/<int:gid>/edit", methods=["GET", "POST"])
@require_role("ms_admin")
def grade_edit(gid):
    g = Grade.query.get_or_404(gid)
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        sort_order = request.form.get("sort_order", 0, type=int)
        if not name:
            flash("年级名称不能为空", "warning")
            return redirect(url_for("ms.grade_edit", gid=gid))
        exist = Grade.query.filter(Grade.name == name, Grade.id != gid).first()
        if exist:
            flash("该年级名称已被使用", "warning")
            return redirect(url_for("ms.grade_edit", gid=gid))
        g.name = name
        g.sort_order = sort_order
        safe_commit()
        flash("年级已更新", "success")
        return redirect(url_for("ms.grade_manage"))
    return render_template("ms/grade_form.html", grade=g)


@ms_bp.route("/grades/<int:gid>/delete", methods=["POST"])
@require_role("ms_admin")
def grade_delete(gid):
    g = Grade.query.get_or_404(gid)
    if g.classes.filter_by(is_active=True).count() > 0:
        flash("该年级下还有活跃班级，请先删除或停用班级", "danger")
        return redirect(url_for("ms.grade_manage"))
    g.is_active = False
    safe_commit()
    flash("年级已标记删除", "success")
    return redirect(url_for("ms.grade_manage"))


# ────────────────────────────────────────────
# 班级管理
# ────────────────────────────────────────────
@ms_bp.route("/classes")
@require_role("ms_admin")
def class_manage():
    grades = Grade.query.filter_by(is_active=True).order_by(Grade.sort_order).all()
    classes = Class.query.filter_by(is_active=True).order_by(Class.grade_id, Class.name).all()
    # 批量预加载学生人数 — 单次 GROUP BY 替代 N 次 COUNT
    cnt_map = dict(db.session.query(
        Student.class_id, func.count(Student.id)
    ).filter(
        Student.is_active == True,
        Student.class_id.in_([c.id for c in classes])
    ).group_by(Student.class_id).all())
    for c in classes:
        c.student_cnt = cnt_map.get(c.id, 0)
    return render_template("ms/class_manage.html", grades=grades, classes=classes)


@ms_bp.route("/classes/create", methods=["GET", "POST"])
@require_role("ms_admin")
def class_create():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        grade_id = request.form.get("grade_id", type=int)
        if not name or not grade_id:
            flash("班级名称和所属年级不能为空", "warning")
            return redirect(url_for("ms.class_manage"))
        if Class.query.filter_by(name=name, grade_id=grade_id).first():
            flash("该年级下已有同名班级", "warning")
            return redirect(url_for("ms.class_manage"))
        c = Class(name=name, grade_id=grade_id)
        db.session.add(c)
        safe_commit()
        flash("班级已创建", "success")
        return redirect(url_for("ms.class_manage"))
    grades = Grade.query.filter_by(is_active=True).order_by(Grade.sort_order).all()
    return render_template("ms/class_form.html", class_=None, grades=grades)


@ms_bp.route("/classes/<int:cid>/edit", methods=["GET", "POST"])
@require_role("ms_admin")
def class_edit(cid):
    c = Class.query.get_or_404(cid)
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        grade_id = request.form.get("grade_id", type=int)
        if not name or not grade_id:
            flash("班级名称和所属年级不能为空", "warning")
            return redirect(url_for("ms.class_edit", cid=cid))
        exist = Class.query.filter(
            Class.name == name, Class.grade_id == grade_id, Class.id != cid
        ).first()
        if exist:
            flash("该年级下已有同名班级", "warning")
            return redirect(url_for("ms.class_edit", cid=cid))
        c.name = name
        c.grade_id = grade_id
        safe_commit()
        flash("班级已更新", "success")
        return redirect(url_for("ms.class_manage"))
    grades = Grade.query.filter_by(is_active=True).order_by(Grade.sort_order).all()
    return render_template("ms/class_form.html", class_=c, grades=grades)


@ms_bp.route("/classes/<int:cid>/delete", methods=["POST"])
@require_role("ms_admin")
def class_delete(cid):
    c = Class.query.get_or_404(cid)
    cnt = Student.query.filter_by(class_id=cid, is_active=True).count()
    if cnt > 0:
        flash("该班级还有 %d 名活跃学生，请先转移或删除学生" % cnt, "danger")
        return redirect(url_for("ms.class_manage"))
    c.is_active = False
    safe_commit()
    flash("班级已标记删除", "success")
    return redirect(url_for("ms.class_manage"))


# ────────────────────────────────────────────
# 科目管理
# ────────────────────────────────────────────
@ms_bp.route("/subjects")
@require_role("ms_admin")
def subject_manage():
    subjects = Subject.query.order_by(Subject.sort_order).all()
    return render_template("ms/subject_manage.html", subjects=subjects)


@ms_bp.route("/subjects/create", methods=["GET", "POST"])
@require_role("ms_admin")
def subject_create():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        full_score = request.form.get("full_score", 100, type=float)
        pass_score = request.form.get("pass_score", 60, type=float)
        sort_order = request.form.get("sort_order", 0, type=int)
        if not name:
            flash("科目名称不能为空", "warning")
            return redirect(url_for("ms.subject_manage"))
        if Subject.query.filter_by(name=name).first():
            flash("该科目已存在", "warning")
            return redirect(url_for("ms.subject_manage"))
        s = Subject(name=name, full_score=full_score,
                     pass_score=pass_score, sort_order=sort_order)
        db.session.add(s)
        safe_commit()
        flash("科目已创建", "success")
        return redirect(url_for("ms.subject_manage"))
    return render_template("ms/subject_form.html", subject=None)


@ms_bp.route("/subjects/<int:sid>/edit", methods=["GET", "POST"])
@require_role("ms_admin")
def subject_edit(sid):
    s = Subject.query.get_or_404(sid)
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        full_score = request.form.get("full_score", 100, type=float)
        pass_score = request.form.get("pass_score", 60, type=float)
        sort_order = request.form.get("sort_order", 0, type=int)
        if not name:
            flash("科目名称不能为空", "warning")
            return redirect(url_for("ms.subject_edit", sid=sid))
        exist = Subject.query.filter(Subject.name == name, Subject.id != sid).first()
        if exist:
            flash("该科目名称已被使用", "warning")
            return redirect(url_for("ms.subject_edit", sid=sid))
        s.name = name
        s.full_score = full_score
        s.pass_score = pass_score
        s.sort_order = sort_order
        safe_commit()
        flash("科目已更新", "success")
        return redirect(url_for("ms.subject_manage"))
    return render_template("ms/subject_form.html", subject=s)


@ms_bp.route("/subjects/<int:sid>/delete", methods=["POST"])
@require_role("ms_admin")
def subject_delete(sid):
    s = Subject.query.get_or_404(sid)
    s.is_active = False
    safe_commit()
    flash("科目已标记删除", "success")
    return redirect(url_for("ms.subject_manage"))


# ── 考勤总览（德育处全局视图） ──
@ms_bp.route("/attendance")
@require_role("ms_admin")
def attendance_overview():
    """德育处全局考勤历史：按年级/班级/日期范围筛选，支持导出"""
    grade_id = request.args.get("grade_id", type=int)
    class_id = request.args.get("class_id", type=int)
    start_date = request.args.get("start_date", "")
    end_date = request.args.get("end_date", "")
    export = request.args.get("export", "")

    today = date.today()
    grades = Grade.query.filter_by(is_active=True).order_by(Grade.sort_order).all()
    classes = Class.query.filter_by(is_active=True).order_by(Class.grade_id, Class.name).all()

    # 默认今天
    if not start_date:
        start_date = today.strftime("%Y-%m-%d")
    if not end_date:
        end_date = today.strftime("%Y-%m-%d")

    q = Attendance.query
    if grade_id:
        q = q.filter(Attendance.grade_id == grade_id)
    if class_id:
        q = q.filter(Attendance.class_id == class_id)

    try:
        sd = date.fromisoformat(start_date)
        ed = date.fromisoformat(end_date)
    except ValueError:
        sd = today
        ed = today
    q = q.filter(Attendance.record_date >= sd, Attendance.record_date <= ed)

    # 导出
    if export == "excel":
        import io
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "考勤记录"
        ws.append(["日期", "年级", "班级", "学号", "姓名", "状态", "备注"])
        records = q.order_by(Attendance.record_date.desc(), Attendance.grade_id,
                              Attendance.class_id, Attendance.student_id).all()
        for r in records:
            stu = Student.query.get(r.student_id) if r.student_id else None
            cls = Class.query.get(r.class_id) if r.class_id else None
            g = Grade.query.get(r.grade_id) if r.grade_id else None
            status_map = {"present": "出勤", "late": "迟到", "early": "早退",
                          "absent": "缺勤", "leave": "请假"}
            ws.append([
                str(r.record_date), g.name if g else "", cls.name if cls else "",
                stu.student_no if stu else "", stu.name if stu else "",
                status_map.get(r.status, r.status), r.note or ""
            ])
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        from flask import send_file
        return send_file(output, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                         as_attachment=True, download_name=f"attendance_{start_date}_{end_date}.xlsx")

    # 按班级汇总统计
    summary_q = db.session.query(
        Attendance.class_id, Class.name,
        func.count().label("total"),
        func.sum(db.case((Attendance.status == "present", 1), else_=0)).label("present_cnt"),
        func.sum(db.case((Attendance.status == "late", 1), else_=0)).label("late_cnt"),
        func.sum(db.case((Attendance.status == "absent", 1), else_=0)).label("absent_cnt"),
        func.sum(db.case((Attendance.status == "leave", 1), else_=0)).label("leave_cnt"),
    ).join(Class, Attendance.class_id == Class.id)

    summary_q = summary_q.filter(Attendance.record_date >= sd, Attendance.record_date <= ed)
    if grade_id:
        summary_q = summary_q.filter(Attendance.grade_id == grade_id)
    if class_id:
        summary_q = summary_q.filter(Attendance.class_id == class_id)
    summary_q = summary_q.group_by(Attendance.class_id, Class.name).order_by(Class.grade_id, Class.name)
    summary = summary_q.all()

    # 分页明细
    page = request.args.get("page", 1, type=int)
    per_page = 50
    records = q.order_by(Attendance.record_date.desc(), Attendance.class_id).paginate(
        page=page, per_page=per_page, error_out=False)

    # 为每条记录附加学生姓名
    student_ids = list(set(r.student_id for r in records.items if r.student_id))
    students_map = {}
    if student_ids:
        for s in Student.query.filter(Student.id.in_(student_ids)).all():
            students_map[s.id] = s

    return render_template("ms/attendance.html",
                           grades=grades, classes=classes,
                           summary=summary, records=records,
                           students_map=students_map,
                           grade_filter=grade_id, class_filter=class_id,
                           start_date=start_date, end_date=end_date)
