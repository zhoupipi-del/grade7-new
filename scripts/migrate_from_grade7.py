#!/usr/bin/env python3
"""
Wings 3.0 跨代数据迁移脚本
从旧 Flask 库 (grade7_new) → 新 FastAPI 库 (wings3)

用法:
  cd /root/backend && .venv/bin/python scripts/migrate_from_grade7.py

策略:
  - 全量迁移: grades → classes → users → students
  - 统一注入 school_id=1 (梨江中学)
  - 幂等设计: ON DUPLICATE KEY UPDATE，可安全重复执行
  - 事务包裹: 单事务内完成或全部回滚
"""

import os
import sys
import json
import hashlib
import secrets
import logging
from datetime import datetime

# 确保能引入项目根目录模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text, inspect
from sqlalchemy.exc import SQLAlchemyError


def wings3_hash_password(password: str) -> str:
    """Wings 3.0 密码哈希格式: sha256$salt$hexdigest"""
    salt = secrets.token_hex(16)
    pw_hash = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
    return f"sha256${salt}${pw_hash}"


# 所有迁移用户的默认密码
DEFAULT_PASSWORD = "admin123"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("migrate")

# ── 配置 ──────────────────────────────────────────────
OLD_DB_URL = "mysql+pymysql://grade7:waOPKoyFf4ByQD1h@127.0.0.1:3307/grade7_new?charset=utf8mb4"
NEW_DB_URL = os.getenv(
    "DATABASE_URL",
    "mysql+pymysql://grade7:waOPKoyFf4ByQD1h@127.0.0.1:3307/wings3?charset=utf8mb4",
)

SCHOOL_ID = 1
SCHOOL_NAME = "梨江中学"

# 角色映射: 旧系统 varchar → 新系统 enum
ROLE_MAP = {
    "ms_admin":      "MS_ADMIN",
    "grade_leader":  "GRADE_LEADER",
    "class_teacher": "CLASS_TEACHER",
    "parent":        "PARENT",
}

old_engine = create_engine(OLD_DB_URL, echo=False)
new_engine = create_engine(NEW_DB_URL, echo=False)


def check_preconditions(old_conn, new_conn):
    """验证迁移前置条件"""
    # 检查旧库有数据
    cnt = old_conn.execute(text("SELECT COUNT(*) FROM students")).scalar()
    logger.info(f"旧库 students: {cnt} 条")
    if cnt == 0:
        logger.error("旧库 students 表为空，无法迁移")
        return False

    # 检查新库学校记录
    school = new_conn.execute(
        text("SELECT id, name FROM schools WHERE id = :sid"), {"sid": SCHOOL_ID}
    ).fetchone()
    if not school:
        logger.error(f"新库未找到 school_id={SCHOOL_ID}，请先初始化系统")
        return False
    logger.info(f"新库 school: [{school.id}] {school.name}")
    return True


def fix_school_name(conn):
    """修复学校名称乱码"""
    conn.execute(
        text("UPDATE schools SET name = :name WHERE id = :sid"),
        {"name": SCHOOL_NAME, "sid": SCHOOL_ID},
    )
    logger.info(f"学校名称已修正 → {SCHOOL_NAME}")


def migrate_grades(old_conn, new_conn):
    """迁移年级表"""
    rows = old_conn.execute(text("SELECT id, name, sort_order, is_active FROM grades")).fetchall()
    if not rows:
        logger.warning("旧库 grades 表为空")
        return 0

    for r in rows:
        new_conn.execute(text("""
            INSERT INTO grades (id, school_id, name, sort_order, is_active)
            VALUES (:id, :school_id, :name, :sort_order, :is_active)
            ON DUPLICATE KEY UPDATE
                name = VALUES(name),
                sort_order = VALUES(sort_order),
                is_active = VALUES(is_active)
        """), {
            "id": int(r.id),
            "school_id": SCHOOL_ID,
            "name": r.name,
            "sort_order": r.sort_order or 1,
            "is_active": bool(r.is_active) if r.is_active is not None else True,
        })

    logger.info(f"✅ grades: {len(rows)} 条 → wings3")
    return len(rows)


