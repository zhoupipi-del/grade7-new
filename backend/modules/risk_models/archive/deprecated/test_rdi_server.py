#!/usr/bin/env python3
"""
服务器上执行的测试脚本：测试 RiskDeviationIndexCalculator.calculate_rdi()
"""
import asyncio
import sys
import logging

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# 添加项目路径
import os
os.chdir("/root/backend")

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from modules.risk_models.services import RiskDeviationIndexCalculator, get_local_now


async def test_calculate_rdi(student_id: int = 6, school_id: int = 1):
    """测试 RDI 计算"""
    print(f"🧪 开始测试 RDI 计算: student_id={student_id}, school_id={school_id}")

    # 创建异步数据库引擎
    engine = create_async_engine(
        "mysql+aiomysql://grade7:waOPKoyFf4ByQD1h@127.0.0.1:3307/wings3",
        echo=False,
    )
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        try:
            # 创建计算器
            calculator = RiskDeviationIndexCalculator(db, school_id)

            # 计算 RDI
            start_time = asyncio.get_event_loop().time()
            result = await calculator.calculate_rdi(student_id)
            end_time = asyncio.get_event_loop().time()

            # 输出结果
            print("\n" + "="*60)
            print("📊 RDI 计算结果:")
            print("="*60)
            for key, value in result.items():
                print(f"  {key}: {value}")
            print("="*60)
            print(f"\n⏱️ 总耗时: {(end_time - start_time)*1000:.2f}ms")
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
