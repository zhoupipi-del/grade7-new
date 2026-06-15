"""数据库查询性能对比测试
验证索引优化前后查询效率差异，为论文提供量化数据支撑。

使用方法：
  cd /opt/grade7-new && source venv/bin/activate && python scripts/benchmark_query.py

输出：
  - 控制台：详细对比表格
  - scripts/benchmark_result.json：结构化结果
  - scripts/benchmark_result.md：Markdown 报告
"""

import time
import statistics
import json
import os
from datetime import datetime
from app import app, db
from sqlalchemy import text

ITERATIONS = 50  # 每个查询重复次数
OUTPUT_DIR = os.path.join(os.path.dirname(__file__))

# 测试数据量范围
SAMPLE_SIZES = [100, 1000, 5000, 6572]  # 100条~全部6572条

BENCHMARK_QUERIES = [
    {
        "name": "按学生ID查询成绩（单表主键）",
        "sql_with_index": """
            SELECT student_id, exam_id, SUM(score) as total
            FROM scores
            WHERE student_id = :sid
            GROUP BY student_id, exam_id
        """,
        "params": {"sid": 50},
        "desc": "scores 表 (6,572行)，student_id 已建索引",
    },
    {
        "name": "按考试ID查询成绩+学生关联（双表JOIN）",
        "sql_with_index": """
            SELECT s.name, sc.subject_id, sc.score
            FROM scores sc
            JOIN students s ON s.id = sc.student_id
            WHERE sc.exam_id = :eid
            LIMIT 1000
        """,
        "params": {"eid": 1},
        "desc": "scores(6,572) JOIN students(389)，exam_id/student_id 已建索引",
    },
    {
        "name": "缺勤学生筛选（条件+日期范围）",
        "sql_with_index": """
            SELECT student_id, COUNT(*) as cnt
            FROM attendance
            WHERE status = 'absent' AND record_date >= :start_date
            GROUP BY student_id
            HAVING cnt >= 3
        """,
        "params": {"start_date": "2026-01-01"},
        "desc": "attendance 全表扫描（status/record_date 复合索引）",
    },
    {
        "name": "违纪分类统计（分组聚合）",
        "sql_with_index": """
            SELECT type, COUNT(*) as cnt
            FROM discipline_records
            GROUP BY type
        """,
        "params": {},
        "desc": "discipline_records 全表聚合，type 列已建索引",
    },
]


def run_query(sql, params, use_index=True):
    """执行一次查询并返回耗时(ms)"""
    t0 = time.perf_counter()
    db.session.execute(text(sql), params)
    t1 = time.perf_counter()
    return (t1 - t0) * 1000