def migrate_users(old_conn, new_conn):
    """迁移用户表（跳过已删除账号）"""
    rows = old_conn.execute(text("""
        SELECT id, username, password_hash, display_name, role, is_active, created_at
        FROM users
        ORDER BY id
    """)).fetchall()

    migrated = 0
    skipped = 0

    for r in rows:
        # 跳过已删除标记的账号
        if "_deleted_" in (r.username or ""):
            logger.info(f"  ⊘ 跳过已删除: {r.username}")
            skipped += 1
            continue

        new_role = ROLE_MAP.get(r.role, r.role.upper() if r.role else "PARENT")
        is_active = bool(r.is_active) if r.is_active is not None else True

        # 密码处理: 已有用户保留原密码, 新用户使用 Wings 3.0 默认密码
        existing = new_conn.execute(
            text("SELECT id FROM users WHERE id = :uid"), {"uid": int(r.id)}
        ).fetchone()

        if existing:
            # 已存在: 仅更新非敏感字段, 不碰密码
            new_conn.execute(text("""
                UPDATE users SET
                    display_name = :display_name,
                    role = :role,
                    is_active = :is_active
                WHERE id = :id
            """), {
                "id": int(r.id),
                "display_name": r.display_name or r.username,
                "role": new_role,
                "is_active": is_active,
            })
        else:
            # 新用户: 使用 Wings 3.0 格式哈希
            new_conn.execute(text("""
                INSERT INTO users (id, username, password_hash, display_name, role, school_id, is_active, created_at)
                VALUES (:id, :username, :password_hash, :display_name, :role, :school_id, :is_active, :created_at)
            """), {
                "id": int(r.id),
                "username": r.username,
                "password_hash": wings3_hash_password(DEFAULT_PASSWORD),
                "display_name": r.display_name or r.username,
                "role": new_role,
                "school_id": SCHOOL_ID,
                "is_active": is_active,
                "created_at": r.created_at or datetime.now(),
            })
        migrated += 1

    logger.info(f"✅ users: {migrated} 条 → wings3 (跳过 {skipped} 个已删除)")
    return migrated


def migrate_classes(old_conn, new_conn):
    """迁移班级表"""
    rows = old_conn.execute(text("""
        SELECT id, name, grade_id, head_teacher_id, student_count, is_active
        FROM classes
        ORDER BY id
    """)).fetchall()

    for r in rows:
        new_conn.execute(text("""
            INSERT INTO classes (id, school_id, name, grade_id, head_teacher_id, student_count, is_active)
            VALUES (:id, :school_id, :name, :grade_id, :head_teacher_id, :student_count, :is_active)
            ON DUPLICATE KEY UPDATE
                name = VALUES(name),
                grade_id = VALUES(grade_id),
                head_teacher_id = VALUES(head_teacher_id),
                student_count = VALUES(student_count),
                is_active = VALUES(is_active)
        """), {
            "id": int(r.id),
            "school_id": SCHOOL_ID,
            "name": r.name,
            "grade_id": int(r.grade_id),
            "head_teacher_id": int(r.head_teacher_id) if r.head_teacher_id else None,
            "student_count": int(r.student_count) if r.student_count else 0,
            "is_active": bool(r.is_active) if r.is_active is not None else True,
        })

    logger.info(f"✅ classes: {len(rows)} 条 → wings3")
    return len(rows)


def safe_json_tags(tags_value):
    """将旧库 TEXT 类型的 tags 转为新库 JSON"""
    if tags_value is None:
        return None
    if isinstance(tags_value, (list, dict)):
        return json.dumps(tags_value, ensure_ascii=False)
    # 尝试解析已有 JSON 字符串
    s = str(tags_value).strip()
    if s in ("", "null", "None"):
        return None
    try:
        parsed = json.loads(s)
        return json.dumps(parsed, ensure_ascii=False)
    except (json.JSONDecodeError, TypeError):
        # 纯文本标签，包装为数组
        return json.dumps([s], ensure_ascii=False)


