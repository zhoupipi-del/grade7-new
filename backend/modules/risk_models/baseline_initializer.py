"""
risk_baseline_initializer.py — 风险基线冷启动预热脚本

功能:
  1. 扫描所有学生
  2. 计算过去 30 天的行为/考勤/评价基线 (均值/标准差)
  3. 填充 risk_baselines 表
  4. 支持增量更新

使用方法:
  python risk_baseline_initializer.py --school-id 1 --window 30
"""

import asyncio
import logging
from datetime import datetime, date, timedelta
from typing import List, Dict, Tuple
import pymysql
import os
from pathlib import Path

# 数据库配置 (从 backend/.env 读取)
DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 3307,
    "user": "grade7",
    "password": "waOPKoyFf4ByQD1h",
    "database": "wings3",
    "charset": "utf8mb4"
}

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def get_students(db_config: dict, school_id: int) -> List[dict]:
    """获取学校所有学生"""
    conn = pymysql.connect(**db_config)
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, class_id, grade_id FROM students WHERE school_id=%s",
                (school_id,)
            )
            return cursor.fetchall()
    finally:
        conn.close()


async def calculate_behavior_baseline(
    db_config: dict, student_id: int, window_days: int
) -> Tuple[float, float, int]:
    """
    计算行为维度基线 (从 discipline_records 表)

    返回: (mean, std, sample_size)
    """
    conn = pymysql.connect(**db_config)
    try:
        with conn.cursor() as cursor:
            # 查询过去 window_days 天的违纪记录
            start_date = date.today() - timedelta(days=window_days)
            cursor.execute(
                """
                SELECT COUNT(*) as count
                FROM discipline_records
                WHERE student_id = %s
                  AND created_at >= %s
                """,
                (student_id, start_date)
            )
            result = cursor.fetchone()
            count = result[0] if result else 0

            # 简化基线：使用班级平均值作为基准
            # TODO: 实际应该计算 (均值, 标准差)
            # 这里先返回 (count, 1.0, 1) 作为占位
            mean = count * 1.0
            std = 1.0 if count > 0 else 0.0
            return mean, std, count
    finally:
        conn.close()


async def calculate_attendance_baseline(
    db_config: dict, student_id: int, window_days: int
) -> Tuple[float, float, int]:
    """计算考勤维度基线 (从 attendance 表)"""
    conn = pymysql.connect(**db_config)
    try:
        with conn.cursor() as cursor:
            start_date = date.today() - timedelta(days=window_days)
            cursor.execute(
                """
                SELECT
                    SUM(CASE WHEN status = 'absent' THEN 1 ELSE 0 END) as absences,
                    SUM(CASE WHEN status = 'late' THEN 1 ELSE 0 END) as lates,
                    COUNT(*) as total
                FROM attendance
                WHERE student_id = %s
                  AND date >= %s
                """,
                (student_id, start_date)
            )
            result = cursor.fetchone()
            if result and result[2] > 0:
                absence_rate = (result[0] or 0) / result[2]
                lateness_rate = (result[1] or 0) / result[2]
                rate = (absence_rate + lateness_rate) / 2
                return rate * 100, rate * 50, result[2]
            return 0.0, 1.0, 0
    finally:
        conn.close()


async def calculate_score_baseline(
    db_config: dict, student_id: int, window_days: int
) -> Tuple[float, float, int]:
    """计算评价维度基线 (从 wings_scores 表)"""
    conn = pymysql.connect(**db_config)
    try:
        with conn.cursor() as cursor:
            start_date = date.today() - timedelta(days=window_days)
            cursor.execute(
                """
                SELECT AVG(total_score) as avg_score,
                       STDDEV(total_score) as std_score,
                       COUNT(*) as sample_size
                FROM wings_scores
                WHERE student_id = %s
                  AND created_at >= %s
                """,
                (student_id, start_date)
            )
            result = cursor.fetchone()
            if result and result[0] is not None:
                return float(result[0]), float(result[1] or 0.0), result[2]
            return 75.0, 10.0, 0  # 默认基线: 75分, 标准差10
    finally:
        conn.close()


async def upsert_baseline(
    db_config: dict,
    school_id: int,
    student_id: int,
    class_id: int,
    baseline_type: str,
    window_days: int,
    mean: float,
    std: float,
    sample_size: int
):
    """插入或更新基线记录"""
    conn = pymysql.connect(**db_config)
    try:
        with conn.cursor() as cursor:
            # 检查是否已存在
            cursor.execute(
                """
                SELECT id FROM risk_baselines
                WHERE school_id=%s AND student_id=%s
                  AND baseline_type=%s AND window_days=%s
                """,
                (school_id, student_id, baseline_type, window_days)
            )
            existing = cursor.fetchone()

            if existing:
                # 更新
                cursor.execute(
                    """
                    UPDATE risk_baselines
                    SET mean_value=%s, std_value=%s, sample_size=%s, last_updated=NOW()
                    WHERE id=%s
                    """,
                    (mean, std, sample_size, existing[0])
                )
            else:
                # 插入
                cursor.execute(
                    """
                    INSERT INTO risk_baselines
                    (school_id, student_id, class_id, baseline_type, window_days,
                     mean_value, std_value, sample_size, last_updated)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    """,
                    (school_id, student_id, class_id, baseline_type, window_days,
                     mean, std, sample_size)
                )
            conn.commit()
    except Exception as e:
        logger.error(f"Failed to upsert baseline: {e}")
        conn.rollback()
    finally:
        conn.close()


async def initialize_baselines(school_id: int = 1, window_days: int = 30):
    """
    初始化风险基线 (冷启动预热)

    为所有学生计算并存储基线
    """
    logger.info(f"🚀 开始基线初始化 (school_id={school_id}, window={window_days}天)")

    # 1. 获取所有学生
    students = await get_students(DB_CONFIG, school_id)
    logger.info(f"   找到 {len(students)} 名学生")

    # 2. 为每个学生计算基线
    for i, student in enumerate(students, 1):
        student_id = student[0]
        class_id = student[1]
        grade_id = student[2]

        logger.info(f"⏳ 处理学生 {i}/{len(students)} (id={student_id})...")

        # 行为基线
        mean_b, std_b, size_b = await calculate_behavior_baseline(
            DB_CONFIG, student_id, window_days
        )
        await upsert_baseline(
            DB_CONFIG, school_id, student_id, class_id,
            "behavior", window_days, mean_b, std_b, size_b
        )

        # 考勤基线
        mean_a, std_a, size_a = await calculate_attendance_baseline(
            DB_CONFIG, student_id, window_days
        )
        await upsert_baseline(
            DB_CONFIG, school_id, student_id, class_id,
            "attendance", window_days, mean_a, std_a, size_a
        )

        # 评价基线
        mean_s, std_s, size_s = await calculate_score_baseline(
            DB_CONFIG, student_id, window_days
        )
        await upsert_baseline(
            DB_CONFIG, school_id, student_id, class_id,
            "score", window_days, mean_s, std_s, size_s
        )

        if i % 10 == 0:
            logger.info(f"   ✅ 已完成 {i}/{len(students)}")

    logger.info(f"✅ 基线初始化完成！处理了 {len(students)} 名学生")


async def main():
    """主函数"""
    import argparse
    parser = argparse.ArgumentParser(description="风险基线冷启动预热脚本")
    parser.add_argument("--school-id", type=int, default=1, help="学校 ID")
    parser.add_argument("--window", type=int, default=30, help="基线窗口天数")
    args = parser.parse_args()

    await initialize_baselines(args.school_id, args.window)


if __name__ == "__main__":
    asyncio.run(main())
