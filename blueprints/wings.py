"""五翼评价 — 评分/勋章/档案/排名（教师/学生/家长共用）"""
from flask import Blueprint, render_template, request, jsonify, session
from models import db, Student, Class, WingsScore, Grade
from decorators import login_required, scope_query
from datetime import datetime
from sqlalchemy import func
from utils.db_utils import safe_commit

# 声呐事件总线（评分实时广播）
from utils.sonar_bus import publish_score

wings_bp = Blueprint("wings", __name__)

DIMENSIONS = ["德", "智", "体", "美", "劳"]


@wings_bp.before_request
@login_required
def check_login():
    pass


# ── 辅助：计算五翼各维度平均分 ──
def _dimension_averages(query_filter=None):
    """返回 {dim: avg_score}"""
    q = db.session.query(
        WingsScore.dimension,
        func.avg(WingsScore.score).label("avg_score"),
        func.count(WingsScore.id).label("cnt"),
    )
    if query_filter is not None:
        q = q.filter(query_filter)
    rows = q.group_by(WingsScore.dimension).all()
    return {r.dimension: round(float(r.avg_score), 1) for r in rows}


def _student_totals(class_id=None, grade_id=None, limit=None):
    """返回按总分排序的学生列表 [(student, {dim: avg, total: float}), ...]"""
    filters = []
    if class_id:
        filters.append(WingsScore.class_id == class_id)
    if grade_id:
        filters.append(WingsScore.grade_id == grade_id)

    q = db.session.query(
        WingsScore.student_id,
        func.avg(WingsScore.score).label("total_avg"),
        func.count(WingsScore.id).label("cnt"),
    )
    for f in filters:
        q = q.filter(f)
    q = q.group_by(WingsScore.student_id).order_by(func.avg(WingsScore.score).desc())
    if limit:
        q = q.limit(limit)
    rows = q.all()

    results = []
    for row in rows:
        student = Student.query.get(row.student_id)
        if not student:
            continue
        dims = {}
        for d in DIMENSIONS:
            dq = db.session.query(func.avg(WingsScore.score)).filter(
                WingsScore.student_id == row.student_id,
                WingsScore.dimension == d,
            )
            for f in filters:
                dq = dq.filter(f)
            avg = dq.scalar()
            dims[d] = round(float(avg), 1) if avg else 0
        results.append((student, dims, round(float(row.total_avg), 1)))
    return results


# ── 五翼仪表盘 ──
@wings_bp.route("/")
def dashboard():
    grade_id = session.get("grade_id")
    class_id = session.get("class_id")

    # 数据范围：根据角色缩小
    if session.get("role") == "class_teacher" and class_id:
        base_filter = WingsScore.class_id == class_id
        student_count = Student.query.filter_by(class_id=class_id, is_active=True).count()
    elif session.get("role") == "grade_leader" and grade_id:
        base_filter = WingsScore.grade_id == grade_id
        student_count = Student.query.filter_by(grade_id=grade_id, is_active=True).count()
    else:
        base_filter = None
        student_count = Student.query.filter_by(is_active=True).count()

    total_scores = WingsScore.query
    if base_filter is not None:
        total_scores = total_scores.filter(base_filter)
    score_count = total_scores.count()
    dim_avgs = _dimension_averages(base_filter)
    # 近期评分
    recent_q = WingsScore.query.order_by(WingsScore.created_at.desc())
    if base_filter is not None:
        recent_q = recent_q.filter(base_filter)
    recent_scores = recent_q.limit(20).all()

    # 维度分布数据（供图表）
    dim_dist = {d: dim_avgs.get(d, 0) for d in DIMENSIONS}

    return render_template("wings/dashboard.html", dimensions=DIMENSIONS,
                           score_count=score_count, student_count=student_count,
                           dim_avgs=dim_avgs, dim_dist=dim_dist,
                           recent_scores=recent_scores)


# ── 评分入口 ──
@wings_bp.route("/score")
def score_page():
    scorer_type = request.args.get("type", "teacher")
    return render_template("wings/scoring.html", scorer_type=scorer_type,
                           dimensions=DIMENSIONS)


@wings_bp.route("/score/teacher")
def score_teacher():
    class_id = session.get("class_id")
    students = []
    if class_id:
        students = Student.query.filter_by(class_id=class_id, is_active=True).all()
    return render_template("wings/scoring_teacher.html", students=students,
                           dimensions=DIMENSIONS)


@wings_bp.route("/score/parent")
def score_parent():
    sid = session.get("bound_student_id")
    student = Student.query.get(sid) if sid else None
    return render_template("wings/scoring_parent.html", student=student,
                           dimensions=DIMENSIONS)


@wings_bp.route("/score/student")
def score_student():
    sid = session.get("student_id")
    student = Student.query.get(sid) if sid else None
    classmates = []
    if student:
        classmates = Student.query.filter(
            Student.class_id == student.class_id,
            Student.id != student.id,
            Student.is_active == True,
        ).all()
    return render_template("wings/scoring_student.html", student=student,
                           classmates=classmates, dimensions=DIMENSIONS)


