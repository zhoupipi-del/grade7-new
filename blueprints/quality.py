"""综合素质评价 — 指标管理/多角色评分/报告分析（跨角色共用）"""
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify, current_app
from models import db, User, Student, Class, Grade, QualityIndicator, QualityScore
from decorators import login_required, require_role, require_permission
from datetime import datetime, timezone, timedelta
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from utils.db_utils import safe_commit

# 东八区时区工具（对齐 ms.py / class_.py 标准）
CST = timezone(timedelta(hours=8))


def get_local_now():
    """获取当前国内标准时间"""
    return datetime.now(CST)

quality_bp = Blueprint("quality", __name__)


@quality_bp.before_request
@login_required
@require_role("ms_admin", "grade_leader", "class_teacher")
def check_role():
    pass

# ── 维度常量 ──
DIMENSIONS = [
    {"key": "moral", "name": "思想品德", "icon": "bi-heart", "color": "danger"},
    {"key": "academic", "name": "学业水平", "icon": "bi-book", "color": "primary"},
    {"key": "health", "name": "身心健康", "icon": "bi-heart-pulse", "color": "success"},
    {"key": "art", "name": "艺术素养", "icon": "bi-palette", "color": "warning"},
    {"key": "social", "name": "社会实践", "icon": "bi-people", "color": "info"},
]

DIMENSION_KEYS = [d["key"] for d in DIMENSIONS]
DIMENSION_NAMES = {d["key"]: d["name"] for d in DIMENSIONS}

# ── 一级维度权重配置（五育均衡）──
# 可通过 SystemConfig 覆盖，默认值体现德育优先、五育并举
DIMENSION_WEIGHTS = {
    "moral": 0.25,     # 思想品德 25%
    "academic": 0.25,  # 学业水平 25%
    "health": 0.20,    # 身心健康 20%
    "art": 0.15,       # 艺术素养 15%
    "social": 0.15,    # 社会实践 15%
}

# 平衡补偿系数：当某维度分 > 其他维度均值 × BALANCE_THRESHOLD 时触发惩罚
BALANCE_THRESHOLD = 1.5   # 触发阈值
BALANCE_PENALTY = 0.85    # 惩罚系数

# 当前学期（简单取当前年月）
def _current_semester():
    now = get_local_now()  # 修复：废除 utcnow()，统一东八区时间
    y = now.year
    m = now.month
    if m >= 9:
        return f"{y}-{y+1}-1"
    elif m >= 2:
        return f"{y-1}-{y}-2"
    else:
        return f"{y-1}-{y}-2"


def _calculate_balanced_score(stu_id, semester, scorer_type="teacher",
                                indicators_by_dim=None, scores_by_student=None):
    """加权平衡算法 — 核心评分函数
    三步计算：
      1. 维度内归一化：各二级指标权重归一化到1.0，计算加权维度分
      2. 平衡补偿：若某维度分 > 其他维度均值×1.5，施加0.85惩罚系数
      3. 一级维度加权：五育维度按配置权重求和得最终总分

    可选参数 indicators_by_dim / scores_by_student 用于批量预加载场景，
    传入时可将函数内 SQL 查询降为 O(1) 内存查找，不传则走原版查询（向后兼容）。

    返回: {
        "dim_scores": {moral: float, ...},      # 各维度原始分
        "balanced_scores": {moral: float, ...},  # 平衡补偿后的维度分
        "total": float,                          # 最终总分
        "penalized": [dim_key, ...],             # 被惩罚的维度
    }
    """
    from models import QualityIndicator, QualityScore

    # 1) 维度内归一化加权
    raw_dim_scores = {}
    for d_key in DIMENSION_KEYS:
        # 🚀 缓存分支 1：批量预加载指标（消除 N+1 来源 1）
        if indicators_by_dim is not None:
            subs = indicators_by_dim.get(d_key, [])
        else:
            subs = QualityIndicator.query.filter(
                QualityIndicator.parent_id > 0,
                QualityIndicator.dimension == d_key,
                QualityIndicator.is_active == True,
            ).all()
        if not subs:
            raw_dim_scores[d_key] = 0.0
            continue

        # 归一化：所有权重除以总和
        total_weight = sum(s.weight for s in subs)
        if total_weight <= 0:
            raw_dim_scores[d_key] = 0.0
            continue

        dim_total = 0.0
        for sub in subs:
            # 🚀 缓存分支 2：批量预加载评分记录（消除 N+1 来源 2）
            if scores_by_student is not None:
                stu_scores = scores_by_student.get(stu_id, {})
                qs = stu_scores.get((sub.id, scorer_type))
            else:
                qs = QualityScore.query.filter(
                    QualityScore.student_id == stu_id,
                    QualityScore.indicator_id == sub.id,
                    QualityScore.scorer_type == scorer_type,
                    QualityScore.semester == semester,
                ).first()
            if qs:
                normalized_weight = sub.weight / total_weight
                dim_total += qs.score * normalized_weight

        raw_dim_scores[d_key] = round(dim_total, 1)

    # 2) 平衡补偿 — 防止"一维独大"
    balanced_scores = dict(raw_dim_scores)
    penalized = []
    non_zero = [v for v in raw_dim_scores.values() if v > 0]
    if len(non_zero) >= 2:
        avg_score = sum(non_zero) / len(non_zero)
        for d_key, score in balanced_scores.items():
            if score > avg_score * BALANCE_THRESHOLD:
                balanced_scores[d_key] = round(score * BALANCE_PENALTY, 1)
                penalized.append(d_key)

    # 3) 一级维度加权求和
    total = 0.0
    for d_key in DIMENSION_KEYS:
        weight = DIMENSION_WEIGHTS.get(d_key, 0.20)
        total += balanced_scores[d_key] * weight

    return {
        "dim_scores": raw_dim_scores,
        "balanced_scores": balanced_scores,
        "total": round(total, 1),
        "penalized": penalized,
    }


