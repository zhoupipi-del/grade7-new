"""
AI 德育处方大脑 — Celery 异步任务 V3
并轨复用 wings3-celery.service（Redis DB 2/3）
双核心任务：班级诊断 + 学生干预
内置 DeepSeek 熔断器（max_retries=3, 指数退避）

V3 升维 (Task #1448 — AIContextHydrator):
  - _build_student_prompt 新增5段数据序列化:
    成长时光轴 / 五维快照 / 作业批改 / 错题断层 / 心理深度档案
  - SYSTEM_PROMPT_STUDENT 升级三段铁闸规则:
    Fact段: 综合时光轴事件流 + 五维快照 + 知识断层 + 心理档案 + 作业数据
    Analysis段: 五维交叉归因链 (行为×学业×心理×考勤×知识断层)
    Growth段: 针对知识断层补习方向 + 作业管理策略 + 尊重已有咨询关系
  - 新增5个格式化辅助函数:
    _format_growth_timeline / _format_growth_snapshot / _format_homework
    _format_error_funnel / _format_psych_deep
"""

from __future__ import annotations

import json
import logging
import os
import time

import httpx
from celery import Task
from modules.ai_prescription.models import (
    AIPrescription,
    PrescriptionType,
    RiskLevel,
)
from modules.reports.celery_app import celery_engine
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# 数据库 URL（Worker 进程用，从环境变量读取，本地兜底）
# ─────────────────────────────────────────────
from core.db_utils import require_db_url, require_sync_db_url

DATABASE_URL = require_db_url()
DATABASE_URL_SYNC = require_sync_db_url()
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
        _SessionLocal = scoped_session(sessionmaker(bind=_sync_engine, expire_on_commit=False))
    return _SessionLocal()


# ─────────────────────────────────────────────
# DeepSeek 配置（从 systemd 环境变量读取）
# ─────────────────────────────────────────────
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_API_URL = os.environ.get("LLM_API_URL", "https://api.deepseek.com/v1/chat/completions")
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
                    "max_tokens": 4096,
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
                _circuit_failures,
                _CIRCUIT_COOLDOWN,
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
你是 Wings 3.0 德育处方引擎 V3，由资深德育主任 + 临床心理咨询师 + 学业诊断专家三轨驱动。

输出严格 JSON 格式（不要 Markdown 代码块包裹），包含以下字段：
- "risk_level": 字符串，"HIGH" / "MEDIUM" / "LOW"
- "summary": 字符串（2-3 句核心判断，不超过 100 字）
- "fact": 字符串（Markdown 事实陈述段，临床严谨风格）
- "analysis": 字符串（Markdown 交叉归因段，诊断推理风格）
- "growth": 字符串（Markdown 递进干预段，实操话术风格）
- "full_text": 字符串（完整 Markdown 干预处方 = fact + analysis + growth 合辑）

## 三段铁闸规则

### Fact 段（事实陈述 — 临床严谨）
- 只陈述数据事实，σ 值精确表达（如 "行为偏离度 2.83σ"），禁止模糊词（"偏高""较差"）
- 列出四维偏离度绝对值 + 心理10维因子最高偏离维度（含 σ 值）
- 如触发一票否决（psych_veto_triggered=True），必须标注 ⚠️ PSYCH_VETO
- 综合成长时光轴事件流（growth_timeline），按时间序列列出关键事件节点
- 如有成长五维快照（growth_snapshot），列出五维得分并标注偏离常态的维度
- 如有知识断层（error_funnel），列出 critical 级断层知识点及连续错误次数
- 如有心理综合档案（psych_deep），引用风险等级、历史最高风险及咨询/筛查频次
- 如有作业数据（homework），列出平均得分率、迟交次数和错题总数
- 语气：冷静、精确、不评价

### Analysis 段（交叉归因 — 诊断推理）
- 从事实出发，建立行为×学业×心理×考勤×知识断层 的五维交叉归因链
- 识别风险主驱动力（哪维偏离最大）和次驱动力
- 区分"表面现象"与"根因机制"：
  · 违纪频发可能是焦虑的外显而非品德问题
  · 知识断层 critical 级可能是学业焦虑的源头而非学习态度问题
  · 作业迟交+错题高发可能指向基础薄弱而非敷衍
  · 心理咨询历史中的 consult_category 可揭示行为问题的深层动因