# ── 保存评分 API ──
@wings_bp.route("/api/score/save", methods=["POST"])
def save_score():
    data = request.get_json()
    score = WingsScore(
        student_id=data["student_id"],
        class_id=data.get("class_id", 0),
        grade_id=data.get("grade_id", 0),
        dimension=data["dimension"],
        score=data["score"],
        scorer_type=data["scorer_type"],
        scorer_id=session.get("user_id"),
        semester=data.get("semester", ""),
    )
    db.session.add(score)
    db.session.flush()  # 确保 score.id 可用
    safe_commit()
    # ── 声呐广播：五翼评分实时推送 ──
    try:
        publish_score(score, session.get("display_name", "系统"))
    except Exception:
        pass
    return jsonify({"ok": True, "id": score.id})


# ── 班级排名 ──
@wings_bp.route("/class-ranking")
def class_ranking():
    grade_id = request.args.get("grade_id", type=int) or session.get("grade_id")
    dimension = request.args.get("dimension", "")

    if not grade_id:
        # 没有年级筛选，显示全部
        grades = Grade.query.order_by(Grade.sort_order).all()
        return render_template("wings/class_ranking.html", dimensions=DIMENSIONS,
                               grades=grades, grade_filter=None, dim_filter=dimension,
                               rankings=[], overall=[])

    # 按班级聚合各维度均分
    classes = Class.query.filter_by(grade_id=grade_id, is_active=True).all()
    rankings = {}  # {class_name: {dim: avg}}
    for c in classes:
        rankings[c.name] = {}
        for d in DIMENSIONS:
            avg = db.session.query(func.avg(WingsScore.score)).filter(
                WingsScore.class_id == c.id,
                WingsScore.dimension == d,
            ).scalar()
            rankings[c.name][d] = round(float(avg), 1) if avg else 0

    # 总均分排名
    overall = []
    for c in classes:
        avg = db.session.query(func.avg(WingsScore.score)).filter(
            WingsScore.class_id == c.id,
        ).scalar()
        overall.append({
            "name": c.name,
            "avg": round(float(avg), 1) if avg else 0,
            "count": WingsScore.query.filter_by(class_id=c.id).count(),
        })
    overall.sort(key=lambda x: x["avg"], reverse=True)

    grades = Grade.query.order_by(Grade.sort_order).all()
    return render_template("wings/class_ranking.html", dimensions=DIMENSIONS,
                           grades=grades, grade_filter=grade_id, dim_filter=dimension,
                           rankings=rankings, overall=overall)


# ── 勋章墙 ──
@wings_bp.route("/medals")
def medals():
    grade_id = request.args.get("grade_id", type=int) or session.get("grade_id")

    # 定义勋章类型
    medal_types = [
        {"key": "de", "name": "品德之星", "dim": "德", "icon": "bi-heart", "color": "danger"},
        {"key": "zhi", "name": "智慧之星", "dim": "智", "icon": "bi-lightbulb", "color": "primary"},
        {"key": "ti", "name": "体育之星", "dim": "体", "icon": "bi-trophy", "color": "success"},
        {"key": "mei", "name": "艺术之星", "dim": "美", "icon": "bi-palette", "color": "warning"},
        {"key": "lao", "name": "劳动之星", "dim": "劳", "icon": "bi-tools", "color": "info"},
        {"key": "all", "name": "全能之星", "dim": None, "icon": "bi-star", "color": "dark"},
    ]

    results = {}
    for mt in medal_types:
        if mt["dim"]:
            # 单维度Top5
            q = db.session.query(
                WingsScore.student_id,
                func.avg(WingsScore.score).label("avg"),
            ).filter(WingsScore.dimension == mt["dim"])
            if grade_id:
                q = q.filter(WingsScore.grade_id == grade_id)
            rows = q.group_by(WingsScore.student_id).order_by(
                func.avg(WingsScore.score).desc()
            ).limit(5).all()
        else:
            # 全能Top5
            q = db.session.query(
                WingsScore.student_id,
                func.avg(WingsScore.score).label("avg"),
            )
            if grade_id:
                q = q.filter(WingsScore.grade_id == grade_id)
            rows = q.group_by(WingsScore.student_id).order_by(
                func.avg(WingsScore.score).desc()
            ).limit(5).all()

        winners = []
        for row in rows:
            student = Student.query.get(row.student_id)
            if student:
                winners.append({
                    "name": student.name,
                    "class": student.class_.name if student.class_ else "",
                    "avg": round(float(row.avg), 1),
                })
        results[mt["key"]] = winners

    grades = Grade.query.order_by(Grade.sort_order).all()
    return render_template("wings/medals.html", medal_types=medal_types,
                           results=results, grades=grades, grade_filter=grade_id)


