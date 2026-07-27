"""
core/services.py — Wings 3.0 核心服务层

AuthService: JWT 签发 / 密码验证 / 权限校验
OrgService:  组织架构 CRUD / 租户上下文注入
"""

import hashlib
import hmac
import logging
import os
import re
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Class, Grade, School, SchoolModule, Student, User, UserRole
from .schemas import UserOut

logger = logging.getLogger("auth")


# ═══════════════════════════════════════════════════════════════
# AuthService — 认证与鉴权
# ═══════════════════════════════════════════════════════════════


class AuthService:
    JWT_ALGORITHM = "HS256"
    ACCESS_TOKEN_EXPIRE_HOURS = 24

    @staticmethod
    def _secret() -> str:
        secret = os.environ.get("JWT_SECRET_KEY")
        if not secret:
            raise ValueError(
                "JWT_SECRET_KEY 环境变量未配置，认证服务无法初始化。请在 .env 中注入安全密钥。"
            )
        return secret

    @classmethod
    def hash_password(cls, password: str) -> str:
        """bcrypt 密码哈希（cost=12）。新密码一律走 bcrypt。"""
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("ascii")

    @classmethod
    def verify_password(cls, password: str, password_hash: str) -> bool:
        """验证密码 — 双轨制: bcrypt 新哈希 + 遗留 sha256$salt$hash 兼容"""
        if not password_hash:
            return False
        try:
            # 新轨: bcrypt
            if password_hash.startswith(("$2a$", "$2b$", "$2y$")):
                return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
            # 旧轨: sha256$salt$hash（遗留数据，登录成功后静默升级）
            if password_hash.startswith("sha256$"):
                algo, salt, stored_hash = password_hash.split("$", 2)
                if algo != "sha256":
                    return False
                computed = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
                return hmac.compare_digest(computed.encode("ascii"), stored_hash.encode("ascii"))
        except (ValueError, AttributeError, UnicodeError):
            return False
        return False

    @staticmethod
    def password_needs_rehash(password_hash: str) -> bool:
        """遗留 SHA-256 哈希需要在下次成功登录时静默升级为 bcrypt"""
        return bool(password_hash and password_hash.startswith("sha256$"))

    # ── 密码安全策略 ──

    # 复杂度规则: 至少包含以下 4 类中的 3 类
    _PW_UPPER = re.compile(r"[A-Z]")
    _PW_LOWER = re.compile(r"[a-z]")
    _PW_DIGIT = re.compile(r"[0-9]")
    _PW_SPECIAL = re.compile(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?`~]")

    # 账户锁定阈值
    MAX_LOGIN_ATTEMPTS = 5
    LOCKOUT_DURATION_SECONDS = 15 * 60  # 15 分钟

    @classmethod
    def _get_redis(cls):
        """延迟导入 Redis 客户端（避免循环依赖）"""
        try:
            from .redis_client import get_redis

            return get_redis()
        except ImportError:
            return None

    @classmethod
    def validate_password_strength(cls, password: str, username: str = "") -> str | None:
        """
        验证密码强度。返回 None 表示通过，否则返回错误消息。

        策略:
        - 最少 8 个字符
        - 不能包含用户名
        - 至少包含大写字母、小写字母、数字、特殊字符中的 3 类
        """
        if len(password) < 8:
            return "密码长度不能少于8位"

        if len(password) > 128:
            return "密码长度不能超过128位"

        if username and username.lower() in password.lower():
            return "密码不能包含用户名"

        categories = 0
        if cls._PW_UPPER.search(password):
            categories += 1
        if cls._PW_LOWER.search(password):
            categories += 1
        if cls._PW_DIGIT.search(password):
            categories += 1
        if cls._PW_SPECIAL.search(password):
            categories += 1

        if categories < 3:
            return "密码强度不足，需包含大写字母、小写字母、数字、特殊字符中的至少3类"

        return None

    @classmethod
    def create_token(cls, user: User) -> str:
        """签发 JWT access token"""
        now = datetime.now(timezone.utc)
        payload = {
            "sub": str(user.id),
            "username": user.username,
            "role": user.role.value if isinstance(user.role, UserRole) else user.role,
            "school_id": user.school_id,
            "iat": now,
            "exp": now + timedelta(hours=cls.ACCESS_TOKEN_EXPIRE_HOURS),
        }
        return jwt.encode(payload, cls._secret(), algorithm=cls.JWT_ALGORITHM)

    @classmethod
    def decode_token(cls, token: str) -> dict:
        """解码 JWT token，无效则抛异常"""
        return jwt.decode(token, cls._secret(), algorithms=[cls.JWT_ALGORITHM])

    @classmethod
    async def authenticate(
        cls, db: AsyncSession, username: str, password: str
    ) -> tuple[User | None, str | None]:
        """
        验证用户凭证（带账户锁定保护）。
        返回 (user, error_message) — 成功时 error_message 为 None。

        锁定策略: 5 次失败 → 15 分钟锁定（基于 Redis 计数）
        """
        redis = cls._get_redis()

        # ── 检查锁定状态 ──
        if redis:
            locked = await redis.get(f"login_locked:{username}")
            if locked:
                ttl = await redis.ttl(f"login_locked:{username}")
                minutes = max(1, ttl // 60)
                return None, f"账户已锁定，请{minutes}分钟后重试"

        # ── 查询用户 ──
        result = await db.execute(select(User).where(User.username == username, User.is_active))
        user = result.scalar_one_or_none()

        if not user:
            await cls._record_failed_attempt(redis, username)
            return None, "用户名或密码错误"

        if not cls.verify_password(password, user.password_hash):
            await cls._record_failed_attempt(redis, username)
            return None, "用户名或密码错误"

        # ── 登录成功: 清除失败计数 ──
        if redis:
            await redis.delete(f"login_fails:{username}", f"login_locked:{username}")

        # ── 静默升级: 遗留 SHA-256 哈希 → bcrypt（明文仅此刻可用）──
        if cls.password_needs_rehash(user.password_hash):
            try:
                user.password_hash = cls.hash_password(password)
                logger.info(f"密码哈希静默升级为 bcrypt: {username}")
            except Exception as e:
                # 升级失败不影响登录，下次再试
                logger.error(f"密码哈希升级失败 ({username}): {e}")

        # 更新最后登录时间
        user.last_login = datetime.now(timezone(timedelta(hours=8))).replace(tzinfo=None)
        await db.commit()

        return user, None

    @classmethod
    async def _record_failed_attempt(cls, redis, username: str) -> None:
        """记录一次登录失败，达到阈值则锁定账户"""
        if redis is None:
            return
        try:
            key = f"login_fails:{username}"
            fails = await redis.incr(key)
            # 首次失败时设置 TTL（15分钟滑动窗口）
            if fails == 1:
                await redis.expire(key, cls.LOCKOUT_DURATION_SECONDS)
            if fails >= cls.MAX_LOGIN_ATTEMPTS:
                await redis.setex(f"login_locked:{username}", cls.LOCKOUT_DURATION_SECONDS, "1")
                logger.warning(f"账户锁定: {username} ({fails}次失败)")
        except Exception as e:
            logger.error(f"Redis 登录失败记录异常: {e}")

    @classmethod
    async def get_user_out(cls, db: AsyncSession, user: User) -> UserOut:
        """将 User ORM 对象转为 UserOut 响应模型"""
        school_name = None
        school_phase = "junior"
        plugin_config = None
        if user.school_id:
            result = await db.execute(
                select(School.name, School.school_phase, School.plugin_config).where(
                    School.id == user.school_id
                )
            )
            row = result.first()
            if row:
                school_name = row[0]
                school_phase = row[1] or "junior"
                plugin_config = row[2]

        return UserOut(
            id=user.id,
            username=user.username,
            display_name=user.display_name,
            role=user.role.value if isinstance(user.role, UserRole) else user.role,
            school_id=user.school_id,
            school_name=school_name,
            school_phase=school_phase,
            plugin_config=plugin_config,
            grade_id=user.grade_id,
            class_id=user.class_id,
            is_active=user.is_active,
            password_change_required=bool(user.password_change_required),
        )

    @classmethod
    async def change_password(
        cls, db: AsyncSession, user: User, old_password: str, new_password: str
    ) -> tuple[bool, str | None]:
        """
        修改密码。验证旧密码 → 强度检查 → 更新哈希 → 清除强制改密标志。
        返回 (success, error_message)
        """
        if not cls.verify_password(old_password, user.password_hash):
            return False, "原密码错误"

        # 密码强度验证
        strength_error = cls.validate_password_strength(new_password, user.username)
        if strength_error:
            return False, strength_error

        if old_password == new_password:
            return False, "新密码不能与原密码相同"

        user.password_hash = cls.hash_password(new_password)
        user.password_change_required = False
        await db.commit()

        return True, None


# ═══════════════════════════════════════════════════════════════
# OrgService — 组织架构与租户管理
# ═══════════════════════════════════════════════════════════════


class OrgService:
    @staticmethod
    async def get_school(db: AsyncSession, school_id: int) -> School | None:
        result = await db.execute(select(School).where(School.id == school_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def create_school(db: AsyncSession, name: str) -> School:
        school = School(name=name, is_active=True)
        db.add(school)
        await db.commit()
        await db.refresh(school)
        return school

    @staticmethod
    async def get_grades(db: AsyncSession, school_id: int) -> list[Grade]:
        result = await db.execute(
            select(Grade)
            .where(Grade.school_id == school_id, Grade.is_active)
            .order_by(Grade.sort_order)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_classes(
        db: AsyncSession, school_id: int, grade_id: int | None = None
    ) -> list[Class]:
        stmt = select(Class).where(
            Class.school_id == school_id,
            Class.is_active,
        )
        if grade_id:
            stmt = stmt.where(Class.grade_id == grade_id)
        stmt = stmt.order_by(Class.name)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_students(
        db: AsyncSession,
        school_id: int,
        class_id: int | None = None,
        grade_id: int | None = None,
        gender: str | None = None,
        is_active: bool | None = True,
        search: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[Student], int]:
        """分页查询学生列表，返回 (students, total)"""
        conditions = [Student.school_id == school_id]
        if is_active is not None:
            conditions.append(Student.is_active == is_active)
        if class_id:
            conditions.append(Student.class_id == class_id)
        if grade_id:
            conditions.append(Student.grade_id == grade_id)
        if gender:
            conditions.append(Student.gender == gender)
        if search:
            conditions.append(
                (Student.name.like(f"%{search}%")) | (Student.student_no.like(f"%{search}%"))
            )

        # 高效 count（避免加载全量数据）
        from sqlalchemy import func

        cnt = await db.scalar(select(func.count()).select_from(Student).where(*conditions))
        total = int(cnt or 0)

        stmt = (
            select(Student)
            .where(*conditions)
            .order_by(Student.student_no)
            .offset(offset)
            .limit(limit)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all()), total

    @staticmethod
    async def get_students_with_names(
        db: AsyncSession,
        school_id: int,
        class_id: int | None = None,
        grade_id: int | None = None,
        gender: str | None = None,
        is_active: bool | None = True,
        search: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        """分页查询学生列表，附班级名和年级名（单次 JOIN 无 N+1）"""
        conditions = [Student.school_id == school_id]
        if is_active is not None:
            conditions.append(Student.is_active == is_active)
        if class_id:
            conditions.append(Student.class_id == class_id)
        if grade_id:
            conditions.append(Student.grade_id == grade_id)
        if gender:
            conditions.append(Student.gender == gender)
        if search:
            conditions.append(
                (Student.name.like(f"%{search}%")) | (Student.student_no.like(f"%{search}%"))
            )

        from sqlalchemy import func

        cnt = await db.scalar(select(func.count()).select_from(Student).where(*conditions))
        total = int(cnt or 0)

        # 单次 JOIN 查学生+班级名+年级名
        stmt = (
            select(
                Student.id,
                Student.name,
                Student.student_no,
                Student.class_id,
                Student.grade_id,
                Student.gender,
                Student.is_active,
                Class.name.label("class_name"),
                Grade.name.label("grade_name"),
            )
            .join(Class, Student.class_id == Class.id)
            .join(Grade, Student.grade_id == Grade.id)
            .where(*conditions)
            .order_by(Student.student_no)
            .offset(offset)
            .limit(limit)
        )
        result = await db.execute(stmt)
        rows = result.all()
        students = [
            {
                "id": r.id,
                "name": r.name,
                "student_no": r.student_no,
                "class_id": r.class_id,
                "grade_id": r.grade_id,
                "gender": r.gender,
                "is_active": r.is_active,
                "class_name": r.class_name,
                "grade_name": r.grade_name,
            }
            for r in rows
        ]
        return students, total

    @staticmethod
    async def get_classes_with_details(
        db: AsyncSession, school_id: int, grade_id: int | None = None
    ) -> list[dict]:
        """查询班级列表，附年级名和班主任名"""
        stmt = (
            select(
                Class.id,
                Class.name,
                Class.school_id,
                Class.grade_id,
                Class.head_teacher_id,
                Class.student_count,
                Class.is_active,
                Grade.name.label("grade_name"),
                User.display_name.label("head_teacher_name"),
            )
            .join(Grade, Class.grade_id == Grade.id)
            .outerjoin(User, Class.head_teacher_id == User.id)
            .where(Class.school_id == school_id, Class.is_active)
        )
        if grade_id:
            stmt = stmt.where(Class.grade_id == grade_id)
        stmt = stmt.order_by(Class.name)
        result = await db.execute(stmt)
        return [
            {
                "id": r.id,
                "name": r.name,
                "school_id": r.school_id,
                "grade_id": r.grade_id,
                "head_teacher_id": r.head_teacher_id,
                "student_count": r.student_count or 0,
                "is_active": r.is_active,
                "grade_name": r.grade_name,
                "head_teacher_name": r.head_teacher_name,
            }
            for r in result.all()
        ]

    @staticmethod
    async def get_enabled_modules(db: AsyncSession, school_id: int) -> list[str]:
        """获取某学校当前启用的模块代码列表"""
        result = await db.execute(
            select(SchoolModule.module_code).where(
                SchoolModule.school_id == school_id,
                SchoolModule.enabled,
            )
        )
        return [row[0] for row in result.all()]

    @staticmethod
    async def set_module_state(
        db: AsyncSession,
        school_id: int,
        module_code: str,
        enabled: bool,
        config: dict | None = None,
    ) -> SchoolModule:
        """启用/禁用学校的某个模块"""
        result = await db.execute(
            select(SchoolModule).where(
                SchoolModule.school_id == school_id,
                SchoolModule.module_code == module_code,
            )
        )
        sm = result.scalar_one_or_none()

        now = datetime.now(timezone(timedelta(hours=8))).replace(tzinfo=None)

        if sm:
            sm.enabled = enabled
            if config is not None:
                sm.config = config
            if enabled:
                sm.enabled_at = sm.enabled_at or now
                sm.disabled_at = None
            else:
                sm.disabled_at = now
        else:
            sm = SchoolModule(
                school_id=school_id,
                module_code=module_code,
                enabled=enabled,
                config=config,
                enabled_at=now if enabled else None,
                disabled_at=None if enabled else now,
            )
            db.add(sm)

        await db.commit()
        await db.refresh(sm)
        return sm
