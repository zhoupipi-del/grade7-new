"""
modules/dashboard/models.py — 大数据看板模块

纯聚合查询模块，不新建任何表。
跨库成绩数据通过原生 SQL (text) 从 grade7_new.scores 只读拉取，
不在 Base.metadata 注册任何 ORM 模型，避免 create_all 误操作旧库。
"""

# 违纪级别权重表 — 用于万字违纪率加权计算
# serious=严重(滑窗报警), major=重大, minor=轻微, warning=警告
VIOLATION_WEIGHTS = {
    "serious": 10,
    "major": 5,
    "minor": 3,
    "warning": 1,
}

# 违纪级别中文标签映射（趋势图堆叠用）
SEVERITY_LABELS = {
    "serious": "严重违纪(滑窗报警)",
    "major": "普通违纪",
    "minor": "轻微违纪",
    "warning": "轻微违纪",
}

# 四象限定义
QUADRANT_LABELS = {
    "Q1": "高德育高分（自律学霸区）",
    "Q2": "低德育高分（聪明违纪区）",
    "Q3": "低德育低分（高危双困区）",
    "Q4": "高德育低分（踏实困顿区）",
}
