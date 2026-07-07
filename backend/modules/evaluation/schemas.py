"""
modules/evaluation/schemas.py — Pydantic 请求/响应模型

命名约定:
  - *Create: 创建请求
  - *Update: 更新请求
  - *Out:    响应模型
  - *Item:   列表项
"""

from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════
# 评价指标 (Indicator)
# ═══════════════════════════════════════════════════════════════

class IndicatorCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=50, description="指标名称")
    parent_id: int = Field(0, ge=0, description="父指标ID，0=一级维度")
    dimension: Optional[str] = Field(None, max_length=30, description="维度标识: moral/academic/health/art/social")
    weight: float = Field(0.0, ge=0.0, le=1.0, description="权重（二级指标在其维度的权重）")
    max_score: float = Field(100.0, ge=0.0, description="满分值")
    sort_order: int = Field(0, ge=0, description="排序")


class IndicatorUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=50)
    weight: Optional[float] = Field(None, ge=0.0, le=1.0)
    max_score: Optional[float] = Field(None, ge=0.0)
    sort_order: Optional[int] = Field(None, ge=0)


class IndicatorOut(BaseModel):
    id: int
    name: str
    parent_id: int
    dimension: Optional[str] = None
    weight: float
    max_score: float
    sort_order: int
    is_active: bool
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class IndicatorGroupedOut(BaseModel):
    """按维度分组返回的指标"""
    dimension: str
    dimension_name: str
    indicators: List[IndicatorOut]


# ═══════════════════════════════════════════════════════════════
# 评分规则 (Rule)
# ═══════════════════════════════════════════════════════════════

class DimensionWeights(BaseModel):
    moral: float = Field(0.25, ge=0.0, le=1.0)
    academic: float = Field(0.25, ge=0.0, le=1.0)
    health: float = Field(0.20, ge=0.0, le=1.0)
    art: float = Field(0.15, ge=0.0, le=1.0)
    social: float = Field(0.15, ge=0.0, le=1.0)


class DeductionMap(BaseModel):
    warning: float = Field(1.0, ge=0.0)
    minor: float = Field(3.0, ge=0.0)
    major: float = Field(5.0, ge=0.0)
    serious: float = Field(10.0, ge=0.0)


class RuleUpdate(BaseModel):
    dimension_weights: Optional[DimensionWeights] = None
    balance_threshold: Optional[float] = Field(None, ge=1.0, le=3.0, description="平衡惩罚触发阈值")
    balance_penalty: Optional[float] = Field(None, ge=0.0, le=1.0, description="平衡惩罚系数")
    deduction_map: Optional[DeductionMap] = None
    base_score: Optional[float] = Field(None, ge=0.0, description="每人起始分")
    max_score: Optional[float] = Field(None, ge=0.0, description="满分上限")


class RuleOut(BaseModel):
    id: int
    dimension_weights: dict
    balance_threshold: float
    balance_penalty: float
    deduction_map: dict
    base_score: float
    max_score: float
    is_active: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ═══════════════════════════════════════════════════════════════
# 评分记录 (Score)
# ═══════════════════════════════════════════════════════════════

class ScoreCreate(BaseModel):
    student_id: int = Field(..., gt=0)
    class_id: int = Field(..., gt=0)
    grade_id: int = Field(..., gt=0)
    indicator_id: int = Field(..., gt=0)
    score: float = Field(..., ge=0.0, description="评分值")
    scorer_type: str = Field(..., description="评分人类型: teacher/self/peer/parent/system")
    semester: Optional[str] = Field(None, description="学期，默认当前学期")
    comment: str = Field("", max_length=500)


class ScoreOut(BaseModel):
    id: int
    student_id: int
    class_id: int
    grade_id: int
    indicator_id: int
    indicator_name: Optional[str] = None
    score: float
    scorer_type: str
    scorer_id: int
    semester: str
    comment: str
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class BatchScoreCreate(BaseModel):
    """批量评分请求"""
    scores: List[ScoreCreate] = Field(..., min_length=1, max_length=200)


