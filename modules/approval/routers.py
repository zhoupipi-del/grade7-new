"""
modules/approval/routers.py — 多租户动态审批链 API 端点

三层隔离:
  L1 数据层 — 所有查询强制 school_id
  L2 控制层 — get_current_user 依赖注入，从 JWT 提取 school_id
  L3 执行层 — 快照拷贝 (在 ApprovalRequest 创建时由调用方执行)

权限模型:
  - 查看: ms_admin, grade_leader, class_teacher
  - 管理: ms_admin only

路由结构 (前缀 /api/v1/approval):
  /chains              — 审批链模板 CRUD (ms_admin 管理)
  /pending-count       — 待审批计数
  /tickets             — 动态链工单视图 (todo/done)
  /tickets/{id}/urge   — 催办通知
  /requests            — 审批请求列表 (分页)
  /requests/{id}       — 审批详情
  /requests/{id}/approve — 批准当前节点
  /requests/{id}/reject  — 驳回当前节点
"""

import logging
from datetime import timedelta

from core.models import School, Student, User, UserRole
from core.routers import get_current_user, get_db
from fastapi import APIRouter, Depends, HTTPException, Query

# ApprovalRequest 定义在 evaluation/models.py 中
from modules.evaluation.models import ApprovalRequest
from sqlalchemy import and_, false, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from .schemas import (
    ApprovalRequestListResponse,
    ApprovalRequestResponse,
    ApprovalRuntimeNode,
    ApprovalTicketResponse,
    ApproveRequestInput,
    ChainActivateResponse,
    PendingCountResponse,
    RejectRequestInput,
    TenantApprovalChainCreate,
    TenantApprovalChainListResponse,
    TenantApprovalChainResponse,
    TenantApprovalChainUpdate,
    UrgeResponse,
)
from core.access import get_student_or_403, student_id_scope
from .services import ApprovalChainService, get_local_now, normalize_chain_config

logger = logging.getLogger(__name__)

router = APIRouter(tags=["approval"])


# ═══════════════════════════════════════════════════════════════
# 依赖: 角色校验
# ═══════════════════════════════════════════════════════════════


def _require_admin(user: User = Depends(get_current_user)):
    """仅 ms_admin 可管理审批链"""
    if user.role != UserRole.MS_ADMIN:
        raise HTTPException(status_code=403, detail="仅德育管理员可管理审批链配置")
    return user


def _require_staff(user: User = Depends(get_current_user)):
    """ms_admin / grade_leader / class_teacher 可操作审批"""
    allowed = {UserRole.MS_ADMIN, UserRole.GRADE_LEADER, UserRole.CLASS_TEACHER}
    if user.role not in allowed:
        raise HTTPException(status_code=403, detail="无审批操作权限")
    return user


# ═══════════════════════════════════════════════════════════════
# 节点指派角色 → 可调用 UserRole 集合（OPENING-APPROVAL-001 / A1）
# ═══════════════════════════════════════════════════════════════
# 说明: DEFAULT_CHAINS 的节点角色含 dean / principal / moral_education_staff,
# 而 UserRole 枚举无对应值（实际由 ms_admin 德育主任代行）。
# 此映射确保「非本节点指派人 → 403」且不卡死真实违纪链
# （behavior_major: 班主任→年级组长→德育处长; behavior_critical 再加校长）。
# R4-B（周主任拍板 Q1）: moral_education_staff 仅 ms_admin 代行，
# 不得下放 grade_leader，否则任意年级组长可代行德育处审批（扩大授权）。
NODE_ROLE_TO_USER_ROLES = {
    "class_teacher": {UserRole.CLASS_TEACHER},
    "grade_leader": {UserRole.GRADE_LEADER},
    "moral_education_staff": {UserRole.MS_ADMIN},
    "dean": {UserRole.MS_ADMIN},
    "principal": {UserRole.MS_ADMIN},
    "ms_admin": {UserRole.MS_ADMIN},
}
# 催办通知目标角色映射（未知节点角色默认通知 ms_admin）
URGE_TARGET_ROLE = {
    "class_teacher": UserRole.CLASS_TEACHER,
    "grade_leader": UserRole.GRADE_LEADER,
    "moral_education_staff": UserRole.MS_ADMIN,
    "dean": UserRole.MS_ADMIN,
    "principal": UserRole.MS_ADMIN,
    "ms_admin": UserRole.MS_ADMIN,
}


