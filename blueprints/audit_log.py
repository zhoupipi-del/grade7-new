"""审计日志装饰器 — AOP方式记录关键操作"""

from functools import wraps
from flask import session, request
from datetime import datetime
from models import db, AuditLog


def _write_audit_log(action, target_type=None, target_id=None, detail=None):
    """写入一条审计日志（内部函数，失败不影响主流程）"""
    try:
        entry = AuditLog(
            username=session.get("username", "unknown"),
            action=action,
            target_type=target_type or "",
            target_id=target_id or 0,
            detail=detail or "",
        )
        db.session.add(entry)
        db.session.commit()
    except Exception:
        pass  # 审计日志失败不影响主流程


def audit_log(action, target_type=None):
    """审计日志装饰器

    用法:
        @audit_log("delete_student", "Student")
        def delete_student(sid):
            ...

        @audit_log("approve_leave")
        def approve_leave(lid):
            ...
    """
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            # 从参数中尝试提取 target_id
            target_id = None
            if args:
                target_id = args[0]  # 通常第一个参数是ID
            elif kwargs:
                # 取第一个值
                target_id = next(iter(kwargs.values()), None)

            result = f(*args, **kwargs)

            # 记录审计日志
            _write_audit_log(
                action=action,
                target_type=target_type,
                target_id=target_id,
            )
            return result
        return wrapper
    return decorator
