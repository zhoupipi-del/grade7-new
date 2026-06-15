#!/usr/bin/env python3
"""
测试脚本：检查 search 蓝图是否真的注册到 Flask 应用
"""
import sys
import os

# 添加项目根目录到 sys.path
sys.path.insert(0, "/opt/grade7-new")

# 从 systemd service 文件读取环境变量
service_file = "/etc/systemd/system/grade7-new.service"
if os.path.exists(service_file):
    with open(service_file, "r") as f:
        for line in f:
            if line.startswith("Environment="):
                # 解析 Environment="KEY=VALUE" 格式
                env_str = line.split("=", 1)[1].strip().strip('"')
                if "=" in env_str:
                    key, value = env_str.split("=", 1)
                    os.environ[key.strip()] = value.strip()

# 切换到应用目录
os.chdir("/opt/grade7-new")

# 导入并创建应用
from app import create_app

app = create_app()

# 检查 /search 开头的路由
print("=" * 60)
print("Flask 应用中的 /search 路由：")
print("=" * 60)

found = False
for rule in app.url_map.iter_rules():
    if str(rule).startswith('/search'):
        methods = getattr(rule, 'methods', set())
        print(f"  {list(methods)} {rule}")
        found = True

if not found:
    print("  ❌ 未找到任何 /search 开头的路由！")

print()
print("=" * 60)
print("所有蓝图列表：")
print("=" * 60)
for bp_name, bp in app.blueprints.items():
    print(f"  - {bp_name}: {bp}")
