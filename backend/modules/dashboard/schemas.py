"""
modules/dashboard/schemas.py — 大数据看板 Pydantic 响应模型

三个端点的 JSON 契约基准线，前后端以此为准。
"""

from typing import List, Optional
from pydantic import BaseModel


# ═══════════════════════════════════════════════════════════════
# 端点一：班级万字违纪率晴雨表
# ═══════════════════════════════════════════════════════════════

class ClassRadarItem(BaseModel):
    class_id: int
    class_name: str
    violation_rate: float          # 万字违纪率（加权÷人数×10^4）
    positive_ratio: float          # 正面行为对冲比（已处理/总数）
    slide_alerts: int              # 滑窗红线触发数（近30天 serious 违纪数）
    total_violations: int          # 违纪总数
    student_count: int             # 班级人数


class ClassRadarOut(BaseModel):
    status: str = "success"
    data: dict                     # {"columns": [...], "rows": [ClassRadarItem...]}


# ═══════════════════════════════════════════════════════════════
# 端点二：违纪严重度堆叠收敛趋势
# ═══════════════════════════════════════════════════════════════

class TrendSeries(BaseModel):
    name: str                      # "轻微违纪" / "普通违纪" / "严重违纪(滑窗报警)"
    data: List[int]


class TrendOut(BaseModel):
    status: str = "success"
    data: dict                     # {"timeline": [...], "series": [TrendSeries...]}


# ═══════════════════════════════════════════════════════════════
# 端点三：德育 X 成绩四象限散点图
# ═══════════════════════════════════════════════════════════════

class ScatterPoint(BaseModel):
    student_id: int
    student_name: str
    x_moral_score: float           # 德育量化总分（X轴）
    y_math_score: float            # 数学/学业成绩（Y轴，跨库拉取）
    quadrant: str                  # Q1/Q2/Q3/Q4
    top_blind_spots: List[str] = []  # 知识点盲区（预留）


class ScatterOut(BaseModel):
    status: str = "success"
    data: dict                     # {"quadrants": {...}, "points": [ScatterPoint...]}