- 综合成长快照趋势：对比五维得分的历史变化，判断是改善还是恶化
- 语气：推理、归因、有判断力

### Growth 段（递进干预 — 实操话术）
- 三层递进：
  1. 班主任话术层：可直接使用的谈话要点（开场→破冰→引导→收束），含具体措辞
     · 如有知识断层，针对性建议补习方向和知识点优先级
     · 如有作业问题，建议作业管理和完成策略
  2. 心理切入层：针对极端维度的专业干预建议（如 CBT 认知重构、行为契约等）
     · 如有 psych_deep 咨询历史，尊重已有咨询关系，避免重复建议
     · 如有 is_crisis=True 或 risk_level=red，必须标注需升级专业心理干预
  3. 家校边界层：家长沟通边界 + 何时升级到专业心理干预 + 48h 跟踪复查节奏
- 语气：实操、可执行、有温度但不失边界

严格基于提供的数据生成，不得捏造事实或虚构数值。
数据中标注为 null 或"（无）"的字段，表示该数据源暂无记录，分析时不应假设或推断。
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
            raise self.retry(exc=exc, countdown=2**self.request.retries * 5)
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
    V2: LLM 输出 Fact→Analysis→Growth 三段式，segments 存入 raw_snapshot.llm_output
    返回：{status, record_id, risk_level, summary, full_text, segments}
    """
    try:
        # 构建 Prompt
        prompt = _build_student_prompt(context)

        # 调用 DeepSeek
        logger.info("[AI-Tasks] 开始生成学生干预处方 (V3)：student_id=%s", context["student"]["id"])
        result = _call_deepseek(prompt, SYSTEM_PROMPT_STUDENT)

        # 解析结果 — V2 三段式
        risk_level_str = result.get("risk_level", "LOW")
        summary = result.get("summary", "")
        full_text = result.get("full_text", "")
        fact_text = result.get("fact", "")
        analysis_text = result.get("analysis", "")
        growth_text = result.get("growth", "")

        # 兜底: 如果 LLM 未返回 full_text，自动拼接三段
        if not full_text and (fact_text or analysis_text or growth_text):
            full_text = f"{fact_text}\n\n{analysis_text}\n\n{growth_text}"

        try:
            risk_level = RiskLevel(risk_level_str)
        except ValueError:
            risk_level = RiskLevel.LOW

        # 落库 — raw_snapshot 新增 llm_output 子键存三段
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
                raw_snapshot={
                    **context,
                    "llm_output": {
                        "fact": fact_text,
                        "analysis": analysis_text,
                        "growth": growth_text,
                        "risk_level": risk_level_str,
                        "summary": summary,
                    },
                },
                creator_id=creator_id,
            )
            db.add(record)
            db.commit()
            record_id = record.id
        finally:
            db.close()

        logger.info(
            "[AI-Tasks] 学生干预处方完成 (V3)：record_id=%s, risk=%s", record_id, risk_level
        )
        return {
            "status": "SUCCESS",
            "record_id": record_id,
            "risk_level": risk_level.value,
            "summary": summary,
            "segments": {
                "fact": fact_text,
                "analysis": analysis_text,
                "growth": growth_text,
            },
        }

    except Exception as exc:
        logger.error("[AI-Tasks] 学生干预话术失败：%s", exc, exc_info=True)
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=2**self.request.retries * 5)
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
    """将学生上下文序列化为 LLM Prompt (V3: 四维RDI + 心理10维 + 历史时间线
    + 成长时光轴 + 五维快照 + 作业批改 + 错题断层 + 心理深度档案)"""
    return f"""\
# Wings 3.0 德育处方生成请求

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

## RDI 四维风险诊断
{_format_rdi_diagnosis(context.get("rdi_diagnosis"))}

## 心理10维因子详情
{_format_psych_profile(context.get("psych_profile"))}

## 历史事件时间线
{_format_timeline(context.get("timeline"))}

