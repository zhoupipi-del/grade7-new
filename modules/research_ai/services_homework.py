"""
modules/research_ai/services_homework.py
=========================================
分层作业生成核心业务逻辑。

V2.1 修复：
  - [P1] LLM 结果业务校验（三层题量严格匹配、选择题4选项），失败重试一次
  - [P1] 异常分层：LLMError 标记 failed，LLMTransportError 标记后向上抛出让 Celery 重试
  - 输出目录修正为 /opt/wings3/shared/uploads/research_ai/
"""
from __future__ import annotations

import logging
import os
import re
import time
from typing import Any

from docx.enum.text import WD_ALIGN_PARAGRAPH
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import get_local_now
from modules.research_ai.llm_client import LLMError, LLMTransportError, chat_json
from modules.research_ai.models_homework import HomeworkTask
from modules.research_ai.schemas import HomeworkLLMResult
from modules.research_ai.word_renderer import (
    HEI,
    SONG,
    new_document,
    set_font,
)

logger = logging.getLogger(__name__)

OUTPUT_DIR = os.environ.get(
    "RESEARCH_AI_OUTPUT_DIR", "/opt/wings3/shared/uploads/research_ai"
)
HOMEWORK_SUBDIR = "homework"

LAYER_NAMES = {
    "basic": "基础巩固层",
    "intermediate": "能力提高层",
    "advanced": "拓展探究层",
}
LAYER_DESCRIPTIONS = {
    "basic": "面向全体学生，紧扣本节课核心知识，题型直接、计算量适中，确保基础达标。",
    "intermediate": "面向中等以上学生，需综合运用2个以上知识点，含变式题和简单应用题。",
    "advanced": "面向学有余力学生，含开放性、探究性或竞赛衔接题，侧重思维拓展和迁移。",
}


def _parse_counts(s: str) -> tuple[int, int, int]:
    parts = s.split("-")
    return int(parts[0]), int(parts[1]), int(parts[2])


def _build_system_prompt() -> str:
    return """你是一位经验丰富的中小学学科教研组长，精通分层作业设计。
你的任务是根据教师输入的学科、年级、知识点和学情，生成一份**三层分层作业**：
1. 基础巩固层（basic）：面向全体，紧扣核心知识
2. 能力提高层（intermediate）：综合运用，变式训练
3. 拓展探究层（advanced）：开放性探究，思维拓展

要求：
- 题目必须符合对应年级的认知水平和课程标准
- 知识点覆盖精准，不超纲、不偏题
- 题目之间不重复、不雷同
- 数学题给出准确数值和清晰计算步骤
- 语文/英语题语言规范
- 选择题选项必须恰好4个（A/B/C/D）
- 每道题标注对应知识点
- 答案和解析必须准确完整

输出严格 JSON 格式，结构如下：
{
  "title": "作业标题",
  "total_score": 100,
  "layers": [
    {
      "layer": "basic",
      "layer_name": "基础巩固层",
      "description": "本层设计说明",
      "questions": [
        {
          "layer": "basic",
          "number": 1,
          "question_type": "choice|fill|short_answer|calculation|proof|essay",
          "content": "题目内容",
          "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
          "score": 3,
          "knowledge_point": "知识点名称",
          "answer": "参考答案",
          "explanation": "解析（如有）"
        }
      ]
    }
  ],
  "teaching_notes": "给教师的使用建议"
}"""


def _build_user_prompt(task: HomeworkTask) -> str:
    basic_n, inter_n, adv_n = _parse_counts(task.question_counts)
    easy, medium, hard = task.difficulty_distribution.split("-")

    parts = [
        f"学科：{task.subject}",
        f"年级：{task.grade}",
    ]
    if task.textbook:
        parts.append(f"教材版本：{task.textbook}")
    if task.unit:
        parts.append(f"章节/单元：{task.unit}")
    parts.append(f"本节课主题：{task.topic}")

    if task.knowledge_points:
        kps = [
            k.strip()
            for k in re.split(r"[,\n，、;；]+", task.knowledge_points)
            if k.strip()
        ]
        parts.append(f"核心知识点：{', '.join(kps)}")

    parts.append(
        f"三层题量：基础巩固{basic_n}题、能力提高{inter_n}题、拓展探究{adv_n}题"
    )
    parts.append(f"整体难易比例（易:中:难）：{easy}:{medium}:{hard}")
    parts.append(f"建议完成时长：{task.estimated_minutes}分钟")

    if task.class_profile:
        parts.append(f"\n班级学情：{task.class_profile}")
    if task.extra_requirements:
        parts.append(f"\n其他要求：{task.extra_requirements}")

    include = "是" if task.include_answers else "否"
    parts.append(
        f"\n请严格按 JSON 格式输出。include_answers={include}，"
        "如果不包含答案，answer 和 explanation 字段留空字符串。"
        f"\n关键要求：basic层恰好{basic_n}题，intermediate层恰好{inter_n}题，advanced层恰好{adv_n}题。"
        "\n选择题的options数组必须恰好4个元素。"
    )
    return "\n".join(parts)


