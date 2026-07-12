"""
module_loader.py — Wings 3.0 模块动态加载引擎

核心职责：
1. 扫描 modules/ 目录下所有 manifest.py
2. 构建模块依赖 DAG，完成拓扑排序
3. 读取 school_modules 表，按租户启用/禁用路由
4. 熔断降级：依赖缺失 → 跳过 + 告警，绝不引发全盘崩溃
"""

import os
import sys
import importlib
import importlib.util
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any, Set
from collections import defaultdict, deque
from dataclasses import dataclass, field
import logging

logger = logging.getLogger("module_loader")


# ═══════════════════════════════════════════════════════════════
# 数据结构
# ═══════════════════════════════════════════════════════════════

@dataclass
class ModuleManifest:
    """模块元信息声明"""
    code: str              # 模块代码，如 "attendance"
    name: str              # 显示名称，如 "考勤管理"
    category: str          # 分类：behavior / academic / mental / admin
    dependencies: List[str] = field(default_factory=list)  # 前置依赖模块代码
    path: str = ""         # 物理路径
    enabled_by_default: bool = False  # 新学校是否默认启用
    phases: List[str] = field(default_factory=list)  # 适用学段白名单, 空列表=全学段开放

    def validate(self) -> List[str]:
        """自检 manifest 合法性，返回错误列表"""
        errors = []
        if not self.code or not self.code.strip():
            errors.append(f"[{self.path}] MODULE_CODE 不能为空")
        if not self.name:
            errors.append(f"[{self.path}] MODULE_NAME 不能为空")
        return errors


@dataclass
class LoadResult:
    """模块加载结果"""
    module: ModuleManifest
    success: bool
    error: Optional[str] = None
    dep_skipped: bool = False  # 因依赖缺失被熔断
    dep_missing: List[str] = field(default_factory=list)
    config_level: Optional[str] = None   # "school" / "branch" / "org" / "default" / None
    config_enabled: Optional[bool] = None  # 级联配置是否启用


# ═══════════════════════════════════════════════════════════════
# 扫描器
# ═══════════════════════════════════════════════════════════════

class ModuleScanner:
    """扫描 modules/ 目录，读取所有 manifest.py"""

    def __init__(self, modules_root: str):
        self.modules_root = Path(modules_root)
        if not self.modules_root.is_dir():
            raise FileNotFoundError(f"模块目录不存在: {modules_root}")

    def scan(self) -> Dict[str, ModuleManifest]:
        """扫描并返回 {module_code: ModuleManifest}"""
        manifests: Dict[str, ModuleManifest] = {}

        for entry in sorted(self.modules_root.iterdir()):
            if not entry.is_dir():
                continue
            if entry.name.startswith("_") or entry.name.startswith("."):
                continue

            manifest_file = entry / "manifest.py"
            if not manifest_file.is_file():
                logger.debug(f"跳过无 manifest 的目录: {entry.name}")
                continue

            try:
                manifest = self._load_manifest(manifest_file, str(entry))
                if manifest.code in manifests:
                    logger.error(f"模块代码冲突: {manifest.code} ({entry.name})")
                    continue
                manifests[manifest.code] = manifest
                logger.info(f"发现模块: [{manifest.code}] {manifest.name}")
            except Exception as e:
                logger.error(f"加载 manifest 失败 [{entry.name}]: {e}")

        return manifests

    def _load_manifest(self, manifest_path: Path, module_dir: str) -> ModuleManifest:
        """从 manifest.py 动态加载模块声明"""
        spec = importlib.util.spec_from_file_location(
            f"_wings_module_{manifest_path.parent.name}",
            manifest_path
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"无法解析: {manifest_path}")

        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)

        code = getattr(mod, "MODULE_CODE", manifest_path.parent.name)
        name = getattr(mod, "MODULE_NAME", code)
        category = getattr(mod, "MODULE_CATEGORY", "uncategorized")
        dependencies = list(getattr(mod, "MODULE_DEPENDENCIES", []))
        enabled_default = getattr(mod, "ENABLED_BY_DEFAULT", False)
        phases = list(getattr(mod, "MODULE_PHASES", []))  # 空列表 = 全学段开放

        manifest = ModuleManifest(
            code=code,
            name=name,
            category=category,
            dependencies=dependencies,
            path=str(module_dir),
            enabled_by_default=enabled_default,
            phases=phases,
        )

        errors = manifest.validate()
        if errors:
            raise ValueError("; ".join(errors))

        return manifest


