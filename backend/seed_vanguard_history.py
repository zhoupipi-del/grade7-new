"""
seed_vanguard_history.py — 30天先遣队历史数据预热

生成两类数据并灌入 wings3 生产库：
1. discipline_records: 30天违纪流水（前20天混乱期 + 后10天收敛期）
2. student_scores: 393名学生德育量化总分（与违纪记录关联扣分）

执行方式: 本地 python3 跑，通过 SSH 管道直接灌入服务器 MySQL
"""

import random
import subprocess
from datetime import date, timedelta

from core.db_utils import get_db_password

random.seed(42)  # 可复现
DB_PASSWORD = get_db_password()
DB_CMD = f"docker exec -i grade7-new-db mysql -ugrade7 -p'{DB_PASSWORD}' wings3"

# ═══════════════════════════════════════════════════════════════
# Step 1: 查学生列表
# ═══════════════════════════════════════════════════════════════

print(">>> Step 1: 查询 wings3 学生列表...")
result = subprocess.run(
    [
        "ssh",
        "root@8.137.180.152",
        f"docker exec grade7-new-db mysql -ugrade7 -p'{DB_PASSWORD}' wings3 -N -e "
        '"SELECT id, class_id, grade_id FROM students WHERE school_id=1 AND is_active=1;"',
    ],
    capture_output=True,
    text=True,
    timeout=15,
)

students = []
for line in result.stdout.strip().split("\n"):
    if line.strip():
        parts = line.split("\t")
        students.append(
            {
                "id": int(parts[0]),
                "class_id": int(parts[1]),
                "grade_id": int(parts[2]),
            }
        )

print(f"    获取 {len(students)} 名学生")

# 按班级分组
class_groups = {}
for s in students:
    class_groups.setdefault(s["class_id"], []).append(s)

print(f"    分布在 {len(class_groups)} 个班级")

# ═══════════════════════════════════════════════════════════════
# Step 2: 生成30天违纪流水
# ═══════════════════════════════════════════════════════════════

print(">>> Step 2: 生成30天违纪流水...")

TODAY = date(2026, 6, 25)
START = TODAY - timedelta(days=30)

CATEGORIES = ["打架", "吸烟", "迟到", "仪容", "课堂", "其他"]
DESCRIPTIONS = {
    "打架": "课间与同学发生肢体冲突",
    "吸烟": "卫生间吸烟被发现",
    "迟到": "早晨迟到超过15分钟",
    "仪容": "仪容仪表不合规",
    "课堂": "课堂纪律扰乱",
    "其他": "其他违纪行为",
}
POINTS_MAP = {"warning": 1, "minor": 3, "major": 5, "serious": 10}

# 记录每个学生的扣分（用于后续德育分计算）
student_deductions = {s["id"]: 0 for s in students}

violation_records = []  # (student_id, class_id, grade_id, type, category, description, points, date_str, datetime_str)

for day_offset in range(30):
    d = START + timedelta(days=day_offset)
    date_str = d.strftime("%Y-%m-%d")

    if day_offset < 20:
        # ── 混乱期：每天 5-10 条 minor/major ──
        num = random.randint(5, 10)
        for _ in range(num):
            stu = random.choice(students)
            vtype = random.choices(["minor", "major", "warning"], weights=[5, 3, 2])[0]
            cat = random.choice(CATEGORIES)
            pts = POINTS_MAP[vtype]
            desc = DESCRIPTIONS[cat]
            violation_records.append(
                (
                    stu["id"],
                    stu["class_id"],
                    stu["grade_id"],
                    vtype,
                    cat,
                    desc,
                    pts,
                    date_str,
                    f"{date_str} 10:{random.randint(0, 59):02d}:00",
                )
            )
            student_deductions[stu["id"]] += pts

        # 每3天1次 serious（滑窗红线）
        if day_offset % 3 == 0:
            stu = random.choice(students)
            violation_records.append(
                (
                    stu["id"],
                    stu["class_id"],
                    stu["grade_id"],
                    "serious",
                    "打架",
                    "严重打架事件触发滑窗红线",
                    10,
                    date_str,
                    f"{date_str} 14:30:00",
                )
            )
            student_deductions[stu["id"]] += 10
    else:
        # ── 收敛期：每天 0-2 条 warning/minor ──
        num = random.randint(0, 2)
        for _ in range(num):
            stu = random.choice(students)
            vtype = random.choice(["warning", "minor"])
            cat = random.choice(["迟到", "仪容", "课堂"])
            pts = POINTS_MAP[vtype]
            desc = DESCRIPTIONS[cat]
            violation_records.append(
                (
                    stu["id"],
                    stu["class_id"],
                    stu["grade_id"],
                    vtype,
                    cat,
                    desc,
                    pts,
                    date_str,
                    f"{date_str} 10:{random.randint(0, 59):02d}:00",
                )
            )
            student_deductions[stu["id"]] += pts

print(f"    生成 {len(violation_records)} 条违纪记录")
print(f"    混乱期(前20天): {sum(1 for r in violation_records if int(r[7][8:10]) < 16)} 条")
print(f"    收敛期(后10天): {sum(1 for r in violation_records if int(r[7][8:10]) >= 16)} 条")

