"""
modules/evaluation/services.py — 事件驱动素质评价引擎 (v2 — 处分强电桥接)

核心流程:
  1. 违纪行为录入 → apply_deduction() → 扣思想品德分 → 重算总分快照
  2. 手动评分     → record_score()     → 写 EvaluationScore → 重算总分快照
  3. 处分生效     → apply_discipline_deduction() → 扣除 penalty_points → 重算
  4. 处分撤销     → 下一轮 recalculate_snapshot() 自动停止扣分
  5. 期末总评     → check_discipline_veto() → 一票否决覆写 D 等

设计原则:
  - 写时计算：每次评分/扣分事件触发一次重算，存入 StudentScore
  - 读时快照：查询端绝不实时 SUM/AVG，直接取预计算结果
  - 流水溯源：每次变更写入 ScoreLog，支持完整回溯
  - 处分叠加：ACTIVE 处分 penalty_points 叠加到 moral 维度的行政扣减层
  - 一票否决：PROBATION/EXPULSION 直接覆写最终等级为 D/不合格
  - 撤销复活：REVOKED 处分在 revoke_date 之后自动停止扣分
"""

import json
import logging
from datetime import date, datetime

# ── 处分模块依赖（跨模块桥接）──
from modules.discipline.models import (
    LEVEL_LABELS,
    LEVEL_PENALTY_MAP,
    DisciplineSanction,
    DisciplineStatus,
)
from modules.lineage.decorators import audit_lineage, get_audit_context
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    EvaluationIndicator,
    EvaluationRule,
    EvaluationScore,
    ScoreLog,
    StudentScore,
)

logger = logging.getLogger("evaluation")

# ═══════════════════════════════════════════════════════════════
# 维度常量
# ═══════════════════════════════════════════════════════════════

DIMENSION_KEYS = ["moral", "academic", "health", "art", "social"]

DIMENSION_NAMES = {
    "moral": "思想品德",
    "academic": "学业水平",
    "health": "身心健康",
    "art": "艺术素养",
    "social": "社会实践",
}

DEFAULT_DIMENSION_WEIGHTS = {
    "moral": 0.25,
    "academic": 0.25,
    "health": 0.20,
    "art": 0.15,
    "social": 0.15,
}

# ═══════════════════════════════════════════════════════════════
# 种子数据
# ═══════════════════════════════════════════════════════════════

SEED_INDICATORS = [
    # 思想品德 (moral)
    ("思想品德", "moral", 0, 0.0, 0),
    ("爱国守法", "moral", 1, 0.30, 1),
    ("诚实守信", "moral", 1, 0.25, 2),
    ("责任担当", "moral", 1, 0.25, 3),
    ("文明礼仪", "moral", 1, 0.20, 4),
    # 学业水平 (academic)
    ("学业水平", "academic", 0, 0.0, 5),
    ("学习态度", "academic", 1, 0.30, 6),
    ("学业成绩", "academic", 1, 0.30, 7),
    ("创新思维", "academic", 1, 0.20, 8),
    ("实践能力", "academic", 1, 0.20, 9),
    # 身心健康 (health)
    ("身心健康", "health", 0, 0.0, 10),
    ("身体素质", "health", 1, 0.30, 11),
    ("心理健康", "health", 1, 0.30, 12),
    ("生活习惯", "health", 1, 0.20, 13),
    ("安全意识", "health", 1, 0.20, 14),
    # 艺术素养 (art)
    ("艺术素养", "art", 0, 0.0, 15),
    ("审美感知", "art", 1, 0.30, 16),
    ("艺术表现", "art", 1, 0.35, 17),
    ("文化理解", "art", 1, 0.35, 18),
    # 社会实践 (social)
    ("社会实践", "social", 0, 0.0, 19),
    ("志愿服务", "social", 1, 0.35, 20),
    ("劳动技能", "social", 1, 0.35, 21),
    ("社会实践", "social", 1, 0.30, 22),
    # 正向加分指标 (positive scoring)
    # 思想品德维度 — 品德表现加分
    ("品德之星", "moral", 1, 0.25, 23),
    ("助人为乐", "moral", 1, 0.25, 24),
    ("拾金不昧", "moral", 1, 0.20, 25),
    ("诚信守诺", "moral", 1, 0.30, 26),
    # 身心健康维度 — 体育竞赛加分
    ("体育竞赛", "health", 1, 0.30, 27),
    # 艺术素养维度 — 文体活动加分
    ("文体活动", "art", 1, 0.25, 28),
    ("文艺演出", "art", 1, 0.25, 29),
    ("艺术考级", "art", 1, 0.20, 30),
    # 社会实践维度 — 志愿服务与劳动实践加分
    ("校园志愿", "social", 1, 0.25, 31),
    ("社区服务", "social", 1, 0.30, 32),
    ("公益捐赠", "social", 1, 0.20, 33),
    ("劳动实践", "social", 1, 0.25, 34),
]