@quality_bp.before_request
@login_required
def check_login():
    pass


# ══════════════════════════════════════════════════════════════
#  种子数据
# ══════════════════════════════════════════════════════════════

def seed_indicators():
    """如果 QualityIndicator 表为空，插入默认五维评价指标"""
    if QualityIndicator.query.first() is not None:
        return

    seed_data = [
        # Dimension 1 - 思想品德 (moral)
        ("思想品德", "moral", 0, None),
        ("爱国守法", "moral", 1, 0.30),
        ("诚实守信", "moral", 1, 0.25),
        ("责任担当", "moral", 1, 0.25),
        ("文明礼仪", "moral", 1, 0.20),
        # Dimension 2 - 学业水平 (academic)
        ("学业水平", "academic", 0, None),
        ("学习态度", "academic", 1, 0.30),
        ("学业成绩", "academic", 1, 0.30),
        ("创新思维", "academic", 1, 0.20),
        ("实践能力", "academic", 1, 0.20),
        # Dimension 3 - 身心健康 (health)
        ("身心健康", "health", 0, None),
        ("身体素质", "health", 1, 0.30),
        ("心理健康", "health", 1, 0.30),
        ("生活习惯", "health", 1, 0.20),
        ("安全意识", "health", 1, 0.20),
        # Dimension 4 - 艺术素养 (art)
        ("艺术素养", "art", 0, None),
        ("审美感知", "art", 1, 0.30),
        ("艺术表现", "art", 1, 0.35),
        ("文化理解", "art", 1, 0.35),
        # Dimension 5 - 社会实践 (social)
        ("社会实践", "social", 0, None),
        ("社会实践", "social", 1, 0.35),
        ("志愿服务", "social", 1, 0.35),
        ("劳动技能", "social", 1, 0.30),
    ]

    sort = 0
    for name, dimension, parent_id, weight in seed_data:
        indicator = QualityIndicator(
            name=name,
            parent_id=parent_id,
            dimension=dimension,
            weight=weight if weight else 0.0,
            max_score=100.0,
            sort_order=sort,
            is_active=True,
        )
        db.session.add(indicator)
        sort += 1

    safe_commit()
    print("[quality] 已初始化默认五维评价指标")


# ══════════════════════════════════════════════════════════════
#  公共：模块首页 Dashboard
# ══════════════════════════════════════════════════════════════

@quality_bp.route("/")
def dashboard():
    role = session.get("role", "")
    my_class_id = session.get("class_id")
    # 统计概览数据 — 班主任只能看本班
    indicator_count = QualityIndicator.query.filter_by(is_active=True).count()
    if role == "class_teacher" and my_class_id:
        student_count = Student.query.filter_by(class_id=my_class_id, is_active=True).count()
        score_count = QualityScore.query.filter_by(class_id=my_class_id).count()
    else:
        student_count = Student.query.filter_by(is_active=True).count()
        score_count = QualityScore.query.count()

    return render_template("quality/dashboard.html",
                           role=role, DIMENSIONS=DIMENSIONS,
                           indicator_count=indicator_count,
                           score_count=score_count,
                           student_count=student_count)


# ══════════════════════════════════════════════════════════════
#  德育处/管理员端：指标管理
# ══════════════════════════════════════════════════════════════

@quality_bp.route("/indicators")
@require_role("ms_admin", "grade_leader")
def indicator_list():
    seed_indicators()
    indicators = QualityIndicator.query.order_by(
        QualityIndicator.sort_order, QualityIndicator.id
    ).all()

    # 按 dimension 分组
    grouped = {}
    for ind in indicators:
        key = ind.dimension or "other"
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(ind)

    # 一级指标列表（parent_id==0）
    level1 = [ind for ind in indicators if ind.parent_id == 0]
    # 二级指标按父级索引
    level2_by_parent = {}
    for ind in indicators:
        if ind.parent_id > 0:
            level2_by_parent.setdefault(ind.parent_id, []).append(ind)

    return render_template("quality/indicators.html",
                           indicators=indicators, grouped=grouped,
                           level1=level1, level2_by_parent=level2_by_parent,
                           DIMENSION_NAMES=DIMENSION_NAMES)


