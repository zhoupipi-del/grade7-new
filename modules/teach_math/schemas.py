"""
modules/teach_math/schemas.py — Pydantic 请求/响应模型
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


# ═══════════════════════════════════════════════════════
# 审题翻译
# ═══════════════════════════════════════════════════════

class TranslateRequest(BaseModel):
    """请求 AI 逐句翻译题目"""
    question_text: str = Field(..., min_length=5, max_length=5000, description="数学应用题原始文本")
    grade_level: str = Field(default="七年级", description="年级")
    knowledge_point: Optional[str] = Field(default=None, description="关联知识点")


class TranslatedSentence(BaseModel):
    """单句翻译结果"""
    sentence: str = Field(..., description="原句")
    math_expression: str = Field(..., description="数学表达式")
    explanation: str = Field(..., description="翻译解释")


class TranslateResponse(BaseModel):
    """翻译完整响应"""
    translations: list[TranslatedSentence] = Field(default=[], description="逐句翻译列表")
    suggested_variables: dict[str, str] = Field(default={}, description="变量含义映射")
    raw_llm_response: dict = Field(default={}, description="LLM 原始响应（调试用）")
    translation_id: Optional[int] = Field(default=None, description="保存后的记录 ID")


# ═══════════════════════════════════════════════════════
# 课件管理（预留，Phase 2+ 使用）
# ═══════════════════════════════════════════════════════

class SlideConfig(BaseModel):
    """单张幻灯片配置"""
    slide_type: str = Field(default="content", description="封面/内容/互动/测验")
    title: Optional[str] = None
    content: Optional[str] = None
    layout: Optional[str] = None
    components: list[dict] = Field(default=[])


class LessonCreate(BaseModel):
    """创建课件"""
    title: str = Field(..., min_length=1, max_length=200)
    grade_level: str = Field(default="七年级")
    knowledge_point: Optional[str] = None
    slides: list[SlideConfig] = Field(default=[])
    status: str = Field(default="draft")


class LessonOut(BaseModel):
    """课件响应"""
    id: int
    title: str
    subject: str
    grade_level: str
    knowledge_point: Optional[str] = None
    slides: list[dict] = []
    status: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class TranslationHistoryOut(BaseModel):
    """翻译历史记录"""
    id: int
    question_text: str
    grade_level: str
    knowledge_point: Optional[str] = None
    llm_response: dict
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ═══════════════════════════════════════════════════════
# 教师端学情报表 (P1: 班级诊断仪表盘)
# ═══════════════════════════════════════════════════════

class TrendDataPoint(BaseModel):
    """翻译使用趋势单点（按日聚合）"""
    date: str = Field(..., description="日期 YYYY-MM-DD")
    count: int = Field(..., description="当日翻译次数")


class MathReportKPI(BaseModel):
    """班级整体 KPI 与趋势"""
    active_students: int = Field(..., description="活跃学生数（有过翻译记录）")
    total_translations: int = Field(..., description="总翻译次数")
    avg_queries_per_student: float = Field(..., description="人均翻译次数")
    risk_students_count: int = Field(..., description="RDI 风险学生数")
    trend_data: list[TrendDataPoint] = Field(default=[], description="按日翻译趋势")


class BlindSpotItem(BaseModel):
    """审题盲区实体 — 高频知识点 = 薄弱环节"""
    term: str = Field(..., description="知识点/盲区术语")
    frequency: int = Field(..., description="出现频次")
    error_type: str = Field(..., description="错误类型标签")


class StudentUsageItem(BaseModel):
    """学生个体学情画像"""
    student_id: int = Field(..., description="用户ID")
    student_name: str = Field(..., description="学生姓名")
    query_count: int = Field(..., description="翻译使用次数")
    top_blind_spot: str = Field(..., description="最高频知识点（盲区）")
    independence_score: float = Field(..., description="自主学习指数 0-100")
    rdi_status: str = Field(..., description="RDI 风险等级: safe/warning/danger")
