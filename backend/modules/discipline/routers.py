"""
modules/discipline/routers.py — 处分管理 API (二级审批流)

端点:
  POST   /api/v1/discipline/sanctions              创建处分（班主任提报）
  GET    /api/v1/discipline/sanctions              分页查询处分列表
  GET    /api/v1/discipline/sanctions/{id}         查看单条处分详情
  PUT    /api/v1/discipline/sanctions/{id}         编辑处分（仅 DRAFT_PENDING/PENDING）
  DELETE /api/v1/discipline/sanctions/{id}         删除处分（仅 MS_ADMIN）
  POST   /api/v1/discipline/sanctions/{id}/approve 审批通过（年级组长初审 / 德育处终审）
  POST   /api/v1/discipline/sanctions/{id}/reject  审批驳回（任一阶段均可驳回）
  POST   /api/v1/discipline/sanctions/{id}/revoke  撤销处分（ACTIVE→REVOKED）
  GET    /api/v1/discipline/stats                  处分统计概览
  GET    /api/v1/discipline/escalation/{student_id} 违纪一键升级评估
  POST   /api/v1/discipline/escalation/{student_id} 违纪一键升级执行

Phase 4 — 家校申诉:
  POST   /api/v1/discipline/webhooks/appeal         Webhook 接收外部申诉（需 X-Webhook-Secret 头）
  GET    /api/v1/discipline/appeals                 申诉列表
  GET    /api/v1/discipline/appeals/{id}            申诉详情
  POST   /api/v1/discipline/appeals/{id}/review     复核申诉（ACCEPTED/REJECTED）
"""

import os
from typing import Optional
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from core.models import User, UserRole
from core.routers import get_db, get_current_user, require_role
from .services import DisciplineService, STATUS_LABELS
from .models import (
    DisciplineLevel, DisciplineStatus, LEVEL_LABELS, LEVEL_PENALTY_MAP, VETO_LEVELS,
    AppealStatus, APPEAL_STATUS_LABELS,
)
from .schemas import (
    SanctionCreate, SanctionUpdate, SanctionOut,
    SanctionReview, SanctionRevoke, SanctionStatsOut,
    DraftSubmit,
    AppealWebhookCreate, AppealReview, AppealOut,
)

router = APIRouter(tags=["discipline"])


# ═══════════════════════════════════════════════════════════════
# CRUD
# ═══════════════════════════════════════════════════════════════

@router.post("/sanctions", status_code=201)
async def create_sanction(
    body: SanctionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _guard: User = Depends(require_role(
        UserRole.MS_ADMIN, UserRole.GRADE_LEADER, UserRole.CLASS_TEACHER,
    )),
):
    """班主任提报处分 → PENDING 状态"""
    try:
        sanction = await DisciplineService.create_sanction(
            db, current_user.school_id,
            body.model_dump(), current_user.id,
        )
        return _format(sanction)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/sanctions")