@quality_bp.route("/indicators/create", methods=["GET", "POST"])
@require_role("ms_admin")
def indicator_create():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        dimension = request.form.get("dimension", "")
        parent_id = int(request.form.get("parent_id", "0") or "0")
        weight = float(request.form.get("weight", "0"))
        max_score = float(request.form.get("max_score", "100"))
        sort_order = int(request.form.get("sort_order", "0") or "0")

        if not name:
            flash("指标名称不能为空", "danger")
            return redirect(url_for("quality.indicator_create"))

        indicator = QualityIndicator(
            name=name, dimension=dimension or None,
            parent_id=parent_id, weight=weight,
            max_score=max_score, sort_order=sort_order,
            is_active=True,
        )
        db.session.add(indicator)
        safe_commit()
        flash(f"指标「{name}」创建成功", "success")
        return redirect(url_for("quality.indicator_list"))

    # GET: 获取一级指标供选择父级
    level1 = QualityIndicator.query.filter_by(parent_id=0).order_by(
        QualityIndicator.sort_order
    ).all()
    return render_template("quality/indicator_form.html",
                           indicator=None, level1=level1)


@quality_bp.route("/indicators/<int:iid>/edit", methods=["GET", "POST"])
@require_role("ms_admin")
def indicator_edit(iid):
    indicator = QualityIndicator.query.get_or_404(iid)
    if request.method == "POST":
        indicator.name = request.form.get("name", "").strip()
        indicator.dimension = request.form.get("dimension", "") or None
        indicator.parent_id = int(request.form.get("parent_id", "0") or "0")
        indicator.weight = float(request.form.get("weight", "0"))
        indicator.max_score = float(request.form.get("max_score", "100"))
        indicator.sort_order = int(request.form.get("sort_order", "0") or "0")

        if not indicator.name:
            flash("指标名称不能为空", "danger")
            return redirect(url_for("quality.indicator_edit", iid=iid))

        safe_commit()
        flash(f"指标「{indicator.name}」更新成功", "success")
        return redirect(url_for("quality.indicator_list"))

    level1 = QualityIndicator.query.filter_by(parent_id=0).order_by(
        QualityIndicator.sort_order
    ).all()
    return render_template("quality/indicator_form.html",
                           indicator=indicator, level1=level1)


@quality_bp.route("/indicators/<int:iid>/toggle", methods=["POST"])
@require_role("ms_admin")
def indicator_toggle(iid):
    indicator = QualityIndicator.query.get_or_404(iid)
    indicator.is_active = not indicator.is_active
    safe_commit()
    return jsonify({
        "code": 0,
        "data": {"is_active": indicator.is_active, "name": indicator.name}
    })


# ══════════════════════════════════════════════════════════════
#  德育处/管理员端：总览
# ══════════════════════════════════════════════════════════════

@quality_bp.route("/overview")
@require_role("ms_admin", "grade_leader")
def overview():
    semester = _current_semester()
    grades = Grade.query.filter_by(is_active=True).order_by(Grade.sort_order).all()

    # 各年级各维度平均分
    grade_dim_data = {}
    for g in grades:
        grade_dim_data[g.id] = {}
        grade_dim_data[g.id]["name"] = g.name
        for d_key in DIMENSION_KEYS:
            # 获取该维度下所有活跃二级指标的ID
            sub_ids = [
                ind.id for ind in QualityIndicator.query.filter(
                    QualityIndicator.parent_id > 0,
                    QualityIndicator.dimension == d_key,
                    QualityIndicator.is_active == True,
                ).all()
            ]
            if sub_ids:
                avg = db.session.query(
                    func.avg(QualityScore.score)
                ).filter(
                    QualityScore.grade_id == g.id,
                    QualityScore.semester == semester,
                    QualityScore.indicator_id.in_(sub_ids),
                ).scalar()
                grade_dim_data[g.id][d_key] = round(float(avg), 1) if avg else 0.0
            else:
                grade_dim_data[g.id][d_key] = 0.0

        # 各年级综合均分（纯维度键求和，排除 "name" 字符串键）
        grade_dim_data[g.id]["total"] = round(
            sum(grade_dim_data[g.id].get(d, 0) for d in DIMENSION_KEYS), 1
        )

    return render_template("quality/overview.html",
                           grades=grades, grade_dim_data=grade_dim_data,
                           DIMENSIONS=DIMENSIONS, DIMENSION_KEYS=DIMENSION_KEYS,
                           semester=semester)


