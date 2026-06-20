"""梨江中学德育管理平台 — 业务服务层

服务层职责：
  1. 封装数据库 CRUD 逻辑（替代蓝图中的内嵌 ORM 调用）
  2. 注入 school_id 多租户隔离（为多校 SaaS 奠基）
  3. 统一异常处理与日志
  4. 暴露可复用的业务方法给蓝图/API/定时任务

使用模式：
  # 蓝图中
  from services.attendance_service import AttendanceService
  result = AttendanceService.get_class_attendance(class_id, school_id=session.get("school_id", 1))
"""

from services.base import SchoolMixin, BaseService

__all__ = ["SchoolMixin", "BaseService"]
