"""
测试脚本：测试 RiskDeviationIndexCalculator.calculate_rdi()
"""
import asyncio
import sys
import os

# 添加项目路径
sys.path.insert(0, "/root/backend")

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from modules.risk_models.services import RiskDeviationIndexCalculator, load_policy_config


async def test_calculate_rdi(student_id: int = 6):
    """测试 RDI 计算"""
    print(f"🧪 开始测试 RDI 计算: student_id={student_id}")

    # 创建异步数据库会话
    # TODO: 使用实际的数据库连接
    # engine = create_async_engine("mysql+aiomysql://grade7:password@127.0.0.1:3307/wings3")
    # async_session = sessionmaker(engine, class_=AsyncSession)

    # 临时模拟
    print("⚠️ 注意: 当前使用模拟数据，实际需要连接数据库")
    print("📝 测试结果 (模拟):")
    print({
        "student_id": student_id,
        "rdi_score": 1.85,
        "risk_level": "attention",
        "behavior_deviation": 1.2,
        "attendance_deviation": -0.3,
        "score_deviation": 0.8,
        "warning_suppressed": False,
        "recommended_action": "heart_to_heart",
        "compute_latency_ms": 45.2,
    })


if __name__ == "__main__":
    student_id = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    asyncio.run(test_calculate_rdi(student_id))