def _check_node_assignee(node: dict, user: User) -> None:
    """
    校验当前操作人是否为该审批节点的指派人；否则 403。

    - USER 型节点: 必须是指定的 user_id
    - ROLE 型节点: 用户角色必须落在节点角色的「可调用集合」内
      （见 NODE_ROLE_TO_USER_ROLES，保证 dean/principal 等由 ms_admin 代行）
    """
    if node.get("approver_type") == "USER":
        if str(node.get("approver_value")) != str(user.id):
            raise HTTPException(status_code=403, detail="当前节点非您审批，无权操作")
        return
    role = node.get("role") or "ms_admin"
    allowed = NODE_ROLE_TO_USER_ROLES.get(role, {UserRole.MS_ADMIN})
    if user.role not in allowed:
        raise HTTPException(
            status_code=403,
            detail=f"当前节点（{node.get('label', role)}）非您审批，无权操作",
        )


# ═══════════════════════════════════════════════════════════════
# 辅助函数: chain_config 快照 → 前端 ApprovalNode 映射
# ═══════════════════════════════════════════════════════════════


def _map_chain_nodes(
    chain_config: dict,
    current_step: int,
) -> list[ApprovalRuntimeNode]:
    """
    将后端 chain_config.nodes 转换为前端 ApprovalNode[] 格式。

    状态映射:
      approved  → approved
      rejected  → rejected
      denied    → rejected
      pending + node_index == current_step → pending
      pending + node_index != current_step → waiting
    """
    # 防御: 旧数据 chain_config 可能是 list 而非 dict，归一化为标准结构
    chain_config = normalize_chain_config(chain_config)
    nodes = chain_config.get("nodes", [])
    result = []

    for n in nodes:
        raw_status = n.get("status", "pending")
        node_index = n.get("node_index", 0)

        if raw_status in ("approved", "auto_approved"):
            frontend_status = "approved"
        elif raw_status in ("rejected", "denied"):
            frontend_status = "rejected"
        elif raw_status == "pending" and node_index == current_step:
            frontend_status = "pending"
        else:
            frontend_status = "waiting"

        approved_at = n.get("approved_at") or n.get("auto_approved_at")
        update_time = approved_at if approved_at else None

        result.append(
            ApprovalRuntimeNode(
                node_id=str(node_index),
                node_name=n.get("label", n.get("node_name", "审批节点")),
                assignee_role=n.get("role", ""),
                assignee_name=None,
                status=frontend_status,
                update_time=update_time,
            )
        )

    return result


def _build_ticket_title(event_type: str, student_name: str) -> str:
    """构建工单标题"""
    event_labels = {
        "fighting": "打架斗殴",
        "smoking": "吸烟违纪",
        "lateness": "迟到",
        "truancy": "旷课",
        "cheating": "考试作弊",
        "disrespect": "不尊重师长",
        "damage": "损坏公物",
        "theft": "盗窃",
        "ai_intervention": "AI干预处方",
    }
    label = event_labels.get(event_type, event_type)
    return f"{student_name} {label}审批"


def _calculate_deadline(created_at, chain_config: dict | list) -> str:
    """计算截止时间 = 创建时间 + 总超时小时数"""
    # 防御: 旧数据 chain_config 可能是 list 而非 dict
    chain_config = normalize_chain_config(chain_config)
    if not created_at:
        return ""
    total_hours = chain_config.get("total_timeout_hours", 48)
    deadline = created_at + timedelta(hours=total_hours)
    return deadline.isoformat()


# ═══════════════════════════════════════════════════════════════
# 1. 审批链模板 CRUD (/chains)
# ═══════════════════════════════════════════════════════════════