class BatchScoreResult(BaseModel):
    """批量评分结果"""
    success: int
    failed: int
    errors: List[dict] = []


# ═══════════════════════════════════════════════════════════════
# 学生总分 (StudentScore)
# ═══════════════════════════════════════════════════════════════

class DimensionBreakdown(BaseModel):
    moral: float = 0.0
    academic: float = 0.0
    health: float = 0.0
    art: float = 0.0
    social: float = 0.0


class StudentScoreOut(BaseModel):
    student_id: int
    student_name: Optional[str] = None
    student_no: Optional[str] = None
    class_id: int
    grade_id: int
    semester: str
    total_score: float
    moral_score: float
    academic_score: float
    health_score: float
    art_score: float
    social_score: float
    base_score: float
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ClassRankingItem(BaseModel):
    rank: int
    student_id: int
    student_name: str
    student_no: str
    total_score: float
    moral_score: float
    academic_score: float
    health_score: float
    art_score: float
    social_score: float


class ClassRankingOut(BaseModel):
    class_id: int
    semester: str
    total_students: int
    avg_score: float
    ranking: List[ClassRankingItem]


# ═══════════════════════════════════════════════════════════════
# 审计流水 (ScoreLog)
# ═══════════════════════════════════════════════════════════════

class ScoreLogOut(BaseModel):
    id: int
    student_id: int
    student_name: Optional[str] = None
    dimension: Optional[str] = None
    change_amount: float
    before_score: float
    after_score: float
    reason: str
    source_type: str
    source_id: Optional[int] = None
    created_by: Optional[int] = None
    creator_name: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ScoreLogListOut(BaseModel):
    items: List[ScoreLogOut]
    total: int
    page: int
    per_page: int


# ═══════════════════════════════════════════════════════════════
# 通用
# ═══════════════════════════════════════════════════════════════

class MessageOut(BaseModel):
    message: str
    detail: Optional[str] = None


class SeedResultOut(BaseModel):
    rules_created: bool
    indicators_count: int
    message: str


# ═══════════════════════════════════════════════════════════════
# 处分强电桥接 —— 期末综合评价输出
# ═══════════════════════════════════════════════════════════════

class SanctionBrief(BaseModel):
    """处分摘要"""
    level: str
    label: str
    punish_date: Optional[str] = None
    document_no: Optional[str] = None
    reason: Optional[str] = None


class RevokedSanctionBrief(BaseModel):
    """已撤销处分摘要（含正向复活标签）"""
    level: str
    label: str
    punish_date: Optional[str] = None
    revoke_date: Optional[str] = None
    revoke_reason: Optional[str] = None
    document_no: Optional[str] = None


class DisciplinePenaltyOut(BaseModel):
    """处分扣分结果"""
    total_deduction: float
    active_sanctions: List[SanctionBrief] = []
    active_count: int = 0


class VetoResult(BaseModel):
    """一票否决裁定"""
    is_veto: bool
    forced_grade: Optional[str] = None
    reason: Optional[str] = None


class FiveDimScores(BaseModel):
    """五维分数"""
    moral: float = 0.0
    academic: float = 0.0
    health: float = 0.0
    art: float = 0.0
    social: float = 0.0
    total: float = 0.0


class FinalEvaluationOut(BaseModel):
    """期末综合评价 — 含处分影响的最终裁定"""
    student_id: int
    semester: str
    base_scores: FiveDimScores
    discipline_penalty: DisciplinePenaltyOut
    adjusted_scores: FiveDimScores
    veto: VetoResult
    revoked_sanctions: List[RevokedSanctionBrief] = []
    has_revoked: bool = False
    final_grade: str
    grade_label: str


class DisciplineVetoOut(BaseModel):
    """一票否决检查结果"""
    student_id: int
    is_veto: bool
    forced_grade: Optional[str] = None
    veto_reason: Optional[str] = None
    active_sanctions: List[SanctionBrief] = []
    active_count: int = 0
