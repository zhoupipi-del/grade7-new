"""
modules/dashboard/services.py — 大数据看板聚合引擎

三刀连射：
  刀1 get_class_radar       — 班级万字违纪率晴雨表（横向红黑榜）
  刀2 get_trends            — 违纪严重度堆叠收敛趋势（断崖曲线）
  刀3 get_correlation_scatter — 跨库德育X成绩四象限散点图（王牌）

RBAC 策略（由 router 层传入 scope 限定）：
  MS_ADMIN     → 全校（grade_id=None, class_id=None）
  GRADE_LEADER → 本年级（grade_id=user.grade_id, class_id=None）
  CLASS_TEACHER → 仅本班（class_id=user.class_id）
"""

from datetime import date, timedelta

from core.models import Class, Student
from modules.behavior.models import DisciplineRecord
from modules.evaluation.models import StudentScore
from sqlalchemy import bindparam, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from .models import QUADRANT_LABELS, SEVERITY_LABELS, VIOLATION_WEIGHTS

# ═══════════════════════════════════════════════════════════════
# 刀 1：班级万字违纪率晴雨表
# ═══════════════════════════════════════════════════════════════


async def get_class_radar(
    db: AsyncSession,
    school_id: int,
    grade_id: int | None = None,
    class_id: int | None = None,
) -> dict:
    """
    万字违纪率公式：
      ω_class = (Σ(W_type × C_i) / N_student) × 10^4
      权重: serious=10, major=5, minor=3, warning=1

    正面行为对冲比 = status in (resolved/appealed) 的违纪数 / 总违纪数
    滑窗红线触发数 = 近30天 serious 违纪数
    """
    # ── 构建查询条件 ──
    conds = [DisciplineRecord.school_id == school_id]
    if class_id:
        conds.append(DisciplineRecord.class_id == class_id)
    elif grade_id:
        conds.append(DisciplineRecord.grade_id == grade_id)

    # ── 按班级 × 违纪级别分组聚合 ──
    rows = await db.execute(
        select(
            DisciplineRecord.class_id,
            Class.name.label("class_name"),
            DisciplineRecord.type,
            func.count(DisciplineRecord.id).label("cnt"),
        )
        .join(Class, DisciplineRecord.class_id == Class.id)
        .where(*conds)
        .group_by(DisciplineRecord.class_id, Class.name, DisciplineRecord.type)
    )

    # ── 按班级汇总 ──
    class_map: dict[int, dict] = {}
    for r in rows:
        cid = r.class_id
        if cid not in class_map:
            class_map[cid] = {
                "class_id": cid,
                "class_name": r.class_name,
                "counts_by_type": {},
                "total_violations": 0,
            }
        class_map[cid]["counts_by_type"][r.type] = int(r.cnt)
        class_map[cid]["total_violations"] += int(r.cnt)

    if not class_map:
        return {
            "columns": ["班级名称", "万字违纪率", "正面行为对冲比", "滑窗红线触发数"],
            "rows": [],
        }

    # ── 查班级人数 ──
    cids = list(class_map.keys())
    pop_rows = await db.execute(
        select(Class.id, Class.student_count, Class.name).where(Class.id.in_(cids))
    )
    for r in pop_rows:
        if r[0] in class_map:
            class_map[r[0]]["student_count"] = int(r[1] or 0)
            class_map[r[0]]["class_name"] = r[2]

    # ── 查近30天 serious 违纪数（滑窗红线）──
    thirty_ago = date.today() - timedelta(days=30)
    alert_conds = list(conds) + [
        DisciplineRecord.type == "serious",
        DisciplineRecord.incident_date >= thirty_ago,
    ]
    alert_rows = await db.execute(
        select(
            DisciplineRecord.class_id,
            func.count(DisciplineRecord.id),
        )
        .where(*alert_conds)
        .group_by(DisciplineRecord.class_id)
    )
    alert_map = {r[0]: int(r[1]) for r in alert_rows}

    # ── 查已处理违纪数（正面对冲）──
    resolved_conds = list(conds) + [
        DisciplineRecord.status.in_(["resolved", "appealed"]),
    ]
    resolved_rows = await db.execute(
        select(
            DisciplineRecord.class_id,
            func.count(DisciplineRecord.id),
        )
        .where(*resolved_conds)
        .group_by(DisciplineRecord.class_id)
    )
    resolved_map = {r[0]: int(r[1]) for r in resolved_rows}

    # ── 计算万字违纪率 ──
    result_rows = []
    for cid, info in class_map.items():
        sc = info.get("student_count", 0) or 1  # 防除零
        weighted_sum = sum(
            VIOLATION_WEIGHTS.get(vtype, 1) * cnt for vtype, cnt in info["counts_by_type"].items()
        )
        violation_rate = round((weighted_sum / sc) * 10000, 2)

        total_v = info["total_violations"] or 1
        positive_ratio = round(resolved_map.get(cid, 0) / total_v, 2)
        slide_alerts = alert_map.get(cid, 0)

        result_rows.append(
            {
                "class_id": cid,
                "class_name": info["class_name"],
                "violation_rate": violation_rate,
                "positive_ratio": positive_ratio,
                "slide_alerts": slide_alerts,
                "total_violations": info["total_violations"],
                "student_count": sc,
            }
        )

    # 按万字违纪率降序排（红黑榜）
    result_rows.sort(key=lambda x: x["violation_rate"], reverse=True)

    return {
        "columns": ["班级名称", "万字违纪率", "正面行为对冲比", "滑窗红线触发数"],
        "rows": result_rows,
    }


