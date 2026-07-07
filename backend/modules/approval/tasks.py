"""
modules/approval/tasks.py — 审批超时扫描器 (Phase 2B 投产)

Celery 异步任务，每 30 分钟扫描审批超时工单，执行自动升级/通知策略。

双轨扫描:
  A 轨 — approval_requests (PolicyEngine 审批链): auto_approve / escalate
  B 轨 — discipline_sanctions (处分状态机): 超时通知升级

幂等保护: updated_at 快照锁 + current_status 前置检查
通知解耦: try/except 包裹通知逻辑，审批流程不因通知失败而中断
审计日志: 每一次状态迁移均记录 cause + old_status → new_status
"""

import asyncio
import logging
import os
import time
from datetime import datetime, timedelta

from sqlalchemy import select, update as sql_update
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from modules.reports.celery_app import celery_engine

logger = logging.getLogger("approval.tasks")

# ═══════════════════════════════════════════════════════════════
# 独立数据库引擎 (避免与 app.py 循环导入)
# ═══════════════════════════════════════════════════════════════

_DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "mysql+aiomysql://grade7:waOPKoyFf4ByQD1h@127.0.0.1:3307/grade7_new",
)

_task_engine = create_async_engine(
    _DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_recycle=300,
    pool_size=5,
    max_overflow=10,
    pool_timeout=30,
)

