"""
PolicyEngine ApprovalRouter — 分层路由串并行审批引擎

日常行为 → 并行 OR（班主任/德育干事任一方确认即生效）
严重违纪 → 串行 AND（班主任→级组长→德育处长）
重大处分 → 串行 AND + 升级（四级链条，超时自动升级）
"""

from __future__ import annotations

import structlog

from .config import ApprovalRoutingConfig, ApprovalRule
from .models import ApprovalAction, ApprovalChain, ApprovalNode

logger = structlog.get_logger("policy_engine.router")


class ApprovalRouter:
    """分层路由串并行审批引擎"""

    def __init__(self, config: ApprovalRoutingConfig) -> None:
        self.config = config
        self._rule_index: dict[str, int] = {}  # event_type → rule_index
        self._build_index()

    # ── / ── / ── / ── / ── / ── / ── / ── / ── / ── / ──
    # 公开入口
    # ── / ── / ── / ── / ── / ── / ── / ── / ── / ── / ──

    def route(
        self,
        event_type: str,
        creator_role: str,
    ) -> ApprovalChain:
        """
        根据事件类型创建审批链。

        参数：
          event_type:     行为类型（如 "fighting", "lateness"）
          creator_role:   创建者的角色（用于 auto_approve_if_creator 判断）

        返回：
          ApprovalChain（含审批节点列表和模式）
        """
        rule_idx = self._rule_index.get(event_type)

        if rule_idx is None:
            logger.info(
                "approval.rule_not_found",
                event_type=event_type,
                fallback="default_rule",
            )
            return self._build_default_chain(event_type)

        rule = self.config.rules[rule_idx]
        return self._build_chain(rule, event_type, creator_role)

    def check_next_action(
        self,
        chain: ApprovalChain,
        completed_approvals: list[dict],
    ) -> ApprovalAction:
        """
        检查审批链当前状态——供轮询/Webhook 调用。

        参数：
          chain:               审批链
          completed_approvals: 已完成审批列表 [{role, status, timestamp}]

        返回：
          PENDING / APPROVED / REJECTED / ESCALATED / TIMEOUT
        """
        if chain.mode == "serial_and":
            return self._check_serial(chain, completed_approvals)
        else:
            return self._check_parallel(chain, completed_approvals)

    def get_next_pending_role(
        self, chain: ApprovalChain, completed_approvals: list[dict]
    ) -> str | None:
        """获取下一个待审批的角色（串行模式）"""
        completed_roles = {a["role"] for a in completed_approvals}
        for node in chain.nodes:
            if node.role not in completed_roles:
                return node.role
        return None

    # ── / ── / ── / ── / ── / ── / ── / ── / ── / ── / ──
    # 内部：构建索引
    # ── / ── / ── / ── / ── / ── / ── / ── / ── / ── / ──

    def _build_index(self) -> None:
        """构建事件类型→规则索引的快速查找表"""
        for i, rule in enumerate(self.config.rules):
            for et in rule.event_types:
                self._rule_index[et] = i
        logger.info(
            "approval.index_built", rules=len(self.config.rules), events=len(self._rule_index)
        )

    # ── / ── / ── / ── / ── / ── / ── / ── / ── / ── / ──
    # 内部：构建审批链
    # ── / ── / ── / ── / ── / ── / ── / ── / ── / ── / ──

    def _build_chain(
        self,
        rule: ApprovalRule,
        event_type: str,
        creator_role: str,
    ) -> ApprovalChain:
        """根据规则构建审批链"""
        if rule.mode.value == "parallel_or":
            nodes = [
                ApprovalNode(
                    role=a.role,
                    label=a.label,
                    timeout_hours=rule.timeout_hours,
                )
                for a in rule.approvers
                # 如果 auto_approve_if_creator=True 且创建者即为审批人，跳过该节点
                if not rule.auto_approve_if_creator or a.role != creator_role
            ]
            esc = None
            timeout = rule.timeout_hours

        else:  # serial_and
            nodes = [
                ApprovalNode(
                    role=cn.role,
                    label=cn.label,
                    timeout_hours=cn.timeout_hours,
                )
                for cn in rule.chain
            ]
            esc = rule.escalation_on_timeout.value if rule.escalation_on_timeout else None
            timeout = sum(cn.timeout_hours for cn in rule.chain)

        return ApprovalChain(
            event_type=event_type,
            mode=rule.mode.value,
            nodes=nodes,
            escalation_strategy=esc,
            total_timeout_hours=timeout,
        )

    def _build_default_chain(self, event_type: str) -> ApprovalChain:
        """使用默认规则构建审批链"""
        dr = self.config.default_rule
        nodes = [
            ApprovalNode(
                role=a.role,
                label=a.label,
                timeout_hours=48,
            )
            for a in dr.approvers
        ]
        return ApprovalChain(
            event_type=event_type,
            mode=dr.mode.value,
            nodes=nodes,
            escalation_strategy=None,
            total_timeout_hours=48,
        )

    # ── / ── / ── / ── / ── / ── / ── / ── / ── / ── / ──
    # 内部：状态检查
    # ── / ── / ── / ── / ── / ── / ── / ── / ── / ── / ──

    def _check_serial(
        self,
        chain: ApprovalChain,
        completed: list[dict],
    ) -> ApprovalAction:
        """串行 AND 模式状态检查"""
        # 任一节点拒绝 → 整链拒绝
        for a in completed:
            if a["status"] == "rejected":
                logger.info("approval.rejected", chain_event=chain.event_type)
                return ApprovalAction.REJECTED

        # 全部通过？
        if len(completed) == len(chain.nodes):
            logger.info("approval.approved", chain_event=chain.event_type)
            return ApprovalAction.APPROVED

        # 超时检查（简化版：只要有节点超时即触发策略）
        # 生产环境应在 Celery 中做定时超时检查，此处只做状态判断
        return ApprovalAction.PENDING

    def _check_parallel(
        self,
        chain: ApprovalChain,
        completed: list[dict],
    ) -> ApprovalAction:
        """并行 OR 模式状态检查"""
        # 任一方批准 → 生效
        for a in completed:
            if a["status"] == "approved":
                logger.info("approval.approved_parallel", chain_event=chain.event_type)
                return ApprovalAction.APPROVED

        # 全部拒绝？
        if len(completed) == len(chain.nodes):
            all_rejected = all(a["status"] == "rejected" for a in completed)
            if all_rejected:
                return ApprovalAction.REJECTED

        return ApprovalAction.PENDING
