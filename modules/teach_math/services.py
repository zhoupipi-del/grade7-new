"""
modules/teach_math/services.py — 数学教学辅助业务逻辑

核心服务:
- TranslationService: 审题翻译（调用 DeepSeek LLM 逐句翻译数学应用题）
- ReportService: 教师端学情报表（班级维度聚合 + RDI 交叉预警）
"""

import json
import logging
import os
from collections import Counter
from datetime import datetime, timedelta
from typing import Optional

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, text as sa_text, bindparam

from core.models import User, Student, UserRole
from modules.risk_models.models import RiskWarning
from .models import TranslationRecord
from .schemas import (
    TranslateRequest,
    TranslateResponse,
    TranslatedSentence,
    MathReportKPI,
    TrendDataPoint,
    BlindSpotItem,
    StudentUsageItem,
)

logger = logging.getLogger(__name__)

# ── DeepSeek 配置 ──────────────────────────────────────────────
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_API_URL = os.environ.get("LLM_API_URL", "https://api.deepseek.com/v1/chat/completions")
LLM_MODEL = os.environ.get("LLM_MODEL", "deepseek-chat")

SYSTEM_PROMPT = """你是初中数学老师，专门训练学生把应用题"翻译"成数学表达式。

核心规则：
1. 把题目拆成逐句（按逗号/句号分句）
2. 每句话翻译成一个或多个数学表达式，用中文单字变量（明、红、长、宽、速、时 等）
3. 解释为什么这样翻译——用初二学生能听懂的语言
4. 翻译完列出所有变量及其含义
5. 如果某句话只是背景描述（不包含数学关系），标记为"上下文"并跳过翻译
6. 必须用标准数学符号：=、+、-、×、÷、()、≥、≤

示例：
题目：小明比小红大3岁，5年后两人年龄之和是45岁，求小明今年几岁？

翻译：
- "小明比小红大3岁" → 明 = 红 + 3（小明的年龄 = 小红的年龄 + 3）
- "5年后两人年龄之和是45岁" → (明 + 5) + (红 + 5) = 45（5年后的年龄 = 当前年龄 + 5，再相加等于45）
- 变量：明 = 小明今年的年龄，红 = 小红今年的年龄

请严格按照以下 JSON 格式返回，不要输出任何其他内容：
{
  "translations": [
    {
      "sentence": "原句文本",
      "math_expression": "数学表达式",
      "explanation": "翻译解释（面向学生）"
    }
  ],
  "suggested_variables": {
    "变量名": "含义说明"
  }
}"""


