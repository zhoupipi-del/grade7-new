"""
db_utils.py — 数据库连接 URL 统一解析器

安全策略:
- 生产运行时: 只从环境变量读取，无默认值回退
- 脚本/工具: 提供安全回退机制但必须有明确的警告
- 禁止在任何代码中硬编码数据库密码
"""

import logging
import os
import sys
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)


def require_db_url() -> str:
    """获取异步数据库 URL（生产运行时使用）

    从 DATABASE_URL 环境变量读取，未设置则崩溃退出。
    适用于: app.py, app_server.py, Celery tasks, CEP 管线

    Returns:
        str: 完整的 async database URL (如 mysql+aiomysql://...)
    """
    url = os.environ.get("DATABASE_URL")
    if not url:
        logger.critical("FATAL: DATABASE_URL 环境变量未设置，Wings 3.0 无法启动")
        print(
            "\n[SECURITY] DATABASE_URL 环境变量未设置",
            "\n请确保已在 .env 文件或 systemd 服务中配置 DATABASE_URL",
            "\n示例: DATABASE_URL=mysql+aiomysql://user:password@host:port/dbname",
            "\n",
            file=sys.stderr,
        )
        sys.exit(1)
    return url


def require_sync_db_url() -> str:
    """获取同步数据库 URL（同步任务使用）

    从 DATABASE_URL 环境变量读取，自动替换 aiomysql→pymysql。
    未设置则崩溃退出。
    适用于: 同步脚本、Celery 同步任务、数据迁移

    Returns:
        str: 完整的 sync database URL (如 mysql+pymysql://...)
    """
    async_url = require_db_url()
    return async_url.replace("mysql+aiomysql://", "mysql+pymysql://")


def get_db_url_for_script(fallback_hint: str = "") -> str:
    """脚本/工具使用的数据库 URL 获取函数

    优先从环境变量读取，未设置时打印警告并使用提示信息。
    注意: 此函数仅用于开发/运维脚本，生产运行时禁止使用。

    Args:
        fallback_hint: 失败时显示的提示信息

    Returns:
        str: async database URL
    """
    url = os.environ.get("DATABASE_URL")
    if url:
        return url

    print(
        "\n[WARNING] DATABASE_URL 环境变量未设置",
        file=sys.stderr,
    )
    if fallback_hint:
        print(f"  提示: {fallback_hint}", file=sys.stderr)
    print(
        "  请在运行脚本前设置:",
        "    export DATABASE_URL=mysql+aiomysql://user:password@host:port/dbname",
        "",
        sep="\n",
        file=sys.stderr,
    )
    sys.exit(1)


def get_db_password() -> str:
    """从 DATABASE_URL 中安全提取数据库密码

    用于 vanguard_watchdog、seed_vanguard_history 等需要
    docker exec mysql 命令的运维脚本。

    禁止在任何代码中硬编码数据库密码。

    Returns:
        str: 数据库密码
    """
    url = require_db_url()
    # mysql+aiomysql://user:PASSWORD@host:port/db
    # 使用 urlsplit 安全解析，避免密码中含有 '@' 或 ':' 时误截断
    try:
        return urlsplit(url).password or ""
    except (IndexError, ValueError):
        logger.critical("FATAL: 无法从 DATABASE_URL 解析密码，请检查格式")
        print(
            "\n[SECURITY] DATABASE_URL 格式错误，无法解析密码",
            "\n期望格式: mysql+aiomysql://user:password@host:port/dbname",
            "\n",
            file=sys.stderr,
        )
        sys.exit(1)
