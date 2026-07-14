"""
modules/grades/schemas.py — Pydantic 请求/响应模型

覆盖端点:
- 科目 CRUD: SubjectCreate / SubjectUpdate / SubjectOut
- 考试 CRUD: ExamCreate / ExamUpdate / ExamOut
- 成绩录入: ScoreUploadRequest（批量）+ ScoreUploadResult
- 成绩查询: StudentScoreOut / ExamResultOut / ClassScoreSummary
- 审计日志: AuditLogOut
"""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

# ═══════════════════════════════════════════════════════
# 科目管理
# ═══════════════════════════════════════════════════════


class SubjectCreate(BaseModel):
    """创建/注册科目"""

    name: str = Field(..., min_length=1, max_length=50, description="科目名称（语文/数学/英语...）")
    code: str = Field(
        ..., min_length=1, max_length=30, description="科目代码（chinese/math/english...）"
    )
    full_score: Decimal = Field(default=Decimal("100.00"), description="满分值")
    sort_order: int = Field(default=0, description="排序权重")


class SubjectUpdate(BaseModel):
    """更新科目信息（所有字段可选）"""

    name: str | None = Field(default=None, max_length=50)
    code: str | None = Field(default=None, max_length=30)
    full_score: Decimal | None = None
    sort_order: int | None = None
    is_active: bool | None = None


class SubjectOut(BaseModel):
    """科目响应"""

    id: int
    name: str
    code: str
    full_score: Decimal
    sort_order: int
    is_active: bool
    created_at: datetime | None = None

    class Config:
        from_attributes = True


class SubjectItem(BaseModel):
    """科目列表项（精简版）"""

    id: int
    name: str
    code: str
    full_score: Decimal
    is_active: bool

    class Config:
        from_attributes = True


# ═══════════════════════════════════════════════════════
# 考试管理
# ═══════════════════════════════════════════════════════


class ExamCreate(BaseModel):
    """创建考试"""

    name: str = Field(..., min_length=1, max_length=200, description="考试名称")
    exam_type: str = Field(default="midterm", description="类型: monthly/midterm/final/quiz")
    grade_id: int = Field(..., description="年级 ID")
    semester: str = Field(default="2025-1", description="学期标识")
    exam_date: datetime | None = Field(default=None, description="考试日期")


class ExamUpdate(BaseModel):
    """更新考试信息"""

    name: str | None = Field(default=None, max_length=200)
    exam_type: str | None = None
    semester: str | None = None
    exam_date: datetime | None = None
    status: str | None = None  # draft / published / archived


class ExamOut(BaseModel):
    """考试响应"""

    id: int
    name: str
    exam_type: str
    grade_id: int
    semester: str
    exam_date: datetime | None = None
    status: str
    created_by: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class ExamItem(BaseModel):
    """考试列表项（精简版）"""

    id: int
    name: str
    exam_type: str
    semester: str
    exam_date: datetime | None = None
    status: str

    class Config:
        from_attributes = True


# ═══════════════════════════════════════════════════════
# 成绩录入（批量）
# ═══════════════════════════════════════════════════════


class ScoreEntry(BaseModel):
    """单条成绩记录"""

    student_id: int = Field(..., description="学生 ID")
    subject_id: int = Field(..., description="科目 ID")
    score: Decimal | None = Field(default=None, description="得分（None 表示缺考）")
    is_absent: bool = Field(default=False, description="是否缺考")
    remark: str | None = Field(default=None, max_length=200, description="备注")


class ScoreUploadRequest(BaseModel):
    """批量成绩录入请求

    支持两趟扫描模式：
    - 扫描1: 请求中包含所有 student×subject 条目
    - 扫描2: 服务层 upsert（新增/更新）后统一计算排名
    """

    exam_id: int = Field(..., description="考试 ID")
    scores: list[ScoreEntry] = Field(..., min_length=1, description="成绩列表")


class ScoreUploadResult(BaseModel):
    """批量成绩录入结果"""

    exam_id: int
    total: int = Field(..., description="总提交条数")
    success: int = Field(..., description="成功录入数")
    failed: int = Field(..., description="失败数")
    errors: list[str] = Field(default=[], description="失败详情")
    ranks_computed: bool = Field(default=True, description="是否已完成排名计算")


# ═══════════════════════════════════════════════════════
# 成绩查询
# ═══════════════════════════════════════════════════════


class StudentScoreOut(BaseModel):
    """单科成绩（学生视角）"""

    subject_id: int
    subject_name: str = Field(..., description="科目名称")
    full_score: Decimal = Field(..., description="满分值")
    score: Decimal | None = Field(default=None, description="得分")
    is_absent: bool = False
    class_rank: int | None = None
    grade_rank: int | None = None

    class Config:
        from_attributes = True


class StudentExamResult(BaseModel):
    """某学生在某次考试中的全科成绩"""

    student_id: int
    student_name: str
    class_id: int
    class_name: str
    total_score: Decimal | None = Field(default=None, description="总分")
    avg_score: float | None = Field(default=None, description="均分（剔除缺考科目）")
    class_rank: int | None = Field(default=None, description="班级排名")
    grade_rank: int | None = Field(default=None, description="年级排名")
    subjects: list[StudentScoreOut] = Field(default=[], description="各科成绩明细")


class ExamResultQuery(BaseModel):
    """考试结果查询参数"""

    exam_id: int = Field(..., description="考试 ID")
    class_id: int | None = Field(default=None, description="班级 ID（可选，按班级过滤）")
    student_name: str | None = Field(default=None, description="学生姓名（模糊搜索）")
    sort_by: str = Field(default="total_score_desc", description="排序: total_score_desc/asc")
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=200)


class ClassScoreSummary(BaseModel):
    """班级成绩汇总"""

    class_id: int
    class_name: str
    student_count: int = Field(..., description="参考人数")
    avg_total: float | None = Field(default=None, description="总分均分")
    max_total: float | None = Field(default=None, description="总分最高")
    min_total: float | None = Field(default=None, description="总分最低")
    pass_rate: float | None = Field(default=None, description="及格率（总分≥60%）")
    excellent_rate: float | None = Field(default=None, description="优秀率（总分≥90%）")
    subjects: list["SubjectSummary"] = Field(default=[], description="各科统计")


class SubjectSummary(BaseModel):
    """单科班级统计"""

    subject_id: int
    subject_name: str
    full_score: Decimal
    avg_score: float | None = None
    max_score: float | None = None
    min_score: float | None = None
    pass_rate: float | None = None
    excellent_rate: float | None = None


class ExamResultPage(BaseModel):
    """考试结果分页响应"""

    exam: ExamOut
    total: int
    page: int
    page_size: int
    results: list[StudentExamResult] = []
    class_summaries: list[ClassScoreSummary] = []


# ═══════════════════════════════════════════════════════
# 审计日志
# ═══════════════════════════════════════════════════════


class AuditLogOut(BaseModel):
    """成绩变更审计日志"""

    id: int
    exam_id: int
    student_id: int
    subject_id: int
    old_score: Decimal | None = None
    new_score: Decimal | None = None
    action: str
    operator_id: int | None = None
    operator_name: str | None = None
    created_at: datetime | None = None

    class Config:
        from_attributes = True


class AuditLogQuery(BaseModel):
    """审计日志查询参数"""

    exam_id: int | None = None
    student_id: int | None = None
    action: str | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=200)