# ═══════════════════════════════════════════════════════════════
# 刀 2：违纪严重度堆叠收敛趋势
# ═══════════════════════════════════════════════════════════════


async def get_trends(
    db: AsyncSession,
    school_id: int,
    time_frame: str = "30d",
    grade_id: int | None = None,
    class_id: int | None = None,
) -> dict:
    """
    按日/周聚合违纪频次，按严重度堆叠。
    time_frame: 7d=近7天按日, 30d=近30天按周, 90d=近90天按周
    """
    # ── 解析时间范围 ──
    days_map = {"7d": 7, "30d": 30, "90d": 90}
    days = days_map.get(time_frame, 30)
    start_date = date.today() - timedelta(days=days)
    weekly = days > 7  # 30d/90d 按周聚合

    # ── 构建查询条件 ──
    conds = [
        DisciplineRecord.school_id == school_id,
        DisciplineRecord.incident_date >= start_date,
    ]
    if class_id:
        conds.append(DisciplineRecord.class_id == class_id)
    elif grade_id:
        conds.append(DisciplineRecord.grade_id == grade_id)

    # ── 按日期 + 级别分组 ──
    rows = await db.execute(
        select(
            DisciplineRecord.incident_date,
            DisciplineRecord.type,
            func.count(DisciplineRecord.id),
        )
        .where(*conds)
        .group_by(
            DisciplineRecord.incident_date,
            DisciplineRecord.type,
        )
        .order_by(DisciplineRecord.incident_date)
    )

    # ── Python 侧聚合到时间桶 ──
    # bucket_key -> {severity_group: count}
    buckets: dict[str, dict[str, int]] = {}
    for r in rows:
        d = r[0]
        if d is None:
            continue
        vtype = r[1]
        cnt = int(r[2])

        if weekly:
            # 按周聚合：取本周周一作为桶键
            monday = d - timedelta(days=d.weekday())
            bucket_key = monday.strftime("%m-%d")
        else:
            bucket_key = d.strftime("%m-%d")

        if bucket_key not in buckets:
            buckets[bucket_key] = {"轻微违纪": 0, "普通违纪": 0, "严重违纪(滑窗报警)": 0}

        severity = SEVERITY_LABELS.get(vtype, "轻微违纪")
        buckets[bucket_key][severity] += cnt

    # ── 排序时间线 ──
    sorted_keys = sorted(buckets.keys())
    timeline = sorted_keys
    series = [
        {"name": "轻微违纪", "data": [buckets[k]["轻微违纪"] for k in sorted_keys]},
        {"name": "普通违纪", "data": [buckets[k]["普通违纪"] for k in sorted_keys]},
        {
            "name": "严重违纪(滑窗报警)",
            "data": [buckets[k]["严重违纪(滑窗报警)"] for k in sorted_keys],
        },
    ]

    return {"timeline": timeline, "series": series}