# ── 成长档案 ──
@wings_bp.route("/portfolio")
def portfolio():
    grade_id = request.args.get("grade_id", type=int) or session.get("grade_id")
    class_id = request.args.get("class_id", type=int) or session.get("class_id")
    page = request.args.get("page", 1, type=int)

    filters = [Student.is_active == True]
    if grade_id:
        filters.append(Student.grade_id == grade_id)
    if class_id:
        filters.append(Student.class_id == class_id)

    students_page = Student.query.filter(*filters).order_by(
        Student.grade_id, Student.class_id, Student.student_no
    ).paginate(page=page, per_page=30)

    # 查每个学生的总分
    student_summaries = []
    for s in students_page.items:
        avg = db.session.query(func.avg(WingsScore.score)).filter(
            WingsScore.student_id == s.id
        ).scalar()
        count = WingsScore.query.filter_by(student_id=s.id).count()
        student_summaries.append({
            "student": s,
            "avg": round(float(avg), 1) if avg else 0,
            "count": count,
        })

    grades = Grade.query.order_by(Grade.sort_order).all()
    classes = []
    if grade_id:
        classes = Class.query.filter_by(grade_id=grade_id, is_active=True).all()

    return render_template("wings/portfolio.html", students_page=students_page,
                           student_summaries=student_summaries,
                           grades=grades, classes=classes,
                           grade_filter=grade_id, class_filter=class_id)


@wings_bp.route("/portfolio/<int:sid>")
def portfolio_detail(sid):
    student = Student.query.get_or_404(sid)
    scores = WingsScore.query.filter_by(student_id=sid).order_by(
        WingsScore.created_at.desc()).all()
    # 维度均值
    dim_avgs = {}
    for d in DIMENSIONS:
        avg = db.session.query(func.avg(WingsScore.score)).filter(
            WingsScore.student_id == sid,
            WingsScore.dimension == d,
        ).scalar()
        dim_avgs[d] = round(float(avg), 1) if avg else 0
    total_avg = db.session.query(func.avg(WingsScore.score)).filter(
        WingsScore.student_id == sid
    ).scalar()
    total_avg = round(float(total_avg), 1) if total_avg else 0
    return render_template("wings/portfolio_detail.html", student=student,
                           scores=scores, dim_avgs=dim_avgs, total_avg=total_avg,
                           dimensions=DIMENSIONS)


# ── 数据分析 ──
@wings_bp.route("/analysis")
def analysis():
    grade_id = request.args.get("grade_id", type=int) or session.get("grade_id")
    class_id = request.args.get("class_id", type=int) or session.get("class_id")

    filters = []
    if grade_id:
        filters.append(WingsScore.grade_id == grade_id)
    if class_id:
        filters.append(WingsScore.class_id == class_id)

    # 各维度均分
    dim_avgs = _dimension_averages(db.and_(*filters) if filters else None)

    # 分数段分布
    dist_data = {}
    for d in DIMENSIONS:
        dq = db.session.query(WingsScore.score).filter(WingsScore.dimension == d)
        for f in filters:
            dq = dq.filter(f)
        scores = [row[0] for row in dq.all()]
        buckets = {"0-2": 0, "2-4": 0, "4-6": 0, "6-8": 0, "8-10": 0}
        for s in scores:
            if s < 2: buckets["0-2"] += 1
            elif s < 4: buckets["2-4"] += 1
            elif s < 6: buckets["4-6"] += 1
            elif s < 8: buckets["6-8"] += 1
            else: buckets["8-10"] += 1
        dist_data[d] = buckets

    # 评分来源占比
    source_counts = {}
    sq = db.session.query(
        WingsScore.scorer_type, func.count(WingsScore.id)
    )
    for f in filters:
        sq = sq.filter(f)
    for row in sq.group_by(WingsScore.scorer_type).all():
        label = {"teacher": "教师", "parent": "家长", "peer": "学生互评", "self": "自评"}.get(row[0], row[0])
        source_counts[label] = row[1]

    # 近期趋势（最近7天各维度日均分）
    trend_data = {}
    from datetime import date, timedelta
    today = date.today()
    for d in DIMENSIONS:
        trend_data[d] = []
        for i in range(6, -1, -1):
            day = today - timedelta(days=i)
            tq = db.session.query(func.avg(WingsScore.score)).filter(
                WingsScore.dimension == d,
                func.date(WingsScore.created_at) == day,
            )
            for f in filters:
                tq = tq.filter(f)
            avg = tq.scalar()
            trend_data[d].append({
                "date": day.strftime("%m-%d"),
                "avg": round(float(avg), 1) if avg else 0,
            })

    grades = Grade.query.order_by(Grade.sort_order).all()
    classes = []
    if grade_id:
        classes = Class.query.filter_by(grade_id=grade_id, is_active=True).all()

    return render_template("wings/analysis.html", dimensions=DIMENSIONS,
                           dim_avgs=dim_avgs, dist_data=dist_data,
                           source_counts=source_counts, trend_data=trend_data,
                           grades=grades, classes=classes,
                           grade_filter=grade_id, class_filter=class_id)
