"""成绩管理模块 — 考试/科目/成绩录入/排名/分析"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from models import db, Student, Class, Grade, User, Subject, Exam, Score
from decorators import login_required, require_role, scope_query
from datetime import date
from sqlalchemy import func, text
from utils.db_utils import safe_commit
from blueprints.common import notify_parent
from blueprints.audit_log import audit_log

scores_bp = Blueprint("scores", __name__)


@scores_bp.before_request
@login_required
@require_role("ms_admin", "grade_leader", "class_teacher")
def check_role():
    pass


# ── 成绩管理首页 ──
@scores_bp.route("/")
def index():
    """成绩管理概览"""
    role = session.get("role", "")
    my_class_id = session.get("class_id")
    my_grade_id = session.get("grade_id")

    # 统计信息 — 按角色隔离
    if role == "class_teacher" and my_class_id:
        student_ids = [s.id for s in Student.query.filter_by(class_id=my_class_id, is_active=True).all()]
        stats = {
            "exam_count": Exam.query.filter_by(grade_id=my_grade_id).count() if my_grade_id else 0,
            "subject_count": Subject.query.count(),
            "score_count": Score.query.filter(Score.student_id.in_(student_ids)).count() if student_ids else 0,
            "student_count": len(student_ids),
        }
        recent_exams = Exam.query.filter_by(grade_id=my_grade_id).order_by(Exam.exam_date.desc()).limit(5).all() if my_grade_id else []
        exam_counts = {my_grade_id: stats["exam_count"]} if my_grade_id else {}
        score_counts = {my_grade_id: stats["score_count"]} if my_grade_id else {}
        grades = [Grade.query.get(my_grade_id)] if my_grade_id else []
    else:
        stats = {
            "exam_count": Exam.query.count(),
            "subject_count": Subject.query.count(),
            "score_count": Score.query.count(),
            "student_count": Student.query.filter_by(is_active=True).count(),
        }
        recent_exams = Exam.query.order_by(Exam.exam_date.desc()).limit(5).all()
        exam_counts = dict(db.session.query(
            Exam.grade_id, func.count(Exam.id)
        ).group_by(Exam.grade_id).all())
        score_counts = dict(db.session.query(
            Score.grade_id, func.count(Score.id)
        ).group_by(Score.grade_id).all())
        grades = Grade.query.order_by(Grade.sort_order).all()

    grade_stats = []
    for g in grades:
        grade_stats.append({
            "grade": g,
            "exam_count": exam_counts.get(g.id, 0),
            "score_count": score_counts.get(g.id, 0),
        })

    return render_template("scores/index.html", stats=stats, recent_exams=recent_exams, grade_stats=grade_stats)


# ══════════════════════════════════════════════════════════════
#  考试管理
# ══════════════════════════════════════════════════════════════

@scores_bp.route("/exams")
@login_required
def exam_list():
    """考试列表"""
    role = session.get("role", "")
    my_grade_id = session.get("grade_id")
    grade_id = request.args.get("grade_id", type=int)
    exam_type = request.args.get("exam_type", "")

    q = Exam.query
    # 班主任只能看自己年级的考试
    if role == "class_teacher" and my_grade_id:
        q = q.filter_by(grade_id=my_grade_id)
        grade_id = my_grade_id
    elif grade_id:
        q = q.filter_by(grade_id=grade_id)
    if exam_type:
        q = q.filter_by(exam_type=exam_type)

    exams = q.order_by(Exam.exam_date.desc()).all()

    # 班主任只能看到自己的年级
    if role == "class_teacher" and my_grade_id:
        grades = [Grade.query.get(my_grade_id)] if my_grade_id else []
    else:
        grades = Grade.query.order_by(Grade.sort_order).all()
    exam_types = ["月考", "期中", "期末", "模拟", "其他"]

    return render_template("scores/exam_list.html", exams=exams, grades=grades,
                           exam_types=exam_types, grade_id=grade_id, exam_type=exam_type)


@scores_bp.route("/exams/create", methods=["POST"])
@login_required
@require_role("ms_admin", "grade_leader")
def create_exam():
    """创建考试"""
    name = request.form.get("name", "").strip()
    exam_date = request.form.get("exam_date", "")
    exam_type = request.form.get("exam_type", "月考")
    grade_id = request.form.get("grade_id", type=int)

    if not name or not exam_date or not grade_id:
        flash("请填写完整信息", "danger")
        return redirect(url_for("scores.exam_list"))

    # 检查是否已存在同名考试
    if Exam.query.filter_by(name=name).first():
        flash("已存在同名考试", "danger")
        return redirect(url_for("scores.exam_list"))

    exam = Exam(
        name=name,
        exam_date=date.fromisoformat(exam_date),
        exam_type=exam_type,
        grade_id=grade_id,
    )
    db.session.add(exam)
    safe_commit()

    flash(f"考试「{name}」已创建", "success")
    return redirect(url_for("scores.exam_list"))


@scores_bp.route("/exams/<int:eid>/delete", methods=["POST"])
@login_required
@require_role("ms_admin", "grade_leader")
def delete_exam(eid):
    """删除考试"""
    exam = Exam.query.get_or_404(eid)

    # 权限检查
    if session.get("role") != "ms_admin":
        if exam.grade_id != session.get("grade_id"):
            flash("无权操作", "danger")
            return redirect(url_for("scores.exam_list"))

    # 删除相关成绩
    Score.query.filter_by(exam_id=eid).delete()
    db.session.delete(exam)
    safe_commit()

    flash(f"考试「{exam.name}」已删除", "success")
    return redirect(url_for("scores.exam_list"))


@scores_bp.route("/exams/<int:eid>")
@login_required
def exam_detail(eid):
    """考试详情 — 成绩表"""
    exam = Exam.query.get_or_404(eid)

    # 权限检查
    if session.get("role") not in ("ms_admin", "grade_leader"):
        if exam.grade_id != session.get("grade_id"):
            flash("无权查看", "danger")
            return redirect(url_for("scores.index"))

    # 获取该考试的所有成绩（班主任只能看本班）
    q = Score.query.filter_by(exam_id=eid)
    if session.get("role") == "class_teacher":
        q = q.filter_by(class_id=session.get("class_id"))
    scores = q.all()

    # 获取科目
    subjects = Subject.query.order_by(Subject.sort_order).all()

    # 获取班级
    classes = Class.query.filter_by(grade_id=exam.grade_id).all()

    # 构建成绩矩阵
    score_matrix = {}
    for s in scores:
        key = (s.student_id, s.subject_id)
        score_matrix[key] = s

    return render_template("scores/exam_detail.html", exam=exam, subjects=subjects,
                           classes=classes, scores=score_matrix, students=[])


@scores_bp.route("/exams/<int:eid>/input")
@login_required
def score_input(eid):
    """成绩录入表单"""
    exam = Exam.query.get_or_404(eid)

    # 权限检查
    if session.get("role") not in ("ms_admin", "grade_leader", "class_teacher"):
        flash("无权录入成绩", "danger")
        return redirect(url_for("scores.index"))

    # 获取班级
    class_id = request.args.get("class_id", type=int)
    if session.get("role") == "class_teacher":
        class_id = session.get("class_id")

    classes = Class.query.filter_by(grade_id=exam.grade_id).all()
    subjects = Subject.query.order_by(Subject.sort_order).all()

    # 获取学生
    q = Student.query.filter_by(is_active=True)
    if class_id:
        q = q.filter_by(class_id=class_id)
    students = q.order_by(Student.student_no).all()

    # 获取已有成绩
    scores = Score.query.filter_by(exam_id=eid)
    if class_id:
        scores = scores.filter_by(class_id=class_id)
    score_dict = {}
    for s in scores:
        score_dict[(s.student_id, s.subject_id)] = s.score

    return render_template("scores/score_input.html", exam=exam, classes=classes,
                           subjects=subjects, students=students, score_dict=score_dict,
                           class_id=class_id)


@scores_bp.route("/exams/<int:eid>/input", methods=["POST"])
@login_required
@audit_log("save_scores", "Score")
def save_scores(eid):
    """保存成绩（批量），并通知家长"""
    exam = Exam.query.get_or_404(eid)

    # 权限检查
    if session.get("role") not in ("ms_admin", "grade_leader", "class_teacher"):
        flash("无权录入成绩", "danger")
        return redirect(url_for("scores.index"))

    # ==================== 战点 2: 第一趟扫描（纯 ID 收集） ====================
    form_sids = set()
    for key in request.form:
        if key.startswith("score_"):
            parts = key.split("_")
            if len(parts) == 3:
                form_sids.add(int(parts[1]))

    # 班主任只能录入本班学生成绩
    teacher_class_id = None
    if session.get("role") == "class_teacher":
        teacher_class_id = session.get("class_id")
        valid_sids = set(
            sid for sid, in db.session.query(Student.id)
            .filter(Student.id.in_(list(form_sids)), Student.class_id == teacher_class_id)
            .all()
        )
        form_sids = form_sids & valid_sids

    # 🚀 仅 2 次批量查询，将上百次 filter/get 压降为 O(1)
    existing = Score.query.filter(
        Score.exam_id == eid,  # 严格对齐生产变量名 eid
        Score.student_id.in_(list(form_sids))
    ).all()
    score_cache = {(s.student_id, s.subject_id): s for s in existing}
    student_cache = {
        stu.id: stu
        for stu in Student.query.filter(Student.id.in_(list(form_sids))).all()
    }

    # ==================== 第二趟扫描：纯内存安全处理 ====================
    count = 0
    affected_student_ids = set()
    for key, value in request.form.items():
        if key.startswith("score_"):
            parts = key.split("_")
            if len(parts) != 3:
                continue
            student_id = int(parts[1])
            subject_id = int(parts[2])

            try:
                score_value = float(value) if value.strip() else 0.0
            except ValueError:
                score_value = 0.0

            if score_value is None:
                continue

            # 从内存索引中直接获取
            score_obj = score_cache.get((student_id, subject_id))
            if score_obj:
                score_obj.score = score_value
                score_obj.verify_status = 'VERIFIED'
            else:
                student_obj = student_cache.get(student_id)
                if student_obj:
                    score = Score(
                        exam_id=eid,
                        student_id=student_id,
                        subject_id=subject_id,
                        class_id=student_obj.class_id,
                        grade_id=student_obj.grade_id,
                        score=score_value,
                        verify_status='VERIFIED',
                    )
                    db.session.add(score)

            affected_student_ids.add(student_id)
            count += 1

    safe_commit()

    # ── 战点 2.5: 自动重算排名（窗口函数，永久修复排名污染）──
    try:
        _recalculate_ranks(eid)
    except Exception:
        pass  # 排名重算失败不影响成绩保存主流程

    # ==================== 战点 3: 通知循环复用缓存 ====================
    from_user_id = session.get("user_id")
    for sid in affected_student_ids:
        stu = student_cache.get(sid)  # 🚀 零外部 SQL 查询，完美复用
        if stu:
            notify_parent(
                stu,
                title=f"成绩通知 — {stu.name}",
                content=f"您孩子的【{exam.name}】成绩已录入/更新，请登录系统查看详情。",
                from_user_id=from_user_id,
            )

    # ── 成绩变更后触发AI风险分析（后台线程，不阻塞响应） ──
    def _bg_ai_analysis():
        try:
            from flask import current_app
            app = current_app._get_current_object()
            with app.app_context():
                from blueprints.ai_analysis import _analyze_student_detail
                from models import RiskRecord
                import json as json_mod
                from blueprints.common import notify_class_teacher

                scan_date = date.today()
                for sid in list(affected_student_ids):
                    try:
                        # 🚀 战点 4: 嵌套子事务隔离（上下文管理器确保异常自动回滚）
                        with db.session.begin_nested():
                            # 状态机守卫：检查该学生本次录入的成绩是否都是 VERIFIED
                            unverified = Score.query.filter(
                                Score.student_id == sid,
                                Score.exam_id == eid,
                                Score.verify_status != 'VERIFIED'
                            ).first()
                            if unverified:
                                continue

                            stu = student_cache.get(sid)
                            if not stu:
                                continue
                        warnings = _analyze_student_detail(stu, scan_date)
                        if not warnings:
                            continue

                        levels = [w["level"] for w in warnings]
                        if "red" in levels:
                            max_level = "red"
                        elif "yellow" in levels:
                            max_level = "yellow"
                        else:
                            max_level = "green"

                        if max_level == "green":
                            continue

                        # 幂等性守卫：同一学生同一天只生成一次风险记录
                        from blueprints.linkage_utils import try_linkage, tk_risk
                        if not try_linkage(
                            "score_to_risk",
                            f"score:{eid}:{sid}",
                            tk_risk(sid, scan_date),
                        ):
                            continue

                        risk = RiskRecord(
                            student_id=sid,
                            grade_id=stu.grade_id,
                            class_id=stu.class_id,
                            scan_date=scan_date,
                            risk_level=max_level,
                            warning_details=json_mod.dumps(warnings, ensure_ascii=False),
                            warning_count=len(warnings),
                            notification_sent=False,
                        )
                        db.session.add(risk)
                        # 严禁在此处执行单步 commit()，彻底释放磁盘 I/O

                        w_types = ", ".join(set(w["type"] for w in warnings))
                        notify_class_teacher(
                            stu,
                            title=f"AI预警 — {stu.name}（成绩变更触发）",
                            content=f"{stu.name} 在【{exam.name}】成绩更新后触发{len(warnings)}条风险预警（{w_types}），\n风险等级：{max_level}，请登录AI分析页面查看详情。",
                            from_user_id=from_user_id,
                        )
                    except Exception:
                        continue  # 单生AI分析失败不中断批量

                # ==================== 统一外提的单批次原子提交 ====================
                try:
                    db.session.commit()
                except Exception as e:
                    db.session.rollback()
                    current_app.logger.error(f"AI异步分析批次合并提交失败: {str(e)}")
        except Exception:
            pass  # 后台线程整体失败不影响前端

    from threading import Thread
    t = Thread(target=_bg_ai_analysis, daemon=True)
    t.start()

    flash(f"已保存 {count} 条成绩", "success")

    # ── MLOps 自进化: 成绩变更触发模型自动重训 ──
    try:
        from utils.model_retrain import trigger_auto_retrain
        trigger_auto_retrain(current_app._get_current_object(), grade_id=exam.grade_id)
    except Exception:
        pass  # 重训失败不影响成绩保存

    class_id = request.args.get("class_id", "")
    return redirect(url_for("scores.score_input", eid=eid, class_id=class_id))


@scores_bp.route("/exams/<int:eid>/ranking")
@login_required
def exam_ranking(eid):
    """班级排名"""
    exam = Exam.query.get_or_404(eid)

    # 权限检查
    if session.get("role") not in ("ms_admin", "grade_leader"):
        if exam.grade_id != session.get("grade_id"):
            flash("无权查看", "danger")
            return redirect(url_for("scores.index"))

    class_id = request.args.get("class_id", type=int)
    # 班主任只能看本班排名
    if session.get("role") == "class_teacher":
        class_id = session.get("class_id")

    subjects = Subject.query.order_by(Subject.sort_order).all()

    # 获取成绩并按班级分组
    q = Score.query.filter_by(exam_id=eid)
    if class_id:
        q = q.filter_by(class_id=class_id)

    scores = q.all()

    # 构建排名数据
    ranking_data = {}
    for s in scores:
        if s.class_id not in ranking_data:
            ranking_data[s.class_id] = []
        ranking_data[s.class_id].append(s)

    # 获取班级信息
    classes = Class.query.filter_by(grade_id=exam.grade_id).all()

    return render_template("scores/exam_ranking.html", exam=exam, subjects=subjects,
                           classes=classes, ranking_data=ranking_data, class_id=class_id)


@scores_bp.route("/exams/<int:eid>/analysis")
@login_required
def exam_analysis(eid):
    """成绩分析 — 分数分布图表"""
    exam = Exam.query.get_or_404(eid)

    # 权限检查
    if session.get("role") not in ("ms_admin", "grade_leader"):
        if exam.grade_id != session.get("grade_id"):
            flash("无权查看", "danger")
            return redirect(url_for("scores.index"))

    # 获取成绩（班主任只能看本班）
    q = Score.query.filter_by(exam_id=eid)
    if session.get("role") == "class_teacher":
        q = q.filter_by(class_id=session.get("class_id"))
    scores = q.all()

    # 获取科目
    subjects = Subject.query.order_by(Subject.sort_order).all()

    # 统计数据
    analysis_data = {}
    for subject in subjects:
        subject_scores = [s.score for s in scores if s.subject_id == subject.id and s.score is not None]
        if subject_scores:
            analysis_data[subject.name] = {
                "count": len(subject_scores),
                "avg": sum(subject_scores) / len(subject_scores),
                "max": max(subject_scores),
                "min": min(subject_scores),
                "pass_rate": len([s for s in subject_scores if s >= subject.pass_score]) / len(subject_scores) * 100,
                "excellent_rate": len([s for s in subject_scores if s >= subject.full_score * 0.85]) / len(subject_scores) * 100,
            }

    return render_template("scores/exam_analysis.html", exam=exam, subjects=subjects,
                           analysis_data=analysis_data)


# ══════════════════════════════════════════════════════════════
#  科目管理
# ══════════════════════════════════════════════════════════════

@scores_bp.route("/subjects")
@login_required
@require_role("ms_admin", "grade_leader")
def subject_list():
    """科目列表"""
    subjects = Subject.query.order_by(Subject.sort_order).all()
    return render_template("scores/subject_list.html", subjects=subjects)


@scores_bp.route("/subjects/create", methods=["POST"])
@login_required
@require_role("ms_admin", "grade_leader")
def create_subject():
    """创建科目"""
    name = request.form.get("name", "").strip()
    full_score = request.form.get("full_score", 100, type=float)
    pass_score = request.form.get("pass_score", 60, type=float)
    sort_order = request.form.get("sort_order", 0, type=int)

    if not name:
        flash("请输入科目名称", "danger")
        return redirect(url_for("scores.subject_list"))

    if Subject.query.filter_by(name=name).first():
        flash("已存在同名科目", "danger")
        return redirect(url_for("scores.subject_list"))

    subject = Subject(
        name=name,
        full_score=full_score,
        pass_score=pass_score,
        sort_order=sort_order,
    )
    db.session.add(subject)
    safe_commit()

    flash(f"科目「{name}」已创建", "success")
    return redirect(url_for("scores.subject_list"))


@scores_bp.route("/subjects/<int:sid>/delete", methods=["POST"])
@login_required
@require_role("ms_admin", "grade_leader")
def delete_subject(sid):
    """删除科目"""
    subject = Subject.query.get_or_404(sid)

    # 检查是否有成绩使用该科目
    if Score.query.filter_by(subject_id=sid).first():
        flash("该科目已有成绩记录，无法删除", "danger")
        return redirect(url_for("scores.subject_list"))

    db.session.delete(subject)
    safe_commit()

    flash(f"科目「{subject.name}」已删除", "success")
    return redirect(url_for("scores.subject_list"))


# ══════════════════════════════════════════════════════════════
#  排名计算
# ══════════════════════════════════════════════════════════════

def _recalculate_ranks(eid):
    """MySQL 8.0 RANK() OVER() 窗口函数 — 单条 SQL 替代 Python O(n log n)
    
    同时计算 class_id+subject_id 维度（班级排名）和 grade_id+subject_id 维度（年级排名）。
    排名污染修复: 每次成绩变更后自动触发，确保 rank_class/rank_grade 始终与 score 同步。
    """
    db.session.execute(text("""
        UPDATE scores s
        INNER JOIN (
            SELECT id,
                RANK() OVER (
                    PARTITION BY class_id, subject_id
                    ORDER BY score DESC
                ) AS new_rank_class,
                RANK() OVER (
                    PARTITION BY grade_id, subject_id
                    ORDER BY score DESC
                ) AS new_rank_grade
            FROM scores
            WHERE exam_id = :eid AND score IS NOT NULL
        ) r ON s.id = r.id
        SET s.rank_class = r.new_rank_class,
            s.rank_grade = r.new_rank_grade
        WHERE s.exam_id = :eid
    """), {"eid": eid})
    safe_commit()


@scores_bp.route("/rank/calculate/<int:eid>", methods=["POST"])
@login_required
@require_role("ms_admin", "grade_leader")
def calculate_rank(eid):
    """计算排名 — MySQL 8.0 RANK() OVER() 窗口函数版"""
    exam = Exam.query.get_or_404(eid)

    if session.get("role") != "ms_admin":
        if exam.grade_id != session.get("grade_id"):
            flash("无权操作", "danger")
            return redirect(url_for("scores.exam_list"))

    _recalculate_ranks(eid)

    flash("排名计算完成", "success")
    return redirect(url_for("scores.exam_detail", eid=eid))


# ══════════════════════════════════════════════════════════════
#  多学期对比分析
# ══════════════════════════════════════════════════════════════

@scores_bp.route("/comparison")
@login_required
def comparison():
    """多学期对比分析 — 跨考试趋势/班级对比/进退步榜"""
    role = session.get("role", "")
    my_class_id = session.get("class_id")
    my_grade_id = session.get("grade_id")

    grade_id = session.get("grade_id") or request.args.get("grade_id", type=int)
    if not grade_id:
        # admin/multi-role users: default to first grade
        g = Grade.query.order_by(Grade.sort_order).first()
        grade_id = g.id if g else 1
    view_class_id = request.args.get("class_id", type=int)
    view_subject_id = request.args.get("subject_id", type=int)

    # 班主任强制限制在自己班级
    if role == "class_teacher" and my_class_id:
        view_class_id = my_class_id
        grade_id = my_grade_id or grade_id

    # 获取所有考试（按日期排序）
    exams = Exam.query.filter_by(grade_id=grade_id).order_by(Exam.exam_date.asc()).all()
    if len(exams) < 2:
        return render_template("scores/comparison.html", exams=exams, error="至少需要2场考试数据才能进行对比分析")

    # 获取班级和科目 — 班主任只能看自己的班
    if role == "class_teacher" and my_class_id:
        classes = [Class.query.get(my_class_id)]
    else:
        classes = Class.query.filter_by(grade_id=grade_id).order_by(Class.name).all()
    subjects = Subject.query.order_by(Subject.sort_order).all()

    # ── 数据聚合 ──
    exam_ids = [e.id for e in exams]
    score_q = Score.query.filter(
        Score.exam_id.in_(exam_ids),
        Score.grade_id == grade_id,
        Score.score.isnot(None),
    )
    # 班主任只能看自己班学生的成绩
    if role == "class_teacher" and my_class_id:
        score_q = score_q.filter(Score.class_id == my_class_id)
    all_scores = score_q.all()

    # 1) 学生-考试-总分 (用于个人趋势)
    student_exam_total = {}  # {student_id: {exam_id: total}}
    for s in all_scores:
        st = student_exam_total.setdefault(s.student_id, {})
        st[s.exam_id] = st.get(s.exam_id, 0) + s.score

    # 2) 学生-考试-单科分 (用于单科趋势)
    student_exam_subject = {}  # {student_id: {exam_id: {subject_id: score}}}
    for s in all_scores:
        se = student_exam_subject.setdefault(s.student_id, {})
        ex = se.setdefault(s.exam_id, {})
        ex[s.subject_id] = s.score

    # 3) 班级-考试-均分
    class_exam_avgs = {}  # {class_id: {exam_id: avg}}
    for s in all_scores:
        ce = class_exam_avgs.setdefault(s.class_id, {})
        ce.setdefault(s.exam_id, []).append(s.score)
    for cid, ed in class_exam_avgs.items():
        for eid, lst in ed.items():
            ed[eid] = round(sum(lst) / len(lst), 1)

    # 4) 班级-考试-科目-均分
    class_exam_subject_avgs = {}  # {class_id: {exam_id: {subject_id: avg}}}
    for s in all_scores:
        ce = class_exam_subject_avgs.setdefault(s.class_id, {})
        se = ce.setdefault(s.exam_id, {})
        se.setdefault(s.subject_id, []).append(s.score)
    for cid, ed in class_exam_subject_avgs.items():
        for eid, sd in ed.items():
            for sid, lst in sd.items():
                sd[sid] = round(sum(lst) / len(lst), 1)

    # ── 进退步榜（仅比较两场考试的交集科目，避免科目数不同导致失真）──
    subject_count_warning = ""
    if len(exams) >= 2:
        e_prev, e_curr = exams[-2], exams[-1]

        # 找出两场考试的共同科目
        prev_subjects = set(
            s.subject_id for s in all_scores if s.exam_id == e_prev.id
        )
        curr_subjects = set(
            s.subject_id for s in all_scores if s.exam_id == e_curr.id
        )
        common_subjects = prev_subjects & curr_subjects
        only_prev = prev_subjects - curr_subjects
        only_curr = curr_subjects - prev_subjects

        if only_prev or only_curr:
            warn_parts = []
            if only_prev:
                names = [s.name for s in subjects if s.id in only_prev]
                warn_parts.append("上次有而本次没有: " + "、".join(names))
            if only_curr:
                names = [s.name for s in subjects if s.id in only_curr]
                warn_parts.append("本次有而上次没有: " + "、".join(names))
            subject_count_warning = "⚠️ 注意：" + "；".join(warn_parts) + "。进退步榜仅基于共同科目计算，仅供参考。"

        # 用交集科目重新计算总分
        student_exam_common = {}  # {student_id: {exam_id: common_subject_total}}
        for s in all_scores:
            if s.subject_id in common_subjects:
                student_exam_common.setdefault(s.student_id, {}).setdefault(s.exam_id, 0)
                student_exam_common[s.student_id][s.exam_id] += s.score

        delta_list = []
        for sid, exam_totals in student_exam_common.items():
            a = exam_totals.get(e_prev.id)
            b = exam_totals.get(e_curr.id)
            if a is not None and b is not None:
                delta_list.append((sid, round(b - a, 1), round(a, 1), round(b, 1)))
        delta_list.sort(key=lambda x: x[1])
        decliners = delta_list[:20]  # 退步最大
        improvers = delta_list[-20:][::-1]  # 进步最大
    else:
        decliners, improvers = [], []

    # ── 学生姓名映射 ── 班主任只能看本班学生
    student_map = {}
    student_q = Student.query.filter_by(grade_id=grade_id, is_active=True)
    if role == "class_teacher" and my_class_id:
        student_q = student_q.filter_by(class_id=my_class_id)
    for st in student_q.all():
        student_map[st.id] = {
            "name": st.name,
            "student_no": st.student_no,
            "class_name": st.class_.name if st.class_ else "—",
            "class_id": st.class_id,
        }

    # ── 班级均分对比数据 (Chart.js) ──
    chart_labels = [e.name for e in exams]
    chart_datasets = []
    colors = ["#4e79a7","#f28e2b","#e15759","#76b7b2","#59a14f","#edc948","#b07aa1","#ff9da7"]
    for i, cls in enumerate(classes):
        data = [class_exam_avgs.get(cls.id, {}).get(eid) for eid in exam_ids]
        chart_datasets.append({
            "label": cls.name,
            "data": [d if d else None for d in data],
            "borderColor": colors[i % len(colors)],
            "backgroundColor": colors[i % len(colors)] + "33",
            "tension": 0.3,
            "fill": False,
        })

    # ── 科目雷达图数据 (各班期末各科均分, 仅限最近1场) ──
    last_exam = exams[-1]
    radar_labels = [s.name for s in subjects]
    radar_datasets = []
    for i, cls in enumerate(classes):
        data = [class_exam_subject_avgs.get(cls.id, {}).get(last_exam.id, {}).get(s.id)
                for s in subjects]
        radar_datasets.append({
            "label": cls.name,
            "data": [d if d else 0 for d in data],
            "borderColor": colors[i % len(colors)],
            "backgroundColor": colors[i % len(colors)] + "44",
        })

    return render_template(
        "scores/comparison.html",
        exams=exams, classes=classes, subjects=subjects,
        class_exam_avgs=class_exam_avgs,
        class_exam_subject_avgs=class_exam_subject_avgs,
        student_exam_total=student_exam_total,
        student_exam_subject=student_exam_subject,
        student_map=student_map,
        improvers=improvers, decliners=decliners,
        subject_count_warning=subject_count_warning,
        chart_labels=chart_labels, chart_datasets=chart_datasets,
        radar_labels=radar_labels, radar_datasets=radar_datasets,
        last_exam=last_exam,
        view_class_id=view_class_id, view_subject_id=view_subject_id,
        grade_id=grade_id,
    )


# ── 批量删除成绩 ──
@scores_bp.route("/exams/<int:eid>/batch-delete", methods=["POST"])
@login_required
@require_role("ms_admin", "grade_leader", "class_teacher")
def batch_delete_scores(eid):
    """批量删除选中成绩（JSON: {score_ids: [...]}）"""
    exam = Exam.query.get_or_404(eid)

    # 权限检查
    if session.get("role") not in ("ms_admin", "grade_leader", "class_teacher"):
        return jsonify({"code": 1, "msg": "无权操作"})

    data = request.get_json(force=True)
    score_ids = data.get("score_ids", [])

    if not score_ids:
        return jsonify({"code": 1, "msg": "未选择任何成绩记录"})

    q = Score.query.filter(Score.id.in_(score_ids), Score.exam_id == eid)
    # 班主任只能删除本班成绩
    if session.get("role") == "class_teacher":
        q = q.filter(Score.class_id == session.get("class_id"))
    deleted = q.delete(synchronize_session=False)
    safe_commit()

    return jsonify({
        "code": 0,
        "msg": f"已删除 {deleted} 条成绩记录",
        "deleted_count": deleted,
    })


@scores_bp.route("/exams/<int:eid>/scores/delete", methods=["POST"])
@login_required
@require_role("ms_admin", "grade_leader", "class_teacher")
def delete_score(eid):
    """删除单条成绩"""
    exam = Exam.query.get_or_404(eid)
    student_id = request.form.get("student_id", type=int)
    subject_id = request.form.get("subject_id", type=int)
    if not student_id or not subject_id:
        flash("参数不完整", "warning")
        return redirect(url_for("scores.score_input", eid=eid))
    score = Score.query.filter_by(
        exam_id=eid, student_id=student_id, subject_id=subject_id
    ).first()
    if score:
        # 班主任只能删除本班成绩
        if session.get("role") == "class_teacher" and score.class_id != session.get("class_id"):
            flash("无权操作", "danger")
            return redirect(url_for("scores.score_input", eid=eid))
        db.session.delete(score)
        safe_commit()
        flash("成绩已删除", "success")
    else:
        flash("未找到该成绩记录", "warning")
    return redirect(url_for("scores.score_input", eid=eid))


@scores_bp.route("/exams/<int:eid>/students/<int:sid>/delete", methods=["POST"])
@login_required
def delete_student_scores(eid, sid):
    """删除某学生在某场考试的所有成绩"""
    exam = Exam.query.get_or_404(eid)
    # 权限检查
    if session.get("role") not in ("ms_admin", "grade_leader", "class_teacher"):
        flash("无权操作", "danger")
        return redirect(url_for("scores.score_input", eid=eid))
    if session.get("role") == "class_teacher":
        stu = Student.query.get(sid)
        if not stu or stu.class_id != session.get("class_id"):
            flash("只能删除本班学生的成绩", "danger")
            return redirect(url_for("scores.score_input", eid=eid))
    # 删除该学生该考试所有成绩
    deleted = Score.query.filter_by(exam_id=eid, student_id=sid).delete()
    safe_commit()
    flash("已删除该学生所有成绩（共 %d 条）" % deleted, "success")
    return redirect(url_for("scores.score_input", eid=eid))


# ══════════════════════════════════════════════════════════════
#  成绩趋势线 — 个体追踪/多生对比/成绩预测
# ══════════════════════════════════════════════════════════════

def _linear_regression(x, y):
    """简单线性回归，返回 (斜率, 截距, R²)"""
    n = len(x)
    if n < 2:
        return 0, y[0] if y else 0, 0
    sum_x = sum(x)
    sum_y = sum(y)
    sum_xy = sum(xi * yi for xi, yi in zip(x, y))
    sum_x2 = sum(xi * xi for xi in x)
    sum_y2 = sum(yi * yi for yi in y)

    denom = n * sum_x2 - sum_x * sum_x
    if denom == 0:
        return 0, sum_y / n, 0
    slope = (n * sum_xy - sum_x * sum_y) / denom
    intercept = (sum_y - slope * sum_x) / n

    # R² 决定系数
    y_mean = sum_y / n
    ss_res = sum((yi - (slope * xi + intercept)) ** 2 for xi, yi in zip(x, y))
    ss_tot = sum((yi - y_mean) ** 2 for yi in y)
    r2 = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0

    return round(slope, 2), round(intercept, 1), round(r2, 3)


@scores_bp.route("/trend")
@login_required
def trend():
    """成绩趋势线页面 — 学生搜索入口"""
    role = session.get("role", "")
    my_class_id = session.get("class_id")
    my_grade_id = session.get("grade_id")

    grade_id = session.get("grade_id") or request.args.get("grade_id", type=int)
    if not grade_id:
        g = Grade.query.order_by(Grade.sort_order).first()
        grade_id = g.id if g else 1

    # 班主任强制限制在自己班级
    if role == "class_teacher" and my_class_id:
        grade_id = my_grade_id or grade_id
        classes = [Class.query.get(my_class_id)] if my_class_id else []
    else:
        classes = Class.query.filter_by(grade_id=grade_id, is_active=True).order_by(Class.name).all()

    exams = Exam.query.filter_by(grade_id=grade_id).order_by(Exam.exam_date.asc()).all()
    subjects = Subject.query.order_by(Subject.sort_order).all()

    # 预加载所有学生（按班级分组），供前端JS使用 — 班主任只能看本班
    student_q = Student.query.filter_by(grade_id=grade_id, is_active=True)
    if role == "class_teacher" and my_class_id:
        student_q = student_q.filter_by(class_id=my_class_id)
    all_students = student_q.order_by(Student.student_no).all()

    students_json = []
    for st in all_students:
        students_json.append({
            "id": st.id,
            "name": st.name,
            "class_id": st.class_id,
            "student_no": st.student_no,
        })

    return render_template(
        "scores/trend.html",
        classes=classes, exams=exams, subjects=subjects,
        grade_id=grade_id,
        students_json=students_json,
    )


@scores_bp.route("/trend/api/student/<int:sid>")
@login_required
def trend_api_student(sid):
    """API: 单个学生成绩趋势数据（总分+各科）"""
    student = Student.query.get_or_404(sid)

    # 权限：班主任只能看本班
    if session.get("role") == "class_teacher" and student.class_id != session.get("class_id"):
        return jsonify({"code": 1, "msg": "无权查看该学生数据"})

    grade_id = student.grade_id
    exams = Exam.query.filter_by(grade_id=grade_id).order_by(Exam.exam_date.asc()).all()
    subjects = Subject.query.order_by(Subject.sort_order).all()

    exam_ids = [e.id for e in exams]
    all_scores = Score.query.filter(
        Score.student_id == sid,
        Score.exam_id.in_(exam_ids),
    ).all()

    # 总分趋势
    exam_total = {}  # {exam_id: total}
    for s in all_scores:
        exam_total[s.exam_id] = exam_total.get(s.exam_id, 0) + s.score

    total_trend = []
    for e in exams:
        t = exam_total.get(e.id)
        total_trend.append({
            "exam_id": e.id,
            "exam_name": e.name,
            "exam_date": e.exam_date.strftime("%Y-%m-%d") if e.exam_date else "",
            "total": round(t, 1) if t else None,
        })

    # 各科趋势
    subject_trends = {}
    for sub in subjects:
        sub_data = []
        for e in exams:
            sc = next((s.score for s in all_scores
                       if s.exam_id == e.id and s.subject_id == sub.id), None)
            sub_data.append({
                "exam_id": e.id,
                "exam_name": e.name,
                "exam_date": e.exam_date.strftime("%Y-%m-%d") if e.exam_date else "",
                "score": round(sc, 1) if sc is not None else None,
            })
        # 只返回有数据的科目
        if any(d["score"] is not None for d in sub_data):
            subject_trends[sub.name] = sub_data

    # 班级排名趋势
    rank_trend = []
    for e in exams:
        scores_in_exam = [s for s in all_scores if s.exam_id == e.id]
        if scores_in_exam:
            rank_trend.append({
                "exam_id": e.id,
                "exam_name": e.name,
                "rank_class": scores_in_exam[0].rank_class or None,
                "rank_grade": scores_in_exam[0].rank_grade or None,
            })

    return jsonify({
        "code": 0,
        "data": {
            "student": {
                "id": student.id,
                "name": student.name,
                "student_no": student.student_no,
                "class_name": student.class_.name if student.class_ else "",
            },
            "total_trend": total_trend,
            "subject_trends": subject_trends,
            "rank_trend": rank_trend,
            "subject_labels": [s.name for s in subjects],
        }
    })


@scores_bp.route("/trend/api/compare", methods=["POST"])
@login_required
def trend_api_compare():
    """API: 多学生总分趋势对比（最多3人）"""
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"code": 1, "msg": "Invalid JSON"}), 400
    sids = data.get("student_ids", [])[:3]  # 最多3人

    if not sids:
        return jsonify({"code": 1, "msg": "请选择至少1名学生"})

    students = Student.query.filter(Student.id.in_(sids)).all()
    if len(students) < len(sids):
        return jsonify({"code": 1, "msg": "部分学生不存在"})

    # 统一取第一个学生的年级考试
    grade_id = students[0].grade_id
    exams = Exam.query.filter_by(grade_id=grade_id).order_by(Exam.exam_date.asc()).all()
    exam_ids = [e.id for e in exams]

    exam_labels = [e.name for e in exams]
    student_data = []

    colors = ["#4e79a7", "#f28e2b", "#e15759"]
    for i, stu in enumerate(students):
        scores = Score.query.filter(
            Score.student_id == stu.id,
            Score.exam_id.in_(exam_ids),
        ).all()

        exam_total = {}
        for s in scores:
            exam_total[s.exam_id] = exam_total.get(s.exam_id, 0) + s.score

        totals = [round(exam_total.get(eid), 1) if eid in exam_total else None
                  for eid in exam_ids]

        student_data.append({
            "id": stu.id,
            "name": stu.name,
            "class_name": stu.class_.name if stu.class_ else "",
            "totals": totals,
            "color": colors[i % len(colors)],
        })

    return jsonify({
        "code": 0,
        "data": {
            "exam_labels": exam_labels,
            "students": student_data,
        }
    })


@scores_bp.route("/trend/api/prediction/<int:sid>")
@login_required
def trend_api_prediction(sid):
    """API: 成绩预测 — 基于历史总分线性回归"""
    student = Student.query.get_or_404(sid)
    if session.get("role") == "class_teacher" and student.class_id != session.get("class_id"):
        return jsonify({"code": 1, "msg": "无权查看"})

    exams = Exam.query.filter_by(grade_id=student.grade_id).order_by(Exam.exam_date.asc()).all()
    exam_ids = [e.id for e in exams]

    all_scores = Score.query.filter(
        Score.student_id == sid,
        Score.exam_id.in_(exam_ids),
    ).all()

    exam_total = {}
    for s in all_scores:
        exam_total[s.exam_id] = exam_total.get(s.exam_id, 0) + s.score

    # 需要至少2场考试有成绩
    valid_exams = [(i + 1, exam_total[e.id]) for i, e in enumerate(exams) if e.id in exam_total]
    if len(valid_exams) < 2:
        return jsonify({"code": 1, "msg": "历史成绩不足（需要至少2场考试），无法预测"})

    x = [ve[0] for ve in valid_exams]
    y = [ve[1] for ve in valid_exams]
    slope, intercept, r2 = _linear_regression(x, y)

    # 预测下一场考试
    next_x = len(exams) + 1
    predicted = round(slope * next_x + intercept, 1)

    # 趋势方向
    if slope > 2:
        trend_label = "上升"
        trend_icon = "arrow-up-circle"
        trend_color = "success"
    elif slope < -2:
        trend_label = "下降"
        trend_icon = "arrow-down-circle"
        trend_color = "danger"
    else:
        trend_label = "平稳"
        trend_icon = "dash-circle"
        trend_color = "secondary"

    return jsonify({
        "code": 0,
        "data": {
            "slope": slope,
            "intercept": intercept,
            "r2": r2,
            "predicted_score": predicted,
            "trend_label": trend_label,
            "trend_icon": trend_icon,
            "trend_color": trend_color,
            "exam_count": len(exams),
            "predicted_exam_num": next_x,
            "regression_points": [
                {"x": xi, "y": round(slope * xi + intercept, 1)}
                for xi in range(1, next_x + 1)
            ],
        }
    })

