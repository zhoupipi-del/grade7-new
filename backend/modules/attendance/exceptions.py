"""
modules/attendance/exceptions.py — 考勤模块领域异常体系

斩断 HTTPException 的"长臂管辖"：
- Service 层只抛出领域异常
- Router 层 / 全局异常处理器负责映射到 HTTP 状态码
- 异步任务（Celery 等）可优雅捕获业务异常，无需依赖 HTTP 上下文
"""


class AttendanceError(Exception):
    """考勤模块基础异常"""
    def __init__(self, message: str, http_status: int = 400):
        super().__init__(message)
        self.http_status = http_status


class StudentLeaveConflictError(AttendanceError):
    """请假时间冲突 — 同一学生存在时间重叠的已批准/审批中请假"""
    def __init__(self, existing_start: str = "", existing_end: str = "", existing_status: str = ""):
        msg = (
            f"该学生已有时间重叠的请假申请 "
            f"({existing_start} ~ {existing_end}, 状态: {existing_status})"
        )
        super().__init__(msg, http_status=409)


class ScopePermissionDeniedError(AttendanceError):
    """越权访问 — 用户角色无权查看/操作目标数据范围"""
    def __init__(self, message: str = "无权访问该数据范围"):
        super().__init__(message, http_status=403)


class NoPermissionError(AttendanceError):
    """操作权限不足 — 用户角色无权执行该操作"""
    def __init__(self, message: str = "无权执行此操作"):
        super().__init__(message, http_status=403)


class InvalidStatusError(AttendanceError):
    """无效考勤状态值"""
    def __init__(self, status: str):
        super().__init__(f"无效考勤状态: {status}", http_status=400)


class LeaveNotFoundError(AttendanceError):
    """请假申请不存在"""
    def __init__(self, leave_id: int):
        super().__init__(f"请假申请不存在: {leave_id}", http_status=404)


class DateRangeError(AttendanceError):
    """日期范围错误"""
    def __init__(self, message: str = "结束日期不能早于开始日期"):
        super().__init__(message, http_status=400)
