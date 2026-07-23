#!/usr/bin/env python3
"""Wings 3 安全补丁静态回归检查。无需连接数据库或启动应用。"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"

errors: list[str] = []


def text(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# 1. 全仓 Python 语法树检查
for path in BACKEND.rglob("*.py"):
    if any(part.startswith(".venv") for part in path.parts):
        continue
    try:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        errors.append(f"语法错误: {path.relative_to(ROOT)}: {exc}")

# 2. 已确认漏洞的静态回归断言
app = text("backend/app.py")
if "admin / {admin_pw}" in app:
    errors.append("默认管理员密码仍写入日志")
if "INITIAL_ADMIN_PASSWORD" not in app:
    errors.append("首次管理员密码未改为安全环境变量注入")

auth = text("backend/core/services.py")
for marker in ["bcrypt.hashpw", "bcrypt.checkpw", "password_needs_rehash", 'startswith("sha256$")']:
    if marker not in auth:
        errors.append(f"密码双轨迁移缺失: {marker}")

webhook = text("backend/modules/discipline/routers.py")
if "change-me-in-production" in webhook:
    errors.append("Webhook 仍包含默认密钥")
if "hmac.compare_digest" not in webhook or '.encode("utf-8")' not in webhook:
    errors.append("Webhook 未使用 bytes + compare_digest")

psych_service = text("backend/modules/psych_counseling/services.py")
if "TeacherRoleAssignment.user_id" in psych_service:
    errors.append("心理咨询 counselor 查询仍引用不存在的 user_id")
if "TeacherRoleAssignment.teacher_user_id" not in psych_service:
    errors.append("心理咨询 counselor 查询未使用 teacher_user_id")
if "allowed_student_ids" not in psych_service:
    errors.append("心理咨询服务层缺少学生归属过滤")

psych_router = text("backend/modules/psych_counseling/routers.py")
for marker in ["_allowed_student_ids", "_assert_student_access", "student_ids=allowed_student_ids"]:
    if marker not in psych_router:
        errors.append(f"心理咨询路由归属守卫缺失: {marker}")

reports_router = text("backend/modules/reports/routers.py")
for marker in ["Depends(get_current_user)", "download_task_report", "FileResponse"]:
    if marker not in reports_router:
        errors.append(f"报告鉴权下载缺失: {marker}")

reports_task = text("backend/modules/reports/tasks.py")
if "/root/backend/static/exports/reports" in reports_task:
    errors.append("报告仍默认写入公开静态目录")
if '"school_id": school_id' not in reports_task or '"created_by": created_by' not in reports_task:
    errors.append("报告任务结果缺少归属元数据")

ai_router = text("backend/modules/ai_prescription/routers.py")
if "AIPrescription.school_id == current_user.school_id" not in ai_router:
    errors.append("AI 任务状态缺少学校归属校验")

feedback = text("backend/modules/parent_portal/services.py")
if "feedback.school_id != current_user.school_id" not in feedback:
    errors.append("家长反馈详情缺少跨校隔离")

models = text("backend/core/models.py")
schemas = text("backend/core/schemas.py")
if 'COUNSELOR = "counselor"' not in models or 'COUNSELOR = "counselor"' not in schemas:
    errors.append("COUNSELOR 角色枚举未对齐")

if (BACKEND / ".venv_migration").exists():
    errors.append("交付包仍包含 .venv_migration")

if errors:
    print("SECURITY PATCH VERIFY: FAIL")
    for item in errors:
        print(f"- {item}")
    sys.exit(1)

print("SECURITY PATCH VERIFY: PASS")