# ═══════════════════════════════════════════════════════════════
# DAG 拓扑排序器
# ═══════════════════════════════════════════════════════════════

class TopologicalSorter:
    """
    基于 Kahn 算法的 DAG 拓扑排序。

    输入: {module_code: ModuleManifest}
    输出: 按依赖顺序排列的 module_code 列表
    """

    @staticmethod
    def sort(manifests: Dict[str, ModuleManifest]) -> Tuple[List[str], Set[str]]:
        """
        返回 (sorted_codes, missing_deps)
        - sorted_codes: 拓扑排序后的模块代码列表
        - missing_deps: 声明了但系统中不存在的依赖
        """
        # 构建邻接表和入度
        in_degree: Dict[str, int] = {code: 0 for code in manifests}
        adjacency: Dict[str, List[str]] = {code: [] for code in manifests}
        missing: Set[str] = set()

        for code, manifest in manifests.items():
            for dep in manifest.dependencies:
                if dep not in manifests:
                    missing.add(dep)
                    logger.warning(f"[{code}] 依赖缺失模块: {dep} — 将触发熔断")
                else:
                    adjacency[dep].append(code)
                    in_degree[code] += 1

        # Kahn 算法
        queue = deque([code for code, deg in in_degree.items() if deg == 0])
        sorted_codes: List[str] = []

        while queue:
            current = queue.popleft()
            sorted_codes.append(current)
            for neighbor in adjacency.get(current, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # 检查环
        if len(sorted_codes) != len(manifests):
            remaining = set(manifests.keys()) - set(sorted_codes)
            logger.error(f"DAG 检测到循环依赖! 涉及模块: {remaining}")
            # 环中模块追加到末尾（降级运行）
            sorted_codes.extend(remaining)

        return sorted_codes, missing


# ═══════════════════════════════════════════════════════════════
# 主加载器
# ═══════════════════════════════════════════════════════════════

class ModuleLoader:
    """
    Wings 3.0 模块动态加载引擎。

    使用方式:
        loader = ModuleLoader("backend/modules")
        loader.discover()   # 扫描 manifest
        loader.sort()       # 拓扑排序
        loader.load(school_id, db_session)  # 按租户启用状态加载

    熔断策略:
    - 依赖缺失 → 跳过该模块 + WARNING 日志
    - 模块加载异常 → 跳过该模块 + ERROR 日志
    - 以上两种均不影响其他模块正常运行
    """

    def __init__(self, modules_root: str):
        self.modules_root = modules_root
        self.scanner = ModuleScanner(modules_root)
        self.sorter = TopologicalSorter()

        self.manifests: Dict[str, ModuleManifest] = {}
        self.sorted_codes: List[str] = []
        self.missing_deps: Set[str] = set()

        # 加载结果
        self.results: List[LoadResult] = []
        # 已注册的路由: {module_code: (APIRouter, prefix)}
        self.registered_routers: Dict[str, Any] = {}
        # 级联配置矩阵: {module_code: {school_id: (source_level, is_enabled)}}
        self.config_matrix: Dict[str, Dict[int, tuple]] = {}

    # ── 阶段 1: 发现 ──

    def discover(self) -> Dict[str, ModuleManifest]:
        """扫描 modules/ 目录，返回所有发现的模块清单"""
        self.manifests = self.scanner.scan()
        logger.info(f"模块扫描完成: 发现 {len(self.manifests)} 个候选模块")
        return self.manifests

    # ── 阶段 2: 排序 ──

    def sort(self) -> Tuple[List[str], Set[str]]:
        """拓扑排序，返回 (有序模块列表, 缺失依赖集合)"""
        self.sorted_codes, self.missing_deps = self.sorter.sort(self.manifests)

        if self.missing_deps:
            logger.warning(f"发现 {len(self.missing_deps)} 个缺失依赖: {self.missing_deps}")

        logger.info(
            f"拓扑排序完成: {' → '.join(self.sorted_codes)}"
            if self.sorted_codes else "无模块可加载"
        )
        return self.sorted_codes, self.missing_deps

    # ── 阶段 3: 按租户加载 ──

    async def load_for_school(
        self,
        school_id: int,
        db_session,
        fastapi_app,
        enabled_module_codes: Optional[set] = None,
        resolve_configs: bool = False,
        config_school_ids: Optional[List[int]] = None,
    ) -> List[LoadResult]:
        """
        为指定学校加载已启用的模块路由。

        Args:
            school_id: 学校 ID（school_id=0 表示全局并集模式）
            db_session: 异步数据库会话（用于查询 school_modules）
            fastapi_app: FastAPI 应用实例
            enabled_module_codes: 可选，预查询的启用模块集合（避免重复 DB 查询）
            resolve_configs: 加载完成后是否解析级联配置并输出日志
            config_school_ids: 级联配置解析的目标学校列表（None=所有活跃学校）

        Returns:
            加载结果列表
        """
        self.results = []

        # 查询该学校启用的模块
        if enabled_module_codes is None:
            from core.models import SchoolModule
            from sqlalchemy import select
            result = await db_session.execute(
                select(SchoolModule.module_code).where(
                    SchoolModule.school_id == school_id,
                    SchoolModule.enabled == True,
                )
            )
            enabled_module_codes = {row[0] for row in result.all()}

        logger.info(
            f"学校 [{school_id}] 启用模块: {enabled_module_codes}"
            if enabled_module_codes else f"学校 [{school_id}] 无启用模块"
        )

        core_loaded = False

        for code in self.sorted_codes:
            manifest = self.manifests.get(code)
            if manifest is None:
                continue

            # 检查是否启用
            if code not in enabled_module_codes:
                self.results.append(LoadResult(
                    module=manifest,
                    success=False,
                    error=f"学校 [{school_id}] 未启用此模块",
                ))
                logger.debug(f"[{code}] 跳过: 学校 [{school_id}] 未启用")
                continue

            # 熔断检查: 依赖缺失
            missing_for_this = [d for d in manifest.dependencies if d in self.missing_deps]
            if missing_for_this:
                self.results.append(LoadResult(
                    module=manifest,
                    success=False,
                    dep_skipped=True,
                    dep_missing=missing_for_this,
                    error=f"依赖缺失: {missing_for_this}",
                ))
                logger.warning(f"[{code}] 熔断: 依赖缺失 {missing_for_this}")
                continue

            # 加载模块
            result = await self._load_single_module(
                manifest, fastapi_app, school_id, db_session
            )
            self.results.append(result)

            if result.success:
                core_loaded = True

        logger.info(
            f"学校 [{school_id}] 模块加载完毕: "
            f"{sum(1 for r in self.results if r.success)} 成功, "
            f"{sum(1 for r in self.results if r.dep_skipped)} 熔断, "
            f"{sum(1 for r in self.results if not r.success and not r.dep_skipped)} 未启用"
        )

        # ── 级联配置解析（可选）──
        if resolve_configs:
            await self._resolve_cascading_configs(db_session, config_school_ids)

        return self.results

    async def _load_single_module(
        self,
        manifest: ModuleManifest,
        fastapi_app,
        school_id: int,
        db_session,
    ) -> LoadResult:
        """加载单个模块：执行 manifest.register() → 注册路由"""
        try:
            # 动态导入模块的 manifest
            spec = importlib.util.spec_from_file_location(
                f"_wings_runtime_{manifest.code}",
                os.path.join(manifest.path, "manifest.py")
            )
            if spec is None or spec.loader is None:
                return LoadResult(module=manifest, success=False, error="无法解析 manifest")

            mod = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = mod
            spec.loader.exec_module(mod)

            # 调用 register() 获取路由
            register_fn = getattr(mod, "register", None)
            if register_fn is None:
                return LoadResult(module=manifest, success=False, error="manifest 缺少 register() 函数")

            router_prefix = f"/api/v1/{manifest.code}"
            result = register_fn(router_prefix=router_prefix)

            if result is None:
                return LoadResult(module=manifest, success=False, error="register() 返回 None")

            if isinstance(result, tuple) and len(result) == 2:
                router, prefix = result
            else:
                router = result
                prefix = router_prefix

            # 注册到 FastAPI（学段隔离闸：若模块声明了 MODULE_PHASES，自动注入 phase guard）
            deps = []
            if manifest.phases:
                from core.routers import require_school_phase
                from fastapi import Depends as FastAPIDepends
                phase_guard = require_school_phase(manifest.phases)
                deps = [FastAPIDepends(phase_guard)]
                logger.info(
                    f"[{manifest.code}] 🔒 学段隔离已激活: {manifest.phases}"
                )

            fastapi_app.include_router(router, prefix=prefix, dependencies=deps)

            self.registered_routers[manifest.code] = (router, prefix)
            logger.info(f"[{manifest.code}] ✓ 已注册: {prefix}")

            return LoadResult(module=manifest, success=True)

        except Exception as e:
            logger.error(f"[{manifest.code}] 加载失败: {e}", exc_info=True)
            return LoadResult(module=manifest, success=False, error=str(e))

    # ── 级联配置解析 ──

    async def _resolve_cascading_configs(
        self,
        db_session,
        school_ids: Optional[List[int]] = None,
    ) -> None:
        """
        为所有已加载模块解析级联配置，输出 School→Branch→Org→Default 查找链日志。

        Args:
            db_session: 异步数据库会话
            school_ids: 目标学校 ID 列表（None=所有活跃学校）
        """
        from core.tenant_context import get_effective_config_with_source
        from core.models import School
        from sqlalchemy import select

        # 获取学校列表
        if school_ids is None:
            result = await db_session.execute(
                select(School.id, School.name).where(School.is_active == True)
            )
            schools = result.all()
        else:
            result = await db_session.execute(
                select(School.id, School.name).where(School.id.in_(school_ids))
            )
            schools = result.all()

        school_map = {sid: sname for sid, sname in schools}
        self.config_matrix = {}

        logger.info(f"级联配置解析开始: {len(schools)} 所学校 × {len(self.registered_routers)} 个已加载模块")

        for code in self.sorted_codes:
            if code not in self.registered_routers:
                continue

            self.config_matrix[code] = {}
            parts = []

            for sid, _ in schools:
                config, source = await get_effective_config_with_source(
                    code, sid, db_session
                )
                is_on = config.get("enabled", False)
                self.config_matrix[code][sid] = (source, is_on)

                sname = school_map.get(sid, f"school_{sid}")
                parts.append(f"{sname}={source}:{'ON' if is_on else 'OFF'}")

                # 回写到对应 LoadResult
                for r in self.results:
                    if r.module.code == code and r.success:
                        r.config_level = source
                        r.config_enabled = is_on

            logger.info(f"  级联配置 [{code}]: {', '.join(parts)}")

        logger.info("级联配置解析完成")

    def get_config_matrix(self) -> Dict[str, Dict[int, tuple]]:
        """
        返回级联配置矩阵: {module_code: {school_id: (source_level, is_enabled)}}

        在 load_for_school(resolve_configs=True) 之后调用。
        """
        return self.config_matrix

    # ── 工具方法 ──

    def get_load_report(self) -> str:
        """生成加载报告（人类可读）"""
        lines = ["=" * 60, "  Wings 3.0 模块加载报告", "=" * 60]

        for r in self.results:
            status = "OK" if r.success else ("FUSE" if r.dep_skipped else "SKIP")
            line = f"  [{status}] {r.module.code:<20} {r.module.name}"
            if r.success and r.config_level:
                on = "ON" if r.config_enabled else "OFF"
                line += f"  config={r.config_level}:{on}"
            lines.append(line)
            if r.error:
                lines.append(f"       原因: {r.error}")
            if r.dep_missing:
                lines.append(f"       缺失依赖: {', '.join(r.dep_missing)}")

        total = len(self.results)
        ok = sum(1 for r in self.results if r.success)
        skipped = sum(1 for r in self.results if r.dep_skipped)
        disabled = sum(1 for r in self.results if not r.success and not r.dep_skipped)

        lines.append("-" * 60)
        lines.append(f"  总计: {total} | 已加载: {ok} | 熔断: {skipped} | 未启用: {disabled}")
        lines.append("=" * 60)

        return "\n".join(lines)