@quality_bp.route("/class-overview")
@require_role("ms_admin", "grade_leader")
def class_overview():
    grade_id = request.args.get("grade_id", type=int) or session.get("grade_id")
    semester = _current_semester()

    grades = Grade.query.filter_by(is_active=True).order_by(Grade.sort_order).all()
    classes_query = Class.query.filter_by(is_active=True).order_by(Class.name)
    if grade_id:
        classes_query = classes_query.filter_by(grade_id=grade_id)
    classes = classes_query.all()

    # 各班级各维度平均分
    class_dim_data = {}
    for c in classes:
        class_dim_data[c.id] = {
            "name": c.name,
            "grade_name": c.grade.name if c.grade else "",
        }
        for d_key in DIMENSION_KEYS:
            sub_ids = [
                ind.id for ind in QualityIndicator.query.filter(
                    QualityIndicator.parent_id > 0,
                    QualityIndicator.dimension == d_key,
                    QualityIndicator.is_active == True,
                ).all()
            ]
            if sub_ids:
                avg = db.session.query(
                    func.avg(QualityScore.score)
                ).filter(
                    QualityScore.class_id == c.id,
                    QualityScore.semester == semester,
                    QualityScore.indicator_id.in_(sub_ids),
                ).scalar()
                class_dim_data[c.id][d_key] = round(float(avg), 1) if avg else 0.0
            else:
                class_dim_data[c.id][d_key] = 0.0
        # 班级总分
        total_avg = db.session.query(func.avg(QualityScore.score)).filter(
            QualityScore.class_id == c.id,
            QualityScore.semester == semester,
        ).scalar()
        class_dim_data[c.id]["total"] = round(float(total_avg), 1) if total_avg else 0.0

    return render_template("quality/class_overview.html",
                           classes=classes, class_dim_data=class_dim_data,
                           grades=grades, grade_filter=grade_id,
                           DIMENSIONS=DIMENSIONS, DIMENSION_KEYS=DIMENSION_KEYS)


# ══════════════════════════════════════════════════════════════
#  班主任端：评分
# ══════════════════════════════════════════════════════════════

@quality_bp.route("/score", methods=["GET", "POST"])
@require_role("class_teacher", "teacher", "ms_admin")
def score():
    class_id = session.get("class_id")
    students = []
    if class_id:
        students = Student.query.filter_by(class_id=class_id, is_active=True).order_by(
            Student.student_no
        ).all()

    selected_student_id = request.args.get("student_id", type=int)
    selected_student = None
    indicators_tree = []
    scores_map = {}

    if selected_student_id:
        selected_student = Student.query.get(selected_student_id)
    elif students:
        selected_student = students[0]
        selected_student_id = selected_student.id

    # 构建指标树：一级 -> 二级
    level1_inds = QualityIndicator.query.filter(
        QualityIndicator.parent_id == 0,
        QualityIndicator.is_active == True,
    ).order_by(QualityIndicator.sort_order).all()

    for l1 in level1_inds:
        l2_inds = QualityIndicator.query.filter(
            QualityIndicator.parent_id == l1.id,
            QualityIndicator.is_active == True,
        ).order_by(QualityIndicator.sort_order).all()
        indicators_tree.append({"level1": l1, "level2": l2_inds})

    # 已有分数
    if selected_student_id:
        semester = _current_semester()
        existing = QualityScore.query.filter(
            QualityScore.student_id == selected_student_id,
            QualityScore.scorer_type == "teacher",
            QualityScore.scorer_id == session.get("user_id"),
            QualityScore.semester == semester,
        ).all()
        scores_map = {s.indicator_id: s for s in existing}

    # 自动计算建议分
    auto_hint = get_auto_score_hint(selected_student_id, _current_semester()) if selected_student_id else None

    if request.method == "POST" and selected_student_id:
        semester = _current_semester()
        scorer_id = session.get("user_id")

        # 遍历所有二级指标接收分数
        for l1 in level1_inds:
            l2_inds = QualityIndicator.query.filter(
                QualityIndicator.parent_id == l1.id,
                QualityIndicator.is_active == True,
            ).all()
            for ind in l2_inds:
                score_val = request.form.get(f"score_{ind.id}", "")
                comment = request.form.get(f"comment_{ind.id}", "").strip()

                if score_val != "":
                    score_float = float(score_val)
                    # 更新或创建
                    existing_score = scores_map.get(ind.id)
                    if existing_score:
                        existing_score.score = score_float
                        existing_score.comment = comment
                    else:
                        new_score = QualityScore(
                            student_id=selected_student_id,
                            class_id=selected_student.class_id if selected_student else 0,
                            grade_id=selected_student.grade_id if selected_student else 0,
                            indicator_id=ind.id,
                            score=score_float,
                            scorer_type="teacher",
                            scorer_id=scorer_id,
                            semester=semester,
                            comment=comment,
                        )
                        db.session.add(new_score)

        safe_commit()
        flash(f"已保存对「{selected_student.name}」的评价分数", "success")
        return redirect(url_for("quality.score", student_id=selected_student_id))

    return render_template("quality/score.html",
                           students=students, selected_student=selected_student,
                           indicators_tree=indicators_tree, scores_map=scores_map,
                           auto_hint=auto_hint, DIMENSIONS=DIMENSIONS)


