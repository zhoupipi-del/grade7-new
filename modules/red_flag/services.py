"""
modules/red_flag/services.py — 流动红旗三维加权引擎

算法管道:
  ① 跨模块聚合 → ② 权重重分配 → ③ 加权底分 →
  ④ 违纪熔断扣分 → ⑤ 考勤熔断扣分 → ⑥ 最终得分

标准权重: 班主任 0.2 | 年级组 0.3 | 德育处 0.5
缺失维度自动重分配（按现有维度比例瓜分缺失权重）

周期扣分系数:
  week:  违纪0.10  考勤0.05  (周期短，力度大)
  month: 违纪0.05  考勤0.03  (周期中，力度中)
  term:  违纪0.01  考勤0.01  (周期长，力度小)

核心函数:
  generate_evaluations() — 一步到位：聚合→加权→扣分→落库草稿
  publish_evaluations() — 计算排名→发布
  archive_evaluations() — 物理冻结快照
  get_leaderboard()      — 已发布排名展示
"""

from datetime import date, datetime
from typing import Optional

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import get_local_now

# ── 标准权重基座 ──
BASE_WEIGHTS = [0.2, 0.3, 0.5]  # self, grade, ms

# ── 周期→扣分系数映射 ──
DEDUCTION_COEFFICIENTS = {
    "week":  {"discipline": 0.10, "attendance": 0.05},
    "month": {"discipline": 0.05, "attendance": 0.03},
    "term":  {"discipline": 0.01, "attendance": 0.01},
}


