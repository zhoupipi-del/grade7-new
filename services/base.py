"""多租户基类与服务基类

SchoolMixin — 为所有数据模型注入 school_id，实现物理级多租户隔离。
  设计原则:
  - school_id 默认值 1（当前梨江中学），向后兼容，零改动
  - 新学校接入时只需 INSERT 一条 School 记录，所有查询自动带 school_id
  - 不强制重构现有模型，渐进式迁移

BaseService — 服务层统一基类。
  提供: school_id 注入 / 事务管理 / 统一日志 / 批量查询优化
"""

import logging
from models import db
from utils import get_local_now

logger = logging.getLogger(__name__)


class SchoolMixin:
    """多租户基因 — 混入任意 db.Model 即可获得 school_id 隔离能力。

    用法:
      class Attendance(SchoolMixin, db.Model):
          __tablename__ = "attendance"
          ...
          school_id = SchoolMixin.school_id  # 或直接用继承

    注意:
      - 这是一个纯 Mixin，不继承 db.Model
      - school_id 默认 1 = 梨江中学（现有数据不受影响）
      - 未来多校时，每个请求通过 session["school_id"] 注入
    """

    school_id = db.Column(db.Integer, nullable=False, default=1, index=True,
                          comment="学校ID (1=梨江中学, 多租户隔离键)")

    @classmethod
    def by_school(cls, school_id=1):
        """按学校过滤的快捷查询入口。

        Example:
          Attendance.by_school(school_id=1).filter_by(student_id=42).all()
        """
        return cls.query.filter_by(school_id=school_id)

    @classmethod
    def for_school(cls, school_id):
        """返回当前学校的 scoped_query（兼容旧 scope_query 约定）。

        Example:
          q = Attendance.for_school(school_id)
          q = q.filter(Attendance.record_date >= start_date)
          return q.all()
        """
        return cls.query.filter(cls.school_id == school_id)


class BaseService:
    """服务层统一基类。

    职责:
      1. 持有当前请求的 school_id（从 session 注入）
      2. 提供统一的事务安全提交方法
      3. 标准化日志输出
      4. 批量查询优化入口

    使用模式:
      svc = AttendanceService(school_id=session.get("school_id", 1))
      result = svc.get_today_attendance(class_id=5)
    """

    def __init__(self, school_id=1):
        self.school_id = school_id
        self.logger = logging.getLogger(self.__class__.__name__)

    # ── 事务管理 ──
    def commit(self):
        """安全提交，失败时回滚并记录详细日志。"""
        try:
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            self.logger.error(
                "[%s] 事务提交失败 school_id=%d | %s",
                self.__class__.__name__, self.school_id, exc,
                exc_info=True
            )
            raise RuntimeError(f"数据保存失败: {exc}") from exc

    # ── 批量加载优化入口 ──
    @staticmethod
    def batch_load(model_class, id_list, school_id=None):
        """批量预加载，消灭 N+1 查询。

        Example:
          student_map = BaseService.batch_load(Student, [1, 2, 3])
          for record in records:
              s = student_map.get(record.student_id)  # 零查询
        """
        if not id_list:
            return {}
        q = model_class.query.filter(model_class.id.in_(id_list))
        if school_id is not None:
            q = q.filter(model_class.school_id == school_id)
        items = q.all()
        return {item.id: item for item in items}

    @staticmethod
    def multi_key_cache(items, *key_attrs):
        """多键缓存 — 按属性元组索引。

        Example:
          cache = BaseService.multi_key_cache(scores, "student_id", "subject_id")
          score = cache.get((student_id, subject_id))
        """
        cache = {}
        for item in items:
            key = tuple(getattr(item, attr) for attr in key_attrs)
            cache[key] = item
        return cache

    @staticmethod
    def now():
        """统一时间源 — 必须用 get_local_now，禁止 datetime.utcnow()。"""
        return get_local_now()


# ── 全局响应封装（为 Phase 1 Step 3 统一接口契约准备）──
def success_api(data=None, msg="ok", code=0):
    """统一成功响应。

    Returns:
        {"code": 0, "msg": "ok", "data": ...}
    """
    return {"code": code, "msg": msg, "data": data}


def error_api(msg="操作失败", code=1, http_status=200):
    """统一错误响应 — 返回 dict，调用方自行 jsonify。

    注意: 不在此处直接 jsonify，保持与 Flask 蓝图返回值的兼容性。
    """
    return {"code": code, "msg": msg, "data": None}
