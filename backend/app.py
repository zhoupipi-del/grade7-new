"""
app.py — Wings 3.0 飞机总装车间

FastAPI 异步主入口，负责:
1. 加载 .env 环境变量
2. 初始化异步数据库引擎
3. 注册核心路由 (core)
4. 启动 ModuleLoader 动态加载业务模块
5. 提供全局中间件与异常处理
"""

import os
import sys
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text

# ── 确保 backend 目录在 sys.path 中 ──
BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


# ═══════════════════════════════════════════════════════════════
# 环境变量加载
# ═══════════════════════════════════════════════════════════════

def _load_dotenv():
    """加载 .env 文件到 os.environ（仅设置尚未定义的环境变量）"""
    env_path = BACKEND_DIR / ".env"
    if not env_path.is_file():
        return

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


_load_dotenv()


# ═══════════════════════════════════════════════════════════════
# 日志配置
# ═══════════════════════════════════════════════════════════════

def _setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # 抑制 SQLAlchemy 的 DEBUG 日志
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


_setup_logging()
logger = logging.getLogger("wings3")


# ═══════════════════════════════════════════════════════════════
# 数据库引擎
# ═══════════════════════════════════════════════════════════════

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "mysql+aiomysql://grade7:waOPKoyFf4ByQD1h@127.0.0.1:3307/grade7_new",
)

# 异步引擎
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_recycle=300,
    pool_size=5,
    max_overflow=10,
    pool_timeout=30,
)

# 异步会话工厂
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ═══════════════════════════════════════════════════════════════
# 模块加载器（顶层初始化，lifespan 中调用）
# ═══════════════════════════════════════════════════════════════

from module_loader import ModuleLoader

modules_dir = str(BACKEND_DIR / "modules")
module_loader = ModuleLoader(modules_dir)