# ════════════════════════════════════════════════════════════
# Word 渲染
# ════════════════════════════════════════════════════════════

def _add_title(doc, text: str, size: int = 16) -> None:
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(text)
    set_font(run, HEI, size, True)


def _add_heading(doc, text: str, size: int = 13) -> None:
    p = doc.add_paragraph()
    run = p.add_run(text)
    set_font(run, HEI, size, True)


def _add_body(doc, text: str, size: float = 11, bold: bool = False) -> None:
    p = doc.add_paragraph()
    run = p.add_run(text)
    set_font(run, SONG, size, bold)


def _render_question(doc, q: dict[str, Any], show_answer: bool) -> None:
    qtype_map = {
        "choice": "选择题",
        "fill": "填空题",
        "short_answer": "简答题",
        "calculation": "计算题",
        "proof": "证明题",
        "essay": "论述题",
    }
    qtype = qtype_map.get(q.get("question_type", ""), "")
    score = q.get("score")
    kp = q.get("knowledge_point", "")

    header = f"{q.get('number', '?')}. "
    if qtype:
        header += f"（{qtype}"
        if score:
            header += f"，{score}分"
        header += "）"
    if kp:
        header += f" [{kp}]"

    p = doc.add_paragraph()
    run = p.add_run(header)
    set_font(run, SONG, 11, True)

    for line in str(q.get("content", "")).split("\n"):
        _add_body(doc, line)

    options = q.get("options")
    if options:
        for opt in options:
            _add_body(doc, f"    {opt}")

    if show_answer:
        answer = q.get("answer", "")
        explanation = q.get("explanation", "")
        if answer:
            p = doc.add_paragraph()
            run = p.add_run(f"【答案】{answer}")
            set_font(run, SONG, 10.5, color=(0x00, 0x66, 0x00))
        if explanation:
            p = doc.add_paragraph()
            run = p.add_run(f"【解析】{explanation}")
            set_font(run, SONG, 10.5, color=(0x00, 0x00, 0x99))


def generate_homework_docx(
    result: dict[str, Any],
    task: HomeworkTask,
) -> str:
    doc = new_document()

    title = result.get("title") or f"{task.grade}{task.subject}分层作业——{task.topic}"
    _add_title(doc, title)

    meta = (
        f"年级：{task.grade}    学科：{task.subject}    "
        f"建议时长：{task.estimated_minutes}分钟    "
        f"总分：{result.get('total_score', 100)}分"
    )
    _add_body(doc, meta, size=10.5)
    doc.add_paragraph()

    for layer in result.get("layers", []) or []:
        layer_key = layer.get("layer", "")
        layer_name = layer.get("layer_name") or LAYER_NAMES.get(
            layer_key, layer_key
        )
        desc = layer.get("description") or LAYER_DESCRIPTIONS.get(layer_key, "")

        _add_heading(doc, "=" * 20)
        _add_heading(doc, f"【{layer_name}】")
        if desc:
            _add_body(doc, desc, size=10)
        doc.add_paragraph()

        for q in layer.get("questions", []) or []:
            _render_question(doc, q, bool(task.include_answers))
        doc.add_paragraph()

    notes = result.get("teaching_notes")
    if notes:
        doc.add_paragraph()
        _add_heading(doc, "【教师使用建议】")
        _add_body(doc, notes)

    _add_body(doc, "本作业由 WINGS AI 教研助手辅助生成，教师请结合学情审阅使用。",
              size=9)

    out_dir = os.path.join(OUTPUT_DIR, HOMEWORK_SUBDIR)
    os.makedirs(out_dir, exist_ok=True)
    safe_topic = re.sub(r'[\\/:*?"<>|\s]+', "_", task.topic)[:40]
    filename = f"homework_{task.id}_{safe_topic}.docx"
    full_path = os.path.join(out_dir, filename)
    doc.save(full_path)
    return os.path.join(HOMEWORK_SUBDIR, filename), filename


