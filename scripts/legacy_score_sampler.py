"""
旧成绩采样验证脚本 — legacy_score_sampler.py

功能:
  1. 连接旧数据库（MySQL legacy_db / SQLite dump）
  2. 随机抽取 100 条成绩记录
  3. 比对满分制（100/120/150/其他）
  4. 比对科目名称映射（旧名 → 新标准名）
  5. 输出差异报告到 JSON 文件

用法:
  # 使用 MySQL 旧库
  python -m scripts.legacy_score_sampler --source mysql --host 127.0.0.1 --port 3306 \
    --user root --password xxx --database legacy_grades

  # 使用 SQLite dump
  python -m scripts.legacy_score_sampler --source sqlite --file /path/to/legacy.db

  # 输出到指定文件
  python -m scripts.legacy_score_sampler ... --output /path/to/report.json
"""

import argparse
import json
import random
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# ═══════════════════════════════════════════════════════════
# 新系统满分值映射（来自 grades/models.py GradeSubject）
# ═══════════════════════════════════════════════════════════

NEW_FULL_SCORES = {
    "chinese": 120,    # 语文
    "math": 120,       # 数学
    "english": 120,    # 英语
    "physics": 100,    # 物理
    "chemistry": 100,  # 化学
    "biology": 100,    # 生物
    "politics": 100,   # 政治/道法
    "history": 100,    # 历史
    "geography": 100,  # 地理
    "pe": 60,          # 体育
}

# 旧系统科目名 → 新系统标准科目名映射
SUBJECT_NAME_MAP = {
    "语文": "chinese",
    "数学": "math",
    "英语": "english",
    "物理": "physics",
    "化学": "chemistry",
    "生物": "biology",
    "道德与法治": "politics",
    "政治": "politics",
    "道法": "politics",
    "历史": "history",
    "地理": "geography",
    "体育": "pe",
    "信息技术": "it",
    "音乐": "music",
    "美术": "art",
}


def connect_mysql(host: str, port: int, user: str, password: str, database: str):
    """连接 MySQL 旧库"""
    try:
        import pymysql
        conn = pymysql.connect(
            host=host, port=port, user=user, password=password,
            database=database, charset="utf8mb4",
        )
        return conn
    except ImportError:
        print("[ERROR] pymysql 未安装, 请执行: pip install pymysql")
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] MySQL 连接失败: {e}")
        sys.exit(1)


def connect_sqlite(filepath: str):
    """连接 SQLite 旧库"""
    import sqlite3
    try:
        conn = sqlite3.connect(filepath)
        return conn
    except Exception as e:
        print(f"[ERROR] SQLite 连接失败: {e}")
        sys.exit(1)


def discover_grade_tables(cursor) -> list[str]:
    """
    自动发现旧库中可能包含成绩数据的表。
    策略: 查找表名含 grade/score/exam/test 的表。
    """
    cursor.execute("SHOW TABLES")
    tables = [row[0] for row in cursor.fetchall()]
    candidates = [
        t for t in tables
        if any(kw in t.lower() for kw in ("grade", "score", "exam", "test", "成绩", "考试"))
    ]
    return candidates


def sample_records(cursor, table: str, sample_size: int = 100) -> list[dict]:
    """
    从表中随机抽样记录。
    优先使用 MySQL 的 ORDER BY RAND(), SQLite 用 RANDOM().
    """
    try:
        cursor.execute(f"SELECT COUNT(*) FROM `{table}`")
        total = cursor.fetchone()[0]
        if total == 0:
            return []

        actual_size = min(sample_size, total)
        cursor.execute(f"SELECT * FROM `{table}` ORDER BY RAND() LIMIT {actual_size}")
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        return [dict(zip(columns, row)) for row in rows]
    except Exception as e:
        print(f"  [WARN] 表 {table} 抽样失败: {e}")
        return []


def detect_score_columns(columns: list[str]) -> dict[str, str]:
    """
    自动检测成绩相关列:
    - 匹配已知科目名（语文/数学/...）
    - 匹配模糊列名（总分/平均分/...）
    返回 {column_name: subject_code} 映射
    """
    detected = {}
    for col in columns:
        col_normalized = col.strip().replace(" ", "").replace("_", "")
        for old_name, std_code in SUBJECT_NAME_MAP.items():
            if old_name in col_normalized or old_name in col:
                detected[col] = std_code
                break
    return detected


