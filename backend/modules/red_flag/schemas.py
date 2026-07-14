"""
modules/red_flag/schemas.py — Pydantic 请求/响应模型
"""

from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator

# ═══════════════════════════════════════════════════════════════
# RoutineScore 常规评分
# ═══════════════════════════════════════════════════════════════

VALID_CATEGORIES = {"卫生", "纪律", "两操", "礼仪", "自习"}
VALID_SCORER_TYPES = {"class_teacher", "grade_leader", "ms_admin"}


class RoutineScoreCreate(BaseModel):
    class_id: int = Field(..., ge=1)
    grade_id: int = Field(..., ge=1)
    category: str = Field(..., min_length=1, max_length=40)
    score: int = Field(..., ge=0, le=100)
    note: str | None = None
    inspector: str | None = Field(None, max_length=64)
    scorer_type: str = Field(..., min_length=1, max_length=20)
    record_date: date

    @field_validator("category")
    @classmethod
    def check_category(cls, v):
        if v not in VALID_CATEGORIES:
            raise ValueError(f"评分类别仅支持: {', '.join(sorted(VALID_CATEGORIES))}")
        return v

    @field_validator("scorer_type")
    @classmethod
    def check_scorer_type(cls, v):
        if v not in VALID_SCORER_TYPES:
            raise ValueError(f"评分人类型仅支持: {', '.join(sorted(VALID_SCORER_TYPES))}")
        return v


class RoutineScoreBatch(BaseModel):
    scores: list[RoutineScoreCreate] = Field(..., min_length=1, max_length=200)


class RoutineScoreOut(BaseModel):
    id: int
    class_id: int
    grade_id: int
    category: str
    score: int
    note: str | None = None
    inspector: str | None = None
    scorer_type: str
    record_date: date
    created_at: datetime

    class Config:
        from_attributes = True


class RoutineScoreListOut(BaseModel):
    total: int
    items: list[RoutineScoreOut]


# ═══════════════════════════════════════════════════════════════
# FlagEvaluation 流动红旗评价
# ═══════════════════════════════════════════════════════════════

VALID_PERIOD_TYPES = {"week", "month", "term"}


class FlagGenerateRequest(BaseModel):
    period_type: str = Field(..., min_length=1, max_length=10)
    period_label: str = Field(..., min_length=1, max_length=60)
    grade_id: int = Field(..., ge=1)
    start_date: date
    end_date: date

    @field_validator("period_type")
    @classmethod
    def check_period_type(cls, v):
        if v not in VALID_PERIOD_TYPES:
            raise ValueError(f"周期类型仅支持: {', '.join(sorted(VALID_PERIOD_TYPES))}")
        return v


class FlagEvaluationOut(BaseModel):
    id: int
    period_type: str
    period_label: str
    grade_id: int
    class_id: int
    class_name: str | None = None
    self_score: float | None = None
    grade_score: float | None = None
    ms_score: float | None = None
    self_weight: float
    grade_weight: float
    ms_weight: float
    base_score: float | None = None
    discipline_points: float | None = None
    discipline_deduction: float | None = None
    attendance_exceptions: int | None = None
    attendance_deduction: float | None = None
    final_score: float
    rank: int | None = None
    status: str
    created_at: datetime
    published_at: datetime | None = None

    class Config:
        from_attributes = True


class FlagLeaderboardOut(BaseModel):
    """排行榜返回 — 按年级分组的已发布排名"""

    grade_id: int
    grade_name: str | None = None
    period_type: str
    period_label: str
    rankings: list[FlagEvaluationOut]


class FlagDraftListOut(BaseModel):
    total: int
    drafts: list[FlagEvaluationOut]


class PublishResult(BaseModel):
    message: str
    period_type: str
    period_label: str
    grade_id: int
    published_count: int


# ═══════════════════════════════════════════════════════════════
# FlagArchiveReport 归档快照
# ═══════════════════════════════════════════════════════════════


class FlagArchiveOut(BaseModel):
    id: int
    period_type: str
    period_label: str
    grade_id: int
    class_id: int
    class_name: str | None = None
    final_score: float
    rank: int
    has_flag: bool
    base_score: float | None = None
    discipline_deduction: float
    attendance_deduction: float
    snapshot_data: dict | None = None
    archived_at: datetime
    archived_by: int

    class Config:
        from_attributes = True


class ArchiveResult(BaseModel):
    message: str
    period_type: str
    period_label: str
    grade_id: int
    archived_count: int


class ArchiveHistoryOut(BaseModel):
    total: int
    items: list[FlagArchiveOut]


class ClassTrendOut(BaseModel):
    class_id: int
    class_name: str | None = None
    periods: list[str] = []
    scores: list[float] = []
    ranks: list[int] = []
    total_flags_won: int = 0


class TrendResult(BaseModel):
    status: str = "success"
    class_id: int
    class_name: str | None = None
    trends: ClassTrendOut