DEFAULT_DEDUCTION_MAP = {
    "warning": 1,
    "minor": 3,
    "major": 5,
    "serious": 10,
}


class EvaluationService:
    """素质评价引擎服务"""

    # ═══════════════════════════════════════════════════════════
    # 初始化
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def ensure_rules(db: AsyncSession, school_id: int) -> EvaluationRule:
        """确保学校有评分规则（无则创建默认）"""
        result = await db.execute(
            select(EvaluationRule).where(
                EvaluationRule.school_id == school_id,
                EvaluationRule.is_active == True,
            )
        )
        rule = result.scalar_one_or_none()
        if not rule:
            rule = EvaluationRule(school_id=school_id)
            db.add(rule)
            await db.flush()
        return rule

    @staticmethod
    async def seed_indicators(db: AsyncSession, school_id: int) -> int:
        """初始化默认五维评价指标（幂等）"""
        result = await db.execute(
            select(func.count(EvaluationIndicator.id)).where(
                EvaluationIndicator.school_id == school_id,
            )
        )
        count = result.scalar()
        if count > 0:
            return count

        indicators = []
        for name, dim, parent_id, weight, sort_order in SEED_INDICATORS:
            indicators.append(
                EvaluationIndicator(
                    school_id=school_id,
                    name=name,
                    parent_id=parent_id,
                    dimension=dim,
                    weight=weight,
                    sort_order=sort_order,
                )
            )
        db.add_all(indicators)
        await db.flush()
        logger.info(f"[evaluation] 学校 {school_id} 已初始化 {len(indicators)} 条评价指标")
        return len(indicators)

    # ═══════════════════════════════════════════════════════════
    # 维度辅助
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def _get_indicators_by_dim(
        db: AsyncSession, school_id: int, dim: str
    ) -> list[EvaluationIndicator]:
        """获取某维度下所有活跃二级指标"""
        result = await db.execute(
            select(EvaluationIndicator).where(
                EvaluationIndicator.school_id == school_id,
                EvaluationIndicator.dimension == dim,
                EvaluationIndicator.parent_id > 0,
                EvaluationIndicator.is_active == True,
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def _get_all_indicators_grouped(
        db: AsyncSession, school_id: int
    ) -> dict[str, list[EvaluationIndicator]]:
        """按维度分组获取所有活跃二级指标"""
        result = await db.execute(
            select(EvaluationIndicator)
            .where(
                EvaluationIndicator.school_id == school_id,
                EvaluationIndicator.parent_id > 0,
                EvaluationIndicator.is_active == True,
            )
            .order_by(EvaluationIndicator.sort_order)
        )
        all_inds = list(result.scalars().all())
        grouped = {d: [] for d in DIMENSION_KEYS}
        for ind in all_inds:
            if ind.dimension in grouped:
                grouped[ind.dimension].append(ind)
        return grouped

    # ═══════════════════════════════════════════════════════════
    # 核心——违纪扣分事件
    # ═══════════════════════════════════════════════════════════

    @audit_lineage(
        transformation="apply_deduction",
        source_type="discipline_record",
        target_type="score_log",
    )
    @staticmethod
    async def apply_deduction(
        db: AsyncSession,
        student_id: int,
        class_id: int,
        grade_id: int,
        school_id: int,
        discipline_type: str,
        discipline_id: int,
        created_by: int,
        semester: str | None = None,
        source_type: str = "behavior",
        penalty_override: float | None = None,
        policy_tag: str = "repairable",
    ) -> ScoreLog | None:
        """
        违纪/考勤事件 → 自动扣思想品德分 → 重算总分快照 → 写审计流水

        参数:
          - source_type: 事件来源 (behavior/attendance/discipline/manual/appeal)
          - penalty_override: PolicyEngine 分类器给出的精确扣分，覆盖 deduction_map
          - policy_tag: 政策标签 (repairable/non_repairable/recovered/permanent)

        返回 ScoreLog 或 None（规则不存在时）
        """
        rule = await EvaluationService.ensure_rules(db, school_id)
        deduction_map = rule.deduction_map or DEFAULT_DEDUCTION_MAP
        weights = rule.dimension_weights or DEFAULT_DIMENSION_WEIGHTS

        # 精确扣分优先: PolicyEngine base_penalty > deduction_map 严重度映射
        if penalty_override is not None:
            points = float(penalty_override)
        else:
            points = deduction_map.get(discipline_type, 1)

        if not semester:
            semester = EvaluationService._current_semester()

        # 1. 获取/创建当前学期快照
        result = await db.execute(
            select(StudentScore).where(
                StudentScore.student_id == student_id,
                StudentScore.semester == semester,
            )
        )
        snapshot = result.scalar_one_or_none()

        if not snapshot:
            snapshot = StudentScore(
                student_id=student_id,
                class_id=class_id,
                grade_id=grade_id,
                school_id=school_id,
                semester=semester,
                base_score=rule.base_score,
                moral_score=rule.base_score * weights.get("moral", 0.25),
                academic_score=rule.base_score * weights.get("academic", 0.25),
                health_score=rule.base_score * weights.get("health", 0.20),
                art_score=rule.base_score * weights.get("art", 0.15),
                social_score=rule.base_score * weights.get("social", 0.15),
            )
            snapshot.total_score = round(
                snapshot.moral_score * weights.get("moral", 0.25)
                + snapshot.academic_score * weights.get("academic", 0.25)
                + snapshot.health_score * weights.get("health", 0.20)
                + snapshot.art_score * weights.get("art", 0.15)
                + snapshot.social_score * weights.get("social", 0.15),
                1,
            )
            db.add(snapshot)
            await db.flush()

        # 2. 从思想品德维度扣分
        before_total = snapshot.total_score
        snapshot.moral_score = max(0.0, snapshot.moral_score - points)

        # 3. 重算总分（加权计算，与 get_final_evaluation / recalculate_snapshot 一致）
        snapshot.total_score = round(
            snapshot.moral_score * weights.get("moral", 0.25)
            + snapshot.academic_score * weights.get("academic", 0.25)
            + snapshot.health_score * weights.get("health", 0.20)
            + snapshot.art_score * weights.get("art", 0.15)
            + snapshot.social_score * weights.get("social", 0.15),
            1,
        )

        # 4. 写审计流水
        source_label = {
            "attendance": "考勤扣分",
            "behavior": "违纪扣分",
            "discipline": "处分扣分",
            "manual": "手动扣分",
            "appeal": "申诉扣分",
        }.get(source_type, "违纪扣分")

        # 获取审计上下文（由 @audit_score_log 装饰器或 HTTP middleware 注入）
        ctx = get_audit_context()

        log = ScoreLog(
            student_id=student_id,
            school_id=school_id,
            dimension="moral",
            change_amount=-points,
            before_score=before_total,
            after_score=snapshot.total_score,
            reason=f"{source_label} — {discipline_type} ({discipline_id})",
            source_type=source_type,
            source_id=discipline_id,
            created_by=created_by,
            policy_tag=policy_tag,
            # ── #1193 血缘增强字段 ──
            actor_id=ctx["actor_id"] or created_by,
            source_ip=ctx["source_ip"],
            trace_context_id=ctx["trace_context_id"],
            diff_snapshot=json.dumps(
                {
                    "before": before_total,
                    "after": snapshot.total_score,
                    "change": -points,
                    "dimension": "moral",
                },
                ensure_ascii=False,
            ),
        )
        db.add(log)

        await db.flush()
        logger.info(
            f"[evaluation] 学生 {student_id} {source_label} {points}, "
            f"总分 {before_total} → {snapshot.total_score} "
            f"source={source_type} tag={policy_tag}"
        )
        return log

    # ═══════════════════════════════════════════════════════════
    # 处分强电桥接 —— ACTIVE 处分扣分 + 一票否决 + 撤销复活
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def _get_active_sanctions(
        db: AsyncSession,
        student_id: int,
        semester: str | None = None,
    ) -> list[DisciplineSanction]:
        """
        获取学生当前学期所有 ACTIVE 状态的处分记录。

        用于: 评价引擎每日扣分流、学期总评一票否决判定
        """
        conditions = [
            DisciplineSanction.student_id == student_id,
            DisciplineSanction.status == DisciplineStatus.ACTIVE,
        ]
        # 可选学期过滤：处分 punish_date 在本学期范围内
        if semester:
            # 解析学期: "2025-2026-2" → 起止日期: 2026-02-01 ~ 2026-07-15
            semester_start, semester_end = EvaluationService._semester_date_range(semester)
            if semester_start and semester_end:
                conditions.append(DisciplineSanction.punish_date >= semester_start)
                conditions.append(DisciplineSanction.punish_date <= semester_end)

        result = await db.execute(
            select(DisciplineSanction)
            .where(*conditions)
            .order_by(DisciplineSanction.punish_date.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    def _semester_date_range(semester: str) -> tuple:
        """
        解析学期字符串 → 起止日期。

        "2025-2026-2" → (date(2026,2,1), date(2026,7,15))
        "2025-2026-1" → (date(2025,9,1), date(2026,1,20))
        """
        try:
            parts = semester.split("-")
            if len(parts) == 3:
                start_year = int(parts[0])
                end_year = int(parts[1])
                sem_num = int(parts[2])
                if sem_num == 1:
                    return (date(start_year, 9, 1), date(end_year, 1, 20))
                else:
                    return (date(end_year, 2, 1), date(end_year, 7, 15))
        except (ValueError, IndexError):
            pass
        return (None, None)

    @staticmethod
    def compute_discipline_penalty(
        sanctions: list[DisciplineSanction],
    ) -> tuple[float, bool, list[dict]]:
        """
        根据 ACTIVE 处分列表计算扣分总额、一票否决标志、处分摘要。

        返回:
          - penalty_total: 总分扣减额（负数或 0）
          - is_veto: 是否触发一票否决
          - sanction_summary: 处分摘要列表 [{level, label, punish_date, document_no}]
        """
        penalty_total = 0.0
        is_veto = False
        sanction_summary = []

        for s in sanctions:
            pts = LEVEL_PENALTY_MAP.get(s.level)
            if pts is not None:
                penalty_total += pts
            else:
                # PROBATION / EXPULSION → 一票否决（不扣分，直接标记）
                is_veto = True

            sanction_summary.append(
                {
                    "level": s.level.value if hasattr(s.level, "value") else str(s.level),
                    "label": LEVEL_LABELS.get(s.level, str(s.level)),
                    "punish_date": s.punish_date.isoformat() if s.punish_date else None,
                    "document_no": s.document_no,
                    "reason": s.reason[:100] if s.reason else "",
                }
            )

        return (penalty_total, is_veto, sanction_summary)

    @staticmethod
    def compute_resurrection_info(
        db_session_is_async: bool = True,
    ) -> dict:
        """占位 — REVOKED 处分信息在 get_final_evaluation 中单独查询"""
        return {}

    @staticmethod
    async def get_revoked_sanctions(
        db: AsyncSession,
        student_id: int,
        semester: str | None = None,
    ) -> list[dict]:
        """
        获取已撤销处分 — 用于前端报告单追回"处分已撤销"正向标签。
        """
        conditions = [
            DisciplineSanction.student_id == student_id,
            DisciplineSanction.status == DisciplineStatus.REVOKED,
        ]
        if semester:
            sem_start, sem_end = EvaluationService._semester_date_range(semester)
            if sem_start and sem_end:
                conditions.append(DisciplineSanction.revoke_date >= sem_start)
                conditions.append(DisciplineSanction.revoke_date <= sem_end)

        result = await db.execute(
            select(DisciplineSanction)
            .where(*conditions)
            .order_by(DisciplineSanction.revoke_date.desc())
        )
        sanctions = result.scalars().all()

        return [
            {
                "level": s.level.value if hasattr(s.level, "value") else str(s.level),
                "label": LEVEL_LABELS.get(s.level, str(s.level)),
                "punish_date": s.punish_date.isoformat() if s.punish_date else None,
                "revoke_date": s.revoke_date.isoformat() if s.revoke_date else None,
                "revoke_reason": s.revoke_reason,
                "document_no": s.document_no,
            }
            for s in sanctions
        ]

    @staticmethod
    async def check_discipline_veto(
        db: AsyncSession,
        student_id: int,
        semester: str | None = None,
    ) -> dict:
        """
        一票否决熔断器 — 期末总评调用。

        若发现 ACTIVE 且等级为 PROBATION/EXPULSION 的处分:
          → 返回 is_veto=True, forced_grade="D", reason 含具体处分信息
        """
        sanctions = await EvaluationService._get_active_sanctions(db, student_id, semester)
        _, is_veto, summary = EvaluationService.compute_discipline_penalty(sanctions)

        result = {
            "student_id": student_id,
            "is_veto": is_veto,
            "forced_grade": None,
            "veto_reason": None,
            "active_sanctions": summary,
            "active_count": len(sanctions),
        }

        if is_veto:
            veto_sanctions = [s for s in summary if s["level"] in ("PROBATION", "EXPULSION")]
            result["forced_grade"] = "D"
            result["veto_reason"] = (
                f"该生处于{'/'.join(s['label'] for s in veto_sanctions)}处分期内，"
                f"根据德育管理规定，本学期综合素质评价等级强制评定为 D（不合格）"
            )

        return result

    @staticmethod
    async def get_final_evaluation(
        db: AsyncSession,
        student_id: int,
        school_id: int,
        semester: str | None = None,
    ) -> dict:
        """
        学生期末综合评价 — 含处分影响的最终裁定。

        返回:
          - base_scores: 纯评分引擎产出的五维原始分 + 总分
          - discipline_penalty: ACTIVE 处分扣分总额
          - adjusted_scores: 扣分后的五维分 + 总分（min 0 保底）
          - veto: 一票否决裁定（is_veto + forced_grade + reason）
          - revoked_sanctions: 已撤销处分列表（"处分已撤销"正向标签）
          - final_grade: 最终等级（A/B/C/D）
          - grade_label: 等级中文说明
        """
        if not semester:
            semester = EvaluationService._current_semester()

        # 1. 获取评价引擎原始快照
        snapshot = await db.execute(
            select(StudentScore).where(
                StudentScore.student_id == student_id,
                StudentScore.semester == semester,
            )
        )
        ss = snapshot.scalar_one_or_none()

        base_scores = {
            "moral": ss.moral_score if ss else 0.0,
            "academic": ss.academic_score if ss else 0.0,
            "health": ss.health_score if ss else 0.0,
            "art": ss.art_score if ss else 0.0,
            "social": ss.social_score if ss else 0.0,
            "total": ss.total_score if ss else 0.0,
        }

        # 2. 获取 ACTIVE 处分 → 计算扣分 + 一票否决
        active_sanctions = await EvaluationService._get_active_sanctions(db, student_id, semester)
        penalty_total, is_veto, sanction_summary = EvaluationService.compute_discipline_penalty(
            active_sanctions
        )

        # 3. 计算处分调整后的分数（仅扣 moral 维度，保底 0）
        adjusted_moral = max(0.0, base_scores["moral"] + penalty_total)

        # 使用与 recalculate_snapshot 相同的加权公式计算调整后总分
        rule = await EvaluationService.ensure_rules(db, school_id)
        weights = rule.dimension_weights or DEFAULT_DIMENSION_WEIGHTS

        adjusted_total = round(
            adjusted_moral * weights.get("moral", 0.25)
            + base_scores["academic"] * weights.get("academic", 0.25)
            + base_scores["health"] * weights.get("health", 0.20)
            + base_scores["art"] * weights.get("art", 0.15)
            + base_scores["social"] * weights.get("social", 0.15),
            1,
        )

        # 4. 一票否决裁定
        veto_info = {
            "is_veto": is_veto,
            "forced_grade": "D" if is_veto else None,
            "reason": (
                f"处于处分期内（{'/'.join(s['label'] for s in sanction_summary if s['level'] in ('PROBATION', 'EXPULSION'))})"
                if is_veto
                else None
            ),
        }

        # 5. 已撤销处分（正向标签）
        revoked = await EvaluationService.get_revoked_sanctions(db, student_id, semester)

        # 6. 最终等级判定
        if is_veto:
            final_grade = "D"
            grade_label = "不合格（一票否决）"
        else:
            t = adjusted_total
            if t >= 90:
                final_grade = "A"
                grade_label = "优秀"
            elif t >= 75:
                final_grade = "B"
                grade_label = "良好"
            elif t >= 60:
                final_grade = "C"
                grade_label = "合格"
            else:
                final_grade = "D"
                grade_label = "不合格"

        return {
            "student_id": student_id,
            "semester": semester,
            "base_scores": base_scores,
            "discipline_penalty": {
                "total_deduction": penalty_total,
                "active_sanctions": sanction_summary,
                "active_count": len(active_sanctions),
            },
            "adjusted_scores": {
                "moral": adjusted_moral,
                "academic": base_scores["academic"],
                "health": base_scores["health"],
                "art": base_scores["art"],
                "social": base_scores["social"],
                "total": adjusted_total,
            },
            "veto": veto_info,
            "revoked_sanctions": revoked,
            "has_revoked": len(revoked) > 0,
            "final_grade": final_grade,
            "grade_label": grade_label,
        }

    # ═══════════════════════════════════════════════════════════
    # 核心——手动评分 + 重算快照
    # ═══════════════════════════════════════════════════════════

    @audit_lineage(
        transformation="record_score",
        source_type="evaluation_score",
        target_type="student_score",
    )
    @staticmethod
    async def record_score(
        db: AsyncSession,
        student_id: int,
        class_id: int,
        grade_id: int,
        school_id: int,
        indicator_id: int,
        score: float,
        scorer_type: str,
        scorer_id: int,
        semester: str | None = None,
        comment: str = "",
    ) -> EvaluationScore:
        """录入手动评分 → 重算该学生总分快照"""
        if not semester:
            semester = EvaluationService._current_semester()

        # 1. 写入评分记录
        record = EvaluationScore(
            student_id=student_id,
            class_id=class_id,
            grade_id=grade_id,
            school_id=school_id,
            indicator_id=indicator_id,
            score=score,
            scorer_type=scorer_type,
            scorer_id=scorer_id,
            semester=semester,
            comment=comment,
        )
        db.add(record)
        await db.flush()

        # 2. 重算快照
        await EvaluationService.recalculate_snapshot(db, student_id, school_id, semester)

        return record

    @audit_lineage(
        transformation="recalculate_snapshot",
        source_type="evaluation_score",
        target_type="student_score",
    )
    @staticmethod
    async def recalculate_snapshot(
        db: AsyncSession,
        student_id: int,
        school_id: int,
        semester: str,
    ) -> StudentScore | None:
        """
        重算学生总分快照

        算法（与旧 Flask 一致的三步）：
          1. 维度内归一化加权（各二级指标分 × 归一化权重）
          2. 平衡补偿（一维独大触发 0.85 惩罚）
          3. 一级维度加权求和得总分
        """
        rule = await EvaluationService.ensure_rules(db, school_id)
        indicators_by_dim = await EvaluationService._get_all_indicators_grouped(db, school_id)
        weights = rule.dimension_weights or DEFAULT_DIMENSION_WEIGHTS

        # 获取该学生本学期的所有评分
        result = await db.execute(
            select(EvaluationScore).where(
                EvaluationScore.student_id == student_id,
                EvaluationScore.semester == semester,
            )
        )
        scores = list(result.scalars().all())

        # 构建: {indicator_id: score}
        score_map = {s.indicator_id: s.score for s in scores}

        # 步骤 1: 维度内归一化加权
        raw_dim_scores = {}
        for d_key in DIMENSION_KEYS:
            subs = indicators_by_dim.get(d_key, [])
            if not subs:
                raw_dim_scores[d_key] = 0.0
                continue

            total_weight = sum(s.weight for s in subs)
            if total_weight <= 0:
                raw_dim_scores[d_key] = 0.0
                continue

            dim_total = 0.0
            for sub in subs:
                s = score_map.get(sub.id)
                if s is not None:
                    normalized_weight = sub.weight / total_weight
                    dim_total += s * normalized_weight
            raw_dim_scores[d_key] = round(dim_total, 1)

        # 步骤 2: 平衡补偿
        balanced_scores = dict(raw_dim_scores)
        non_zero = [v for v in raw_dim_scores.values() if v > 0]
        if len(non_zero) >= 2:
            avg_score = sum(non_zero) / len(non_zero)
            for d_key, d_score in balanced_scores.items():
                if d_score > avg_score * rule.balance_threshold:
                    balanced_scores[d_key] = round(d_score * rule.balance_penalty, 1)

        # 步骤 3: 一级维度加权求和
        total = 0.0
        for d_key in DIMENSION_KEYS:
            w = weights.get(d_key, 0.20)
            total += balanced_scores[d_key] * w

        # 更新快照
        result = await db.execute(
            select(StudentScore).where(
                StudentScore.student_id == student_id,
                StudentScore.semester == semester,
            )
        )
        snapshot = result.scalar_one_or_none()

        if not snapshot:
            snapshot = StudentScore(
                student_id=student_id,
                class_id=scores[0].class_id if scores else 0,
                grade_id=scores[0].grade_id if scores else 0,
                school_id=school_id,
                semester=semester,
                base_score=rule.base_score,
            )
            db.add(snapshot)
            await db.flush()

        # 更新维度分和总分（先设纯评价引擎的分数）
        snapshot.moral_score = balanced_scores["moral"]
        snapshot.academic_score = balanced_scores["academic"]
        snapshot.health_score = balanced_scores["health"]
        snapshot.art_score = balanced_scores["art"]
        snapshot.social_score = balanced_scores["social"]
        snapshot.total_score = round(total, 1)

        # ⚡ 处分强电桥接: 叠加 ACTIVE 处分扣分
        active_sanctions = await EvaluationService._get_active_sanctions(db, student_id, semester)
        if active_sanctions:
            penalty_total, _, _ = EvaluationService.compute_discipline_penalty(active_sanctions)
            if penalty_total < 0:
                before_moral = snapshot.moral_score
                snapshot.moral_score = max(0.0, snapshot.moral_score + penalty_total)
                # 修复: 使用加权计算（与 get_final_evaluation / recalculate_snapshot 主路径一致）
                snapshot.total_score = round(
                    snapshot.moral_score * weights.get("moral", 0.25)
                    + snapshot.academic_score * weights.get("academic", 0.25)
                    + snapshot.health_score * weights.get("health", 0.20)
                    + snapshot.art_score * weights.get("art", 0.15)
                    + snapshot.social_score * weights.get("social", 0.15),
                    1,
                )
                logger.info(
                    f"[evaluation] 学生 {student_id} 处分扣分 {penalty_total}, "
                    f"思想品德 {before_moral} → {snapshot.moral_score}, "
                    f"总分 → {snapshot.total_score}"
                )

        await db.flush()
        return snapshot

    # ═══════════════════════════════════════════════════════════
    # 查询——排名与统计
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def get_class_ranking(
        db: AsyncSession,
        class_id: int,
        semester: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """班级排名 — 按总分降序"""
        if not semester:
            semester = EvaluationService._current_semester()

        result = await db.execute(
            select(StudentScore)
            .where(
                StudentScore.class_id == class_id,
                StudentScore.semester == semester,
            )
            .order_by(StudentScore.total_score.desc())
            .limit(limit)
        )
        snapshots = result.scalars().all()

        ranking = []
        for rank, ss in enumerate(snapshots, 1):
            student = ss.student
            ranking.append(
                {
                    "rank": rank,
                    "student_id": ss.student_id,
                    "student_name": student.name if student else "",
                    "student_no": student.student_no if student else "",
                    "total_score": ss.total_score,
                    "moral_score": ss.moral_score,
                    "academic_score": ss.academic_score,
                    "health_score": ss.health_score,
                    "art_score": ss.art_score,
                    "social_score": ss.social_score,
                }
            )
        return ranking

    @staticmethod
    async def get_dimension_scores(
        db: AsyncSession,
        student_id: int,
        semester: str | None = None,
    ) -> dict | None:
        """获取单学生的五维分 + 总分"""
        if not semester:
            semester = EvaluationService._current_semester()

        result = await db.execute(
            select(StudentScore).where(
                StudentScore.student_id == student_id,
                StudentScore.semester == semester,
            )
        )
        ss = result.scalar_one_or_none()
        if not ss:
            return None

        return {
            "student_id": ss.student_id,
            "class_id": ss.class_id,
            "grade_id": ss.grade_id,
            "semester": ss.semester,
            "total_score": ss.total_score,
            "dimensions": {
                "moral": ss.moral_score,
                "academic": ss.academic_score,
                "health": ss.health_score,
                "art": ss.art_score,
                "social": ss.social_score,
            },
            "base_score": ss.base_score,
        }

    @staticmethod
    async def get_score_logs(
        db: AsyncSession,
        student_id: int,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[ScoreLog], int]:
        """获取评分流水（分页）"""
        count_result = await db.execute(
            select(func.count(ScoreLog.id)).where(
                ScoreLog.student_id == student_id,
            )
        )
        total = count_result.scalar()

        result = await db.execute(
            select(ScoreLog)
            .where(
                ScoreLog.student_id == student_id,
            )
            .order_by(ScoreLog.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        logs = list(result.scalars().all())
        return logs, total

    # ═══════════════════════════════════════════════════════════
    # 规则 CRUD
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def get_rules(db: AsyncSession, school_id: int) -> EvaluationRule | None:
        """获取学校当前生效的评分规则"""
        result = await db.execute(
            select(EvaluationRule).where(
                EvaluationRule.school_id == school_id,
                EvaluationRule.is_active == True,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def update_rules(
        db: AsyncSession,
        school_id: int,
        **kwargs,
    ) -> EvaluationRule:
        """更新评分规则 — 不存在则创建"""
        rule = await EvaluationService.get_rules(db, school_id)
        if not rule:
            rule = EvaluationRule(school_id=school_id)
            db.add(rule)

        for key, value in kwargs.items():
            if value is not None and hasattr(rule, key):
                if key in ("dimension_weights", "deduction_map"):
                    setattr(
                        rule,
                        key,
                        value.model_dump() if hasattr(value, "model_dump") else dict(value),
                    )
                else:
                    setattr(rule, key, value)

        await db.flush()
        logger.info(f"[evaluation] 学校 {school_id} 评分规则已更新")
        return rule

    # ═══════════════════════════════════════════════════════════
    # 指标 CRUD
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def list_indicators(
        db: AsyncSession,
        school_id: int,
        dimension: str | None = None,
    ) -> list[dict]:
        """列出指标 — 按维度分组返回"""
        conditions = [
            EvaluationIndicator.school_id == school_id,
        ]
        if dimension:
            conditions.append(EvaluationIndicator.dimension == dimension)
        else:
            conditions.append(EvaluationIndicator.dimension.in_(DIMENSION_KEYS))

        result = await db.execute(
            select(EvaluationIndicator)
            .where(*conditions)
            .order_by(EvaluationIndicator.dimension, EvaluationIndicator.sort_order)
        )
        indicators = list(result.scalars().all())

        # 按维度分组
        grouped = {}
        for ind in indicators:
            dim = ind.dimension or "other"
            if dim not in grouped:
                grouped[dim] = {
                    "dimension": dim,
                    "dimension_name": DIMENSION_NAMES.get(dim, dim),
                    "indicators": [],
                }
            grouped[dim]["indicators"].append(ind)

        return list(grouped.values())

    @staticmethod
    async def create_indicator(
        db: AsyncSession,
        school_id: int,
        name: str,
        parent_id: int = 0,
        dimension: str | None = None,
        weight: float = 0.0,
        max_score: float = 100.0,
        sort_order: int = 0,
    ) -> EvaluationIndicator:
        """创建评价指标"""
        indicator = EvaluationIndicator(
            school_id=school_id,
            name=name,
            parent_id=parent_id,
            dimension=dimension,
            weight=weight,
            max_score=max_score,
            sort_order=sort_order,
        )
        db.add(indicator)
        await db.flush()
        logger.info(f"[evaluation] 已创建指标: {name} (维度: {dimension})")
        return indicator

    @staticmethod
    async def update_indicator(
        db: AsyncSession,
        indicator_id: int,
        school_id: int,
        **kwargs,
    ) -> EvaluationIndicator | None:
        """更新评价指标"""
        result = await db.execute(
            select(EvaluationIndicator).where(
                EvaluationIndicator.id == indicator_id,
                EvaluationIndicator.school_id == school_id,
            )
        )
        indicator = result.scalar_one_or_none()
        if not indicator:
            return None

        for key, value in kwargs.items():
            if value is not None and hasattr(indicator, key):
                setattr(indicator, key, value)

        await db.flush()
        return indicator

    @staticmethod
    async def toggle_indicator(
        db: AsyncSession,
        indicator_id: int,
        school_id: int,
    ) -> EvaluationIndicator | None:
        """切换指标启用/禁用"""
        result = await db.execute(
            select(EvaluationIndicator).where(
                EvaluationIndicator.id == indicator_id,
                EvaluationIndicator.school_id == school_id,
            )
        )
        indicator = result.scalar_one_or_none()
        if not indicator:
            return None

        indicator.is_active = not indicator.is_active
        await db.flush()
        logger.info(
            f"[evaluation] 指标 {indicator.name} {'启用' if indicator.is_active else '禁用'}"
        )
        return indicator

    @staticmethod
    async def delete_indicator(
        db: AsyncSession,
        indicator_id: int,
        school_id: int,
    ) -> bool:
        """删除指标（仅当无关联评分记录时）"""
        result = await db.execute(
            select(EvaluationIndicator).where(
                EvaluationIndicator.id == indicator_id,
                EvaluationIndicator.school_id == school_id,
            )
        )
        indicator = result.scalar_one_or_none()
        if not indicator:
            return False

        # 检查是否有评分记录关联
        count_result = await db.execute(
            select(func.count(EvaluationScore.id)).where(
                EvaluationScore.indicator_id == indicator_id,
            )
        )
        if count_result.scalar() > 0:
            raise ValueError(f"指标「{indicator.name}」已有评分记录，无法删除。请改用禁用。")

        await db.delete(indicator)
        await db.flush()
        logger.info(f"[evaluation] 已删除指标: {indicator.name}")
        return True

    # ═══════════════════════════════════════════════════════════
    # 正向加分排行榜
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def get_positive_score_ranking(
        db: AsyncSession,
        class_id: int | None = None,
        grade_id: int | None = None,
        school_id: int = 1,
        dimension: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """
        正向加分排行榜 — 按正向加分总分降序

        Args:
            class_id: 班级ID（可选，不传则返回全校排名）
            grade_id: 年级ID（可选）
            school_id: 学校ID
            dimension: 维度筛选（可选：moral/academic/health/art/social）
            limit: 返回记录数
            offset: 偏移量

        Returns:
            排名列表，每项包含 student_id, student_name, class_name, positive_score, record_count
        """
        # 构建基础查询：从 score_logs 表统计正向加分
        # 只统计 change_amount > 0 的记录（正向加分）
        from core.models import Class, Student

        query = (
            select(
                ScoreLog.student_id,
                Student.name.label("student_name"),
                Class.name.label("class_name"),
                func.sum(ScoreLog.change_amount).label("positive_score"),
                func.count(ScoreLog.id).label("record_count"),
            )
            .join(Student, ScoreLog.student_id == Student.id)
            .join(Class, Student.class_id == Class.id)
            .where(
                ScoreLog.change_amount > 0,  # 只统计正向加分
                Class.school_id == school_id,
            )
        )

        # 维度筛选（ScoreLog 自带 dimension 字段）
        if dimension:
            query = query.where(ScoreLog.dimension == dimension)

        # 班级/年级筛选
        if class_id:
            query = query.where(Student.class_id == class_id)
        if grade_id:
            query = query.where(Class.grade_id == grade_id)

        # 分组、排序、分页
        query = (
            query.group_by(ScoreLog.student_id, Student.name, Class.name)
            .order_by(func.sum(ScoreLog.change_amount).desc())
            .limit(limit)
            .offset(offset)
        )

        result = await db.execute(query)
        rows = result.all()

        # 格式化结果
        ranking = []
        for rank, row in enumerate(rows, offset + 1):
            ranking.append(
                {
                    "rank": rank,
                    "student_id": row.student_id,
                    "student_name": row.student_name,
                    "class_name": row.class_name,
                    "positive_score": int(row.positive_score or 0),
                    "record_count": int(row.record_count or 0),
                }
            )

        return ranking

    # ═══════════════════════════════════════════════════════════
    # 工具
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def _current_semester() -> str:
        """计算当前学期: '2025-2026-2' / '2026-2027-1'"""
        from datetime import timedelta, timezone

        now = datetime.now(timezone(timedelta(hours=8)))
        y = now.year
        m = now.month
        if m >= 9:
            return f"{y}-{y + 1}-1"
        elif m >= 2:
            return f"{y - 1}-{y}-2"
        else:
            return f"{y - 1}-{y}-2"
