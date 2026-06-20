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

    # 5. 为默认学校 (school_id=1) 加载模块
    async with AsyncSessionLocal() as session:
        try:
            results = await module_loader.load_for_school(
                school_id=1,
                db_session=session,
                fastapi_app=app,
            )
            logger.info("\n" + module_loader.get_load_report())
        except Exception as e:
            logger.error(f"模块加载异常: {e}", exc_info=True)

    logger.info("Wings 3.0 全部引擎就绪 ✓")
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
    """创建默认学校和管理员账号（幂等）"""
    from sqlalchemy import select
    from core.models import School, User, UserRole, SchoolModule
    from core.services import AuthService

    async with AsyncSessionLocal() as session:
        # 检查默认学校是否存在
        result = await session.execute(select(School).where(School.id == 1))
        school = result.scalar_one_or_none()

        if not school:
            school = School(id=1, name="梨江中学", is_active=True)
            session.add(school)
            await session.commit()
            logger.info("默认学校已创建: 梨江中学 (id=1)")

        # 检查默认管理员
        result = await session.execute(
            select(User).where(User.username == "admin")
        )
        admin = result.scalar_one_or_none()

        if not admin:
            admin = User(
                username="admin",
                password_hash=AuthService.hash_password("admin123"),
                display_name="系统管理员",
                role=UserRole.MS_ADMIN,
                school_id=1,
                is_active=True,
            )
            session.add(admin)
            await session.commit()
            logger.info("默认管理员已创建: admin / admin123")

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