# ════════════════════════════════════════════════════════════
# 主服务
# ════════════════════════════════════════════════════════════

class HomeworkValidationError(ValueError):
    """分层作业 LLM 结果业务校验失败。"""


async def generate_layered_homework(db: AsyncSession, task_id: int) -> None:
    """调 LLM → 校验 → 生成 Word → 落库。"""
    task = await db.get(HomeworkTask, task_id)
    if not task:
        return

    task.status = "processing"
    db.add(task)
    await db.commit()

    t0 = time.time()
    expected_counts = _parse_counts(task.question_counts)

    try:
        system_prompt = _build_system_prompt()
        user_prompt = _build_user_prompt(task)
        data = None
        usage = {}

        # [P1] 业务校验失败重试一次
        for attempt in range(1, 3):
            data, usage, _elapsed = await chat_json(
                system_prompt, user_prompt, temperature=0.5
            )

            # 结构校验
            try:
                result = HomeworkLLMResult(**data)
            except Exception as ve:
                logger.warning(
                    "[Homework] task=%s 结构校验失败(第%s次): %s",
                    task_id, attempt, ve,
                )
                if attempt < 2:
                    user_prompt += f"\n\n【重要纠错】你上次返回的JSON结构有误：{ve}，请修正后重新返回。"
                    continue
                raise HomeworkValidationError(f"JSON结构校验失败：{ve}") from ve

            # 业务规则校验
            biz_errors = result.validate_business_rules(expected_counts)
            if biz_errors:
                logger.warning(
                    "[Homework] task=%s 业务校验失败(第%s次): %s",
                    task_id, attempt, biz_errors,
                )
                if attempt < 2:
                    user_prompt += (
                        f"\n\n【重要纠错】你上次的作业有以下问题，请修正："
                        f"{'；'.join(biz_errors)}。"
                        f"\n请确保basic层恰好{expected_counts[0]}题、"
                        f"intermediate层恰好{expected_counts[1]}题、"
                        f"advanced层恰好{expected_counts[2]}题。"
                    )
                    continue
                raise HomeworkValidationError(f"业务规则校验失败：{'；'.join(biz_errors)}")

            break

        rel_path, filename = generate_homework_docx(data, task)

        task.status = "success"
        task.file_path = rel_path
        task.file_name = filename
        task.ai_raw_json = data
        task.prompt_tokens = usage.get("prompt_tokens")
        task.completion_tokens = usage.get("completion_tokens")
        task.elapsed_sec = int(time.time() - t0)
        task.finished_at = get_local_now()
        logger.info(
            "[Homework] task=%s 生成成功，耗时 %ss", task_id, task.elapsed_sec
        )

    except HomeworkValidationError as e:
        logger.error("[Homework] task=%s 校验失败: %s", task_id, e)
        task.status = "failed"
        task.error_msg = str(e)[:2000]
        task.elapsed_sec = int(time.time() - t0)
        task.finished_at = get_local_now()

    except LLMError as e:
        logger.error("[Homework] task=%s LLM 错误: %s", task_id, e)
        task.status = "failed"
        task.error_msg = f"LLM 错误：{e}"[:2000]
        task.elapsed_sec = int(time.time() - t0)
        task.finished_at = get_local_now()

    except LLMTransportError as e:
        # [V2.1.1] 传输错误：保持 processing，不写 terminal failed，
        # Celery 重试耗尽后由 tasks.py 标记最终 failed。
        logger.error("[Homework] task=%s 传输错误（Celery 将重试）: %s", task_id, e)
        task.status = "processing"
        task.error_msg = f"网络异常，正在自动重试：{e}"[:2000]
        db.add(task)
        await db.commit()
        raise

    except Exception as e:
        logger.exception("[Homework] task=%s 生成失败", task_id)
        task.status = "failed"
        task.error_msg = f"生成失败：{type(e).__name__}: {e}"[:2000]
        task.elapsed_sec = int(time.time() - t0)
        task.finished_at = get_local_now()

    db.add(task)
    await db.commit()