@quality_bp.route("/batch-score", methods=["GET", "POST"])
@require_role("class_teacher", "teacher", "ms_admin")
def batch_score():
    class_id = session.get("class_id")
    students = []
    if class_id:
        students = Student.query.filter_by(class_id=class_id, is_active=True).order_by(
            Student.student_no
        ).all()

    # 所有活跃的二级指标供选择
    all_l2 = QualityIndicator.query.filter(
        QualityIndicator.parent_id > 0,
        QualityIndicator.is_active == True,
    ).order_by(QualityIndicator.dimension, QualityIndicator.sort_order).all()

    selected_indicator_id = request.args.get("indicator_id", type=int)
    selected_indicator = None
    if selected_indicator_id:
        selected_indicator = QualityIndicator.query.get(selected_indicator_id)
    elif all_l2:
        selected_indicator = all_l2[0]
        selected_indicator_id = selected_indicator.id

    if request.method == "POST" and selected_indicator_id and students:
        semester = _current_semester()
        scorer_id = session.get("user_id")
        indicator = QualityIndicator.query.get(selected_indicator_id)

        for stu in students:
            score_val = request.form.get(f"score_{stu.id}", "")
            if score_val != "":
                # 检查是否已有记录
                existing = QualityScore.query.filter(
                    QualityScore.student_id == stu.id,
                    QualityScore.indicator_id == selected_indicator_id,
                    QualityScore.scorer_type == "teacher",
                    QualityScore.scorer_id == scorer_id,
                    QualityScore.semester == semester,
                ).first()
                if existing:
                    existing.score = float(score_val)
                else:
                    new_score = QualityScore(
                        student_id=stu.id,
                        class_id=stu.class_id,
                        grade_id=stu.grade_id,
                        indicator_id=selected_indicator_id,
                        score=float(score_val),
                        scorer_type="teacher",
                        scorer_id=scorer_id,
                        semester=semester,
                    )
                    db.session.add(new_score)

        safe_commit()
        flash(f"已批量保存「{indicator.name}」的评分", "success")
        return redirect(url_for("quality.batch_score", indicator_id=selected_indicator_id))

    # 加载已有分数用于回显
    batch_scores = {}
    if selected_indicator_id and students:
        semester = _current_semester()
        scorer_id = session.get("user_id")
        stu_ids = [s.id for s in students]
        existing_qs = QualityScore.query.filter(
            QualityScore.student_id.in_(stu_ids),
            QualityScore.indicator_id == selected_indicator_id,
            QualityScore.scorer_type == "teacher",
            QualityScore.scorer_id == scorer_id,
            QualityScore.semester == semester,
        ).all()
        batch_scores = {qs.student_id: qs.score for qs in existing_qs}

    return render_template("quality/batch_score.html",
                           students=students, all_l2=all_l2,
                           selected_indicator=selected_indicator,
                           batch_scores=batch_scores)


@quality_bp.route("/my-class")
@require_role("ms_admin", "grade_leader", "class_teacher")
def my_class():
    class_id = session.get("class_id")
    semester = request.args.get("semester") or _current_semester()

    if not class_id:
        flash("未绑定班级，请联系德育处", "warning")
        return redirect(url_for("quality.dashboard"))

    students = Student.query.filter_by(class_id=class_id, is_active=True).all()
    student_ids = [s.id for s in students]

    # 🚀 批量预加载：仅 2 次查询替代 N×23 次循环穿透
    if student_ids:
        from models import QualityIndicator, QualityScore

        # 预加载 1：所有活跃三级指标，按维度分组
        indicators_cache = QualityIndicator.query.filter(
            QualityIndicator.parent_id > 0,
            QualityIndicator.is_active == True,
        ).all()
        indicators_by_dim = {}
        for ind in indicators_cache:
            indicators_by_dim.setdefault(ind.dimension, []).append(ind)

        # 预加载 2：全班教师评分记录，按 (student_id, (indicator_id, scorer_type)) 索引
        all_scores = QualityScore.query.filter(
            QualityScore.student_id.in_(student_ids),
            QualityScore.semester == semester,
            QualityScore.scorer_type == "teacher",
        ).all()
        scores_by_student = {}
        for s_score in all_scores:
            scores_by_student.setdefault(s_score.student_id, {})[(s_score.indicator_id, s_score.scorer_type)] = s_score
    else:
        indicators_by_dim = None
        scores_by_student = None

    # 内存计算：零 SQL 穿透
    student_results = []
    for stu in students:
        result = _calculate_balanced_score(
            stu.id, semester,
            indicators_by_dim=indicators_by_dim,
            scores_by_student=scores_by_student,
        )
        student_results.append({
            "student": stu,
            "dim_scores": result["dim_scores"],
            "balanced_scores": result["balanced_scores"],
            "total": result["total"],
            "penalized": result["penalized"],
            "has_any": any(v > 0 for v in result["dim_scores"].values()),
        })

    # 按总分排序 + 内存排名
    student_results.sort(key=lambda x: x["total"], reverse=True)
    for idx, item in enumerate(student_results):
        item["rank"] = idx + 1

    # 计算班级各维度均分（用于雷达图，避免在模板中用 Jinja2 sum 过滤器）
    class_avg_data = []
    for d_key in DIMENSION_KEYS:
        total_score = 0
        count = 0
        for item in student_results:
            score = item["dim_scores"].get(d_key, 0)
            total_score += score
            count += 1
        avg = round(total_score / count, 1) if count > 0 else 0
        class_avg_data.append(avg)

    return render_template("quality/my_class.html",
                           student_results=student_results,
                           DIMENSIONS=DIMENSIONS,
                           DIMENSION_KEYS=DIMENSION_KEYS,
                           class_avg_data=class_avg_data,
                           semester=semester)


