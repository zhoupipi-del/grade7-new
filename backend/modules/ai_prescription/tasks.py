"""
AI 德育处方大脑 — Celery 异步任务
并轨复用 wings3-celery.service（Redis DB 2/3）
双核心任务：班级诊断 + 学生干预
内置 DeepSeek 熔断器（max_retries=3, 指数退避）
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone

import httpx
from celery import Task
from celery.exceptions import Retry
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

from modules.ai_prescription.models import (
    AIPrescription,
    PrescriptionType,
    RiskLevel,
)
from modules.reports.celery_app import celery_engine

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# 数据库 URL（Worker 进程用，从环境变量读取，本地兜底）
# ─────────────────────────────────────────────
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "mysql+aiomysql://grade7:waOPKoyFf4ByQD1h@127.0.0.1:3307/wings3"
)
DATABASE_URL_SYNC = os.environ.get(
    "DATABASE_URL_SYNC",
    "mysql+pymysql://grade7:waOPKoyFf4ByQD1h@127.0.0.1:3307/wings3"
)
_SessionLocal: scoped_session | None = None


def _get_sync_session():
    """获取同步 DB session（Worker 进程内单例）"""
    global _sync_engine, _SessionLocal
    if _SessionLocal is None:
        _sync_engine = create_engine(
            DATABASE_URL_SYNC,
            pool_size=2,
            max_overflow=4,
            pool_pre_ping=True,
            pool_recycle=300,
        )
        _SessionLocal = scoped_session(
            sessionmaker(bind=_sync_engine, expire_on_commit=False)
        )
    return _SessionLocal()


# ─────────────────────────────────────────────
# DeepSeek 配置（从 systemd 环境变量读取）
# ─────────────────────────────────────────────
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_API_URL = os.environ.get(
    "LLM_API_URL",
    "https://api.deepseek.com/v1/chat/completions"
)
LLM_MODEL = os.environ.get("LLM_MODEL", "deepseek-chat")

# 熔断器：连续失败 3 次 → 冷却 60s
_circuit_failures = 0
_circuit_cooldown_until = 0.0
_CIRCUIT_THRESHOLD = 3
_CIRCUIT_COOLDOWN = 60  # seconds


def _call_deepseek(prompt: str, system_prompt: str, timeout: int = 60) -> dict:
    """
    调用 DeepSeek API，带熔断器 + 超时控制
    返回解析后的 JSON dict
    """
    global _circuit_failures, _circuit_cooldown_until

    # 熔断器检查
    if _circuit_failures >= _CIRCUIT_THRESHOLD:
        if time.time() < _circuit_cooldown_until:
            raise RuntimeError("LLM 熔断器开启中，暂时不可用")
        else:
            # 冷却结束，重置
            _circuit_failures = 0

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
                    "max_tokens": 2048,
                },
            )
            resp.raise_for_status()
            data = resp.json()

        # 解析 LLM 输出
        content = data["choices"][0]["message"]["content"]
        result = json.loads(content)

        # 成功 → 重置熔断器
        _circuit_failures = 0
        return result

    except Exception as exc:
        _circuit_failures += 1
        if _circuit_failures >= _CIRCUIT_THRESHOLD:
            _circuit_cooldown_until = time.time() + _CIRCUIT_COOLDOWN
            logger.error(
                "[AI-Tasks] 熔断器触发！连续失败 %s 次，冷却 %s 秒",
                _circuit_failures, _CIRCUIT_COOLDOWN
            )
        raise RuntimeError(f"DeepSeek 调用失败：{exc}") from exc


# ─────────────────────────────────────────────
# System Prompts
# ─────────────────────────────────────────────

SYSTEM_PROMPT_CLASS = """\
你是资深德育主任，擅长班级风气诊断与干预策略设计。

输出严格 JSON 格式（不要 Markdown 代码块包裹），包含以下字段：
- "risk_level": 字符串，"HIGH" / "MEDIUM" / "LOW"
- "summary": 字符串（2-3 句核心判断，不超过 100 字）
- "full_text": 字符串（完整 Markdown 诊断书，含以下章节：
    ## 一、班级风气评估
    ## 二、关键问题识别
    ## 三、干预策略建议（含具体班会设计方案）
    ## 四、预期效果与跟踪指标
  ）

诊断书需基于提供的数据客观分析，不得捏造数据。
措辞专业、可操作，避免空洞套话。
"""

SYSTEM_PROMPT_STUDENT = """\
你是资深德育主任 + 心理咨询师，擅长高风险学生心理干预话术设计。

