"""
modules/evaluation/routers.py — 素质评价 API 端点

端点清单 (15):
  GET    /indicators                        — 按维度列出指标树
  POST   /indicators                        — 创建指标 (ms_admin)
  PUT    /indicators/{indicator_id}          — 更新指标 (ms_admin)
  POST   /indicators/{indicator_id}/toggle   — 切换启用/禁用 (ms_admin)
  DELETE /indicators/{indicator_id}          — 删除指标 (ms_admin)
  GET    /rules                             — 获取评分规则
  PUT    /rules                             — 更新评分规则 (ms_admin)
  POST   /scores                            — 手动录分
  POST   /scores/batch                      — 批量录分
  GET    /students/{student_id}/scores       — 学生五维分+总分
  GET    /classes/{class_id}/ranking         — 班级排名
  GET    /students/{student_id}/logs         — 评分流水审计
  POST   /seed                              — 初始化种子数据 (ms_admin)
  GET    /students/{student_id}/final-evaluation  — 期末综合评价(含处分)
  GET    /students/{student_id}/discipline-veto   — 一票否决检查
"""

import logging

from core.access import get_student_or_403
from core.models import User, UserRole
from core.routers import get_current_user, get_db, require_role
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from .schemas import (
    BatchScoreCreate,
    BatchScoreResult,
    ClassRankingOut,
    DisciplineVetoOut,
    IndicatorCreate,
    IndicatorGroupedOut,
    IndicatorOut,
    IndicatorUpdate,
    MessageOut,
    QuickPraiseCreate,
    QuickPraiseOut,
    RuleOut,
    RuleUpdate,
    ScoreCreate,
    ScoreLogListOut,
    ScoreOut,
    SeedResultOut,
    StudentScoreOut,
)
from .services import EvaluationService

logger = logging.getLogger("evaluation.api")
router = APIRouter(tags=["evaluation"])


# ── 辅助函数 ──────────────────────────────────────────────────


def _format_score_log(log, student_name: str = "", creator_name: str = "") -> dict:
    """安全格式化评分日志"""
    return {
        "id": log.id,
        "student_id": log.student_id,
        "student_name": student_name,
        "dimension": log.dimension,
        "change_amount": log.change_amount,
        "before_score": log.before_score,
        "after_score": log.after_score,
        "reason": log.reason,
        "source_type": log.source_type,
        "source_id": log.source_id,
        "created_by": log.created_by,
        "creator_name": creator_name,
        "created_at": log.created_at,
    }


def _format_student_score(ss, student_name: str = "", student_no: str = "") -> dict:
    """安全格式化学生总分快照"""
    return {
        "student_id": ss.student_id,
        "student_name": student_name,
        "student_no": student_no,
        "class_id": ss.class_id,
        "grade_id": ss.grade_id,
        "semester": ss.semester,
        "total_score": ss.total_score,
        "moral_score": ss.moral_score,
        "academic_score": ss.academic_score,
        "health_score": ss.health_score,
        "art_score": ss.art_score,
        "social_score": ss.social_score,
        "base_score": ss.base_score,
        "updated_at": ss.updated_at,
    }


# ═══════════════════════════════════════════════════════════════
# 指标管理
# ═══════════════════════════════════════════════════════════════