# ═══════════════════════════════════════════════════════════════
# 刀 3：跨库德育 X 成绩四象限散点图
# ═══════════════════════════════════════════════════════════════


async def get_correlation_scatter(
    db: AsyncSession,
    school_id: int,
    grade_id: int | None = None,
    class_id: int | None = None,
    semester: str = "2025-2026-2",
) -> dict:
    """
    X轴 = Wings 3.0 StudentScore.total_score（德育量化总分）
    Y轴 = 旧库 grade7_new.scores 跨库拉取的学业平均分

    跨库方案：同一 MySQL 实例，直接用 text() 原生 SQL 查 grade7_new.scores
    四象限分类：以中位数为分界线
    """
    # ── Step 1: 拉取德育分（X轴）──
    score_conds = [
        StudentScore.school_id == school_id,
        StudentScore.semester == semester,
    ]
    if class_id:
        score_conds.append(StudentScore.class_id == class_id)
    elif grade_id:
        score_conds.append(StudentScore.grade_id == grade_id)

    score_rows = await db.execute(
        select(
            StudentScore.student_id,
            StudentScore.total_score,
            Student.name.label("student_name"),
        )
        .join(Student, StudentScore.student_id == Student.id)
        .where(*score_conds)
    )

    moral_data = {}  # student_id -> (total_score, name)
    for r in score_rows:
        moral_data[r.student_id] = (float(r.total_score or 0), r.student_name)

    if not moral_data:
        return {"quadrants": QUADRANT_LABELS, "points": []}

    # ── Step 2: 跨库拉取成绩（Y轴）──
    student_ids = list(moral_data.keys())
    # 用 expanding bindparam 安全展开 IN 子句
    legacy_sql = text(
        "SELECT student_id, AVG(score) as avg_score "
        "FROM grade7_new.scores "
        "WHERE student_id IN :sids "
        "GROUP BY student_id"
    ).bindparams(bindparam("sids", expanding=True))

    legacy_rows = await db.execute(legacy_sql, {"sids": student_ids})
    legacy_scores = {int(r[0]): float(r[1]) for r in legacy_rows}

    # ── Step 3: 合并 + 四象限分类 ──
    merged = []
    for sid, (moral_score, name) in moral_data.items():
        math_score = legacy_scores.get(sid)
        if math_score is None:
            continue  # 旧库无成绩，跳过
        merged.append(
            {
                "student_id": sid,
                "student_name": name,
                "x_moral_score": round(moral_score, 1),
                "y_math_score": round(math_score, 1),
            }
        )

    if not merged:
        return {"quadrants": QUADRANT_LABELS, "points": []}

    # ── 计算中位数 ──
    moral_vals = sorted([m["x_moral_score"] for m in merged])
    math_vals = sorted([m["y_math_score"] for m in merged])
    moral_median = moral_vals[len(moral_vals) // 2]
    math_median = math_vals[len(math_vals) // 2]

    # ── 四象限分类 ──
    for m in merged:
        x, y = m["x_moral_score"], m["y_math_score"]
        if x >= moral_median and y >= math_median:
            m["quadrant"] = "Q1"
        elif x < moral_median and y >= math_median:
            m["quadrant"] = "Q2"
        elif x < moral_median and y < math_median:
            m["quadrant"] = "Q3"
        else:
            m["quadrant"] = "Q4"
        m["top_blind_spots"] = []  # 知识点盲区预留，后续对接

    return {
        "quadrants": QUADRANT_LABELS,
        "points": merged,
        "medians": {
            "moral_median": moral_median,
            "math_median": math_median,
        },
    }