输出严格 JSON 格式（不要 Markdown 代码块包裹），包含以下字段：
- "risk_level": 字符串，"HIGH" / "MEDIUM" / "LOW"
- "summary": 字符串（2-3 句核心判断，不超过 100 字）
- "full_text": 字符串（完整 Markdown 干预话术，含以下章节：
    ## 一、学生画像速览
    ## 二、威慑性谈话要点（校规依据 + 严肃后果）
    ## 三、同理心谈话脚手架（破冰 → 倾听 → 共情 → 引导）
    ## 四、家校协同建议
    ## 五、跟踪观察要点
  ）

话术需严格基于提供的数据，不得捏造事实。
威慑部分要有法理依据，同理心部分要有人文温度。
"""

# ─────────────────────────────────────────────
# Celery 任务
# ─────────────────────────────────────────────


@celery_engine.task(
    bind=True,
    name="ai_prescription.generate_class_diagnosis",
    max_retries=3,
    default_retry_delay=10,
)
def generate_class_diagnosis(
    self: Task,
    context: dict,
    creator_id: int,
    school_id: int,
) -> dict:
    """
    班级月度诊断（Celery 异步）
    返回：{status, record_id, risk_level, summary, full_text}
    """
    try:
        # 构建 Prompt
        prompt = _build_class_prompt(context)

        # 调用 DeepSeek
        logger.info("[AI-Tasks] 开始生成班级诊断：class_id=%s", context["class"]["id"])
        result = _call_deepseek(prompt, SYSTEM_PROMPT_CLASS)

        # 解析结果
        risk_level_str = result.get("risk_level", "LOW")
        summary = result.get("summary", "")
        full_text = result.get("full_text", "")

        # 校验风险等级
        try:
            risk_level = RiskLevel(risk_level_str)
        except ValueError:
            risk_level = RiskLevel.LOW

        # 落库（同步 session）
        db = _get_sync_session()
        try:
            record = AIPrescription(
                school_id=school_id,
                prescription_type=PrescriptionType.CLASS_DIAGNOSIS,
                target_id=context["class"]["id"],
                target_type="class",
                risk_level=risk_level,
                summary=summary[:500] if summary else None,
                full_text=full_text,
                raw_snapshot=context,
                creator_id=creator_id,
            )
            db.add(record)
            db.commit()
            record_id = record.id
        finally:
            db.close()

        logger.info("[AI-Tasks] 班级诊断完成：record_id=%s, risk=%s", record_id, risk_level)
        return {
            "status": "SUCCESS",
            "record_id": record_id,
            "risk_level": risk_level.value,
            "summary": summary,
        }

    except Exception as exc:
        logger.error("[AI-Tasks] 班级诊断失败：%s", exc, exc_info=True)
        # Celery 重试（指数退避）
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=2 ** self.request.retries * 5)
        # 超限：写入失败记录
        db = _get_sync_session()
        try:
            record = AIPrescription(
                school_id=school_id,
                prescription_type=PrescriptionType.CLASS_DIAGNOSIS,
                target_id=context.get("class", {}).get("id", 0),
                target_type="class",
                summary=f"任务失败：{str(exc)[:200]}",
                full_text=f"## 生成失败\n\n{str(exc)}",
                raw_snapshot=context,
                creator_id=creator_id,
            )
            db.add(record)
            db.commit()
        finally:
            db.close()
        return {"status": "FAILURE", "error": str(exc)}


@celery_engine.task(
    bind=True,
    name="ai_prescription.generate_student_intervention",
    max_retries=3,
    default_retry_delay=10,
)
def generate_student_intervention(
    self: Task,
    context: dict,
    creator_id: int,
    school_id: int,
) -> dict:
    """
    学生心理干预话术生成（Celery 异步）
    返回：{status, record_id, risk_level, summary, full_text}
    """
    try:
        # 构建 Prompt
        prompt = _build_student_prompt(context)

        # 调用 DeepSeek
        logger.info("[AI-Tasks] 开始生成学生干预话术：student_id=%s", context["student"]["id"])
        result = _call_deepseek(prompt, SYSTEM_PROMPT_STUDENT)

        # 解析结果
        risk_level_str = result.get("risk_level", "LOW")
        summary = result.get("summary", "")
        full_text = result.get("full_text", "")

        try:
            risk_level = RiskLevel(risk_level_str)
        except ValueError:
            risk_level = RiskLevel.LOW

        # 落库
        db = _get_sync_session()
        try:
            record = AIPrescription(
                school_id=school_id,
                prescription_type=PrescriptionType.STUDENT_INTV,
                target_id=context["student"]["id"],
                target_type="student",
                risk_level=risk_level,
                summary=summary[:500] if summary else None,
                full_text=full_text,
                raw_snapshot=context,
                creator_id=creator_id,
            )
            db.add(record)
            db.commit()
            record_id = record.id
        finally:
            db.close()

        logger.info("[AI-Tasks] 学生干预话术完成：record_id=%s, risk=%s", record_id, risk_level)
        return {
            "status": "SUCCESS",
            "record_id": record_id,
            "risk_level": risk_level.value,
            "summary": summary,
        }

    except Exception as exc:
        logger.error("[AI-Tasks] 学生干预话术失败：%s", exc, exc_info=True)
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=2 ** self.request.retries * 5)
        db = _get_sync_session()
        try:
            record = AIPrescription(
                school_id=school_id,
                prescription_type=PrescriptionType.STUDENT_INTV,
                target_id=context.get("student", {}).get("id", 0),
                target_type="student",
                summary=f"任务失败：{str(exc)[:200]}",
                full_text=f"## 生成失败\n\n{str(exc)}",
                raw_snapshot=context,
                creator_id=creator_id,
            )
            db.add(record)
            db.commit()
        finally:
            db.close()
        return {"status": "FAILURE", "error": str(exc)}


# ─────────────────────────────────────────────
# Prompt 构建器
# ─────────────────────────────────────────────

def _build_class_prompt(context: dict) -> str:
    """将班级上下文序列化为 LLM Prompt"""
    return f"""\