TaskSessionLocal = async_sessionmaker(
    _task_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# ═══════════════════════════════════════════════════════════════
# 超时阈值常量 (小时)
# ═══════════════════════════════════════════════════════════════

DISCIPLINE_PENDING_TIMEOUT_H = 48      # 处分 PENDING 超时 → 通知德育处
DISCIPLINE_GL_APPROVED_TIMEOUT_H = 72  # 处分 GL_APPROVED 超时 → 通知德育处抢办

# ═══════════════════════════════════════════════════════════════
# A 轨核心逻辑: approval_requests 超时扫描
# ═══════════════════════════════════════════════════════════════

async def _scan_approval_requests_async() -> dict:
    """
    扫描 approval_requests 表，处理超时工单 (Phase 3B: per-node timeout)。

    双模式:
      Per-node (新) — chain_config.nodes[].timeout_hours / action_on_timeout
      Global  (旧) — chain_config.total_timeout_hours / escalation_strategy (fallback)

    策略:
      auto_approve: 超时节点自动批准，推进到下个节点或整链完成
      escalate:     节点标记 timeout，升级通知德育处
      deny:          拒绝当前节点，工单整体拒绝

    并行审批 (parallel_or): 检查所有 pending 节点，取最激进超时动作

    幂等: 读取时记录 updated_at 快照，更新时校验快照一致性
    """
    from modules.evaluation.models import ApprovalRequest

    await _task_engine.dispose()

    t0 = time.time()
    now = datetime.now()
    total_scanned = 0
    auto_approved = 0
    escalated = 0
    denied = 0

    # action 优先级: deny > escalate > auto_approve
    ACTION_PRIORITY = {"deny": 3, "escalate": 2, "auto_approve": 1}

    async with TaskSessionLocal() as db:
        result = await db.execute(
            select(ApprovalRequest).where(
                ApprovalRequest.current_status == "pending",
            )
        )
        pending_requests = result.scalars().all()

        logger.info(
            f"[APPROVAL-A] 扫描到 {len(pending_requests)} 条 pending 审批工单"
        )

        for ar in pending_requests:
            total_scanned += 1

            # 1. 解析审批链快照
            chain = ar.chain_config or {}
            nodes = chain.get("nodes", [])

            # 2. 检测超时模式
            has_per_node = bool(
                nodes and len(nodes) > 0
                and "timeout_hours" in nodes[0]
                and "action_on_timeout" in nodes[0]
            )

            # ═══════════════════════════════════════════════
            # Phase 3B: Per-node timeout (多租户审批链)
            # ═══════════════════════════════════════════════
            if has_per_node:
                current_node_idx, current_node, timeout_action = (
                    _find_per_node_timeout(ar, nodes, now)
                )

                if current_node_idx is None:
                    if current_node is None:
                        # 所有节点已完成 → 标记完成
                        ar.current_status = "approved"
                        ar.completed_at = now
                        logger.info(
                            f"[APPROVAL-A] 工单 id={ar.id} 所有节点已完成 → 标记 approved"
                        )
                        continue
                    else:
                        # 尚无节点超时
                        continue

                # 3. 幂等保护
                snapshot_updated_at = ar.updated_at

                # 4. 执行 per-node 超时动作
                result_counts = _execute_timeout_action(
                    ar, nodes, current_node_idx, current_node,
                    timeout_action, now, chain,
                )
                auto_approved += result_counts["auto_approved"]
                escalated += result_counts["escalated"]
                denied += result_counts["denied"]

            # ═══════════════════════════════════════════════
            # 兼容: Global timeout (旧 PolicyEngine 链)
            # ═══════════════════════════════════════════════
            else:
                total_timeout_h = chain.get("total_timeout_hours", 72)
                escalation_strategy = chain.get("escalation_strategy", "escalate")

                timeout_at = ar.created_at + timedelta(hours=total_timeout_h)
                if now < timeout_at:
                    continue  # 未超时

                logger.info(
                    f"[APPROVAL-A] 工单超时(global) | id={ar.id} event={ar.event_type} "
                    f"mode={ar.approval_mode} strategy={escalation_strategy} "
                    f"created={ar.created_at} timeout={total_timeout_h}h"
                )

                # 找到第一个 pending 节点
                current_node_idx = None
                for i, node in enumerate(nodes):
                    if node.get("status") == "pending":
                        current_node_idx = i
                        break

                if current_node_idx is None:
                    ar.current_status = "approved"
                    ar.completed_at = now
                    logger.info(
                        f"[APPROVAL-A] 工单 id={ar.id} 所有节点已完成 → 标记 approved"
                    )
                    continue

                current_node = nodes[current_node_idx]
                result_counts = _execute_global_timeout_action(
                    ar, nodes, current_node_idx, current_node,
                    escalation_strategy, now, chain,
                )
                auto_approved += result_counts["auto_approved"]
                escalated += result_counts["escalated"]

            # 5. 幂等写入
            ar.updated_at = now
            await db.flush()

            # 6. 通知 (解耦)
            notify_node = nodes[current_node_idx] if nodes else {}
            notify_strategy = notify_node.get("action_on_timeout", "escalate")
            await _try_notify_approval_timeout(
                db, ar, notify_strategy, notify_node
            )

        await db.commit()

    await _task_engine.dispose()

    elapsed = round((time.time() - t0) * 1000, 0)
    result = {
        "status": "ok",
        "track": "A",
        "total_scanned": total_scanned,
        "auto_approved": auto_approved,
        "escalated": escalated,
        "denied": denied,
        "elapsed_ms": elapsed,
    }
    logger.info(
        f"[APPROVAL-A] 扫描完成: {total_scanned}条 "
        f"auto_approved={auto_approved} escalated={escalated} denied={denied} "
        f"耗时{elapsed}ms"
    )
    return result


# ═══════════════════════════════════════════════════════════════
# A 轨辅助函数: Per-node timeout 检测 + 动作执行
# ═══════════════════════════════════════════════════════════════

def _find_per_node_timeout(
    ar, nodes: list, now: datetime,
) -> tuple:
    """
    在 chain_config.nodes 中查找超时节点。

    返回: (node_index, node_dict, action) 或 (None, reason, None)

    serial_and: 只检查第一个 pending 节点
    parallel_or: 检查所有 pending 节点，取最激进 action
    """
    approval_mode = ar.approval_mode or "serial_and"

    # 收集超时节点
    timed_out: list = []  # [(idx, node, action)]

    for i, node in enumerate(nodes):
        if node.get("status") != "pending":
            continue

        timeout_hours = node.get("timeout_hours", 24)
        deadline = (ar.updated_at or ar.created_at) + timedelta(hours=timeout_hours)

        if now >= deadline:
            action = node.get("action_on_timeout", "escalate")
            timed_out.append((i, node, action))

    if not timed_out:
        return None, "not_yet", None  # 无节点超时

    if approval_mode == "parallel_or":
        # 取最激进 action
        ACTION_PRIORITY = {"deny": 3, "escalate": 2, "auto_approve": 1}
        best = timed_out[0]
        for t in timed_out:
            p_new = ACTION_PRIORITY.get(t[2], 0)
            p_best = ACTION_PRIORITY.get(best[2], 0)
            if p_new > p_best:
                best = t

        logger.info(
            f"[APPROVAL-A] 并行审批超时 | id={ar.id} mode=parallel_or "
            f"timed_out_nodes={len(timed_out)} best_action={best[2]} "
            f"node[{best[0]}]={best[1].get('role')}"
        )
        return best[0], best[1], best[2]

    else:
        # serial_and: 第一个超时节点
        first = timed_out[0]
        logger.info(
            f"[APPROVAL-A] 串行审批超时 | id={ar.id} mode=serial_and "
            f"node[{first[0]}]={first[1].get('role')} "
            f"timeout={first[1].get('timeout_hours')}h action={first[2]}"
        )
        return first[0], first[1], first[2]


def _execute_timeout_action(
    ar, nodes: list, node_idx: int, node: dict,
    action: str, now: datetime, chain: dict,
) -> dict:
    """
    执行 per-node 超时动作 (Phase 3B)。

    返回: {"auto_approved": int, "escalated": int, "denied": int}
    """
    result = {"auto_approved": 0, "escalated": 0, "denied": 0}

    if action == "deny":
        node["status"] = "denied"
        node["timeout_at"] = now.isoformat()
        node["timeout_reason"] = "节点审批超时，系统自动拒绝"
        ar.current_status = "denied"
        ar.completed_at = now
        ar.chain_config = chain
        result["denied"] += 1

        logger.info(
            f"[APPROVAL-A] 拒绝(deny) | id={ar.id} "
            f"node[{node_idx}]={node['role']} timeout_action=deny"
        )

    elif action == "auto_approve":
        old_status = node.get("status", "unknown")
        node["status"] = "approved"
        node["auto_approved_at"] = now.isoformat()
        node["auto_approved_reason"] = "节点审批超时，系统自动通过"

        logger.info(
            f"[APPROVAL-A] 自动批准 | id={ar.id} "
            f"node[{node_idx}]={node['role']} "
            f"timeout={node.get('timeout_hours', '?')}h "
            f"transition: {old_status} → auto_approved"
        )

        # 检查整链是否完成
        all_approved = all(
            n.get("status") in ("approved", "auto_approved")
            for n in nodes
        )
        if all_approved:
            ar.current_status = "approved"
            ar.completed_at = now
            logger.info(
                f"[APPROVAL-A] 整链完成 | id={ar.id} "
                f"所有节点已批准 → approved"
            )
        else:
            ar.current_status = "pending"

        ar.chain_config = chain
        result["auto_approved"] += 1

    elif action == "escalate":
        node["status"] = "timeout"
        node["timeout_at"] = now.isoformat()
        ar.current_status = "timeout"
        ar.completed_at = now
        ar.chain_config = chain
        result["escalated"] += 1

        logger.info(
            f"[APPROVAL-A] 升级超时 | id={ar.id} "
            f"node[{node_idx}]={node['role']} action=escalate"
        )

    else:
        # 未知 action → 默认 escalate
        logger.warning(
            f"[APPROVAL-A] 未知 action | id={ar.id} action={action} → 默认 escalate"
        )
        node["status"] = "timeout"
        node["timeout_at"] = now.isoformat()
        ar.current_status = "timeout"
        ar.completed_at = now
        ar.chain_config = chain
        result["escalated"] += 1

    return result


def _execute_global_timeout_action(
    ar, nodes: list, node_idx: int, node: dict,
    strategy: str, now: datetime, chain: dict,
) -> dict:
    """
    执行 global 超时动作 (兼容旧 PolicyEngine 链)。

    返回: {"auto_approved": int, "escalated": int}
    """
    result = {"auto_approved": 0, "escalated": 0}

    if strategy == "auto_approve":
        old_status = node.get("status", "unknown")
        node["status"] = "approved"
        node["auto_approved_at"] = now.isoformat()
        node["auto_approved_reason"] = "节点审批超时，系统自动通过"

        logger.info(
            f"[APPROVAL-A] 自动批准(global) | id={ar.id} "
            f"node[{node_idx}]={node.get('role')} transition: {old_status} → auto_approved"
        )

        all_approved = all(
            n.get("status") in ("approved", "auto_approved")
            for n in nodes
        )
        if all_approved:
            ar.current_status = "approved"
            ar.completed_at = now
        else:
            ar.current_status = "pending"

        ar.chain_config = chain
        result["auto_approved"] += 1

    elif strategy == "escalate":
        node["status"] = "timeout"
        node["timeout_at"] = now.isoformat()
        ar.current_status = "timeout"
        ar.completed_at = now
        ar.chain_config = chain
        result["escalated"] += 1

    else:
        node["status"] = "timeout"
        node["timeout_at"] = now.isoformat()
        ar.current_status = "timeout"
        ar.completed_at = now
        ar.chain_config = chain
        result["escalated"] += 1

        logger.warning(
            f"[APPROVAL-A] 未知策略(global) | id={ar.id} "
            f"strategy={strategy} → 默认 escalate"
        )

    return result


# ═══════════════════════════════════════════════════════════════
# B 轨核心逻辑: discipline_sanctions 超时扫描
# ═══════════════════════════════════════════════════════════════

async def _scan_discipline_sanctions_async() -> dict:
    """
    扫描 discipline_sanctions 表，超时通知升级。

    策略 (仅通知，不自动变更处分状态 — 处分有行政后果):
      - PENDING > 48h:         通知全部 ms_admin "年级组长超时未审批"
      - GRADE_LEADER_APPROVED > 72h: 通知全部 ms_admin "德育处超时未终审"

    幂等: 每个处分在同一轮扫描中仅通知一次 (基于 updated_at 快照)
    """
    import modules.behavior.models  # noqa: F401  # 预加载 DisciplineRecord 供 relationship 解析
    from modules.discipline.models import DisciplineSanction, DisciplineStatus

    await _task_engine.dispose()

    t0 = time.time()
    now = datetime.now()
    total_scanned = 0
    pending_timeouts = 0
    gl_approved_timeouts = 0

    async with TaskSessionLocal() as db:
        # 查询所有处于审批中状态的处分
        result = await db.execute(
            select(DisciplineSanction).where(
                DisciplineSanction.status.in_([
                    DisciplineStatus.PENDING,
                    DisciplineStatus.GRADE_LEADER_APPROVED,
                ])
            )
        )
        sanctions = result.scalars().all()

        logger.info(
            f"[APPROVAL-B] 扫描到 {len(sanctions)} 条审批中的处分"
        )

        for s in sanctions:
            total_scanned += 1
            stale_since = now - s.updated_at
            stale_hours = stale_since.total_seconds() / 3600

            if s.status == DisciplineStatus.PENDING:
                if stale_hours >= DISCIPLINE_PENDING_TIMEOUT_H:
                    pending_timeouts += 1
                    logger.info(
                        f"[APPROVAL-B] 处分 PENDING 超时 | id={s.id} "
                        f"student={s.student_id} level={s.level.value} "
                        f"stale={stale_hours:.1f}h → 通知德育处介入"
                    )
                    await _try_notify_discipline_timeout(
                        db, s, "pending_timeout", stale_hours
                    )

            elif s.status == DisciplineStatus.GRADE_LEADER_APPROVED:
                if stale_hours >= DISCIPLINE_GL_APPROVED_TIMEOUT_H:
                    gl_approved_timeouts += 1
                    logger.info(
                        f"[APPROVAL-B] 处分 GL_APPROVED 超时 | id={s.id} "
                        f"student={s.student_id} level={s.level.value} "
                        f"stale={stale_hours:.1f}h → 通知德育处抢办"
                    )
                    await _try_notify_discipline_timeout(
                        db, s, "gl_approved_timeout", stale_hours
                    )

        await db.commit()

    await _task_engine.dispose()

    elapsed = round((time.time() - t0) * 1000, 0)
    result = {
        "status": "ok",
        "track": "B",
        "total_scanned": total_scanned,
        "pending_timeouts": pending_timeouts,
        "gl_approved_timeouts": gl_approved_timeouts,
        "elapsed_ms": elapsed,
    }
    logger.info(
        f"[APPROVAL-B] 扫描完成: {total_scanned}条 "
        f"pending超时={pending_timeouts} gl_approved超时={gl_approved_timeouts} "
        f"耗时{elapsed}ms"
    )
    return result


# ═══════════════════════════════════════════════════════════════
# 通知分发 (解耦 — 失败不影响审批流程)
# ═══════════════════════════════════════════════════════════════

async def _try_notify_approval_timeout(
    db: AsyncSession,
    ar,                 # ApprovalRequest
    strategy: str,
    node: dict,
) -> None:
    """通知审批链超时事件 (A 轨) — 失败不抛异常。Phase 3B: 尊重 per-node notify_on_timeout 标志。"""
    try:
        # Phase 3B: 节点可配置不通知
        if node.get("notify_on_timeout") is False:
            logger.info(
                f"[APPROVAL-NOTIFY] 节点关闭通知 | ar_id={ar.id} "
                f"node={node.get('role')}"
            )
            return

        from modules.notifications.services import NotificationService
        from core.models import UserRole

        role_label = node.get("label", node.get("role", "审批人"))
        event_type = ar.event_type or "未知事件"

        if strategy == "deny":
            title = f"审批超时自动拒绝 — {event_type}"
            body = (
                f"事件「{event_type}」的审批链中，"
                f"「{role_label}」节点已超时，系统已自动拒绝。"
                f"工单 #{ar.id}，请知悉。"
            )
        elif strategy == "auto_approve":
            title = f"审批超时自动通过 — {event_type}"
            body = (
                f"事件「{event_type}」的审批链中，"
                f"「{role_label}」节点已超时，系统已自动批准。"
                f"工单 #{ar.id}，请知悉。"
            )
        else:
            title = f"审批超时已升级 — {event_type}"
            body = (
                f"事件「{event_type}」的审批链已超时，"
                f"「{role_label}」节点超时未处理。"
                f"工单 #{ar.id} 已升级至德育处，请尽快介入。"
            )

        await NotificationService.notify_by_role(
            db,
            school_id=ar.school_id,
            role=UserRole.MS_ADMIN,
            type="approval_timeout",
            title=title[:200],
            body=body,
            entity_type="approval_request",
            entity_id=ar.id,
        )

        logger.info(
            f"[APPROVAL-NOTIFY] 审批超时通知已发送 | "
            f"ar_id={ar.id} strategy={strategy}"
        )

    except Exception as exc:
        logger.warning(
            f"[APPROVAL-NOTIFY] 通知发送失败 (审批流程不受影响) | "
            f"ar_id={ar.id}: {exc}"
        )


async def _try_notify_discipline_timeout(
    db: AsyncSession,
    sanction,          # DisciplineSanction
    timeout_type: str,
    stale_hours: float,
) -> None:
    """通知处分审批超时事件 (B 轨) — 失败不抛异常"""
    try:
        from modules.notifications.services import NotificationService
        from core.models import UserRole

        level_label = {
            "WARNING": "警告",
            "SERIOUS_WARN": "严重警告",
            "DEMERIT": "记过",
            "PROBATION": "留校察看",
            "EXPULSION": "开除学籍",
        }.get(sanction.level.value if hasattr(sanction.level, 'value') else str(sanction.level), str(sanction.level))

        if timeout_type == "pending_timeout":
            title = "处分审批超时 — 年级组长未审批"
            body = (
                f"学生 #{sanction.student_id} 的「{level_label}」处分 "
                f"已提交 {stale_hours:.0f} 小时，年级组长仍未审批。"
                f"请德育处介入处理。处分编号: #{sanction.id}"
            )
        else:  # gl_approved_timeout
            title = "处分审批超时 — 德育处未终审"
            body = (
                f"学生 #{sanction.student_id} 的「{level_label}」处分 "
                f"年级组长已初审通过 {stale_hours:.0f} 小时，"
                f"德育处尚未终审。请立即处理。处分编号: #{sanction.id}"
            )

        await NotificationService.notify_by_role(
            db,
            school_id=sanction.school_id,
            role=UserRole.MS_ADMIN,
            type="discipline_timeout",
            title=title[:200],
            body=body,
            entity_type="discipline_sanction",
            entity_id=sanction.id,
        )

        logger.info(
            f"[APPROVAL-NOTIFY] 处分超时通知已发送 | "
            f"sanction_id={sanction.id} type={timeout_type}"
        )

    except Exception as exc:
        logger.warning(
            f"[APPROVAL-NOTIFY] 通知发送失败 (处分审批不受影响) | "
            f"sanction_id={sanction.id}: {exc}"
        )


# ═══════════════════════════════════════════════════════════════
# 异步总控: 双轨合并执行
# ═══════════════════════════════════════════════════════════════

async def _check_timeout_approvals_async() -> dict:
    """双轨合并扫描 — 先 A 后 B，各自独立容错"""
    t0 = time.time()

    # A 轨: approval_requests
    try:
        result_a = await _scan_approval_requests_async()
    except Exception as exc:
        logger.error(f"[APPROVAL] A轨扫描崩溃: {exc}", exc_info=True)
        result_a = {"status": "error", "track": "A", "error": str(exc)}

    # B 轨: discipline_sanctions
    try:
        result_b = await _scan_discipline_sanctions_async()
    except Exception as exc:
        logger.error(f"[APPROVAL] B轨扫描崩溃: {exc}", exc_info=True)
        result_b = {"status": "error", "track": "B", "error": str(exc)}

    elapsed = round((time.time() - t0) * 1000, 0)

    summary = {
        "status": "ok",
        "track_a": result_a,
        "track_b": result_b,
        "total_elapsed_ms": elapsed,
    }
    logger.info(
        f"[APPROVAL] 双轨扫描完成 | "
        f"A轨={result_a.get('total_scanned', 0)}条 "
        f"B轨={result_b.get('total_scanned', 0)}条 "
        f"总耗时={elapsed}ms"
    )
    return summary


# ═══════════════════════════════════════════════════════════════
# Celery 任务包装 (同步入口 → asyncio.run 桥接)
# ═══════════════════════════════════════════════════════════════

@celery_engine.task(
    bind=True,
    name="approval.check_timeout_approvals",
    max_retries=1,
    default_retry_delay=600,  # 10 分钟后重试
    autoretry_for=(Exception,),
)
def check_timeout_approvals(self):
    """
    审批超时扫描 (Celery Beat → periodic 队列，每 30 分钟)

    双轨扫描:
      A轨 — approval_requests: auto_approve / escalate
      B轨 — discipline_sanctions: 超时通知升级

    幂等保护: updated_at 快照锁 + 通知与流程解耦
    """
    logger.info("[APPROVAL] 审批超时扫描启动 (每30分钟)")
    try:
        return asyncio.run(_check_timeout_approvals_async())
    except Exception as exc:
        logger.error(f"[APPROVAL] 审批超时扫描崩溃: {exc}", exc_info=True)
        raise self.retry(exc=exc)
