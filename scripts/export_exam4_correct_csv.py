"""从正确的考试文件导出CSV"""
import csv
import pandas as pd

EXCEL_PATH = r"C:\Users\Administrator\Desktop\【初一期中】全部考生成绩汇总(4).xls"
CSV_PATH = r"C:\Users\Administrator\Desktop\exam4_correct.csv"

CLASS_MAP = {
    "2501": 1, "2502": 2, "2503": 3, "2504": 4,
    "2505": 5, "2506": 6, "2507": 7, "2508": 8,
}
SUBJECT_IDS = {
    "语文": 1, "数学": 2, "英语": 3,
    "政治": 4, "历史": 5, "地理": 6, "生物": 7,
}

df = pd.read_excel(EXCEL_PATH)
print(f"读取 {len(df)} 行")

# 构建CSV列
rows = []
skipped = 0
for _, row in df.iterrows():
    class_name = str(row["班级"]).strip()
    class_id = CLASS_MAP.get(class_name)
    if class_id is None:
        print(f"  未知班级: {class_name}")
        skipped += 1
        continue

    record = {
        "class_id": class_id,
        "class_name": class_name,
        "student_name": str(row["姓名"]).strip(),
    }
    for sub_name, sub_id in SUBJECT_IDS.items():
        val = row.get(sub_name)
        if pd.isna(val) or str(val).strip() in ("", "缺考", "未扫", "-"):
            record[f"subject_{sub_id}"] = ""
        else:
            record[f"subject_{sub_id}"] = float(val)
    rows.append(record)

# 写入CSV
fieldnames = ["class_id", "class_name", "student_name"] + [
    f"subject_{i}" for i in range(1, 8)
]
with open(CSV_PATH, "w", newline="", encoding="utf-8-sig") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

print(f"导出 {len(rows)} 条学生记录到 {CSV_PATH}")
print(f"跳过 {skipped} 条")

# 验证平均分
print("\n=== CSV平均分验证 ===")
df_check = pd.read_csv(CSV_PATH)
for sub_name, sub_id in SUBJECT_IDS.items():
    col = f"subject_{sub_id}"
    vals = pd.to_numeric(df_check[col], errors="coerce")
    non_null = vals.notna().sum()
    avg = vals.mean()
    print(f"  {sub_name}: {non_null}人, 平均分={avg:.2f}")
