"""操作审计日志"""
from flask import Blueprint, render_template, request
from datetime import datetime

from decorators import login_required, require_role
from models import db, AuditLog

audit_bp = Blueprint("audit", __name__, url_prefix="/audit")


@audit_bp.route("/")
@login_required
@require_role("ms_admin")
def index():
    """审计日志列表"""
    page = request.args.get("page", 1, type=int)
    per_page = 50

    query = AuditLog.query

    # filters
    username = request.args.get("username", "")
    action = request.args.get("action", "")
    target_type = request.args.get("target_type", "")
    date_from = request.args.get("date_from", "")
    date_to = request.args.get("date_to", "")

    if username:
        query = query.filter(AuditLog.username.contains(username))
    if action:
        query = query.filter(AuditLog.action == action)
    if target_type:
        query = query.filter(AuditLog.target_type == target_type)
    if date_from:
        query = query.filter(AuditLog.created_at >= datetime.strptime(date_from, "%Y-%m-%d"))
    if date_to:
        query = query.filter(AuditLog.created_at <= datetime.strptime(date_to + " 23:59:59", "%Y-%m-%d %H:%M:%S"))

    pagination = query.order_by(AuditLog.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return render_template("audit/index.html",
                           logs=pagination.items,
                           pagination=pagination,
                           username=username, action=action,
                           target_type=target_type,
                           date_from=date_from, date_to=date_to)