## 成长时光轴事件流 (V3)
{_format_growth_timeline(context.get("growth_timeline"))}

## 周期成长五维快照 (V3)
{_format_growth_snapshot(context.get("growth_snapshot"))}

## 作业提交与批改数据 (V3)
{_format_homework(context.get("homework"))}

## 错题本与知识断层 (V3)
{_format_error_funnel(context.get("error_funnel"))}

## 心理综合档案与咨询记录 (V3)
{_format_psych_deep(context.get("psych_deep"))}

---
请基于以上数据，严格按 Fact→Analysis→Growth 三段铁闸规则输出 JSON。
重点关注：四维偏离度中哪个维度是主驱动力，心理10维是否有极端偏离因子，
成长快照五维趋势是否恶化，知识断层 critical 级是否与学业焦虑存在因果链，
以及行为、学业、心理、知识断层四者之间的交叉归因关系。
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
    """格式化四维 RDI 风险诊断 (V2: 含心理偏离度 + 一票否决标注)"""
    if not rdi:
        return "（无活跃 RDI 预警）"
    escalating = "是" if rdi["is_escalating"] else "否"
    veto_flag = ""
    if rdi.get("psych_veto_triggered"):
        veto_flag = (
            f"\n- ⚠️ 心理一票否决已触发 (PSYCH_VETO)，否决维度：{rdi.get('veto_dimension', '未知')}"
        )
    psych_dev_line = ""
    if rdi.get("psych_deviation") is not None:
        psych_dev_line = f"\n- 心理偏离度：{rdi['psych_deviation']}σ"
    return (
        f"- RDI 总分：{rdi['rdi_score']}（风险等级：{rdi['risk_level']}）\n"
        f"- 行为偏离度：{rdi['behavior_deviation']}σ\n"
        f"- 考勤偏离度：{rdi['attendance_deviation']}σ\n"
        f"- 学业偏离度：{rdi['score_deviation']}σ"
        f"{psych_dev_line}"
        f"{veto_flag}\n"
        f"- EWMA 趋势：{rdi['ewma_trend']}（是否恶化：{escalating}）\n"
        f"- 触发方式：{rdi['trigger']}，预警时间：{rdi['warned_at']}"
    )


def _format_psych_profile(profile: dict | None) -> str:
    """格式化心理10维因子详情 (V2 新增)"""
    if not profile:
        return "（无心理筛查数据）"
    lines = []
    lines.append(f"- 问卷类型：{profile['survey_type']}，总分：{profile.get('total_score', 'N/A')}")
    lines.append(f"- 完成时间：{profile.get('completed_at', 'N/A')}")
    for dim in profile.get("dimensions", []):
        extreme_tag = " ★极端" if dim.get("is_extreme") else ""
        lines.append(f"  · {dim['label']}：{dim['score']}σ{extreme_tag}")
    if profile.get("extreme_dimension_cn"):
        lines.append(
            f"- 最高偏离维度：{profile['extreme_dimension_cn']} ({profile['extreme_value']}σ)"
        )
    return "\n".join(lines)


def _format_timeline(timeline: list | None) -> str:
    """格式化历史事件时间线 (V2 新增)"""
    if not timeline:
        return "（无近期事件记录）"
    lines = []
    for ev in timeline[:15]:  # 最多15条，避免 Prompt 过长
        date_str = ev.get("date", "")[:10] if ev.get("date") else "?"
        type_icon = {
            "discipline": "⚠️",
            "academic_snapshot": "📊",
            "psych_survey": "🧠",
            "sanction": "📋",
        }.get(ev.get("event_type", ""), "·")
        extra = ""
        if ev.get("severity"):
            extra = f" [严重度:{ev['severity']}]"
        if ev.get("risk_flag"):
            extra = f" [总分:{ev['risk_flag']}]"
        if ev.get("semester"):
            extra += f" ({ev['semester']})"
        lines.append(f"{type_icon} {date_str} — {ev.get('summary', '')}{extra}")
    return "\n".join(lines)


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


# ─────────────────────────────────────────────
# V3 格式化辅助 (Task #1448 — 5路新数据源)
# ─────────────────────────────────────────────


