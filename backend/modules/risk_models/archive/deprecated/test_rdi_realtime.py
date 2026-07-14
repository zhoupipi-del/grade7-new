#!/usr/bin/env python3
"""
测试 RiskDeviationIndexCalculator.calculate_rdi() — 直接在服务器上运行
"""

import asyncio
import logging
import os
import sys

# 配置日志
logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# 切换到项目目录
os.chdir("/root/backend")

# 添加项目路径
sys.path.insert(0, "/root/backend")

from modules.risk_models.services import RiskDeviationIndexCalculator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker


async def test_calculate_rdi(student_id: int = 6, school_id: int = 1):
    """测试 RDI 计算"""
    print(f"🧪 开始测试 RDI 计算: student_id={student_id}, school_id={school_id}")

    # 创建异步数据库引擎
    engine = create_async_engine(
        os.environ.get("DATABASE_URL", ""),
        echo=False,
        pool_size=5,
        max_overflow=10,
    )
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        try:
            # 创建计算器
            calculator = RiskDeviationIndexCalculator(db, school_id)

            # 计算 RDI
            print("\n⏳ 正在计算 RDI...")
            start_time = asyncio.get_event_loop().time()
            result = await calculator.calculate_rdi(student_id)
            end_time = asyncio.get_event_loop().time()

            # 输出结果
            print("\n" + "=" * 60)
            print("📊 RDI 计算结果:")
            print("=" * 60)
            for key, value in result.items():
                if key == "suppression_reason" and value is None:
                    continue
                print(f"  {key}: {value}")
            print("=" * 60)
            print(f"\n⏱️ 总耗时: {(end_time - start_time) * 1000:.2f}ms")
            print("✅ 测试通过！")

        except Exception as e:
            print(f"\n❌ 测试失败: {e}")
            import traceback

            traceback.print_exc()

    await engine.dispose()


if __name__ == "__main__":
    student_id = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    school_id = int(sys.argv[2]) if len(sys.argv) > 2 else 1

    print(f"🚀 启动测试: student_id={student_id}, school_id={school_id}")
    asyncio.run(test_calculate_rdi(student_id, school_id))