def run_benchmark():
    with app.app_context():
        results = []
        summary = {
            "test_time": datetime.now().isoformat(),
            "tables": {
                "scores": db.session.execute(text("SELECT COUNT(*) FROM scores")).scalar(),
                "students": db.session.execute(text("SELECT COUNT(*) FROM students")).scalar(),
                "attendance": db.session.execute(text("SELECT COUNT(*) FROM attendance")).scalar(),
                "discipline_records": db.session.execute(text("SELECT COUNT(*) FROM discipline_records")).scalar(),
            },
            "iterations": ITERATIONS,
            "queries": [],
        }

        print("=" * 70)
        print("  梨江中学 Wings系统 — 数据库查询性能对比测试")
        print(f"  测试时间: {summary['test_time']}")
        print(f"  数据规模: {summary['tables']}")
        print(f"  每查询重复: {ITERATIONS}次")
        print("=" * 70)

        for bq in BENCHMARK_QUERIES:
            print(f"\n{'─'*50}")
            print(f"  测试: {bq['name']}")
            print(f"  说明: {bq['desc']}")

            # 有索引 → SQLAlchemy 正常查询（利用索引）
            sql = bq['sql_with_index']
            params = bq['params']

            times_with = []
            times_without = []

            # 预热 5 次（消除冷缓存影响）
            for _ in range(5):
                run_query(sql, params, use_index=True)
                run_query(sql, params, use_index=False)

            # 正式测试
            for _ in range(ITERATIONS):
                # 有索引
                t = run_query(sql, params, use_index=True)
                times_with.append(t)

                # 无索引 — 通过 SQL 注释 + 随机赋值破坏索引选择性
                # 实际无索引环境：将查询中的条件列用 LOWER() 包裹破坏索引
                sql_no_idx = sql
                # 破坏索引技巧：在 WHERE 条件上包裹函数
                if 'student_id =' in sql:
                    sql_no_idx = sql.replace('student_id =', 'student_id + 0 =')
                elif 'exam_id =' in sql:
                    sql_no_idx = sql.replace('exam_id =', 'exam_id + 0 =')
                elif 'status =' in sql:
                    sql_no_idx = sql.replace("status = 'absent'", "CONCAT(status,'') = 'absent'")

                t = run_query(sql_no_idx, params, use_index=False)
                times_without.append(t)

            avg_with = statistics.mean(times_with)
            avg_without = statistics.mean(times_without)
            p50_with = statistics.median(times_with)
            p50_without = statistics.median(times_without)
            p95_with = sorted(times_with)[int(ITERATIONS * 0.95)]
            p95_without = sorted(times_without)[int(ITERATIONS * 0.95)]
            ratio = avg_without / max(avg_with, 0.001)

            print(f"    有索引  avg={avg_with:.2f}ms  p50={p50_with:.2f}ms  p95={p95_with:.2f}ms")
            print(f"    无索引  avg={avg_without:.2f}ms  p50={p50_without:.2f}ms  p95={p95_without:.2f}ms")
            print(f"    >>> 提升 {ratio:.1f}x")

            qr = {
                "name": bq["name"],
                "desc": bq["desc"],
                "avg_indexed_ms": round(avg_with, 2),
                "avg_nonindexed_ms": round(avg_without, 2),
                "p50_indexed_ms": round(p50_with, 2),
                "p50_nonindexed_ms": round(p50_without, 2),
                "p95_indexed_ms": round(p95_with, 2),
                "p95_nonindexed_ms": round(p95_without, 2),
                "speedup": round(ratio, 1),
            }
            summary["queries"].append(qr)

        # 综合指标
        ratios = [q["speedup"] for q in summary["queries"]]
        if ratios:
            summary["avg_speedup"] = round(statistics.mean(ratios), 1)
            summary["max_speedup"] = round(max(ratios), 1)
            summary["min_speedup"] = round(min(ratios), 1)

        # 保存 JSON
        json_path = os.path.join(OUTPUT_DIR, "benchmark_result.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)

        # 保存 Markdown 报告
        md_path = os.path.join(OUTPUT_DIR, "benchmark_result.md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(f"# Wings系统 数据库查询性能对比测试\n\n")
            f.write(f"**测试时间**：{summary['test_time']}\n\n")
            f.write(f"**数据规模**：\n")
            for tbl, cnt in summary["tables"].items():
                f.write(f"- {tbl}: {cnt} 条\n")
            f.write(f"\n**测试方法**：每查询重复 {ITERATIONS} 次取平均值，消除冷缓存影响。\n")
            f.write(f"**索引破坏方法**：在 WHERE 条件列上包裹函数（+0 / CONCAT）使索引失效，模拟无索引场景。\n\n")
            f.write(f"## 测试结果\n\n")
            f.write(f"| 查询场景 | 有索引(ms) | 无索引(ms) | 提升倍数 |\n")
            f.write(f"|---------|-----------|-----------|--------|\n")
            for q in summary["queries"]:
                f.write(f"| {q['name']} | {q['avg_indexed_ms']} | {q['avg_nonindexed_ms']} | **{q['speedup']}x** |\n")
            f.write(f"\n## 综合指标\n\n")
            f.write(f"- 平均提升倍数：**{summary['avg_speedup']}x**\n")
            f.write(f"- 最大提升倍数：**{summary['max_speedup']}x**\n")
            f.write(f"- 最小提升倍数：**{summary['min_speedup']}x**\n")

        # 打印总结
        print(f"\n{'='*70}")
        print(f"  📊 综合结论")
        print(f"  平均提升: {summary['avg_speedup']}x")
        print(f"  最大提升: {summary['max_speedup']}x")
        print(f"  最小提升: {summary['min_speedup']}x")
        print(f"  结果已保存: {json_path}")
        print(f"  报告已保存: {md_path}")
        print(f"{'='*70}")

        return summary


if __name__ == "__main__":
    run_benchmark()
