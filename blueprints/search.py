"""
全局搜索蓝图
提供全局搜索页面和 API
"""
from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for
from models import Student, User, Class, Grade, db
from decorators import login_required, require_role

search_bp = Blueprint("search", __name__)  # url_prefix 由 blueprint_registry.py 统一管理


# ── 路由 ──


@search_bp.route("/page")
@login_required
def search_page():
    """
    全局搜索页面
    GET /search/page?q=xxx&type=student
    """
    q = request.args.get("q", "").strip()
    type_ = request.args.get("type", "student")

    results = []
    if q:
        results = perform_search(q, type_)

    return render_template(
        "search/page.html",
        q=q,
        type=type_,
        results=results,
        title="全局搜索"
    )


@search_bp.route("/api")
@login_required
def api():
    """
    全局搜索 API（供前端 AJAX 调用）
    GET /search/api?q=xxx&type=student

    返回 JSON:
    {
        "results": [...],
        "total": 100
    }
    """
    q = request.args.get("q", "").strip()
    type_ = request.args.get("type", "student")
    limit = request.args.get("limit", 20, type=int)

    if not q:
        return jsonify({"results": [], "total": 0})

    results = perform_search(q, type_, limit=limit)
    total = len(results)  # 简化：实际应该单独查询 count

    return jsonify({
        "results": results,
        "total": total
    })


# ── 搜索逻辑 ──


def perform_search(q, type_, limit=20):
    """
    执行搜索

    :param q: 搜索关键词
    :param type_: 搜索类型 (student/parent/teacher/class)
    :param limit: 返回结果数量限制
    :return: 结果列表
    """
    results = []

    if type_ == "student":
        # 搜索学生
        query = Student.query.filter(
            Student.is_active == True,
            Student.name.contains(q)
        ).limit(limit)

        for s in query.all():
            class_name = s.class_.name if s.class_ else "未分配"
            results.append({
                "id": s.id,
                "name": s.name,
                "type": "student",
                "class_name": class_name,
                "url": url_for("class.student_detail", sid=s.id) if s.class_id else "#"
            })

    elif type_ == "parent":
        # 搜索家长（User 表中 role=parent）
        query = User.query.filter(
            User.role == "parent",
            User.username.contains(q)
        ).limit(limit)

        for u in query:
            student_name = u.student.name if u.student else "未知"
            results.append({
                "id": u.id,
                "name": u.username,
                "type": "parent",
                "student_name": student_name,
                "url": "#"  # TODO: 家长详情页
            })

    elif type_ == "teacher":
        # 搜索教师（User 表中 role=class_teacher/grade_leader/ms_admin）
        query = User.query.filter(
            User.role.in_(["class_teacher", "grade_leader", "ms_admin"]),
            User.username.contains(q)
        ).limit(limit)

        for u in query:
            results.append({
                "id": u.id,
                "name": u.username,
                "type": "teacher",
                "role": u.role,
                "url": "#"  # TODO: 教师详情页
            })

    elif type_ == "class":
        # 搜索班级
        query = Class.query.filter(
            Class.is_active == True,
            Class.name.contains(q)
        ).limit(limit)

        for c in query:
            grade_name = c.grade.name if c.grade else "未知"
            results.append({
                "id": c.id,
                "name": c.name,
                "type": "class",
                "grade_name": grade_name,
                "url": url_for("grade.class_detail", class_id=c.id) if c.grade_id else "#"
            })

    return results


# ── 快捷搜索（供导航栏使用）──


@search_bp.route("/quick")
@login_required
def quick():
    """
    快捷搜索 API（导航栏实时搜索）
    GET /search/quick?q=xxx

    返回简化的 JSON，用于下拉菜单
    """
    q = request.args.get("q", "").strip()
    if not q or len(q) < 2:
        return jsonify([])

    # 搜索学生（限制 5 条）
    students = Student.query.filter(
        Student.is_active == True,
        Student.name.contains(q)
    ).limit(5).all()

    results = []
    for s in students:
        class_name = s.class_.name if s.class_ else "未分配"
        results.append({
            "id": s.id,
            "name": s.name,
            "type": "student",
            "subtitle": class_name,
            "url": url_for("class.student_detail", sid=s.id) if s.class_id else "#"
        })

    return jsonify(results)
