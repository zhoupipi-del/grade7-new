"""
权限守卫检查脚本 — 扫描所有蓝图，检查是否都有权限保护

使用方法：
    cd /opt/grade7-new
    python3 scripts/check_permission_guards.py

输出：
    - 没有被任何权限装饰器保护的路由 → 高危！
    - 只被 login_required 保护但缺少 require_role/require_permission 的路由 → 中危
    - 建议添加的权限装饰器
"""

import ast
import os
import sys
from pathlib import Path

# ── 配置 ──

# 需要检查的蓝图目录
BLUEPRINT_DIR = Path(__file__).parent.parent / "blueprints"

# 排除的文件（如 __init__.py、decorators.py 等）
EXCLUDE_FILES = {
    "__init__.py",
    "decorators.py",
    "blueprint_registry.py",
}

# 公共路由（不需要权限检查，如登录、公开API等）
PUBLIC_ROUTE_KEYWORDS = {
    "login", "logout", "register", "public", "static",
    "health", "ping", "webhook",
}


# ── 检查逻辑 ──

def is_public_route(route_path):
    """判断是否是公共路由（不需要权限）"""
    path_lower = route_path.lower()
    return any(kw in path_lower for kw in PUBLIC_ROUTE_KEYWORDS)


def check_file(filepath):
    """
    检查单个文件中的路由定义。
    返回：(file_path, routes_without_guard, routes_with_only_login)
    """
    with open(filepath, "r", encoding="utf-8") as f:
        source = f.read()
    
    tree = ast.parse(source)
    
    results = []
    
    # 遍历所有函数定义
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        
        # 检查是否有路由装饰器（@bp.route 或 @app.route）
        route_decorators = []
        other_decorators = []
        
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Call):
                if isinstance(decorator.func, ast.Attribute):
                    if decorator.func.attr == "route":
                        route_decorators.append(decorator)
                elif isinstance(decorator.func, ast.Name):
                    if decorator.func.id in (
                        "login_required",
                        "require_role",
                        "require_permission",
                        "require_any_permission",
                        "require_all_permissions",
                    ):
                        other_decorators.append(decorator.func.id)
        
        # 如果没有路由装饰器，跳过
        if not route_decorators:
            continue
        
        # 检查权限装饰器
        has_login = "login_required" in other_decorators
        has_role = "require_role" in other_decorators
        has_permission = "require_permission" in other_decorators
        has_any_permission = "require_any_permission" in other_decorators
        has_all_permissions = "require_all_permissions" in other_decorators
        
        # 获取路由路径（从第一个 route 装饰器）
        route_path = None
        if route_decorators:
            first_route = route_decorators[0]
            if first_route.args:
                route_path = first_route.args[0].value
        
        # 判断风险等级
        if not has_login and not has_role and not has_permission:
            risk = "HIGH"  # 完全没有权限保护
        elif has_login and not has_role and not has_permission:
            risk = "MEDIUM"  # 只有登录检查，缺少角色/权限检查
        else:
            risk = "LOW"  # 已有完整保护
        
        results.append({
            "function": node.name,
            "route_path": route_path,
            "risk": risk,
            "has_login": has_login,
            "has_role": has_role,
            "has_permission": has_permission,
            "decorators": other_decorators,
        })
    
    return filepath, results


def scan_all_blueprints():
    """扫描所有蓝图文件"""
    all_results = []
    
    for py_file in BLUEPRINT_DIR.glob("*.py"):
        if py_file.name in EXCLUDE_FILES:
            continue
        
        filepath, results = check_file(py_file)
        
        # 只保留有风险的路由
        risky = [r for r in results if r["risk"] in ("HIGH", "MEDIUM")]
        
        if risky:
            all_results.append((filepath, risky))
    
    return all_results


def generate_report(results):
    """生成检查报告"""
    lines = []
    lines.append("# 权限守卫检查报告")
    lines.append("")
    lines.append(f"生成时间: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    
    # 统计
    high_count = sum(len([r for r in rs if r["risk"] == "HIGH"]) for _, rs in results)
    medium_count = sum(len([r for r in rs if r["risk"] == "MEDIUM"]) for _, rs in results)
    
    lines.append("## 统计")
    lines.append(f"- 🔴 高危（无权限保护）: {high_count} 个路由")
    lines.append(f"- 🟡 中危（仅有登录检查）: {medium_count} 个路由")
    lines.append("")
    
    if not results:
        lines.append("✅ **所有蓝图都已正确添加权限守卫！**")
        return "\n".join(lines)
    
    # 详细报告
    lines.append("## 详细报告")
    lines.append("")
    
    for filepath, routes in results:
        rel_path = filepath.relative_to(BLUEPRINT_DIR.parent)
        lines.append(f"### {rel_path}")
        lines.append("")
        
        for route in routes:
            risk_emoji = "🔴" if route["risk"] == "HIGH" else "🟡"
            lines.append(f"{risk_emoji} **`{route['function']}`**")
            
            if route["route_path"]:
                lines.append(f"   - 路径: `{route['route_path']}`")
            
            lines.append(f"   - 风险: `{route['risk']}`")
            lines.append(f"   - 当前装饰器: `{route['decorators']}`")
            
            # 建议
            if route["risk"] == "HIGH":
                lines.append(f"   - **建议**: 添加 `@require_role(...)` 或 `@require_permission(...)`")
            elif route["risk"] == "MEDIUM":
                lines.append(f"   - **建议**: 添加 `@require_role(...)` 或 `@require_permission(...)`")
            
            lines.append("")
    
    # 修复建议
    lines.append("## 修复建议")
    lines.append("")
    lines.append("### 方式1：使用装饰器（推荐，灵活性高）")
    lines.append("")
    lines.append("```python")
    lines.append("from decorators import login_required, require_role, require_permission")
    lines.append("")
    lines.append("@bp.route('/some-route')")
    lines.append("@login_required")
    lines.append("@require_role('ms_admin', 'grade_leader')  # 按角色控制")
    lines.append("def my_view():")
    lines.append("    ...")
    lines.append("")
    lines.append("# 或者按权限控制（更细粒度）")
    lines.append("@bp.route('/some-route')")
    lines.append("@require_permission('manage_discipline')")
    lines.append("def my_view():")
    lines.append("    ...")
    lines.append("```")
    lines.append("")
    lines.append("### 方式2：使用蓝图级 before_request（适合整站统一权限）")
    lines.append("")
    lines.append("```python")
    lines.append("from decorators import protect_blueprint")
    lines.append("")
    lines.append("# 在蓝图文件末尾添加：")
    lines.append("protect_blueprint(my_bp, 'manage_discipline')")
    lines.append("```")
    lines.append("")
    
    return "\n".join(lines)


def main():
    print("🔍 开始扫描所有蓝图文件...")
    print(f"📂 扫描目录: {BLUEPRINT_DIR}")
    print("")
    
    results = scan_all_blueprints()
    
    report = generate_report(results)
    
    # 输出到控制台
    print(report)
    print("")
    
    # 保存到文件
    output_path = Path(__file__).parent / "permission_guard_report.md"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)
    
    print(f"📄 报告已保存到: {output_path}")
    print("")
    
    # 退出码：如果发现高危路由，返回1
    high_count = sum(len([r for r in rs if r["risk"] == "HIGH"]) for _, rs in results)
    if high_count > 0:
        print(f"⚠️  发现 {high_count} 个高危路由（无任何权限保护）")
        sys.exit(1)
    else:
        print("✅ 未发现高危路由")
        sys.exit(0)


if __name__ == "__main__":
    main()