# ═══════════════════════════════════════════════════════════════
# Step 3: 生成德育分数（StudentScore）
# ═══════════════════════════════════════════════════════════════

print(">>> Step 3: 生成393名学生德育量化总分...")

SEMESTER = "2025-2026-2"
score_records = []

for s in students:
    deduction = student_deductions[s["id"]]
    # 德育总分 = 100 - 扣分（下限30）
    total = max(30.0, 100.0 - deduction + random.uniform(-5, 5))

    # 五维分（有随机扰动，但与总分关联）
    moral = round(total * 0.35 + random.uniform(-3, 3), 1)
    academic = round(75 + random.uniform(-10, 10), 1)
    health = round(80 + random.uniform(-8, 8), 1)
    art = round(75 + random.uniform(-10, 10), 1)
    social = round(80 + random.uniform(-8, 8), 1)

    score_records.append(
        {
            "student_id": s["id"],
            "class_id": s["class_id"],
            "grade_id": s["grade_id"],
            "semester": SEMESTER,
            "moral_score": moral,
            "academic_score": academic,
            "health_score": health,
            "art_score": art,
            "social_score": social,
            "total_score": round(total, 1),
            "base_score": 100.0,
        }
    )

print(f"    生成 {len(score_records)} 条德育分数记录")

# ═══════════════════════════════════════════════════════════════
# Step 4: 构建 SQL 并通过 SSH 管道执行
# ═══════════════════════════════════════════════════════════════

print(">>> Step 4: 构建批量 SQL...")

sql_parts = []
sql_parts.append("SET NAMES utf8mb4;")
sql_parts.append("SET FOREIGN_KEY_CHECKS=0;")

# ── 清空旧测试数据 ──
sql_parts.append(
    "DELETE FROM discipline_records WHERE school_id=1 AND created_by=1 AND verify_status='VERIFIED' AND description LIKE '%烟幕%' OR (school_id=1 AND incident_date >= '2026-05-26');"
)
sql_parts.append("DELETE FROM student_scores WHERE school_id=1 AND semester='2025-2026-2';")

# ── 批量插入违纪记录 ──
sql_parts.append(
    "INSERT INTO discipline_records (student_id, class_id, grade_id, type, category, description, points, status, verify_status, created_by, school_id, incident_date, created_at) VALUES"
)
values_parts = []
for r in violation_records:
    sid, cid, gid, vtype, cat, desc, pts, dstr, dtstr = r
    # 转义单引号
    desc_esc = desc.replace("'", "\\'")
    cat_esc = cat.replace("'", "\\'")
    values_parts.append(
        f"({sid},{cid},{gid},'{vtype}','{cat_esc}','{desc_esc}',{pts},'active','VERIFIED',1,1,'{dstr}','{dtstr}')"
    )
sql_parts.append(",\n".join(values_parts) + ";")

# ── 批量插入德育分数 ──
sql_parts.append(
    "INSERT INTO student_scores (student_id, class_id, grade_id, semester, moral_score, academic_score, health_score, art_score, social_score, total_score, base_score, school_id) VALUES"
)
score_values = []
for sr in score_records:
    score_values.append(
        f"({sr['student_id']},{sr['class_id']},{sr['grade_id']},'{sr['semester']}',"
        f"{sr['moral_score']},{sr['academic_score']},{sr['health_score']},{sr['art_score']},"
        f"{sr['social_score']},{sr['total_score']},{sr['base_score']},1)"
    )
sql_parts.append(",\n".join(score_values) + ";")

sql_parts.append("SET FOREIGN_KEY_CHECKS=1;")

full_sql = "\n".join(sql_parts)
print(f"    SQL 总长度: {len(full_sql)} 字符")

# ═══════════════════════════════════════════════════════════════
# Step 5: 通过 SSH 管道执行
# ═══════════════════════════════════════════════════════════════

print(">>> Step 5: 通过 SSH 管道灌入生产库...")
process = subprocess.Popen(
    ["ssh", "root@8.137.180.152", f"{DB_CMD}"],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
)
stdout, stderr = process.communicate(input=full_sql, timeout=30)

if process.returncode == 0:
    print("    ✓ 数据灌入成功！")
    if stdout.strip():
        print(f"    MySQL 输出: {stdout.strip()[:200]}")
else:
    print(f"    ✗ 执行失败: {stderr[:500]}")
    exit(1)

# ═══════════════════════════════════════════════════════════════
# Step 6: 验证
# ═══════════════════════════════════════════════════════════════

print(">>> Step 6: 验证数据...")
verify_result = subprocess.run(
    [
        "ssh",
        "root@8.137.180.152",
        f"docker exec grade7-new-db mysql -ugrade7 -p'{DB_PASSWORD}' wings3 -e "
        "\"SELECT COUNT(*) as total_violations FROM discipline_records WHERE school_id=1 AND incident_date >= '2026-05-26';"
        "SELECT type, COUNT(*) as cnt FROM discipline_records WHERE school_id=1 AND incident_date >= '2026-05-26' GROUP BY type;"
        "SELECT COUNT(*) as total_scores FROM student_scores WHERE school_id=1 AND semester='2025-2026-2';\"",
    ],
    capture_output=True,
    text=True,
    timeout=15,
)
print(verify_result.stdout)
print("=== 数据预热完成 ===")
