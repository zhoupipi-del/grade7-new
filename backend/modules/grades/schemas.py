"""
modules/grades/schemas.py — Pydantic 请求/响应模型

覆盖端点:
- 科目 CRUD: SubjectCreate / SubjectUpdate / SubjectOut
- 考试 CRUD: ExamCreate / ExamUpdate / ExamOut
- 成绩录入: ScoreUploadRequest（批量）+ ScoreUploadResult
- 成绩查询: StudentScoreOut / ExamResultOut / ClassScoreSummary
- 审计日志: AuditLogOut
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from decimal import Decimal


# ═══════════════════════════════════════════════════════
# 科目管理
# ═══════════════════════════════════════════════════════

class SubjectCreate(BaseModel):
    """创建/注册科目"""
    name: str = Field(..., min_length=1, max_length=50, description="科目名称（语文/数学/英语...）")
    code: str = Field(..., min_length=1, max_length=30, description="科目代码（chinese/math/english...）")
    full_score: Decimal = Field(default=Decimal("100.00"), description="满分值")
    sort_order: int = Field(default=0, description="排序权重")


class SubjectUpdate(BaseModel):
    """更新科目信息（所有字段可选）"""
    name: Optional[str] = Field(default=None, max_length=50)
    code: Optional[str] = Field(default=None, max_length=30)
    full_score: Optional[Decimal] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class SubjectOut(BaseModel):
    """科目响应"""
    id: int
    name: str
    code: str
    full_score: Decimal
    sort_order: int
    is_active: bool
    created_at: Optional[datetime] = None

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
    exam_date: Optional[datetime] = Field(default=None, description="考试日期")


class ExamUpdate(BaseModel):
    """更新考试信息"""
    name: Optional[str] = Field(default=None, max_length=200)
    exam_type: Optional[str] = None
    semester: Optional[str] = None
    exam_date: Optional[datetime] = None
    status: Optional[str] = None  # draft / published / archived


class ExamOut(BaseModel):
    """考试响应"""
    id: int
    name: str
    exam_type: str
    grade_id: int
    semester: str
    exam_date: Optional[datetime] = None
    status: str
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ExamItem(BaseModel):
    """考试列表项（精简版）"""
    id: int
    name: str
    exam_type: str
    semester: str
    exam_date: Optional[datetime] = None
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
    score: Optional[Decimal] = Field(default=None, description="得分（None 表示缺考）")
    is_absent: bool = Field(default=False, description="是否缺考")
    remark: Optional[str] = Field(default=None, max_length=200, description="备注")


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
    score: Optional[Decimal] = Field(default=None, description="得分")
    is_absent: bool = False
    class_rank: Optional[int] = None
    grade_rank: Optional[int] = None

    class Config:
        from_attributes = True


class StudentExamResult(BaseModel):
    """某学生在某次考试中的全科成绩"""
    student_id: int
    student_name: str
    class_id: int
    class_name: str
    total_score: Optional[Decimal] = Field(default=None, description="总分")
    avg_score: Optional[float] = Field(default=None, description="均分（剔除缺考科目）")
    class_rank: Optional[int] = Field(default=None, description="班级排名")
    grade_rank: Optional[int] = Field(default=None, description="年级排名")
    subjects: list[StudentScoreOut] = Field(default=[], description="各科成绩明细")


class ExamResultQuery(BaseModel):
    """考试结果查询参数"""
    exam_id: int = Field(..., description="考试 ID")
    class_id: Optional[int] = Field(default=None, description="班级 ID（可选，按班级过滤）")
    student_name: Optional[str] = Field(default=None, description="学生姓名（模糊搜索）")
    sort_by: str = Field(default="total_score_desc", description="排序: total_score_desc/asc")
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=200)


class ClassScoreSummary(BaseModel):
    """班级成绩汇总"""
    class_id: int
    class_name: str
    student_count: int = Field(..., description="参考人数")
    avg_total: Optional[float] = Field(default=None, description="总分均分")
    max_total: Optional[float] = Field(default=None, description="总分最高")
    min_total: Optional[float] = Field(default=None, description="总分最低")
    pass_rate: Optional[float] = Field(default=None, description="及格率（总分≥60%）")
    excellent_rate: Optional[float] = Field(default=None, description="优秀率（总分≥90%）")
    subjects: list["SubjectSummary"] = Field(default=[], description="各科统计")


class SubjectSummary(BaseModel):
    """单科班级统计"""
    subject_id: int
    subject_name: str
    full_score: Decimal
    avg_score: Optional[float] = None
    max_score: Optional[float] = None
    min_score: Optional[float] = None
    pass_rate: Optional[float] = None
    excellent_rate: Optional[float] = None


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
    old_score: Optional[Decimal] = None
    new_score: Optional[Decimal] = None
    action: str
    operator_id: Optional[int] = None
    operator_name: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AuditLogQuery(BaseModel):
    """审计日志查询参数"""
    exam_id: Optional[int] = None
    student_id: Optional[int] = None
    action: Optional[str] = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=200)
