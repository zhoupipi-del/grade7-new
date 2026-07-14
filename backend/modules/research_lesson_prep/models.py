"""
research_lesson_prep/models.py — 集体备课协同编辑引擎

物理表:
  1. research_lesson_plans    — 备课主案表 (定稿与主干)
  2. research_plan_versions   — 版本快照表 (流式版本控制)
  3. research_plan_reviews    — 协同评审批注表

状态机:
  DRAFT → COLLECTIVE_REVIEW → ADMIN_APPROVE → PUBLISHED
  (任一非PUBLISHED状态均可回退至DRAFT)
"""

from core.models import Base, SchoolMixin, get_local_now
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

# ──────────────────────────────────────────────
# 状态枚举常量
# ──────────────────────────────────────────────
STATUS_DRAFT = "draft"  # 主备手稿
STATUS_COLLECTIVE_REVIEW = "review"  # 集体协同评议
STATUS_ADMIN_APPROVE = "approved"  # 组长定稿审核
STATUS_PUBLISHED = "published"  # 全校引用

VALID_TRANSITIONS = {
    STATUS_DRAFT: [STATUS_COLLECTIVE_REVIEW],
    STATUS_COLLECTIVE_REVIEW: [STATUS_ADMIN_APPROVE, STATUS_DRAFT],
    STATUS_ADMIN_APPROVE: [STATUS_PUBLISHED, STATUS_DRAFT],
    STATUS_PUBLISHED: [],  # 终态, 不可逆
}

# 课型
LESSON_TYPE_NEW = "new"  # 新授课
LESSON_TYPE_REVIEW = "review"  # 复习课
LESSON_TYPE_EXAM = "exam"  # 考试讲评
LESSON_TYPE_TEST = "test"  # 测试课
LESSON_TYPE_ACTIVITY = "activity"  # 活动课


class ResearchLessonPlan(Base, SchoolMixin):
    """集体备课主案表 — 一份教案的主干元信息 + 状态机控制"""

    __tablename__ = "research_lesson_plans"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    # ── 教案元信息 ──
    title = Column(String(200), nullable=False, comment="教案标题")
    description = Column(Text, comment="教案简介/教学说明")
    subject_code = Column(String(20), nullable=False, comment="学科代码: chinese/math/english/...")
    grade_level = Column(String(20), nullable=False, comment="年级: grade_7/grade_8/...")
    lesson_type = Column(
        String(20),
        default=LESSON_TYPE_NEW,
        comment="课型: new/review/exam/test/activity",
    )
    duration = Column(Integer, default=1, comment="课时数(默认1课时)")
    tags = Column(JSON, default=list, comment='标签: ["函数", "大单元", "跨学科"]')

    # ── Markdown+LaTeX 教案正文 (Wings 3.1 AI全息备课仓) ──
    content_markdown = Column(Text, comment="Markdown+LaTeX 教案正文 (协同编辑的完整文本内容)")

    # ── AI学情逆向处方 (Wings 3.1 从error_funnel逆向注入) ──
    ai_bias_prescription = Column(
        Text, comment="AI学情逆向处方 (DeepSeek从错题断层逆向生成的教学偏方)"
    )
    ai_prescription_generated_at = Column(DateTime, comment="AI处方最后生成时间")

    # ── 状态机 ──
    status = Column(
        String(20),
        default=STATUS_DRAFT,
        nullable=False,
        comment="状态: draft/review/approved/published",
    )
    status_updated_at = Column(DateTime, comment="状态最后变更时间")
    status_updated_by = Column(BigInteger, comment="状态变更操作人 user_id")
    reject_reason = Column(Text, comment="打回原因(回退至draft时填写)")

    # ── 版本控制 ──
    current_version = Column(Integer, default=1, nullable=False, comment="当前版本号(递增)")
    published_version = Column(Integer, comment="已发布版本号(NULL=未发布)")

    # ── 引用统计 ──
    reference_count = Column(Integer, default=0, comment="被其他教师引用次数")
    fork_count = Column(Integer, default=0, comment="被Fork派生次数")

    # ── 人员 ──
    creator_id = Column(BigInteger, nullable=False, comment="主备人 user_id")
    grade_leader_id = Column(BigInteger, comment="教研组长 user_id (审核人)")

    # ── 关联 ──
    forked_from_id = Column(BigInteger, comment="Fork来源 plan_id (NULL=原创)")
    chapter_id = Column(BigInteger, comment="关联章节ID (如有教材管理模块)")

    created_at = Column(DateTime, default=get_local_now)
    updated_at = Column(DateTime, default=get_local_now, onupdate=get_local_now)

    __table_args__ = (
        Index("idx_rlp_school_status", "school_id", "status"),
        Index("idx_rlp_school_subject", "school_id", "subject_code", "grade_level"),
        Index("idx_rlp_creator", "school_id", "creator_id"),
        Index("idx_rlp_published", "school_id", "published_version"),
    )


