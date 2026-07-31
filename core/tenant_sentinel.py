"""
core/tenant_sentinel.py — 租户检查哨兵 (Tenant Sentinel)

Wings 3.0 安全免疫系统：启动时自动扫描所有已注册 FastAPI 路由，
检测缺失 verify_entity_ownership 守卫的端点，从"被动修补"转向"主动免疫"。

原理：
  1. 遍历 app.routes 中所有 APIRoute
  2. 识别路径中含实体 ID 参数（{student_id}, {class_id} 等）的端点
  3. 检查端点函数源码是否调用了 verify_entity_ownership
  4. 对比允许名单，报告所有未受保护的路由

模式：
  TENANT_SENTINEL_MODE=warn  → 仅警告日志（默认，生产推荐）
  TENANT_SENTINEL_MODE=error → 阻断启动，直到所有路由合规
  TENANT_SENTINEL_MODE=off   → 完全关闭

集成方式（在 app.py lifespan 中，yield 之前调用）：
  from core.tenant_sentinel import TenantSentinel
  sentinel = TenantSentinel()
  violations = sentinel.scan(app)
  sentinel.report(violations)
"""

import inspect
import logging
import os
import re
from dataclasses import dataclass, field
from typing import List, Optional, Set, Dict, Tuple

from fastapi import FastAPI
from fastapi.routing import APIRoute
from starlette.routing import Mount

logger = logging.getLogger("tenant_sentinel")

# ── 已知实体 ID 路径参数模式 ──
# 匹配 {xxx_id} 格式的路径参数（排除 task_id / trace_id 等非数据库实体）
ENTITY_ID_PATTERN = re.compile(r"\{([a-z_]+_id)\}")

# 非数据库实体的 ID 参数（Celery task UUID、日志 trace UUID 等）
NON_ENTITY_IDS: Set[str] = {
    "task_id",      # Celery 异步任务 UUID
    "trace_id",     # 数据血缘追踪 UUID（lineage 模块）
}


@dataclass
class Violation:
    """单个守卫缺失违规"""
    route_path: str           # 完整路径，如 /api/v1/grades/scores/{exam_id}/student/{student_id}
    methods: List[str]        # HTTP 方法，如 ['GET']
    module: str               # 所属模块名，如 'grades'
    missing_entity_ids: List[str]  # 缺失守卫的实体ID参数，如 ['exam_id', 'student_id']
    current_guard: str        # 当前使用的守卫方式描述

    def __str__(self) -> str:
        ids = ", ".join(self.missing_entity_ids)
        methods = "/".join(self.methods)
        return f"[{self.module}] {methods} {self.route_path} — 缺失: {ids} (当前: {self.current_guard})"


@dataclass
class ScanResult:
    """扫描结果"""
    total_routes: int = 0
    entity_routes: int = 0    # 含实体ID参数的路由数
    guarded_routes: int = 0   # 已守卫的路由数
    violations: List[Violation] = field(default_factory=list)
    allowlisted: int = 0      # 允许名单放行的路由数
    errors: List[str] = field(default_factory=list)

    @property
    def pass_rate(self) -> float:
        if self.entity_routes == 0:
            return 100.0
        return (self.guarded_routes / self.entity_routes) * 100


