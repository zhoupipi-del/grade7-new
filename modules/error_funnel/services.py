"""
error_funnel/services.py — 错题断层漏斗引擎核心

核心功能:
  1. 知识点 CRUD (树形结构)
  2. 错题本 CRUD + 来源归集
  3. ingest_errors_from_homework — 供 homework_mgmt 调用
  4. 知识点断层聚合 — error_book_items → knowledge_gaps
  5. 断层等级: watch(≥1) → warning(≥2连续/≥3累计) → critical(≥3连续/≥5累计)
  6. AI处方生成 — critical 断层触发 DeepSeek
  7. 看板统计
  8. 从考试成绩批量导入错题
"""

import os
import json
import httpx
import logging
from sqlalchemy import select, func, and_, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List, Tuple, Dict, Any
from datetime import datetime

from core.models import get_local_now, User, Student
from modules.grades.models import GradeSubject, GradeRecord
from .models import (
    KnowledgePoint, ErrorBookItem, KnowledgeGap,
    ERROR_CONCEPTUAL, ERROR_PROCEDURAL, ERROR_CARELESS, ERROR_OMISSION, ERROR_UNKNOWN,
    SOURCE_HOMEWORK, SOURCE_EXAM, SOURCE_MANUAL,
    GAP_NONE, GAP_WATCH, GAP_WARNING, GAP_CRITICAL,
    GAP_ACTIVE, GAP_RESOLVED,
    AI_PENDING, AI_COMPLETED, AI_FAILED,
)

logger = logging.getLogger(__name__)

# ── DeepSeek 配置 ──
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_API_URL = os.environ.get("LLM_API_URL", "https://api.deepseek.com/v1/chat/completions")
LLM_MODEL = os.environ.get("LLM_MODEL", "deepseek-chat")


# ──────────────────────────────────────────────
# 辅助函数
# ──────────────────────────────────────────────

async def _get_student_names_batch(db: AsyncSession, student_ids: List[int]) -> Dict[int, str]:
    if not student_ids:
        return {}
    result = await db.execute(
        select(Student.id, Student.name).where(Student.id.in_(student_ids))
    )
    return {row[0]: row[1] for row in result.all()}


async def _get_subject_names_batch(db: AsyncSession, subject_ids: List[int]) -> Dict[int, str]:
    if not subject_ids:
        return {}
    result = await db.execute(
        select(GradeSubject.id, GradeSubject.name).where(GradeSubject.id.in_(subject_ids))
    )
    return {row[0]: row[1] for row in result.all()}


async def _get_kp_names_batch(db: AsyncSession, school_id: int, kp_ids: List[int]) -> Dict[int, str]:
    """批量获取知识点名"""
    if not kp_ids:
        return {}
    result = await db.execute(
        select(KnowledgePoint.id, KnowledgePoint.name).where(
            and_(
                KnowledgePoint.school_id == school_id,
                KnowledgePoint.id.in_(kp_ids),
            )
        )
    )
    return {row[0]: row[1] for row in result.all()}


def _calculate_gap_level(error_count: int, consecutive_errors: int) -> str:
    """计算断层等级"""
    if consecutive_errors >= 3 or error_count >= 5:
        return GAP_CRITICAL
    elif consecutive_errors >= 2 or error_count >= 3:
        return GAP_WARNING
    elif error_count >= 1:
        return GAP_WATCH
    else:
        return GAP_NONE


# ──────────────────────────────────────────────
# 知识点 CRUD
# ──────────────────────────────────────────────

async def create_knowledge_point(
    db: AsyncSession, school_id: int, data: "KnowledgePointCreate",
) -> KnowledgePoint:
    """创建知识点"""
    kp = KnowledgePoint(
        school_id=school_id,
        subject_id=data.subject_id,
        name=data.name,
        code=data.code,
        description=data.description,
        parent_id=data.parent_id,
        sort_order=data.sort_order,
    )
    db.add(kp)
    await db.commit()
    await db.refresh(kp)
    return kp


