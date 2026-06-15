#!/usr/bin/env python3
"""
导出第4次考试成绩为CSV，用于服务器导入
数据源: 桌面【七年级期中】全部考生成绩汇总.xls
输出: exam4_scores.csv (含学号、姓名、班级、7科成绩)
"""

import pandas as pd
import sys

EXCEL_PATH = r"C:\Users\Administrator\Desktop\【七年级期中】全部考生成绩汇总.xls"
OUTPUT_CSV = r"C:\Users\Administrator\Desktop\exam4_scores.csv"

# 班级名 → class_id
CLASS_MAP = {
    "2501班": 1, "2502班": 2, "2503班": 3, "2504班": 4,
    "2505班": 5, "2506班": 6, "2507班": 7, "2508班": 8,
}

# Excel列名 → Subject.id
SUBJECT_MAP = {
    "语文": 1, "数学": 2, "英语": 3,
    "生物": 7, "政治": 4, "历史": 5, "地理": 6,
}

def parse_score(val):
    if val is None:
        return ""
    s = str(val).strip()
    if s in ("", "缺考", "未扫", "缺", "—", "-", "NaN", "nan"):
        return ""
    try:
        return str(float(s))
    except ValueError:
        return ""

def main():
    print("读取Excel...")
    df = pd.read_excel(EXCEL_PATH)
    print(f"  共 {len(df)} 行")

    # 构建输出数据
    rows = []
    for idx, row in df.iterrows():
        class_name = str(row["班级"]).strip()
        student_name = str(row["姓名"]).strip()
        class_id = CLASS_MAP.get(class_name)

        if not class_id:
            print(f"  ⚠ 跳过未知班级: {class_name} ({student_name})")
            continue

        out = {
            "class_id": class_id,
            "class_name": class_name,
            "student_name": student_name,
        }
        for col, sub_id in SUBJECT_MAP.items():
            out[f"subject_{sub_id}"] = parse_score(row[col])

        rows.append(out)

    # 输出CSV
    out_df = pd.DataFrame(rows)
    out_df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
    print(f"\n✅ 已导出 {len(rows)} 条记录到:")
    print(f"   {OUTPUT_CSV}")
    print(f"\n列说明:")
    print(f"  class_id, class_name, student_name, subject_1(语文), subject_2(数学), ..., subject_7(生物)")
    print(f"\n下一步: 将CSV传到服务器，运行服务器上的导入脚本")

if __name__ == "__main__":
    main()