class TenantSentinel:
    """租户检查哨兵 — 启动时路由安全扫描器"""

    # ── 允许名单：已知安全的端点 ──
    # 格式: (路径前缀, HTTP方法集合, 原因)
    # 这些端点已通过其他方式保证数据隔离（自定义守卫 / 等效逻辑）
    ALLOWLIST: List[Tuple[str, Set[str], str]] = [
        # ── Core 模块 — 认证/基础设施 ──
        ("/api/v1/health", {"GET"}, "健康检查，无需认证"),
        ("/api/v1/auth/", {"POST", "GET"}, "认证端点，无数据实体"),
        ("/api/v1/schools/{school_id}", {"GET"}, "已使用 verify_school_access() 等效守卫"),
        ("/api/v1/schools/{school_id}/modules", {"GET"}, "已使用 verify_school_access() 等效守卫"),

        # ── growth 模块 — 自定义守卫 ──
        ("/api/v1/growth/timeline/{student_id}", {"GET"}, "已使用 _verify_student_access() 更强自定义守卫"),

        # ── notifications 模块 — 按收件人隔离 ──
        ("/api/v1/notifications/{notification_id}", {"PUT", "DELETE"}, "按 recipient_id 隔离"),

        # ── reports 模块 — Celery UUID ──
        ("/api/v1/reports/tasks/{task_id}", {"GET"}, "Celery 异步任务 UUID"),

        # ═══════════════════════════════════════════════════════
        # 以下 14 条为等效守卫端点 ALLOWLIST 扩展 (2026-07-06)
        # 覆盖 26 个违规端点，按模块审计确认均存在等效 school_id 隔离
        # ═══════════════════════════════════════════════════════

        # ── ai_prescription: GET records/{record_id} ──
        # 等效守卫: AIPrescription.school_id == current_user.school_id
        ("/api/v1/ai_prescription/records/{record_id}", {"GET"},
         "AIPrescription.school_id == current_user.school_id 等效守卫"),

        # ── evaluation: PUT/POST/DELETE indicators/{indicator_id} (3条) ──
        # 等效守卫: require_role(MS_ADMIN) + update_indicator/delete_indicator 传递 school_id
        ("/api/v1/evaluation/indicators/{indicator_id}", {"PUT", "POST", "DELETE"},
         "require_role(MS_ADMIN) + service 层 school_id 过滤"),

        # ── grades: subjects + exams + scores (5条) ──
        # 等效守卫: require_role(MS_ADMIN) / get_current_user + service 层 school_id
        ("/api/v1/grades/subjects/{subject_id}", {"PUT", "PATCH"},
         "require_role(MS_ADMIN) + update_subject/toggle_subject 传递 school_id"),
        ("/api/v1/grades/exams/{exam_id}", {"PUT", "PATCH"},
         "require_role(MS_ADMIN) + update_exam/update_exam_status 传递 school_id"),
        ("/api/v1/grades/scores/{exam_id}/", {"GET"},
         "get_current_user 传递 school_id 到 get_student_score 服务层"),

        # ── lineage: students + sources (2条) ──
        # 等效守卫: school_id 参数已在 Task #1268 修复，SQL WHERE 强制隔离
        ("/api/v1/lineage/students/{student_id}", {"GET"},
         "get_student_lineage() 已传递 school_id 到 SQL WHERE (Task #1268 修复)"),
        ("/api/v1/lineage/sources/{source_type}/", {"GET"},
         "get_source_descendants() 已传递 school_id 到 SQL WHERE (Task #1268 修复)"),

        # ── teach_math: report/{class_id}/kpi|blind-spots|students (3条) ──
        # 等效守卫: _check_class_access() RBAC + 报告服务层 school_id 过滤
        ("/api/v1/teach_math/report/{class_id}/", {"GET"},
         "_check_class_access() RBAC + 报告服务层 school_id 过滤"),

        # ── risk_models: warnings/{warning_id}/handle + scan/class/{class_id} (2条) ──
        # 等效守卫: Celery 异步任务链传递 school_id / require_role 等效
        ("/api/v1/risk_models/warnings/{warning_id}/handle", {"POST"},
         "handle_warning() 通过 Celery 任务链传递 school_id"),
        ("/api/v1/risk_models/scan/class/{class_id}", {"POST"},
         "require_role() + trigger_class_scan() 传递 school_id"),

        # ── approval: chains + tickets + requests (8条) ──
        # 等效守卫: 内联 school_id == user.school_id / get_current_user 传递
        ("/api/v1/approval/chains/{chain_id}", {"GET", "PUT", "POST", "DELETE"},
         "内联 school_id == user.school_id 等效守卫 / get_current_user"),
        ("/api/v1/approval/tickets/{ticket_id}/urge", {"POST"},
         "内联 school_id == user.school_id 等效守卫"),
        ("/api/v1/approval/requests/{req_id}", {"GET", "POST"},
         "内联 school_id == user.school_id 等效守卫 / get_current_user"),

        # ── parent_portal: feedbacks/{feedback_id} + reply (2条) ──
        # 等效守卫: get_current_user / 内联 school_id 检查
        ("/api/v1/parent_portal/feedbacks/{feedback_id}", {"GET", "POST"},
         "get_current_user 传递 school_id / 内联 school_id 等效守卫"),
    ]

    def __init__(self, mode: Optional[str] = None):
        """
        Args:
            mode: 'warn' | 'error' | 'off' (默认从环境变量 TENANT_SENTINEL_MODE 读取)
        """
        self.mode = mode or os.getenv("TENANT_SENTINEL_MODE", "warn").lower()
        if self.mode not in ("warn", "error", "off"):
            logger.warning(f"未知 TENANT_SENTINEL_MODE='{self.mode}'，回退为 'warn'")
            self.mode = "warn"

    def scan(self, app: FastAPI) -> ScanResult:
        """执行全量路由扫描 — 递归穿透 _IncludedRouter / Mount / APIRouter"""
        result = ScanResult()

        # 递归收集所有 APIRoute（穿透包装器），携带完整路径前缀
        all_api_routes: List[Tuple[APIRoute, str]] = []
        self._collect_all_routes(app.routes, "", all_api_routes)

        for route, prefix in all_api_routes:
            result.total_routes += 1

            # 构造完整路径
            full_path = prefix + route.path

            # 提取路径中的实体 ID 参数
            entity_ids = self._extract_entity_ids(full_path)

            if not entity_ids:
                continue  # 无实体 ID，跳过

            result.entity_routes += 1

            # 检查允许名单
            if self._is_allowlisted(full_path, route.methods):
                result.allowlisted += 1
                result.guarded_routes += 1
                continue

            # 检查端点源码是否调用了 verify_entity_ownership
            if self._has_ownership_guard(route):
                result.guarded_routes += 1
                continue

            # 违规！
            result.violations.append(
                Violation(
                    route_path=full_path,
                    methods=list(route.methods) if route.methods else [],
                    module=self._guess_module(full_path),
                    missing_entity_ids=entity_ids,
                    current_guard=self._detect_current_guard(route),
                )
            )

        return result

    def _collect_all_routes(
        self, routes: list, prefix: str, result: List[Tuple[APIRoute, str]]
    ) -> None:
        """递归收集所有 APIRoute，穿透 _IncludedRouter / Mount / APIRouter

        将 (APIRoute, accumulated_prefix) 添加到 result 列表。
        """
        for obj in routes:
            if isinstance(obj, APIRoute):
                result.append((obj, prefix))
            elif isinstance(obj, Mount):
                # Mount 对象（如 StaticFiles）— 递归进入，累加路径
                mount_prefix = prefix + (obj.path or "")
                self._collect_all_routes(obj.routes, mount_prefix, result)
            elif hasattr(obj, "original_router") and hasattr(obj, "include_context"):
                # FastAPI _IncludedRouter — 获取注册时的前缀
                included_prefix = prefix + (obj.include_context.prefix or "")
                self._collect_all_routes(obj.original_router.routes, included_prefix, result)
            elif hasattr(obj, "routes"):
                # 通用 APIRouter / 其他有 routes 属性的对象
                self._collect_all_routes(obj.routes, prefix, result)

    def report(self, result: ScanResult) -> None:
        """输出扫描报告并根据模式决定是否阻断"""
        if self.mode == "off":
            logger.info("Tenant Sentinel 已关闭 (TENANT_SENTINEL_MODE=off)")
            return

        # ── 汇总 ──
        logger.info("═" * 60)
        logger.info("Tenant Sentinel — 租户检查哨兵扫描报告")
        logger.info("═" * 60)
        logger.info(f"  总路由数:     {result.total_routes}")
        logger.info(f"  含实体ID路由: {result.entity_routes}")
        logger.info(f"  已守卫:       {result.guarded_routes} ({result.pass_rate:.0f}%)")
        logger.info(f"  允许名单放行: {result.allowlisted}")
        logger.info(f"  违规:         {len(result.violations)}")

        if result.errors:
            logger.info(f"  扫描错误:     {len(result.errors)}")
            for err in result.errors:
                logger.warning(f"    ⚠ {err}")

        if not result.violations:
            logger.info("  ✓ 全部实体 ID 路由已通过守卫验证！")
            logger.info("═" * 60)
            return

        # ── 违规详情 ──
        logger.warning("─" * 60)
        logger.warning(f"  发现 {len(result.violations)} 个未守卫的实体 ID 端点：")
        logger.warning("─" * 60)
        for i, v in enumerate(result.violations, 1):
            logger.warning(f"  #{i} {v}")

        # 分类汇总
        by_module: Dict[str, int] = {}
        for v in result.violations:
            by_module[v.module] = by_module.get(v.module, 0) + 1

        logger.warning("─" * 60)
        logger.warning("  按模块汇总：")
        for mod, count in sorted(by_module.items()):
            logger.warning(f"    {mod}: {count} 个违规")

        logger.warning("═" * 60)

        # ── 模式决定 ──
        if self.mode == "error":
            msg = (
                f"Tenant Sentinel 发现 {len(result.violations)} 个未守卫端点，"
                f"当前模式为 'error'，拒绝启动。"
                f"请为所有违规端点添加 verify_entity_ownership 守卫，"
                f"或将已知安全端点加入 ALLOWLIST。"
            )
            logger.error(msg)
            raise RuntimeError(msg)
        else:
            logger.warning(
                f"当前模式为 'warn'，允许继续运行。"
                f"设置 TENANT_SENTINEL_MODE=error 可阻断未合规部署。"
            )

    # ── 内部方法 ──

    def _extract_entity_ids(self, path: str) -> List[str]:
        """从路径中提取实体 ID 参数（排除 task_id 等非实体 ID）"""
        ids = ENTITY_ID_PATTERN.findall(path)
        return [id_ for id_ in ids if id_ not in NON_ENTITY_IDS]

    def _is_allowlisted(self, path: str, methods: Set[str]) -> bool:
        """检查端点是否在允许名单中"""
        for allow_path, allow_methods, _reason in self.ALLOWLIST:
            if path.startswith(allow_path):
                if not allow_methods or methods & allow_methods:
                    return True
        return False

    def _has_ownership_guard(self, route: APIRoute) -> bool:
        """检查端点函数源码是否调用了 verify_entity_ownership"""
        try:
            endpoint = route.endpoint
            source = inspect.getsource(endpoint)
            return "verify_entity_ownership" in source
        except (OSError, TypeError, Exception):
            # 无法获取源码（内置函数 / lambda / 装饰器包装等）
            return False

    def _guess_module(self, path: str) -> str:
        """从路径推断模块名"""
        # 路径格式: /api/v1/{module-code}/*
        parts = path.split("/")
        if len(parts) >= 4 and parts[1] == "api" and parts[2] == "v1":
            return parts[3]
        return "unknown"

    def _detect_current_guard(self, route: APIRoute) -> str:
        """检测端点当前使用的守卫方式"""
        try:
            source = inspect.getsource(route.endpoint)
        except (OSError, TypeError, Exception):
            return "未知（无法读取源码）"

        guards = []
        if "require_role" in source:
            # 提取角色名
            roles = re.findall(r'require_role\s*\(\s*[^)]*\)', source)
            if roles:
                guards.append(f"require_role({roles[0][:60]}...)")
            else:
                guards.append("require_role()")
        if "get_current_user" in source:
            guards.append("get_current_user")
        if "_check_class_access" in source:
            guards.append("_check_class_access")
        if "_verify_student_access" in source:
            guards.append("_verify_student_access")
        if "verify_school_access" in source:
            guards.append("verify_school_access")
        if "_require_parent" in source:
            guards.append("_require_parent")

        if not guards:
            # 检查是否有内联 school_id 检查
            if "school_id" in source or "current_user.school_id" in source:
                return "内联 school_id 检查（非集中式守卫）"

        return ", ".join(guards) if guards else "无任何守卫（裸奔）"


# ── 便捷工厂函数 ──

def create_sentinel(mode: Optional[str] = None) -> TenantSentinel:
    """创建哨兵实例"""
    return TenantSentinel(mode=mode)


async def scan_and_report(app: FastAPI, mode: Optional[str] = None) -> ScanResult:
    """一键扫描 + 报告"""
    sentinel = TenantSentinel(mode=mode)
    result = sentinel.scan(app)
    sentinel.report(result)
    return result
