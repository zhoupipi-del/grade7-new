"""
modules/research_ai/services_essay.py
======================================
AI 作文批改核心业务逻辑。

V2.1 修复（生产上线前审计）：
  - [P0] 评分维度按 subject + total_score_config 建唯一配置表，Prompt/后端验证共用
  - [P0] 不发送 student_name 给 LLM（隐私清洗），prompt 中用匿名占位符
  - [P0] AI 返回分数后端校验：维度之和=total_score，total_score <= total_score_config
  - [P1] LLM 业务校验失败自动重试一次，第二次仍失败才标记 error
  - 语文 / 英语双模式
  - 同步调用 LLM（temperature=0.3 保证评分稳定）
  - AI 边界：结果仅为"初评"，最终研判权归教师
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from modules.research_ai.llm_client import (
    LLMError,
    LLMTransportError,
    chat_json,
    sanitize_student_info,
)
from modules.research_ai.models_essay import EssayGradeRecord
from modules.research_ai.schemas import EssayLLMResult

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════
# 评分维度配置（唯一事实来源 — Prompt、后端校验、前端共用）
# ════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class ScoreDimension:
    key: str
    label_zh: str
    label_en: str
    max_score: int


@dataclass(frozen=True)
class RubricConfig:
    subject: str          # "chinese" | "english"
    total: int            # 卷面总分
    dimensions: tuple     # tuple of ScoreDimension

    @property
    def dim_max_sum(self) -> int:
        return sum(d.max_score for d in self.dimensions)

    def dimension_keys(self) -> list[str]:
        return [d.key for d in self.dimensions]

    def get_dim(self, key: str) -> ScoreDimension | None:
        for d in self.dimensions:
            if d.key == key:
                return d
        return None


# ── 语文维度定义 ──
_CN_BASE = lambda content, expr, struct, hand, dev: (
    ScoreDimension("content", "内容", "Content", content),
    ScoreDimension("expression", "表达", "Expression", expr),
    ScoreDimension("structure", "结构", "Structure", struct),
    ScoreDimension("handwriting", "书写", "Handwriting", hand),
    ScoreDimension("development", "发展等级", "Development", dev),
)

# ── 英语维度定义 ──
_EN_BASE = lambda content, lang_acc, vocab_syn, org, hand: (
    ScoreDimension("content", "内容", "Content", content),
    ScoreDimension("language_accuracy", "语言准确性", "Language Accuracy", lang_acc),
    ScoreDimension("vocabulary_syntax", "词汇句式", "Vocabulary & Syntax", vocab_syn),
    ScoreDimension("organization", "组织结构", "Organization", org),
    ScoreDimension("handwriting", "书写", "Handwriting", hand),
)

# ── 唯一评分配置表 ──
RUBRIC_CONFIGS: dict[tuple[str, int], RubricConfig] = {
    # 语文 50分：内容20+表达20+书写5+发展5 = 50（无独立结构维度，合并到表达）
    ("chinese", 50): RubricConfig("chinese", 50, _CN_BASE(20, 20, 0, 5, 5)),
    # 语文 60分：内容20+表达20+结构0(合并)+书写5+发展15 = 60
    ("chinese", 60): RubricConfig("chinese", 60, _CN_BASE(20, 20, 0, 5, 15)),
    # 语文 40分：内容15+表达15+书写5+发展5 = 40
    ("chinese", 40): RubricConfig("chinese", 40, _CN_BASE(15, 15, 0, 5, 5)),
    # 语文 100分：内容30+表达30+结构15+书写10+发展15 = 100
    ("chinese", 100): RubricConfig("chinese", 100, _CN_BASE(30, 30, 15, 10, 15)),

    # 英语 50分：内容15+语言15+词汇10+组织5+书写5 = 50
    ("english", 50): RubricConfig("english", 50, _EN_BASE(15, 15, 10, 5, 5)),
    # 英语 60分：内容18+语言18+词汇12+组织7+书写5 = 60
    ("english", 60): RubricConfig("english", 60, _EN_BASE(18, 18, 12, 7, 5)),
    # 英语 40分：内容12+语言12+词汇8+组织4+书写4 = 40
    ("english", 40): RubricConfig("english", 40, _EN_BASE(12, 12, 8, 4, 4)),
    # 英语 100分：内容30+语言25+词汇20+组织15+书写10 = 100
    ("english", 100): RubricConfig("english", 100, _EN_BASE(30, 25, 20, 15, 10)),
}


def get_rubric_config(subject: str, total: int) -> RubricConfig:
    """
    获取评分配置。[V2.1.1] 未知组合直接 KeyError，不静默 fallback，
    防止代码漂移导致卷面总分与 rubric 不一致。
    """
    try:
        return RUBRIC_CONFIGS[(subject, total)]
    except KeyError:
        raise KeyError(
            f"未找到评分配置：subject={subject!r}, total={total}；"
            f"有效值：{sorted({(s, t) for s, t in RUBRIC_CONFIGS if s == subject})}"
        ) from None


# 评分标准文本（Prompt 用）
RUBRIC_TEXTS: dict[str, dict[int, str]] = {
    "chinese": {
        50: "中考语文作文评分标准（50分制）：内容（20分）立意明确、内容充实；表达（20分）文体规范、语言流畅；书写（5分）卷面整洁；发展等级（5分）思想深刻、有创意。",
        60: "中考语文作文评分标准（60分制）：内容（20分）审题准确、立意深刻；表达（20分）文体鲜明、结构严谨、语言流畅；书写（5分）卷面整洁；发展等级（15分）深刻、丰富、有文采、有创意。",
        40: "语文作文评分标准（40分制）：内容（15分）、表达（15分）、书写（5分）、发展等级（5分）。",
        100: "语文作文评分标准（100分制）：内容（30分）、表达（30分）、结构（15分）、书写（10分）、发展等级（15分）。",
    },
    "english": {
        50: "中考英语作文评分标准（50分制）：内容（15分）要点齐全；语言准确性（15分）语法正确；词汇句式（10分）词汇丰富；组织结构（5分）连贯；书写（5分）整洁。",
        60: "中考英语作文评分标准（60分制）：内容（18分）覆盖所有要点；语言准确性（18分）时态语态正确；词汇句式（12分）复合句和高级句式；组织结构（7分）逻辑连贯；书写（5分）工整。",
        40: "English writing rubric (40pts): Content 12, Language Accuracy 12, Vocabulary & Grammar 8, Organization 4, Handwriting 4.",
        100: "English writing rubric (100pts): Content 30, Language Accuracy 25, Vocabulary & Sentence Structure 20, Organization 15, Handwriting 10.",
    },
}


def get_rubric_text(subject: str, total: int) -> str:
    return RUBRIC_TEXTS.get(subject, RUBRIC_TEXTS["chinese"]).get(
        total, RUBRIC_TEXTS[subject][60]
    )


# ════════════════════════════════════════════════════════════
# Prompt 构建
# ════════════════════════════════════════════════════════════

def _build_system_prompt(is_en: bool) -> str:
    if is_en:
        return (
            "You are an experienced middle school English teacher in China, very familiar "
            "with the 中考 English writing rubric. You grade essays fairly and provide "
            "detailed, actionable feedback. You MUST return a valid JSON object only — "
            "no markdown, no explanations outside JSON. Respond in English for essay "
            "feedback and refined version, but include a Chinese summary "
            "(chinese_summary field). Use temperature 0.3 for scoring consistency."
        )
    return (
        "你是一位资深初中语文教师，熟悉中考作文评分标准，批改公正、细致、有建设性。"
        "你必须只返回一个合法的 JSON 对象——不要 markdown 代码块、不要 JSON 以外的解释文字。"
        "所有评语用中文。"
    )


def _build_dimension_schema(cfg: RubricConfig, is_en: bool) -> str:
    """根据评分配置生成 prompt 中的维度 schema 描述。"""
    parts = []
    for d in cfg.dimensions:
        if d.max_score == 0:
            continue  # 分值为0的维度不出现在 prompt 中（如语文50/60的结构合并到表达）
        label = d.label_en if is_en else d.label_zh
        parts.append(f'"{d.key}": <0-{d.max_score}>  // {label}，满分{d.max_score}')
    return ",\n    ".join(parts)


def _build_user_prompt(
    *,
    grade: str,
    total: int,
    prompt: str,
    essay: str,
    rubric: str,
    is_en: bool,
) -> str:
    cfg = get_rubric_config("english" if is_en else "chinese", total)
    dim_schema = _build_dimension_schema(cfg, is_en)

    # 过滤掉 max_score=0 的维度，得到有效维度列表
    valid_dims = [d for d in cfg.dimensions if d.max_score > 0]
    dim_sum = sum(d.max_score for d in valid_dims)

    anno_desc = (
        '"annotations": [{"quote": "original sentence", '
        '"type": "highlight|issue|suggestion", '
        '"comment": "comment", "suggestion": "how to improve"}]'
        if is_en
        else '"annotations": [{"quote": "引用原文", '
        '"type": "highlight|issue|suggestion", '
        '"comment": "批注", "suggestion": "修改建议"}]'
    )
    grammar_schema = (
        ',\n  "grammar_errors": [{"original": "wrong sentence", '
        '"error_type": "tense/spelling/article/plural etc", '
        '"explanation": "why wrong (Chinese)", "correction": "correct version"}]'
        if is_en
        else ""
    )
    en_summary_field = '\n  "chinese_summary": "<中文概要100字内>",' if is_en else ""

    return f"""Please grade the following {'English' if is_en else 'Chinese'} essay according to the given rubric.

