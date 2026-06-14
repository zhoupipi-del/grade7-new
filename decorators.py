"""全局权限管理系统 — 装饰器 + 权限注册表 + 审计日志"""

from functools import wraps
from flask import session, redirect, url_for, flash, request, jsonify, current_app, g
from datetime import datetime
import json

# ─────────────────────────────────────────
# 1. 权限注册表（Permission Registry）
# ─────────────────────────────────────────

class PermissionRegistry:
    """
    集中管理所有权限标识和使用位置。
    用途：
      - 统一权限检查逻辑
      - 生成权限矩阵报告
      - 方便未来迁移到数据库/Redis
    """
    
    # 所有权限标识的定义
    PERMISSIONS = {
        # ── 成绩管理 ──
        "view_scores": "查看成绩",
        "edit_scores": "编辑成绩",
        "delete_scores": "删除成绩",
        "publish_scores": "发布成绩",
        
        # ── 违纪管理 ──
        "view_discipline": "查看违纪记录",
        "manage_discipline": "管理违纪记录",
        "approve_discipline": "审批违纪处分",
        
        # ── 心理健康 ──
        "view_mental_health": "查看心理健康评估",
        "edit_mental_health": "编辑心理健康评估",
        "view_mental_raw": "查看原始问卷数据",
        
        # ── 综合素质 ──
        "view_quality": "查看综合素质评价",
        "edit_quality": "编辑综合素质评价",
        
        # ── 考勤管理 ──
        "view_attendance": "查看考勤记录",
        "edit_attendance": "编辑考勤记录",
        
        # ── 活动管理 ──
        "view_activities": "查看活动",
        "manage_activities": "管理活动",
        
        # ── 通知管理 ──
        "send_notifications": "发送通知",
        "manage_notices": "管理公告",
        
        # ── 数据导出 ──
        "export_data": "导出数据",
        "export_pdf": "导出PDF",
        "export_excel": "导出Excel",
        
        # ── 系统管理 ──
        "manage_users": "管理用户账号",
        "manage_classes": "管理班级",
        "manage_grades": "管理年级",
        "manage_subjects": "管理科目",
        "view_audit_log": "查看审计日志",
        "manage_system": "系统管理（最高权限）",
        
        # ── 数据大屏 ──
        "view_bigscreen": "查看数据大屏",
        "view_workload": "查看工作量统计",
        
        # ── AI分析 ──
        "view_ai_analysis": "查看AI分析",
        "use_ml_models": "使用ML数学模型",
        
        # ── 成长报告 ──
        "view_growth_report": "查看成长报告",
        "generate_growth_report": "生成成长报告",
    }
    
    # 角色 → 权限列表 映射
    ROLE_PERMISSIONS = {
        "ms_admin": list(PERMISSIONS.keys()),  # 德育处：所有权限
        
        "grade_leader": [
            "view_scores", "edit_scores", "publish_scores",
            "view_discipline", "manage_discipline", "approve_discipline",
            "view_mental_health", "edit_mental_health",
            "view_quality", "edit_quality",
            "view_attendance", "edit_attendance",
            "view_activities", "manage_activities",
            "send_notifications", "manage_notices",
            "export_data", "export_pdf", "export_excel",
            "view_bigscreen", "view_workload",
            "view_ai_analysis", "use_ml_models",
            "view_growth_report", "generate_growth_report",
        ],
        
        "class_teacher": [
            "view_scores", "edit_scores",
            "view_discipline", "manage_discipline",
            "view_mental_health",
            "view_quality", "edit_quality",
            "view_attendance", "edit_attendance",
            "view_activities", "manage_activities",
            "send_notifications",
            "export_data", "export_pdf",
            "view_ai_analysis",
            "view_growth_report",
        ],
        
        "teacher": [
            "view_scores",
            "view_discipline",
            "view_mental_health",
            "view_quality",
            "view_attendance",
            "view_activities",
            "send_notifications",
        ],
        
        "parent": [
            "view_scores",  # 仅自己孩子
            "view_discipline",
            "view_mental_health",
            "view_quality",
            "view_attendance",
            "view_activities",
            "view_growth_report",
        ],
        
        "student": [
            "view_scores",  # 仅自己
            "view_discipline",
            "view_mental_health",
            "view_quality",
            "view_attendance",
            "view_activities",
        ],
    }
    
    @classmethod
    def get_permissions_for_role(cls, role):
        """获取指定角色的所有权限"""
        return cls.ROLE_PERMISSIONS.get(role, [])
    
    @classmethod
    def has_permission(cls, role, permission_name):
        """检查指定角色是否有某个权限"""
        if role not in cls.ROLE_PERMISSIONS:
            return False
        return permission_name in cls.ROLE_PERMISSIONS[role]
    
    @classmethod
    def get_permission_description(cls, permission_name):
        """获取权限描述"""
        return cls.PERMISSIONS.get(permission_name, "未知权限")


