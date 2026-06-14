"""梨江中学德育管理平台 — 主应用入口"""
import sys, os, logging, time
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from flask import Flask, render_template, session, redirect, url_for, request, jsonify, g
from config import Config
from models import db, Student, Class, Semester, Announcement, ROLES
from decorators import login_required
from blueprint_registry import register_all
from utils.db_utils import safe_commit


def _load_dotenv():
    """加载 .env 文件到 os.environ（仅设置未定义的环境变量）"""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.isfile(env_path):
        return

    loaded = 0
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip("'\"").strip("'").strip('"')
            if key and key not in os.environ:
                os.environ[key] = val
                loaded += 1

    if loaded:
        print(f"[app] 从 .env 加载了 {loaded} 个环境变量")


def create_app():
    # ── 加载 .env 文件（开发环境用，生产环境由 systemd 注入）──
    _load_dotenv()

    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)

    # ── 配置校验（密钥/数据库未设置则拒绝启动）──
    try:
        Config.init_app(app)
    except RuntimeError as e:
        print(f"[配置错误] {e}")
        print("[提示] 请在环境变量或 .env 文件中设置必需配置后重试。")
        raise

    # ── 日志配置 ──
    _setup_logging(app)

    # ── 一键注册所有蓝图 ──
    register_all(app)

    # ── Jinja 全局变量 ──
    @app.context_processor
    def inject_globals():
        """向所有模板注入全局变量，减少路由重复传参"""
        from datetime import datetime as dt_now
        try:
            _classes = Class.query.filter_by(is_active=True).order_by(Class.name).all()
        except Exception:
            _classes = []
        try:
            _semesters = Semester.query.order_by(Semester.id.desc()).all()
        except Exception:
            _semesters = []
        return {
            "session": session,
            "ROLES": ROLES,
            "now": dt_now.utcnow(),
            "classes": _classes,
            "semesters": _semesters,
        }

    # ── 首页 → 按角色自动跳转 ──
    @app.route("/")
    @login_required
    def index():
        role = session.get("role", "")
        if role == "ms_admin":
            return redirect(url_for("ms.dashboard"))
        elif role == "grade_leader":
            return redirect(url_for("grade.dashboard"))
        elif role in ("class_teacher", "teacher"):
            return redirect(url_for("class.dashboard"))
        elif role == "parent":
            return redirect(url_for("parent_portal.dashboard"))  # 家长端门户
        else:
            stats = {
                "student_count": Student.query.filter_by(is_active=True).count(),
                "class_count": Class.query.filter_by(is_active=True).count(),
            }
            return render_template("index.html", stats=stats)

    # ── 健康检查 ──
    @app.route("/health")
    def health():
        try:
            db.session.execute(db.text("SELECT 1"))
            return jsonify({"status": "ok"})
        except Exception as e:
            app.logger.error(f"Health check failed: {e}")
            return jsonify({"status": "degraded", "error": str(e)}), 503

    # ── 全局异常捕获（大坝式治理）──
    @app.errorhandler(Exception)
    def handle_all_exceptions(e):
        """捕获所有未处理异常：回滚事务 + 记录日志 + 统一响应"""
        # 如果已经是 HTTP 异常（如 404 from abort()），交给 Flask 默认处理
        from werkzeug.exceptions import HTTPException
        if isinstance(e, HTTPException):
            return e

        db.session.rollback()
        app.logger.error(f"未捕获异常: {request.method} {request.path}", exc_info=e)

        if request.path.startswith("/api/"):
            return jsonify({
                "code": 500,
                "msg": "系统内部错误，请联系管理员"
            }), 500
        return render_template("error.html",
            message="系统暂时不可用，请联系管理员。错误已记录。"), 500

    # ── HTTP 错误处理器 ──
    @app.errorhandler(404)
    def not_found(e):
        if request.path.startswith("/api/"):
            return jsonify({"code": 404, "msg": "接口不存在"}), 404
        return render_template("error.html", message="页面不存在"), 404

    @app.errorhandler(500)
    def server_error(e):
        db.session.rollback()
        app.logger.error(f"500 错误: {request.method} {request.path}", exc_info=e)
        if request.path.startswith("/api/"):
            return jsonify({"code": 500, "msg": "服务器内部错误"}), 500
        return render_template("error.html", message="服务器内部错误"), 500

    # ── 请求耗时监控（慢请求日志）──
    @app.before_request
    def _start_timer():
        g._start_time = time.time()

    @app.after_request
    def _log_slow_request(response):
        if hasattr(g, "_start_time"):
            duration = time.time() - g._start_time
            g._request_duration = duration  # 供后续使用
            if duration > 1.0:  # 超过 1 秒记录 WARN
                app.logger.warning(
                    f"[慢请求] {request.method} {request.path} "
                    f"耗时 {duration:.2f}s status={response.status_code}"
                )
            elif duration > 3.0:  # 超过 3 秒记录 ERROR
                app.logger.error(
                    f"[极慢请求] {request.method} {request.path} "
                    f"耗时 {duration:.2f}s status={response.status_code}"
                )
        return response

    # ── 防止浏览器缓存 HTML 页面 ──
    @app.after_request
    def add_no_cache_headers(response):
        """HTML 页面添加 no-cache 头，防止浏览器缓存导致旧版代码残留"""
        if response.content_type and "text/html" in response.content_type:
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

    # ── 确保上传目录存在 ──
    os.makedirs(app.config.get("UPLOAD_FOLDER", "uploads"), exist_ok=True)

    # ── 初始化数据库 ──
    with app.app_context():
        try:
            db.create_all()
        except Exception as e:
            if "already exists" not in str(e):
                raise
        _seed_admin(app)

    return app


def _setup_logging(app):
    """配置应用日志"""
    if not app.debug:
        # 生产环境：输出到文件
        log_dir = os.path.join(app.root_path, "logs")
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "grade7-new.log")

        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s [%(name)s] %(message)s"
        ))
        app.logger.addHandler(file_handler)
        app.logger.setLevel(logging.INFO)
        app.logger.info("系统启动完成")
    else:
        app.logger.setLevel(logging.DEBUG)


def _seed_admin(app):
    """首次启动自动创建管理员账号"""
    from models import User
    admin = User.query.filter_by(username="admin").first()
    if not admin:
        admin = User(
            username="admin",
            display_name="系统管理员",
            role="ms_admin",
        )
        admin.set_password("admin123")
        db.session.add(admin)
        safe_commit()
        app.logger.info("初始化: 管理员账号已创建: admin / admin123")


if __name__ == "__main__":
    app = create_app()
    print("\n" + "=" * 60)
    print("  梨江中学德育管理平台")
    print("  角色: 德育处 → 年级组 → 班主任 → 家长")
    print("  http://127.0.0.1:5000")
    print("=" * 60 + "\n")
    app.run(host="0.0.0.0", port=5000, debug=True)


if __name__ == "__main__":
    app = create_app()
    print("\n" + "=" * 60)
    print("  梨江中学德育管理平台")
    print("  角色: 德育处 → 年级组 → 班主任 → 家长")
    print("  http://127.0.0.1:5000")
    print("=" * 60 + "\n")
    app.run(host="0.0.0.0", port=5000, debug=True)