def analyze_score_range(values: list[Optional[float]], subject: str) -> dict:
    """
    分析一门科目的分数范围，推断满分制。
    """
    clean = [v for v in values if v is not None]
    if not clean:
        return {"sample_count": 0, "max_score": None, "inferred_full_score": None}

    max_val = max(clean)
    min_val = min(clean)

    # 推断满分制: 向上取整到最近的 "标准满分"
    candidates = [60, 70, 80, 100, 120, 150]
    inferred = None
    for fs in candidates:
        if max_val <= fs:
            inferred = fs
            break
    if inferred is None:
        inferred = round(max_val / 10) * 10  # 近似取整

    expected = NEW_FULL_SCORES.get(subject)
    mismatch = expected != inferred if expected else False

    return {
        "sample_count": len(clean),
        "min_score": min_val,
        "max_score": max_val,
        "inferred_full_score": inferred,
        "expected_full_score": expected,
        "mismatch": mismatch,
        "mismatch_detail": (
            f"旧库满分≈{inferred}, 新系统满分={expected}" if mismatch else None
        ),
    }


def analyze_subject_mapping(
    sample: list[dict], score_columns: dict[str, str]
) -> list[dict]:
    """
    对每门检测到的科目，抽样分析分数范围和不一致项。
    """
    results = []
    for col, std_code in score_columns.items():
        values = []
        for row in sample:
            try:
                v = float(row.get(col, 0) or 0)
                if v > 0:
                    values.append(v)
            except (ValueError, TypeError):
                continue

        analysis = analyze_score_range(values, std_code)
        results.append({
            "column_name": col,
            "subject_code": std_code,
            "analysis": analysis,
        })
    return results


def detect_inconsistencies(sample: list[dict], score_columns: dict[str, str]) -> list[dict]:
    """
    检测单条记录中的异常:
    - Null 值行
    - 超出满分值的行
    - 科目名不匹配
    """
    issues = []
    for i, row in enumerate(sample):
        row_issues = []
        for col, std_code in score_columns.items():
            val = row.get(col)
            if val is None or val == "" or val == "None":
                row_issues.append({
                    "column": col, "value": val, "issue": "NULL 或空值",
                })
                continue
            try:
                val_f = float(val)
                expected = NEW_FULL_SCORES.get(std_code)
                if expected and val_f > expected * 1.1:
                    row_issues.append({
                        "column": col, "value": val_f,
                        "issue": f"分数 {val_f} 远超满分 {expected}",
                    })
                if val_f < 0:
                    row_issues.append({
                        "column": col, "value": val_f, "issue": "负分异常",
                    })
            except (ValueError, TypeError):
                row_issues.append({
                    "column": col, "value": val,
                    "issue": "无法解析为数字",
                })

        if row_issues:
            issues.append({
                "row_index": i,
                "row_id": row.get("id"),  # type: ignore
                "issues": row_issues,
            })

    return issues


def generate_report(
    table: str, sample: list[dict], score_columns: dict[str, str],
    subject_analysis: list[dict], inconsistencies: list[dict],
) -> dict:
    """生成 JSON 格式差异报告"""
    return {
        "report_meta": {
            "generated_at": datetime.now().isoformat(),
            "script_version": "1.0.0",
            "table": table,
            "total_rows_sampled": len(sample),
            "total_score_columns_detected": len(score_columns),
        },
        "schema_discovery": {
            "all_columns": list(sample[0].keys()) if sample else [],
            "detected_score_columns": score_columns,
            "undetected_columns": [
                c for c in (sample[0].keys() if sample else [])
                if c not in score_columns
            ],
        },
        "full_score_analysis": {
            "new_system_full_scores": NEW_FULL_SCORES,
            "per_subject": subject_analysis,
            "mismatch_count": sum(
                1 for a in subject_analysis if a["analysis"]["mismatch"]
            ),
            "mismatch_subjects": [
                a["subject_code"] for a in subject_analysis
                if a["analysis"]["mismatch"]
            ],
        },
        "data_quality": {
            "total_issues": len(inconsistencies),
            "issue_rows": inconsistencies,
        },
        "recommendations": _generate_recommendations(
            subject_analysis, inconsistencies, sample
        ),
    }


