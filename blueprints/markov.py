"""
Markov Chain Event Horizon Blueprint
数学学力"事件视界" - Flask蓝图
VERSION 3.0 — 对齐暗色战情模板字段 + 全局矩阵端点
"""
from flask import Blueprint, jsonify, render_template, request, session, current_app
from functools import wraps

bp = Blueprint("markov", __name__, template_folder="../templates")


def _require_role(*allowed_roles):
    """权限装饰器 — 基于session认证"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not session.get("logged_in"):
                return jsonify({"error": "未登录"}), 401
            if session.get("role") not in allowed_roles:
                return jsonify({"error": "权限不足"}), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator


@bp.route("/event-horizon/scan")
@_require_role("ms_admin", "grade_leader", "class_teacher")
def scan_event_horizon():
    """
    API：扫描事件视界预警名单
    参数：
      - class_id: 班级ID (可选)
      - subject: 科目名称（默认"数学"）
      - top_n: 返回前N名（默认0=全部）
    返回：{subject, total_warnings, warnings: [{name, warning_state, fall_to_s1_prob, current_score, ...}]}
    """
    from markov_engine import scan_all_students

    class_id = request.args.get("class_id", type=int)
    subject = request.args.get("subject", "数学")
    top_n = request.args.get("top_n", 0, type=int)

    try:
        warnings = scan_all_students(class_id=class_id, subject_name=subject, top_n=top_n)
        return jsonify({
            "subject": subject,
            "total_warnings": len(warnings),
            "warnings": warnings
        })
    except Exception as e:
        current_app.logger.error(f"Markov scan error: {e}")
        return jsonify({"error": str(e)}), 500


@bp.route("/event-horizon/matrix")
@_require_role("ms_admin", "grade_leader", "class_teacher")
def global_matrix():
    """
    API：获取全校全局Markov状态转移矩阵 (3x3子集: S1/S2/S3)
    参数：
      - subject: 科目名称（默认"数学"）
    返回：{matrix: [[p00,p01,p02],[p10,p11,p12],[p20,p21,p22]], counts, student_count, total_transitions}
    """
    from markov_engine import build_global_matrix

    subject = request.args.get("subject", "数学")

    try:
        result = build_global_matrix(subject)
        if not result:
            return jsonify({"error": "无数据", "matrix": [[0]*3]*3, "student_count": 0, "total_transitions": 0})

        # 返回 S1/S2/S3 的 3x3 子矩阵
        full_matrix = result["matrix"]
        sub_matrix = [row[:3] for row in full_matrix[:3]]
        sub_counts = result["counts"][:3]

        return jsonify({
            "matrix": sub_matrix,
            "counts": sub_counts,
            "student_count": result["student_count"],
            "total_transitions": result["total_transitions"]
        })
    except Exception as e:
        current_app.logger.error(f"Markov matrix error: {e}")
        return jsonify({"error": str(e)}), 500


@bp.route("/event-horizon/student/<int:student_id>")
@_require_role("ms_admin", "grade_leader", "class_teacher")
def student_event_horizon(student_id):
    """
    API：获取单个学生的详细分析
    参数：
      - subject: 科目名称（默认"数学"）
    """
    from markov_engine import compute_event_horizon

    subject = request.args.get("subject", "数学")

    try:
        result = compute_event_horizon(student_id, subject)
        if not result:
            return jsonify({"error": "数据不足，无法分析"}), 400
        return jsonify(result)
    except Exception as e:
        current_app.logger.error(f"Markov student analysis error: {e}")
        return jsonify({"error": str(e)}), 500


@bp.route("/event-horizon/dashboard")
@_require_role("ms_admin", "grade_leader", "class_teacher")
def dashboard():
    """渲染事件视界仪表盘页面（暗色战情主题）"""
    from models import Class

    classes = Class.query.order_by(Class.name).all()
    return render_template("markov/event_horizon_dashboard.html", classes=classes)


@bp.route("/event-horizon/version")
@_require_role("ms_admin")
def markov_version():
    """检查markov_engine版本"""
    import markov_engine
    version = getattr(markov_engine, "VERSION", "unknown")
    return jsonify({"version": version})
