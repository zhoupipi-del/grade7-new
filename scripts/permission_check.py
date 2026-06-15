#!/usr/bin/env python3
"""
数据权限一致性检查脚本
检查所有蓝图、路由、API的权限装饰器是否一致
输出Markdown格式的报告
"""
import sys
import os
import re
from collections import defaultdict
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/..')

try:
    from app import create_app
    app = create_app()
except:
    print("警告：无法导入Flask app，将只进行静态代码分析")
    app = None

report = []
routes_info = []

def check_file_permissions(filepath):
    """检查单个文件的权限装饰器"""
    issues = []
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except:
        return issues
    
    # 查找所有路由定义
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # 找到路由定义
        route_match = re.search(r'@\w+_bp\.route\("([^"]+)"', line)
        if route_match:
            route_path = route_match.group(1)
            
            # 向前查找@require_role装饰器
            has_login = False
            has_require_role = False
            roles = []
            
            # 检查前10行（装饰器通常在路由上方）
            for j in range(max(0, i-10), i):
                if '@login_required' in lines[j]:
                    has_login = True
                if '@require_role' in lines[j]:
                    has_require_role = True
                    # 提取角色
                    role_match = re.search(r'@require_role\(([^)]+)\)', lines[j])
                    if role_match:
                        roles_str = role_match.group(1)
                        # 解析角色列表
                        roles = [r.strip().strip('"\'') for r in roles_str.split(',')]
            
            # 检查问题
            if not has_login and not has_require_role:
                issues.append({
                    'route': route_path,
                    'severity': 'HIGH',
                    'issue': '缺少权限验证（既无@login_required也无@require_role）',
                    'line': i + 1,
                })
            elif has_login and not has_require_role:
                # 只有@login_required，没有具体角色限制
                issues.append({
                    'route': route_path,
                    'severity': 'MEDIUM',
                    'issue': '只有@login_required，未限制具体角色（可能权限过宽）',
                    'line': i + 1,
                })
            
            routes_info.append({
                'file': os.path.basename(filepath),
                'route': route_path,
                'has_login': has_login,
                'has_require_role': has_require_role,
                'roles': roles,
                'line': i + 1,
            })
        
        i += 1
    
    return issues

def generate_permission_matrix():
    """生成权限矩阵"""
    matrix = defaultdict(lambda: defaultdict(list))
    
    for r in routes_info:
        route = r['route']
        roles = r['roles'] if r['has_require_role'] else ['any_logged_in']
        
        for role in roles:
            matrix[role].append(route)
    
    return matrix

def main():
    print("=" * 70)
    print("  梨江中学德育管理平台 · 数据权限一致性检查")
    print("=" * 70)
    print()
    
    # 扫描blueprints目录
    blueprints_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'blueprints')
    blueprints_dir = os.path.normpath(blueprints_dir)
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 扫描蓝图目录: {blueprints_dir}")
    print()
    
    all_issues = []
    scanned_files = 0
    
    for filename in sorted(os.listdir(blueprints_dir)):
        if filename.endswith('.py'):
            filepath = os.path.join(blueprints_dir, filename)
            print(f"  扫描: {filename}...")
            
            issues = check_file_permissions(filepath)
            all_issues.extend([(filename, i) for i in issues])
            scanned_files += 1
            
            if issues:
                print(f"    ⚠️  发现 {len(issues)} 个问题")
            else:
                print(f"    ✅ 通过")
    
    print()
    print("=" * 70)
    print("  权限检查报告")
    print("=" * 70)
    print()
    
    # 按严重程度分组
    high_issues = [(f, i) for f, i in all_issues if i['severity'] == 'HIGH']
    medium_issues = [(f, i) for f, i in all_issues if i['severity'] == 'MEDIUM']
    
    print(f"总问题数: {len(all_issues)}")
    print(f"  🔴 高优先级: {len(high_issues)}")
    print(f"  🟡 中优先级: {len(medium_issues)}")
    print()
    
    if high_issues:
        print("🔴 高优先级问题（必须修复）:")
        print("-" * 70)
        for filename, issue in high_issues:
            print(f"  [{issue['severity']}] {filename}:{issue['line']}")
            print(f"    路由: {issue['route']}")
            print(f"    问题: {issue['issue']}")
            print()
    
    if medium_issues:
        print("🟡 中优先级问题（建议修复）:")
        print("-" * 70)
        for filename, issue in medium_issues:
            print(f"  [{issue['severity']}] {filename}:{issue['line']}")
            print(f"    路由: {issue['route']}")
            print(f"    问题: {issue['issue']}")
            print()
    
    # 生成权限矩阵
    print("=" * 70)
    print("  权限矩阵（哪个角色能访问哪些路由）")
    print("=" * 70)
    print()
    
    matrix = generate_permission_matrix()
    
    for role in sorted(matrix.keys()):
        routes = matrix[role]
        print(f"## {role}")
        print()
        for route in sorted(routes)[:10]:  # 只显示前10个
            print(f"  - {route}")
        if len(routes) > 10:
            print(f"  ... 共 {len(routes)} 个路由")
        print()
    
    # 保存报告到文件
    report_file = f"permission_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write("# 梨江中学德育管理平台 · 数据权限一致性检查报告\n\n")
        f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"扫描文件数: {scanned_files}\n")
        f.write(f"总问题数: {len(all_issues)}\n")
        f.write(f"- 高优先级: {len(high_issues)}\n")
        f.write(f"- 中优先级: {len(medium_issues)}\n\n")
        
        if high_issues:
            f.write("## 🔴 高优先级问题\n\n")
            for filename, issue in high_issues:
                f.write(f"### [{issue['severity']}] {filename}:{issue['line']}\n\n")
                f.write(f"- 路由: `{issue['route']}`\n")
                f.write(f"- 问题: {issue['issue']}\n\n")
        
        if medium_issues:
            f.write("## 🟡 中优先级问题\n\n")
            for filename, issue in medium_issues:
                f.write(f"### [{issue['severity']}] {filename}:{issue['line']}\n\n")
                f.write(f"- 路由: `{issue['route']}`\n")
                f.write(f"- 问题: {issue['issue']}\n\n")
        
        f.write("## 权限矩阵\n\n")
        for role in sorted(matrix.keys()):
            routes = matrix[role]
            f.write(f"### {role}\n\n")
            for route in sorted(routes):
                f.write(f"- `{route}`\n")
            f.write("\n")
    
    print(f"报告已保存到: {report_file}")
    print()
    print("=" * 70)
    
    if len(all_issues) == 0:
        print("✅ 恭喜！未发现权限一致性问题。")
    else:
        print(f"⚠️  发现 {len(all_issues)} 个权限问题，请修复。")
    print("=" * 70)

if __name__ == '__main__':
    main()