def _format_growth_timeline(timeline: list | None) -> str:
    """格式化成长时光轴事件流 (V3 新增)"""
    if not timeline:
        return "（无成长事件记录）"
    lines = []
    dim_cn = {
        "academic": "学业",
        "attendance": "考勤",
        "behavior": "行为",
        "psychology": "心理",
        "activity": "活动",
    }
    sev_icon = {
        "info": "○",
        "bonus": "★",
        "warning": "△",
        "critical": "⚠",
    }
    for ev in timeline[:15]:
        date_str = ev.get("occurred_at", "")[:10] if ev.get("occurred_at") else "?"
        dim_label = dim_cn.get(ev.get("dimension", ""), ev.get("dimension", ""))
        icon = sev_icon.get(ev.get("severity", ""), "·")
        lines.append(
            f"{icon} {date_str} [{dim_label}] {ev.get('title', '')} "
            f"(type={ev.get('event_type', '')})"
        )
    return "\n".join(lines)


def _format_growth_snapshot(snapshots: list | None) -> str:
    """格式化周期成长五维快照 (V3 新增)"""
    if not snapshots:
        return "（无成长快照记录）"
    lines = []
    for snap in snapshots:
        type_cn = {"monthly": "月度", "semester": "学期"}.get(
            snap.get("snapshot_type", ""), snap.get("snapshot_type", "")
        )
        lines.append(f"- [{type_cn}] {snap.get('period_label', '')}:")
        lines.append(
            f"  学业={snap.get('academic_score')} 考勤={snap.get('attendance_score')} "
            f"行为={snap.get('behavior_score')} 心理={snap.get('psych_score')} "
            f"活动={snap.get('activity_score')}"
        )
        if snap.get("teacher_comment"):
            lines.append(f"  教师评语：{snap['teacher_comment'][:80]}")
        if snap.get("ai_growth_prescription"):
            lines.append(f"  AI处方(历史)：{snap['ai_growth_prescription'][:80]}")
    return "\n".join(lines)


def _format_homework(homework: dict | None) -> str:
    """格式化作业提交与批改数据 (V3 新增)"""
    if not homework:
        return "（无作业记录）"
    summary = homework.get("summary", {})
    lines = [
        f"- 总提交数：{summary.get('total_submissions', 0)}",
        f"- 已批改数：{summary.get('graded_count', 0)}",
        f"- 迟交次数：{summary.get('late_count', 0)}",
        f"- 平均得分率：{summary.get('avg_score_pct', 'N/A')}%",
        f"- 错题总数：{summary.get('total_errors', 0)}",
    ]
    # 最近3条批改明细
    recent = homework.get("recent_submissions", [])[:3]
    if recent:
        lines.append("- 最近提交明细：")
        grade_cn = {
            "excellent": "优",
            "good": "良",
            "fair": "中",
            "needs_improvement": "待提高",
        }
        for item in recent:
            grade_label = grade_cn.get(item.get("grade", ""), item.get("grade", ""))
            pct = item.get("score_percentage")
            pct_str = f"得分率{pct}%" if pct is not None else "未批改"
            late_tag = (
                f" 迟交{item.get('late_minutes', 0)}min" if item.get("late_minutes", 0) > 0 else ""
            )
            err_tag = f" 错题{item.get('error_count', 0)}道" if item.get("error_count") else ""
            lines.append(
                f"  · {item.get('status', '')} {pct_str}({grade_label}){late_tag}{err_tag}"
            )
    return "\n".join(lines)


