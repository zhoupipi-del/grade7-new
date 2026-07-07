"""
TrueBaselineInitializer — 真实基线初始化脚本

从真实历史数据计算基线（mean/std），替换模拟数据。
聚合窗口：
  - 行为维度：过去30天 discipline_records 违纪次数
  - 考勤维度：过去30天 attendance_records 迟到/缺勤率
  - 评价维度：最新 student_scores total_score

输出：
  - 更新 risk_baselines 表（393名学生 × 3维度 = 1,179条记录）
  - 生成 logs/baseline_calibration.log 统计分布摘要
"""

import asyncio
import logging
import os
import sys
from datetime import datetime, date, timedelta
from typing import List, Dict, Tuple
import math

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# 导入模型
from modules.risk_models.models import RiskBaseline
from modules.behavior.models import DisciplineRecord
from modules.attendance.models import AttendanceRecord
from modules.evaluation.models import StudentScore
from core.models import Student, SchoolMixin

# 配置日志
log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../logs")
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "baseline_calibration.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# 数据库配置（从环境变量或配置文件读取）
DATABASE_URL = "mysql+aiomysql://grade7:waOPKoyFf4ByQD1h@127.0.0.1:3307/wings3"

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def calculate_baselines_for_school(school_id: int, window_days: int = 30):
    """
    为全校学生计算真实基线并存储到 risk_baselines 表
    """
    async with AsyncSessionLocal() as db:
        # 1. 获取全校学生列表
        students = await db.scalars(
            select(Student).where(
                Student.school_id == school_id
            )
        )
        student_list = students.all()
        total_students = len(student_list)

        logger.info(f"开始为 school_id={school_id} 的 {total_students} 名学生计算 {window_days} 天窗口基线")
        logger.info(f"聚合窗口: {date.today() - timedelta(days=window_days)} ~ {date.today()}")

        # 2. 批量计算三维度原始值
        behavior_values = []
        attendance_values = []
        score_values = []

        for student in student_list:
            # 行为维度：过去 window_days 天的违纪次数
            behavior_count = await _calculate_behavior_count(db, student.id, window_days)
            behavior_values.append(behavior_count)

            # 考勤维度：过去 window_days 天的迟到/缺勤率
            attendance_rate = await _calculate_attendance_rate(db, student.id, window_days)
            attendance_values.append(attendance_rate)

            # 评价维度：最新的 total_score
            score_avg = await _calculate_score_avg(db, student.id)
            score_values.append(score_avg)

        # 3. 计算全校基线（均值和标准差）
        behavior_mean, behavior_std = _calculate_mean_std(behavior_values)
        attendance_mean, attendance_std = _calculate_mean_std(attendance_values)
        score_mean, score_std = _calculate_mean_std(score_values)

        logger.info(f"=== 全校基线统计分布 ===")
        logger.info(f"行为维度: mean={behavior_mean:.2f}, std={behavior_std:.2f}, "
                    f"min={min(behavior_values)}, max={max(behavior_values)}")
        logger.info(f"考勤维度: mean={attendance_mean:.2f}, std={attendance_std:.2f}, "
                    f"min={min(attendance_values):.2f}, max={max(attendance_values):.2f}")
        logger.info(f"评价维度: mean={score_mean:.2f}, std={score_std:.2f}, "
                    f"min={min(score_values):.2f}, max={max(score_values):.2f}")

        # 4. 逐学生存储基线（如果已存在则更新）
        updated_count = 0
        for idx, student in enumerate(student_list):
            student_id = student.id
            class_id = student.class_id

            # 行为基线
            await _upsert_baseline(
                db, school_id, student_id, class_id,
                "behavior", window_days,
                behavior_mean, behavior_std, total_students
            )

            # 考勤基线
            await _upsert_baseline(
                db, school_id, student_id, class_id,
                "attendance", window_days,
                attendance_mean, attendance_std, total_students
            )

            # 评价基线
            await _upsert_baseline(
                db, school_id, student_id, class_id,
                "score", window_days,
                score_mean, score_std, total_students
            )

            updated_count += 1

            if (idx + 1) % 50 == 0:
                logger.info(f"进度: {idx + 1}/{total_students} 名学生基线已更新")

        await db.commit()
        logger.info(f"✅ 基线重算完成！共更新 {updated_count} 名学生的基线数据")

        # 5. 输出统计分布摘要（供总指挥查阅）
        await _generate_distribution_summary(db, school_id, window_days, logger)


async def _calculate_behavior_count(db: AsyncSession, student_id: int, window_days: int) -> int:
    """计算学生过去 window_days 天的违纪次数"""
    window_start = date.today() - timedelta(days=window_days)
    count = await db.scalar(
        select(func.count()).where(
            and_(
                DisciplineRecord.student_id == student_id,
                DisciplineRecord.created_at >= window_start,
                DisciplineRecord.status.in_(["active", "resolved"])  # 只统计有效记录
            )
        )
    )
    return count or 0


