#!/usr/bin/env python3
"""
P0 安全债务清除 — 默认密码强制改密迁移

用法:
  cd /root/backend && .venv/bin/python scripts/security_force_password_change.py

策略:
  1. ALTER TABLE 添加 password_change_required 列（如不存在）
  2. 标记所有使用 admin123 默认密码的用户 password_change_required=True
  3. 验证并报告

⚠️ 此脚本安全、幂等、可重复执行。
   用户仍可用现有密码登录，但将被强制要求修改密码。
"""

import hashlib
import hmac
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("security_migration")


# 复刻 Wings 3.0 密码验证逻辑（避免导入异步依赖）
def wings3_verify_password(password: str, password_hash: str) -> bool:
    """验证密码是否为给定值"""
    try:
        algo, salt, stored_hash = password_hash.split("$", 2)
        if algo != "sha256":
            return False
        computed = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
        return hmac.compare_digest(computed, stored_hash)
    except (ValueError, AttributeError):
        return False


from core.db_utils import get_db_url_for_script

DB_URL = get_db_url_for_script("运行前请先 export DATABASE_URL=...")
DEFAULT_PASSWORDS = ["admin123", "123456", "password", "888888"]


def main():
    logger.info("=" * 60)
    logger.info("🔐 P0 安全债务清除 — 默认密码强制改密")
    logger.info("=" * 60)

    engine = create_engine(DB_URL, echo=False)

    try:
        with engine.begin() as conn:
            # ── Step 1: 确保列存在 ──
            logger.info("Step 1: 检查/添加 password_change_required 列...")
            try:
                conn.execute(
                    text(
                        "ALTER TABLE users ADD COLUMN password_change_required TINYINT(1) DEFAULT 0 "
                        "COMMENT '是否需要强制修改密码'"
                    )
                )
                conn.execute(
                    text("ALTER TABLE users ADD INDEX idx_pwd_change (password_change_required)")
                )
                logger.info("  ✅ 列 password_change_required 已添加")
            except Exception as e:
                if "Duplicate column" in str(e) or "already exists" in str(e):
                    logger.info("  ⊘ 列已存在，跳过")
                else:
                    logger.warning(f"  ⚠️  无法添加列: {e}")

            # ── Step 2: 扫描默认密码用户 ──
            logger.info("Step 2: 扫描使用默认密码的用户...")
            result = conn.execute(
                text("SELECT id, username, password_hash FROM users WHERE is_active = 1")
            )
            all_users = result.fetchall()

            flagged = 0
            for user in all_users:
                is_default = False
                matched_pw = None
                for pw in DEFAULT_PASSWORDS:
                    if wings3_verify_password(pw, user.password_hash):
                        is_default = True
                        matched_pw = pw
                        break

                if is_default:
                    conn.execute(
                        text("UPDATE users SET password_change_required = TRUE WHERE id = :uid"),
                        {"uid": user.id},
                    )
                    logger.info(
                        f"  🔴 [{user.username}] 使用默认密码 '{matched_pw}' → 已标记强制改密"
                    )
                    flagged += 1

            # ── Step 3: 报告 ──
            logger.info("─" * 50)
            logger.info(f"📊 结果: 扫描 {len(all_users)} 个活跃用户, {flagged} 个被标记强制改密")
            logger.info("")
            logger.info("✅ 安全加固完成！以上用户下次登录将被迫修改密码。")
            logger.info("   他们仍可使用现有密码登录，但会被导向密码修改页。")
            logger.info("=" * 60)

    except SQLAlchemyError as e:
        logger.error(f"❌ 数据库错误: {e}")
        return 1
    except Exception as e:
        logger.error(f"❌ 未预期错误: {e}")
        import traceback

        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
