"""
modules/risk_models/explainer.py — PenaltyExplainer 判罚透明化解释引擎

核心功能:
  - 三段式解释生成 (Fact → Rule → Growth)
  - 模板变量替换 + 禁止用语校验
  - RDI 联动动态解释
  - 回血路径计算 + 补救方案推荐

三段式表达架构 (总指挥决策):
  1. Fact (事实陈述)   — 客观引用 discipline_records / score_logs 原始数据
  2. Rule (校规映射)   — 引用 policy.yaml 处罚规则 + 扣分计算逻辑
  3. Growth (建设性引导) — 回血/补救路径 + AI 处方推荐

设计原则:
  - Fail-Soft: 所有外部依赖均包裹在 try-except 中
  - Policy as Code: 模板和规则完全由 policy.yaml 驱动
  - 建议性语气: 强制检查禁止用语清单

v1.0.0 — 2026-06-29
"""

import logging
import math
import os
from datetime import datetime, date, timedelta
from typing import Optional, Dict, List, Tuple

import yaml
from sqlalchemy import select, and_, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import Student, Class as ClassModel
from modules.behavior.models import DisciplineRecord
from modules.evaluation.models import ScoreLog

logger = logging.getLogger(__name__)


def _load_policy_config() -> dict:
    """加载 policy.yaml 配置 (独立函数，供 Explainer 和测试脚本使用)"""
    policy_path = os.path.join(os.path.dirname(__file__), "../../policy.yaml")
    try:
        with open(policy_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
            return config.get("policy_engine", {})
    except Exception as e:
        logger.warning(f"Failed to load policy.yaml: {e}")
        return {}


# ═══════════════════════════════════════════════════════════════════════════════
# 校规解析器 — 从 Markdown/文本中加载校规条文
# ═══════════════════════════════════════════════════════════════════════════════

def _load_school_regulations(policy: dict) -> Dict[str, str]:
    """
    加载校规条文映射
    
    优先从 policy.yaml 指定的 source_path 读取
    若文件不存在则使用内置兜底规则
    """
    pe = policy.get("penalty_explanation", {})
    school_regs = pe.get("school_regulations", {})
    source_path = school_regs.get("source_path", "docs/school_regulations.md")
    auto_parse = school_regs.get("auto_parse", True)
    
    regulations = {}
    
    # 尝试读取校规文件
    if auto_parse and source_path:
        base_dir = os.path.join(os.path.dirname(__file__), "../..")
        full_path = os.path.join(base_dir, source_path)
        try:
            if os.path.exists(full_path):
                with open(full_path, "r", encoding="utf-8") as f:
                    content = f.read()
                regulations = _parse_regulations_markdown(content)
                logger.info(f"Loaded {len(regulations)} regulation entries from {source_path}")
                return regulations
        except Exception as e:
            logger.warning(f"Failed to load school regulations from {full_path}: {e}")
    
    # ── 内置兜底校规 (从 event_classification 反向生成) ──
    return _build_fallback_regulations(policy)


def _parse_regulations_markdown(content: str) -> Dict[str, str]:
    """
    解析 Markdown 格式的校规文件
    
    预期格式:
      ## fighting
      在校园内打架斗殴，视情节轻重给予警告至记过处分，扣15分...
    
      ## smoking
      在校园内吸烟，给予警告处分，扣10分...
    """
    regulations = {}
    current_key = None
    current_text = []
    
    for line in content.split("\n"):
        line = line.strip()
        if line.startswith("## "):
            # 保存上一段
            if current_key and current_text:
                regulations[current_key] = " ".join(current_text)
            current_key = line[3:].strip().lower().replace(" ", "_")
            current_text = []
        elif line.startswith("# "):
            if current_key and current_text:
                regulations[current_key] = " ".join(current_text)
            current_key = None
            current_text = []
        elif current_key and line:
            current_text.append(line)
    
    # 保存最后一段
    if current_key and current_text:
        regulations[current_key] = " ".join(current_text)
    
    return regulations


def _build_fallback_regulations(policy: dict) -> Dict[str, str]:
    """
    从 event_classification 反向构建兜底校规
    
    每个事件类型生成一条简明的规则描述
    """
    ec = policy.get("event_classification", {})
    behavior_types = ec.get("behavior_types", {})
    
    regulations = {}
    
    rule_templates = {
        "fighting": "在校园内打架斗殴，视情节轻重给予警告至记过处分。扣15分，权重乘数2.0。",
        "smoking": "在校园内吸烟，给予警告或严重警告处分。扣10分，权重乘数1.5。",
        "cheating": "考试作弊或学术不诚信，给予记过至留校察看处分。扣20分，权重乘数2.5。",
        "lateness": "无故迟到，每次扣3分。累计多次将升级处理。",
        "absence": "无故缺勤，每次扣5分。连续缺勤超过3天将启动家校联动。",
    }
    
    for event_type, event_config in behavior_types.items():
        if event_type in rule_templates:
            regulations[event_type] = rule_templates[event_type]
        else:
            severity = event_config.get("severity", "minor")
            penalty = event_config.get("base_penalty", 5)
            regulations[event_type] = f"违反校规行为 ({event_type})，严重程度: {severity}，基础扣分: {penalty}分。"
    
    return regulations


# ═══════════════════════════════════════════════════════════════════════════════
# PenaltyExplainer — 核心解释引擎
# ═══════════════════════════════════════════════════════════════════════════════

class PenaltyExplainer:
    """
    PenaltyExplainer — 判罚透明化解释引擎
    
    使用方式:
      explainer = PenaltyExplainer(db, school_id)
      result = await explainer.generate_explanation(
          student_id=123,
          event_type="fighting",
          event_id=456,
      )
    """
    
    # ── DB category (中文) → policy.yaml key (英文) 映射 ──
    # Wings 3.0 discipline_records.category 存储中文，policy.yaml event_classification 使用英文key
    _CATEGORY_TO_POLICY_KEY = {
        "打架": "fighting",
        "吸烟": "smoking",
        "迟到": "lateness",
        "缺勤": "absence",
        "作弊": "cheating",
        "课堂": "classroom_disruption",
        "仪容": "uniform_violation",
        "其他": "other",
        # 兜底映射: 直接匹配英文字段
        "fighting": "fighting",
        "smoking": "smoking",
        "cheating": "cheating",
        "lateness": "lateness",
        "absence": "absence",
        # Wings type 字段的严重程度 → 不合适，忽略
    }
    
    def __init__(self, db: AsyncSession, school_id: int):
        self.db = db
        self.school_id = school_id
        self.policy = _load_policy_config()
        self._load_config()
        self._regulations = _load_school_regulations(self.policy)
    
    def _load_config(self):
        """加载判罚说明相关配置"""
        pe = self.policy.get("penalty_explanation", {})
        
        # 文本模板
        self.text_templates = pe.get("text_templates", {})
        self.tone_guideline = self.text_templates.get("tone_guideline", "建议性")
        self.prohibited_phrases: List[str] = self.text_templates.get("prohibited_phrases", [])
        
        # 推送配置
        delivery = pe.get("delivery", {})
        self.deliver_to_parent = delivery.get("to_parent", True)
    
    # ══════════════════════════════════════════════════════════════════
    # 公开接口: generate_explanation()
    # ══════════════════════════════════════════════════════════════════
    
    async def generate_explanation(
        self,
        student_id: int,
        event_type: Optional[str] = None,
        event_id: Optional[int] = None,
        rdi_result: Optional[Dict] = None,
    ) -> Dict:
        """
        生成三段式判罚解释
        
        参数:
          student_id:  学生ID (必填)
          event_type:  事件类型 (如 "fighting", "lateness") 
          event_id:    违纪记录ID (可选，指定则查询具体记录)
          rdi_result:  已有的 RDI 计算结果 (可选，避免重复计算)
        
        返回:
          {
            "student_id": int,
            "student_name": str,
            "student_no": str | None,
            "class_name": str | None,
            "rdi_score": float | None,
            "risk_level": str | None,
            "fact": {
                "event_type": str,
                "event_date": str | None,
                "penalty_amount": float | None,
                "description": str,
                "data_source": str,
            },
            "rule": {
                "regulation_ref": str,
                "severity": str,
                "dimension": str,
                "base_penalty": float,
                "weight_multiplier": float,
            },
            "growth": {
                "repairable": bool,
                "recovery_path": str | None,
                "recovery_eta_days": int | None,
                "suggested_actions": List[str],
                "ai_prescription_ref": str | None,
            },
            "explanation_text": str,
            "template_used": str,
            "tone": str,
            "prohibited_phrase_violations": List[str],
            "generated_at": datetime,
          }
        """
        # ── Step 0: 获取学生基本信息 ──
        student_info = await self._fetch_student_info(student_id)
        if not student_info:
            raise ValueError(f"学生不存在: id={student_id}")
        
        # ── Step 1: 构建事实陈述 (Fact) ──
        fact = await self._build_fact(student_id, event_type, event_id)
        
        # ── Step 2: 构建校规映射 (Rule) ──
        rule = self._build_rule(fact["event_type"] or event_type or "unknown")
        
        # ── Step 3: 构建建设性引导 (Growth) ──
        growth = self._build_growth(
            event_type=fact["event_type"] or event_type,
            rdi_result=rdi_result,
            severity=rule["severity"],
        )
        
        # ── Step 4: 注入 Z-Score 量化分析 (从基线数据提取) ──
        z_score = 0.0
        percentile = 50.0
        baseline_mean = 0.0
        dominant_dim = "behavior"

        if rdi_result and rdi_result.get("behavior_deviation") is not None:
            # 取三维度中最偏离的 Z-Score (主导维度)
            deviations = {
                "behavior": abs(rdi_result.get("behavior_deviation", 0) or 0),
                "attendance": abs(rdi_result.get("attendance_deviation", 0) or 0),
                "score": abs(rdi_result.get("score_deviation", 0) or 0),
            }
            dominant_dim = max(deviations, key=lambda k: deviations[k])
            raw_z = rdi_result.get(f"{dominant_dim}_deviation", 0) or 0
            z_score = round(raw_z, 2)
            percentile = ExplainerService._compute_percentile(z_score)
            baseline_mean = round(rdi_result.get(f"{dominant_dim}_baseline_mean", 0) or 0, 2)

        # ── Step 5: 生成格式化解释文本 ──
        risk_level = rdi_result.get("risk_level", "normal") if rdi_result else "normal"
        is_escalating = rdi_result.get("is_escalating", False) if rdi_result else False
        # 判罚解释场景不使用预警抑制模板 (suppression_explanation 仅用于推送系统)
        # 即使 RDI < 阈值也坚持三段式表达 — 为家长/教师提供完整的校规解释
        penalty_warning_suppressed = False
        
        template_name, rendered_text, violations = self._render_template(
            student_name=student_info["name"],
            event_type=fact["event_type"] or event_type or "未知事件",
            rdi_score=rdi_result.get("rdi_score", 0.0) if rdi_result else 0.0,
            risk_level=risk_level,
            is_escalating=is_escalating,
            warning_suppressed=penalty_warning_suppressed,  # 判罚解释不移用推送抑制
            dimension=self._get_dimension_label(rule["dimension"]),
            recommended_action=growth["suggested_actions"][0] if growth["suggested_actions"] else "观察",
            suppression_reason=rdi_result.get("suppression_reason", "") if rdi_result else "",
            cooldown_hours=str(self.policy.get("risk_warning", {}).get("warning_suppression", {}).get("repeated_warning_cooldown_hours", 48)),
            z_score=z_score,
            percentile=percentile,
            baseline_mean=baseline_mean,
        )
        
        return {
            "student_id": student_id,
            "student_name": student_info["name"],
            "student_no": student_info.get("student_no"),
            "class_name": student_info.get("class_name"),
            "rdi_score": rdi_result.get("rdi_score") if rdi_result else None,
            "risk_level": risk_level if rdi_result else None,
            "fact": fact,
            "rule": rule,
            "growth": growth,
            "explanation_text": rendered_text,
            "template_used": template_name,
            "tone": self.tone_guideline,
            "prohibited_phrase_violations": violations,
            "generated_at": datetime.now(),
        }
    
    # ══════════════════════════════════════════════════════════════════
    # 1. 事实陈述 (The Fact)
    # ══════════════════════════════════════════════════════════════════
    
    async def _build_fact(
        self,
        student_id: int,
        event_type: Optional[str] = None,
        event_id: Optional[int] = None,
    ) -> Dict:
        """
        构建事实陈述段
        
        数据来源优先级:
          1. 指定 event_id → 查询具体 discipline_record
          2. 指定 event_type → 查询该类型最新记录
          3. 无指定 → 查询最近违纪记录
          4. 无违纪记录 → 查询 score_logs 评价流水
          
        注意: 用户传入的 event_type 始终优先 (覆盖 DB 记录的 raw_type/category)
        """
        try:
            # ── 路径 A: 查询具体的违纪记录 ──
            if event_id:
                record = await self._fetch_discipline_record(event_id)
                if record:
                    effective_type = event_type or record.get("event_type", "unknown")
                    return {
                        "event_type": effective_type,
                        "event_date": record.get("event_date"),
                        "penalty_amount": record.get("penalty_amount"),
                        "description": record.get("description", ""),
                        "data_source": "discipline_records",
                        "record_id": event_id,
                    }
            
            # ── 路径 B: 按事件类型查询最新记录 ──
            if event_type:
                record = await self._fetch_latest_discipline_record(student_id, event_type)
                if record:
                    return {
                        "event_type": event_type,  # 使用传入的类型, 非DB原始字段
                        "event_date": record.get("event_date"),
                        "penalty_amount": record.get("penalty_amount"),
                        "description": record.get("description", ""),
                        "data_source": "discipline_records",
                        "record_id": record.get("id"),
                    }
            
            # ── 路径 C: 查询最近违纪记录 ──
            record = await self._fetch_latest_discipline_record(student_id)
            if record:
                return {
                    "event_type": event_type or record.get("event_type", "unknown"),
                    "event_date": record.get("event_date"),
                    "penalty_amount": record.get("penalty_amount"),
                    "description": record.get("description", ""),
                    "data_source": "discipline_records",
                    "record_id": record.get("id"),
                }
            
            # ── 路径 D: 无违纪记录 → 查询评价流水 ──
            score_log = await self._fetch_latest_score_log(student_id)
            if score_log:
                return {
                    "event_type": event_type or "evaluation_change",
                    "event_date": score_log.get("created_at"),
                    "penalty_amount": score_log.get("change_amount"),
                    "description": f"评价分变动: {score_log.get('change_amount', 0)}分 ({score_log.get('source_type', '未知来源')})",
                    "data_source": "score_logs",
                    "record_id": score_log.get("id"),
                }
            
            # ── 兜底 ──
            return {
                "event_type": event_type or "unknown",
                "event_date": str(date.today()),
                "penalty_amount": None,
                "description": "暂无具体违纪记录",
                "data_source": "none",
                "record_id": None,
            }
            
        except Exception as e:
            logger.error(f"Failed to build fact for student_id={student_id}: {e}", exc_info=True)
            return {
                "event_type": event_type or "unknown",
                "event_date": str(date.today()),
                "penalty_amount": None,
                "description": f"事实数据查询异常: {str(e)[:100]}",
                "data_source": "error",
                "record_id": None,
            }
    
    async def _fetch_discipline_record(self, record_id: int) -> Optional[Dict]:
        """查询指定违纪记录"""
        try:
            result = await self.db.execute(
                select(DisciplineRecord).where(
                    and_(
                        DisciplineRecord.id == record_id,
                        DisciplineRecord.school_id == self.school_id,
                    )
                )
            )
            record = result.scalar_one_or_none()
            if record:
                # 优先使用 category (中文→英文映射), 其次 behavior_type, 最后 type (严重程度)
                raw_category = getattr(record, "category", None)
                raw_type = getattr(record, "type", None)
                event_type_from_db = self._CATEGORY_TO_POLICY_KEY.get(
                    raw_category, 
                    self._CATEGORY_TO_POLICY_KEY.get(raw_type, raw_type or "unknown")
                )
                return {
                    "id": record.id,
                    "event_type": event_type_from_db,
                    "raw_category": raw_category,
                    "raw_type": raw_type,
                    "event_date": str(getattr(record, "incident_date", getattr(record, "created_at", date.today()))),
                    "penalty_amount": getattr(record, "points", None),
                    "description": getattr(record, "description", "") or getattr(record, "detail", ""),
                    "student_id": record.student_id,
                }
        except Exception as e:
            logger.warning(f"Failed to fetch discipline_record id={record_id}: {e}")
        return None
    
    async def _fetch_latest_discipline_record(
        self, student_id: int, event_type: Optional[str] = None
    ) -> Optional[Dict]:
        """查询学生最新的违纪记录 (可选按事件类型过滤)"""
        try:
            conditions = [
                DisciplineRecord.student_id == student_id,
                DisciplineRecord.school_id == self.school_id,
            ]
            
            query = select(DisciplineRecord).where(and_(*conditions))
            
            if event_type:
                # 尝试匹配 behavior_type 或 type 字段
                query = query.where(
                    (getattr(DisciplineRecord, "behavior_type", None) == event_type)
                )
            
            query = query.order_by(
                desc(getattr(DisciplineRecord, "incident_date", getattr(DisciplineRecord, "created_at", datetime.min)))
            ).limit(1)
            
            result = await self.db.execute(query)
            record = result.scalar_one_or_none()
            
            if record:
                raw_category = getattr(record, "category", None)
                raw_type = getattr(record, "type", None)
                event_type_from_db = self._CATEGORY_TO_POLICY_KEY.get(
                    raw_category,
                    self._CATEGORY_TO_POLICY_KEY.get(raw_type, raw_type or event_type or "unknown")
                )
                return {
                    "id": record.id,
                    "event_type": event_type_from_db,
                    "raw_category": raw_category,
                    "raw_type": raw_type,
                    "event_date": str(getattr(record, "incident_date", getattr(record, "created_at", date.today()))),
                    "penalty_amount": getattr(record, "points", None),
                    "description": getattr(record, "description", "") or getattr(record, "detail", ""),
                    "student_id": record.student_id,
                }
        except Exception as e:
            logger.warning(f"Failed to fetch latest discipline_record for student_id={student_id}: {e}")
        return None
    
    async def _fetch_latest_score_log(self, student_id: int) -> Optional[Dict]:
        """查询学生最新的评价变动流水"""
        try:
            result = await self.db.execute(
                select(ScoreLog).where(
                    and_(
                        ScoreLog.student_id == student_id,
                        ScoreLog.school_id == self.school_id,
                    )
                ).order_by(desc(ScoreLog.created_at)).limit(1)
            )
            log = result.scalar_one_or_none()
            if log:
                return {
                    "id": log.id,
                    "change_amount": log.change_amount,
                    "source_type": getattr(log, "source_type", "unknown"),
                    "created_at": str(log.created_at) if log.created_at else str(date.today()),
                }
        except Exception as e:
            logger.warning(f"Failed to fetch score_log for student_id={student_id}: {e}")
        return None
    
    # ══════════════════════════════════════════════════════════════════
    # 2. 校规映射 (The Rule)
    # ══════════════════════════════════════════════════════════════════
    
    def _build_rule(self, event_type: str) -> Dict:
        """
        构建校规映射段
        
        步骤:
          1. 从 event_classification 查事件配置
          2. 从 school_regulations 查校规条文
          3. 组装处罚计算逻辑
        """
        try:
            ec = self.policy.get("event_classification", {})
            behavior_types = ec.get("behavior_types", {})
            
            # 查找事件配置
            event_config = behavior_types.get(event_type, {})
            if not event_config:
                # 尝试从 default_mapping 兜底
                event_config = ec.get("default_mapping", {
                    "dimension": "academic_moral",
                    "sub_dimension": "classroom_discipline",
                    "severity": "minor",
                    "base_penalty": 5,
                    "weight_multiplier": 1.0,
                })
            
            # 查找校规条文
            regulation_ref = self._regulations.get(
                event_type,
                self._regulations.get("default", "违反校规行为，按照《梨江中学学生违纪处分条例》处理。")
            )
            
            return {
                "regulation_ref": regulation_ref,
                "severity": event_config.get("severity", "minor"),
                "dimension": event_config.get("dimension", "academic_moral"),
                "sub_dimension": event_config.get("sub_dimension", "classroom_discipline"),
                "base_penalty": float(event_config.get("base_penalty", 5)),
                "weight_multiplier": float(event_config.get("weight_multiplier", 1.0)),
                "effective_penalty": float(event_config.get("base_penalty", 5)) * float(event_config.get("weight_multiplier", 1.0)),
            }
            
        except Exception as e:
            logger.error(f"Failed to build rule for event_type={event_type}: {e}", exc_info=True)
            return {
                "regulation_ref": "校规查询异常，请参考《梨江中学学生违纪处分条例》",
                "severity": "minor",
                "dimension": "academic_moral",
                "sub_dimension": "classroom_discipline",
                "base_penalty": 5.0,
                "weight_multiplier": 1.0,
                "effective_penalty": 5.0,
            }
    
    # ══════════════════════════════════════════════════════════════════
    # 3. 建设性引导 (The Growth)
    # ══════════════════════════════════════════════════════════════════
    
    def _build_growth(
        self,
        event_type: Optional[str] = None,
        rdi_result: Optional[Dict] = None,
        severity: str = "minor",
    ) -> Dict:
        """
        构建建设性引导段
        
        内容:
          - 是否可回血 (repairable)
          - 回血路径说明 + 预计天数
          - 建议行动清单 (从 text_templates 提取)
          - AI 处方引用
        """
        try:
            # ── 判断是否可回血 ──
            recovery_model = self.policy.get("recovery_model", {})
            per_severity = recovery_model.get("per_severity", {})
            
            # 映射 severity → recovery config
            severity_map = {
                "minor": "warning",
                "major": "serious_warning",
                "critical": "demerit",
            }
            recovery_key = severity_map.get(severity, "warning")
            severity_config = per_severity.get(recovery_key, {})
            
            is_repairable = severity_config.get("recovery_enabled", True)
            
            # ── 回血路径 ──
            recovery_path = None
            recovery_eta_days = None
            
            if is_repairable:
                # 获取回血参数
                k = severity_config.get("k_override", recovery_model.get("parameters", {}).get("k", 0.5))
                min_days = severity_config.get(
                    "min_observation_days_override",
                    recovery_model.get("parameters", {}).get("min_observation_days", 7)
                )
                
                # 计算回血到 85% 的预估天数: solve R(t) = 1/(1+t)^k = 0.85*target
                # 简化: 半衰期约30天 (k=0.5)，约60天恢复到85%
                if k == 0.5:
                    recovery_eta_days = 60
                elif k == 0.7:
                    recovery_eta_days = 90
                elif k == 1.0:
                    recovery_eta_days = 120
                else:
                    recovery_eta_days = 60
                
                channels = recovery_model.get("channels", [])
                channel_descriptions = []
                for ch in channels:
                    if ch.get("code") == "behavioral":
                        channel_descriptions.append(
                            f"连续{ch.get('streak_days', 14)}天无违纪行为，每期回血{int(ch.get('recovery_ratio', 0.05)*100)}%"
                        )
                    elif ch.get("code") == "temporal":
                        channel_descriptions.append(
                            f"随时间自然衰减，约{recovery_eta_days}天恢复到85%"
                        )
                    elif ch.get("code") == "revocation":
                        channel_descriptions.append("若处分撤销，可100%回血")
                
                recovery_path = "；".join(channel_descriptions) if channel_descriptions else \
                    f"保持{min_days}天无违纪行为后进入观察期，随时间自然回血"
            else:
                recovery_path = "该处分类型不支持回血，请关注其他维度的正向表现以提升综合评价。"
            
            # ── 建议行动 ──
            suggested_actions = self._get_suggested_actions(rdi_result)
            
            # ── AI 处方引用 ──
            ai_prescription_ref = None
            if event_type and rdi_result:
                risk_level = rdi_result.get("risk_level", "normal")
                if risk_level in ("attention", "intervention"):
                    ai_prescription_ref = f"建议参考 AI 德育处方模块，为 {event_type} 类型事件匹配个性化干预方案"
            
            return {
                "repairable": is_repairable,
                "recovery_path": recovery_path,
                "recovery_eta_days": recovery_eta_days,
                "min_observation_days": severity_config.get(
                    "min_observation_days_override",
                    recovery_model.get("parameters", {}).get("min_observation_days", 7)
                ),
                "suggested_actions": suggested_actions,
                "ai_prescription_ref": ai_prescription_ref,
            }
            
        except Exception as e:
            logger.error(f"Failed to build growth for event_type={event_type}: {e}", exc_info=True)
            return {
                "repairable": False,
                "recovery_path": "回血信息查询异常，请联系德育处确认",
                "recovery_eta_days": None,
                "min_observation_days": 7,
                "suggested_actions": ["建议联系班主任了解情况"],
                "ai_prescription_ref": None,
            }
    
    def _get_suggested_actions(self, rdi_result: Optional[Dict] = None) -> List[str]:
        """从 text_templates 中提取建议行动"""
        if not rdi_result:
            # 返回 attention 级别默认建议
            tmpl = self.text_templates.get("attention", {})
            return tmpl.get("suggested_actions", ["建议与孩子轻松谈心，了解近期状态"])
        
        risk_level = rdi_result.get("risk_level", "normal")
        is_escalating = rdi_result.get("is_escalating", False)
        
        if risk_level == "intervention":
            tmpl = self.text_templates.get("intervention", {})
        elif risk_level == "attention" and is_escalating:
            tmpl = self.text_templates.get("attention_escalating", {})
        else:
            tmpl = self.text_templates.get("attention", {})
        
        return tmpl.get("suggested_actions", ["建议与孩子轻松谈心，了解近期状态"])
    
    # ══════════════════════════════════════════════════════════════════
    # 4. 模板渲染 + 禁止用语校验
    # ══════════════════════════════════════════════════════════════════
    
    def _select_template(
        self,
        risk_level: str,
        is_escalating: bool,
        warning_suppressed: bool,
    ) -> Tuple[str, str]:
        """
        根据风险等级选择合适的文本模板
        
        返回: (template_name, template_text)
        """
        # 抑制优先
        if warning_suppressed:
            tmpl = self.text_templates.get("suppression_explanation", {})
            return ("suppression_explanation", tmpl.get("template", ""))
        
        # 按风险等级选择
        if risk_level == "intervention":
            tmpl = self.text_templates.get("intervention", {})
            return ("intervention", tmpl.get("template", ""))
        elif risk_level == "attention":
            if is_escalating:
                tmpl = self.text_templates.get("attention_escalating", {})
                return ("attention_escalating", tmpl.get("template", ""))
            else:
                tmpl = self.text_templates.get("attention", {})
                return ("attention", tmpl.get("template", ""))
        else:
            # normal → 也使用 attention 模板 (温和提醒)
            tmpl = self.text_templates.get("attention", {})
            return ("attention_normal", tmpl.get("template", ""))
    
    def _render_template(
        self,
        student_name: str,
        event_type: str,
        rdi_score: float,
        risk_level: str,
        is_escalating: bool,
        warning_suppressed: bool,
        dimension: str = "学业品德",
        recommended_action: str = "观察",
        suppression_reason: str = "",
        cooldown_hours: str = "48",
        z_score: float = 0.0,
        percentile: float = 50.0,
        baseline_mean: float = 0.0,
    ) -> Tuple[str, str, List[str]]:
        """
        渲染模板并校验禁止用语
        
        步骤:
          1. 根据风险等级选择模板
          2. 变量替换
          3. 禁止用语扫描
          4. 返回模板名 + 渲染后文本 + 违规列表
        
        返回: (template_name, rendered_text, violations)
        """
        # ── Step 1: 选择模板 ──
        template_name, template_text = self._select_template(
            risk_level, is_escalating, warning_suppressed
        )
        
        # 提取模板的 tone 标签
        tone_label = ""
        for key in ["attention", "attention_escalating", "intervention", "suppression_explanation"]:
            tmpl = self.text_templates.get(key, {})
            if tmpl.get("template") == template_text:
                tone_label = tmpl.get("tone", "")
                break
        
        # ── Step 2: 变量替换 ──
        # 事件类型中文映射
        event_type_cn_map = {
            "fighting": "打架斗殴",
            "smoking": "校园吸烟",
            "cheating": "考试作弊",
            "lateness": "迟到",
            "absence": "缺勤",
            "good_job": "正向表现",
            "academic_dishonesty": "学术不诚信",
        }
        event_type_cn = event_type_cn_map.get(event_type, event_type)
        
        # 风险等级中文映射
        risk_level_cn_map = {
            "normal": "🟢 正常",
            "attention": "🟡 关注",
            "intervention": "🔴 干预",
        }
        risk_level_cn = risk_level_cn_map.get(risk_level, risk_level)
        
        rendered = template_text
        rendered = rendered.replace("{student_name}", student_name)
        rendered = rendered.replace("{event_type}", event_type_cn)
        rendered = rendered.replace("{rdi_score}", f"{rdi_score:.2f}" if isinstance(rdi_score, (int, float)) else str(rdi_score))
        rendered = rendered.replace("{risk_level}", risk_level_cn)
        rendered = rendered.replace("{dimension}", dimension)
        rendered = rendered.replace("{recommended_action}", recommended_action)
        rendered = rendered.replace("{suppression_reason}", suppression_reason or "")
        rendered = rendered.replace("{cooldown_hours}", cooldown_hours or "48")
        rendered = rendered.replace("{z_score}", f"{z_score:.2f}")
        rendered = rendered.replace("{percentile}", f"{percentile:.1f}")
        rendered = rendered.replace("{baseline_mean}", f"{baseline_mean:.2f}")
        
        # 清理多余空白
        rendered = " ".join(rendered.split())
        
        # ── Step 3: 禁止用语扫描 ──
        violations = []
        for phrase in self.prohibited_phrases:
            if phrase in rendered:
                violations.append(phrase)
        
        if violations:
            logger.warning(
                f"⚠️ 模板渲染结果包含禁止用语: {violations} | "
                f"template={template_name}, student={student_name}"
            )
        
        return template_name, rendered, violations
    
    # ══════════════════════════════════════════════════════════════════
    # 辅助方法
    # ══════════════════════════════════════════════════════════════════
    
    async def _fetch_student_info(self, student_id: int) -> Optional[Dict]:
        """获取学生基本信息"""
        try:
            result = await self.db.execute(
                select(
                    Student.id,
                    Student.name,
                    Student.student_no,
                    Student.class_id,
                    ClassModel.name.label("class_name"),
                )
                .outerjoin(ClassModel, Student.class_id == ClassModel.id)
                .where(
                    and_(
                        Student.id == student_id,
                        Student.school_id == self.school_id,
                    )
                )
            )
            row = result.one_or_none()
            if row:
                return {
                    "name": row[1] or f"学生{student_id}",
                    "student_no": row[2],
                    "class_id": row[3],
                    "class_name": row[4],
                }
        except Exception as e:
            logger.warning(f"Failed to fetch student info for id={student_id}: {e}")
        return None
    
    def _get_dimension_label(self, dimension_code: str) -> str:
        """获取维度中文标签"""
        dim_map = {
            "academic_moral": "学业品德",
            "discipline": "纪律处分",
            "attendance": "考勤表现",
            "activity": "活动参与",
        }
        return dim_map.get(dimension_code, "学业品德")


# ═══════════════════════════════════════════════════════════════════════════════
# ExplainerService — 静态方法封装，供 routers 层调用
# ═══════════════════════════════════════════════════════════════════════════════

class ExplainerService:
    """
    ExplainerService — PenaltyExplainer 的静态服务封装
    
    遵循模块架构约定 (与 RiskWarningService / RiskMonitorService 一致)
    """
    
    @staticmethod
    def _compute_percentile(z_score: float) -> float:
        """
        基于 Z-Score 计算当前偏差在全校的百分位 (CDF)

        利用正态分布特性, math.erf 无需 scipy 依赖。
        返回 0.1 到 99.9 之间的 float，保留 1 位小数。

        示例:
          Z=0   → 50.0 (正好在均值)
          Z=1.0 → 84.1 (高于 84.1% 的同学)
          Z=2.0 → 97.7 (高于 97.7% 的同学)
        """
        cdf = 0.5 * (1 + math.erf(z_score / math.sqrt(2)))
        percentile = max(0.1, min(99.9, cdf * 100))
        return round(percentile, 1)

    @staticmethod
    async def explain_event(
        db: AsyncSession,
        school_id: int,
        student_id: int,
        event_type: Optional[str] = None,
        event_id: Optional[int] = None,
        rdi_result: Optional[Dict] = None,
    ) -> Dict:
        """
        生成判罚解释
        
        参数:
          db: 数据库会话
          school_id: 学校ID
          student_id: 学生ID
          event_type: 事件类型
          event_id: 违纪记录ID
          rdi_result: 已有的 RDI 计算结果
        
        返回: PenaltyExplainer.generate_explanation() 的输出
        """
        explainer = PenaltyExplainer(db, school_id)
        return await explainer.generate_explanation(
            student_id=student_id,
            event_type=event_type,
            event_id=event_id,
            rdi_result=rdi_result,
        )