# ═══════════════════════════════════════════════════════════════
# 应用生命周期
# ═══════════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动/关闭时的初始化与清理"""
    # ── 启动: 创建表 + 种子数据 + 加载模块 ──
    logger.info("═" * 50)
    logger.info("Wings 3.0 点火启动中...")
    logger.info(f"数据库: {DATABASE_URL.split('@')[-1] if '@' in DATABASE_URL else DATABASE_URL}")

    # 1. 创建所有表（core + 所有已导入模块共用同一个 declarative Base）
    from core.models import Base
    # 触发模块模型导入，确保所有表注册到 Base.metadata
    import modules.attendance.models  # noqa: F401
    import modules.behavior.models    # noqa: F401
    import modules.red_flag.models      # noqa: F401
    import modules.evaluation.models     # noqa: F401
    import modules.discipline.models    # noqa: F401
    import modules.reports.models      # noqa: F401
    import modules.ai_prescription.models  # noqa: F401
    import modules.notifications.models   # noqa: F401
    import modules.dashboard.models        # noqa: F401  (纯聚合，不建表)
    import modules.growth.models          # noqa: F401  (只读融合模块，不建表)
    import modules.approval.models        # noqa: F401
    import modules.teach_math.models     # noqa: F401
    import modules.risk_models.models    # noqa: F401
    import modules.parent_portal.models  # noqa: F401
    import modules.grades.models         # noqa: F401
    import modules.lineage.models       # noqa: F401
    import modules.data_adapter.models  # noqa: F401
    # ── P0 新模块：学籍 + 班级管理（数据铁三角）──
    import modules.student_registry.models  # noqa: F401
    import modules.class_mgmt.models       # noqa: F401
    import modules.teacher_mgmt.models    # noqa: F401
    import modules.timetable.models      # noqa: F401
    # ── Phase 2 心理关怀：咨询预约 + 工作台 + 心理档案 + 双轨预警 ──
    import modules.psych_counseling.models  # noqa: F401
    import modules.psych_profiles.models   # noqa: F401
    # ── Phase 2 教研铁三角：集体备课 + 听课评课 + 教研活动 (100%合围) ──
    import modules.research_lesson_prep.models  # noqa: F401
    import modules.research_observation.models  # noqa: F401
    import modules.research_activities.models   # noqa: F401
    # ── Phase 3 教务板块：作业管理 + 错题断层漏斗 ──
    import modules.homework_mgmt.models   # noqa: F401
    import modules.error_funnel.models    # noqa: F401
    # ── 三级组织架构模型（Organization/Branch/CascadingConfig/ScopeType）──
    # 已通过 `from core.models import Base` 的模块级加载注册到 Base.metadata
    # create_all 将自动建表: organizations / branches / cascading_configs
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info("数据库表初始化完成")

    # 3. 种子数据: 默认学校 + 管理员
    await _seed_default_data()

    # 4. 模块发现 + 拓扑排序
    manifests = module_loader.discover()
    sorted_codes, missing = module_loader.sort()

    logger.info(f"模块清单: {list(manifests.keys())}")
    logger.info(f"加载顺序: {' → '.join(sorted_codes)}")
    if missing:
        logger.warning(f"缺失依赖: {missing}")

    # 5. 全局模块加载 + 级联配置感知（多租户 SaaS 底座）
    #    FastAPI 路由注册是进程级的，不可按租户拆分 → 并集模式全局注册
    #    各 endpoint 内部用 TenantContext.get_config() 或 build_scope_filter() 做开关校验
    async with AsyncSessionLocal() as session:
        try:
            from core.models import School, SchoolModule
            from sqlalchemy import select

            # 查询所有活跃学校
            schools_result = await session.execute(
                select(School).where(School.is_active == True)
            )
            schools = schools_result.scalars().all()

            # 收集所有学校的启用模块并集（全局路由注册）
            all_enabled_modules: set = set()
            for school in schools:
                mods_result = await session.execute(
                    select(SchoolModule.module_code).where(
                        SchoolModule.school_id == school.id,
                        SchoolModule.enabled == True,
                    )
                )
                all_enabled_modules.update(row[0] for row in mods_result.all())

            logger.info(
                f"多租户模块加载: {len(schools)} 活跃学校 "
                f"({[s.name for s in schools]}), 模块并集: {all_enabled_modules}"
            )

            # ── 全局路由注册 + 级联配置解析（委托给 module_loader）──
            if all_enabled_modules:
                results = await module_loader.load_for_school(
                    school_id=0,  # sentinel: 全局路由注册（进程级不可拆分）
                    db_session=session,
                    fastapi_app=app,
                    enabled_module_codes=all_enabled_modules,
                    resolve_configs=True,  # 级联配置解析 + 日志输出
                )
            else:
                # Fallback: 至少加载 school_id=1
                results = await module_loader.load_for_school(
                    school_id=1,
                    db_session=session,
                    fastapi_app=app,
                    resolve_configs=True,
                )

            logger.info("\n" + module_loader.get_load_report())
        except Exception as e:
            logger.error(f"模块加载异常: {e}", exc_info=True)

    logger.info("Wings 3.0 全部引擎就绪 ✓")

    # 6. PolicyEngine 启动注入 — 数字宪法加载
    try:
        from modules.policy_engine import PolicyEngine, set_engine
        policy_yaml_path = str(BACKEND_DIR / "policy.yaml")
        pe = PolicyEngine.from_yaml(policy_yaml_path)
        set_engine(pe)
        app.state.policy_engine = pe
        logger.info(f"PolicyEngine 数字宪法已加载: {policy_yaml_path}")
    except Exception as e:
        logger.error(f"PolicyEngine 加载失败(降级模式，Hook将跳过): {e}", exc_info=True)

    logger.info("═" * 50)

    yield  # ← 应用运行中

    # ── 关闭: 清理资源 ──
    logger.info("Wings 3.0 正在关闭...")
    await engine.dispose()
    logger.info("数据库连接池已释放")


# ═══════════════════════════════════════════════════════════════
# 种子数据
# ═══════════════════════════════════════════════════════════════

