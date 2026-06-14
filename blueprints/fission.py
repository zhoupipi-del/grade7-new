"""
方向十：群体违纪"链式核裂变"溯源引擎 — Flask蓝图
Chain Fission Trace Engine Blueprint
"""
from flask import Blueprint, jsonify, render_template, request, session, current_app
from functools import wraps

from utils import get_local_now

bp = Blueprint("fission", __name__, template_folder="../templates")


def _require_role(*allowed_roles):
    """权限装饰器"""
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


@bp.route("/trace")
@_require_role("ms_admin", "grade_leader")
def trace_super_source():
    """
    API：执行链式核裂变溯源
    参数：
      - class_id: 重点排查班级 (可选)
      - days: 回溯天数 (默认30)
    返回：{ super_sources, chain_events, summary }
    """
    from fission_engine import trace_fission_chain
    from datetime import datetime, timedelta

    class_id = request.args.get("class_id", type=int)
    days = request.args.get("days", 30, type=int)
    end_date = get_local_now()
    start_date = end_date - timedelta(days=days)

    try:
        result = trace_fission_chain(
            subject_class_id=class_id,
            start_date=start_date,
            end_date=end_date
        )
        return jsonify(result)
    except Exception as e:
        current_app.logger.error(f"Fission trace error: {e}")
        return jsonify({"error": str(e)}), 500


@bp.route("/summary")
@_require_role("ms_admin", "grade_leader", "class_teacher")
def fission_summary():
    """
    API：获取简化版溯源摘要
    参数：
      - class_id: 班级 (可选)
    返回：{ summary, top_sources, total_chains, total_records }
    """
    from fission_engine import get_fission_summary

    class_id = request.args.get("class_id", type=int)

    try:
        result = get_fission_summary(class_id)
        return jsonify(result)
    except Exception as e:
        current_app.logger.error(f"Fission summary error: {e}")
        return jsonify({"error": str(e)}), 500


@bp.route("/dashboard")
@_require_role("ms_admin", "grade_leader")
def dashboard():
    """渲染链式核裂变溯源仪表盘"""
    from models import Class
    classes = Class.query.order_by(Class.name).all()
    return render_template("fission/dashboard.html", classes=classes)