def _format_error_funnel(error_funnel: dict | None) -> str:
    """格式化错题本与知识断层 (V3 新增)"""
    if not error_funnel:
        return "（无错题/断层记录）"
    summary = error_funnel.get("summary", {})
    lines = [
        f"- 活跃知识断层：{summary.get('total_gaps', 0)} 个",
        f"  其中 critical 级：{summary.get('critical_gaps', 0)}，warning 级：{summary.get('warning_gaps', 0)}",
        f"- 最近错题：{summary.get('total_errors', 0)} 道，未纠错：{summary.get('unresolved_errors', 0)} 道",
    ]
    gaps = error_funnel.get("knowledge_gaps", [])
    if gaps:
        lines.append("- 断层知识点（按连续错误次数排序）：")
        gap_level_cn = {"critical": "🔴", "warning": "🟡", "watch": "🔵", "none": "○"}
        for g in gaps[:8]:
            icon = gap_level_cn.get(g.get("gap_level", ""), "·")
            lines.append(
                f"  {icon} {g.get('knowledge_point', '')}: "
                f"连续错误{g.get('consecutive_errors', 0)}次 "
                f"(累计{g.get('error_count', 0)}次, {g.get('gap_level', '')})"
            )
    errors = error_funnel.get("recent_errors", [])
    if errors:
        error_type_cn = {
            "conceptual": "概念错误",
            "procedural": "过程错误",
            "careless": "粗心错误",
            "omission": "遗漏错误",
            "unknown": "未知",
        }
        lines.append("- 最近错题摘要：")
        for e in errors[:5]:
            etype = error_type_cn.get(e.get("error_type", ""), e.get("error_type", ""))
            resolved_tag = "✓已纠错" if e.get("is_resolved") else "✗未纠错"
            lines.append(f"  · [{etype}] {e.get('question_preview', '')} ({resolved_tag})")
    return "\n".join(lines)


def _format_psych_deep(psych_deep: dict | None) -> str:
    """格式化心理综合档案与咨询记录 (V3 新增 — 严格排除加密字段)"""
    if not psych_deep:
        return "（无心理档案记录）"
    lines = []
    # 心理档案主表
    profile = psych_deep.get("profile")
    if profile:
        risk_cn = {
            "green": "🟢正常",
            "yellow": "🟡关注",
            "orange": "🟠预警",
            "red": "🔴危机",
        }
        lines.append(
            f"- 当前风险等级：{risk_cn.get(profile.get('risk_level'), profile.get('risk_level'))}"
        )
        lines.append(
            f"- 历史最高风险：{risk_cn.get(profile.get('highest_risk_level'), profile.get('highest_risk_level'))}"
        )
        lines.append(f"- 累计咨询次数：{profile.get('total_counseling_count', 0)}")
        lines.append(f"- 累计筛查次数：{profile.get('total_screening_count', 0)}")
        if profile.get("is_referred"):
            lines.append("  ⚠ 曾转介外部机构")
        tags = profile.get("tags", [])
        if tags:
            lines.append(f"- 标签云：{', '.join(tags[:5])}")
        if profile.get("last_counseling_date"):
            lines.append(f"- 最近咨询日期：{profile['last_counseling_date'][:10]}")
    else:
        lines.append("- （无心理综合档案）")

    # 筛查记录
    screenings = psych_deep.get("screenings", [])
    if screenings:
        lines.append("- 最近筛查记录：")
        for s in screenings:
            lines.append(
                f"  · {s.get('scale_name', '')} 总分={s.get('total_score', 'N/A')} "
                f"风险={s.get('risk_level', 'N/A')} 日期={s.get('test_date', '')[:10]}"
            )
            if s.get("risk_factors"):
                lines.append(f"    风险因子：{', '.join(s['risk_factors'][:3])}")

    # 咨询记录元数据 (encrypted_clog 已严格排除)
    consults = psych_deep.get("consults", [])
    if consults:
        lines.append("- 最近咨询记录元数据：")
        cat_cn = {
            "emotion": "情绪",
            "interpersonal": "人际",
            "academic": "学业",
            "family": "家庭",
            "self_harm": "自伤风险",
            "other": "其他",
        }
        for c in consults:
            cat_label = cat_cn.get(c.get("consult_category", ""), c.get("consult_category", ""))
            crisis_tag = " ⚠危机干预" if c.get("is_crisis") else ""
            referred_tag = " 已转介" if c.get("is_referred") else ""
            duration = c.get("session_duration_min")
            dur_str = f"{duration}分钟" if duration else "时长未记录"
            lines.append(
                f"  · [{cat_label}] 风险={c.get('risk_level', 'N/A')} "
                f"{dur_str}{crisis_tag}{referred_tag} 日期={c.get('created_at', '')[:10]}"
            )
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# Phase 2C: RDI → AI 处方 → 审批工单 全自动桥接
# ═══════════════════════════════════════════════════════════════