async def _seed_default_data():
    """创建默认组织/片区/学校和管理员账号（幂等，支持三级架构初始化）"""
    from sqlalchemy import select
    from core.models import (
        School, User, UserRole, SchoolModule,
        Organization, Branch, ScopeType,
    )
    from core.services import AuthService

    async with AsyncSessionLocal() as session:
        # ── Step 1: 默认集团/教育集团 ──
        result = await session.execute(
            select(Organization).where(Organization.code == "lijiang-edu")
        )
        org = result.scalar_one_or_none()

        if not org:
            org = Organization(
                id=1,
                name="梨江教育集团",
                code="lijiang-edu",
                is_active=True,
            )
            session.add(org)
            await session.commit()
            logger.info("默认集团已创建: 梨江教育集团 (id=1, code=lijiang-edu)")

        # ── Step 2: 默认片区/校区（幂等：优先按 code 查找，兜底按 id=1 查找）──
        result = await session.execute(
            select(Branch).where(
                Branch.org_id == org.id,
                Branch.code == "changsha-xingsha",
            )
        )
        branch = result.scalar_one_or_none()

        if not branch:
            # 迁移脚本可能已插入 id=1 但 code 不同，兜底查找
            result2 = await session.execute(
                select(Branch).where(Branch.id == 1)
            )
            branch = result2.scalar_one_or_none()

        if not branch:
            branch = Branch(
                id=1,
                org_id=org.id,
                name="长沙县星沙片区",
                code="changsha-xingsha",
                is_active=True,
            )
            session.add(branch)
            await session.commit()
            logger.info(f"默认片区已创建: 长沙县星沙片区 (id=1, org_id={org.id})")
        elif branch.code != "changsha-xingsha":
            # 统一 code 命名
            old_code = branch.code
            branch.code = "changsha-xingsha"
            await session.commit()
            logger.info(f"默认片区 code 已统一: {old_code} → changsha-xingsha")

        # ── Step 3: 默认学校 ──
        result = await session.execute(select(School).where(School.id == 1))
        school = result.scalar_one_or_none()

        if not school:
            school = School(
                id=1,
                name="梨江中学",
                school_phase="junior",
                is_active=True,
                org_id=org.id,
                branch_id=branch.id,
            )
            session.add(school)
            await session.commit()
            logger.info(f"默认学校已创建: 梨江中学 (id=1, phase=junior, org_id={org.id}, branch_id={branch.id})")
        else:
            # 向下兼容: 补齐已有学校的 org_id/branch_id/phase（旧数据可能为 None）
            needs_commit = False
            if school.org_id is None or school.branch_id is None:
                school.org_id = org.id
                school.branch_id = branch.id
                needs_commit = True
            if not school.school_phase:
                school.school_phase = "junior"
                needs_commit = True
                logger.info(f"学校梨江中学 school_phase 已补齐: junior (默认值)")
            if needs_commit:
                await session.commit()
                logger.info(f"学校梨江中学 org_id/branch_id 已补齐: org={org.id}, branch={branch.id}")

        # ── Step 4: 默认管理员 ──
        result = await session.execute(
            select(User).where(User.username == "admin")
        )
        admin = result.scalar_one_or_none()

        if not admin:
            import secrets as _secrets
            admin_pw = _secrets.token_urlsafe(12)
            admin = User(
                username="admin",
                password_hash=AuthService.hash_password(admin_pw),
                display_name="系统管理员",
                role=UserRole.MS_ADMIN,
                school_id=1,
                org_id=org.id,
                branch_id=branch.id,
                is_active=True,
                password_change_required=True,
            )
            session.add(admin)
            await session.commit()
            logger.info("=" * 60)
            logger.info(f"默认管理员已创建: admin / {admin_pw}")
            logger.info("⚠️  请立即登录并修改此密码！首次登录将强制要求改密。")
            logger.info("=" * 60)
        else:
            # 向下兼容: 补齐已有管理员 org_id/branch_id
            if admin.org_id is None or admin.branch_id is None:
                admin.org_id = org.id
                admin.branch_id = branch.id
                await session.commit()
                logger.info(f"管理员 admin org_id/branch_id 已补齐: org={org.id}, branch={branch.id}")

        # 确保 attendance 模块配置存在
        result = await session.execute(
            select(SchoolModule).where(
                SchoolModule.school_id == 1,
                SchoolModule.module_code == "attendance",
            )
        )
        sm = result.scalar_one_or_none()
        if not sm:
            sm = SchoolModule(
                school_id=1,
                module_code="attendance",
                enabled=True,
            )
            session.add(sm)
            await session.commit()
            logger.info("默认模块已配置: attendance (已启用)")

        # 确保 behavior 模块配置存在
        result = await session.execute(
            select(SchoolModule).where(
                SchoolModule.school_id == 1,
                SchoolModule.module_code == "behavior",
            )
        )
        sm = result.scalar_one_or_none()
        if not sm:
            sm = SchoolModule(
                school_id=1,
                module_code="behavior",
                enabled=True,
            )
            session.add(sm)
            await session.commit()
            logger.info("默认模块已配置: behavior (已启用)")

        # 确保 red_flag 模块配置存在
        result = await session.execute(
            select(SchoolModule).where(
                SchoolModule.school_id == 1,
                SchoolModule.module_code == "red_flag",
            )
        )
        sm = result.scalar_one_or_none()
        if not sm:
            sm = SchoolModule(
                school_id=1,
                module_code="red_flag",
                enabled=True,
            )
            session.add(sm)
            await session.commit()
            logger.info("默认模块已配置: red_flag (已启用)")

        # 确保 evaluation 模块配置存在
        result = await session.execute(
            select(SchoolModule).where(
                SchoolModule.school_id == 1,
                SchoolModule.module_code == "evaluation",
            )
        )
        sm = result.scalar_one_or_none()
        if not sm:
            sm = SchoolModule(
                school_id=1,
                module_code="evaluation",
                enabled=True,
            )
            session.add(sm)
            await session.commit()
            logger.info("默认模块已配置: evaluation (已启用)")

        # 确保 discipline 模块配置存在
        result = await session.execute(
            select(SchoolModule).where(
                SchoolModule.school_id == 1,
                SchoolModule.module_code == "discipline",
            )
        )
        sm = result.scalar_one_or_none()
        if not sm:
            sm = SchoolModule(
                school_id=1,
                module_code="discipline",
                enabled=True,
            )
            session.add(sm)
            await session.commit()
            logger.info("默认模块已配置: discipline (已启用)")

        # 确保 reports 模块配置存在
        result = await session.execute(
            select(SchoolModule).where(
                SchoolModule.school_id == 1,
                SchoolModule.module_code == "reports",
            )
        )
        sm = result.scalar_one_or_none()
        if not sm:
            sm = SchoolModule(
                school_id=1,
                module_code="reports",
                enabled=True,
            )
            session.add(sm)
            await session.commit()
            logger.info("默认模块已配置: reports (已启用)")

        # 确保 ai_prescription 模块配置存在
        result = await session.execute(
            select(SchoolModule).where(
                SchoolModule.school_id == 1,
                SchoolModule.module_code == "ai_prescription",
            )
        )
        sm = result.scalar_one_or_none()
        if not sm:
            sm = SchoolModule(
                school_id=1,
                module_code="ai_prescription",
                enabled=True,
            )
            session.add(sm)
            await session.commit()
            logger.info("默认模块已配置: ai_prescription (已启用)")

        # 确保 notifications 模块配置存在
        result = await session.execute(
            select(SchoolModule).where(
                SchoolModule.school_id == 1,
                SchoolModule.module_code == "notifications",
            )
        )
        sm = result.scalar_one_or_none()
        if not sm:
            sm = SchoolModule(
                school_id=1,
                module_code="notifications",
                enabled=True,
            )
            session.add(sm)
            await session.commit()
            logger.info("默认模块已配置: notifications (已启用)")

        # ── teach_math 模块 ──────────────────────
        result = await session.execute(
            select(SchoolModule).where(
                SchoolModule.school_id == 1,
                SchoolModule.module_code == "teach_math",
            )
        )
        sm = result.scalar_one_or_none()
        if not sm:
            sm = SchoolModule(
                school_id=1,
                module_code="teach_math",
                enabled=True,
            )
            session.add(sm)
            await session.commit()
            logger.info("默认模块已配置: teach_math (已启用)")

        # ── grades 模块 ──────────────────────
        result = await session.execute(
            select(SchoolModule).where(
                SchoolModule.school_id == 1,
                SchoolModule.module_code == "grades",
            )
        )
        sm = result.scalar_one_or_none()
        if not sm:
            sm = SchoolModule(
                school_id=1,
                module_code="grades",
                enabled=True,
            )
            session.add(sm)
            await session.commit()
            logger.info("默认模块已配置: grades (已启用)")

        # ── lineage 模块 ──────────────────────
        result = await session.execute(
            select(SchoolModule).where(
                SchoolModule.school_id == 1,
                SchoolModule.module_code == "lineage",
            )
        )
        sm = result.scalar_one_or_none()
        if not sm:
            sm = SchoolModule(
                school_id=1,
                module_code="lineage",
                enabled=True,
            )
            session.add(sm)
            await session.commit()
            logger.info("默认模块已配置: lineage (已启用)")


