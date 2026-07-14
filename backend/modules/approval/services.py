"""
modules/approval/services.py — 多租户动态审批链 业务逻辑层

核心职责:
  1. 审批链模板 CRUD (增删改查 + 版本管理 + 激活切换)
  2. 链解析 (resolve_chain): 查询活跃模板 → 转换为 Runtime Snapshot

三层隔离:
  L1 — 所有 SQL 查询强制过滤 school_id
  L2 — school_id 来自调用方（FastAPI 依赖注入 或 service 参数）
  L3 — 快照拷贝到 ApprovalRequest.chain_config，工单生命周期内不变

双接口:
  - resolve_chain(db, ...)       : 同步版 (ai_prescription tasks 等离线脚本)
  - resolve_chain_async(db, ...) : 异步版 (behavior/attendance 等 FastAPI 请求)
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy import update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from .models import TenantApprovalChain
from .schemas import TenantApprovalChainCreate, TenantApprovalChainUpdate

logger = logging.getLogger(__name__)


def get_local_now() -> datetime:
    return datetime.now(timezone(timedelta(hours=8))).replace(tzinfo=None)


# ═══════════════════════════════════════════════════════════════
# 角色 → 中文标签映射
# ═══════════════════════════════════════════════════════════════

ROLE_LABELS = {
    "class_teacher": "班主任",
    "grade_leader": "年级组长",
    "dean": "德育处长",
    "moral_education_staff": "德育干事",
    "principal": "校长",
    "ms_admin": "德育管理员",
}


# ═══════════════════════════════════════════════════════════════
# 模板 → 快照 转换器 (L3 执行层隔离的核心)
# ═══════════════════════════════════════════════════════════════


def _template_to_snapshot(template: TenantApprovalChain) -> dict[str, Any]:
    """
    将 TenantApprovalChain 模板转换为 ApprovalRequest.chain_config 快照格式。

    快照 = 模板节点 + 运行时状态（status=pending/approver_id=null/...）
    快照在工单创建时冻结，后续模板变更不影响已有工单。

    输出格式 (与现有 ApprovalRequest.chain_config 兼容):
    {
      "chain_id": 1,                       # 模板 ID（来源追溯）
      "total_timeout_hours": 144,          # 所有节点超时总和
      "escalation_strategy": "escalate",   # 最激进的 timeout action
      "nodes": [
        {
          "node_index": 0,
          "role": "class_teacher",
          "label": "班主任",
          "timeout_hours": 24,
          "action_on_timeout": "auto_approve",
          "status": "pending",
          "approver_id": null,
          "approved_at": null,
          "comment": null,
        }
      ]
    }
    """
    nodes_config = template.nodes or []

    total_timeout_h = 0
    for n in nodes_config:
        tc = n.get("timeout_config", {})
        total_timeout_h += tc.get("timeout_hours", 24)

    # 确定 escalation_strategy（取最激进的超时动作）
    strategy_priority = {"deny": 3, "escalate": 2, "auto_approve": 1}
    best_strategy = "escalate"
    best_priority = 0
    for n in nodes_config:
        tc = n.get("timeout_config", {})
        action = tc.get("action_on_timeout", "escalate")
        p = strategy_priority.get(action, 0)
        if p > best_priority:
            best_priority = p
            best_strategy = action

    runtime_nodes = []
    for n in nodes_config:
        approver_value = n.get("approver_value", "class_teacher")
        tc = n.get("timeout_config", {})

        node = {
            "node_index": n.get("node_index", len(runtime_nodes)),
            "role": approver_value,
            "label": ROLE_LABELS.get(approver_value, n.get("node_name", approver_value)),
            "timeout_hours": tc.get("timeout_hours", 24),
            "action_on_timeout": tc.get("action_on_timeout", "escalate"),
            "notify_on_timeout": tc.get("notify_on_timeout", True),
            "status": "pending",
            "activated_at": None,  # 首次激活时间 (node_index==0 时为工单创建时间)
            "approver_id": None,
            "approved_at": None,
            "comment": None,
        }
        runtime_nodes.append(node)

    return {
        "chain_id": template.id,
        "total_timeout_hours": total_timeout_h or 48,
        "escalation_strategy": best_strategy,
        "approval_mode": "serial_and" if len(runtime_nodes) > 1 else "parallel_or",
        "nodes": runtime_nodes,
    }


# ═══════════════════════════════════════════════════════════════
# 审批链解析器 — 同步版 (离线任务/脚本用)
# ═══════════════════════════════════════════════════════════════


def resolve_chain(
    db: Session,
    school_id: int,
    business_type: str,
) -> dict[str, Any] | None:
    """
    解析审批链（同步）— 查活跃模板 → 转为快照。

    返回 None = 该 school 未配置自定义链，调用方应 fallback 到 PolicyEngine / 硬编码。
    """
    template = (
        db.query(TenantApprovalChain)
        .filter(
            TenantApprovalChain.school_id == school_id,
            TenantApprovalChain.business_type == business_type,
            TenantApprovalChain.is_active == True,  # noqa: E712
        )
        .order_by(TenantApprovalChain.version.desc())
        .first()
    )

    if not template:
        return None

    snapshot = _template_to_snapshot(template)
    logger.info(
        "[CHAIN] 解析审批链(sync) | school=%s biz=%s chain_id=%s v%s nodes=%s timeout=%sh",
        school_id,
        business_type,
        template.id,
        template.version,
        len(snapshot["nodes"]),
        snapshot["total_timeout_hours"],
    )
    return snapshot


# ═══════════════════════════════════════════════════════════════
# 审批链解析器 — 异步版 (FastAPI 请求用)
# ═══════════════════════════════════════════════════════════════


async def resolve_chain_async(
    db: AsyncSession,
    school_id: int,
    business_type: str,
) -> dict[str, Any] | None:
    """
    解析审批链（异步）— 查活跃模板 → 转为快照。

    返回 None = 该 school 未配置自定义链，调用方应 fallback。
    """
    result = await db.execute(
        select(TenantApprovalChain)
        .where(
            TenantApprovalChain.school_id == school_id,
            TenantApprovalChain.business_type == business_type,
            TenantApprovalChain.is_active == True,  # noqa: E712
        )
        .order_by(TenantApprovalChain.version.desc())
    )
    template = result.scalars().first()

    if not template:
        return None

    snapshot = _template_to_snapshot(template)
    logger.info(
        "[CHAIN] 解析审批链(async) | school=%s biz=%s chain_id=%s v%s nodes=%s timeout=%sh",
        school_id,
        business_type,
        template.id,
        template.version,
        len(snapshot["nodes"]),
        snapshot["total_timeout_hours"],
    )
    return snapshot


# ═══════════════════════════════════════════════════════════════
# CRUD Service (AsyncSession)
# ═══════════════════════════════════════════════════════════════


class ApprovalChainService:
    @staticmethod
    async def list_chains(
        db: AsyncSession,
        school_id: int,
        business_type: str | None = None,
        active_only: bool = False,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[TenantApprovalChain], int]:
        """列出审批链"""
        conditions = [TenantApprovalChain.school_id == school_id]
        if business_type:
            conditions.append(TenantApprovalChain.business_type == business_type)
        if active_only:
            conditions.append(TenantApprovalChain.is_active == True)  # noqa: E712

        # 计数
        count_result = await db.execute(
            select(func.count()).select_from(TenantApprovalChain).where(and_(*conditions))
        )
        total = count_result.scalar() or 0

        # 列表
        result = await db.execute(
            select(TenantApprovalChain)
            .where(and_(*conditions))
            .order_by(
                TenantApprovalChain.business_type,
                TenantApprovalChain.version.desc(),
            )
            .offset(offset)
            .limit(limit)
        )
        items = list(result.scalars().all())
        return items, total

    @staticmethod
    async def get_chain(
        db: AsyncSession, chain_id: int, school_id: int
    ) -> TenantApprovalChain | None:
        """获取单个审批链（带 school_id 隔离）"""
        result = await db.execute(
            select(TenantApprovalChain).where(
                TenantApprovalChain.id == chain_id,
                TenantApprovalChain.school_id == school_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create_chain(
        db: AsyncSession,
        school_id: int,
        data: TenantApprovalChainCreate,
        created_by: int | None = None,
    ) -> TenantApprovalChain:
        """创建审批链（version 自动递增）"""
        # 查找 max version
        max_ver_result = await db.execute(
            select(func.max(TenantApprovalChain.version)).where(
                TenantApprovalChain.school_id == school_id,
                TenantApprovalChain.business_type == data.business_type,
            )
        )
        max_version = max_ver_result.scalar() or 0
        new_version = max_version + 1

        chain = TenantApprovalChain(
            school_id=school_id,
            business_type=data.business_type,
            chain_name=data.chain_name,
            version=new_version,
            is_active=True,
            nodes=[n.model_dump() for n in data.nodes],
            description=data.description,
            created_by=created_by,
        )
        db.add(chain)
        await db.flush()

        # 停用旧版本
        await db.execute(
            sql_update(TenantApprovalChain)
            .where(
                TenantApprovalChain.school_id == school_id,
                TenantApprovalChain.business_type == data.business_type,
                TenantApprovalChain.id != chain.id,
                TenantApprovalChain.is_active == True,  # noqa: E712
            )
            .values(is_active=False)
        )

        await db.commit()
        await db.refresh(chain)
        logger.info(
            "[CHAIN] 创建审批链 | school=%s biz=%s id=%s v=%s name=%s",
            school_id,
            data.business_type,
            chain.id,
            new_version,
            data.chain_name,
        )
        return chain

    @staticmethod
    async def update_chain(
        db: AsyncSession,
        chain_id: int,
        school_id: int,
        data: TenantApprovalChainUpdate,
    ) -> TenantApprovalChain | None:
        """更新审批链 — 节点变更创建新版本"""
        chain = await ApprovalChainService.get_chain(db, chain_id, school_id)
        if not chain:
            return None

        if data.nodes is not None:
            # 节点变更 → 新版本
            new_version = chain.version + 1
            new_chain = TenantApprovalChain(
                school_id=school_id,
                business_type=chain.business_type,
                chain_name=data.chain_name or chain.chain_name,
                version=new_version,
                is_active=chain.is_active,
                nodes=[n.model_dump() for n in data.nodes],
                description=data.description if data.description is not None else chain.description,
                created_by=chain.created_by,
            )
            db.add(new_chain)

            # 停用旧版本
            chain.is_active = False
            await db.flush()
            await db.commit()
            await db.refresh(new_chain)
            logger.info(
                "[CHAIN] 审批链节点变更→新版本 | school=%s biz=%s old_v=%s new_v=%s",
                school_id,
                chain.business_type,
                chain.version,
                new_version,
            )
            return new_chain
        else:
            # 仅元信息变更
            if data.chain_name is not None:
                chain.chain_name = data.chain_name
            if data.description is not None:
                chain.description = data.description
            if data.is_active is not None:
                chain.is_active = data.is_active
            await db.commit()
            await db.refresh(chain)
            return chain

    @staticmethod
    async def activate_chain(
        db: AsyncSession,
        chain_id: int,
        school_id: int,
    ) -> tuple[TenantApprovalChain | None, int | None]:
        """激活审批链 — 停用同 business_type 其他活跃链"""
        chain = await ApprovalChainService.get_chain(db, chain_id, school_id)
        if not chain:
            return None, None

        # 找当前活跃链
        prev_result = await db.execute(
            select(TenantApprovalChain).where(
                TenantApprovalChain.school_id == school_id,
                TenantApprovalChain.business_type == chain.business_type,
                TenantApprovalChain.is_active == True,  # noqa: E712
                TenantApprovalChain.id != chain_id,
            )
        )
        prev_active = prev_result.scalars().first()
        prev_id = prev_active.id if prev_active else None

        # 停用旧链
        await db.execute(
            sql_update(TenantApprovalChain)
            .where(
                TenantApprovalChain.school_id == school_id,
                TenantApprovalChain.business_type == chain.business_type,
                TenantApprovalChain.id != chain_id,
                TenantApprovalChain.is_active == True,  # noqa: E712
            )
            .values(is_active=False)
        )

        chain.is_active = True
        await db.commit()
        await db.refresh(chain)
        logger.info(
            "[CHAIN] 激活审批链 | school=%s biz=%s id=%s v=%s prev=%s",
            school_id,
            chain.business_type,
            chain.id,
            chain.version,
            prev_id,
        )
        return chain, prev_id

    @staticmethod
    async def delete_chain(
        db: AsyncSession,
        chain_id: int,
        school_id: int,
    ) -> bool:
        """软删除审批链（停用）"""
        chain = await ApprovalChainService.get_chain(db, chain_id, school_id)
        if not chain:
            return False
        chain.is_active = False
        await db.commit()
        logger.info(
            "[CHAIN] 停用审批链 | school=%s id=%s biz=%s v=%s",
            school_id,
            chain_id,
            chain.business_type,
            chain.version,
        )
        return True


# ═══════════════════════════════════════════════════════════════
# 默认链初始化
# ═══════════════════════════════════════════════════════════════

DEFAULT_CHAINS = {
    "behavior_minor": {
        "chain_name": "轻微违纪审批（默认）",
        "description": "班主任或德育干事任一方确认即生效，48h超时自动通过",
        "nodes": [
            {
                "node_index": 0,
                "node_name": "班主任审批",
                "approver_type": "ROLE",
                "approver_value": "class_teacher",
                "timeout_config": {
                    "timeout_hours": 24,
                    "action_on_timeout": "auto_approve",
                    "notify_on_timeout": True,
                },
            },
            {
                "node_index": 1,
                "node_name": "德育干事审批",
                "approver_type": "ROLE",
                "approver_value": "moral_education_staff",
                "timeout_config": {
                    "timeout_hours": 24,
                    "action_on_timeout": "auto_approve",
                    "notify_on_timeout": True,
                },
            },
        ],
    },
    "behavior_major": {
        "chain_name": "严重违纪审批（默认）",
        "description": "班主任→年级组长→德育处长 串行审批，超时自动通过",
        "nodes": [
            {
                "node_index": 0,
                "node_name": "班主任审批",
                "approver_type": "ROLE",
                "approver_value": "class_teacher",
                "timeout_config": {
                    "timeout_hours": 24,
                    "action_on_timeout": "auto_approve",
                    "notify_on_timeout": True,
                },
            },
            {
                "node_index": 1,
                "node_name": "年级组长审批",
                "approver_type": "ROLE",
                "approver_value": "grade_leader",
                "timeout_config": {
                    "timeout_hours": 48,
                    "action_on_timeout": "auto_approve",
                    "notify_on_timeout": True,
                },
            },
            {
                "node_index": 2,
                "node_name": "德育处长审批",
                "approver_type": "ROLE",
                "approver_value": "dean",
                "timeout_config": {
                    "timeout_hours": 72,
                    "action_on_timeout": "auto_approve",
                    "notify_on_timeout": True,
                },
            },
        ],
    },
    "behavior_critical": {
        "chain_name": "临界处分审批（默认）",
        "description": "班主任→年级组长→德育处长→校长 串行审批，超时升级",
        "nodes": [
            {
                "node_index": 0,
                "node_name": "班主任审批",
                "approver_type": "ROLE",
                "approver_value": "class_teacher",
                "timeout_config": {
                    "timeout_hours": 12,
                    "action_on_timeout": "escalate",
                    "notify_on_timeout": True,
                },
            },
            {
                "node_index": 1,
                "node_name": "年级组长审批",
                "approver_type": "ROLE",
                "approver_value": "grade_leader",
                "timeout_config": {
                    "timeout_hours": 24,
                    "action_on_timeout": "escalate",
                    "notify_on_timeout": True,
                },
            },
            {
                "node_index": 2,
                "node_name": "德育处长审批",
                "approver_type": "ROLE",
                "approver_value": "dean",
                "timeout_config": {
                    "timeout_hours": 48,
                    "action_on_timeout": "escalate",
                    "notify_on_timeout": True,
                },
            },
            {
                "node_index": 3,
                "node_name": "校长审批",
                "approver_type": "ROLE",
                "approver_value": "principal",
                "timeout_config": {
                    "timeout_hours": 72,
                    "action_on_timeout": "escalate",
                    "notify_on_timeout": True,
                },
            },
        ],
    },
    "ai_intervention": {
        "chain_name": "AI 处方干预审批（默认）",
        "description": "班主任+年级组长 并行审批，48h超时升级至德育处",
        "nodes": [
            {
                "node_index": 0,
                "node_name": "班主任审批",
                "approver_type": "ROLE",
                "approver_value": "class_teacher",
                "timeout_config": {
                    "timeout_hours": 24,
                    "action_on_timeout": "escalate",
                    "notify_on_timeout": True,
                },
            },
            {
                "node_index": 1,
                "node_name": "年级组长审批",
                "approver_type": "ROLE",
                "approver_value": "grade_leader",
                "timeout_config": {
                    "timeout_hours": 24,
                    "action_on_timeout": "escalate",
                    "notify_on_timeout": True,
                },
            },
        ],
    },
}


def seed_default_chains(db: Session, school_id: int = 1) -> int:
    """播种默认审批链（同步）— 幂等"""
    existing = (
        db.query(TenantApprovalChain)
        .filter(
            TenantApprovalChain.school_id == school_id,
        )
        .first()
    )
    if existing:
        logger.info("[CHAIN] 学校 %s 已有审批链，跳过播种", school_id)
        return 0

    count = 0
    for biz_type, config in DEFAULT_CHAINS.items():
        chain = TenantApprovalChain(
            school_id=school_id,
            business_type=biz_type,
            chain_name=config["chain_name"],
            version=1,
            is_active=True,
            nodes=config["nodes"],
            description=config.get("description", ""),
        )
        db.add(chain)
        count += 1

    db.commit()
    logger.info("[CHAIN] 学校 %s 播种 %s 条默认审批链", school_id, count)
    return count
