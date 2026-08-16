"""
modules/research_ai/services_paper.py
======================================
AI 试卷命制核心业务逻辑。

流程：取任务 → 调 AI → 结构校验 → 业务规则校验（题量/分值/选项）→ 生成 docx → 回写。
- 选择题强制 A/B/C/D 四选项
- 各题分值之和必须等于卷面总分
- 输出 Word（试卷正文 + 答案与解析）
- Celery 异步（V2.2 新增）
"""
from __future__ import annotations

import logging
import os
import time

from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import get_local_now
from modules.research_ai.llm_client import LLMError, LLMTransportError, chat_json
from modules.research_ai.models_paper import PaperTask
from modules.research_ai.schemas import PaperLLMResult
from modules.research_ai.word_renderer import (
    HEI,
    SONG,
    add_heading,
    add_label_body,
    add_paragraph,
    fill_cell,
    make_table,
    new_document,
    safe_filename_part,
)

logger = logging.getLogger(__name__)

OUTPUT_DIR = os.environ.get(
    "RESEARCH_AI_OUTPUT_DIR", "/opt/wings3/shared/uploads/research_ai"
)
PAPERS_SUBDIR = "papers"

_TYPE_LABEL = {"choice": "选择题", "blank": "填空题", "qa": "解答题"}
_TYPE_EN = {"choice": "choice questions", "blank": "fill-in-the-blank", "qa": "open-ended questions"}


def build_paper_prompt(task: PaperTask) -> str:
    """根据任务构建试卷命制 prompt。"""
    parts = task.question_types.split("-")
    counts = f"选择题 {parts[0]} 题、填空题 {parts[1]} 题、解答题 {parts[2]} 题"
    diff = task.difficulty.split("-")
    diff_desc = f"易:{diff[0]} 中:{diff[1]} 难:{diff[2]}"

    return f"""请为下列要求命制一份试卷。

【学科】{task.subject}
【年级】{task.grade}
【教材】{task.textbook or '不限定'}
【单元/章节】{task.unit or '不限定'}
【考查主题】{task.topic}
【知识点】{task.knowledge_points or '围绕主题自动选择'}
【题型与题量】{counts}
【卷面总分】{task.total_score} 分
【难度分布（易:中:难）】{diff_desc}
{'【包含答案与解析】是' if task.include_answers else '【包含答案与解析】否'}
【额外要求】{task.extra_requirements or '无'}

返回 JSON，必须严格使用以下结构：
{{
  "title": "试卷标题",
  "total_score": {task.total_score},
  "questions": [
    {{
      "number": 1,
      "question_type": "choice|blank|qa",
      "type_label": "选择题|填空题|解答题",
      "score": 分值,
      "knowledge_point": "考查知识点",
      "difficulty": "easy|medium|hard",
      "content": "题干",
      "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
      "answer": "答案（选择题填 A/B/C/D，解答题填完整解答）",
      "explanation": "解析"
    }}
  ],
  "notes": "命题说明（难度分布、考查意图）"
}}

规则：
1. 选择题数量={parts[0]}、填空题数量={parts[1]}、解答题数量={parts[2]}，必须精确匹配。
2. 选择题必须恰好 4 个选项，且以 A./B./C./D. 开头。
3. 各题 score 之和必须等于卷面总分 {task.total_score}。
4. 题目难度按 易:中:难 = {diff_desc} 分布。
5. 内容贴合 {task.grade} 学生水平，题干清晰、无歧义。
6. 只返回 JSON，不要任何额外文字。"""


def render_paper_docx(task: PaperTask, data: dict, out_path: str) -> None:
    """渲染试卷 docx（试卷正文 + 答案与解析）。"""
    doc = new_document()

    title = data.get("title") or f"{task.subject}试卷"
    add_paragraph(
        doc, title, HEI, 22, True,
        align=WD_ALIGN_PARAGRAPH.CENTER, before=6, after=4,
    )
    add_paragraph(
        doc, f"（{task.grade} · {task.subject} · 满分{task.total_score}分）",
        SONG, 12, False, align=WD_ALIGN_PARAGRAPH.CENTER, after=10,
    )

    questions = data.get("questions", [])
    # V2.2.1 P0 修复：正文与答案必须使用同一 canonical order。
    # 只保留合法题型（choice/blank/qa）并按题型分组序排列、组内保持 LLM 原序，
    # 杜绝"正文按题型重排、答案按原顺序"导致的题号错位；未知题型已被 validator
    # 拒绝（不会走到这里），此处 double-guard 直接过滤，避免静默丢题造成总分错误。
    ordered: list[dict] = []
    for qtype in ("choice", "blank", "qa"):
        for q in questions:
            if q.get("question_type") == qtype:
                ordered.append(q)

    # 一、正文（按题型分组，组内 canonical 顺序）
    q_no = 0
    group_no = 0
    for qtype in ("choice", "blank", "qa"):
        qlist = [q for q in ordered if q.get("question_type") == qtype]
        if not qlist:
            continue
        group_no += 1
        label = _TYPE_LABEL.get(qtype, qtype)
        add_heading(doc, f"{['一', '二', '三'][group_no - 1]}、{label}", level=1)
        for q in qlist:
            q_no += 1
            score = q.get("score", 0)
            add_paragraph(
                doc, f"{q_no}. （{score}分）{q.get('content', '')}",
                SONG, 12, indent=0.5,
            )
            for opt in q.get("options") or []:
                add_paragraph(doc, f"    {opt}", SONG, 12)

    # 二、答案与解析（与正文同一 canonical 顺序，题号严格对应）
    if task.include_answers:
        doc.add_page_break()
        add_heading(doc, "参考答案与解析", level=1)
        for i, q in enumerate(ordered, start=1):
            add_label_body(
                doc,
                f"第{i}题（{q.get('knowledge_point', '')}）",
                f"答案：{q.get('answer', '')}",
            )
            if q.get("explanation"):
                add_paragraph(doc, f"解析：{q['explanation']}", SONG, 11, indent=0.7)

    notes = data.get("notes")
    if notes:
        doc.add_page_break()
        add_heading(doc, "命题说明", level=1)
        add_paragraph(doc, str(notes), SONG, 11, indent=0.7)

    doc.save(out_path)