# ══════════════════════════════════════════════════════════════
#  学生/家长端：自评、互评、报告
# ══════════════════════════════════════════════════════════════

@quality_bp.route("/self", methods=["GET", "POST"])
@require_role("student")
def self_eval():
    sid = session.get("student_id")
    student = Student.query.get(sid) if sid else None
    if not student:
        flash("未找到学生信息", "danger")
        return redirect(url_for("quality.dashboard"))

    semester = _current_semester()

    # 指标树
    level1_inds = QualityIndicator.query.filter(
        QualityIndicator.parent_id == 0,
        QualityIndicator.is_active == True,
    ).order_by(QualityIndicator.sort_order).all()

    indicators_tree = []
    scores_map = {}

    for l1 in level1_inds:
        l2_inds = QualityIndicator.query.filter(
            QualityIndicator.parent_id == l1.id,
            QualityIndicator.is_active == True,
        ).order_by(QualityIndicator.sort_order).all()
        indicators_tree.append({"level1": l1, "level2": l2_inds})

    # 已有自评
    existing = QualityScore.query.filter(
        QualityScore.student_id == sid,
        QualityScore.scorer_type == "self",
        QualityScore.semester == semester,
    ).all()
    scores_map = {s.indicator_id: s for s in existing}

    if request.method == "POST":
        for l1 in level1_inds:
            l2_inds = QualityIndicator.query.filter(
                QualityIndicator.parent_id == l1.id,
                QualityIndicator.is_active == True,
            ).all()
            for ind in l2_inds:
                score_val = request.form.get(f"score_{ind.id}", "")
                comment = request.form.get(f"comment_{ind.id}", "").strip()

                if score_val != "":
                    ex_score = scores_map.get(ind.id)
                    if ex_score:
                        ex_score.score = float(score_val)
                        ex_score.comment = comment
                    else:
                        ns = QualityScore(
                            student_id=sid,
                            class_id=student.class_id,
                            grade_id=student.grade_id,
                            indicator_id=ind.id,
                            score=float(score_val),
                            scorer_type="self",
                            scorer_id=sid,
                            semester=semester,
                            comment=comment,
                        )
                        db.session.add(ns)

        safe_commit()
        flash("自评提交成功", "success")
        return redirect(url_for("quality.self_eval"))

    return render_template("quality/self_eval.html",
                           student=student, indicators_tree=indicators_tree,
                           scores_map=scores_map)


@quality_bp.route("/peer", methods=["GET", "POST"])
@require_role("student")
def peer_eval():
    sid = session.get("student_id")
    me = Student.query.get(sid) if sid else None

    classmates = []
    if me:
        classmates = Student.query.filter(
            Student.class_id == me.class_id,
            Student.id != me.id,
            Student.is_active == True,
        ).order_by(Student.student_no).all()

    selected_peer_id = request.args.get("peer_id", type=int)
    selected_peer = None
    indicators_tree = []
    scores_map = {}

    if selected_peer_id:
        selected_peer = Student.query.get(selected_peer_id)

    semester = _current_semester()

    if selected_peer:
        level1_inds = QualityIndicator.query.filter(
            QualityIndicator.parent_id == 0,
            QualityIndicator.is_active == True,
        ).order_by(QualityIndicator.sort_order).all()

        for l1 in level1_inds:
            l2_inds = QualityIndicator.query.filter(
                QualityIndicator.parent_id == l1.id,
                QualityIndicator.is_active == True,
            ).order_by(QualityIndicator.sort_order).all()
            indicators_tree.append({"level1": l1, "level2": l2_inds})

        existing = QualityScore.query.filter(
            QualityScore.student_id == selected_peer_id,
            QualityScore.scorer_type == "peer",
            QualityScore.scorer_id == sid,
            QualityScore.semester == semester,
        ).all()
        scores_map = {s.indicator_id: s for s in existing}

    if request.method == "POST" and selected_peer_id:
        level1_inds = QualityIndicator.query.filter(
            QualityIndicator.parent_id == 0,
            QualityIndicator.is_active == True,
        ).all()

        for l1 in level1_inds:
            l2_inds = QualityIndicator.query.filter(
                QualityIndicator.parent_id == l1.id,
                QualityIndicator.is_active == True,
            ).all()
            for ind in l2_inds:
                score_val = request.form.get(f"score_{ind.id}", "")
                if score_val != "":
                    ex_score = scores_map.get(ind.id)
                    if ex_score:
                        ex_score.score = float(score_val)
                    else:
                        ns = QualityScore(
                            student_id=selected_peer_id,
                            class_id=selected_peer.class_id if selected_peer else 0,
                            grade_id=selected_peer.grade_id if selected_peer else 0,
                            indicator_id=ind.id,
                            score=float(score_val),
                            scorer_type="peer",
                            scorer_id=sid,
                            semester=semester,
                        )
                        db.session.add(ns)

        safe_commit()
        flash(f"已完成对「{selected_peer.name}」的互评", "success")
        return redirect(url_for("quality.peer_eval", peer_id=selected_peer_id))

    return render_template("quality/peer_eval.html",
                           me=me, classmates=classmates,
                           selected_peer=selected_peer,
                           indicators_tree=indicators_tree,
                           scores_map=scores_map)


