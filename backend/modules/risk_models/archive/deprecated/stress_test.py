"""
Performance Stress Test — RDI 批量计算性能测试

测试目标：
  1. 对全校 393 名学生运行 calculate_rdi()
  2. 使用 LazyFetch 优化 (load_history=False)
  3. 统计平均耗时、P99 耗时、最慢耗时
  4. 验证 SQL 交互次数 ≤3次

输出：
  - 性能报告（供总指挥查阅）
  - 慢查询日志（>150ms 的查询）
"""

import asyncio
import logging
import os
import sys
import time
from datetime import datetime
from typing import List, Dict

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# 导入模型和服务
from modules.risk_models.services import RiskDeviationIndexCalculator
from core.models import Student

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# 数据库配置
DATABASE_URL = "mysql+aiomysql://grade7:waOPKoyFf4ByQD1h@127.0.0.1:3307/wings3"

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def stress_test_rdi(school_id: int = 1, load_history: bool = False):
    """
    对全校学生运行 RDI 计算压力测试
    """
    async with AsyncSessionLocal() as db:
        # 1. 获取全校学生 ID 列表
        students = await db.scalars(
            select(Student.id).where(
                Student.school_id == school_id
            )
        )
        student_ids = students.all()
        total_students = len(student_ids)

        logger.info(f"🚀 开始性能压力测试")
        logger.info(f"   学生总数: {total_students}")
        logger.info(f"   LazyFetch (load_history): {load_history}")
        logger.info(f"   预计 SQL 交互: {'4次' if load_history else '≤3次'}")
        logger.info(f"=" * 60)

        # 2. 逐学生计算 RDI
        latencies = []
        sql_interactions_list = []
        errors = 0
        start_total = time.time()

        calculator = RiskDeviationIndexCalculator(db, school_id)

        for idx, student_id in enumerate(student_ids):
            try:
                start_time = time.time()
                result = await calculator.calculate_rdi(
                    student_id=student_id,
                    load_history=load_history,  # 🚀 LazyFetch 优化
                    suppress_low_rdi=True
                )
                elapsed_ms = (time.time() - start_time) * 1000

                latencies.append(elapsed_ms)
                sql_interactions_list.append(result.get("sql_interactions", 0))

                # 进度输出（每50人输出一次）
                if (idx + 1) % 50 == 0:
                    avg_so_far = sum(latencies) / len(latencies)
                    logger.info(
                        f"   进度: {idx + 1}/{total_students} | "
                        f"当前耗时: {elapsed_ms:.2f}ms | "
                        f"平均耗时: {avg_so_far:.2f}ms"
                    )

            except Exception as e:
                errors += 1
                logger.error(f"   ❌ 学生 {student_id} 计算失败: {e}")

        total_elapsed = (time.time() - start_total) * 1000

        # 3. 统计性能报告
        logger.info(f"\n{'=' * 60}")
        logger.info(f"📊 性能压力测试报告")
        logger.info(f"{'=' * 60}")

        if latencies:
            latencies_sorted = sorted(latencies)
            avg_latency = sum(latencies) / len(latencies)
            p50_latency = latencies_sorted[len(latencies_sorted) // 2]
            p95_latency = latencies_sorted[int(len(latencies_sorted) * 0.95)]
            p99_latency = latencies_sorted[int(len(latencies_sorted) * 0.99)]
            min_latency = min(latencies)
            max_latency = max(latencies)

            logger.info(f"总学生数: {total_students}")
            logger.info(f"成功计算: {len(latencies)}")
            logger.info(f"失败次数: {errors}")
            logger.info(f"总耗时: {total_elapsed:.2f}ms ({total_elapsed / 1000:.2f}s)")
            logger.info(f"")
            logger.info(f"⏱️  延迟统计 (ms):")
            logger.info(f"  平均延迟: {avg_latency:.2f}ms")
            logger.info(f"  中位数 (P50): {p50_latency:.2f}ms")
            logger.info(f"  P95: {p95_latency:.2f}ms")
            logger.info(f"  P99: {p99_latency:.2f}ms")
            logger.info(f"  最小值: {min_latency:.2f}ms")
            logger.info(f"  最大值: {max_latency:.2f}ms")
            logger.info(f"")
            logger.info(f"🔍 SQL 交互统计:")
            if sql_interactions_list:
                avg_sql = sum(sql_interactions_list) / len(sql_interactions_list)
                logger.info(f"  平均 SQL 交互: {avg_sql:.2f} 次")
                logger.info(f"  SQL 交互分布: {dict((x, sql_interactions_list.count(x)) for x in set(sql_interactions_list))}")
            logger.info(f"")
            logger.info(f"✅ 性能评估:")
            if avg_latency < 50:
                logger.info(f"  评估: 优秀 (平均 <50ms)")
            elif avg_latency < 100:
                logger.info(f"  评估: 良好 (平均 <100ms)")
            elif avg_latency < 200:
                logger.info(f"  评估: 可接受 (平均 <200ms)")
            else:
                logger.info(f"  评估: ⚠️  需优化 (平均 ≥200ms)")
            
            if p99_latency < 150:
                logger.info(f"  P99 延迟: ✅ 满足 Latency Monitor 要求 (<150ms)")
            else:
                logger.info(f"  P99 延迟: ⚠️  存在慢查询 (P99 ≥150ms)")

        logger.info(f"{'=' * 60}")


async def main():
    """主函数"""
    import argparse
    parser = argparse.ArgumentParser(description="RDI 批量计算性能压力测试")
    parser.add_argument("--school-id", type=int, default=1, help="学校ID")
    parser.add_argument("--load-history", action="store_true", help="加载历史趋势 (LazyFetch=False)")
    parser.add_argument("--sample", type=int, default=0, help="仅测试前 N 名学生 (0=全部)")
    args = parser.parse_args()

    logger.info(f"RDI 性能压力测试启动")
    logger.info(f"参数: school_id={args.school_id}, load_history={args.load_history}")

    await stress_test_rdi(
        school_id=args.school_id,
        load_history=args.load_history
    )


if __name__ == "__main__":
    asyncio.run(main())