class TranslationService:
    """审题翻译服务 — 调用 DeepSeek LLM"""

    @staticmethod
    async def translate(
        request: TranslateRequest,
        db: AsyncSession,
        user: Optional[User] = None,
    ) -> TranslateResponse:
        """调用 DeepSeek 逐句翻译数学应用题

        Args:
            request: 翻译请求（题目文本 + 年级 + 知识点）
            db: 数据库会话
            user: 当前登录用户（用于区分学生/教师身份）

        Returns:
            TranslateResponse: 逐句翻译 + 变量建议
        """
        # ── 第1步：构造 prompt ─────────────────
        user_prompt = f"题目：{request.question_text}\n年级：{request.grade_level}"

        # ── 第2步：调用 DeepSeek ───────────────
        raw_response, error = _call_deepseek(user_prompt, SYSTEM_PROMPT)

        if error:
            logger.error(f"DeepSeek 调用失败: {error}")
            return TranslateResponse(
                translations=[],
                suggested_variables={},
                raw_llm_response={"error": str(error)},
                translation_id=None,
            )

        # ── 第3步：解析 LLM 响应 ───────────────
        translations = []
        suggested_vars = {}

        try:
            if isinstance(raw_response, dict):
                trans_list = raw_response.get("translations", [])
                for t in trans_list:
                    translations.append(TranslatedSentence(
                        sentence=t.get("sentence", ""),
                        math_expression=t.get("math_expression", ""),
                        explanation=t.get("explanation", ""),
                    ))
                suggested_vars = raw_response.get("suggested_variables", {})
        except Exception as e:
            logger.warning(f"LLM 响应解析异常: {e}, raw={raw_response}")

        # ── 第4步：保存记录（区分学生/教师身份）─────
        record_id = None
        try:
            # 判断当前用户身份，正确设置 student_id / teacher_id
            student_id = None
            teacher_id = None
            school_id = 1  # 默认

            if user:
                school_id = user.school_id
                if user.role == UserRole.PARENT and user.bound_student_id:
                    # 家长账号 → 关联到绑定的学生
                    student_id = user.bound_student_id
                elif user.role in (UserRole.MS_ADMIN, UserRole.GRADE_LEADER, UserRole.CLASS_TEACHER):
                    # 教师账号 → 记录为教师操作
                    teacher_id = user.id
                else:
                    # 其他角色尝试用 bound_student_id
                    if user.bound_student_id:
                        student_id = user.bound_student_id
                    else:
                        teacher_id = user.id

            record = TranslationRecord(
                school_id=school_id,
                question_text=request.question_text,
                grade_level=request.grade_level,
                knowledge_point=request.knowledge_point,
                llm_response=raw_response,
                student_id=student_id,
                teacher_id=teacher_id,
            )
            db.add(record)
            await db.commit()
            await db.refresh(record)
            record_id = record.id
        except Exception as e:
            logger.error(f"保存翻译记录失败: {e}")
            await db.rollback()

        return TranslateResponse(
            translations=translations,
            suggested_variables=suggested_vars,
            raw_llm_response=raw_response,
            translation_id=record_id,
        )

    @staticmethod
    async def get_history(
        db: AsyncSession,
        school_id: int = 1,
        limit: int = 20,
    ) -> list[TranslationRecord]:
        """获取翻译历史"""
        result = await db.execute(
            select(TranslationRecord)
            .where(TranslationRecord.school_id == school_id)
            .order_by(TranslationRecord.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())


# ═══════════════════════════════════════════════════════════
# DeepSeek 调用工具函数
# ═══════════════════════════════════════════════════════════

def _call_deepseek(prompt: str, system_prompt: str, timeout: int = 60) -> tuple[dict, Optional[str]]:
    """调用 DeepSeek API，返回 (响应dict, 错误信息)

    Returns:
        tuple[dict, Optional[str]]: (LLM 响应 JSON, 错误信息)
    """
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(
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
                    "max_tokens": 4096,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            return json.loads(content), None
    except httpx.HTTPStatusError as e:
        return {}, f"HTTP {e.response.status_code}: {e.response.text[:200]}"
    except httpx.TimeoutException:
        return {}, "请求超时（60秒）"
    except json.JSONDecodeError as e:
        return {}, f"JSON 解析失败: {e}"
    except Exception as e:
        return {}, f"未知错误: {e}"


# ═══════════════════════════════════════════════════════════
# 教师端学情报表服务
# ═══════════════════════════════════════════════════════════

def _parse_time_range(time_range: str) -> datetime:
    """将时间范围字符串转换为截止时间"""
    now = datetime.now()
    r = (time_range or "30d").strip().lower()
    if r == "7d":
        return now - timedelta(days=7)
    elif r == "30d":
        return now - timedelta(days=30)
    elif r == "semester":
        return now - timedelta(days=180)
    elif r == "all":
        return now - timedelta(days=3650)
    else:
        return now - timedelta(days=30)


async def _get_class_student_ids(db: AsyncSession, school_id: int, class_id: int) -> dict[int, str]:
    """获取班级内所有学生的 {id: name} 映射 — 从 students 表查询"""
    result = await db.execute(
        select(Student.id, Student.name)
        .where(
            Student.class_id == class_id,
            Student.school_id == school_id,
            Student.is_active == True,
        )
    )
    return {row[0]: row[1] for row in result.all()}


class ReportService:
    """教师端学情报表服务 — 班级维度聚合 TranslationRecord 数据"""

    @staticmethod
    async def get_class_kpi(
        db: AsyncSession,
        school_id: int,
        class_id: int,
        time_range: str = "30d",
    ) -> MathReportKPI:
        """获取班级整体 KPI 概览与趋势

        - active_students: 有过翻译记录的学生数
        - total_translations: 总翻译次数
        - avg_queries_per_student: 人均翻译次数
        - risk_students_count: 有活跃 RDI 风险预警的学生数
        - trend_data: 按日翻译次数趋势
        """
        cutoff = _parse_time_range(time_range)

        # ── 获取班级学生列表 ─────────────────────
        student_map = await _get_class_student_ids(db, school_id, class_id)
        student_ids = list(student_map.keys())

        if not student_ids:
            return MathReportKPI(
                active_students=0,
                total_translations=0,
                avg_queries_per_student=0.0,
                risk_students_count=0,
                trend_data=[],
            )

        # ── 活跃学生数 + 总翻译次数 ────────────────
        stats_result = await db.execute(
            select(
                func.count(func.distinct(TranslationRecord.student_id)),
                func.count(TranslationRecord.id),
            ).where(
                TranslationRecord.student_id.in_(student_ids),
                TranslationRecord.school_id == school_id,
                TranslationRecord.created_at >= cutoff,
            )
        )
        active, total = stats_result.one()
        active = active or 0
        total = total or 0

        # ── RDI 风险学生数 ─────────────────────────
        risk_result = await db.execute(
            select(func.count(func.distinct(RiskWarning.student_id)))
            .where(
                RiskWarning.student_id.in_(student_ids),
                RiskWarning.school_id == school_id,
                RiskWarning.risk_level.in_(["attention", "intervention"]),
            )
        )
        risk_count = risk_result.scalar() or 0

        # ── 按日趋势 ──────────────────────────────
        trend_rows = await db.execute(
            select(
                func.date(TranslationRecord.created_at).label("day"),
                func.count(TranslationRecord.id).label("cnt"),
            )
            .where(
                TranslationRecord.student_id.in_(student_ids),
                TranslationRecord.school_id == school_id,
                TranslationRecord.created_at >= cutoff,
            )
            .group_by(func.date(TranslationRecord.created_at))
            .order_by(func.date(TranslationRecord.created_at).asc())
        )
        trend = [
            TrendDataPoint(date=str(row.day), count=row.cnt)
            for row in trend_rows.all()
        ]

        avg = round(total / active, 1) if active > 0 else 0.0

        return MathReportKPI(
            active_students=active,
            total_translations=total,
            avg_queries_per_student=avg,
            risk_students_count=risk_count,
            trend_data=trend,
        )

    @staticmethod
    async def get_blind_spots(
        db: AsyncSession,
        school_id: int,
        class_id: int,
        time_range: str = "30d",
    ) -> list[BlindSpotItem]:
        """获取审题盲区排行 — 高频知识点 = 薄弱环节

        聚合 TranslationRecord.knowledge_point 的频次,
        最高频的 TOP 10 作为班级审题盲区。
        """
        cutoff = _parse_time_range(time_range)

        # ── 获取班级学生列表 ─────────────────────
        student_map = await _get_class_student_ids(db, school_id, class_id)
        student_ids = list(student_map.keys())

        if not student_ids:
            return []

        # ── 按知识点聚合频次 ───────────────────────
        rows = await db.execute(
            select(
                TranslationRecord.knowledge_point,
                func.count(TranslationRecord.id).label("cnt"),
            )
            .where(
                TranslationRecord.student_id.in_(student_ids),
                TranslationRecord.school_id == school_id,
                TranslationRecord.created_at >= cutoff,
                TranslationRecord.knowledge_point.isnot(None),
            )
            .group_by(TranslationRecord.knowledge_point)
            .order_by(func.count(TranslationRecord.id).desc())
            .limit(10)
        )

        spots = []
        for row in rows.all():
            knowledge = row.knowledge_point or "未分类"
            freq = row.cnt
            error_type = _classify_error_type(knowledge)
            spots.append(BlindSpotItem(
                term=knowledge,
                frequency=freq,
                error_type=error_type,
            ))

        return spots

    @staticmethod
    async def get_student_usage(
        db: AsyncSession,
        school_id: int,
        class_id: int,
    ) -> list[StudentUsageItem]:
        """获取学生个体学情下钻 — 每人翻译使用量 + 盲区 + 自主学习指数

        同时交叉查询 RDI 风险预警状态。
        independence_score: 查询越少 → 独立性越高（100=完全自主, 低=高依赖）
        """
        # ── 获取班级学生列表 ─────────────────────
        student_map = await _get_class_student_ids(db, school_id, class_id)
        student_ids = list(student_map.keys())

        if not student_ids:
            return []

        # ── 每个学生的翻译次数 ─────────────────────
        student_stats = await db.execute(
            select(
                TranslationRecord.student_id,
                func.count(TranslationRecord.id).label("cnt"),
            )
            .where(
                TranslationRecord.student_id.in_(student_ids),
                TranslationRecord.school_id == school_id,
            )
            .group_by(TranslationRecord.student_id)
        )
        stats = {row.student_id: row.cnt for row in student_stats.all()}

        # ── 每个人的最高频知识点（用 ORM 替代原始 SQL）──
        # 先查所有学生的 knowledge_point 聚合
        kp_rows = await db.execute(
            select(
                TranslationRecord.student_id,
                TranslationRecord.knowledge_point,
                func.count(TranslationRecord.id).label("cnt"),
            )
            .where(
                TranslationRecord.student_id.in_(student_ids),
                TranslationRecord.school_id == school_id,
                TranslationRecord.knowledge_point.isnot(None),
            )
            .group_by(TranslationRecord.student_id, TranslationRecord.knowledge_point)
            .order_by(TranslationRecord.student_id, func.count(TranslationRecord.id).desc())
        )
        # 取每个 student_id 的第一行（最高频）
        top_blind_map: dict[int, str] = {}
        for row in kp_rows.all():
            sid = row.student_id
            if sid not in top_blind_map:
                top_blind_map[sid] = row.knowledge_point or "未分类"

        # ── RDI 风险状态 ──────────────────────────
        risk_rows = await db.execute(
            select(RiskWarning.student_id, RiskWarning.risk_level)
            .where(
                RiskWarning.student_id.in_(student_ids),
                RiskWarning.school_id == school_id,
            )
        )
        risk_map: dict[int, str] = {}
        for row in risk_rows.all():
            existing = risk_map.get(row.student_id)
            if existing is None or _risk_priority(row.risk_level) > _risk_priority(existing):
                risk_map[row.student_id] = row.risk_level

        # ── 计算自主学习指数 ──────────────────────
        # 逻辑: 查询越少 → 独立性越高
        # 公式: 100 - (query_count / max_cnt * 80)
        # 查询最多的学生得 20 分（高依赖），查询 0 次的得 100 分（完全自主）
        max_cnt = max(stats.values()) if stats else 1

        # ── 组装结果 ──────────────────────────────
        items = []
        for sid in student_ids:
            query_count = stats.get(sid, 0)
            if max_cnt > 0 and query_count > 0:
                independence = round(max(0, 100 - (query_count / max_cnt * 80)), 1)
            else:
                independence = 100.0

            items.append(StudentUsageItem(
                student_id=sid,
                student_name=student_map.get(sid, f"学生{sid}"),
                query_count=query_count,
                top_blind_spot=top_blind_map.get(sid, "暂无数据"),
                independence_score=independence,
                rdi_status=_rdi_status_label(risk_map.get(sid)),
            ))

        # 按 query_count 降序排列（最需要关注的学生排前面）
        items.sort(key=lambda x: x.query_count, reverse=True)
        return items


# ═══════════════════════════════════════════════════════════
# ReportService 辅助函数
# ═══════════════════════════════════════════════════════════

def _classify_error_type(knowledge_point: str) -> str:
    """根据知识点名称推断错误类型标签"""
    k = knowledge_point.lower() if knowledge_point else ""
    if any(w in k for w in ["方程", "不等式"]):
        return "等量关系建模困难"
    elif any(w in k for w in ["函数", "图像"]):
        return "函数概念混淆"
    elif any(w in k for w in ["几何", "三角形", "勾股", "四边形", "圆"]):
        return "几何直观不足"
    elif any(w in k for w in ["因式分解", "整式", "分式"]):
        return "代数运算薄弱"
    elif any(w in k for w in ["应用题", "行程", "工程", "利润", "浓度"]):
        return "情境转译障碍"
    elif any(w in k for w in ["统计", "概率"]):
        return "数据解读偏差"
    else:
        return "审题理解障碍"


def _risk_priority(risk_level: str) -> int:
    """风险等级 → 优先级数值（越大越严重）"""
    priorities = {"intervention": 3, "attention": 2, "normal": 1}
    return priorities.get(risk_level, 0)


def _rdi_status_label(risk_level: Optional[str]) -> str:
    """RDI risk_level → 前端状态标签"""
    if not risk_level or risk_level == "normal":
        return "safe"
    elif risk_level == "attention":
        return "warning"
    elif risk_level == "intervention":
        return "danger"
    return "safe"