【Grade】{grade}
【Total Score】{total}

【Essay Prompt】
{prompt}

【Scoring Rubric】
{rubric}

【Student Essay】
{essay}

Return a JSON with EXACTLY these fields:
{{
  "total_score": <number, must equal sum of dimensions and not exceed {total}>,
  "grade_label": "<brief grade e.g. A/B/C or 优秀/良好/及格/待提高>",
  "dimensions": {{
    {dim_schema}
  }},
  {anno_desc},
  "overall_comment": "<{'overall comment in English' if is_en else '总体评语，中文，300字以内'}>",{en_summary_field}
  "refined_essay": "<polished version preserving student voice and structure — NOT a complete rewrite. {'In English.' if is_en else '中文。'}>",
  "improvement_tips": ["<tip 1>", "<tip 2>", "<tip 3>", "<tip 4>", "<tip 5>"]{grammar_schema}
}}

Rules:
1. The sum of all dimension scores MUST equal total_score, and total_score MUST NOT exceed {total}.
   The valid dimensions and their maximum scores are:
   {', '.join(f'{d.key}={d.max_score}' for d in valid_dims)}
   (sum of max scores = {dim_sum})
2. annotations should reference specific sentences from the essay.
3. refined_essay should be a polished version of the student's own essay.
4. Be encouraging but honest. Point out specific issues with concrete suggestions.
5. Return ONLY the JSON object."""


# ════════════════════════════════════════════════════════════
# 业务校验
# ════════════════════════════════════════════════════════════

class EssayValidationError(ValueError):
    """AI 返回的作文评分数据业务校验失败。"""


def validate_essay_result(
    data: dict[str, Any],
    cfg: RubricConfig,
) -> None:
    """
    校验 AI 返回的评分数据业务正确性。
    不合法则抛 EssayValidationError。
    """
    total = cfg.total

    # 1. total_score 存在性和范围
    ai_total = data.get("total_score")
    if ai_total is None:
        raise EssayValidationError("AI 返回缺少 total_score")
    if not isinstance(ai_total, (int, float)):
        raise EssayValidationError(f"total_score 不是数字: {type(ai_total)}")
    if ai_total < 0 or ai_total > total:
        raise EssayValidationError(
            f"total_score={ai_total} 超出范围 [0, {total}]"
        )

    # 2. dimensions 存在性
    dims = data.get("dimensions")
    if not isinstance(dims, dict):
        raise EssayValidationError("dimensions 缺失或不是对象")

    # 3. 逐维度校验范围 + 求和
    dim_sum = 0
    for d in cfg.dimensions:
        if d.max_score == 0:
            continue
        val = dims.get(d.key)
        if val is None:
            raise EssayValidationError(f"维度 {d.key} 缺失")
        if not isinstance(val, (int, float)):
            raise EssayValidationError(f"维度 {d.key} 不是数字: {type(val)}")
        if val < 0 or val > d.max_score:
            raise EssayValidationError(
                f"维度 {d.key}={val} 超出范围 [0, {d.max_score}]"
            )
        dim_sum += val

    # 4. 维度之和必须等于 total_score
    if dim_sum != ai_total:
        raise EssayValidationError(
            f"维度之和({dim_sum}) != total_score({ai_total})"
        )

    # 5. 必填字段
    for field in ("overall_comment", "grade_label"):
        if not data.get(field):
            raise EssayValidationError(f"必填字段 {field} 为空")


# ════════════════════════════════════════════════════════════
# 主服务
# ════════════════════════════════════════════════════════════

async def grade_essay(db: AsyncSession, record_id: int) -> None:
    """批改作文并回写结果（同步 API 调用，30-60 秒）。"""
    rec = await db.get(EssayGradeRecord, record_id)
    if not rec:
        return

    is_en = rec.subject == "english"
    cfg = get_rubric_config(rec.subject, rec.total_score_config)
    rubric = rec.rubric or get_rubric_text(rec.subject, rec.total_score_config)
    system_prompt = _build_system_prompt(is_en)

    # [V2.1.1 隐私] 真正调用 sanitize_student_info()，此前函数定义了但从未调用。
    # 对 essay_prompt / essay_text / rubric 做清洗；
    # 如果数据库中有 student_name，额外做定向替换。
    clean_prompt = sanitize_student_info(rec.essay_prompt)
    clean_essay = sanitize_student_info(rec.essay_text)
    clean_rubric = sanitize_student_info(rubric)
    if rec.student_name:
        # 把正文中可能出现的学生姓名替换为 [学生]
        for name in str(rec.student_name).split():
            if name:
                clean_prompt = clean_prompt.replace(name, "[学生]")
                clean_essay = clean_essay.replace(name, "[学生]")
                clean_rubric = clean_rubric.replace(name, "[学生]")

    # [V2.1.2 P0] student_id 精确清洗：数据库已知的学生ID做精确替换。
    # 兜底正则只覆盖 8-12 位学号；此处覆盖任何形态的已知 student_id，
    # 即使不足 8 位或格式异常也能保证不把学号发给 LLM。
    if rec.student_id is not None:
        sid = str(rec.student_id).strip()
        if sid:
            clean_prompt = clean_prompt.replace(sid, "[学号已隐去]")
            clean_essay = clean_essay.replace(sid, "[学号已隐去]")
            clean_rubric = clean_rubric.replace(sid, "[学号已隐去]")

    user_prompt = _build_user_prompt(
        grade=rec.grade,
        total=rec.total_score_config,
        prompt=clean_prompt,
        essay=clean_essay,
        rubric=clean_rubric,
        is_en=is_en,
    )

    # [P1] 业务校验失败重试一次
    max_attempts = 2
    for attempt in range(1, max_attempts + 1):
        try:
            data, usage, _elapsed = await chat_json(
                system_prompt, user_prompt, temperature=0.3
            )

            # [V2.1.1] 先用 Pydantic EssayLLMResult 做结构校验
            # 此前 EssayLLMResult 定义了但从未使用，导致 annotations 类型错误等
            # 可能直接炸在 FastAPI response validation 阶段。
            try:
                parsed = EssayLLMResult(**data)
            except Exception as struct_err:
                logger.warning(
                    "[EssayGrader] record=%s 结构校验失败(第%s次): %s",
                    record_id, attempt, struct_err,
                )
                if attempt < max_attempts:
                    user_prompt += (
                        f"\n\n【重要纠错】你上次返回的JSON结构有误：{struct_err}。"
                        f"请确保 annotations 是数组、dimensions 是对象、"
                        f"improvement_tips 是字符串数组，并修正后重新返回。"
                    )
                    continue
                raise EssayValidationError(f"JSON结构校验失败：{struct_err}") from struct_err

            # 结构校验通过后，用 dump 后的干净数据做业务校验
            data = parsed.model_dump()
            validate_essay_result(data, cfg)

            # 校验通过，落库
            rec.ai_total_score = data.get("total_score")
            rec.ai_grade_label = data.get("grade_label")
            rec.ai_dimensions = data.get("dimensions")
            rec.ai_annotations = data.get("annotations", [])
            rec.ai_grammar_errors = data.get("grammar_errors") if is_en else None
            rec.ai_comment = data.get("overall_comment")
            rec.ai_chinese_summary = (
                data.get("chinese_summary") if is_en else None
            )
            rec.ai_refined_essay = data.get("refined_essay")
            rec.ai_tips = data.get("improvement_tips", [])
            rec.ai_raw_json = data
            rec.prompt_tokens = usage.get("prompt_tokens")
            rec.completion_tokens = usage.get("completion_tokens")
            logger.info(
                "[EssayGrader] record=%s 批改完成 score=%s/%s (attempt %s)",
                record_id, rec.ai_total_score, rec.total_score_config, attempt,
            )
            break

        except EssayValidationError as ve:
            logger.warning(
                "[EssayGrader] record=%s 业务校验失败(第%s次): %s",
                record_id, attempt, ve,
            )
            if attempt < max_attempts:
                # 在 prompt 中追加纠错提示后重试
                user_prompt += (
                    f"\n\n【重要纠错】你上次返回的数据有以下问题，请修正后重新返回：{ve}。"
                    f"请严格确保各维度分数之和等于 total_score，且不超过卷面总分{rec.total_score_config}。"
                )
                continue
            # 第二次仍失败
            rec.ai_comment = f"AI 返回数据校验失败：{ve}"
            rec.ai_grade_label = "ERROR"

        except (LLMError, LLMTransportError) as e:
            logger.exception("[EssayGrader] record=%s AI 批改失败", record_id)
            rec.ai_comment = f"AI 批改失败：{e}"
            rec.ai_grade_label = "ERROR"
            break  # 传输/配置错误不重试

    db.add(rec)
    await db.commit()