async def list_knowledge_points(
    db: AsyncSession, school_id: int,
    subject_id: Optional[int] = None,
    parent_id: Optional[int] = None,
) -> List[dict]:
    """列出知识点 (平铺)"""
    conditions = [KnowledgePoint.school_id == school_id, KnowledgePoint.is_active == True]
    if subject_id:
        conditions.append(KnowledgePoint.subject_id == subject_id)
    if parent_id is not None:
        conditions.append(KnowledgePoint.parent_id == parent_id)

    result = await db.execute(
        select(KnowledgePoint)
        .where(and_(*conditions))
        .order_by(KnowledgePoint.sort_order, KnowledgePoint.id)
    )
    kps = result.scalars().all()

    subject_map = await _get_subject_names_batch(db, list(set(kp.subject_id for kp in kps)))

    return [{
        "id": kp.id,
        "school_id": kp.school_id,
        "subject_id": kp.subject_id,
        "subject_name": subject_map.get(kp.subject_id, ""),
        "name": kp.name,
        "code": kp.code,
        "description": kp.description,
        "parent_id": kp.parent_id,
        "sort_order": kp.sort_order,
        "is_active": kp.is_active,
        "created_at": kp.created_at,
    } for kp in kps]


async def update_knowledge_point(
    db: AsyncSession, school_id: int, kp_id: int, data: "KnowledgePointUpdate",
) -> Optional[KnowledgePoint]:
    """更新知识点"""
    result = await db.execute(
        select(KnowledgePoint).where(
            and_(KnowledgePoint.school_id == school_id, KnowledgePoint.id == kp_id)
        )
    )
    kp = result.scalar_one_or_none()
    if not kp:
        return None

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(kp, key, value)

    await db.commit()
    await db.refresh(kp)
    return kp


# ──────────────────────────────────────────────
# 错题本 CRUD
# ──────────────────────────────────────────────

async def add_error_item(
    db: AsyncSession, school_id: int, data: "ErrorItemCreate",
) -> ErrorBookItem:
    """手动添加错题"""
    item = ErrorBookItem(
        school_id=school_id,
        student_id=data.student_id,
        subject_id=data.subject_id,
        source_type=data.source_type,
        source_id=data.source_id,
        source_desc=data.source_desc,
        question_content=data.question_content,
        question_type=data.question_type,
        student_answer=data.student_answer,
        correct_answer=data.correct_answer,
        error_type=data.error_type,
        knowledge_point_ids=data.knowledge_point_ids,
        difficulty=data.difficulty,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)

    # 自动聚合到 knowledge_gaps
    if data.knowledge_point_ids:
        await _aggregate_gaps(db, school_id, data.student_id, data.subject_id, data.knowledge_point_ids, data.source_desc)

    return item


