"""
modules/research_ai/schemas.py
==============================
教研 AI 工具 Pydantic v2 schemas。

V2.1 修复（生产上线前审计）：
  - [P1] 移除假 concurrency 字段（UI可选但实际不控制批次并发）
  - [P0] EssayReviewIn.final_score 上限动态校验（不能靠固定 0-100）
  - [P1] 新增 LLM 结果业务校验 schema（EssayLLMResult / LessonLLMResult / HomeworkLLMResult）
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ════════════════════════════════════════════════════════════
# 批量教案生成
# ════════════════════════════════════════════════════════════

class LessonItemIn(BaseModel):
    """单个课题输入。"""

    subject: str = Field(..., max_length=50, description="学科")
    textbook: Optional[str] = Field(None, max_length=100, description="教材版本")
    grade: str = Field(..., max_length=50, description="年级")
    unit: Optional[str] = Field(None, max_length=200, description="单元/章节")
    topic: str = Field(..., max_length=200, description="课题")
    periods: int = Field(1, ge=1, le=6, description="课时数")
    key_point: Optional[str] = Field(None, max_length=500, description="教学重点")
    diff_point: Optional[str] = Field(None, max_length=500, description="教学难点")

    @field_validator("subject", "grade", "topic")
    @classmethod
    def _not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("不能为空")
        return v.strip()


class LessonBatchCreateIn(BaseModel):
    """批量教案生成请求。"""

    task_name: str = Field(..., max_length=200, description="任务名称")
    items: list[LessonItemIn] = Field(..., min_length=1, max_length=50)


class LessonItemOut(BaseModel):
    """单篇教案输出。"""

    model_config = {"from_attributes": True}

    id: int
    subject: str
    textbook: Optional[str] = None
    grade: str
    unit: Optional[str] = None
    topic: str
    periods: int
    key_point: Optional[str] = None
    diff_point: Optional[str] = None
    status: str
    file_path: Optional[str] = None
    file_name: Optional[str] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    error_msg: Optional[str] = None
    elapsed_sec: Optional[int] = None
    created_at: datetime
    finished_at: Optional[datetime] = None


class LessonTaskOut(BaseModel):
    """批量任务输出。"""

    model_config = {"from_attributes": True}

    id: int
    task_name: str
    status: str
    total_count: int
    success_count: int
    fail_count: int
    created_at: datetime
    finished_at: Optional[datetime] = None
    items: list[LessonItemOut] = Field(default_factory=list)


# ════════════════════════════════════════════════════════════
# AI 作文批改
# ════════════════════════════════════════════════════════════

class EssayGradeIn(BaseModel):
    """作文批改请求（同步）。"""

    subject: str = Field("chinese", pattern="^(chinese|english)$")
    grade: str = Field("八年级", max_length=20)
    total_score_config: Literal[40, 50, 60, 100] = Field(
        60, description="卷面总分配置，仅允许 40/50/60/100"
    )
    student_id: Optional[int] = None
    student_name: Optional[str] = Field(None, max_length=100)
    essay_prompt: str = Field(..., min_length=2, max_length=5000)
    essay_text: str = Field(..., min_length=10, max_length=20000)
    rubric: Optional[str] = Field(None, max_length=3000)


class EssayReviewIn(BaseModel):
    """教师复核：可改分、写评语。final_score 上限在 router 中动态校验。"""

    final_score: Optional[int] = Field(None, ge=0, description="教师最终分数（上限=卷面总分，后端校验）")
    teacher_comment: Optional[str] = Field(None, max_length=5000)


class EssayGradeOut(BaseModel):
    """作文批改记录输出。"""

    model_config = {"from_attributes": True}

    id: int
    subject: str
    grade: str
    total_score_config: int
    student_name: Optional[str] = None
    ai_total_score: Optional[int] = None
    ai_grade_label: Optional[str] = None
    ai_dimensions: Optional[dict[str, Any]] = None
    ai_annotations: Optional[list[dict[str, Any]]] = None
    ai_grammar_errors: Optional[list[dict[str, Any]]] = None
    ai_comment: Optional[str] = None
    ai_chinese_summary: Optional[str] = None
    ai_refined_essay: Optional[str] = None
    ai_tips: Optional[list[str]] = None
    review_status: str
    final_score: Optional[int] = None
    teacher_comment: Optional[str] = None
    created_at: datetime
    reviewed_at: Optional[datetime] = None


class EssayHistoryOut(BaseModel):
    """作文历史列表项（精简）。"""

    model_config = {"from_attributes": True}

    id: int
    subject: str
    grade: str
    student_name: Optional[str] = None
    ai_total_score: Optional[int] = None
    total_score_config: int
    review_status: str
    final_score: Optional[int] = None
    created_at: datetime


# ════════════════════════════════════════════════════════════
# 分层作业设计
# ════════════════════════════════════════════════════════════

class HomeworkCreateIn(BaseModel):
    """分层作业生成请求。"""

    subject: str = Field(..., max_length=50, description="学科")
    grade: str = Field(..., max_length=50, description="年级")
    textbook: Optional[str] = Field(None, max_length=100, description="教材版本")
    unit: Optional[str] = Field(None, max_length=200, description="章节/单元")
    topic: str = Field(..., max_length=200, description="本节课主题")
    knowledge_points: Optional[str] = Field(
        None, max_length=1000, description="知识点，逗号/换行分隔"
    )
    class_profile: Optional[str] = Field(
        None, max_length=2000, description="班级学情描述"
    )
    question_counts: str = Field(
        "8-5-3", max_length=20, description="基础-提高-拓展题量"
    )
    difficulty_distribution: str = Field(
        "4-4-2", max_length=20, description="易-中-难比例"
    )
    estimated_minutes: int = Field(40, ge=10, le=180)
    include_answers: bool = Field(True, description="是否附答案")
    extra_requirements: Optional[str] = Field(None, max_length=2000)

    @field_validator("subject", "grade", "topic")
    @classmethod
    def _not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("不能为空")
        return v.strip()

    @field_validator("question_counts")
    @classmethod
    def _validate_counts(cls, v: str) -> str:
        parts = v.split("-")
        if len(parts) != 3:
            raise ValueError("题量格式必须为 基础-提高-拓展，如 8-5-3")
        for p in parts:
            if not p.isdigit() or int(p) < 0:
                raise ValueError("题量必须为非负整数")
        if sum(int(p) for p in parts) < 3:
            raise ValueError("总题量至少 3 题")
        return v

    @field_validator("difficulty_distribution")
    @classmethod
    def _validate_dist(cls, v: str) -> str:
        parts = v.split("-")
        if len(parts) != 3:
            raise ValueError("难度比例格式必须为 易-中-难，如 4-4-2")
        for p in parts:
            if not p.isdigit() or int(p) < 0:
                raise ValueError("难度比例必须为非负整数")
        return v


class HomeworkOut(BaseModel):
    """分层作业记录输出。"""

    model_config = {"from_attributes": True}

    id: int
    subject: str
    grade: str
    textbook: Optional[str] = None
    unit: Optional[str] = None
    topic: str
    knowledge_points: Optional[str] = None
    class_profile: Optional[str] = None
    question_counts: str
    difficulty_distribution: str
    estimated_minutes: int
    include_answers: bool
    extra_requirements: Optional[str] = None
    status: str
    file_path: Optional[str] = None
    file_name: Optional[str] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    error_msg: Optional[str] = None
    elapsed_sec: Optional[int] = None
    created_at: datetime
    finished_at: Optional[datetime] = None


# ════════════════════════════════════════════════════════════
# LLM 结果业务校验 Schemas（V2.1 新增）
# ════════════════════════════════════════════════════════════

class LessonStage(BaseModel):
    """教案教学过程单个环节。"""
    环节: str = Field(..., min_length=1)
    时长: str = Field(..., min_length=1)
    教师活动: list[str] = Field(default_factory=list)
    学生活动: list[str] = Field(default_factory=list)
    设计意图: str = ""


class LessonLLMResult(BaseModel):
    """
    教案 LLM 返回结果校验。
    业务规则：
      - 教学过程各环节时长之和 = periods × 45 分钟
      - 数学学科核心素养目标 3~4 个
    """
    model_config = {"extra": "ignore"}

    课标依据: Any = ""
    教学目标: dict[str, str] = Field(default_factory=dict)
    教学重点: str = ""
    教学难点: str = ""
    教学方法: str = ""
    教学准备: dict[str, str] = Field(default_factory=dict)
    教学过程: list[LessonStage] = Field(default_factory=list)
    板书设计: str = ""
    作业布置: dict[str, str] = Field(default_factory=dict)
    教学反思提示: list[str] = Field(default_factory=list)

    def total_minutes(self) -> int:
        """从'时长'字段解析总分钟数（支持'5分钟'/'45min'/'1课时'等格式）。"""
        total = 0
        import re as _re
        for stage in self.教学过程:
            s = stage.时长
            m = _re.search(r'(\d+)', s)
            if m:
                total += int(m.group(1))
        return total

    def validate_business_rules(self, periods: int, subject: str) -> list[str]:
        """返回业务规则违规列表，空列表表示通过。"""
        errors: list[str] = []
        expected_minutes = periods * 45
        actual = self.total_minutes()
        if actual != expected_minutes:
            errors.append(
                f"教学过程总时长={actual}分钟，应为{periods}×45={expected_minutes}分钟"
            )
        if "数学" in subject:
            n_obj = len(self.教学目标)
            if n_obj < 3 or n_obj > 4:
                errors.append(f"数学核心素养目标应为3~4个，当前{n_obj}个")
        return errors


class HomeworkQuestion(BaseModel):
    """分层作业单题。"""
    model_config = {"extra": "ignore"}

    layer: str = ""
    number: int = 0
    question_type: str = ""
    content: str = ""
    options: Optional[list[str]] = None
    score: Optional[int] = None
    knowledge_point: str = ""
    answer: str = ""
    explanation: str = ""


class HomeworkLayer(BaseModel):
    """分层作业单层。"""
    model_config = {"extra": "ignore"}

    layer: str = ""
    layer_name: str = ""
    description: str = ""
    questions: list[HomeworkQuestion] = Field(default_factory=list)


class HomeworkLLMResult(BaseModel):
    """
    分层作业 LLM 返回结果校验。
    业务规则：
      - 三层题量严格匹配配置的 基础-提高-拓展
      - 选择题必须恰好 A/B/C/D 四个选项
    """
    model_config = {"extra": "ignore"}

    title: str = ""
    total_score: int = 100
    layers: list[HomeworkLayer] = Field(default_factory=list)
    teaching_notes: str = ""

    def validate_business_rules(
        self, expected_counts: tuple[int, int, int]
    ) -> list[str]:
        """返回业务规则违规列表。"""
        errors: list[str] = []
        layer_map = {l.layer: l for l in self.layers}
        expected_layers = ["basic", "intermediate", "advanced"]
        for i, key in enumerate(expected_layers):
            layer = layer_map.get(key)
            if not layer:
                errors.append(f"缺少{key}层")
                continue
            actual_count = len(layer.questions)
            if actual_count != expected_counts[i]:
                errors.append(
                    f"{key}层题量={actual_count}，应为{expected_counts[i]}"
                )
            # 选择题选项校验
            for q in layer.questions:
                if q.question_type == "choice":
                    # [V2.1.1] options=None 必须拒绝，此前漏口
                    if not q.options:
                        errors.append(
                            f"{key}层第{q.number}题是选择题但缺少选项(options为空)"
                        )
                        continue
                    if len(q.options) != 4:
                        errors.append(
                            f"{key}层第{q.number}题选择题选项数={len(q.options)}，应为4"
                        )
                        continue
                    # [V2.1.1] 校验四项确实是 A/B/C/D 开头
                    expected_prefixes = ("A", "B", "C", "D")
                    for idx, opt in enumerate(q.options):
                        opt_stripped = str(opt).strip()
                        if not opt_stripped or opt_stripped[0].upper() != expected_prefixes[idx]:
                            errors.append(
                                f"{key}层第{q.number}题第{idx+1}个选项应以"
                                f"'{expected_prefixes[idx]}'开头，实际为'{opt_stripped[:10]}'"
                            )
                            break
        return errors


class EssayLLMResult(BaseModel):
    """
    作文 LLM 返回结果校验（轻量结构校验，分数范围由 services_essay.validate_essay_result 做）。
    """
    model_config = {"extra": "ignore"}

    total_score: int
    grade_label: str = ""
    dimensions: dict[str, Any] = Field(default_factory=dict)
    annotations: list[dict[str, Any]] = Field(default_factory=list)
    overall_comment: str = ""
    refined_essay: str = ""
    improvement_tips: list[str] = Field(default_factory=list)
    grammar_errors: Optional[list[dict[str, Any]]] = None
    chinese_summary: Optional[str] = None



# ════════════════════════════════════════════════════════════
# V2.2 新功能：AI 试卷命制
# ════════════════════════════════════════════════════════════

class PaperCreateIn(BaseModel):
    """试卷命制请求。"""

    subject: str = Field(..., max_length=50, description="学科")
    grade: str = Field(..., max_length=50, description="年级")
    textbook: Optional[str] = Field(None, max_length=100, description="教材版本")
    unit: Optional[str] = Field(None, max_length=200, description="单元/章节")
    topic: str = Field(..., max_length=200, description="考查主题")
    knowledge_points: Optional[str] = Field(None, max_length=2000, description="知识点（逗号分隔）")
    # 选择题-填空题-解答题数量，如 "6-4-3"
    question_types: str = Field("6-4-3", max_length=50)
    total_score: int = Field(100, ge=50, le=150, description="卷面总分")
    difficulty: str = Field("4-4-2", max_length=20, description="易中难比例")
    include_answers: bool = Field(True, description="是否包含答案与解析")
    extra_requirements: Optional[str] = Field(None, max_length=2000)

    @field_validator("subject", "grade", "topic")
    @classmethod
    def _not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("不能为空")
        return v.strip()

    @field_validator("question_types")
    @classmethod
    def _validate_question_types(cls, v: str) -> str:
        parts = [p.strip() for p in str(v).split("-")]
        if len(parts) != 3 or not all(p.isdigit() for p in parts):
            raise ValueError("题型配置格式应为 选择-填空-解答，如 6-4-3")
        nums = [int(p) for p in parts]
        if any(n < 0 or n > 30 for n in nums):
            raise ValueError("每种题型题量应在 0-30 之间")
        if sum(nums) < 1:
            raise ValueError("总题量不能为 0")
        return "-".join(parts)

    @field_validator("difficulty")
    @classmethod
    def _validate_difficulty(cls, v: str) -> str:
        parts = [p.strip() for p in str(v).split("-")]
        if len(parts) != 3 or not all(p.isdigit() for p in parts):
            raise ValueError("难易比例格式应为 易-中-难，如 4-4-2")
        nums = [int(p) for p in parts]
        if any(n < 1 or n > 9 for n in nums):
            raise ValueError("难度比例每项应在 1-9 之间")
        if sum(nums) != 10:
            raise ValueError("难度比例三项之和应为 10（如 4-4-2 表示易:中:难=40:40:20）")
        return "-".join(parts)


class PaperOut(BaseModel):
    """试卷任务输出。"""

    model_config = {"from_attributes": True}

    id: int
    subject: str
    grade: str
    textbook: Optional[str] = None
    unit: Optional[str] = None
    topic: str
    knowledge_points: Optional[str] = None
    question_types: str
    total_score: int
    difficulty: str
    include_answers: bool
    # V2.2.1-final P1：补齐 extra_requirements，保证历史任务 retry 时
    # 前端能取回原额外要求，避免重试任务与原任务意图漂移
    extra_requirements: Optional[str] = None
    status: str
    file_path: Optional[str] = None
    file_name: Optional[str] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    error_msg: Optional[str] = None
    elapsed_sec: Optional[int] = None
    created_at: datetime
    finished_at: Optional[datetime] = None


class PaperQuestion(BaseModel):
    """试卷单题。"""

    model_config = {"extra": "ignore"}

    number: int = 0
    question_type: str = ""   # choice / blank / qa
    type_label: str = ""      # 选择题 / 填空题 / 解答题
    score: int = 0
    knowledge_point: str = ""
    difficulty: str = ""      # easy / medium / hard
    content: str = ""
    options: Optional[list[str]] = None
    answer: str = ""
    explanation: str = ""


class PaperLLMResult(BaseModel):
    """试卷 LLM 返回结果校验。业务规则见 validate_business_rules。"""

    model_config = {"extra": "ignore"}

    title: str = ""
    total_score: int = 0
    questions: list[PaperQuestion] = Field(default_factory=list)
    notes: str = ""   # 命题说明/难度分布说明

    def validate_business_rules(
        self,
        expected_counts: tuple[int, int, int],
        expected_total: int,
    ) -> list[str]:
        """返回业务规则违规列表（V2.2.1 P0 收紧）。

        新增拦截：
        - 未知 question_type（如 essay）→ 拒绝，杜绝 renderer 静默丢题造成卷面总分错误
        - 题号必须恰好为 1..N 连续且无重复（重复/跳号 → 拒绝）
        - 各题 score 必须为正整数（>0）
        - LLM 返回 total_score 必须等于期望卷面总分
        - 选择题 answer 必须为 A/B/C/D 之一
        """
        errors: list[str] = []
        by_type = {"choice": 0, "blank": 0, "qa": 0}
        score_sum = 0
        seen_numbers: set[int] = set()

        for q in self.questions:
            qtype = q.question_type
            # 未知题型：直接拒绝（renderer 只渲染 choice/blank/qa，未知题会静默消失）
            if qtype not in by_type:
                errors.append(f"第{q.number}题题型 '{qtype}' 不合法，仅支持 choice/blank/qa")
                continue
            by_type[qtype] += 1
            if q.number <= 0:
                errors.append(f"第{q.number}题题号非法（应为正整数）")
            if q.number in seen_numbers:
                errors.append(f"题号 {q.number} 重复")
            seen_numbers.add(q.number)

            score = q.score or 0
            if score <= 0:
                errors.append(f"第{q.number}题分值必须为正整数，当前 {q.score}")
            score_sum += score

            if qtype == "choice":
                if not q.options or len(q.options) != 4:
                    errors.append(f"第{q.number}题是选择题但选项数≠4")
                    continue
                expected_prefixes = ("A", "B", "C", "D")
                for idx, opt in enumerate(q.options):
                    s = str(opt).strip()
                    if not s or s[0].upper() != expected_prefixes[idx]:
                        errors.append(f"第{q.number}题第{idx+1}个选项应以'{expected_prefixes[idx]}'开头")
                        break
                ans = str(q.answer or "").strip().upper()
                if ans not in ("A", "B", "C", "D"):
                    errors.append(f"第{q.number}题选择题答案 '{q.answer}' 必须为 A/B/C/D 之一")
            if not q.content.strip():
                errors.append(f"第{q.number}题题干为空")

        # 题号连续性：合法题号集合必须恰为 {1..N}
        if seen_numbers and seen_numbers != set(range(1, len(self.questions) + 1)):
            errors.append(f"题号必须为 1..{len(self.questions)} 连续无重复，当前 {sorted(seen_numbers)}")

        for key, expected in zip(("choice", "blank", "qa"), expected_counts):
            if by_type[key] != expected:
                errors.append(f"{key}题数量={by_type[key]}，应为{expected}")
        if score_sum != expected_total:
            errors.append(f"各题分值之和={score_sum}，应为卷面总分{expected_total}")
        if self.total_score != expected_total:
            errors.append(f"LLM 返回 total_score={self.total_score}，应为{expected_total}")
        if not self.title.strip():
            errors.append("试卷标题为空")
        return errors


# ════════════════════════════════════════════════════════════
# V2.2 新功能：AI 学情分析报告
# ════════════════════════════════════════════════════════════

class AnalysisCreateIn(BaseModel):
    """学情分析请求。"""

    scope_name: str = Field(..., max_length=100, description="分析对象（班级/年级名称）")
    subject: str = Field(..., max_length=50, description="学科")
    grade: str = Field(..., max_length=50, description="年级")
    exam_name: Optional[str] = Field(None, max_length=200, description="考试名称")
    data_summary: str = Field(..., max_length=10000, description="学情数据摘要（分数段/知识点正确率等，不得含学生姓名学号）")
    analysis_focus: Optional[str] = Field(None, max_length=2000, description="关注点")

    @field_validator("scope_name", "subject", "grade", "data_summary")
    @classmethod
    def _not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("不能为空")
        return v.strip()


class AnalysisOut(BaseModel):
    """学情分析任务输出。"""

    model_config = {"from_attributes": True}

    id: int
    scope_name: str
    subject: str
    grade: str
    exam_name: Optional[str] = None
    data_summary: str
    analysis_focus: Optional[str] = None
    status: str
    file_path: Optional[str] = None
    file_name: Optional[str] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    error_msg: Optional[str] = None
    elapsed_sec: Optional[int] = None
    created_at: datetime
    finished_at: Optional[datetime] = None


class AnalysisLLMResult(BaseModel):
    """学情分析 LLM 返回结果校验。"""

    model_config = {"extra": "ignore"}

    overall_assessment: str = ""                       # 总体评估
    score_distribution: dict[str, Any] = Field(default_factory=dict)  # 分数段解读
    findings: list[str] = Field(default_factory=list)  # 关键发现
    knowledge_mastery: list[dict[str, Any]] = Field(default_factory=list)  # 知识点掌握
    student_stratification: list[dict[str, Any]] = Field(default_factory=list)  # 学生分层建议
    recommendations: list[str] = Field(default_factory=list)  # 教学建议

    def validate_business_rules(self) -> list[str]:
        """返回业务规则违规列表（V2.2.1 P1 收紧）。

        报告承诺的「分数段/知识点/分层」三块必须实际非空，
        不能只输出总体评估+建议就 PASS。
        """
        errors: list[str] = []
        if not self.overall_assessment.strip():
            errors.append("总体评估为空")
        if not self.score_distribution:
            errors.append("分数段解读（score_distribution）为空")
        if len(self.findings) < 1:
            errors.append("关键发现为空")
        if not self.knowledge_mastery:
            errors.append("知识点掌握（knowledge_mastery）为空")
        if not self.student_stratification:
            errors.append("学生分层建议（student_stratification）为空")
        if len(self.recommendations) < 3:
            errors.append(f"教学建议应至少3条，当前{len(self.recommendations)}条")
        return errors


# ════════════════════════════════════════════════════════════
# V2.2 新功能：AI 学生评语生成
# ════════════════════════════════════════════════════════════

class CommentStudentIn(BaseModel):
    """单个学生的评语输入。"""

    name: str = Field(..., max_length=50, description="学生姓名（存库显示，不发给 LLM）")
    keywords: Optional[str] = Field(None, max_length=500, description="表现关键词（课堂/作业/品德/进步/待改进）")

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("学生姓名不能为空或纯空白")
        return v.strip()


class CommentCreateIn(BaseModel):
    """学生评语生成请求。"""

    class_name: str = Field(..., max_length=100, description="班级名称")
    term: str = Field(..., max_length=100, description="学期")
    comment_type: str = Field("semester", max_length=50, description="semester学期评语/moral品德评语/parent家校沟通")
    students: list[CommentStudentIn] = Field(..., min_length=1, max_length=60)
    style: Optional[str] = Field(None, max_length=500, description="风格/字数要求")

    @field_validator("class_name", "term")
    @classmethod
    def _not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("不能为空")
        return v.strip()

    @field_validator("comment_type")
    @classmethod
    def _validate_type(cls, v: str) -> str:
        if v not in ("semester", "moral", "parent"):
            raise ValueError("comment_type 必须为 semester/moral/parent")
        return v


class CommentOut(BaseModel):
    """学生评语任务输出。"""

    model_config = {"from_attributes": True}

    id: int
    class_name: str
    term: str
    comment_type: str
    students: list[dict[str, Any]] = Field(default_factory=list)
    student_count: int
    style: Optional[str] = None
    status: str
    file_path: Optional[str] = None
    file_name: Optional[str] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    error_msg: Optional[str] = None
    elapsed_sec: Optional[int] = None
    created_at: datetime
    finished_at: Optional[datetime] = None


class CommentItem(BaseModel):
    """评语单条（LLM 输出，匿名编号）。"""

    model_config = {"extra": "ignore"}

    student_ref: str = ""   # "学生1" / "学生2"（匿名编号，回填时映射真实姓名）
    comment: str = ""


class CommentLLMResult(BaseModel):
    """评语 LLM 返回结果校验。"""

    model_config = {"extra": "ignore"}

    comments: list[CommentItem] = Field(default_factory=list)

    def validate_business_rules(self, expected_count: int) -> list[str]:
        """返回业务规则违规列表（V2.2.1 P0 收紧）。

        只校验条数不够——必须同时满足：
        - 条数 == expected_count
        - student_ref 恰好覆盖 学生1..学生N，无重复、无缺失、无多余
          （否则会把李四的评语错配到张三名下，或让某学生凭空消失）
        - 每条评语非空
        """
        errors: list[str] = []
        if len(self.comments) != expected_count:
            errors.append(f"评语条数={len(self.comments)}，应为{expected_count}")
        refs = [str(c.student_ref or "").strip() for c in self.comments]
        expected_refs = {f"学生{i}" for i in range(1, expected_count + 1)}
        seen: set[str] = set()
        for ref in refs:
            if not ref:
                errors.append("存在 student_ref 为空的评语")
                continue
            if ref in seen:
                errors.append(f"student_ref '{ref}' 重复")
            seen.add(ref)
            if ref not in expected_refs:
                errors.append(f"student_ref '{ref}' 超出名单范围（应为 学生1..学生{expected_count}）")
        missing = expected_refs - seen
        if missing:
            errors.append(f"缺少学生 {sorted(missing, key=lambda x: int(x.replace('学生', '')))} 的评语")
        for c in self.comments:
            if not c.comment.strip():
                errors.append(f"{c.student_ref} 评语为空")
        return errors
