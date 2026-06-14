"""认证模块 — 登录/退出/改密码/账号管理"""
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from models import db, User, ROLES
from decorators import login_required, require_role
from blueprints.audit_log import audit_log
from datetime import datetime
from utils.db_utils import safe_commit

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login_page():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username, is_active=True).first()
        if user and user.check_password(password):
            session["logged_in"] = True
            session["user_id"] = user.id
            session["username"] = user.username
            session["display_name"] = user.display_name
            session["role"] = user.role
            session["grade_id"] = user.grade_id
            session["class_id"] = user.class_id
            session["bound_student_id"] = user.bound_student_id
            user.last_login = datetime.utcnow()
            safe_commit()
            next_url = request.args.get("next") or url_for("index")
            return redirect(next_url)
        flash("用户名或密码错误", "danger")
    return render_template("login.html")


@auth_bp.route("/logout")
def logout():
    session.clear()
    flash("已安全退出", "info")
    return redirect(url_for("auth.login_page"))


@auth_bp.route("/accounts/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        old_pw = request.form.get("old_password", "")
        new_pw = request.form.get("new_password", "")
        confirm = request.form.get("confirm_password", "")
        user = User.query.get(session.get("user_id"))
        if not user.check_password(old_pw):
            flash("原密码错误", "danger")
        elif new_pw != confirm:
            flash("两次新密码不一致", "danger")
        elif len(new_pw) < 6:
            flash("密码至少6位", "danger")
        else:
            user.set_password(new_pw)
            safe_commit()
            flash("密码修改成功", "success")
            return redirect(url_for("index"))
    return render_template("accounts/change_password.html")


@auth_bp.route("/accounts")
@require_role("ms_admin")
def account_list():
    users = User.query.order_by(User.role, User.username).all()
    return render_template("accounts/list.html", users=users, ROLES=ROLES)


@auth_bp.route("/accounts/create", methods=["POST"])
@require_role("ms_admin")
def create_account():
    data = request.get_json() if request.is_json else request.form
    username = data.get("username", "").strip()
    if User.query.filter_by(username=username).first():
        return jsonify({"error": "用户名已存在"}), 400
    user = User(
        username=username,
        display_name=data.get("display_name", username),
        role=data.get("role", "teacher"),
        grade_id=data.get("grade_id") or None,
        class_id=data.get("class_id") or None,
        bound_student_id=data.get("bound_student_id") or None,
        phone=data.get("phone") or None,
    )
    user.set_password(data.get("password", "123456"))
    db.session.add(user)
    safe_commit()
    return jsonify({"ok": True, "id": user.id})


@auth_bp.route("/accounts/<int:uid>/toggle", methods=["POST"])
@require_role("ms_admin")
def toggle_account(uid):
    user = User.query.get_or_404(uid)
    user.is_active = not user.is_active
    safe_commit()
    return jsonify({"ok": True, "is_active": user.is_active})


@auth_bp.route("/accounts/<int:uid>/reset-password", methods=["POST"])
@require_role("ms_admin")
@audit_log("reset_password", "User")
def reset_password(uid):
    user = User.query.get_or_404(uid)
    user.set_password("123456")
    safe_commit()
    return jsonify({"ok": True, "message": "密码已重置为 123456"})


@auth_bp.route("/accounts/<int:uid>/delete", methods=["POST"])
@require_role("ms_admin")
@audit_log("delete", "User")
def delete_account(uid):
    """软删除账号：禁用登录 + 清除敏感字段，保留历史数据"""
    my_id = session.get("user_id")
    if uid == my_id:
        return jsonify({"error": "不能删除自己当前登录的账号"}), 400

    # 防止删除最后一个德育处管理员
    if User.query.filter_by(role="ms_admin", is_active=True).count() <= 1:
        target = User.query.get_or_404(uid)
        if target.role == "ms_admin":
            return jsonify({"error": "不能删除最后一个德育处管理员账号"}), 400

    user = User.query.get_or_404(uid)
    # 软删除：禁用登录，用户名加后缀避免冲突，清除手机号
    user.is_active = False
    user.username = f"{user.username}_deleted_{user.id}"
    user.phone = None
    safe_commit()
    return jsonify({"ok": True, "message": f"账号 {user.display_name} 已删除"})
