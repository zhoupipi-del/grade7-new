"""
research_profile/schemas.py — Pydantic 数据契约 (V3 融合版)

metrics + scores 双层嵌套，支持前端勋章墙渲染。
"""

from pydantic import BaseModel, Field


class ActiveTeacherResponse(BaseModel):
    """活跃教师列表项"""

    id: int = Field(..., description="教师ID")
    real_name: str = Field(..., description="教师姓名")
    subject_code: str | None = Field(None, description="教学学科代码")

    class Config:
        from_attributes = True


class ResearchMetrics(BaseModel):
    """教研行为数量审计指标（V3.2 含质量维度）"""

    plans_count: int = Field(default=0, description="编写教案总数")
    versions_count: int = Field(default=0, description="教案迭代版本总数")
    published_count: int = Field(default=0, description="已审批发布教案数")
    comments_count: int = Field(default=0, description="协同批注与讨论条数")
    activities_count: int = Field(default=0, description="参与教研活动次数")
    observations_count: int = Field(default=0, description="主动听课评课次数")
    observed_count: int = Field(default=0, description="被听课次数")
    timeline_marks_count: int = Field(default=0, description="听评课弹幕打点反馈数")
    ai_integration_count: int = Field(default=0, description="应用AI逆向处方的教案数")
    ai_published_count: int = Field(default=0, description="借助AI最终发布的教案数")
    avg_versions_per_plan: float = Field(default=0.0, description="单教案平均打磨迭代版本")
    # V3.2 质量维度
    observed_avg_score: float = Field(default=0.0, description="被听课时获得平均得分率(0-100)")
    scoring_avg: float = Field(default=0.0, description="该教师给他人评课时平均打分(0-100)")
    scoring_count: int = Field(default=0, description="已完成的评课打分次数")
    school_avg_score: float = Field(default=0.0, description="全校听课评分基准(0-100)")
    rubric_count: int = Field(default=0, description="含多维评分矩阵的听课记录数")


class ResearchScores(BaseModel):
    """四维评估得分体系 (0-100)"""

    intensity: int = Field(default=0, description="备课狂热度得分")
    social: int = Field(default=0, description="教研社交活跃度")
    rigor: int = Field(default=0, description="监理质感/精细听课度")
    ai_integration: int = Field(default=0, description="AI教案转化率得分")


class TeacherResearchProfile(BaseModel):
    """教师教研全息画像"""

    teacher_id: int = Field(..., description="目标教师ID")
    metrics: ResearchMetrics = Field(default_factory=ResearchMetrics)
    scores: ResearchScores = Field(default_factory=ResearchScores)

    class Config:
        from_attributes = True


class TeacherRankingItem(BaseModel):
    """全校教研效能排行榜单项"""

    rank: int = Field(..., description="排名(从1开始)")
    teacher_id: int = Field(..., description="教师ID")
    real_name: str = Field(..., description="教师姓名")
    subject_code: str | None = Field(None, description="教学学科代码")
    composite: float = Field(default=0.0, description="综合教研效能分(0-100, 加权)")
    scores: ResearchScores = Field(default_factory=ResearchScores)

    class Config:
        from_attributes = True


class ResearchRankingResponse(BaseModel):
    """全校教研效能排行榜（领导视图）"""

    metric: str = Field(
        default="composite", description="排序维度: composite/intensity/social/rigor/ai_integration"
    )
    total: int = Field(default=0, description="参与排名的教师总数")
    items: list[TeacherRankingItem] = Field(default_factory=list)

    class Config:
        from_attributes = True


# ═══════════════════════════════════════════════════════════════
# 错题断层归因（dim5 诊断维度，独立子维度，不计入四维综合分）
# ═══════════════════════════════════════════════════════════════


class ErrorGapBreakdown(BaseModel):
    """错题本指标明细"""

    total: int = Field(default=0, description="归因错题总数")
    unresolved: int = Field(default=0, description="未纠错掌握数")
    by_error_type: dict = Field(
        default_factory=dict,
        description="按错误类型分布 conceptual/procedural/careless/omission/unknown",
    )


class KnowledgeGapBreakdown(BaseModel):
    """知识点断层指标明细"""

    total: int = Field(default=0, description="断层记录总数")
    critical: int = Field(default=0, description="critical 级断层数")
    active: int = Field(default=0, description="active 状态断层数")
    resolved: int = Field(default=0, description="resolved 状态断层数")


class TeacherErrorGapResponse(BaseModel):
    """教师任教范围学生错题断层归因（教学盲区关注度诊断信号）"""

    teacher_id: int = Field(..., description="目标教师ID")
    attributed_students: int = Field(default=0, description="归因到的任教学生数（密度分母）")
    attribution: str = Field(
        default="none",
        description="归因桥: precise(课表时空实例)/fallback(教师学科年级组)/none(无任教映射)",
    )
    error_book: ErrorGapBreakdown = Field(default_factory=ErrorGapBreakdown)
    knowledge_gap: KnowledgeGapBreakdown = Field(default_factory=KnowledgeGapBreakdown)
    score: int = Field(default=0, description="教学盲区关注度(0-100)，诊断信号非惩罚分")

    class Config:
        from_attributes = True