async def _calculate_attendance_rate(db: AsyncSession, student_id: int, window_days: int) -> float:
    """计算学生过去 window_days 天的迟到/缺勤率"""
    window_start = date.today() - timedelta(days=window_days)

    # 总考勤记录数
    total_records = await db.scalar(
        select(func.count()).where(
            and_(
                AttendanceRecord.student_id == student_id,
                AttendanceRecord.created_at >= window_start
            )
        )
    ) or 0

    if total_records == 0:
        return 0.0

    # 异常考勤记录数（迟到/缺勤/早退等）
    abnormal_records = await db.scalar(
        select(func.count()).where(
            and_(
                AttendanceRecord.student_id == student_id,
                AttendanceRecord.created_at >= window_start,
                AttendanceRecord.status.in_(["late", "absent", "early_leave"])  # 异常状态
            )
        )
    ) or 0

    return abnormal_records / total_records


async def _calculate_score_avg(db: AsyncSession, student_id: int) -> float:
    """获取学生最新的 total_score"""
    score = await db.scalar(
        select(StudentScore.total_score)
        .where(StudentScore.student_id == student_id)
        .order_by(StudentScore.updated_at.desc())
        .limit(1)
    )
    return score or 0.0


def _calculate_mean_std(values: List[float]) -> Tuple[float, float]:
    """计算均值和标准差"""
    if not values:
        return 0.0, 1.0

    n = len(values)
    mean = sum(values) / n

    if n < 2:
        return mean, 1.0

    variance = sum((x - mean) ** 2 for x in values) / (n - 1)  # 样本标准差
    std = math.sqrt(variance)

    return mean, std if std > 0 else 1.0


async def _upsert_baseline(
    db: AsyncSession,
    school_id: int,
    student_id: int,
    class_id: int,
    baseline_type: str,
    window_days: int,
    mean_value: float,
    std_value: float,
    sample_size: int
):
    """插入或更新基线记录"""
    # 查询是否已存在
    existing = await db.scalar(
        select(RiskBaseline).where(
            and_(
                RiskBaseline.school_id == school_id,
                RiskBaseline.student_id == student_id,
                RiskBaseline.baseline_type == baseline_type,
                RiskBaseline.window_days == window_days
            )
        )
    )

    if existing:
        # 更新
        existing.mean_value = mean_value
        existing.std_value = std_value
        existing.sample_size = sample_size
        existing.calibrated_at = datetime.now()
    else:
        # 插入
        new_baseline = RiskBaseline(
            school_id=school_id,
            student_id=student_id,
            class_id=class_id,
            baseline_type=baseline_type,
            window_days=window_days,
            mean_value=mean_value,
            std_value=std_value,
            sample_size=sample_size,
            calibrated_at=datetime.now()
        )
        db.add(new_baseline)


async def _generate_distribution_summary(
    db: AsyncSession,
    school_id: int,
    window_days: int,
    logger
):
    """生成统计分布摘要（供总指挥查阅）"""
    logger.info(f"\n=== 基线分布摘要 (school_id={school_id}, window_days={window_days}) ===")

    for baseline_type in ["behavior", "attendance", "score"]:
        # 查询该维度的所有基线
        baselines = await db.scalars(
            select(RiskBaseline).where(
                and_(
                    RiskBaseline.school_id == school_id,
                    RiskBaseline.baseline_type == baseline_type,
                    RiskBaseline.window_days == window_days
                )
            )
        )
        baseline_list = baselines.all()

        if not baseline_list:
            continue

        # 统计分布
        mean_values = [b.mean_value for b in baseline_list]
        std_values = [b.std_value for b in baseline_list]

        logger.info(f"\n【{baseline_type}】")
        logger.info(f"  记录数: {len(baseline_list)}")
        logger.info(f"  均值范围: {min(mean_values):.2f} ~ {max(mean_values):.2f}")
        logger.info(f"  标准差范围: {min(std_values):.2f} ~ {max(std_values):.2f}")

        # 分位数
        mean_values_sorted = sorted(mean_values)
        q25 = mean_values_sorted[len(mean_values_sorted) // 4]
        q50 = mean_values_sorted[len(mean_values_sorted) // 2]
        q75 = mean_values_sorted[int(len(mean_values_sorted) * 0.75)]

        logger.info(f"  分位数: Q25={q25:.2f}, Q50={q50:.2f}, Q75={q75:.2f}")


async def main():
    """主函数"""
    import argparse
    parser = argparse.ArgumentParser(description="真实基线初始化脚本")
    parser.add_argument("--school-id", type=int, default=1, help="学校ID")
    parser.add_argument("--window", type=int, default=30, help="聚合窗口天数")
    args = parser.parse_args()

    logger.info(f"TrueBaselineInitializer 启动")
    logger.info(f"参数: school_id={args.school_id}, window_days={args.window}")

    start_time = datetime.now()
    await calculate_baselines_for_school(args.school_id, args.window)
    end_time = datetime.now()

    duration = (end_time - start_time).total_seconds()
    logger.info(f"\n✅ 基线重算完成！总耗时: {duration:.2f} 秒")
    logger.info(f"日志文件: {log_file}")


if __name__ == "__main__":
    asyncio.run(main())