@router.get("/indicators", response_model=list[IndicatorGroupedOut])
async def list_indicators(
    dimension: str | None = Query(None, description="筛选维度: moral/academic/health/art/social"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """按维度分组列出评价指标树（含二级评分项）"""
    grouped = await EvaluationService.list_indicators(db, current_user.school_id, dimension)
    return grouped


@router.post("/indicators", response_model=IndicatorOut, status_code=201)
async def create_indicator(
    body: IndicatorCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _guard: User = Depends(require_role(UserRole.MS_ADMIN)),
):
    """创建评价指标（德育处管理员）"""
    try:
        indicator = await EvaluationService.create_indicator(
            db,
            current_user.school_id,
            name=body.name,
            parent_id=body.parent_id,
            dimension=body.dimension,
            weight=body.weight,
            max_score=body.max_score,
            sort_order=body.sort_order,
        )
        return indicator
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/indicators/{indicator_id}", response_model=IndicatorOut)
async def update_indicator(
    indicator_id: int,
    body: IndicatorUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _guard: User = Depends(require_role(UserRole.MS_ADMIN)),
):
    """更新评价指标"""
    indicator = await EvaluationService.update_indicator(
        db,
        indicator_id,
        current_user.school_id,
        **body.model_dump(exclude_none=True),
    )
    if not indicator:
        raise HTTPException(status_code=404, detail="指标不存在")
    return indicator


@router.post("/indicators/{indicator_id}/toggle", response_model=IndicatorOut)
async def toggle_indicator(
    indicator_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _guard: User = Depends(require_role(UserRole.MS_ADMIN)),
):
    """切换指标启用/禁用状态"""
    indicator = await EvaluationService.toggle_indicator(db, indicator_id, current_user.school_id)
    if not indicator:
        raise HTTPException(status_code=404, detail="指标不存在")
    return indicator


@router.delete("/indicators/{indicator_id}", response_model=MessageOut)
async def delete_indicator(
    indicator_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _guard: User = Depends(require_role(UserRole.MS_ADMIN)),
):
    """删除指标（仅当无关联评分记录时可用）"""
    try:
        deleted = await EvaluationService.delete_indicator(db, indicator_id, current_user.school_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="指标不存在")
        return {"message": "指标已删除", "detail": None}
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


# ═══════════════════════════════════════════════════════════════
# 评分规则
# ═══════════════════════════════════════════════════════════════


@router.get("/rules", response_model=RuleOut)
async def get_rules(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取学校当前生效的评分规则（无规则时自动创建默认）"""
    rule = await EvaluationService.ensure_rules(db, current_user.school_id)
    return rule


@router.put("/rules", response_model=RuleOut)
async def update_rules(
    body: RuleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _guard: User = Depends(require_role(UserRole.MS_ADMIN)),
):
    """更新评分规则（德育处管理员）"""
    try:
        rule = await EvaluationService.update_rules(
            db,
            current_user.school_id,
            **body.model_dump(exclude_none=True),
        )
        return rule
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ═══════════════════════════════════════════════════════════════
# 评分录入
# ═══════════════════════════════════════════════════════════════


@router.post("/scores", response_model=ScoreOut, status_code=201)
async def record_score(
    body: ScoreCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    录入手动评分 → 自动重算该学生总分快照。

    评分人权限（P0 越权修复 2026-08-13）：
      - 先经 ResourceScope → get_student_or_403 行级校验：
          跨校 → 404；本校越权（非本班/非授权年级/非管理员）→ 403
      - class_id / grade_id / school_id 一律由服务端从 student 反查，
        前端传值不作任何授权依据（旧客户端传了也被覆盖）
      - 评分人 = 当前用户（scorer_id=current_user.id 服务端写死）
    """
    # 1) 行级归属校验：跨校→404，本校越权→403
    student = await get_student_or_403(db, current_user, body.student_id)
    try:
        record = await EvaluationService.record_score(
            db,
            student_id=student.id,
            class_id=student.class_id,
            grade_id=student.grade_id,
            school_id=student.school_id,
            indicator_id=body.indicator_id,
            score=body.score,
            scorer_type=body.scorer_type,
            scorer_id=current_user.id,
            semester=body.semester,
            comment=body.comment,
            source=body.source or "legacy_unknown",
        )
        return {
            "id": record.id,
            "student_id": record.student_id,
            "class_id": record.class_id,
            "grade_id": record.grade_id,
            "indicator_id": record.indicator_id,
            "indicator_name": record.indicator.name if record.indicator else None,
            "score": record.score,
            "scorer_type": record.scorer_type,
            "scorer_id": record.scorer_id,
            "semester": record.semester,
            "comment": record.comment,
            "created_at": record.created_at,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/quick-praise", response_model=QuickPraiseOut, status_code=201)
async def quick_praise(
    body: QuickPraiseCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    极简正向表扬（Step6 · QuickPraise）——15 秒完成一条可信正向记录。

    服务端锁死：
      school/class/grade   = 从 student 反查（get_student_or_403 已校验归属）
      scorer               = 当前用户(teacher)
      source               = teacher_manual（前端不可传）
      indicator + score    = praise_type 服务端映射（杜绝标准不一）
      incident_date        = 当天

    权限：班主任/年级组长/管理员（行级范围仍受 get_student_or_403 约束）。
    """
    student = await get_student_or_403(db, current_user, body.student_id)
    try:
        record, default_score = await EvaluationService.quick_praise(
            db,
            student,
            current_user.id,
            body.praise_type,
            body.description,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    from .services import PRAISE_TYPE_MAP
    _, _, label = PRAISE_TYPE_MAP[body.praise_type]
    monthly = await EvaluationService.count_monthly_praise(
        db, student.school_id, student.id
    )
    return {
        "id": record.id,
        "student_id": record.student_id,
        "student_name": record.student.name if record.student else None,
        "class_name": record.student.class_.name if record.student and getattr(record.student, "class_", None) else None,
        "praise_type": body.praise_type,
        "praise_label": label,
        "indicator_name": record.indicator.name if record.indicator else None,
        "score": default_score,
        "source": record.source,
        "incident_date": record.incident_date,
        "monthly_praise_count": monthly,
    }


@router.post("/scores/batch", response_model=BatchScoreResult, status_code=201)
async def batch_record_scores(
    body: BatchScoreCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    批量录入手动评分（P0 越权修复 2026-08-13：逐条 get_student_or_403，
    class_id/grade_id/school_id 服务端反查，前端传值不生效）。
    逐条处理，遇到失败继续执行后续，返回成功/失败计数。
    """
    success = 0
    errors = []
    for i, sc in enumerate(body.scores):
        try:
            # 行级归属校验：跨校→404，本校越权→403
            student = await get_student_or_403(db, current_user, sc.student_id)
            await EvaluationService.record_score(
                db,
                student_id=student.id,
                class_id=student.class_id,
                grade_id=student.grade_id,
                school_id=student.school_id,
                indicator_id=sc.indicator_id,
                score=sc.score,
                scorer_type=sc.scorer_type,
                scorer_id=current_user.id,
                semester=sc.semester,
                comment=sc.comment,
                source=sc.source or "legacy_unknown",
            )
            success += 1
        except Exception as e:
            errors.append(
                {
                    "index": i,
                    "student_id": sc.student_id,
                    "indicator_id": sc.indicator_id,
                    "error": str(e),
                }
            )
    return {"success": success, "failed": len(errors), "errors": errors}


# ═══════════════════════════════════════════════════════════════
# 学生查询
# ═══════════════════════════════════════════════════════════════


@router.get("/students/{student_id}/scores", response_model=StudentScoreOut)
async def get_student_scores(
    student_id: int,
    semester: str | None = Query(None, description="学期，默认当前"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取单个学生的五维分 + 总分"""
    # P0 归属校验（2026-08-09 开学前审计）：原实现零守卫，任意登录用户可枚举
    # student_id 拿到他校/他班学生分数；查无快照时还会返回零值占位对象，
    # 造成"越权也有返回"的假数据。守卫前置后越权直接 404/403。
    await get_student_or_403(db, current_user, student_id)
    result = await EvaluationService.get_dimension_scores(db, student_id, semester)
    if not result:
        # 该学生还没有评分快照，返回空数据
        return StudentScoreOut(
            student_id=student_id,
            class_id=0,
            grade_id=0,
            semester=semester or EvaluationService._current_semester(),
            total_score=0.0,
            moral_score=0.0,
            academic_score=0.0,
            health_score=0.0,
            art_score=0.0,
            social_score=0.0,
            base_score=100.0,
        )

    # Flatten: service returns {"dimensions": {...}} → flat fields
    dims = result.get("dimensions", {})
    return {
        "student_id": result["student_id"],
        "class_id": result.get("class_id", 0),
        "grade_id": result.get("grade_id", 0),
        "semester": result["semester"],
        "total_score": result["total_score"],
        "moral_score": dims.get("moral", 0.0),
        "academic_score": dims.get("academic", 0.0),
        "health_score": dims.get("health", 0.0),
        "art_score": dims.get("art", 0.0),
        "social_score": dims.get("social", 0.0),
        "base_score": result.get("base_score", 100.0),
    }


@router.get("/classes/{class_id}/ranking", response_model=ClassRankingOut)
async def get_class_ranking(
    class_id: int,
    semester: str | None = Query(None, description="学期，默认当前"),
    limit: int = Query(50, ge=1, le=200, description="返回前 N 名"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """班级排名 — 按总分降序，返回前 N 名"""
    ranking = await EvaluationService.get_class_ranking(db, class_id, semester, limit)
    total = len(ranking)
    avg = round(sum(r["total_score"] for r in ranking) / max(total, 1), 1)
    return {
        "class_id": class_id,
        "semester": semester or EvaluationService._current_semester(),
        "total_students": total,
        "avg_score": avg,
        "ranking": ranking,
    }


# ═══════════════════════════════════════════════════════════════
# 审计日志
# ═══════════════════════════════════════════════════════════════


@router.get("/students/{student_id}/logs", response_model=ScoreLogListOut)
async def get_score_logs(
    student_id: int,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """评分流水审计 — 家长质疑"为什么扣分"时的精确回溯"""
    # P0 归属校验（2026-08-09 开学前审计）：流水含教师姓名与扣分理由
    await get_student_or_403(db, current_user, student_id)
    offset = (page - 1) * per_page
    logs, total = await EvaluationService.get_score_logs(db, student_id, per_page, offset)

    # 批量预加载创建人信息
    creator_ids = {log.created_by for log in logs if log.created_by}
    creator_map = {}
    if creator_ids:
        from sqlalchemy import select as sa_select

        r = await db.execute(sa_select(User).where(User.id.in_(list(creator_ids))))
        for u in r.scalars().all():
            creator_map[u.id] = u.display_name or u.username

    items = []
    for log in logs:
        student_name = log.student.name if log.student else ""
        creator_name = creator_map.get(log.created_by, "")
        items.append(_format_score_log(log, student_name, creator_name))

    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
    }


# ═══════════════════════════════════════════════════════════════
# 种子数据
# ═══════════════════════════════════════════════════════════════


@router.post("/seed", response_model=SeedResultOut)
async def seed_evaluation_data(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _guard: User = Depends(require_role(UserRole.MS_ADMIN)),
):
    """初始化评价引擎种子数据：评分规则 + 五维评价指标树（幂等）"""
    rule = await EvaluationService.ensure_rules(db, current_user.school_id)
    count = await EvaluationService.seed_indicators(db, current_user.school_id)
    return {
        "rules_created": rule is not None,
        "indicators_count": count,
        "message": f"已就绪：1 条评分规则 + {count} 条评价指标",
    }


# ═══════════════════════════════════════════════════════════════
# 处分强电桥接 — 期末综合评价 + 一票否决检查
# ═══════════════════════════════════════════════════════════════


@router.get("/students/{student_id}/final-evaluation")
async def get_final_evaluation(
    student_id: int,
    semester: str | None = Query(None, description="学期，默认当前"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    学生期末综合评价 — 含处分影响的最终裁定。

    返回:
      - base_scores: 纯评价引擎产出的五维原始分
      - discipline_penalty: ACTIVE 处分扣分详情
      - adjusted_scores: 扣分后的五维分（>=0 保底）
      - veto: 一票否决裁定（PROBATION/EXPULSION → D 等）
      - revoked_sanctions: 已撤销处分列表（"处分已撤销"正向标签）
      - final_grade: A/B/C/D
      - grade_label: 等级中文（优秀/良好/合格/不合格）
    """
    # P0 归属校验（2026-08-09 开学前审计）：含处分明细，属敏感数据
    await get_student_or_403(db, current_user, student_id)
    result = await EvaluationService.get_final_evaluation(
        db, student_id, current_user.school_id, semester
    )
    return result


@router.get("/students/{student_id}/discipline-veto", response_model=DisciplineVetoOut)
async def check_student_veto(
    student_id: int,
    semester: str | None = Query(None, description="学期，默认当前"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    一票否决快查 — 期末总评前快速判定学生是否处于处分熔断期。

    若 is_veto=True，学期总评直接覆写 D 等，无需其他计算。
    """
    # P0 归属校验（2026-08-09 开学前审计）：暴露学生是否处于处分期
    await get_student_or_403(db, current_user, student_id)
    return await EvaluationService.check_discipline_veto(db, student_id, semester)


# ═══════════════════════════════════════════════════════════════
# 正向加分排行榜
# ═══════════════════════════════════════════════════════════════


@router.get("/ranking/positive")
async def get_positive_score_ranking(
    class_id: int | None = Query(None, description="班级ID（不传则返回全校排名）"),
    grade_id: int | None = Query(None, description="年级ID"),
    dimension: str | None = Query(None, description="维度筛选（moral/academic/health/art/social）"),
    sort_by: str = Query("score", description="score=正向积分榜 / count=表扬次数榜"),
    limit: int = Query(50, ge=1, le=200, description="返回记录数"),
    offset: int = Query(0, ge=0, description="偏移量"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    正向加分排行榜 — 只消费「可信正向 EvaluationScore」（2026-08-13 治理）。

    数据源修复：旧实现读 score_logs(change_amount>0) 与 EvaluationScore 断裂，
    排行榜永远查不到正向加分。现直读 EvaluationScore 且严格过滤：
      source='teacher_manual' AND indicator∈正向表扬指标白名单
    成绩导入(import)与常规评分永不进榜。

    支持 sort_by：score=正向积分榜 / count=表扬次数榜；班级/年级/维度筛选。

    权限:
      - MS_ADMIN: 可查看全校
      - GRADE_LEADER: 可查看本年级
      - CLASS_TEACHER: 可查看本班级
      - STUDENT/PARENT: 可查看本班级/全校（仅查看，无操作）
    """
    # 权限控制：非 MS_ADMIN 只能查看自己管理的范围
    if current_user.role != UserRole.MS_ADMIN:
        if current_user.role == UserRole.GRADE_LEADER:
            # 级组长仅看本年级：取当前用户绑定的 grade_id（User.grade_id 同表列，必加载）
            if not grade_id:
                grade_id = current_user.grade_id
        elif current_user.role == UserRole.CLASS_TEACHER:
            # 班主任仅看本班：取当前用户绑定的 class_id（User.class_id 同表列，必加载）
            if not class_id:
                class_id = current_user.class_id

    ranking = await EvaluationService.get_positive_score_ranking(
        db=db,
        class_id=class_id,
        grade_id=grade_id,
        school_id=current_user.school_id,
        dimension=dimension,
        sort_by=sort_by,
        limit=limit,
        offset=offset,
    )

    return {
        "class_id": class_id,
        "grade_id": grade_id,
        "dimension": dimension,
        "total": len(ranking),  # TODO: 需要单独查询总数
        "ranking": ranking,
    }
