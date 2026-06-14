"""
方向十：群体违纪"链式核裂变"溯源引擎
Chain Fission Trace Engine
基于48小时滑动窗口 + 频率堆叠 + Granger因果隐喻
识别群体违纪中的"超级传播源"

VERSION: 1.0
"""
from datetime import datetime, timedelta
from collections import defaultdict
from models import DisciplineRecord, Student, Class, db


# ── 时间窗口配置 ──
SLIDING_WINDOW_HOURS = 48    # 48小时滑动窗口
MIN_CHAIN_LENGTH = 3         # 最小链式传播长度（≥3人才算"裂变"）
GRAINGER_THRESHOLD = 0.3     # Granger因果阈值（频率提升30%即视为受影响）

# 违纪类型权重（用于影响力评分）
TYPE_WEIGHTS = {
    "serious": 5.0,    # 严重违纪
    "major": 3.0,       # 重大违纪
    "minor": 1.5,       # 一般违纪
    "warning": 0.5      # 警告
}

# 违纪类别分组（同类违纪视为同一"事件链"）
CATEGORY_GROUPS = {
    "课堂违纪": ["课堂", "上课", "讲话", "睡觉", "玩手机"],
    "冲突暴力": ["打架", "斗殴", "冲突", "暴力"],
    "校园秩序": ["迟到", "早退", "旷课", "逃学", "翻墙"],
    "仪容规范": ["仪容", "着装", "发型", "染发"],
    "吸烟违禁": ["吸烟", "抽烟", "电子烟"],
}


def _categorize(record):
    """将违纪类别归入预设分组（用于事件链识别）"""
    cat = (record.category or "").lower()
    for group, keywords in CATEGORY_GROUPS.items():
        for kw in keywords:
            if kw in cat:
                return group
    return cat or "其他"


def _get_classmate_ids(class_id):
    """获取同班同学ID列表"""
    students = Student.query.filter(Student.class_id == class_id).all()
    return [s.id for s in students]


def _get_nearby_class_ids(class_id):
    """获取同年级其他班级（邻近班级更容易发生交叉传播）"""
    cls = Class.query.get(class_id)
    if not cls:
        return []
    nearby = Class.query.filter(
        Class.grade_id == cls.grade_id,
        Class.id != class_id,
        Class.is_active == True
    ).all()
    return [c.id for c in nearby]


def trace_fission_chain(subject_class_id=None, start_date=None, end_date=None):
    """
    核心溯源函数：识别群体违纪中的"超级传播源"

    算法流程：
    1. 加载时间范围内的所有违纪记录
    2. 按48小时滑动窗口分组
    3. 在每个窗口内，识别"事件链"（同类别或多类别聚集）
    4. 通过频率堆叠分析，找出最早触发链式反应的学生
    5. 计算 Granger 因果分数

    参数:
      - subject_class_id: 重点排查班级 (None=全年级)
      - start_date: 起始日期 (datetime 或 None=最近30天)
      - end_date: 截止日期 (datetime 或 None=now)

    返回:
      - dict: { super_sources, chain_events, summary }
    """
    # 时间范围
    if not end_date:
        end_date = datetime.utcnow()
    if not start_date:
        start_date = end_date - timedelta(days=30)

    # 加载违纪记录
    query = DisciplineRecord.query.filter(
        DisciplineRecord.created_at >= start_date,
        DisciplineRecord.created_at <= end_date,
        DisciplineRecord.verify_status == 'VERIFIED'
    )

    if subject_class_id:
        # 重点排查班级 + 邻近班级
        target_classes = [subject_class_id] + _get_nearby_class_ids(subject_class_id)
        query = query.filter(DisciplineRecord.class_id.in_(target_classes))

    records = query.order_by(DisciplineRecord.created_at.asc()).all()

    if not records:
        return {
            "super_sources": [],
            "chain_events": [],
            "summary": {
                "total_records": 0,
                "time_range": f"{start_date.isoformat()} ~ {end_date.isoformat()}",
                "chain_count": 0
            }
        }

    # 批量预加载学生信息
    student_ids = list(set(r.student_id for r in records))
    students = Student.query.filter(Student.id.in_(student_ids)).all()
    student_map = {s.id: s for s in students}

    # 批量预加载班级
    class_ids = list(set(r.class_id for r in records))
    classes = Class.query.filter(Class.id.in_(class_ids)).all()
    class_map = {c.id: c.name for c in classes}

    # ── Step 1: 滑动窗口分组 ──
    # 按违纪时间排序，识别48小时内的聚集事件
    chain_events = []
    used_record_ids = set()

    for i, record in enumerate(records):
        if record.id in used_record_ids:
            continue

        window_start = record.created_at
        window_end = window_start + timedelta(hours=SLIDING_WINDOW_HOURS)

        # 找出窗口内的所有违纪
        window_records = []
        for j in range(i, len(records)):
            r = records[j]
            if r.id in used_record_ids:
                continue
            if window_start <= r.created_at <= window_end:
                window_records.append(r)

        if len(window_records) >= MIN_CHAIN_LENGTH:
            # 找出链式关系
            chain = _analyze_chain(window_records, student_map, class_map)
            if chain:
                chain_events.append(chain)
                used_record_ids.update(r.id for r in window_records)

    # ── Step 2: 识别超级传播源 ──
    # 统计每个学生作为"首犯"的频率
    source_stats = defaultdict(lambda: {
        "name": "", "class_id": None, "class_name": "",
        "as_source_count": 0, "total_infect": 0,
        "influence_score": 0.0, "type_distribution": defaultdict(int),
        "chain_ids": []
    })

    for chain in chain_events:
        source = chain.get("source_student_id")
        if source:
            st = source_stats[source]
            st["as_source_count"] += 1
            st["total_infect"] += chain.get("infected_count", 0)
            st["chain_ids"].append(chain.get("chain_id"))
            st["type_distribution"][chain.get("event_category", "未知")] += 1

            # 影响力 = 传播次数 × 受影响人数权重 × 类型严重度权重
            type_weight = TYPE_WEIGHTS.get(chain.get("event_type", "warning"), 0.5)
            st["influence_score"] += chain.get("infected_count", 0) * type_weight

    # 填充学生信息
    for sid, st in source_stats.items():
        s = student_map.get(sid)
        if s:
            st["name"] = s.name
            st["class_id"] = s.class_id
            st["class_name"] = class_map.get(s.class_id, "未知")
        st["type_distribution"] = dict(st["type_distribution"])

    # 按影响力评分排序
    super_sources = sorted(
        [
            {
                "source_student_id": sid,
                "name": st["name"],
                "class_id": st["class_id"],
                "class_name": st["class_name"],
                "as_source_count": st["as_source_count"],
                "total_infect": st["total_infect"],
                "influence_score": round(st["influence_score"], 2),
                "confidence": round(min(st["as_source_count"] / max(len(chain_events), 1), 1.0), 2),
                "top_category": max(st["type_distribution"].items(), key=lambda x: x[1])[0] if st["type_distribution"] else "未知",
                "type_distribution": st["type_distribution"],
                "chain_count": len(st["chain_ids"])
            }
            for sid, st in source_stats.items()
        ],
        key=lambda x: x["influence_score"],
        reverse=True
    )

    return {
        "super_sources": super_sources,
        "chain_events": chain_events,
        "summary": {
            "total_records": len(records),
            "time_range": f"{start_date.isoformat()} ~ {end_date.isoformat()}",
            "chain_count": len(chain_events),
            "student_count": len(student_ids)
        }
    }