@router.get("/chains", response_model=TenantApprovalChainListResponse)
async def list_chains(
    business_type: str | None = Query(default=None, description="按业务类型筛选"),
    active_only: bool = Query(default=False, description="仅显示活跃链"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    user: User = Depends(_require_staff),
    db: AsyncSession = Depends(get_db),
):
    """列出当前学校的审批链（家长/学生 403）"""
    items, total = await ApprovalChainService.list_chains(
        db,
        school_id=user.school_id,
        business_type=business_type,
        active_only=active_only,
        offset=offset,
        limit=limit,
    )
    return TenantApprovalChainListResponse(
        items=[TenantApprovalChainResponse.model_validate(item) for item in items],
        total=total,
    )


@router.post("/chains", response_model=TenantApprovalChainResponse, status_code=201)
async def create_chain(
    data: TenantApprovalChainCreate,
    user: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """创建审批链模板（版本号自动递增）"""
    chain = await ApprovalChainService.create_chain(
        db,
        school_id=user.school_id,
        data=data,
        created_by=user.id,
    )
    return TenantApprovalChainResponse.model_validate(chain)


@router.get("/chains/{chain_id}", response_model=TenantApprovalChainResponse)
async def get_chain(
    chain_id: int,
    user: User = Depends(_require_staff),
    db: AsyncSession = Depends(get_db),
):
    """获取审批链详情（家长/学生 403）"""
    chain = await ApprovalChainService.get_chain(db, chain_id, user.school_id)
    if not chain:
        raise HTTPException(status_code=404, detail="审批链不存在")
    return TenantApprovalChainResponse.model_validate(chain)


@router.put("/chains/{chain_id}", response_model=TenantApprovalChainResponse)
async def update_chain(
    chain_id: int,
    data: TenantApprovalChainUpdate,
    user: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """更新审批链 — 节点变更自动创建新版本"""
    chain = await ApprovalChainService.update_chain(db, chain_id, user.school_id, data)
    if not chain:
        raise HTTPException(status_code=404, detail="审批链不存在")
    return TenantApprovalChainResponse.model_validate(chain)


@router.post("/chains/{chain_id}/activate", response_model=ChainActivateResponse)
async def activate_chain(
    chain_id: int,
    user: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """激活审批链 — 停用同业务类型的其他版本"""
    chain, prev_id = await ApprovalChainService.activate_chain(db, chain_id, user.school_id)
    if not chain:
        raise HTTPException(status_code=404, detail="审批链不存在")
    return ChainActivateResponse(
        message=f"审批链 #{chain.id} ({chain.chain_name}) 已激活",
        chain_id=chain.id,
        previous_active_id=prev_id,
    )


@router.delete("/chains/{chain_id}", status_code=200)
async def deactivate_chain(
    chain_id: int,
    user: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """停用审批链（软删除）"""
    ok = await ApprovalChainService.delete_chain(db, chain_id, user.school_id)
    if not ok:
        raise HTTPException(status_code=404, detail="审批链不存在")
    return {"message": f"审批链 #{chain_id} 已停用"}


# ═══════════════════════════════════════════════════════════════
# 2. 待审批计数 (/pending-count)
# ═══════════════════════════════════════════════════════════════


@router.get("/pending-count", response_model=PendingCountResponse)
async def get_pending_count(
    user: User = Depends(_require_staff),
    db: AsyncSession = Depends(get_db),
):
    """获取当前用户可见范围内的待审批工单数量（家长/学生 403）"""
    conditions = [
        ApprovalRequest.school_id == user.school_id,
        ApprovalRequest.current_status == "pending",
    ]
    # 行级范围收敛: None=本校全部 / []=零可见 / [..]=白名单
    scope = await student_id_scope(db, user)
    if scope is not None:
        conditions.append(
            ApprovalRequest.student_id.in_(scope) if scope else false()
        )
    result = await db.execute(
        select(func.count(ApprovalRequest.id)).where(and_(*conditions))
    )
    count = result.scalar() or 0
    return PendingCountResponse(pending=count)


# ═══════════════════════════════════════════════════════════════
# 3. 动态链工单视图 (/tickets)
# ═══════════════════════════════════════════════════════════════


@router.get("/tickets", response_model=list[ApprovalTicketResponse])
async def get_tickets(
    type: str = Query(default="todo", description="todo=待审批, done=已完成"),
    user: User = Depends(_require_staff),
    db: AsyncSession = Depends(get_db),
):
    """
    获取审批工单列表（动态链视图）。

    前端 ApprovalTicket 契约:
      ticket_id, title, applicant_name, tenant_school,
      created_at, deadline_at, current_node_index, chain_config[]
    """
    if type not in ("todo", "done"):
        raise HTTPException(status_code=400, detail="type 参数必须是 todo 或 done")

    # 构建查询条件
    conditions = [ApprovalRequest.school_id == user.school_id]
    # 行级范围收敛: None=本校全部 / []=零可见 / [..]=白名单
    scope = await student_id_scope(db, user)
    if scope is not None:
        conditions.append(
            ApprovalRequest.student_id.in_(scope) if scope else false()
        )
    if type == "todo":
        conditions.append(ApprovalRequest.current_status == "pending")
    else:
        conditions.append(
            ApprovalRequest.current_status.in_(
                ["approved", "rejected", "timeout", "denied", "cancelled"]
            )
        )

    # 查询工单 + 学生名 + 学校名
    result = await db.execute(
        select(ApprovalRequest, Student.name, School.name)
        .outerjoin(Student, ApprovalRequest.student_id == Student.id)
        .outerjoin(School, ApprovalRequest.school_id == School.id)
        .where(and_(*conditions))
        .order_by(ApprovalRequest.created_at.desc())
        .limit(100)
    )
    rows = result.all()

    tickets = []
    for ar, student_name, school_name in rows:
        # 防御: 旧数据 chain_config 可能是 list 而非 dict
        chain = normalize_chain_config(ar.chain_config)
        nodes = _map_chain_nodes(chain, ar.current_step or 0)
        title = _build_ticket_title(ar.event_type, student_name or "未知学生")

        tickets.append(
            ApprovalTicketResponse(
                ticket_id=str(ar.id),
                title=title,
                applicant_name="系统提交",
                tenant_school=school_name or "本校",
                created_at=ar.created_at.isoformat() if ar.created_at else "",
                deadline_at=_calculate_deadline(ar.created_at, chain),
                current_node_index=ar.current_step or 0,
                chain_config=nodes,
            )
        )

    return tickets


@router.post("/tickets/{ticket_id}/urge", response_model=UrgeResponse)
async def urge_ticket_node(
    ticket_id: str,
    node_id: str = Query(..., description="要催办的节点 ID"),
    user: User = Depends(_require_staff),
    db: AsyncSession = Depends(get_db),
):
    """催办当前审批节点（发送通知给审批人）"""
    # 查找工单
    try:
        req_id = int(ticket_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的工单 ID")

    result = await db.execute(
        select(ApprovalRequest).where(
            ApprovalRequest.id == req_id,
            ApprovalRequest.school_id == user.school_id,
        )
    )
    ar = result.scalar_one_or_none()
    if not ar:
        raise HTTPException(status_code=404, detail="审批工单不存在")
    if ar.current_status != "pending":
        raise HTTPException(status_code=400, detail="该工单已处理，无需催办")

    # 解析当前待审节点
    chain = normalize_chain_config(ar.chain_config)
    nodes = chain.get("nodes", [])
    current_step = ar.current_step or 0
    node = nodes[current_step] if current_step < len(nodes) else {}
    target_role = URGE_TARGET_ROLE.get(node.get("role"), UserRole.MS_ADMIN)

    # 站内催办（真实落地）：向当前节点的指派角色发送站内通知
    # 外部消息通道（钉钉/企业微信）开学后接入，此处不谎称已发送
    try:
        from modules.notifications.services import NotificationService
        node_label = node.get("label") or node.get("role") or "审批"
        await NotificationService.notify_by_role(
            db,
            school_id=ar.school_id,
            role=target_role,
            type="approval_urge",
            title=f"审批催办 — {ar.event_type or '待办工单'}",
            body=f"工单 #{ar.id} 的「{node_label}」节点待您审批，请尽快处理。",
            sender_id=user.id,
            entity_type="approval_request",
            entity_id=ar.id,
        )
        await db.commit()
    except Exception as exc:
        logger.warning("[URGE] 站内通知发送失败 (不影响催办记录): %s", exc)

    return UrgeResponse(
        message="催办已发送站内提醒（外部消息通道暂未启用）",
        ticket_id=ticket_id,
        node_id=node_id,
    )


# ═══════════════════════════════════════════════════════════════
# 4. 审批请求 CRUD (/requests)
# ═══════════════════════════════════════════════════════════════


@router.get("/requests", response_model=ApprovalRequestListResponse)
async def list_requests(
    status: str | None = Query(default=None, description="按状态筛选"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(_require_staff),
    db: AsyncSession = Depends(get_db),
):
    """分页查询审批请求列表（家长/学生 403；按角色收敛到本年级/本班）"""
    conditions = [ApprovalRequest.school_id == user.school_id]
    # 行级范围收敛: None=本校全部 / []=零可见 / [..]=白名单
    scope = await student_id_scope(db, user)
    if scope is not None:
        conditions.append(
            ApprovalRequest.student_id.in_(scope) if scope else false()
        )
    if status:
        conditions.append(ApprovalRequest.current_status == status)

    # 计数
    count_result = await db.execute(
        select(func.count()).select_from(ApprovalRequest).where(and_(*conditions))
    )
    total = count_result.scalar() or 0

    # 列表
    offset = (page - 1) * page_size
    result = await db.execute(
        select(ApprovalRequest)
        .where(and_(*conditions))
        .order_by(ApprovalRequest.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    items = list(result.scalars().all())

    return ApprovalRequestListResponse(
        items=[
            ApprovalRequestResponse(
                id=ar.id,
                student_id=ar.student_id,
                event_type=ar.event_type,
                source_type=ar.source_type,
                source_id=ar.source_id,
                severity=ar.severity,
                approval_mode=ar.approval_mode,
                chain_config=normalize_chain_config(ar.chain_config),
                current_status=ar.current_status,
                current_step=ar.current_step or 0,
                created_at=ar.created_at,
                updated_at=ar.updated_at,
                completed_at=ar.completed_at,
            )
            for ar in items
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/requests/{req_id}", response_model=ApprovalRequestResponse)
async def get_request(
    req_id: int,
    user: User = Depends(_require_staff),
    db: AsyncSession = Depends(get_db),
):
    """获取单个审批请求详情（家长/学生 403；非管辖学生 403）"""
    result = await db.execute(
        select(ApprovalRequest).where(
            ApprovalRequest.id == req_id,
            ApprovalRequest.school_id == user.school_id,
        )
    )
    ar = result.scalar_one_or_none()
    # 行级归属校验: 非本人管辖的学生工单一律 403
    if ar is not None:
        await get_student_or_403(db, user, ar.student_id)
    if not ar:
        raise HTTPException(status_code=404, detail="审批请求不存在")

    return ApprovalRequestResponse(
        id=ar.id,
        student_id=ar.student_id,
        event_type=ar.event_type,
        source_type=ar.source_type,
        source_id=ar.source_id,
        severity=ar.severity,
        approval_mode=ar.approval_mode,
        chain_config=normalize_chain_config(ar.chain_config),
        current_status=ar.current_status,
        current_step=ar.current_step or 0,
        created_at=ar.created_at,
        updated_at=ar.updated_at,
        completed_at=ar.completed_at,
    )


@router.post("/requests/{req_id}/approve")
async def approve_request(
    req_id: int,
    data: ApproveRequestInput,
    user: User = Depends(_require_staff),
    db: AsyncSession = Depends(get_db),
):
    """
    批准当前审批节点。

    serial_and: 当前节点通过 → 推进到下一节点；全部通过 → 工单完成
    parallel_or: 当前节点通过；全部通过 → 工单完成
    """
    result = await db.execute(
        select(ApprovalRequest).where(
            ApprovalRequest.id == req_id,
            ApprovalRequest.school_id == user.school_id,
        )
    )
    ar = result.scalar_one_or_none()
    if not ar:
        raise HTTPException(status_code=404, detail="审批请求不存在")
    if ar.current_status != "pending":
        raise HTTPException(status_code=400, detail="该审批已处理，不可重复操作")

    # R4-A (APPROVAL-AUTH-001): 资源范围校验 —— 仅能审批自己责任范围内的学生工单。
    # ms_admin 为 school-wide（scope=None 放行）；年级组长限本年级、班主任限本班。
    # 与 _check_node_assignee（角色资格）共同构成「角色资格 + 资源范围」双闸，
    # 彻底消除「2501班主任批2502班 / A年级组长批B年级」类越权。
    scope = await student_id_scope(db, user)
    if scope is not None and ar.student_id not in scope:
        raise HTTPException(
            status_code=403,
            detail="无该学生审批权限（超出您的责任范围）",
        )

    # 归一化 + 自愈: 历史裸 list 快照在首次审批动作时被规整为标准 dict 并落库
    chain = normalize_chain_config(ar.chain_config)
    if chain is not ar.chain_config:
        ar.chain_config = chain
    nodes = chain.get("nodes", [])
    now = get_local_now()

    if not nodes:
        raise HTTPException(status_code=500, detail="审批链配置异常：无节点")

    current_step = ar.current_step or 0
    if current_step >= len(nodes):
        raise HTTPException(status_code=400, detail="无待审批节点")

    # 更新当前节点
    node = nodes[current_step]
    _check_node_assignee(node, user)
    node["status"] = "approved"
    node["approver_id"] = user.id
    node["approved_at"] = now.isoformat()
    if data.comment:
        node["comment"] = data.comment

    # 标记 JSON 字段为已修改
    flag_modified(ar, "chain_config")

    approval_mode = chain.get("approval_mode") or ar.approval_mode or "serial_and"

    if approval_mode == "serial_and":
        # 串行：推进到下一节点
        ar.current_step = current_step + 1
        if ar.current_step >= len(nodes):
            ar.current_status = "approved"
            ar.completed_at = now
            logger.info("[APPROVE] 工单 #%s 全部通过 (serial_and)", req_id)
        else:
            logger.info(
                "[APPROVE] 工单 #%s 节点 %s 通过 → 推进到 %s",
                req_id,
                current_step,
                ar.current_step,
            )
    else:
        # 并行：检查是否全部通过
        all_approved = all(n.get("status") in ("approved", "auto_approved") for n in nodes)
        if all_approved:
            ar.current_status = "approved"
            ar.completed_at = now
            logger.info("[APPROVE] 工单 #%s 全部通过 (parallel_or)", req_id)
        else:
            logger.info("[APPROVE] 工单 #%s 节点 %s 通过 (parallel_or)", req_id, current_step)

    ar.updated_at = now
    await db.commit()

    return {
        "message": "审批已通过",
        "request_id": req_id,
        "current_status": ar.current_status,
        "current_step": ar.current_step,
    }


@router.post("/requests/{req_id}/reject")
async def reject_request(
    req_id: int,
    data: RejectRequestInput,
    user: User = Depends(_require_staff),
    db: AsyncSession = Depends(get_db),
):
    """
    驳回当前审批节点 — 工单立即终止为 rejected。
    """
    result = await db.execute(
        select(ApprovalRequest).where(
            ApprovalRequest.id == req_id,
            ApprovalRequest.school_id == user.school_id,
        )
    )
    ar = result.scalar_one_or_none()
    if not ar:
        raise HTTPException(status_code=404, detail="审批请求不存在")
    if ar.current_status != "pending":
        raise HTTPException(status_code=400, detail="该审批已处理，不可重复操作")

    # R4-A (APPROVAL-AUTH-001): 资源范围校验 —— 仅能驳回自己责任范围内的学生工单。
    # ms_admin 为 school-wide（scope=None 放行）；年级组长限本年级、班主任限本班。
    scope = await student_id_scope(db, user)
    if scope is not None and ar.student_id not in scope:
        raise HTTPException(
            status_code=403,
            detail="无该学生审批权限（超出您的责任范围）",
        )

    # 归一化 + 自愈: 历史裸 list 快照在首次审批动作时被规整为标准 dict 并落库
    chain = normalize_chain_config(ar.chain_config)
    if chain is not ar.chain_config:
        ar.chain_config = chain
    nodes = chain.get("nodes", [])
    now = get_local_now()

    if not nodes:
        raise HTTPException(status_code=500, detail="审批链配置异常：无节点")

    current_step = ar.current_step or 0
    if current_step >= len(nodes):
        raise HTTPException(status_code=400, detail="无待审批节点")

    # 更新当前节点为 rejected
    node = nodes[current_step]
    _check_node_assignee(node, user)
    node["status"] = "rejected"
    node["approver_id"] = user.id
    node["rejected_at"] = now.isoformat()
    node["comment"] = data.comment

    # 标记 JSON 字段为已修改
    flag_modified(ar, "chain_config")

    # 驳回 → 工单终止
    ar.current_status = "rejected"
    ar.completed_at = now
    ar.updated_at = now

    logger.info(
        "[REJECT] 工单 #%s 被驳回 | node=%s user=%s comment=%s",
        req_id,
        current_step,
        user.id,
        data.comment[:100],
    )

    await db.commit()

    return {
        "message": "审批已驳回",
        "request_id": req_id,
        "current_status": ar.current_status,
    }