class ResearchPlanVersion(Base, SchoolMixin):
    """备课版本快照 — 每次保存创建一个不可变版本, 供回溯和对比"""

    __tablename__ = "research_plan_versions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    plan_id = Column(BigInteger, nullable=False, comment="关联 research_lesson_plans.id")
    version_number = Column(Integer, nullable=False, comment="版本号(从1递增)")
    editor_id = Column(BigInteger, nullable=False, comment="编辑人 user_id")

    # ── 结构化教案内容 ──
    content_json = Column(
        JSON,
        nullable=False,
        comment=(
            "结构化教案: {"
            "teaching_objectives:[], key_points:[], difficulties:[], "
            "teaching_methods:[], teaching_process:[{phase,duration,content,activities}], "
            "homework:[], blackboard_design, reflection"
            "}"
        ),
    )

    # ── Markdown正文快照 (Wings 3.1 AI全息备课仓) ──
    content_markdown = Column(
        Text, comment="Markdown+LaTeX 正文快照 (每次保存时锁定一份不可变副本)"
    )

    # ── 变更说明 ──
    change_log = Column(Text, comment="本版本变更说明 (编辑人填写)")
    is_major = Column(Boolean, default=False, comment="是否重大修订 (影响版本号大跳)")

    created_at = Column(DateTime, default=get_local_now)

    __table_args__ = (
        UniqueConstraint("plan_id", "version_number", "school_id", name="uk_rpv_plan_ver_school"),
        Index("idx_rpv_plan", "school_id", "plan_id", "version_number"),
    )


class ResearchPlanReview(Base, SchoolMixin):
    """协同评审批注 — 教研组成员对特定版本教案特定段落的批注"""

    __tablename__ = "research_plan_reviews"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    plan_id = Column(BigInteger, nullable=False, comment="关联 research_lesson_plans.id")
    version_number = Column(Integer, nullable=False, comment="批注针对的版本号")
    reviewer_id = Column(BigInteger, nullable=False, comment="批注人 user_id")

    # ── 批注定位 ──
    target_section = Column(
        String(100),
        nullable=False,
        comment="指向教案组件: teaching_objectives / teaching_process[0] / homework / ...",
    )
    target_anchor = Column(String(200), comment="锚点文本 (批注所引用的原文片段)")

    # ── 批注内容 ──
    comment = Column(Text, nullable=False, comment="批注正文")
    severity = Column(
        String(20),
        default="suggestion",
        comment="严重度: suggestion(建议) / issue(问题) / critical(严重缺陷)",
    )

    # ── 解决状态 ──
    is_resolved = Column(Boolean, default=False, comment="是否已解决")
    resolved_by = Column(BigInteger, comment="解决人 user_id")
    resolved_at = Column(DateTime, comment="解决时间")
    resolution_note = Column(Text, comment="解决说明")

    # ── 回复链 ──
    parent_review_id = Column(BigInteger, comment="父批注ID (回复链, NULL=顶级批注)")

    created_at = Column(DateTime, default=get_local_now)

    __table_args__ = (
        Index("idx_rpr_plan_ver", "school_id", "plan_id", "version_number"),
        Index("idx_rpr_resolved", "school_id", "plan_id", "is_resolved"),
        Index("idx_rpr_reviewer", "school_id", "reviewer_id"),
    )