# ═══════════════════════════════════════════════════════════════
# FastAPI 应用实例
# ═══════════════════════════════════════════════════════════════

app = FastAPI(
    title="Wings 3.0 — 梨江中学德育管理平台",
    description="SaaS 多租户模块化德育管理系统",
    version="3.0.0-alpha",
    lifespan=lifespan,
)

# CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应限制
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ═══════════════════════════════════════════════════════════════
# DB 依赖覆盖
# ═══════════════════════════════════════════════════════════════

from core.routers import get_db as _core_get_db


async def get_db_override():
    """覆盖 core.routers.get_db，提供真实的异步会话"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


app.dependency_overrides[_core_get_db] = get_db_override


# ═══════════════════════════════════════════════════════════════
# 核心路由注册
# ═══════════════════════════════════════════════════════════════

from core.routers import router as core_router
app.include_router(core_router)


# ═══════════════════════════════════════════════════════════════
# 全局异常处理
# ═══════════════════════════════════════════════════════════════

# 模块领域异常的顶层导入（供全局异常处理器使用）
from modules.attendance.exceptions import AttendanceError


@app.exception_handler(AttendanceError)
async def attendance_global_handler(request: Request, exc: AttendanceError):
    """AttendanceError → HTTP 统一翻译器（覆盖所有模块）"""
    return JSONResponse(
        status_code=exc.http_status,
        content={"detail": str(exc)},
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """大坝式异常处理 — 兜底所有未捕获异常"""
    logger.error(f"未处理异常 [{request.method} {request.url.path}]: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "服务器内部错误",
            "error_code": "INTERNAL_ERROR",
        },
    )


@app.exception_handler(404)
async def not_found_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=404,
        content={"detail": "资源不存在", "path": request.url.path},
    )


# ═══════════════════════════════════════════════════════════════
# 健康检查（直接挂载，不走模块）
# ═══════════════════════════════════════════════════════════════

@app.get("/")
async def root():
    return {
        "app": "Wings 3.0",
        "version": "3.0.0-alpha",
        "status": "operational",
    }


@app.get("/ping")
async def ping():
    """数据库连通性检测"""
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={"status": "error", "database": str(e)},
        )


# ═══════════════════════════════════════════════════════════════
# 启动入口
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=os.environ.get("ENV") == "development",
        log_level="info",
    )