# 班级德育诊断请求

## 班级基本信息
- 班级 ID：{context["class"]["id"]}
- 班级名称：{context["class"]["name"]}
- 学生人数：{context["class"]["student_count"]} 人

## 分析周期
- 回溯天数：{context["analysis_period"]["days"]} 天
- 时间范围：{context["analysis_period"]["since"]} ~ {context["analysis_period"]["until"]}

## 考勤数据
- 出勤率：{context["attendance"]["attendance_rate"]}
- 全勤次数：{context["attendance"]["present"]}
- 迟到：{context["attendance"]["late"]} 次
- 缺勤：{context["attendance"]["absent"]} 次
- 请假：{context["attendance"]["leave"]} 次

## 违纪行为分布
- 总事件数：{context["behavior"]["total_incidents"]}
- 人均事件数：{context["behavior"]["incident_per_student"]}
- 分类统计：{json.dumps(context["behavior"]["by_category"], ensure_ascii=False)}

## 流动红旗历史（最近3次）
{_format_flag_history(context["red_flag"])}

## 活跃处分
- 当前处于 ACTIVE 处分状态的学生数：{context["active_sanctions_count"]} 人

## 素质评价五维平均分
- 德育：{context["evaluation_avg"]["moral"]}
- 智育：{context["evaluation_avg"]["academic"]}
- 体育：{context["evaluation_avg"]["sports"]}
- 美育：{context["evaluation_avg"]["arts"]}
- 劳育：{context["evaluation_avg"]["labor"]}

---
请基于以上数据，输出 JSON 格式诊断结果。
"""


def _build_student_prompt(context: dict) -> str:
    """将学生上下文序列化为 LLM Prompt"""
    return f"""\
# 学生心理干预话术生成请求

## 学生基本信息
- 学生 ID：{context["student"]["id"]}
- 姓名：{context["student"]["name"]}
- 性别：{context["student"]["gender"]}
- 班级 ID：{context["student"]["class_id"]}

## 分析周期
- 回溯天数：{context["analysis_period"]["days"]} 天
- 时间范围：{context["analysis_period"]["since"]} ~ {context["analysis_period"]["until"]}

## 考勤数据
- 出勤率：{context["attendance"]["attendance_rate"]}
- 全勤：{context["attendance"]["present"]} 次
- 迟到：{context["attendance"]["late"]} 次
- 缺勤：{context["attendance"]["absent"]} 次
- 请假：{context["attendance"]["leave"]} 次

## 违纪行为记录
- 总事件数：{context["behavior"]["total_incidents"]}
- 分类统计：{json.dumps(context["behavior"]["by_category"], ensure_ascii=False)}

## 活跃处分
{_format_sanctions(context["sanctions"])}