# ─────────────────────────────────────────
# 2. 审计日志功能
# ─────────────────────────────────────────

def log_unauthorized_access(user_id, permission_name, endpoint=None):
    """
    记录越权访问尝试（审计日志）。
    未来可扩展到：
      - 写入数据库 audit_log 表
      - 发送安全告警邮件
      - 集成到 ELK / Splunk
    """
    endpoint = endpoint or request.endpoint or "unknown"
    remote_addr = request.remote_addr or "unknown"
    user_agent = request.headers.get("User-Agent", "unknown")
    
    log_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "user_id": user_id,
        "permission_attempted": permission_name,
        "endpoint": endpoint,
        "remote_addr": remote_addr,
        "user_agent": user_agent[:200],  # 截断避免过长
        "severity": "HIGH",  # 越权尝试是高严重级别
    }
    
    # 输出到应用日志
    current_app.logger.warning(
        f"[SECURITY] Unauthorized access attempt: {json.dumps(log_entry, ensure_ascii=False)}"
    )
    
    # TODO:  future: 写入数据库
    # TODO:  future: 发送告警邮件（如果1小时内超过5次尝试）


def log_permission_check(user_id, permission_name, endpoint, result):
    """
    记录权限检查（用于调试和审计）。
    注意：生产环境建议只记录失败案例（上面那个函数），避免日志过大。
    """
    if current_app.debug:
        current_app.logger.debug(
            f"[PERMISSION] user_id={user_id}, "
            f"permission={permission_name}, "
            f"endpoint={endpoint}, "
            f"result={result}"
        )


# ─────────────────────────────────────────
# 3. 权限检查辅助函数
# ─────────────────────────────────────────

def current_user_has_permission(permission_name):
    """
    检查当前登录用户是否有指定权限。
    用法：在视图函数中调用。
    """
    role = session.get("role")
    if not role:
        return False
    return PermissionRegistry.has_permission(role, permission_name)


def get_current_user_permissions():
    """获取当前登录用户的所有权限列表"""
    role = session.get("role")
    if not role:
        return []
    return PermissionRegistry.get_permissions_for_role(role)


# ─────────────────────────────────────────
# 4. 权限装饰器
# ─────────────────────────────────────────