async def list_error_items(
    db: AsyncSession, school_id: int,
    student_id: Optional[int] = None,
    subject_id: Optional[int] = None,
    source_type: Optional[str] = None,
    error_type: Optional[str] = None,
    is_resolved: Optional[bool] = None,
    page: int = 1, page_size: int = 20,
) -> Tuple[List[dict], int]:
    """列出错题本条目"""
    conditions = [ErrorBookItem.school_id == school_id]
    if student_id:
        conditions.append(ErrorBookItem.student_id == student_id)
    if subject_id:
        conditions.append(ErrorBookItem.subject_id == subject_id)
    if source_type:
        conditions.append(ErrorBookItem.source_type == source_type)
    if error_type:
        conditions.append(ErrorBookItem.error_type == error_type)
    if is_resolved is not None:
        conditions.append(ErrorBookItem.is_resolved == is_resolved)

    where_clause = and_(*conditions)

    count_result = await db.execute(
        select(func.count(ErrorBookItem.id)).where(where_clause)
    )
    total = count_result.scalar() or 0

    result = await db.execute(
        select(ErrorBookItem)
        .where(where_clause)
        .order_by(ErrorBookItem.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = result.scalars().all()

    # 批量获取名称
    student_ids = list(set(i.student_id for i in items))
    subject_ids = list(set(i.subject_id for i in items))
    student_map = await _get_student_names_batch(db, student_ids)
    subject_map = await _get_subject_names_batch(db, subject_ids)

    # 获取知识点名
    all_kp_ids = set()
    for i in items:
        if i.knowledge_point_ids:
            all_kp_ids.update(i.knowledge_point_ids)
    kp_map = await _get_kp_names_batch(db, school_id, list(all_kp_ids))

    enriched = []
    for i in items:
        kp_names = []
        if i.knowledge_point_ids:
            kp_names = [kp_map.get(kp_id, f"知识点{kp_id}") for kp_id in i.knowledge_point_ids]
        enriched.append({
            "id": i.id,
            "school_id": i.school_id,
            "student_id": i.student_id,
            "student_name": student_map.get(i.student_id, f"学生{i.student_id}"),
            "subject_id": i.subject_id,
            "subject_name": subject_map.get(i.subject_id, ""),
            "source_type": i.source_type,
            "source_id": i.source_id,
            "source_desc": i.source_desc,
            "question_content": i.question_content,
            "question_type": i.question_type,
            "student_answer": i.student_answer,
            "correct_answer": i.correct_answer,
            "error_type": i.error_type,
            "knowledge_point_ids": i.knowledge_point_ids or [],
            "knowledge_point_names": kp_names,
            "difficulty": i.difficulty,
            "ai_analysis": i.ai_analysis,
            "ai_status": i.ai_status,
            "is_resolved": i.is_resolved,
            "resolved_at": i.resolved_at,
            "created_at": i.created_at,
        })

    return enriched, total


async def resolve_error_item(
    db: AsyncSession, school_id: int, error_id: int,
) -> Optional[ErrorBookItem]:
    """标记错题为已纠错"""
    result = await db.execute(
        select(ErrorBookItem).where(
            and_(ErrorBookItem.school_id == school_id, ErrorBookItem.id == error_id)
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        return None

    item.is_resolved = True
    item.resolved_at = get_local_now()
    await db.commit()
    await db.refresh(item)
    return item


# ──────────────────────────────────────────────
# 作业错题归集 — 供 homework_mgmt 调用
# ──────────────────────────────────────────────

async def ingest_errors_from_homework(
    db: AsyncSession, school_id: int, student_id: int,
    assignment_id: int, error_items: List[dict],
) -> int:
    """
    从作业批改中归集错题 — 由 homework_mgmt/services.py 调用

    每个 error_item dict 包含:
      question_content, student_answer, correct_answer,
      error_type, knowledge_point_ids, difficulty, question_no
    """
    # 获取作业信息用于 source_desc
    from modules.homework_mgmt.models import HwAssignment
    hw_result = await db.execute(
        select(HwAssignment).where(
            and_(HwAssignment.school_id == school_id, HwAssignment.id == assignment_id)
        )
    )
    hw = hw_result.scalar_one_or_none()
    hw_title = hw.title if hw else f"作业{assignment_id}"
    subject_id = hw.subject_id if hw else 0

    count = 0
    for ei in error_items:
        item = ErrorBookItem(
            school_id=school_id,
            student_id=student_id,
            subject_id=subject_id,
            source_type=SOURCE_HOMEWORK,
            source_id=assignment_id,
            source_desc=f"作业: {hw_title}",
            question_content=ei.get("question_content", ""),
            question_type=ei.get("question_type"),
            student_answer=ei.get("student_answer"),
            correct_answer=ei.get("correct_answer"),
            error_type=ei.get("error_type", ERROR_UNKNOWN),
            knowledge_point_ids=ei.get("knowledge_point_ids", []),
            difficulty=ei.get("difficulty"),
        )
        db.add(item)
        count += 1

        # 聚合到 knowledge_gaps
        kp_ids = ei.get("knowledge_point_ids", [])
        if kp_ids:
            await _aggregate_gaps(
                db, school_id, student_id, subject_id, kp_ids,
                f"作业: {hw_title}",
            )

    await db.commit()
    logger.info(f"从作业{assignment_id}归集{count}条错题, 学生={student_id}")
    return count


# ──────────────────────────────────────────────
# 知识点断层聚合 — 漏斗核心
# ──────────────────────────────────────────────

async def _aggregate_gaps(
    db: AsyncSession, school_id: int, student_id: int,
    subject_id: int, knowledge_point_ids: List[int],
    source_desc: str = "",
) -> None:
    """
    聚合错题到知识点断层表 — 每次有新错题时调用

    逻辑:
      1. 查找已有的 knowledge_gap 记录
      2. error_count + 1, consecutive_errors + 1
      3. 重新计算 gap_level
      4. 如果达到 critical 且无AI处方 → 标记待生成
    """
    now = get_local_now()
    critical_events = []  # 收集新晋 critical 的断层 (用于事件总线盲发)

    for kp_id in knowledge_point_ids:
        # 获取知识点名
        kp_result = await db.execute(
            select(KnowledgePoint.name).where(
                and_(KnowledgePoint.school_id == school_id, KnowledgePoint.id == kp_id)
            )
        )
        kp_name_row = kp_result.one_or_none()
        kp_name = kp_name_row[0] if kp_name_row else f"知识点{kp_id}"

        # 查找已有记录
        existing = await db.execute(
            select(KnowledgeGap).where(
                and_(
                    KnowledgeGap.school_id == school_id,
                    KnowledgeGap.student_id == student_id,
                    KnowledgeGap.knowledge_point_id == kp_id,
                )
            )
        )
        gap = existing.scalar_one_or_none()

        if gap:
            # 更新已有记录
            gap.error_count += 1
            gap.consecutive_errors += 1
            gap.last_error_date = now
            gap.last_error_source = source_desc
            old_level = gap.gap_level
            gap.gap_level = _calculate_gap_level(gap.error_count, gap.consecutive_errors)
            gap.gap_status = GAP_ACTIVE  # 新错误入列，重新激活
            gap.resolved_at = None

            # 🔌 事件总线: 新晋 critical (非 critical → critical) 才发射
            if old_level != GAP_CRITICAL and gap.gap_level == GAP_CRITICAL:
                critical_events.append({
                    "knowledge_point": kp_name,
                    "consecutive_errors": gap.consecutive_errors,
                    "error_count": gap.error_count,
                })
        else:
            # 新建记录
            gap = KnowledgeGap(
                school_id=school_id,
                student_id=student_id,
                subject_id=subject_id,
                knowledge_point_id=kp_id,
                knowledge_point_name=kp_name,
                error_count=1,
                consecutive_errors=1,
                last_error_date=now,
                last_error_source=source_desc,
                gap_level=GAP_WATCH,
                gap_status=GAP_ACTIVE,
            )
            db.add(gap)

    await db.flush()

    # 🔌 事件总线盲发: critical 断层 → growth 时光轴 (fire-and-forget)
    for evt in critical_events:
        try:
            from core.event_bus import EventBus
            EventBus().publish("error_funnel.critical", {
                "school_id": school_id,
                "student_id": student_id,
                "knowledge_point": evt["knowledge_point"],
                "consecutive_errors": evt["consecutive_errors"],
                "error_count": evt["error_count"],
            })
        except Exception:
            pass  # 事件总线不可用时静默降级


# ──────────────────────────────────────────────
# 断层查询
# ──────────────────────────────────────────────

async def list_gaps(
    db: AsyncSession, school_id: int,
    student_id: Optional[int] = None,
    subject_id: Optional[int] = None,
    gap_level: Optional[str] = None,
    gap_status: Optional[str] = None,
    page: int = 1, page_size: int = 20,
) -> Tuple[List[dict], int]:
    """列出知识点断层"""
    conditions = [KnowledgeGap.school_id == school_id]
    if student_id:
        conditions.append(KnowledgeGap.student_id == student_id)
    if subject_id:
        conditions.append(KnowledgeGap.subject_id == subject_id)
    if gap_level:
        conditions.append(KnowledgeGap.gap_level == gap_level)
    if gap_status:
        conditions.append(KnowledgeGap.gap_status == gap_status)

    where_clause = and_(*conditions)

    count_result = await db.execute(
        select(func.count(KnowledgeGap.id)).where(where_clause)
    )
    total = count_result.scalar() or 0

    result = await db.execute(
        select(KnowledgeGap)
        .where(where_clause)
        .order_by(
            # critical 优先, 然后按 error_count 降序
            KnowledgeGap.gap_level.desc(),
            KnowledgeGap.error_count.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    gaps = result.scalars().all()

    student_ids = list(set(g.student_id for g in gaps))
    subject_ids = list(set(g.subject_id for g in gaps))
    student_map = await _get_student_names_batch(db, student_ids)
    subject_map = await _get_subject_names_batch(db, subject_ids)

    return [{
        "id": g.id,
        "school_id": g.school_id,
        "student_id": g.student_id,
        "student_name": student_map.get(g.student_id, f"学生{g.student_id}"),
        "subject_id": g.subject_id,
        "subject_name": subject_map.get(g.subject_id, ""),
        "knowledge_point_id": g.knowledge_point_id,
        "knowledge_point_name": g.knowledge_point_name,
        "error_count": g.error_count,
        "consecutive_errors": g.consecutive_errors,
        "last_error_date": g.last_error_date,
        "last_error_source": g.last_error_source,
        "gap_level": g.gap_level,
        "gap_status": g.gap_status,
        "resolved_at": g.resolved_at,
        "ai_prescription": g.ai_prescription,
        "ai_prescription_generated_at": g.ai_prescription_generated_at,
        "created_at": g.created_at,
        "updated_at": g.updated_at,
    } for g in gaps], total


async def resolve_gap(
    db: AsyncSession, school_id: int, gap_id: int,
) -> Optional[KnowledgeGap]:
    """标记断层为已解决"""
    result = await db.execute(
        select(KnowledgeGap).where(
            and_(KnowledgeGap.school_id == school_id, KnowledgeGap.id == gap_id)
        )
    )
    gap = result.scalar_one_or_none()
    if not gap:
        return None

    gap.gap_status = GAP_RESOLVED
    gap.resolved_at = get_local_now()
    gap.consecutive_errors = 0  # 重置连续错误计数
    await db.commit()
    await db.refresh(gap)
    return gap


# ──────────────────────────────────────────────
# AI 处方生成 — DeepSeek 对接
# ──────────────────────────────────────────────

async def generate_ai_prescription(
    db: AsyncSession, school_id: int, gap_id: int,
) -> Optional[dict]:
    """
    为知识点断层生成 AI 处方

    流程:
      1. 获取断层记录 + 关联错题
      2. 构建 DeepSeek prompt
      3. 调用 API 获取处方
      4. 写入 knowledge_gaps.ai_prescription
    """
    # 获取断层记录
    result = await db.execute(
        select(KnowledgeGap).where(
            and_(KnowledgeGap.school_id == school_id, KnowledgeGap.id == gap_id)
        )
    )
    gap = result.scalar_one_or_none()
    if not gap:
        return None

    # 获取关联错题 (最近5条)
    error_result = await db.execute(
        select(ErrorBookItem).where(
            and_(
                ErrorBookItem.school_id == school_id,
                ErrorBookItem.student_id == gap.student_id,
                ErrorBookItem.subject_id == gap.subject_id,
                ErrorBookItem.knowledge_point_ids.contains([gap.knowledge_point_id]),
            )
        ).order_by(ErrorBookItem.created_at.desc()).limit(5)
    )
    errors = error_result.scalars().all()

    # 获取学生名
    student_map = await _get_student_names_batch(db, [gap.student_id])
    student_name = student_map.get(gap.student_id, f"学生{gap.student_id}")

    # 获取科目名
    subject_map = await _get_subject_names_batch(db, [gap.subject_id])
    subject_name = subject_map.get(gap.subject_id, "")

    # 构建 prompt
    error_list_text = ""
    for i, e in enumerate(errors, 1):
        error_list_text += f"\n错题{i}: {e.question_content[:200]}"
        if e.student_answer:
            error_list_text += f"\n  学生答案: {e.student_answer[:100]}"
        if e.correct_answer:
            error_list_text += f"\n  正确答案: {e.correct_answer[:100]}"
        error_list_text += f"\n  错误类型: {e.error_type}"

    system_prompt = (
        "你是一位资深教育专家,擅长诊断学生的知识点薄弱环节并开具针对性补救处方。"
        "请以JSON格式输出,包含 weakness_analysis(薄弱点分析) 和 action_prescription(行动处方) 两个字段。"
    )

    prompt = (
        f"学生: {student_name}\n"
        f"科目: {subject_name}\n"
        f"薄弱知识点: {gap.knowledge_point_name}\n"
        f"累计错误次数: {gap.error_count}\n"
        f"连续错误次数: {gap.consecutive_errors}\n"
        f"断层等级: {gap.gap_level}\n"
        f"最近错题记录:{error_list_text}\n\n"
        f"请分析该学生在「{gap.knowledge_point_name}」上的薄弱原因,并开具具体的补救处方。"
        f"处方应包含: 1) 核心薄弱点诊断 2) 针对性练习建议 3) 学习方法指导"
    )

    # 调用 DeepSeek
    try:
        prescription = await _call_deepseek(prompt, system_prompt)
        gap.ai_prescription = json.dumps(prescription, ensure_ascii=False)
        gap.ai_prescription_generated_at = get_local_now()

        await db.commit()
        await db.refresh(gap)

        return {
            "gap_id": gap.id,
            "student_name": student_name,
            "knowledge_point_name": gap.knowledge_point_name,
            "gap_level": gap.gap_level,
            "prescription": prescription,
            "generated_at": gap.ai_prescription_generated_at,
        }
    except Exception as e:
        logger.error(f"AI处方生成失败: {e}")
        return {"gap_id": gap_id, "error": str(e)}


async def _call_deepseek(prompt: str, system_prompt: str, timeout: float = 30.0) -> dict:
    """调用 DeepSeek API"""
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            LLM_API_URL,
            headers={
                "Authorization": f"Bearer {LLM_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": LLM_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.3,
                "max_tokens": 2048,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        return json.loads(content)


# ──────────────────────────────────────────────
# 从考试成绩批量导入错题
# ──────────────────────────────────────────────

async def batch_import_from_exam(
    db: AsyncSession, school_id: int,
    exam_id: int, subject_id: int, threshold: float = 60.0,
) -> dict:
    """
    从考试成绩批量导入错题 — 得分率低于阈值的学生自动生成错题记录

    注意: 因为成绩记录中没有题目级别的错题信息,
    这里生成的是"整体性错题"记录,标记为 conceptual 错误类型,
    关联到该科目的所有知识点(如果知识点表有数据)。
    """
    # 查询低分学生
    result = await db.execute(
        select(GradeRecord).where(
            and_(
                GradeRecord.school_id == school_id,
                GradeRecord.exam_id == exam_id,
                GradeRecord.subject_id == subject_id,
                GradeRecord.is_absent == False,
                GradeRecord.score < threshold,
            )
        )
    )
    records = result.scalars().all()

    # 获取科目信息
    subject_result = await db.execute(
        select(GradeSubject).where(GradeSubject.id == subject_id)
    )
    subject = subject_result.scalar_one_or_none()
    subject_name = subject.name if subject else f"科目{subject_id}"
    full_score = float(subject.full_score) if subject and subject.full_score else 100.0

    # 获取该科目的所有知识点
    kp_result = await db.execute(
        select(KnowledgePoint.id).where(
            and_(
                KnowledgePoint.school_id == school_id,
                KnowledgePoint.subject_id == subject_id,
                KnowledgePoint.is_active == True,
            )
        )
    )
    kp_ids = [row[0] for row in kp_result.all()]

    count = 0
    for record in records:
        score = float(record.score) if record.score else 0
        percentage = round(score / full_score * 100, 1) if full_score > 0 else 0

        item = ErrorBookItem(
            school_id=school_id,
            student_id=record.student_id,
            subject_id=subject_id,
            source_type=SOURCE_EXAM,
            source_id=exam_id,
            source_desc=f"考试得分率{percentage}%(低于{threshold}分阈值)",
            question_content=f"考试整体得分率{percentage}%,得分{score}/{full_score}",
            question_type="overall",
            student_answer=f"得分{score}",
            correct_answer=f"满分{full_score}",
            error_type=ERROR_CONCEPTUAL,
            knowledge_point_ids=kp_ids if kp_ids else None,
            difficulty="medium",
        )
        db.add(item)
        count += 1

        # 聚合到 gaps
        if kp_ids:
            await _aggregate_gaps(
                db, school_id, record.student_id, subject_id, kp_ids,
                f"考试得分率{percentage}%",
            )

    await db.commit()
    return {"imported": count, "exam_id": exam_id, "threshold": threshold}


# ──────────────────────────────────────────────
# 看板统计
# ──────────────────────────────────────────────

async def get_dashboard(
    db: AsyncSession, school_id: int,
    student_id: Optional[int] = None,
    subject_id: Optional[int] = None,
) -> dict:
    """错题断层看板"""
    e_conditions = [ErrorBookItem.school_id == school_id]
    g_conditions = [KnowledgeGap.school_id == school_id]
    if student_id:
        e_conditions.append(ErrorBookItem.student_id == student_id)
        g_conditions.append(KnowledgeGap.student_id == student_id)
    if subject_id:
        e_conditions.append(ErrorBookItem.subject_id == subject_id)
        g_conditions.append(KnowledgeGap.subject_id == subject_id)

    e_where = and_(*e_conditions)
    g_where = and_(*g_conditions)

    # 错题统计
    total_errors = await db.scalar(
        select(func.count(ErrorBookItem.id)).where(e_where)
    ) or 0

    unresolved = await db.scalar(
        select(func.count(ErrorBookItem.id)).where(
            and_(e_where, ErrorBookItem.is_resolved == False)
        )
    ) or 0

    # 断层统计
    total_gaps = await db.scalar(
        select(func.count(KnowledgeGap.id)).where(g_where)
    ) or 0

    critical = await db.scalar(
        select(func.count(KnowledgeGap.id)).where(
            and_(g_where, KnowledgeGap.gap_level == GAP_CRITICAL, KnowledgeGap.gap_status == GAP_ACTIVE)
        )
    ) or 0

    warning = await db.scalar(
        select(func.count(KnowledgeGap.id)).where(
            and_(g_where, KnowledgeGap.gap_level == GAP_WARNING, KnowledgeGap.gap_status == GAP_ACTIVE)
        )
    ) or 0

    watch = await db.scalar(
        select(func.count(KnowledgeGap.id)).where(
            and_(g_where, KnowledgeGap.gap_level == GAP_WATCH, KnowledgeGap.gap_status == GAP_ACTIVE)
        )
    ) or 0

    resolved = await db.scalar(
        select(func.count(KnowledgeGap.id)).where(
            and_(g_where, KnowledgeGap.gap_status == GAP_RESOLVED)
        )
    ) or 0

    ai_count = await db.scalar(
        select(func.count(KnowledgeGap.id)).where(
            and_(g_where, KnowledgeGap.ai_prescription.isnot(None))
        )
    ) or 0

    # TOP 错误知识点
    top_kp_result = await db.execute(
        select(
            KnowledgeGap.knowledge_point_name,
            func.sum(KnowledgeGap.error_count),
        ).where(g_where)
        .group_by(KnowledgeGap.knowledge_point_name)
        .order_by(func.sum(KnowledgeGap.error_count).desc())
        .limit(10)
    )
    top_error_kps = [{"name": row[0], "error_count": row[1]} for row in top_kp_result.all()]

    # TOP 错误学生
    top_stu_result = await db.execute(
        select(
            ErrorBookItem.student_id,
            func.count(ErrorBookItem.id),
        ).where(e_where)
        .group_by(ErrorBookItem.student_id)
        .order_by(func.count(ErrorBookItem.id).desc())
        .limit(10)
    )
    top_stu_ids = [row[0] for row in top_stu_result.all()]
    student_map = await _get_student_names_batch(db, top_stu_ids)
    top_error_students = [
        {"student_id": row[0], "student_name": student_map.get(row[0], f"学生{row[0]}"), "error_count": row[1]}
        for row in top_stu_result.all()
    ]

    # 错误类型分布
    type_result = await db.execute(
        select(
            ErrorBookItem.error_type,
            func.count(ErrorBookItem.id),
        ).where(e_where)
        .group_by(ErrorBookItem.error_type)
    )
    error_type_dist = {row[0]: row[1] for row in type_result.all()}

    # 最近错题
    recent_result = await db.execute(
        select(ErrorBookItem)
        .where(e_where)
        .order_by(ErrorBookItem.created_at.desc())
        .limit(5)
    )
    recent_errors = [{
        "id": e.id,
        "student_id": e.student_id,
        "question_content": e.question_content[:100],
        "error_type": e.error_type,
        "source_desc": e.source_desc,
        "created_at": e.created_at,
    } for e in recent_result.scalars().all()]

    return {
        "total_errors": total_errors,
        "unresolved_errors": unresolved,
        "total_gaps": total_gaps,
        "critical_gaps": critical,
        "warning_gaps": warning,
        "watch_gaps": watch,
        "resolved_gaps": resolved,
        "ai_prescriptions_generated": ai_count,
        "top_error_knowledge_points": top_error_kps,
        "top_error_students": top_error_students,
        "error_type_distribution": error_type_dist,
        "recent_errors": recent_errors,
    }