class FlagService:
    """流动红旗服务 — 三维度加权 + 草稿/发布/归档"""

    # ═══════════════════════════════════════════════════════════
    # 权重重分配算法
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def _calc_weights(
        self_score: Optional[float],
        grade_score: Optional[float],
        ms_score: Optional[float],
    ) -> tuple[list[float], float]:
        """
        计算三维度实际权重与加权底分。

        标准权重: [0.2, 0.3, 0.5]
        某维度缺失(data=None)时，其余维度按比例瓜分该维度权重。

        Returns:
            ([self_weight, grade_weight, ms_weight], base_score)
        """
        scores = [self_score, grade_score, ms_score]
        available = [s is not None for s in scores]

        if not any(available):
            return [0.2, 0.3, 0.5], 0.0

        if all(available):
            base = sum(s * w for s, w in zip(scores, BASE_WEIGHTS))
            return list(BASE_WEIGHTS), round(base, 2)

        # ── 缺失维度权重按比例重分配 ──
        missing_weight = sum(w for w, a in zip(BASE_WEIGHTS, available) if not a)
        avail_indices = [i for i, a in enumerate(available) if a]
        avail_total_w = sum(BASE_WEIGHTS[i] for i in avail_indices)

        weights = list(BASE_WEIGHTS)
        for i in avail_indices:
            weights[i] = BASE_WEIGHTS[i] + missing_weight * (BASE_WEIGHTS[i] / avail_total_w)
        for i in range(3):
            if not available[i]:
                weights[i] = 0.0

        base = sum(s * w for s, w in zip(scores, weights) if s is not None)
        return weights, round(base, 2)

    # ═══════════════════════════════════════════════════════════
    # 三类 RoutineScore CRUD
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def add_routine(
        db: AsyncSession,
        class_id: int,
        grade_id: int,
        category: str,
        score: int,
        scorer_type: str,
        record_date: date,
        school_id: int,
        inspector: Optional[str] = None,
        note: Optional[str] = None,
    ) -> dict:
        from .models import RoutineScore

        rs = RoutineScore(
            school_id=school_id,
            class_id=class_id,
            grade_id=grade_id,
            category=category,
            score=score,
            scorer_type=scorer_type,
            record_date=record_date,
            inspector=inspector,
            note=note,
        )
        db.add(rs)
        await db.flush()
        return {
            "id": rs.id,
            "class_id": rs.class_id,
            "category": rs.category,
            "score": rs.score,
            "scorer_type": rs.scorer_type,
            "record_date": rs.record_date.isoformat(),
        }

    @staticmethod
    async def add_routine_batch(
        db: AsyncSession, scores: list[dict], school_id: int
    ) -> dict:
        from .models import RoutineScore

        created = []
        for s in scores:
            rs = RoutineScore(
                school_id=school_id,
                class_id=s["class_id"],
                grade_id=s["grade_id"],
                category=s["category"],
                score=s["score"],
                scorer_type=s["scorer_type"],
                record_date=s["record_date"],
                inspector=s.get("inspector"),
                note=s.get("note"),
            )
            db.add(rs)
            created.append(rs)
        await db.flush()
        return {"created": len(created)}

    @staticmethod
    async def list_routines(
        db: AsyncSession,
        school_id: int,
        grade_id: Optional[int] = None,
        class_id: Optional[int] = None,
        scorer_type: Optional[str] = None,
        category: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        offset: int = 0,
        limit: int = 100,
    ) -> dict:
        from .models import RoutineScore

        conditions = [RoutineScore.school_id == school_id]
        if grade_id:
            conditions.append(RoutineScore.grade_id == grade_id)
        if class_id:
            conditions.append(RoutineScore.class_id == class_id)
        if scorer_type:
            conditions.append(RoutineScore.scorer_type == scorer_type)
        if category:
            conditions.append(RoutineScore.category == category)
        if start_date:
            conditions.append(RoutineScore.record_date >= start_date)
        if end_date:
            conditions.append(RoutineScore.record_date <= end_date)

        # count
        cnt_q = select(func.count()).where(*conditions)
        r = await db.execute(cnt_q)
        total = r.scalar() or 0

        # items
        q = (
            select(RoutineScore)
            .where(*conditions)
            .order_by(RoutineScore.record_date.desc(), RoutineScore.id.desc())
            .offset(offset)
            .limit(limit)
        )
        r = await db.execute(q)
        items = r.scalars().all()

        return {"total": total, "items": list(items)}

    @staticmethod
    async def delete_routine(db: AsyncSession, routine_id: int, school_id: int) -> bool:
        from .models import RoutineScore

        r = await db.get(RoutineScore, routine_id)
        if not r or r.school_id != school_id:
            return False
        await db.delete(r)
        await db.flush()
        return True

    # ═══════════════════════════════════════════════════════════
    # 生成评价草稿（核心算法管道）
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def generate_evaluations(
        db: AsyncSession,
        school_id: int,
        grade_id: int,
        period_type: str,
        period_label: str,
        start_date: date,
        end_date: date,
    ) -> dict:
        """
        全自动生成流动红旗评价草稿。

        管道步骤:
          1. 聚合 RoutineScore → self_score/grade_score/ms_score（按班级取 AVG）
          2. 调用 _calc_weights() 计算实际权重与加权底分
          3. 从 discipline_records 聚合违纪总分 → 扣分
          4. 从 attendance_records 聚合异常次数 → 扣分
          5. final_score = max(0, base_score - 违纪扣分 - 考勤扣分)
          6. 写入 FlagEvaluation (status=draft)，幂等替换同周期旧草稿
        """
        from .models import FlagEvaluation, RoutineScore

        # ── Step 0: 获取该年级所有班级 ──
        r = await db.execute(
            text("SELECT id, name FROM classes WHERE grade_id=:gid AND school_id=:sid"),
            {"gid": grade_id, "sid": school_id},
        )
        class_rows = r.fetchall()
        if not class_rows:
            return {"error": "该年级没有班级", "count": 0}

        # ── Step 0b: 删除同周期旧草稿（幂等）──
        await db.execute(
            text(
                "DELETE FROM flag_evaluations WHERE school_id=:sid AND period_type=:pt "
                "AND period_label=:pl AND grade_id=:gid AND status='draft'"
            ),
            {"sid": school_id, "pt": period_type, "pl": period_label, "gid": grade_id},
        )

        # ── Step 1: 聚合 RoutineScore 按班级 + scorer_type ──
        r = await db.execute(
            select(
                RoutineScore.class_id,
                RoutineScore.scorer_type,
                func.avg(RoutineScore.score).label("avg_score"),
            )
            .where(
                RoutineScore.school_id == school_id,
                RoutineScore.grade_id == grade_id,
                RoutineScore.record_date >= start_date,
                RoutineScore.record_date <= end_date,
            )
            .group_by(RoutineScore.class_id, RoutineScore.scorer_type)
        )
        agg_rows = r.fetchall()

        # 组织: {class_id: {scorer_type: avg_score}}
        agg_map: dict[int, dict[str, float]] = {}
        for cid, st, avg in agg_rows:
            agg_map.setdefault(cid, {})[st] = round(float(avg), 2)

        # ── Step 2: 违纪扣分聚合 ──
        coeff = DEDUCTION_COEFFICIENTS.get(period_type, DEDUCTION_COEFFICIENTS["week"])
        r = await db.execute(
            text(
                "SELECT class_id, COALESCE(SUM(points), 0) AS total_points "
                "FROM discipline_records "
                "WHERE school_id=:sid AND grade_id=:gid "
                "AND incident_date >= :sd AND incident_date <= :ed "
                "GROUP BY class_id"
            ),
            {"sid": school_id, "gid": grade_id, "sd": start_date, "ed": end_date},
        )
        disc_map = {row[0]: float(row[1]) for row in r.fetchall()}

        # ── Step 3: 考勤异常聚合 ──
        r = await db.execute(
            text(
                "SELECT class_id, COUNT(*) AS exc_count "
                "FROM attendance_records "
                "WHERE school_id=:sid AND grade_id=:gid "
                "AND status IN ('late','absent','early') "
                "AND record_date >= :sd AND record_date <= :ed "
                "GROUP BY class_id"
            ),
            {"sid": school_id, "gid": grade_id, "sd": start_date, "ed": end_date},
        )
        att_map = {row[0]: row[1] for row in r.fetchall()}

        # ── Step 4: 逐班生成 FlagEvaluation ──
        created = []
        for cid, cname in class_rows:
            scores = agg_map.get(cid, {})
            self_score = scores.get("class_teacher")
            grade_score = scores.get("grade_leader")
            ms_score = scores.get("ms_admin")

            weights, base_score = FlagService._calc_weights(self_score, grade_score, ms_score)

            disc_points = disc_map.get(cid, 0.0)
            disc_deduction = round(disc_points * coeff["discipline"], 2)

            att_exc = att_map.get(cid, 0)
            att_deduction = round(att_exc * coeff["attendance"], 2)

            final = max(0.0, round(base_score - disc_deduction - att_deduction, 2))

            fe = FlagEvaluation(
                school_id=school_id,
                period_type=period_type,
                period_label=period_label,
                grade_id=grade_id,
                class_id=cid,
                self_score=self_score,
                grade_score=grade_score,
                ms_score=ms_score,
                self_weight=weights[0],
                grade_weight=weights[1],
                ms_weight=weights[2],
                base_score=base_score,
                discipline_points=disc_points,
                discipline_deduction=disc_deduction,
                attendance_exceptions=att_exc,
                attendance_deduction=att_deduction,
                final_score=final,
                status="draft",
            )
            db.add(fe)
            created.append(fe)

        await db.flush()
        return {
            "message": f"生成 {len(created)} 个班级的评价草稿",
            "period_type": period_type,
            "period_label": period_label,
            "grade_id": grade_id,
            "count": len(created),
        }

    # ═══════════════════════════════════════════════════════════
    # 发布评价
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def publish_evaluations(
        db: AsyncSession,
        school_id: int,
        grade_id: int,
        period_type: str,
        period_label: str,
    ) -> dict:
        """
        发布草稿 → 按 final_score 降序排列 → 分配 rank → 状态=published
        """
        from .models import FlagEvaluation
        from sqlalchemy import update

        r = await db.execute(
            select(FlagEvaluation).where(
                FlagEvaluation.school_id == school_id,
                FlagEvaluation.grade_id == grade_id,
                FlagEvaluation.period_type == period_type,
                FlagEvaluation.period_label == period_label,
                FlagEvaluation.status == "draft",
            )
        )
        drafts = r.scalars().all()

        if not drafts:
            return {"error": "没有待发布的草稿", "count": 0}

        # 按 final_score 降序排列
        drafts.sort(key=lambda x: x.final_score, reverse=True)
        now = get_local_now()
        for rank_idx, fe in enumerate(drafts, start=1):
            fe.rank = rank_idx
            fe.status = "published"
            fe.published_at = now

        await db.flush()
        return {
            "message": f"发布完成，共 {len(drafts)} 个班级",
            "period_type": period_type,
            "period_label": period_label,
            "grade_id": grade_id,
            "published_count": len(drafts),
        }

    # ═══════════════════════════════════════════════════════════
    # 查看排行榜 / 草稿
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def get_leaderboard(
        db: AsyncSession,
        school_id: int,
        grade_id: Optional[int] = None,
        period_type: Optional[str] = None,
        period_label: Optional[str] = None,
    ) -> list[dict]:
        """获取已发布的排行榜"""
        from .models import FlagEvaluation

        conditions = [
            FlagEvaluation.school_id == school_id,
            FlagEvaluation.status == "published",
        ]
        if grade_id:
            conditions.append(FlagEvaluation.grade_id == grade_id)
        if period_type:
            conditions.append(FlagEvaluation.period_type == period_type)
        if period_label:
            conditions.append(FlagEvaluation.period_label == period_label)

        q = select(FlagEvaluation).where(*conditions).order_by(
            FlagEvaluation.period_label.desc(),
            FlagEvaluation.grade_id,
            FlagEvaluation.rank.is_(None).asc(),
            FlagEvaluation.rank.asc(),
        )
        r = await db.execute(q)
        items = r.scalars().all()

        # 补 class_name
        return await FlagService._enrich_with_class_names(db, items)

    @staticmethod
    async def get_drafts(
        db: AsyncSession,
        school_id: int,
        grade_id: Optional[int] = None,
        period_type: Optional[str] = None,
    ) -> list[dict]:
        """查看草稿列表"""
        from .models import FlagEvaluation

        conditions = [
            FlagEvaluation.school_id == school_id,
            FlagEvaluation.status == "draft",
        ]
        if grade_id:
            conditions.append(FlagEvaluation.grade_id == grade_id)
        if period_type:
            conditions.append(FlagEvaluation.period_type == period_type)

        q = select(FlagEvaluation).where(*conditions).order_by(
            FlagEvaluation.period_label.desc(),
            FlagEvaluation.grade_id,
            FlagEvaluation.final_score.desc(),
        )
        r = await db.execute(q)
        items = r.scalars().all()
        return await FlagService._enrich_with_class_names(db, items)

    # ═══════════════════════════════════════════════════════════
    # 归档
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def archive_evaluations(
        db: AsyncSession,
        school_id: int,
        grade_id: int,
        period_type: str,
        period_label: str,
        archived_by: int,
    ) -> dict:
        """
        归档已发布评价 → FlagArchiveReport 物理快照。

        快照数据结构:
        {
          "class_name": "...",
          "period_label": "...",
          "scores": {self_score, grade_score, ms_score, ...weights},
          "base_score": ...,
          "deductions_detail": {discipline: {minus, raw_points}, attendance: {minus, exceptions_count}}
        }
        """
        from .models import FlagEvaluation, FlagArchiveReport

        # ── 幂等检查 ──
        r = await db.execute(
            text(
                "SELECT COUNT(*) FROM flag_archive_reports "
                "WHERE school_id=:sid AND period_type=:pt AND period_label=:pl AND grade_id=:gid"
            ),
            {"sid": school_id, "pt": period_type, "pl": period_label, "gid": grade_id},
        )
        existing = r.scalar() or 0
        if existing > 0:
            return {
                "error": f"周期 {period_label} 已有 {existing} 条归档记录，不可重复归档（历史快照不可变）",
                "already_archived": True,
            }

        # ── 查询已发布数据 ──
        r = await db.execute(
            select(FlagEvaluation).where(
                FlagEvaluation.school_id == school_id,
                FlagEvaluation.grade_id == grade_id,
                FlagEvaluation.period_type == period_type,
                FlagEvaluation.period_label == period_label,
                FlagEvaluation.status == "published",
            )
        )
        published = r.scalars().all()

        if not published:
            return {"error": "没有已发布的评价可归档", "count": 0}

        # ── 获取班级名称 ──
        class_ids = [fe.class_id for fe in published]
        r = await db.execute(
            text("SELECT id, name FROM classes WHERE id IN :cids AND school_id=:sid"),
            {"cids": tuple(class_ids), "sid": school_id},
        )
        class_name_map = {row[0]: row[1] for row in r.fetchall()}

        # ── 前2名获红旗 ──
        published.sort(key=lambda x: x.final_score, reverse=True)
        flag_count = 2

        now = get_local_now()
        archived = 0
        for fe in published:
            # 组装快照 JSON
            snapshot = {
                "class_name": class_name_map.get(fe.class_id, f"班级{fe.class_id}"),
                "period_label": fe.period_label,
                "scores": {
                    "self_score": fe.self_score,
                    "grade_score": fe.grade_score,
                    "ms_score": fe.ms_score,
                    "self_weight": fe.self_weight,
                    "grade_weight": fe.grade_weight,
                    "ms_weight": fe.ms_weight,
                },
                "base_score": fe.base_score,
                "deductions_detail": {
                    "discipline": {
                        "minus": fe.discipline_deduction or 0,
                        "raw_points": fe.discipline_points or 0,
                    },
                    "attendance": {
                        "minus": fe.attendance_deduction or 0,
                        "exceptions_count": fe.attendance_exceptions or 0,
                    },
                },
            }

            # 判断是否获红旗（前 N 名）
            has_flag = (fe.rank is not None and fe.rank <= flag_count)

            ar = FlagArchiveReport(
                school_id=school_id,
                period_type=fe.period_type,
                period_label=fe.period_label,
                grade_id=fe.grade_id,
                class_id=fe.class_id,
                final_score=fe.final_score,
                rank=fe.rank,
                has_flag=has_flag,
                base_score=fe.base_score,
                discipline_deduction=fe.discipline_deduction or 0.0,
                attendance_deduction=fe.attendance_deduction or 0.0,
                snapshot_data_json="",
                archived_at=now,
                archived_by=archived_by,
            )
            ar.snapshot_data = snapshot  # trigger setter → JSON serialization
            db.add(ar)
            archived += 1

        await db.flush()
        return {
            "message": f"归档完成，共 {archived} 条记录",
            "period_type": period_type,
            "period_label": period_label,
            "grade_id": grade_id,
            "archived_count": archived,
        }

    # ═══════════════════════════════════════════════════════════
    # 历史趋势 / 归档查询
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def get_class_trends(
        db: AsyncSession, school_id: int, class_id: int
    ) -> dict:
        """获取某班级的历史趋势（归档数据）"""
        from .models import FlagArchiveReport

        q = (
            select(FlagArchiveReport)
            .where(
                FlagArchiveReport.school_id == school_id,
                FlagArchiveReport.class_id == class_id,
            )
            .order_by(FlagArchiveReport.archived_at.asc())
        )
        r = await db.execute(q)
        items = r.scalars().all()

        # 获取班级名称
        r = await db.execute(
            text("SELECT name FROM classes WHERE id=:cid AND school_id=:sid"),
            {"cid": class_id, "sid": school_id},
        )
        cname_row = r.fetchone()

        periods = [ar.period_label for ar in items]
        scores = [ar.final_score for ar in items]
        ranks = [ar.rank for ar in items]
        total_flags = sum(1 for ar in items if ar.has_flag)

        return {
            "class_id": class_id,
            "class_name": cname_row[0] if cname_row else None,
            "periods": periods,
            "scores": scores,
            "ranks": ranks,
            "total_flags_won": total_flags,
        }

    @staticmethod
    async def get_archive_history(
        db: AsyncSession,
        school_id: int,
        grade_id: Optional[int] = None,
        class_id: Optional[int] = None,
        period_type: Optional[str] = None,
        offset: int = 0,
        limit: int = 50,
    ) -> dict:
        """查询归档历史"""
        from .models import FlagArchiveReport

        conditions = [FlagArchiveReport.school_id == school_id]
        if grade_id:
            conditions.append(FlagArchiveReport.grade_id == grade_id)
        if class_id:
            conditions.append(FlagArchiveReport.class_id == class_id)
        if period_type:
            conditions.append(FlagArchiveReport.period_type == period_type)

        cnt_q = select(func.count()).where(*conditions)
        r = await db.execute(cnt_q)
        total = r.scalar() or 0

        q = (
            select(FlagArchiveReport)
            .where(*conditions)
            .order_by(FlagArchiveReport.archived_at.desc())
            .offset(offset)
            .limit(limit)
        )
        r = await db.execute(q)
        items = r.scalars().all()

        # 补 class_name
        enriched = await FlagService._enrich_archives_with_class_names(db, list(items))

        return {"total": total, "items": enriched}

    # ═══════════════════════════════════════════════════════════
    # 工具
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def _enrich_with_class_names(db: AsyncSession, items: list) -> list[dict]:
        """为 FlagEvaluation 对象补充 class_name 字段"""
        if not items:
            return []
        class_ids = list({getattr(it, "class_id", it.class_id) for it in items})
        if not class_ids:
            return []

        r = await db.execute(
            text("SELECT id, name FROM classes WHERE id IN :cids"),
            {"cids": tuple(class_ids)},
        )
        name_map = {row[0]: row[1] for row in r.fetchall()}

        result = []
        for fe in items:
            d = {
                "id": fe.id,
                "period_type": fe.period_type,
                "period_label": fe.period_label,
                "grade_id": fe.grade_id,
                "class_id": fe.class_id,
                "class_name": name_map.get(fe.class_id),
                "self_score": fe.self_score,
                "grade_score": fe.grade_score,
                "ms_score": fe.ms_score,
                "self_weight": fe.self_weight,
                "grade_weight": fe.grade_weight,
                "ms_weight": fe.ms_weight,
                "base_score": fe.base_score,
                "discipline_points": fe.discipline_points,
                "discipline_deduction": fe.discipline_deduction,
                "attendance_exceptions": fe.attendance_exceptions,
                "attendance_deduction": fe.attendance_deduction,
                "final_score": fe.final_score,
                "rank": fe.rank,
                "status": fe.status,
                "created_at": fe.created_at.isoformat() if fe.created_at else None,
                "published_at": fe.published_at.isoformat() if fe.published_at else None,
            }
            result.append(d)
        return result

    @staticmethod
    async def _enrich_archives_with_class_names(db: AsyncSession, items: list) -> list[dict]:
        """为 FlagArchiveReport 对象补充 class_name"""
        if not items:
            return []
        class_ids = list({it.class_id for it in items})
        r = await db.execute(
            text("SELECT id, name FROM classes WHERE id IN :cids"),
            {"cids": tuple(class_ids)},
        )
        name_map = {row[0]: row[1] for row in r.fetchall()}

        result = []
        for ar in items:
            result.append({
                "id": ar.id,
                "period_type": ar.period_type,
                "period_label": ar.period_label,
                "grade_id": ar.grade_id,
                "class_id": ar.class_id,
                "class_name": name_map.get(ar.class_id),
                "final_score": ar.final_score,
                "rank": ar.rank,
                "has_flag": ar.has_flag,
                "base_score": ar.base_score,
                "discipline_deduction": ar.discipline_deduction,
                "attendance_deduction": ar.attendance_deduction,
                "snapshot_data": ar.snapshot_data if hasattr(ar, "snapshot_data") else None,
                "archived_at": ar.archived_at.isoformat() if ar.archived_at else None,
                "archived_by": ar.archived_by,
            })
        return result