## 最新素质评价快照
{_format_score(context["evaluation"])}

## 学业趋势分析
{_format_academic_trend(context.get("academic_trend"))}

## RDI 风险诊断
{_format_rdi_diagnosis(context.get("rdi_diagnosis"))}

---
请基于以上数据，输出 JSON 格式干预话术。
请特别关注学业趋势与行为表现之间的交叉关联，以及 RDI 三维偏离度中哪个维度是主要风险源。
"""


# ─────────────────────────────────────────────
# 格式化辅助
# ─────────────────────────────────────────────

def _format_academic_trend(trend: dict | None) -> str:
    if not trend:
        return "（无多学期对比数据）"
    direction_cn = {"up": "上升", "down": "下降", "stable": "持平"}.get(trend["direction"], "未知")
    return (
        f"- 本学期（{trend['current_semester']}）：学业分={trend['current_academic']}，总分={trend['current_total']}\n"
        f"- 上学期（{trend['previous_semester']}）：学业分={trend['previous_academic']}，总分={trend['previous_total']}\n"
        f"- 学业分变化：{trend['delta']:+} 分（{direction_cn}）"
    )


def _format_rdi_diagnosis(rdi: dict | None) -> str:
    if not rdi:
        return "（无活跃 RDI 预警）"
    escalating = "是" if rdi["is_escalating"] else "否"
    return (
        f"- RDI 总分：{rdi['rdi_score']}（风险等级：{rdi['risk_level']}）\n"
        f"- 行为偏离度：{rdi['behavior_deviation']}\n"
        f"- 考勤偏离度：{rdi['attendance_deviation']}\n"
        f"- 学业偏离度：{rdi['score_deviation']}\n"
        f"- EWMA 趋势：{rdi['ewma_trend']}（是否恶化：{escalating}）\n"
        f"- 触发方式：{rdi['trigger']}，预警时间：{rdi['warned_at']}"
    )


def _format_flag_history(flag_list: list) -> str:
    if not flag_list:
        return "（无历史记录）"
    lines = []
    for f in flag_list:
        lines.append(
            f"- {f['period_label']}：得分 {f['final_score']}，"
            f"是否获奖：{'是' if f['has_flag'] else '否'}，"
            f"排名：{f['rank']}"
        )
    return "\n".join(lines)


def _format_sanctions(sanctions: list) -> str:
    if not sanctions:
        return "（无活跃处分）"
    lines = []
    for s in sanctions:
        lines.append(f"- {s['level']}：{s['reason']}（{s['created_at'][:10]}）")
    return "\n".join(lines)


def _format_score(score: dict | None) -> str:
    if not score:
        return "（无评价记录）"
    return (
        f"- 德育：{score['moral']}，智育：{score['academic']}，"
        f"体育：{score['health']}，美育：{score['art']}，劳育：{score['social']}\n"
        f"- 总分：{score['total']}，"
        f"学期：{score['semester']}"
    )


# ═══════════════════════════════════════════════════════════════
# Phase 2C: RDI → AI 处方 → 审批工单 全自动桥接
# ═══════════════════════════════════════════════════════════════

import asyncio
from datetime import datetime as _dt

from sqlalchemy import create_engine as _create_engine
from sqlalchemy.ext.asyncio import create_async_engine as _create_async_engine
from sqlalchemy.ext.asyncio import AsyncSession as _AsyncSession
from sqlalchemy.ext.asyncio import async_sessionmaker as _async_sm
from sqlalchemy import select as _select, text as _text

# 异步引擎 (仅用于 build_student_context)
_ASYNC_DB_URL = os.environ.get(
    "DATABASE_URL",
    "mysql+aiomysql://grade7:waOPKoyFf4ByQD1h@127.0.0.1:3307/wings3",
)
_async_engine = _create_async_engine(_ASYNC_DB_URL, pool_pre_ping=True, pool_recycle=300, pool_size=2)
_AsyncSessionLocal = _async_sm(_async_engine, class_=_AsyncSession, expire_on_commit=False)


async def _build_context_async(student_id: int, school_id: int) -> dict:
    """异步构建学生上下文 (委托给 AIPrescriptionAggregator)"""
    from modules.ai_prescription.aggregator import AIPrescriptionAggregator

    await _async_engine.dispose()  # Celery prefork stale 连接清理
    async with _AsyncSessionLocal() as db:
        ctx = await AIPrescriptionAggregator.build_student_context(
            db, student_id=student_id, school_id=school_id, days=30
        )
    await _async_engine.dispose()
    return ctx


def _find_class_teacher(sync_db, student_id: int, school_id: int) -> int | None:
    """查询学生的班主任 user_id"""
    from core.models import User, UserRole, Student

    # 1. 获取学生的 class_id
    student = sync_db.execute(
        _text("SELECT class_id FROM students WHERE id = :sid AND school_id = :scid"),
        {"sid": student_id, "scid": school_id},
    ).fetchone()
    if not student or not student.class_id:
        return None

    # 2. 查询该班的班主任
    teacher = sync_db.query(User).filter(
        User.school_id == school_id,
        User.role == UserRole.CLASS_TEACHER,
        User.class_id == student.class_id,
        User.is_active == True,
    ).first()
    return teacher.id if teacher else None


def _create_approval_request(
    sync_db,
    student_id: int,
    school_id: int,
    prescription_id: int,
    warning_id: int,
    rdi_score: float,
) -> int:
    """创建审批工单 — 将 AI 处方挂接到审批链

    三级 Fallback:
      1. TenantApprovalChain (多租户自定义审批链)
      2. PolicyEngine (policy.yaml 统一规则)
      3. 硬编码默认链 (班主任+年级组长 parallel_or, 48h escalate)
    """
    from modules.evaluation.models import ApprovalRequest

    # 幂等检查: 同一 warning_id 不重复创建
    existing = sync_db.query(ApprovalRequest).filter(
        ApprovalRequest.school_id == school_id,
        ApprovalRequest.source_type == "ai_prescription",
        ApprovalRequest.source_id == warning_id,
        ApprovalRequest.current_status == "pending",
    ).first()
    if existing:
        logger.info("[BRIDGE] 幂等跳过: warning_id=%s 已有 pending 审批工单 #%s", warning_id, existing.id)
        return existing.id

    # L1: 尝试多租户审批链
    chain_config = None
    try:
        from modules.approval.services import resolve_chain
        chain_config = resolve_chain(sync_db, school_id, "ai_intervention")
        if chain_config:
            logger.info("[BRIDGE] 使用多租户审批链 | school=%s chain_id=%s", school_id, chain_config.get("chain_id"))
    except Exception as e:
        logger.warning("[BRIDGE] 多租户审批链查询失败(降级到默认): %s", e)

    # L2: Fallback — 硬编码默认链
    if not chain_config:
        chain_config = {
            "total_timeout_hours": 48,
            "escalation_strategy": "escalate",
            "nodes": [
                {
                    "role": "class_teacher",
                    "status": "pending",
                    "approver_id": None,
                    "approved_at": None,
                    "comment": None,
                },
                {
                    "role": "grade_leader",
                    "status": "pending",
                    "approver_id": None,
                    "approved_at": None,
                    "comment": None,
                },
            ],
        }
        logger.info("[BRIDGE] 使用默认审批链 | school=%s", school_id)

    ar = ApprovalRequest(
        school_id=school_id,
        student_id=student_id,
        event_type="ai_intervention",
        source_type="ai_prescription",
        source_id=warning_id,  # 用 warning_id 做幂等键
        severity="major",
        approval_mode="parallel_or",
        chain_config=chain_config,
        current_status="pending",
        current_step=0,
    )
    sync_db.add(ar)
    sync_db.commit()
    sync_db.refresh(ar)
    logger.info(
        "[BRIDGE] 审批工单已创建 | ar_id=%s student=%s prescription=%s warning=%s rdi=%.2f",
        ar.id, student_id, prescription_id, warning_id, rdi_score,
    )
    return ar.id


def _try_notify_class_teacher(
    sync_db,
    teacher_id: int,
    school_id: int,
    student_id: int,
    prescription_id: int,
    ar_id: int,
    rdi_score: float,
):
    """通知班主任 — 解耦: 失败不影响主流程"""
    try:
        from modules.notifications.models import Notification

        notif = Notification(
            school_id=school_id,
            recipient_id=teacher_id,
            sender_id=None,  # 系统通知
            type="ai_intervention",
            title=f"AI 干预处方待审批 (RDI={rdi_score:.2f})",
            body=(
                f"系统检测到您的学生存在高危风险偏离 (RDI={rdi_score:.2f})，\n"
                f"AI 已自动生成干预话术处方 (#{prescription_id})。\n"
                f"请尽快查看并审批。审批工单编号: #{ar_id}"
            ),
            entity_type="ai_prescription",
            entity_id=prescription_id,
            is_read=False,
        )
        sync_db.add(notif)
        sync_db.commit()
        logger.info("[BRIDGE] 班主任通知已发送 | teacher=%s ar=%s", teacher_id, ar_id)
    except Exception as exc:
        logger.warning("[BRIDGE] 通知发送失败 (不影响主流程): %s", exc)


@celery_engine.task(
    bind=True,
    name="ai_prescription.bridge_rdi_to_approval",
    max_retries=2,
    default_retry_delay=30,
)
def bridge_rdi_to_approval(
    self: Task,
    student_id: int,
    school_id: int,
    warning_id: int,
    rdi_score: float,
) -> dict:
    """
    Phase 2C 全自动桥接: RDI intervention → AI 处方 → 审批工单 → 通知班主任

    触发条件: risk_models RDI 扫描发现 risk_level == 'intervention'
    执行队列: high_priority (含 LLM 调用, 预计 10-30s)

    流程:
      1. 构建学生黄金上下文 (async → asyncio.run 桥接)
      2. 调用 DeepSeek 生成干预话术
      3. 落库 ai_prescriptions
      4. 创建 approval_requests (幂等: 同一 warning 仅创建一次)
      5. 通知班主任 (try/except 解耦)
    """
    t0 = time.time()
    logger.info(
        "[BRIDGE] 桥接启动 | student=%s school=%s warning=%s rdi=%.2f",
        student_id, school_id, warning_id, rdi_score,
    )

    try:
        # ── Step 1: 构建学生上下文 ──
        context = asyncio.run(_build_context_async(student_id, school_id))
        logger.info("[BRIDGE] 上下文构建完成 | student=%s", student_id)

        # ── Step 2: 调用 DeepSeek 生成干预话术 ──
        prompt = _build_student_prompt(context)
        result = _call_deepseek(prompt, SYSTEM_PROMPT_STUDENT)

        risk_level_str = result.get("risk_level", "HIGH")
        summary = result.get("summary", "")
        full_text = result.get("full_text", "")

        try:
            risk_level = RiskLevel(risk_level_str)
        except ValueError:
            risk_level = RiskLevel.HIGH

        # ── Step 3: 落库 ai_prescriptions ──
        db = _get_sync_session()
        try:
            record = AIPrescription(
                school_id=school_id,
                prescription_type=PrescriptionType.STUDENT_INTV,
                target_id=student_id,
                target_type="student",
                risk_level=risk_level,
                summary=summary[:500] if summary else None,
                full_text=full_text,
                raw_snapshot={
                    **context,
                    "trigger": "rdi_bridge",
                    "warning_id": warning_id,
                    "rdi_score": rdi_score,
                },
                creator_id=0,  # 0 = 系统
            )
            db.add(record)
            db.commit()
            db.refresh(record)
            prescription_id = record.id
        finally:
            db.close()

        logger.info(
            "[BRIDGE] AI 处方已生成 | prescription_id=%s risk=%s",
            prescription_id, risk_level.value,
        )

        # ── Step 4: 创建审批工单 ──
        db = _get_sync_session()
        try:
            ar_id = _create_approval_request(
                db, student_id, school_id, prescription_id, warning_id, rdi_score
            )

            # ── Step 5: 通知班主任 ──
            teacher_id = _find_class_teacher(db, student_id, school_id)
            if teacher_id:
                _try_notify_class_teacher(
                    db, teacher_id, school_id, student_id,
                    prescription_id, ar_id, rdi_score,
                )
            else:
                logger.warning(
                    "[BRIDGE] 未找到班主任 | student=%s — 跳过通知",
                    student_id,
                )
        finally:
            db.close()

        elapsed = round(time.time() - t0, 2)
        logger.info(
            "[BRIDGE] 桥接完成 | student=%s prescription=%s ar=%s 耗时=%.2fs",
            student_id, prescription_id, ar_id, elapsed,
        )

        return {
            "status": "SUCCESS",
            "student_id": student_id,
            "prescription_id": prescription_id,
            "approval_request_id": ar_id,
            "risk_level": risk_level.value,
            "elapsed_s": elapsed,
        }

    except Exception as exc:
        logger.error(
            "[BRIDGE] 桥接失败 | student=%s warning=%s: %s",
            student_id, warning_id, exc,
            exc_info=True,
        )
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=2 ** self.request.retries * 10)
        return {"status": "FAILURE", "student_id": student_id, "error": str(exc)}