def require_permission(permission_name):
    """
    权限检查装饰器。
    用法：
        @app.route('/scores/edit')
        @require_permission('edit_scores')
        def edit_scores():
            ...
    
    参数：
        permission_name: 权限标识（参见 PermissionRegistry.PERMISSIONS）
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # 1. 检查是否登录
            if not session.get("logged_in"):
                if request.path.startswith("/api/"):
                    return jsonify({"error": "未登录"}), 401
                return redirect(url_for("auth.login_page", next=request.path))
            
            # 2. 检查权限
            role = session.get("role")
            if not PermissionRegistry.has_permission(role, permission_name):
                # 记录越权行为（安全审计）
                user_id = session.get("user_id")
                log_unauthorized_access(user_id, permission_name)
                
                # 返回 403
                if request.path.startswith("/api/"):
                    return jsonify({
                        "error": "权限不足",
                        "required_permission": permission_name,
                        "your_role": role,
                    }), 403
                
                flash(f"您没有权限执行此操作（需要权限：{PermissionRegistry.get_permission_description(permission_name)}）", "danger")
                return redirect(url_for("index"))
            
            # 3. 权限检查通过，记录日志（调试模式）
            user_id = session.get("user_id")
            log_permission_check(user_id, permission_name, request.endpoint, "ALLOW")
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def require_any_permission(*permission_names):
    """
    权限检查装饰器（任一权限即可）。
    用法：
        @require_any_permission('edit_scores', 'manage_scores')
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not session.get("logged_in"):
                if request.path.startswith("/api/"):
                    return jsonify({"error": "未登录"}), 401
                return redirect(url_for("auth.login_page", next=request.path))
            
            role = session.get("role")
            has_any = any(
                PermissionRegistry.has_permission(role, p) 
                for p in permission_names
            )
            
            if not has_any:
                user_id = session.get("user_id")
                log_unauthorized_access(user_id, f"any_of_{permission_names}")
                
                if request.path.startswith("/api/"):
                    return jsonify({
                        "error": "权限不足",
                        "required_permissions": list(permission_names),
                        "your_role": role,
                    }), 403
                
                flash("您没有权限执行此操作", "danger")
                return redirect(url_for("index"))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def require_all_permissions(*permission_names):
    """
    权限检查装饰器（需要所有权限）。
    用法：
        @require_all_permissions('view_scores', 'export_data')
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not session.get("logged_in"):
                if request.path.startswith("/api/"):
                    return jsonify({"error": "未登录"}), 401
                return redirect(url_for("auth.login_page", next=request.path))
            
            role = session.get("role")
            missing = [
                p for p in permission_names
                if not PermissionRegistry.has_permission(role, p)
            ]
            
            if missing:
                user_id = session.get("user_id")
                log_unauthorized_access(user_id, f"all_of_{permission_names}")
                
                if request.path.startswith("/api/"):
                    return jsonify({
                        "error": "权限不足",
                        "missing_permissions": missing,
                        "your_role": role,
                    }), 403
                
                flash("您没有权限执行此操作", "danger")
                return redirect(url_for("index"))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


# ─────────────────────────────────────────
# 5. 蓝图级别权限保护（before_request）
# ─────────────────────────────────────────

def protect_blueprint(blueprint, permission_name):
    """
    为整个蓝图注册权限检查（before_request）。
    用法（在蓝图文件中）：
        from decorators import protect_blueprint
        protect_blueprint(my_bp, 'manage_discipline')
    
    注意：这会导致该蓝图下所有路由都需要该权限！
          如果某些路由需要不同权限，请使用装饰器方式。
    """
    @blueprint.before_request
    def check_permission():
        if not session.get("logged_in"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "未登录"}), 401
            return redirect(url_for("auth.login_page", next=request.path))
        
        role = session.get("role")
        if not PermissionRegistry.has_permission(role, permission_name):
            user_id = session.get("user_id")
            log_unauthorized_access(user_id, f"blueprint:{permission_name}")
            
            if request.path.startswith("/api/"):
                return jsonify({"error": "权限不足"}), 403
            
            flash("您没有权限访问此模块", "danger")
            return redirect(url_for("index"))


# ─────────────────────────────────────────
# 6. 导出：保留原有装饰器（向后兼容）
# ─────────────────────────────────────────

# 原有装饰器（保留，确保现有代码不报错）
def login_required(f):
    """必须登录（原有实现）"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "未登录"}), 401
            flash("请先登录", "warning")
            return redirect(url_for("auth.login_page", next=request.path))
        return f(*args, **kwargs)
    return decorated


def require_role(*roles):
    """限制角色访问（原有实现）"""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not session.get("logged_in"):
                if request.path.startswith("/api/"):
                    return jsonify({"error": "未登录"}), 401
                return redirect(url_for("auth.login_page", next=request.path))
            if session.get("role") not in roles:
                if request.path.startswith("/api/"):
                    return jsonify({"error": "权限不足"}), 403
                flash("您没有权限访问此页面", "danger")
                return redirect(url_for("index"))
            return f(*args, **kwargs)
        return decorated
    return decorator


def scope_query(model):
    """根据当前登录角色，自动添加数据范围过滤"""
    from models import Student

    role = session.get("role", "")
    grade_id = session.get("grade_id")
    class_id = session.get("class_id")
    student_id = session.get("student_id")
    bound_student_id = session.get("bound_student_id")

    q = model.query

    if role == "ms_admin":
        return q   # 德育处：全量
    elif role == "grade_leader":
        if hasattr(model, "grade_id"):
            q = q.filter(model.grade_id == grade_id)
        return q
    elif role in ("class_teacher", "teacher"):
        if hasattr(model, "class_id"):
            q = q.filter(model.class_id == class_id)
        elif hasattr(model, "student_id"):
            sub = (Student.query.filter_by(class_id=class_id)
                   .with_entities(Student.id).subquery())
            q = q.filter(model.student_id.in_(sub))
        return q
    elif role == "parent":
        sid = bound_student_id or student_id
        if sid and hasattr(model, "student_id"):
            q = q.filter(model.student_id == sid)
        return q
    elif role == "student":
        if hasattr(model, "student_id") and student_id:
            q = q.filter(model.student_id == student_id)
        return q
    return q