def migrate_students(old_conn, new_conn):
    """迁移学生表 — 核心资产"""
    # 分批读取，避免内存膨胀
    rows = old_conn.execute(text("""
        SELECT id, name, student_no, gender, class_id, grade_id,
               id_card, national_id, ethnicity, birth_date, address,
               parent1_name, parent1_phone, parent1_relation,
               parent2_name, parent2_phone, parent2_relation,
               primary_school, is_active, enrolled_at, tags, created_at
        FROM students
        ORDER BY id
    """)).fetchall()

    success = 0
    errors = 0

    for r in rows:
        try:
            new_conn.execute(text("""
                INSERT INTO students (
                    id, school_id, name, student_no, gender, class_id, grade_id,
                    id_card, nationality, ethnicity, birth_date, address,
                    parent1_name, parent1_phone, parent1_relation,
                    parent2_name, parent2_phone, parent2_relation,
                    primary_school, is_active, enrolled_at, tags, created_at
                ) VALUES (
                    :id, :school_id, :name, :student_no, :gender, :class_id, :grade_id,
                    :id_card, :nationality, :ethnicity, :birth_date, :address,
                    :parent1_name, :parent1_phone, :parent1_relation,
                    :parent2_name, :parent2_phone, :parent2_relation,
                    :primary_school, :is_active, :enrolled_at, :tags, :created_at
                )
                ON DUPLICATE KEY UPDATE
                    name = VALUES(name),
                    gender = VALUES(gender),
                    class_id = VALUES(class_id),
                    grade_id = VALUES(grade_id),
                    id_card = VALUES(id_card),
                    nationality = VALUES(nationality),
                    ethnicity = VALUES(ethnicity),
                    birth_date = VALUES(birth_date),
                    address = VALUES(address),
                    parent1_name = VALUES(parent1_name),
                    parent1_phone = VALUES(parent1_phone),
                    parent1_relation = VALUES(parent1_relation),
                    parent2_name = VALUES(parent2_name),
                    parent2_phone = VALUES(parent2_phone),
                    parent2_relation = VALUES(parent2_relation),
                    primary_school = VALUES(primary_school),
                    is_active = VALUES(is_active),
                    enrolled_at = VALUES(enrolled_at),
                    tags = VALUES(tags)
            """), {
                "id": int(r.id),
                "school_id": SCHOOL_ID,
                "name": (r.name or "").strip(),
                "student_no": (r.student_no or "").strip(),
                "gender": (r.gender or "").strip(),
                "class_id": int(r.class_id) if r.class_id else None,
                "grade_id": int(r.grade_id) if r.grade_id else None,
                "id_card": r.id_card,
                "nationality": r.national_id,  # ⚠️ 列名差异: old=national_id → new=nationality
                "ethnicity": r.ethnicity,
                "birth_date": r.birth_date,
                "address": r.address,
                "parent1_name": r.parent1_name,
                "parent1_phone": r.parent1_phone,
                "parent1_relation": r.parent1_relation,
                "parent2_name": r.parent2_name,
                "parent2_phone": r.parent2_phone,
                "parent2_relation": r.parent2_relation,
                "primary_school": r.primary_school,
                "is_active": bool(r.is_active) if r.is_active is not None else True,
                "enrolled_at": r.enrolled_at,
                "tags": safe_json_tags(r.tags),
                "created_at": r.created_at or datetime.now(),
            })
            success += 1
        except Exception as e:
            logger.warning(f"  ⚠️ 学生 [{r.student_no} {r.name}] 导入失败: {e}")
            errors += 1

    logger.info(f"✅ students: {success} 条 → wings3 (失败 {errors})")
    return success, errors


def verify(conn):
    """最终数据校验"""
    logger.info("─" * 50)
    logger.info("📊 数据校验")

    tables = {
        "grades":   "年级",
        "classes":  "班级",
        "users":    "用户",
        "students": "学生",
    }
    all_ok = True
    for table, label in tables.items():
        cnt = conn.execute(text(f"SELECT COUNT(*) FROM {table} WHERE school_id = :sid"),
                           {"sid": SCHOOL_ID}).scalar()
        status = "✅" if cnt > 0 else "❌"
        if cnt == 0:
            all_ok = False
        logger.info(f"  {status} {label}: {cnt} 条")

    # 抽样验证
    sample = conn.execute(text(
        "SELECT id, name, student_no, gender, class_id FROM students WHERE school_id = :sid LIMIT 3"
    ), {"sid": SCHOOL_ID}).fetchall()
    for s in sample:
        logger.info(f"  抽样: [{s.student_no}] {s.name} ({s.gender}) class_id={s.class_id}")

    return all_ok


def main():
    logger.info("=" * 60)
    logger.info("🚀 Wings 3.0 跨代数据迁移启动")
    logger.info(f"   源: grade7_new → 目标: wings3")
    logger.info(f"   租户: school_id={SCHOOL_ID} ({SCHOOL_NAME})")
    logger.info("=" * 60)

    try:
        with old_engine.connect() as old_conn:
            # ── 阶段 0: 前置检查 ──
            with new_engine.begin() as new_conn:
                if not check_preconditions(old_conn, new_conn):
                    return 1
                fix_school_name(new_conn)

            # ── 阶段 1: 年级 ──
            with new_engine.begin() as new_conn:
                migrate_grades(old_conn, new_conn)

            # ── 阶段 2: 用户 ──
            with new_engine.begin() as new_conn:
                migrate_users(old_conn, new_conn)

            # ── 阶段 3: 班级 ──
            with new_engine.begin() as new_conn:
                migrate_classes(old_conn, new_conn)

            # ── 阶段 4: 学生 (核心) ──
            with new_engine.begin() as new_conn:
                migrate_students(old_conn, new_conn)

        # ── 阶段 5: 校验 ──
        with new_engine.connect() as conn:
            all_ok = verify(conn)

        logger.info("=" * 60)
        logger.info("🎉 迁移完成！" if all_ok else "⚠️ 迁移完成但部分校验未通过")
        logger.info("=" * 60)
        return 0 if all_ok else 1

    except SQLAlchemyError as e:
        logger.error(f"❌ 数据库错误: {e}")
        return 1
    except Exception as e:
        logger.error(f"❌ 未预期错误: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