@quality_bp.route("/report/<int:sid>")
@require_role("ms_admin", "grade_leader", "class_teacher", "teacher", "parent", "student")
def report(sid):
    # 权限检查：家长只能看自己孩子，学生只能看自己
    role = session.get("role", "")
    if role == "parent":
        bound_sid = session.get("bound_student_id")
        if bound_sid != sid:
            flash("无权查看此学生的报告", "danger")
            return redirect(url_for("quality.dashboard"))
    elif role == "student":
        my_sid = session.get("student_id")
        if my_sid != sid:
            flash("无权查看此学生的报告", "danger")
            return redirect(url_for("quality.dashboard"))

    student = Student.query.get_or_404(sid)
    semester = _current_semester()

    # ==================== Phase 3: 中央缓存战略上移（终极合围版） ====================
    class_rankings = []
    rank = None  # 严格对齐模板变量名 {{ rank }}
    comments = []

    if student.class_id:
        classmates = Student.query.filter_by(class_id=student.class_id, is_active=True).all()
        cm_ids = [c.id for c in classmates]
    else:
        classmates = [student]
        cm_ids = [student.id]

    from models import QualityIndicator, QualityScore

    # [1/2] 批量捞出活跃叶子指标（严格保持 sort_order 排序）
    indicators_cache = QualityIndicator.query.filter(
        QualityIndicator.parent_id > 0,
        QualityIndicator.is_active == True
    ).order_by(QualityIndicator.sort_order).all()

    indicators_by_dim = {}
    for ind in indicators_cache:
        indicators_by_dim.setdefault(ind.dimension, []).append(ind)

    # [2/2] 批量捞出全班所有评分主体数据（teacher/self/peer 复合吃入）
    all_scores = QualityScore.query.filter(
        QualityScore.student_id.in_(cm_ids),
        QualityScore.semester == semester
    ).all()

    scores_by_student = {}
    for s_score in all_scores:
        scores_by_student.setdefault(s_score.student_id, {})[(s_score.indicator_id, s_score.scorer_type)] = s_score

    # ==================== 捞取目标学生权威平衡总分 ====================
    target_balanced = _calculate_balanced_score(
        student.id, semester, scorer_type="teacher",
        indicators_by_dim=indicators_by_dim,
        scores_by_student=scores_by_student
    )

    grand_total = target_balanced["total"]
    dim_radar = [target_balanced["balanced_scores"][d] for d in DIMENSION_KEYS]

    # ==================== 子指标明细纯内存组装（严丝合缝对齐前端契约） ====================
    report_data = []
    target_scores = scores_by_student.get(student.id, {})

    for dim_info in DIMENSIONS:
        d_key = dim_info["key"]
        subs = indicators_by_dim.get(d_key, [])

        dim_detail = {
            "dimension": dim_info["name"],
            "dim_total": target_balanced["balanced_scores"][d_key],
            "subs": []  # 保持原版键名
        }

        for sub in subs:
            t_score = target_scores.get((sub.id, "teacher"))
            s_score = target_scores.get((sub.id, "self"))
            p_score = target_scores.get((sub.id, "peer"))

            teacher_val = float(t_score.score) if t_score else None
            self_val = float(s_score.score) if s_score else None
            peer_val = float(p_score.score) if p_score else None

            # 完美复原原系统 teacher ?? self ?? 0 三级分级回退逻辑
            effective = teacher_val if teacher_val is not None else (self_val if self_val is not None else 0.0)
            weighted_val = round(effective * float(sub.weight or 1.0), 1)

            dim_detail["subs"].append({
                "indicator": sub,            # 保留原始 ORM 对象引用 (.name / .weight)
                "teacher_score": teacher_val,
                "self_score": self_val,
                "peer_avg": peer_val,        # 回正为 "peer_avg"
                "weighted": weighted_val     # 补回加权分
            })

        report_data.append(dim_detail)

    # ==================== 班级排名真值迭代（复用中央缓存） ====================
    if student.class_id:
        for cs in classmates:
            res = _calculate_balanced_score(
                cs.id, semester, scorer_type="teacher",
                indicators_by_dim=indicators_by_dim,
                scores_by_student=scores_by_student
            )
            class_rankings.append((cs, res["total"]))

        # 执行精确平衡名次裁决
        class_rankings.sort(key=lambda x: x[1], reverse=True)
        for idx, (cs, score) in enumerate(class_rankings):
            if cs.id == student.id:
                rank = idx + 1  # 变量名完美对齐
                break

    # 剥离 scorer_type 限制，补回创建时间倒序
    comments = QualityScore.query.filter(
        QualityScore.student_id == student.id,
        QualityScore.semester == semester,
        QualityScore.comment.isnot(None),
        QualityScore.comment != ""
    ).order_by(QualityScore.created_at.desc()).all()

    # 100% 完好无损交付给前端 Jinja2
    return render_template(
        "quality/report.html",
        student=student,
        semester=semester,
        report_data=report_data,
        grand_total=grand_total,
        dim_radar=dim_radar,
        class_rankings=class_rankings[:10],
        rank=rank,  # 变量契约交接完成
        comments=comments
    )