def get_scope_filter(model_or_query, role=None, class_id=None, grade_id=None):
    """
    增强型数据范围过滤 — 支持通过 student_id 间接关联到 class。

    用法：
        q = Score.query
        q = get_scope_filter(q)
        # 或
        q = get_scope_filter(Score)

    参数：
        model_or_query: Model 类或 Query 对象
        role: 角色（默认从 session 读取）
        class_id: 班级ID（默认从 session 读取）
        grade_id: 年级ID（默认从 session 读取）

    返回：过滤后的 Query 对象
    """
    from flask import session
    from models import Student

    role = role or session.get("role", "")
    class_id = class_id or session.get("class_id")
    grade_id = grade_id or session.get("grade_id")

    if hasattr(model_or_query, "query"):
        q = model_or_query.query
    else:
        q = model_or_query

    if role == "ms_admin":
        return q

    if role == "grade_leader" and grade_id:
        if hasattr(q.column_descriptions[0]["type"], "grade_id"):
            return q.filter(q.column_descriptions[0]["type"].grade_id == grade_id)
        # 尝试通过 student.grade_id 关联
        mapper = q.column_descriptions[0]["type"].__mapper__
        if hasattr(mapper.attrs, "student_id"):
            sub = (Student.query.filter_by(grade_id=grade_id)
                   .with_entities(Student.id).subquery())
            return q.filter(q.column_descriptions[0]["type"].student_id.in_(sub))
        return q

    if role in ("class_teacher", "teacher") and class_id:
        model = q.column_descriptions[0]["type"]
        # 1. 直接有 class_id
        if hasattr(model, "class_id"):
            return q.filter(model.class_id == class_id)
        # 2. 有 student_id，通过 Student.class_id 间接过滤
        if hasattr(model, "student_id"):
            sub = (Student.query.filter_by(class_id=class_id)
                   .with_entities(Student.id).subquery())
            return q.filter(model.student_id.in_(sub))
        return q

    return q


def filter_by_class(q, model, class_id=None):
    """
    将查询限制到指定班级（支持直接 class_id 或间接 student_id 关联）。
    用于视图函数中手动过滤。

    用法：
        records = filter_by_class(DisciplineRecord.query, DisciplineRecord).all()
    """
    from flask import session
    from models import Student

    class_id = class_id or session.get("class_id")
    if not class_id:
        return q

    if hasattr(model, "class_id"):
        return q.filter(model.class_id == class_id)
    if hasattr(model, "student_id"):
        sub = (Student.query.filter_by(class_id=class_id)
               .with_entities(Student.id).subquery())
        return q.filter(model.student_id.in_(sub))
    return q


def get_my_class_students(class_id=None):
    """获取当前班主任/教师所在班级的学生列表"""
    from flask import session
    from models import Student
    class_id = class_id or session.get("class_id")
    if not class_id:
        return []
    return Student.query.filter_by(class_id=class_id, is_active=True).all()


def get_my_class_student_ids(class_id=None):
    """获取当前班主任/教师所在班级的学生ID列表"""
    from flask import session
    from models import Student
    class_id = class_id or session.get("class_id")
    if not class_id:
        return []
    return [s.id for s in Student.query.filter_by(class_id=class_id, is_active=True).all()]


# ─────────────────────────────────────────
# 7. 权限矩阵报告生成器
# ─────────────────────────────────────────

def generate_permission_matrix():
    """
    生成权限矩阵报告（Markdown格式）。
    用途：审查所有角色的权限分配是否合理。
    """
    lines = []
    lines.append("# 权限矩阵报告\n")
    lines.append(f"生成时间: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}\n")
    lines.append("\n## 权限列表\n")
    
    for perm, desc in PermissionRegistry.PERMISSIONS.items():
        lines.append(f"- `{perm}`: {desc}")
    
    lines.append("\n## 角色权限矩阵\n")
    lines.append("| 权限标识 | " + " | ".join(PermissionRegistry.ROLE_PERMISSIONS.keys()) + " |")
    lines.append("|" + "|".join(["---"] * (len(PermissionRegistry.ROLE_PERMISSIONS) + 1)) + "|")
    
    for perm in PermissionRegistry.PERMISSIONS.keys():
        row = f"| `{perm}` |"
        for role in PermissionRegistry.ROLE_PERMISSIONS.keys():
            has = PermissionRegistry.has_permission(role, perm)
            row += " ✅ |" if has else " ❌ |"
        lines.append(row)
    
    return "\n".join(lines)
