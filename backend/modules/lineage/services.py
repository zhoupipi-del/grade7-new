"""
modules/lineage/services.py — 血缘查询服务

提供因果链追溯、学生全链路查询、统计概览等查询能力。
"""

import logging
from typing import Optional, List, Dict, Any
from sqlalchemy import select, func, desc, and_
from sqlalchemy.ext.asyncio import AsyncSession

from modules.lineage.models import LineageEvent
from modules.lineage.schemas import (
    CausalNode, CausalChain, LineageStatsOut, LineageEventListItem,
    ScoreLogBrief, ScoreTraceOut,
)
from modules.evaluation.models import ScoreLog
from core.models import Student, Class, User

logger = logging.getLogger("lineage.services")


class LineageService:
    """血缘追踪查询服务"""

    @staticmethod
    async def get_trace_chain(
        db: AsyncSession,
        trace_id: str,
    ) -> Optional[CausalChain]:
        """
        查询一条完整的因果关系链
        按 lineage_depth 升序排列，展示从源头到终点的全链路
        """
        result = await db.execute(
            select(LineageEvent)
            .where(LineageEvent.trace_id == trace_id)
            .order_by(LineageEvent.lineage_depth.asc(), LineageEvent.created_at.asc())
        )
        events = result.scalars().all()

        if not events:
            return None

        nodes = [
            CausalNode(
                id=e.id,
                transformation=e.transformation,
                source_type=e.source_type,
                target_type=e.target_type,
                lineage_depth=e.lineage_depth,
                context=e.context,
                created_at=e.created_at,
            )
            for e in events
        ]

        return CausalChain(
            trace_id=trace_id,
            student_id=events[0].student_id,
            nodes=nodes,
            total_depth=events[-1].lineage_depth,
            started_at=events[0].created_at,
            ended_at=events[-1].created_at,
        )

    @staticmethod
    async def get_student_lineage(
        db: AsyncSession,
        student_id: int,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """查询某个学生的全部血缘事件（分页）"""
        base_query = select(LineageEvent).where(
            LineageEvent.student_id == student_id
        )

        # 总数
        count_result = await db.execute(
            select(func.count()).select_from(base_query.subquery())
        )
        total = count_result.scalar() or 0

        # 分页数据
        result = await db.execute(
            base_query
            .order_by(desc(LineageEvent.created_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        events = result.scalars().all()

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": [
                LineageEventListItem.model_validate(e) for e in events
            ],
        }

    @staticmethod
    async def get_source_descendants(
        db: AsyncSession,
        source_type: str,
        source_id: int,
    ) -> List[CausalChain]:
        """
        查询某个源实体的所有下游影响
        例如: "违纪记录 #42 导致了哪些扣分和快照变更？"
        """
        # 找到所有以此源为起点的血缘事件
        result = await db.execute(
            select(LineageEvent.trace_id)
            .where(
                and_(
                    LineageEvent.source_type == source_type,
                    LineageEvent.source_id == source_id,
                )
            )
            .distinct()
        )
        trace_ids = [row[0] for row in result.all()]

        chains = []
        for tid in trace_ids:
            chain = await LineageService.get_trace_chain(db, tid)
            if chain:
                chains.append(chain)

        return chains

    @staticmethod
    async def get_stats(db: AsyncSession, school_id: int = 1) -> LineageStatsOut:
        """血缘统计概览"""
        # 总事件数
        total_result = await db.execute(
            select(func.count()).select_from(
                select(LineageEvent).where(LineageEvent.school_id == school_id).subquery()
            )
        )
        total_events = total_result.scalar() or 0

        # 总因果链数
        traces_result = await db.execute(
            select(
                func.count(func.distinct(LineageEvent.trace_id))
            ).where(LineageEvent.school_id == school_id)
        )
        total_traces = traces_result.scalar() or 0

        # 按转换类型统计
        trans_result = await db.execute(
            select(
                LineageEvent.transformation,
                func.count(LineageEvent.id),
            )
            .where(LineageEvent.school_id == school_id)
            .group_by(LineageEvent.transformation)
        )
        by_transformation = {row[0]: row[1] for row in trans_result.all()}

        # 按源类型统计
        src_result = await db.execute(
            select(
                LineageEvent.source_type,
                func.count(LineageEvent.id),
            )
            .where(LineageEvent.school_id == school_id)
            .group_by(LineageEvent.source_type)
        )
        by_source_type = {row[0]: row[1] for row in src_result.all()}

        # 按目标类型统计
        tgt_result = await db.execute(
            select(
                LineageEvent.target_type,
                func.count(LineageEvent.id),
            )
            .where(LineageEvent.school_id == school_id)
            .group_by(LineageEvent.target_type)
        )
        by_target_type = {row[0]: row[1] for row in tgt_result.all()}

        # 最近 10 条事件
        recent = await db.execute(
            select(LineageEvent)
            .where(LineageEvent.school_id == school_id)
            .order_by(desc(LineageEvent.created_at))
            .limit(10)
        )
        recent_events = [
            LineageEventListItem.model_validate(e) for e in recent.scalars().all()
        ]

        return LineageStatsOut(
            total_events=total_events,
            total_traces=total_traces,
            by_transformation=by_transformation,
            by_source_type=by_source_type,
            by_target_type=by_target_type,
            recent_events=recent_events,
        )

    @staticmethod
    async def search_lineage(
        db: AsyncSession,
        school_id: int = 1,
        student_id: Optional[int] = None,
        source_type: Optional[str] = None,
        source_id: Optional[int] = None,
        target_type: Optional[str] = None,
        target_id: Optional[int] = None,
        transformation: Optional[str] = None,
        trace_id: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """灵活的多条件血缘查询"""
        conditions = [LineageEvent.school_id == school_id]
        if student_id is not None:
            conditions.append(LineageEvent.student_id == student_id)
        if source_type:
            conditions.append(LineageEvent.source_type == source_type)
        if source_id is not None:
            conditions.append(LineageEvent.source_id == source_id)
        if target_type:
            conditions.append(LineageEvent.target_type == target_type)
        if target_id is not None:
            conditions.append(LineageEvent.target_id == target_id)
        if transformation:
            conditions.append(LineageEvent.transformation == transformation)
        if trace_id:
            conditions.append(LineageEvent.trace_id == trace_id)

        base_query = select(LineageEvent).where(and_(*conditions))

        count_result = await db.execute(
            select(func.count()).select_from(base_query.subquery())
        )
        total = count_result.scalar() or 0

        result = await db.execute(
            base_query
            .order_by(desc(LineageEvent.created_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        events = result.scalars().all()

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": [
                LineageEventListItem.model_validate(e) for e in events
            ],
        }

    # ═══════════════════════════════════════════════════════════
    # #1193 成绩出生证明
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def get_score_trace(
        db: AsyncSession,
        score_log_id: int,
    ) -> Optional[ScoreTraceOut]:
        """
        从 ScoreLog 倒追完整血缘 — 成绩出生证明。

        数据溯源链路:
          ScoreLog.trace_context_id → LineageEvent.trace_id
            → 完整因果链 (源事件 → 中间转换 → 最终快照)
          ScoreLog.student_id → Student.name + Class.name
          ScoreLog.actor_id/created_by → User.display_name

        返回值可直接用于：
          - 家长质疑 "为什么扣了 3 分" 的一键溯源
          - 德育处审计 "谁在什么时间以什么理由改了分数"
          - 前端成绩出生证明面板
        """
        # 1. 查询 ScoreLog
        result = await db.execute(
            select(ScoreLog).where(ScoreLog.id == score_log_id)
        )
        score_log = result.scalar_one_or_none()
        if not score_log:
            return None

        # 2. 查询 Student + Class
        student = None
        class_ = None
        if score_log.student_id:
            student_result = await db.execute(
                select(Student).where(Student.id == score_log.student_id)
            )
            student = student_result.scalar_one_or_none()
            if student:
                class_result = await db.execute(
                    select(Class).where(Class.id == student.class_id)
                )
                class_ = class_result.scalar_one_or_none()

        # 3. 查询 Actor（优先 actor_id，回退 created_by）
        actor = None
        actor_id = score_log.actor_id or score_log.created_by
        if actor_id:
            actor_result = await db.execute(
                select(User).where(User.id == actor_id)
            )
            actor = actor_result.scalar_one_or_none()

        # 4. 查询血缘因果链
        causal_chain = None
        lineage_status = "untracked"
        if score_log.trace_context_id:
            causal_chain = await LineageService.get_trace_chain(
                db, score_log.trace_context_id
            )
            lineage_status = "tracked" if causal_chain else "orphaned"

        # 5. 查询同学生的最近 10 条血缘事件
        related_events: list = []
        if score_log.student_id:
            related_result = await db.execute(
                select(LineageEvent)
                .where(LineageEvent.student_id == score_log.student_id)
                .order_by(desc(LineageEvent.created_at))
                .limit(10)
            )
            related_events = [
                LineageEventListItem.model_validate(e)
                for e in related_result.scalars().all()
            ]

        # 6. 组装 ScoreTraceOut
        return ScoreTraceOut(
            score_log=ScoreLogBrief(
                id=score_log.id,
                student_id=score_log.student_id,
                student_name=student.name if student else None,
                class_name=class_.name if class_ else None,
                dimension=score_log.dimension,
                change_amount=score_log.change_amount,
                before_score=score_log.before_score,
                after_score=score_log.after_score,
                reason=score_log.reason,
                source_type=score_log.source_type,
                source_id=score_log.source_id,
                policy_tag=score_log.policy_tag,
                actor_id=actor_id,
                actor_name=actor.display_name if actor else None,
                source_ip=score_log.source_ip,
                diff_snapshot=score_log.diff_snapshot,
                created_at=score_log.created_at,
            ),
            causal_chain=causal_chain,
            related_events=related_events,
            lineage_status=lineage_status,
        )
