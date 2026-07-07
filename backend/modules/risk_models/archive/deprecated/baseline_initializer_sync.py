#!/usr/bin/env python3
"""
risk_baseline_initializer.py — 风险基线冷启动预热脚本 (同步版)

功能:
  1. 扫描所有学生
  2. 计算过去 30 天的行为/考勤/评价基线 (均值/标准差)
  3. 填充 risk_baselines 表
  4. 支持增量更新

使用方法:
  python3 risk_baseline_initializer.py --school-id 1 --window 30
"""

import pymysql
import logging
from datetime import datetime, date, timedelta
from typing import List, Tuple
import sys
import getopt

# 数据库配置
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


def get_students(school_id: int) -> List[dict]:
    """获取学校所有学生"""
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, class_id, grade_id FROM students WHERE school_id=%s",
                (school_id,)
            )
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        conn.close()


def calculate_behavior_baseline(student_id: int, window_days: int) -> Tuple[float, float, int]:
    """
    计算行为维度基线 (从 discipline_records 表)

    返回: (mean, std, sample_size)
    """
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cursor:
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


def calculate_attendance_baseline(student_id: int, window_days: int) -> Tuple[float, float, int]:
    """计算考勤维度基线 (从 attendance 表)"""
    conn = pymysql.connect(**DB_CONFIG)
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


def calculate_score_baseline(student_id: int, window_days: int) -> Tuple[float, float, int]:
    """计算评价维度基线 (从 wings_scores 表)"""
    conn = pymysql.connect(**DB_CONFIG)
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


def upsert_baseline(
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
    conn = pymysql.connect(**DB_CONFIG)
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
        raise
    finally:
        conn.close()


def initialize_baselines(school_id: int = 1, window_days: int = 30):
    """
    初始化风险基线 (冷启动预热)

    为所有学生计算并存储基线
    """
    logger.info(f"🚀 开始基线初始化 (school_id={school_id}, window={window_days}天)")

    # 1. 获取所有学生
    students = get_students(school_id)
    logger.info(f"   找到 {len(students)} 名学生")

    if not students:
        logger.warning("   ⚠️  未找到学生，请检查 school_id")
        return

    # 2. 为每个学生计算基线
    success_count = 0
    error_count = 0

    for i, student in enumerate(students, 1):
        student_id = student["id"]
        class_id = student["class_id"]
        grade_id = student["grade_id"]

        logger.info(f"⏳ 处理学生 {i}/{len(students)} (id={student_id})...")

        try:
            # 行为基线
            mean_b, std_b, size_b = calculate_behavior_baseline(student_id, window_days)
            upsert_baseline(
                school_id, student_id, class_id,
                "behavior", window_days, mean_b, std_b, size_b
            )

            # 考勤基线
            mean_a, std_a, size_a = calculate_attendance_baseline(student_id, window_days)
            upsert_baseline(
                school_id, student_id, class_id,
                "attendance", window_days, mean_a, std_a, size_a
            )

            # 评价基线
            mean_s, std_s, size_s = calculate_score_baseline(student_id, window_days)
            upsert_baseline(
                school_id, student_id, class_id,
                "score", window_days, mean_s, std_s, size_s
            )

            success_count += 1

            if i % 10 == 0:
                logger.info(f"   ✅ 已完成 {i}/{len(students)}")

        except Exception as e:
            logger.error(f"   ❌ 处理学生 {student_id} 失败: {e}")
            error_count += 1

    logger.info(f"✅ 基线初始化完成！")
    logger.info(f"   成功: {success_count}/{len(students)}")
    if error_count > 0:
        logger.warning(f"   失败: {error_count}/{len(students)}")


def main():
    """主函数"""
    school_id = 1
    window_days = 30

    # 解析命令行参数
    try:
        opts, args = getopt.getopt(sys.argv[1:], "s:w:h", ["school-id=", "window=", "help"])
        for opt, arg in opts:
            if opt in ("-s", "--school-id"):
                school_id = int(arg)
            elif opt in ("-w", "--window"):
                window_days = int(arg)
            elif opt in ("-h", "--help"):
                print("使用方法: python3 risk_baseline_initializer.py --school-id 1 --window 30")
                sys.exit(0)
    except getopt.GetoptError as e:
        print(f"参数错误: {e}")
        sys.exit(1)

    initialize_baselines(school_id, window_days)


if __name__ == "__main__":
    main()