# ── 自动从各模块聚合数据 ─────────────────────────────
def auto_calculate_from_modules(stu_id, semester):
    """自动从各模块计算综合素质评价分数（不写入DB，仅返回建议分）

    返回: {
        "moral":    建议分(0-100),   # 思想品德：违纪记录反推
        "academic": 建议分(0-100),   # 学业水平：考试成绩换算
        "health":   建议分(0-100),   # 身心健康：心理评估 + 体质
        "art":      建议分(0-100),   # 艺术素养：艺术活动参与
        "social":   建议分(0-100),   # 社会实践：活动参与
        "details":  {各维度详细解释}
    }
    """
    from models import DisciplineRecord, Score, Exam, ActivityRegistration, Activity
    from models import MentalHealthAssessment
    from sqlalchemy import func

    result = {
        "moral": 75, "academic": 75, "health": 75, "art": 75, "social": 75,
        "details": {}
    }

    # 1. 思想品德 (moral) — 违纪记录越少分越高
    records = DisciplineRecord.query.filter_by(student_id=stu_id).all()
    total_points = sum(r.points for r in records)
    if total_points == 0:
        moral_score = 95
    elif total_points <= 5:
        moral_score = 85
    elif total_points <= 15:
        moral_score = 70
    else:
        moral_score = 50
    result["moral"] = moral_score
    result["details"]["moral"] = f"违纪扣分合计 {total_points} 分，评定 {moral_score} 分"

    # 2. 学业水平 (academic) — 考试成绩换算
    latest_exam = Exam.query.order_by(Exam.exam_date.desc()).first()
    if latest_exam:
        scores = Score.query.filter_by(student_id=stu_id, exam_id=latest_exam.id).all()
        if scores:
            avg = sum(s.score for s in scores) / len(scores)
            # 假设满分100，换算成 0-100 分
            academic_score = min(100, max(0, avg))
            result["academic"] = round(academic_score, 1)
            result["details"]["academic"] = f"最近考试「{latest_exam.name}」平均分 {round(avg, 1)}，评定 {round(academic_score, 1)} 分"

    # 3. 身心健康 (health) — 心理评估 + 基础分
    mh = MentalHealthAssessment.query.filter_by(student_id=stu_id).order_by(
        MentalHealthAssessment.created_at.desc()
    ).first()
    health_base = 75
    if mh:
        if mh.risk_level == "low":
            health_base = 90
        elif mh.risk_level == "medium":
            health_base = 75
        else:
            health_base = 55
    result["health"] = health_base
    result["details"]["health"] = f"心理健康评估风险等级：{mh.risk_level if mh else '未评估'}，评定 {health_base} 分"

    # 4. 艺术素养 (art) — 艺术节等活动参与
    art_activities = ActivityRegistration.query.join(Activity).filter(
        ActivityRegistration.student_id == stu_id,
        ActivityRegistration.status == "confirmed",
        Activity.activity_type.in_(["艺术节", "社团活动"]),
    ).all()
    art_score = 70 + min(20, len(art_activities) * 5)
    result["art"] = min(100, art_score)
    result["details"]["art"] = f"参与艺术节/社团活动 {len(art_activities)} 次，评定 {min(100, art_score)} 分"

    # 5. 社会实践 (social) — 社会实践/志愿服务活动参与
    social_activities = ActivityRegistration.query.join(Activity).filter(
        ActivityRegistration.student_id == stu_id,
        ActivityRegistration.status == "confirmed",
        Activity.activity_type.in_(["社会实践", "志愿服务"]),
    ).all()
    social_score = 70 + min(25, len(social_activities) * 6)
    result["social"] = min(100, social_score)
    result["details"]["social"] = f"参与社会实践/志愿服务 {len(social_activities)} 次，评定 {min(100, social_score)} 分"

    return result


def get_auto_score_hint(stu_id, semester):
    """获取自动评分提示（用于评分页面展示）"""
    return auto_calculate_from_modules(stu_id, semester)