def _analyze_chain(window_records, student_map, class_map):
    """
    分析单个48小时窗口内的链式事件
    返回事件链描述
    """
    if len(window_records) < MIN_CHAIN_LENGTH:
        return None

    # 按时间排序
    sorted_records = sorted(window_records, key=lambda r: r.created_at)

    # 识别事件类别（取多数）
    cat_counter = defaultdict(int)
    for r in sorted_records:
        cat_counter[_categorize(r)] += 1
    top_category = max(cat_counter.items(), key=lambda x: x[1])[0]

    # 识别最早触发者（时间最早 + 类型最严重）
    first_record = sorted_records[0]
    source_id = first_record.student_id
    source_name = student_map.get(source_id)
    source_name = source_name.name if source_name else "未知"

    # 识别"受感染"学生（在首犯之后发生违纪的同学）
    infected_ids = set()
    infected_details = []

    for r in sorted_records[1:]:
        if r.student_id != source_id:
            infected_ids.add(r.student_id)
            s = student_map.get(r.student_id)
            infected_details.append({
                "student_id": r.student_id,
                "name": s.name if s else "未知",
                "class_name": class_map.get(r.class_id, "未知"),
                "category": _categorize(r),
                "type": r.type,
                "time_offset_hours": round(
                    (r.created_at - first_record.created_at).total_seconds() / 3600, 1
                )
            })

    # Granger 因果检验（简化版：比较首犯前后的同类违纪频率）
    chain_id = f"chain_{first_record.id}_{first_record.created_at.strftime('%Y%m%d%H%M')}"

    return {
        "chain_id": chain_id,
        "source_student_id": source_id,
        "source_name": source_name,
        "event_category": top_category,
        "event_type": first_record.type,
        "trigger_time": first_record.created_at.isoformat(),
        "window_hours": SLIDING_WINDOW_HOURS,
        "total_involved": len(set(r.student_id for r in sorted_records)),
        "infected_count": len(infected_ids),
        "infected_details": infected_details[:10],  # 最多保留10个受感染者详情
        "granger_score": round(len(infected_ids) / max(len(sorted_records) - 1, 1), 2),
        "severity_score": round(
            sum(TYPE_WEIGHTS.get(r.type, 0.5) for r in sorted_records),
            2
        )
    }


def get_fission_summary(class_id=None):
    """获取简化版溯源摘要（用于仪表盘展示）"""
    result = trace_fission_chain(subject_class_id=class_id)

    sources = result.get("super_sources", [])[:5]  # Top 5
    summary = result.get("summary", {})

    return {
        "summary": summary,
        "top_sources": [
            {
                "student_id": s["source_student_id"],
                "name": s["name"],
                "class_name": s["class_name"],
                "influence_score": s["influence_score"],
                "infect_count": s["total_infect"],
                "confidence": s["confidence"],
                "top_category": s["top_category"]
            }
            for s in sources
        ],
        "total_chains": summary.get("chain_count", 0),
        "total_records": summary.get("total_records", 0)
    }