async def list_sanctions(
    class_id: Optional[int] = None,
    grade_id: Optional[int] = None,
    student_id: Optional[int] = None,
    level: Optional[str] = None,
    status: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """分页查询处分列表"""
    offset = (page - 1) * per_page
    records, total = await DisciplineService.list_sanctions(
        db, current_user.school_id,
        class_id=class_id, grade_id=grade_id, student_id=student_id,
        level=level, status=status,
        start_date=start_date, end_date=end_date,
        limit=per_page, offset=offset,
    )
    pages = (total + per_page - 1) // per_page if total > 0 else 0
    return {
        "items": [_format(r) for r in records],
        "total": total, "page": page, "per_page": per_page,
        "pages": pages,
    }


@router.get("/sanctions/{sanction_id}")
async def get_sanction(
    sanction_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """查看单条处分详情"""
    sanction = await DisciplineService.get_sanction(db, sanction_id)
    if not sanction:
        raise HTTPException(status_code=404, detail="处分记录不存在")
    return _format(sanction)


@router.put("/sanctions/{sanction_id}")
async def update_sanction(
    sanction_id: int,
    body: SanctionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """编辑处分 — 仅 PENDING 状态可编辑"""
    try:
        sanction = await DisciplineService.update_sanction(
            db, sanction_id, body.model_dump(exclude_none=True),
        )
        if not sanction:
            raise HTTPException(status_code=404, detail="处分记录不存在")
        return _format(sanction)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/sanctions/{sanction_id}")
async def delete_sanction(
    sanction_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _guard: User = Depends(require_role(UserRole.MS_ADMIN)),
):
    """删除处分 — 仅 PENDING 状态可删除，仅德育处管理员"""
    try:
        ok = await DisciplineService.delete_sanction(db, sanction_id)
        if not ok:
            raise HTTPException(status_code=404, detail="处分记录不存在")
        return {"message": "已删除"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ═══════════════════════════════════════════════════════════════
# 状态机: 审批
# ═══════════════════════════════════════════════════════════════

@router.post("/sanctions/{sanction_id}/approve")
async def approve_sanction(
    sanction_id: int,
    body: SanctionReview,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _guard: User = Depends(require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER)),
):
    """
    行政审批通过 — 角色感知二级审批流

    年级组长 (GRADE_LEADER):
      PENDING → GRADE_LEADER_APPROVED (初审通过，待德育处终审)

    德育处 (MS_ADMIN):
      GRADE_LEADER_APPROVED → ACTIVE (终审通过，处分生效，触发扣分/一票否决)

    角色守卫: 当前用户角色决定执行哪一级审批，不可越级操作。
    """
    try:
        # 角色守卫 — 确定当前用户属于哪一级审批人
        reviewer_role = _resolve_reviewer_role(current_user)

        sanction = await DisciplineService.approve_sanction(
            db, sanction_id,
            comment=body.comment or "",
            reviewer_id=current_user.id,
            reviewer_role=reviewer_role,
        )
        if not sanction:
            raise HTTPException(status_code=404, detail="处分记录不存在")
        return _format(sanction)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/sanctions/{sanction_id}/reject")
async def reject_sanction(
    sanction_id: int,
    body: SanctionReview,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _guard: User = Depends(require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER)),
):
    """
    行政审批驳回 — 任意阶段均可驳回

    年级组长 (GRADE_LEADER):
      PENDING → REJECTED (初审驳回)

    德育处 (MS_ADMIN):
      GRADE_LEADER_APPROVED → REJECTED (终审驳回)

    驳回后处分归档留痕，不可重新审批。
    """
    try:
        reviewer_role = _resolve_reviewer_role(current_user)

        sanction = await DisciplineService.reject_sanction(
            db, sanction_id,
            comment=body.comment or "",
            reviewer_id=current_user.id,
            reviewer_role=reviewer_role,
        )
        if not sanction:
            raise HTTPException(status_code=404, detail="处分记录不存在")
        return _format(sanction)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ═══════════════════════════════════════════════════════════════
# 状态机: 撤销
# ═══════════════════════════════════════════════════════════════

@router.post("/sanctions/{sanction_id}/revoke")
async def revoke_sanction(
    sanction_id: int,
    body: SanctionRevoke,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _guard: User = Depends(require_role(UserRole.MS_ADMIN)),
):
    """
    撤销处分 — ACTIVE → REVOKED

    仅德育处管理员可操作。
    撤销后:
      - 处分历史永久保留
      - 扣分不回溯（历史分值保留）
      - 一票否决标记解除（如果唯一定罪处分）
      - 学期报告展示"已撤销"的正面修正
    """
    try:
        sanction = await DisciplineService.revoke_sanction(
            db, sanction_id,
            revoke_reason=body.revoke_reason,
            revoke_date=body.revoke_date,
        )
        if not sanction:
            raise HTTPException(status_code=404, detail="处分记录不存在")
        return _format(sanction)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ═══════════════════════════════════════════════════════════════
# 违纪一键升级
# ═══════════════════════════════════════════════════════════════

@router.get("/escalation/{student_id}")
async def check_escalation(
    student_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """评估学生是否需要从违纪升级为处分"""
    return await DisciplineService.check_escalation(db, student_id)


@router.post("/escalation/{student_id}", status_code=201)
async def escalate_to_sanction(
    student_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _guard: User = Depends(require_role(
        UserRole.MS_ADMIN, UserRole.GRADE_LEADER, UserRole.CLASS_TEACHER,
    )),
):
    """
    违纪一键升级为处分 — 自动创建 PENDING 处分草案

    系统自动:
      1. 汇总该学生所有活跃违纪扣分
      2. 按阈值建议处分等级
      3. 关联扣分最大的违纪记录作为溯源
      4. 创建 PENDING 处分 → 等待德育处审批
    """
    try:
        sanction = await DisciplineService.escalate_to_sanction(
            db, student_id, current_user.id,
        )
        return _format(sanction)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ═══════════════════════════════════════════════════════════════
# 统计
# ═══════════════════════════════════════════════════════════════

@router.get("/stats")
async def sanction_stats(
    grade_id: Optional[int] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """处分统计概览"""
    return await DisciplineService.get_stats(
        db, current_user.school_id,
        grade_id=grade_id,
        start_date=start_date, end_date=end_date,
    )


# ═══════════════════════════════════════════════════════════════
# Phase 2: 草稿箱管理 — 30天滑窗自动化引擎
# ═══════════════════════════════════════════════════════════════

@router.get("/drafts")
async def list_drafts(
    class_id: Optional[int] = None,
    grade_id: Optional[int] = None,
    student_id: Optional[int] = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    草稿列表 — DRAFT_PENDING 状态

    自动按角色过滤:
      - 班主任: 只看自己班级
      - 年级组长: 看全年级
      - 德育处: 看全校
    """
    # 角色自动过滤: 班主任只看自己班级
    _cid = class_id
    if current_user.role == UserRole.CLASS_TEACHER:
        _cid = _cid or current_user.class_id

    offset = (page - 1) * per_page
    records, total = await DisciplineService.list_drafts(
        db, current_user.school_id,
        class_id=_cid, grade_id=grade_id, student_id=student_id,
        limit=per_page, offset=offset,
    )
    pages = (total + per_page - 1) // per_page if total > 0 else 0

    # 格式化输出（JSON 列自动反序列化，直接取用）
    items = []
    for r in records:
        item = _format(r)
        item["evidence"] = r.evidence_snapshot or None  # JSON 列已自动反序列化
        items.append(item)

    return {
        "items": items,
        "total": total, "page": page, "per_page": per_page,
        "pages": pages,
    }


@router.get("/drafts/{draft_id}")
async def get_draft(
    draft_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """草稿详情 — 含铁证快照解析"""
    draft = await DisciplineService.get_sanction(db, draft_id)
    if not draft or draft.status != DisciplineStatus.DRAFT_PENDING:
        raise HTTPException(status_code=404, detail="处分草稿不存在或已不是草稿状态")

    result = _format(draft)
    result["evidence"] = draft.evidence_snapshot or None  # JSON 列已自动反序列化
    return result


@router.post("/drafts/{draft_id}/submit")
async def submit_draft(
    draft_id: int,
    body: DraftSubmit,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _guard: User = Depends(require_role(
        UserRole.CLASS_TEACHER, UserRole.MS_ADMIN, UserRole.GRADE_LEADER,
    )),
):
    """
    班主任一键提交草稿: DRAFT_PENDING → PENDING

    草稿瞬间转为正式 PENDING 状态，进入德育处行政审批流。
    班主任可附加补充意见（confirm_reason）。
    """
    try:
        sanction = await DisciplineService.submit_draft(
            db, draft_id,
            confirm_reason=body.confirm_reason,
            submitter_id=current_user.id,
        )
        if not sanction:
            raise HTTPException(status_code=404, detail="处分草稿不存在")
        return _format(sanction)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/drafts/{draft_id}")
async def discard_draft(
    draft_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _guard: User = Depends(require_role(UserRole.MS_ADMIN, UserRole.CLASS_TEACHER)),
):
    """废弃草稿 — 物理删除 DRAFT_PENDING 记录"""
    try:
        ok = await DisciplineService.discard_draft(db, draft_id)
        if not ok:
            raise HTTPException(status_code=404, detail="处分草稿不存在")
        return {"message": "草稿已废弃"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/escalation-trigger/{student_id}")
async def check_escalation_trigger(
    student_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    滑窗判定检查 — 查看学生是否触发30天/3次严重违纪红线

    返回:
      - triggered: 是否触发升级
      - evidence: 铁证快照
      - blocked_reason: 未触发原因
    """
    return await DisciplineService.detect_escalation_trigger(db, student_id)


# ═══════════════════════════════════════════════════════════════
# Phase 4: 家校申诉 Webhook + 申诉管理 API
# ═══════════════════════════════════════════════════════════════

# Webhook Secret — 从环境变量读取，默认值仅用于开发
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "change-me-in-production")


@router.post("/webhooks/appeal", status_code=201)
async def webhook_create_appeal(
    body: AppealWebhookCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Webhook 端点 — 接收外部系统（微信小程序）POST 的申诉请求

    安全校验:
      - X-Webhook-Secret 头校验
      - idempotency_key 幂等防重
      - 仅 ACTIVE 状态处分可申诉

    示例请求:
      POST /api/v1/discipline/webhooks/appeal
      Headers: X-Webhook-Secret: <shared-secret>
      Body: {
        "idempotency_key": "wx_appeal_20260623_001",
        "sanction_id": 42,
        "applicant_name": "张三家长",
        "applicant_phone": "13800138000",
        "reason": "孩子当时是被冤枉的，有证人可以证明"
      }
    """
    # ── X-Webhook-Secret 校验 ──
    webhook_secret = request.headers.get("X-Webhook-Secret", "")
    if not webhook_secret or webhook_secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="无效的 Webhook Secret")

    # ── 根据 school_id 查询──
    # Webhook 场景无登录态，需要从处分记录反查 school_id
    from .models import DisciplineSanction as DS
    sanction = await db.scalar(
        select(DS).where(DS.id == body.sanction_id)
    )
    if not sanction:
        raise HTTPException(status_code=404, detail=f"处分记录不存在: id={body.sanction_id}")
    school_id = sanction.school_id

    try:
        result = await DisciplineService.create_appeal_from_webhook(
            db, school_id, body.model_dump(),
        )
        appeal = result["appeal"]
        created = result["created"]
        return {
            "appeal": _format_appeal(appeal),
            "created": created,
        }
    except ValueError as e:
        # 幂等返回不算错误，仍返回已有记录
        raise HTTPException(status_code=409 if "已存在" in str(e) else 400, detail=str(e))


@router.get("/appeals")
async def list_appeals(
    sanction_id: Optional[int] = None,
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _guard: User = Depends(require_role(
        UserRole.MS_ADMIN, UserRole.GRADE_LEADER, UserRole.CLASS_TEACHER,
    )),
):
    """分页查询申诉列表 — 德育处/年级组长/班主任"""
    offset = (page - 1) * per_page
    records, total = await DisciplineService.list_appeals(
        db, current_user.school_id,
        sanction_id=sanction_id, status=status,
        limit=per_page, offset=offset,
    )
    pages = (total + per_page - 1) // per_page if total > 0 else 0
    return {
        "items": [_format_appeal(r) for r in records],
        "total": total, "page": page, "per_page": per_page,
        "pages": pages,
    }


@router.get("/appeals/{appeal_id}")
async def get_appeal(
    appeal_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """查看单条申诉详情"""
    appeal = await DisciplineService.get_appeal(db, appeal_id)
    if not appeal:
        raise HTTPException(status_code=404, detail="申诉记录不存在")
    return _format_appeal(appeal)


@router.post("/appeals/{appeal_id}/review")
async def review_appeal(
    appeal_id: int,
    body: AppealReview,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _guard: User = Depends(require_role(UserRole.MS_ADMIN)),
):
    """
    德育处复核申诉 — 仅 MS_ADMIN 可操作

    ACCEPTED (申诉通过):
      申诉状态 → ACCEPTED + 自动撤销原处分 ACTIVE → REVOKED

    REJECTED (申诉驳回):
      申诉状态 → REJECTED，原处分不受影响
    """
    try:
        result = await DisciplineService.review_appeal(
            db, appeal_id,
            action=body.action,
            reviewer_id=current_user.id,
            comment=body.comment,
        )
        return {
            "appeal": _format_appeal(result["appeal"]),
            "sanction_id": result["sanction"].id if result["sanction"] else None,
            "sanction_status": (
                result["sanction"].status.value
                if result["sanction"] and hasattr(result["sanction"].status, "value")
                else None
            ),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ═══════════════════════════════════════════════════════════════
# 格式化辅助
# ═══════════════════════════════════════════════════════════════

def _resolve_reviewer_role(user: User) -> str:
    """
    角色映射: UserRole → 审批流角色标识

    二级审批链中:
      - GRADE_LEADER → "grade_leader" (初审)
      - MS_ADMIN     → "ms_admin"     (终审)

    若用户同时拥有两个角色（极少见），以 higher authority (MS_ADMIN) 为准。
    """
    if user.role == UserRole.MS_ADMIN:
        return "ms_admin"
    elif user.role == UserRole.GRADE_LEADER:
        return "grade_leader"
    else:
        raise ValueError(f"当前用户角色 {user.role.value} 无权执行审批操作")


def _format(s) -> dict:
    """安全格式化处分记录 → JSON"""
    # 安全获取关系字段
    try:
        student_name = s.student.name if s.student else None
        student_no = s.student.student_no if s.student else None
        class_name = (s.class_.name if s.class_ else
                      s.student.class_.name if s.student and getattr(s.student, 'class_', None) else None)
        grade_name = s.grade.name if s.grade else None
        creator_name = s.creator.display_name if s.creator else None
        approver_name = s.approver.display_name if s.approver else None
        grade_leader_name = s.grade_leader.display_name if s.grade_leader else None
    except Exception:
        student_name = student_no = class_name = grade_name = creator_name = approver_name = grade_leader_name = None

    # 等级标签
    try:
        level_label = LEVEL_LABELS.get(s.level, s.level.value)
    except Exception:
        level_label = str(s.level)

    # 状态标签
    try:
        status_label = STATUS_LABELS.get(s.status.value, s.status.value)
    except Exception:
        status_label = str(s.status)

    # 评价影响
    try:
        penalty = LEVEL_PENALTY_MAP.get(s.level)
        is_veto = s.level in VETO_LEVELS
    except Exception:
        penalty = None
        is_veto = False

    return {
        "id": s.id,
        "school_id": s.school_id,
        "student_id": s.student_id,
        "student_name": student_name,
        "student_no": student_no,
        "class_id": s.class_id,
        "class_name": class_name,
        "grade_id": s.grade_id,
        "grade_name": grade_name,
        "behavior_record_id": s.behavior_record_id,
        "level": s.level.value if hasattr(s.level, 'value') else str(s.level),
        "level_label": level_label,
        "status": s.status.value if hasattr(s.status, 'value') else str(s.status),
        "status_label": status_label,
        "reason": s.reason,
        "document_no": s.document_no,
        "punish_date": s.punish_date.isoformat() if s.punish_date else None,
        "revoke_date": s.revoke_date.isoformat() if s.revoke_date else None,
        "revoke_reason": s.revoke_reason,
        "creator_id": s.creator_id,
        "creator_name": creator_name,
        "approver_id": s.approver_id,
        "approver_name": approver_name,
        "grade_leader_id": s.grade_leader_id,
        "grade_leader_name": grade_leader_name,
        "grade_leader_comment": s.grade_leader_comment,
        "grade_leader_reviewed_at": s.grade_leader_reviewed_at.isoformat() if s.grade_leader_reviewed_at else None,
        "approver_comment": s.approver_comment,
        "penalty_points": penalty,
        "is_veto": is_veto,
        "evidence_snapshot": s.evidence_snapshot,
        "auto_generated": s.auto_generated,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }


def _format_appeal(a) -> dict:
    """安全格式化申诉记录 → JSON"""
    from .models import SanctionAppeal, APPEAL_STATUS_LABELS, LEVEL_LABELS as LL

    # 安全获取关联处分信息
    sanction = a.sanction if hasattr(a, 'sanction') and a.sanction else None
    try:
        sanction_level = sanction.level.value if sanction and hasattr(sanction.level, 'value') else None
        sanction_level_label = LL.get(sanction.level) if sanction else None
        sanction_reason = sanction.reason if sanction else None
        sanction_status = sanction.status.value if sanction and hasattr(sanction.status, 'value') else None
        student_id = sanction.student_id if sanction else None
        student_name = sanction.student.name if sanction and sanction.student else None
    except Exception:
        sanction_level = sanction_level_label = sanction_reason = sanction_status = student_id = student_name = None

    # 状态标签
    try:
        status_label = APPEAL_STATUS_LABELS.get(a.status, a.status.value)
    except Exception:
        status_label = str(a.status)

    # 复核人
    reviewer_name = a.reviewer.display_name if hasattr(a, 'reviewer') and a.reviewer else None

    return {
        "id": a.id,
        "school_id": a.school_id,
        "sanction_id": a.sanction_id,
        "sanction_level": sanction_level,
        "sanction_level_label": sanction_level_label,
        "sanction_reason": sanction_reason,
        "sanction_status": sanction_status,
        "student_id": student_id,
        "student_name": student_name,
        "applicant_name": a.applicant_name,
        "applicant_phone": a.applicant_phone,
        "reason": a.reason,
        "idempotency_key": a.idempotency_key,
        "status": a.status.value if hasattr(a.status, 'value') else str(a.status),
        "status_label": status_label,
        "reviewer_id": a.reviewer_id,
        "reviewer_name": reviewer_name,
        "review_comment": a.review_comment,
        "reviewed_at": a.reviewed_at.isoformat() if a.reviewed_at else None,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "updated_at": a.updated_at.isoformat() if a.updated_at else None,
    }