import asyncio

from sqlalchemy import text as _text
from sqlalchemy.ext.asyncio import AsyncSession as _AsyncSession
from sqlalchemy.ext.asyncio import async_sessionmaker as _async_sm
from sqlalchemy.ext.asyncio import create_async_engine as _create_async_engine

# 异步引擎 (仅用于 build_student_context)
_ASYNC_DB_URL = require_db_url()
_async_engine = _create_async_engine(
    _ASYNC_DB_URL, pool_pre_ping=True, pool_recycle=300, pool_size=2
)
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
    from core.models import User, UserRole

    # 1. 获取学生的 class_id
    student = sync_db.execute(
        _text("SELECT class_id FROM students WHERE id = :sid AND school_id = :scid"),
        {"sid": student_id, "scid": school_id},
    ).fetchone()
    if not student or not student.class_id:
        return None

    # 2. 查询该班的班主任
    teacher = (
        sync_db.query(User)
        .filter(
            User.school_id == school_id,
            User.role == UserRole.CLASS_TEACHER,
            User.class_id == student.class_id,
            User.is_active == True,
        )
        .first()
    )
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
    existing = (
        sync_db.query(ApprovalRequest)
        .filter(
            ApprovalRequest.school_id == school_id,
            ApprovalRequest.source_type == "ai_prescription",
            ApprovalRequest.source_id == warning_id,
            ApprovalRequest.current_status == "pending",
        )
        .first()
    )
    if existing:
        logger.info(
            "[BRIDGE] 幂等跳过: warning_id=%s 已有 pending 审批工单 #%s", warning_id, existing.id
        )
        return existing.id

    # L1: 尝试多租户审批链
    chain_config = None
    try:
        from modules.approval.services import resolve_chain

        chain_config = resolve_chain(sync_db, school_id, "ai_intervention")
        if chain_config:
            logger.info(
                "[BRIDGE] 使用多租户审批链 | school=%s chain_id=%s",
                school_id,
                chain_config.get("chain_id"),
            )
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
        ar.id,
        student_id,
        prescription_id,
        warning_id,
        rdi_score,
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
        student_id,
        school_id,
        warning_id,
        rdi_score,
    )

    try:
        # ── Step 1: 构建学生上下文 ──
        context = asyncio.run(_build_context_async(student_id, school_id))
        logger.info("[BRIDGE] 上下文构建完成 | student=%s", student_id)

        # ── Step 2: 调用 DeepSeek 生成干预处方 (V3 三段式) ──
        prompt = _build_student_prompt(context)
        result = _call_deepseek(prompt, SYSTEM_PROMPT_STUDENT)

        risk_level_str = result.get("risk_level", "HIGH")
        summary = result.get("summary", "")
        full_text = result.get("full_text", "")
        fact_text = result.get("fact", "")
        analysis_text = result.get("analysis", "")
        growth_text = result.get("growth", "")

        # 兜底: 如果 LLM 未返回 full_text，自动拼接三段
        if not full_text and (fact_text or analysis_text or growth_text):
            full_text = f"{fact_text}\n\n{analysis_text}\n\n{growth_text}"

        try:
            risk_level = RiskLevel(risk_level_str)
        except ValueError:
            risk_level = RiskLevel.HIGH

        # ── Step 3: 落库 ai_prescriptions (V2: segments 存入 llm_output) ──
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
                    "llm_output": {
                        "fact": fact_text,
                        "analysis": analysis_text,
                        "growth": growth_text,
                        "risk_level": risk_level_str,
                        "summary": summary,
                    },
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
            prescription_id,
            risk_level.value,
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
                    db,
                    teacher_id,
                    school_id,
                    student_id,
                    prescription_id,
                    ar_id,
                    rdi_score,
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
            student_id,
            prescription_id,
            ar_id,
            elapsed,
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
            student_id,
            warning_id,
            exc,
            exc_info=True,
        )
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=2**self.request.retries * 10)
        return {"status": "FAILURE", "student_id": student_id, "error": str(exc)}