def _generate_recommendations(
    subject_analysis: list[dict],
    inconsistencies: list[dict],
    sample: list[dict],
) -> list[str]:
    """基于分析结果生成迁移建议"""
    recs = []

    for a in subject_analysis:
        if a["analysis"]["mismatch"]:
            recs.append(
                f"[满分制不匹配] {a['subject_code']}({a['column_name']}): "
                f"旧库≈{a['analysis']['inferred_full_score']}分, "
                f"新系统={a['analysis']['expected_full_score']}分, "
                f"建议: 导入时乘以缩放因子 "
                f"{a['analysis']['expected_full_score']}/{a['analysis']['inferred_full_score']}"
            )

    if inconsistencies:
        null_count = sum(
            1 for inc in inconsistencies
            for iss in inc["issues"] if "NULL" in str(iss["issue"])
        )
        outlier_count = sum(
            1 for inc in inconsistencies
            for iss in inc["issues"]
            if "远超满分" in str(iss["issue"]) or "负分" in str(iss["issue"])
        )
        if null_count > 0:
            recs.append(
                f"[数据完整性] 发现 {null_count} 行含空值成绩, "
                f"建议: 导入前与教务确认是否为缺考 + 或补录"
            )
        if outlier_count > 0:
            recs.append(
                f"[异常分数] 发现 {outlier_count} 个异常分数值, "
                f"建议: 人工复核原始 Excel 后再导入"
            )

    dirty_ratio = len(inconsistencies) / len(sample) if sample else 0
    if dirty_ratio > 0.3:
        recs.append(
            f"[脏数据告警] 脏数据占比 {dirty_ratio:.0%}, "
            f"强烈建议采用「影子存储 + 按需激活」策略, "
            f"不要全量直灌核心库"
        )
    elif dirty_ratio > 0.1:
        recs.append(
            f"[建议清洗] 脏数据占比 {dirty_ratio:.0%}, "
            f"建议先经 data_adapter 清洗管道处理后再导入"
        )
    else:
        recs.append(
            f"[数据质量良好] 脏数据占比 {dirty_ratio:.0%}, "
            f"可考虑批量直导入"
        )

    return recs


def main():
    parser = argparse.ArgumentParser(description="旧成绩采样验证脚本")
    parser.add_argument("--source", choices=["mysql", "sqlite"], default="mysql")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3306)
    parser.add_argument("--user", default="root")
    parser.add_argument("--password", default="")
    parser.add_argument("--database", default="legacy_grades")
    parser.add_argument("--file", help="SQLite 文件路径")
    parser.add_argument("--table", help="指定表名 (不指定则自动发现)")
    parser.add_argument("--sample-size", type=int, default=100)
    parser.add_argument("--output", default="legacy_score_report.json")

    args = parser.parse_args()

    print("=" * 60)
    print("  旧成绩采样验证脚本")
    print("=" * 60)

    # 1. 连接旧库
    if args.source == "mysql":
        conn = connect_mysql(args.host, args.port, args.user, args.password, args.database)
    else:
        if not args.file:
            print("[ERROR] SQLite 模式需要 --file 参数")
            sys.exit(1)
        conn = connect_sqlite(args.file)

    cursor = conn.cursor()
    print(f"[OK] 旧库连接成功 ({args.source})")

    # 2. 发现表
    if args.table:
        tables = [args.table]
    else:
        tables = discover_grade_tables(cursor)
    print(f"[OK] 发现 {len(tables)} 个候选表: {tables}")

    # 3. 逐表采样分析
    all_reports = {}
    for table in tables:
        print(f"\n--- 分析表: {table} ---")
        sample = sample_records(cursor, table, args.sample_size)
        if not sample:
            print(f"  [SKIP] 表 {table} 无数据")
            continue

        print(f"  [OK] 抽样 {len(sample)} 条")
        columns = list(sample[0].keys())
        print(f"  [OK] 列: {columns}")

        score_columns = detect_score_columns(columns)
        print(f"  [OK] 检测到 {len(score_columns)} 个成绩列: {score_columns}")

        subject_analysis = analyze_subject_mapping(sample, score_columns)
        inconsistencies = detect_inconsistencies(sample, score_columns)
        print(f"  [OK] 发现 {len(inconsistencies)} 条异常记录")

        report = generate_report(table, sample, score_columns, subject_analysis, inconsistencies)
        all_reports[table] = report

    # 4. 输出报告
    output_path = Path(args.output)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_reports, f, ensure_ascii=False, indent=2)

    print(f"\n{'=' * 60}")
    print(f"  报告已保存: {output_path.absolute()}")
    print(f"  建议在导入前审阅报告中的 recommendations 部分")
    print(f"{'=' * 60}")

    # 5. 汇总建议
    total_mismatches = sum(
        r["full_score_analysis"]["mismatch_count"]
        for r in all_reports.values()
    )
    total_issues = sum(
        r["data_quality"]["total_issues"]
        for r in all_reports.values()
    )

    if total_mismatches > 0:
        print(f"\n⚠️  警告: {total_mismatches} 门科目存在满分制不匹配!")
    if total_issues > 0:
        print(f"\n⚠️  警告: 共发现 {total_issues} 条异常记录!")

    cursor.close()
    conn.close()


if __name__ == "__main__":
    main()
