"""五翼评价 — 评分/勋章/档案/排名（教师/学生/家长共用）"""
from flask import Blueprint, render_template, request, jsonify, session
from models import db, Student, Class, WingsScore, Grade
from decorators import login_required, scope_query
from datetime import datetime
from sqlalchemy import func
from sqlalchemy.orm import joinedload
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

    if not rows:
        return []

    # 批量预加载学生（消除 Student.query.get N+1）
    student_ids = [r.student_id for r in rows]
    student_map = {s.id: s for s in Student.query.options(
        joinedload(Student.class_)
    ).filter(Student.id.in_(student_ids)).all()}

    # 批量预计算各维度均分（一次性 GROUP BY，消除 5N 次查询）
    dim_q = db.session.query(
        WingsScore.student_id,
        WingsScore.dimension,
        func.avg(WingsScore.score).label("avg"),
    )
    for f in filters:
        dim_q = dim_q.filter(f)
    dim_q = dim_q.filter(WingsScore.student_id.in_(student_ids))
    dim_q = dim_q.group_by(WingsScore.student_id, WingsScore.dimension)
    dim_rows = dim_q.all()
    dim_map = {}
    for dr in dim_rows:
        dim_map.setdefault(dr.student_id, {})[dr.dimension] = round(float(dr.avg), 1) if dr.avg else 0

    results = []
    for row in rows:
        student = student_map.get(row.student_id)
        if not student:
            continue
        dims = dim_map.get(row.student_id, {})
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
    # 批量预加载 recent_scores 的学生（模板中访问 s.student.name 会触发懒加载）
    if recent_scores:
        rs_sids = list({s.student_id for s in recent_scores})
        rs_stu_map = {s.id: s for s in Student.query.filter(Student.id.in_(rs_sids)).all()}
        # 将预加载的学生附加到对象上，模板可直接访问
        for s in recent_scores:
            s._student = rs_stu_map.get(s.student_id)

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

    # 按班级聚合各维度均分（批量查询，消除 7C 次 N+1）
    classes = Class.query.filter_by(grade_id=grade_id, is_active=True).all()
    class_ids = [c.id for c in classes]
    class_map = {c.id: c for c in classes}

    # 一次性查所有班级所有维度的均分
    dim_rows = db.session.query(
        WingsScore.class_id,
        WingsScore.dimension,
        func.avg(WingsScore.score).label("avg"),
    ).filter(WingsScore.class_id.in_(class_ids)).group_by(
        WingsScore.class_id, WingsScore.dimension
    ).all()
    class_dim_avgs = {}
    for dr in dim_rows:
        class_dim_avgs.setdefault(dr.class_id, {})[dr.dimension] = round(float(dr.avg), 1) if dr.avg else 0

    # 一次性查所有班级总均分和计数
    total_rows = db.session.query(
        WingsScore.class_id,
        func.avg(WingsScore.score).label("avg"),
        func.count(WingsScore.id).label("cnt"),
    ).filter(WingsScore.class_id.in_(class_ids)).group_by(WingsScore.class_id).all()
    total_map = {r.class_id: {"avg": round(float(r.avg), 1) if r.avg else 0, "count": r.cnt} for r in total_rows}

    # 组装 rankings
    rankings = {}
    for c in classes:
        rankings[c.name] = class_dim_avgs.get(c.id, {})

    # 总均分排名
    overall = []
    for c in classes:
        info = total_map.get(c.id, {"avg": 0, "count": 0})
        overall.append({
            "name": c.name,
            "avg": info["avg"],
            "count": info["count"],
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
    all_winner_ids = []
    medal_rows_map = {}  # {medal_key: [(student_id, avg)]}
    for mt in medal_types:
        if mt["dim"]:
            q = db.session.query(
                WingsScore.student_id,
                func.avg(WingsScore.score).label("avg"),
            ).filter(WingsScore.dimension == mt["dim"])
            if grade_id:
                q = q.filter(WingsScore.grade_id == grade_id)
        else:
            q = db.session.query(
                WingsScore.student_id,
                func.avg(WingsScore.score).label("avg"),
            )
            if grade_id:
                q = q.filter(WingsScore.grade_id == grade_id)
        rows = q.group_by(WingsScore.student_id).order_by(
            func.avg(WingsScore.score).desc()
        ).limit(5).all()
        medal_rows_map[mt["key"]] = rows
        all_winner_ids.extend(r.student_id for r in rows)

    # 批量预加载获奖学生（含班级）
    winner_map = {}
    if all_winner_ids:
        winner_map = {s.id: s for s in Student.query.options(
            joinedload(Student.class_)
        ).filter(Student.id.in_(all_winner_ids)).all()}

    for mt in medal_types:
        winners = []
        for row in medal_rows_map[mt["key"]]:
            student = winner_map.get(row.student_id)
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

    students_page = Student.query.filter(*filters).options(
        joinedload(Student.class_)
    ).order_by(
        Student.grade_id, Student.class_id, Student.student_no
    ).paginate(page=page, per_page=30)

    # 批量查询每个学生的总分和计数（消除 2*30 次 N+1）
    page_sids = [s.id for s in students_page.items]
    stats_rows = db.session.query(
        WingsScore.student_id,
        func.avg(WingsScore.score).label("avg"),
        func.count(WingsScore.id).label("cnt"),
    ).filter(WingsScore.student_id.in_(page_sids)).group_by(WingsScore.student_id).all()
    stats_map = {r.student_id: (float(r.avg), r.cnt) for r in stats_rows}

    student_summaries = []
    for s in students_page.items:
        avg, count = stats_map.get(s.id, (0, 0))
        student_summaries.append({
            "student": s,
            "avg": round(avg, 1) if avg else 0,
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
