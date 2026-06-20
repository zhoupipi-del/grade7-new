"""
core/services.py — Wings 3.0 核心服务层

AuthService: JWT 签发 / 密码验证 / 权限校验
OrgService:  组织架构 CRUD / 租户上下文注入
"""

import os
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple, List

import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import User, School, Grade, Class, Student, SchoolModule, UserRole
from .schemas import UserOut


# ═══════════════════════════════════════════════════════════════
# AuthService — 认证与鉴权
# ═══════════════════════════════════════════════════════════════

class AuthService:
    JWT_ALGORITHM = "HS256"
    ACCESS_TOKEN_EXPIRE_HOURS = 24

    @staticmethod
    def _secret() -> str:
        return os.environ.get("JWT_SECRET_KEY", "change-me-in-production")

    @classmethod
    def hash_password(cls, password: str) -> str:
        """SHA-256 + salt 密码哈希"""
        salt = secrets.token_hex(16)
        pw_hash = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
        return f"sha256${salt}${pw_hash}"

    @classmethod
    def verify_password(cls, password: str, password_hash: str) -> bool:
        """验证密码"""
        try:
            algo, salt, stored_hash = password_hash.split("$", 2)
            if algo != "sha256":
                return False
            computed = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
            return hmac.compare_digest(computed, stored_hash)
        except (ValueError, AttributeError):
            return False

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
    ) -> Tuple[Optional[User], Optional[str]]:
        """
        验证用户凭证。
        返回 (user, error_message) — 成功时 error_message 为 None。
        """
        result = await db.execute(
            select(User).where(User.username == username, User.is_active == True)
        )
        user = result.scalar_one_or_none()

        if not user:
            return None, "用户名或密码错误"

        if not cls.verify_password(password, user.password_hash):
            return None, "用户名或密码错误"

        # 更新最后登录时间
        user.last_login = datetime.now(timezone(timedelta(hours=8))).replace(tzinfo=None)
        await db.commit()

        return user, None

    @classmethod
    async def get_user_out(cls, db: AsyncSession, user: User) -> UserOut:
        """将 User ORM 对象转为 UserOut 响应模型"""
        school_name = None
        if user.school_id:
            result = await db.execute(
                select(School.name).where(School.id == user.school_id)
            )
            school_name = result.scalar_one_or_none()

        return UserOut(
            id=user.id,
            username=user.username,
            display_name=user.display_name,
            role=user.role.value if isinstance(user.role, UserRole) else user.role,
            school_id=user.school_id,
            school_name=school_name,
            grade_id=user.grade_id,
            class_id=user.class_id,
            is_active=user.is_active,
        )


# ═══════════════════════════════════════════════════════════════
# OrgService — 组织架构与租户管理
# ═══════════════════════════════════════════════════════════════

class OrgService:

    @staticmethod
    async def get_school(db: AsyncSession, school_id: int) -> Optional[School]:
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
    async def get_grades(db: AsyncSession, school_id: int) -> List[Grade]:
        result = await db.execute(
            select(Grade)
            .where(Grade.school_id == school_id, Grade.is_active == True)
            .order_by(Grade.sort_order)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_classes(db: AsyncSession, school_id: int, grade_id: Optional[int] = None) -> List[Class]:
        stmt = select(Class).where(
            Class.school_id == school_id,
            Class.is_active == True,
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
        class_id: Optional[int] = None,
        grade_id: Optional[int] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[Student], int]:
        """分页查询学生列表，返回 (students, total)"""
        conditions = [Student.school_id == school_id, Student.is_active == True]
        if class_id:
            conditions.append(Student.class_id == class_id)
        if grade_id:
            conditions.append(Student.grade_id == grade_id)

        count_stmt = select(Student).where(*conditions)
        count_result = await db.execute(count_stmt)
        total = len(count_result.scalars().all())

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
    async def get_enabled_modules(db: AsyncSession, school_id: int) -> List[str]:
        """获取某学校当前启用的模块代码列表"""
        result = await db.execute(
            select(SchoolModule.module_code).where(
                SchoolModule.school_id == school_id,
                SchoolModule.enabled == True,
            )
        )
        return [row[0] for row in result.all()]

    @staticmethod
    async def set_module_state(
        db: AsyncSession, school_id: int, module_code: str, enabled: bool, config: Optional[dict] = None
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