class PaperValidationError(ValueError):
    """试卷业务校验失败。"""


async def generate_paper(db: AsyncSession, task_id: int) -> None:
    """生成试卷并回写结果（Celery 异步任务调用）。"""
    task = await db.get(PaperTask, task_id)
    if not task:
        return
    task.status = "processing"
    db.add(task)
    await db.commit()

    t0 = time.time()
    try:
        prompt = build_paper_prompt(task)
        expected_counts = tuple(int(p) for p in task.question_types.split("-"))
        data = None

        for attempt in range(1, 3):
            data, usage, _elapsed = await chat_json(
                "你是一位经验丰富的中学命题专家，熟悉课程标准与中考命题规范，"
                "命题严谨、科学、无歧义。只返回 JSON。",
                prompt,
                temperature=0.5,
            )
            try:
                result = PaperLLMResult(**data)
            except Exception as ve:
                logger.warning("[Paper] task=%s 结构校验失败(第%s次): %s", task_id, attempt, ve)
                if attempt < 2:
                    prompt += f"\n\n【重要纠错】你上次返回的JSON结构有误：{ve}，请修正后重新返回。"
                    continue
                raise PaperValidationError(f"JSON结构校验失败：{ve}") from ve

            biz_errors = result.validate_business_rules(
                expected_counts, task.total_score
            )
            if biz_errors:
                logger.warning("[Paper] task=%s 业务校验失败(第%s次): %s", task_id, attempt, biz_errors)
                if attempt < 2:
                    prompt += (
                        f"\n\n【重要纠错】你上次的试卷有以下问题，请修正："
                        f"{'；'.join(biz_errors)}。请严格保证题量匹配、"
                        f"选择题四选项A/B/C/D、分值之和={task.total_score}。"
                    )
                    continue
                raise PaperValidationError(f"业务规则校验失败：{'；'.join(biz_errors)}")

            break  # 校验通过

        out_dir = os.path.join(OUTPUT_DIR, PAPERS_SUBDIR, str(task_id))
        os.makedirs(out_dir, exist_ok=True)
        # V2.2.1 P0：所有进入文件名的动态字段统一过 safe_filename_part
        # （subject/grade/topic 均可能含 / \ : * ? 等非法字符，如 "一次函数/反比例函数"）
        fname = (
            f"{safe_filename_part(task.subject, '试卷')}_"
            f"{safe_filename_part(task.grade, '年级')}_"
            f"{safe_filename_part(task.topic, '主题')}.docx"
        )
        out_path = os.path.join(out_dir, fname)
        render_paper_docx(task, data, out_path)

        rel_path = f"{PAPERS_SUBDIR}/{task_id}/{fname}"
        task.status = "success"
        task.file_path = rel_path
        task.file_name = fname
        task.ai_raw_json = data
        task.prompt_tokens = usage.get("prompt_tokens")
        task.completion_tokens = usage.get("completion_tokens")
        task.elapsed_sec = int(time.time() - t0)
        task.finished_at = get_local_now()
        logger.info("[Paper] task=%s 生成成功，耗时 %ss", task_id, task.elapsed_sec)

    except PaperValidationError as e:
        logger.error("[Paper] task=%s 校验失败: %s", task_id, e)
        task.status = "failed"
        task.error_msg = str(e)[:500]
        task.elapsed_sec = int(time.time() - t0)
        task.finished_at = get_local_now()
    except LLMError as e:
        logger.error("[Paper] task=%s LLM 错误: %s", task_id, e)
        task.status = "failed"
        task.error_msg = f"LLM 错误：{e}"[:500]
        task.elapsed_sec = int(time.time() - t0)
        task.finished_at = get_local_now()
    except LLMTransportError as e:
        # 传输错误：保持 processing，Celery 会重试，重试耗尽后 tasks.py 标记最终 failed
        logger.error("[Paper] task=%s 传输错误（Celery 将重试）: %s", task_id, e)
        task.status = "processing"
        task.error_msg = f"网络异常，正在自动重试：{e}"[:500]
        db.add(task)
        await db.commit()
        raise

    db.add(task)
    await db.commit()
