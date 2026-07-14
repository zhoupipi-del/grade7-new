#!/usr/bin/env python3
"""
迁移脚本 — 插入正向加分指标到 evaluation_indicators 表

用法:
  cd /root/backend && .venv/bin/python scripts/insert_positive_indicators.py

功能:
  - 读取 services.py 中的 SEED_INDICATORS 列表
  - 筛选出正向加分指标（sort_order >= 23）
  - 幂等插入（检查 name + dimension + school_id 是否已存在）
  - 支持多学校（默认 school_id=1，可通过环境变量覆盖）

作者: WorkBuddy AI
日期: 2026-07-05
"""

import logging
import os
import sys

from sqlalchemy import create_engine, text

# 确保能引入项目根目录模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("migrate_indicators")

# ── 配置 ──────────────────────────────────────────────
from core.db_utils import get_db_url_for_script

DATABASE_URL = get_db_url_for_script("运行前请先 export DATABASE_URL=...")

# 正向加分指标定义（从 services.py 中提取，sort_order >= 23）
POSITIVE_INDICATORS = [
    # (name, dimension, parent_id, weight, max_score, sort_order)
    ("品德之星", "moral", 1, 0.25, 100.0, 23),
    ("助人为乐", "moral", 1, 0.25, 100.0, 24),
    ("拾金不昧", "moral", 1, 0.20, 100.0, 25),
    ("诚信守诺", "moral", 1, 0.30, 100.0, 26),
    ("体育竞赛", "health", 1, 0.30, 100.0, 27),
    ("文体活动", "art", 1, 0.25, 100.0, 28),
    ("文艺演出", "art", 1, 0.25, 100.0, 29),
    ("艺术考级", "art", 1, 0.20, 100.0, 30),
    ("校园志愿", "social", 1, 0.25, 100.0, 31),
    ("社区服务", "social", 1, 0.30, 100.0, 32),
    ("公益捐赠", "social", 1, 0.20, 100.0, 33),
    ("劳动实践", "social", 1, 0.25, 100.0, 34),
    ("劳动技能", "social", 1, 0.20, 100.0, 35),
]


def insert_positive_indicators(school_id: int = 1):
    """
    插入正向加分指标到指定学校

    参数:
        school_id: 学校ID（默认 1 = 梨江中学）
    """
    engine = create_engine(DATABASE_URL, echo=False)

    with engine.connect() as conn:
        inserted = 0
        skipped = 0

        for name, dimension, parent_id, weight, max_score, sort_order in POSITIVE_INDICATORS:
            # 幂等检查: 根据 name + dimension + school_id 判断是否已存在
            check_sql = text("""
                SELECT id FROM evaluation_indicators
                WHERE school_id = :school_id AND name = :name AND dimension = :dimension
            """)
            result = conn.execute(
                check_sql,
                {
                    "school_id": school_id,
                    "name": name,
                    "dimension": dimension,
                },
            ).fetchone()

            if result:
                logger.info(f"跳过已存在指标: {name} ({dimension}) [id={result[0]}]")
                skipped += 1
                continue

            # 插入新指标
            insert_sql = text("""
                INSERT INTO evaluation_indicators
                (school_id, name, parent_id, dimension, weight, max_score, sort_order, is_active, created_at)
                VALUES
                (:school_id, :name, :parent_id, :dimension, :weight, :max_score, :sort_order, 1, NOW())
            """)
            conn.execute(
                insert_sql,
                {
                    "school_id": school_id,
                    "name": name,
                    "parent_id": parent_id,
                    "dimension": dimension,
                    "weight": weight,
                    "max_score": max_score,
                    "sort_order": sort_order,
                },
            )
            logger.info(f"已插入指标: {name} ({dimension}) [sort_order={sort_order}]")
            inserted += 1

        # 提交事务
        conn.commit()

        logger.info(f"✅ 完成 — 插入 {inserted} 条，跳过 {skipped} 条（已存在）")
        return True


def list_indicators(school_id: int = 1):
    """列出指定学校的所有评价指标（用于验证）"""
    engine = create_engine(DATABASE_URL, echo=False)

    with engine.connect() as conn:
        sql = text("""
            SELECT id, name, dimension, weight, sort_order, is_active
            FROM evaluation_indicators
            WHERE school_id = :school_id
            ORDER BY sort_order
        """)
        results = conn.execute(sql, {"school_id": school_id}).fetchall()

        print(f"\n学校 {school_id} 的评价指标列表:")
        print("-" * 80)
        for row in results:
            id, name, dimension, weight, sort_order, is_active = row
            status = "✅" if is_active else "❌"
            print(
                f"  [{sort_order:2d}] {status} {id:3d} | {dimension:10s} | {name:12s} | weight={weight:.2f}"
            )
        print("-" * 80)
        print(f"总计: {len(results)} 条\n")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="插入正向加分指标到 evaluation_indicators 表")
    parser.add_argument("--school-id", type=int, default=1, help="学校ID（默认 1 = 梨江中学）")
    parser.add_argument("--list", action="store_true", help="仅列出已有指标，不插入")
    args = parser.parse_args()

    if args.list:
        list_indicators(args.school_id)
    else:
        success = insert_positive_indicators(args.school_id)
        if success:
            list_indicators(args.school_id)  # 插入后列出验证
