"""
seed_sandbox_school2.py — 创建 school_id=2 沙箱环境

用途: Wings 3.0 多租户商业验证 — 一键创建第二所学校及其管理员
运行: cd /root/backend && .venv/bin/python3 seed_sandbox_school2.py

幂等设计: 所有操作使用 INSERT IGNORE / 检查存在性，重复运行安全
"""

import asyncio
import sys
import os

# 确保 backend 在路径中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 加载 .env
from dotenv import load_dotenv
load_dotenv()

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select, text

DATABASE_URL = os.getenv("DATABASE_URL", "mysql+aiomysql://grade7:waOPKoyFf4ByQD1h@127.0.0.1:3307/wings3")

engine = create_async_engine(DATABASE_URL, echo=False, pool_size=5)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def seed_school2():
    """创建 school_id=2 沙箱环境（幂等）"""
    from core.models import School, User, UserRole, SchoolModule
    from core.services import AuthService

    async with AsyncSessionLocal() as session:
        # ── Step 1: 创建学校 ──
        result = await session.execute(select(School).where(School.id == 2))
        school = result.scalar_one_or_none()

        if not school:
            school = School(
                id=2,
                name="沙箱实验中学",
                is_active=True,
            )
            session.add(school)
            await session.commit()
            print("✓ 学校已创建: 沙箱实验中学 (id=2)")
        else:
            # 确保 is_active
            if not school.is_active:
                school.is_active = True
                await session.commit()
                print("✓ 学校已激活: 沙箱实验中学 (id=2)")
            else:
                print("○ 学校已存在: 沙箱实验中学 (id=2)")

        # ── Step 2: 创建管理员 ──
        result = await session.execute(
            select(User).where(User.username == "sandbox_admin")
        )
        admin = result.scalar_one_or_none()

        if not admin:
            admin_pw = "admin123"
            admin = User(
                username="sandbox_admin",
                password_hash=AuthService.hash_password(admin_pw),
                display_name="沙箱管理员",
                role=UserRole.MS_ADMIN,
                school_id=2,
                is_active=True,
                password_change_required=True,
            )
            session.add(admin)
            await session.commit()
            print(f"✓ 管理员已创建: sandbox_admin / {admin_pw}")
        else:
            print("○ 管理员已存在: sandbox_admin")

        # ── Step 3: 启用全部 14 模块 ──
        ALL_MODULES = [
            "attendance", "behavior", "red_flag", "evaluation",
            "discipline", "reports", "ai_prescription", "notifications",
            "dashboard", "growth", "policy_engine", "risk_models",
            "teach_math", "approval", "parent_portal", "grades", "lineage",
        ]

        enabled_count = 0
        for module_code in ALL_MODULES:
            result = await session.execute(
                select(SchoolModule).where(
                    SchoolModule.school_id == 2,
                    SchoolModule.module_code == module_code,
                )
            )
            mod = result.scalar_one_or_none()

            if not mod:
                mod = SchoolModule(
                    school_id=2,
                    module_code=module_code,
                    enabled=True,
                )
                session.add(mod)
                enabled_count += 1
            elif not mod.enabled:
                mod.enabled = True
                enabled_count += 1

        await session.commit()
        print(f"✓ 模块已启用: {enabled_count} 新建, 共 {len(ALL_MODULES)} 个")

        # ── Step 4: 创建组织架构（年级 + 班级） ──
        from core.models import Grade, Class

        # 年级
        grade_names = ["七年级", "八年级", "九年级"]
        grade_map = {}
        for gname in grade_names:
            result = await session.execute(
                select(Grade).where(Grade.school_id == 2, Grade.name == gname)
            )
            grade = result.scalar_one_or_none()
            if not grade:
                grade = Grade(name=gname, school_id=2, sort_order=len(grade_map), is_active=True)
                session.add(grade)
                await session.flush()
            grade_map[gname] = grade

        await session.commit()
        print(f"✓ 年级已创建: {list(grade_map.keys())}")

        # 班级（每年级 2 个班）
        for gname, grade in grade_map.items():
            for i in range(1, 3):
                cname = f"{gname}{i}班"
                result = await session.execute(
                    select(Class).where(Class.school_id == 2, Class.grade_id == grade.id, Class.name == cname)
                )
                cls = result.scalar_one_or_none()
                if not cls:
                    cls = Class(
                        name=cname, school_id=2, grade_id=grade.id,
                        student_count=0, is_active=True,
                    )
                    session.add(cls)

        await session.commit()
        print(f"✓ 班级已创建: 6 个 (3年级×2班)")

        # ── 总结 ──
        print("\n" + "=" * 50)
        print("  school_id=2 沙箱环境就绪")
        print("=" * 50)
        print(f"  学校: 沙箱实验中学 (id=2)")
        print(f"  管理员: sandbox_admin / admin123")
        print(f"  角色: ms_admin")
        print(f"  模块: {len(ALL_MODULES)} 个全部启用")
        print(f"  组织: 3 年级, 6 班级")
        print("=" * 50)


if __name__ == "__main__":
    asyncio.run(seed_school2())
