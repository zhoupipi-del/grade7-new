"""系统配置中心 — 学期管理 + 参数配置"""
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from models import db, Semester, SystemConfig
from decorators import login_required, require_role
from utils.db_utils import safe_commit

system_config_bp = Blueprint("system_config", __name__, template_folder="../templates")


@system_config_bp.route("/")
@login_required
@require_role("ms_admin", "grade_leader")
def index():
    """系统配置首页 → 重定向到学期管理"""
    return redirect(url_for("system_config.semesters"))


# ── 学期管理 ────────────────────────────────────────────────────────────────────

@system_config_bp.route("/semesters")
@login_required
@require_role("ms_admin")
def semesters():
    semesters = Semester.query.order_by(Semester.start_date.desc()).all()
    return render_template("system_config/semesters.html", semesters=semesters)


@system_config_bp.route("/semester/create", methods=["GET", "POST"])
@login_required
@require_role("ms_admin")
def create_semester():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        display_name = request.form.get("display_name", "").strip()
        start_date = request.form.get("start_date", "")
        end_date = request.form.get("end_date", "")
        is_current = request.form.get("is_current") == "on"

        if not name or not start_date or not end_date:
            flash("请填写完整信息", "warning")
            return redirect(url_for("system_config.create_semester"))

        if is_current:
            Semester.query.update({Semester.is_current: False})

        semester = Semester(
            name=name,
            display_name=display_name or name,
            start_date=datetime.strptime(start_date, "%Y-%m-%d").date(),
            end_date=datetime.strptime(end_date, "%Y-%m-%d").date(),
            is_current=is_current,
        )
        db.session.add(semester)
        safe_commit()
        flash(f"学期 [{semester.display_name}] 创建成功", "success")
        return redirect(url_for("system_config.semesters"))

    return render_template("system_config/semester_form.html", semester=None)


@system_config_bp.route("/semester/<int:sid>/edit", methods=["GET", "POST"])
@login_required
@require_role("ms_admin")
def edit_semester(sid):
    semester = Semester.query.get_or_404(sid)

    if request.method == "POST":
        semester.name = request.form.get("name", semester.name).strip()
        semester.display_name = request.form.get("display_name", semester.display_name).strip()
        start_date = request.form.get("start_date", "")
        end_date = request.form.get("end_date", "")
        is_current = request.form.get("is_current") == "on"

        if start_date:
            semester.start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
        if end_date:
            semester.end_date = datetime.strptime(end_date, "%Y-%m-%d").date()

        if is_current:
            Semester.query.filter(Semester.id != sid).update({Semester.is_current: False})
            semester.is_current = True
        else:
            semester.is_current = False

        safe_commit()
        flash(f"学期 [{semester.display_name}] 更新成功", "success")
        return redirect(url_for("system_config.semesters"))

    return render_template("system_config/semester_form.html", semester=semester)


@system_config_bp.route("/semester/<int:sid>/activate", methods=["POST"])
@login_required
@require_role("ms_admin")
def activate_semester(sid):
    Semester.query.update({Semester.is_current: False})
    semester = Semester.query.get_or_404(sid)
    semester.is_current = True
    safe_commit()
    flash(f"已将 [{semester.display_name}] 设为当前学期", "success")
    return redirect(url_for("system_config.semesters"))


@system_config_bp.route("/semester/<int:sid>/delete", methods=["POST"])
@login_required
@require_role("ms_admin")
def delete_semester(sid):
    semester = Semester.query.get_or_404(sid)
    if semester.is_current:
        flash("不能删除当前学期", "danger")
        return redirect(url_for("system_config.semesters"))
    db.session.delete(semester)
    safe_commit()
    flash(f"学期 [{semester.display_name}] 已删除", "success")
    return redirect(url_for("system_config.semesters"))


# ── 系统参数配置 ────────────────────────────────────────────────────────────────

@system_config_bp.route("/config")
@login_required
@require_role("ms_admin", "grade_leader")
def config_list():
    configs = SystemConfig.query.order_by(SystemConfig.category, SystemConfig.key).all()
    # 按category分组
    config_by_category = {}
    for c in configs:
        config_by_category.setdefault(c.category, []).append(c)
    return render_template("system_config/config.html", config_by_category=config_by_category)


@system_config_bp.route("/config/create", methods=["GET", "POST"])
@login_required
@require_role("ms_admin", "grade_leader")
def create_config():
    if request.method == "POST":
        key = request.form.get("key", "").strip()
        value = request.form.get("value", "").strip()
        category = request.form.get("category", "general")
        description = request.form.get("description", "").strip()

        if not key:
            flash("配置键不能为空", "warning")
            return redirect(url_for("system_config.create_config"))

        if SystemConfig.query.filter_by(key=key).first():
            flash(f"配置键 [{key}] 已存在", "danger")
            return redirect(url_for("system_config.create_config"))

        config = SystemConfig(
            key=key,
            value=value,
            category=category,
            description=description,
            updated_by=current_user.display_name,
        )
        db.session.add(config)
        safe_commit()
        flash(f"配置项 [{key}] 创建成功", "success")
        return redirect(url_for("system_config.config_list"))

    return render_template("system_config/config_form.html", config=None)


@system_config_bp.route("/config/edit/<int:cid>", methods=["GET", "POST"])
@login_required
@require_role("ms_admin", "grade_leader")
def edit_config(cid):
    config = SystemConfig.query.get_or_404(cid)

    if request.method == "POST":
        config.value = request.form.get("value", config.value).strip()
        config.category = request.form.get("category", config.category)
        config.description = request.form.get("description", config.description).strip()
        config.updated_by = current_user.display_name
        config.updated_at = datetime.utcnow()
        safe_commit()
        flash(f"配置项 [{config.key}] 更新成功", "success")
        return redirect(url_for("system_config.config_list"))

    return render_template("system_config/config_form.html", config=config)


@system_config_bp.route("/config/delete/<int:cid>", methods=["POST"])
@login_required
@require_role("ms_admin")
def delete_config(cid):
    config = SystemConfig.query.get_or_404(cid)
    db.session.delete(config)
    safe_commit()
    flash(f"配置项 [{config.key}] 已删除", "success")
    return redirect(url_for("system_config.config_list"))


@system_config_bp.route("/config/init", methods=["GET", "POST"])
@login_required
@require_role("ms_admin")
def init_config():
    """初始化默认配置项"""
    defaults = [
        ("site_name", "梨江中学德育管理平台", "general", "系统名称"),
        ("academic_year", "2025-2026", "general", "当前学年"),
        ("score_entry_deadline", "17:00", "score", "成绩录入截止时间"),
        ("allow_modify_score", "true", "score", "允许修改成绩"),
        ("late_threshold", "10", "attendance", "迟到阈值（分钟）"),
        ("early_leave_threshold", "5", "attendance", "早退阈值（分钟）"),
        ("notify_parent_auto", "true", "notification", "自动通知家长"),
        ("notify_teacher_on_discipline", "true", "notification", "违纪时通知教师"),
    ]

    added = 0
    for key, value, category, description in defaults:
        if not SystemConfig.query.filter_by(key=key).first():
            config = SystemConfig(
                key=key,
                value=value,
                category=category,
                description=description,
                updated_by=current_user.display_name,
            )
            db.session.add(config)
            added += 1

    safe_commit()
    flash(f"已初始化 {added} 个默认配置项", "success")
    return redirect(url_for("system_config.config_list"))
