"""梨江中学德育管理平台 — 配置"""
import os
import warnings

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    """所有密钥必须从环境变量读取，代码中不含任何明文密码"""

    # ── 密钥（必须从环境变量注入）──
    SECRET_KEY = os.environ.get("SECRET_KEY", "")
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "")
    JWT_EXPIRATION_HOURS = int(os.environ.get("JWT_EXPIRATION_HOURS", "720"))

    # ── 数据库 ──
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "")

    # ── 连接池（Gunicorn --preload 模式必须配置）──
    # 自适应：SQLite 不需要连接池参数
    _uri = os.environ.get("DATABASE_URL", "")
    if _uri.startswith("sqlite://"):
        SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": 300}
    else:
        SQLALCHEMY_ENGINE_OPTIONS = {
            "pool_pre_ping": True,
            "pool_recycle": 300,
            "pool_size": 5,
            "max_overflow": 10,
            "pool_timeout": 30,
        }

    # ── Session / Cookie 安全 ──
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("FLASK_ENV", "") == "production"
    PERMANENT_SESSION_LIFETIME = 86400  # 24 小时

    # ── 上传 ──
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB

    # ── LLM 大模型配置（期末评语生成舱）──
    LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
    LLM_API_URL = os.environ.get("LLM_API_URL", "https://api.deepseek.com/v1/chat/completions")
    LLM_MODEL = os.environ.get("LLM_MODEL", "deepseek-chat")
    LLM_TIMEOUT = int(os.environ.get("LLM_TIMEOUT", "30"))

    # ── 分页 ──
    PAGE_SIZE = 20

    # ── 日志 ──
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

    @classmethod
    def init_app(cls, app):
        """应用启动时校验配置，不安全则拒绝启动"""
        with app.app_context():
            cls._validate(app)

    @classmethod
    def _validate(cls, app):
        errors = []
        warnings_list = []

        if not cls.SECRET_KEY:
            errors.append(
                "SECRET_KEY 未设置！"
                " 生产环境请在 systemd service 中配置 Environment=SECRET_KEY=xxx"
                " 开发环境请创建 .env 文件（参考 .env.example）"
            )
        elif len(cls.SECRET_KEY) < 32:
            warnings_list.append("SECRET_KEY 长度不足 32 字符，存在安全风险")

        if not cls.JWT_SECRET_KEY:
            errors.append("JWT_SECRET_KEY 未设置！请参考 SECRET_KEY 的配置方式。")

        if not cls.SQLALCHEMY_DATABASE_URI:
            errors.append(
                "DATABASE_URL 未设置！"
                " 生产环境请在 systemd service 中配置 Environment=DATABASE_URL=xxx"
                " 开发环境请在 .env 文件中配置。"
            )
        elif "waOPKoyFf4ByQD1h" in cls.SQLALCHEMY_DATABASE_URI:
            warnings_list.append(
                "DATABASE_URL 含有疑似硬编码密码，建议改用环境变量注入"
            )

        for msg in warnings_list:
            app.logger.warning(f"[配置警告] {msg}")
        for msg in errors:
            app.logger.error(f"[配置错误] {msg}")

        if errors:
            raise RuntimeError(
                "配置校验失败，请在环境变量或 .env 文件中正确设置以下项：\n"
                "  - SECRET_KEY（至少 32 字符随机字符串）\n"
                "  - JWT_SECRET_KEY（至少 32 字符随机字符串）\n"
                "  - DATABASE_URL（数据库连接串）\n"
                "然后重新启动应用。"
            )
