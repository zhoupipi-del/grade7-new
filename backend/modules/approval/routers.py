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
from core.routers import get_current_user, get_db, require_role
from fastapi import APIRouter, Depends, HTTPException, Query

# ApprovalRequest 定义在 evaluation/models.py 中
from modules.evaluation.models import ApprovalRequest
from sqlalchemy import and_, func, select
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
from .services import ApprovalChainService, get_local_now

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
    if isinstance(chain_config, list):
        chain_config = {
            "nodes": chain_config,
            "total_timeout_hours": 48,
            "approval_mode": "serial_and",
        }
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
    if isinstance(chain_config, list):
        chain_config = {
            "nodes": chain_config,
            "total_timeout_hours": 48,
            "approval_mode": "serial_and",
        }
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
    user: User = Depends(get_current_user),
    _guard: User = Depends(require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER, UserRole.CLASS_TEACHER)),
    db: AsyncSession = Depends(get_db),
):
    """列出当前学校的审批链"""
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
    user: User = Depends(get_current_user),
    _guard: User = Depends(require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER, UserRole.CLASS_TEACHER)),
    db: AsyncSession = Depends(get_db),
):
    """获取审批链详情"""
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
    user: User = Depends(get_current_user),
    _guard: User = Depends(require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER, UserRole.CLASS_TEACHER)),
    db: AsyncSession = Depends(get_db),
):
    """获取当前学校的待审批工单数量"""
    result = await db.execute(
        select(func.count(ApprovalRequest.id)).where(
            ApprovalRequest.school_id == user.school_id,
            ApprovalRequest.current_status == "pending",
        )
    )
    count = result.scalar() or 0
    return PendingCountResponse(pending=count)


# ═══════════════════════════════════════════════════════════════
# 3. 动态链工单视图 (/tickets)
# ═══════════════════════════════════════════════════════════════


@router.get("/tickets", response_model=list[ApprovalTicketResponse])
async def get_tickets(
    type: str = Query(default="todo", description="todo=待审批, done=已完成"),
    user: User = Depends(get_current_user),
    _guard: User = Depends(require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER, UserRole.CLASS_TEACHER)),
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
        chain = ar.chain_config or {}
        # 防御: 旧数据 chain_config 可能是 list 而非 dict
        if isinstance(chain, list):
            chain = {
                "nodes": chain,
                "total_timeout_hours": 48,
                "approval_mode": "serial_and",
            }
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

    # 记录催办日志（后续可对接通知模块）
    logger.info(
        "[URGE] 催办 | ticket=%s node=%s school=%s user=%s",
        ticket_id,
        node_id,
        user.school_id,
        user.id,
    )

    return UrgeResponse(
        message="催办通知已发送",
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
    user: User = Depends(get_current_user),
    _guard: User = Depends(require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER, UserRole.CLASS_TEACHER)),
    db: AsyncSession = Depends(get_db),
):
    """分页查询审批请求列表"""
    conditions = [ApprovalRequest.school_id == user.school_id]
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
                chain_config=ar.chain_config or {},
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
    user: User = Depends(get_current_user),
    _guard: User = Depends(require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER, UserRole.CLASS_TEACHER)),
    db: AsyncSession = Depends(get_db),
):
    """获取单个审批请求详情"""
    result = await db.execute(
        select(ApprovalRequest).where(
            ApprovalRequest.id == req_id,
            ApprovalRequest.school_id == user.school_id,
        )
    )
    ar = result.scalar_one_or_none()
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
        chain_config=ar.chain_config or {},
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

    chain = ar.chain_config or {}
    nodes = chain.get("nodes", [])
    now = get_local_now()

    if not nodes:
        raise HTTPException(status_code=500, detail="审批链配置异常：无节点")

    current_step = ar.current_step or 0
    if current_step >= len(nodes):
        raise HTTPException(status_code=400, detail="无待审批节点")

    # 更新当前节点
    node = nodes[current_step]
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

    chain = ar.chain_config or {}
    nodes = chain.get("nodes", [])
    now = get_local_now()

    if not nodes:
        raise HTTPException(status_code=500, detail="审批链配置异常：无节点")

    current_step = ar.current_step or 0
    if current_step >= len(nodes):
        raise HTTPException(status_code=400, detail="无待审批节点")

    # 更新当前节点为 rejected
    node = nodes[current_step]
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
