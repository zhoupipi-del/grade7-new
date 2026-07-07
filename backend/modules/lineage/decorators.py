"""
modules/lineage/decorators.py — 零侵入审计装饰器

提供两层装饰器：

1. @audit_lineage — 零侵入血缘追踪装饰器
   自动捕获函数调用参数和返回值，写入 lineage_events 表，
   实现跨模块数据血缘追踪。

2. @audit_score_log — 轻量级审计装饰器 (#1193)
   从函数 kwargs 提取操作者信息，设置审计 ContextVar，
   为 ScoreLog 的 actor_id / source_ip / trace_context_id / diff_snapshot 提供数据源。

使用 ContextVar 传播 trace_id，支持嵌套调用链自动串联：
  record_score() → recalculate_snapshot() → StudentScore
  以上三次调用共享同一个 trace_id。

设计原则：
  1. 绝对不阻断主流程 — lineage 记录失败时静默忽略
  2. ContextVar 传播 trace_id — 无需显式传参
  3. 自动提取 student_id/school_id — 从函数参数中推断
"""

import json
import uuid
import logging
from contextvars import ContextVar
from functools import wraps
from typing import Optional, Callable, Any, Dict, List

logger = logging.getLogger("lineage.decorators")

# ═══════════════════════════════════════════════════════════
# ContextVar — 线程安全的 trace_id 传播
# ═══════════════════════════════════════════════════════════

_current_trace_id: ContextVar[Optional[str]] = ContextVar(
    "lineage_trace_id", default=None
)
_current_lineage_depth: ContextVar[int] = ContextVar(
    "lineage_depth", default=0
)


def get_current_trace_id() -> Optional[str]:
    """获取当前上下文中的 trace_id（用于手动记录血缘）"""
    return _current_trace_id.get()


def set_trace_context(trace_id: Optional[str] = None, depth: int = 0):
    """设置血缘追踪上下文 — 由 HTTP middleware 或手动调用"""
    tid = trace_id or str(uuid.uuid4())
    _current_trace_id.set(tid)
    _current_lineage_depth.set(depth)


def clear_trace_context():
    """清除血缘追踪上下文"""
    _current_trace_id.set(None)
    _current_lineage_depth.set(0)


# ═══════════════════════════════════════════════════════════
# #1193 审计上下文 ContextVars — 为 ScoreLog 新字段提供数据源
# ═══════════════════════════════════════════════════════════

_current_actor_id: ContextVar[Optional[int]] = ContextVar(
    "audit_actor_id", default=None
)
_current_source_ip: ContextVar[Optional[str]] = ContextVar(
    "audit_source_ip", default=None
)


def get_audit_context() -> dict:
    """
    获取当前审计上下文 — 用于 ScoreLog 的 4 个血缘增强字段。

    Returns:
        {
            "actor_id": int or None,       # 实际操作者 ID
            "source_ip": str or None,      # 操作来源 IP
            "trace_context_id": str or None,  # 关联 LineageEvent.trace_id
        }

    用法（在 Service 层 ScoreLog 创建处）:
        ctx = get_audit_context()
        score_log = ScoreLog(
            ...
            actor_id=ctx["actor_id"],
            source_ip=ctx["source_ip"],
            trace_context_id=ctx["trace_context_id"],
        )
    """
    return {
        "actor_id": _current_actor_id.get(),
        "source_ip": _current_source_ip.get(),
        "trace_context_id": _current_trace_id.get(),
    }


def set_audit_context(
    actor_id: Optional[int] = None,
    source_ip: Optional[str] = None,
):
    """
    设置审计上下文 — 由 @audit_score_log 装饰器或 HTTP middleware 调用。

    Args:
        actor_id: 实际操作者 ID
        source_ip: 操作来源 IP 地址
    """
    if actor_id is not None:
        _current_actor_id.set(actor_id)
    if source_ip is not None:
        _current_source_ip.set(source_ip)


# ═══════════════════════════════════════════════════════════
# 装饰器
# ═══════════════════════════════════════════════════════════

def audit_lineage(
    transformation: str,
    source_type: str = "",
    target_type: str = "",
    extract_context: Optional[Callable] = None,
):
    """
    零侵入审计装饰器 — 自动记录数据血缘

    Args:
        transformation: 转换类型标识 (如 "recalculate_snapshot")
        source_type: 源实体类型的默认值
        target_type: 目标实体类型的默认值
        extract_context: (result, *args, **kwargs) -> dict 自定义上下文提取

    用法:
        @audit_lineage("recalculate_snapshot", "evaluation_score", "student_score")
        async def recalculate_snapshot(db, student_id, school_id, semester):
            ...

    嵌套调用链自动串联:
        当被装饰函数内部调用另一个被装饰函数时，trace_id 自动继承，
        lineage_depth 自动递增，形成完整的因果链。
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            from modules.lineage.models import LineageEvent

            # Step 1: 获取/创建 trace_id
            parent_trace = _current_trace_id.get()
            if parent_trace:
                # 嵌套调用 — 继承父 trace_id, 深度 +1
                trace_id = parent_trace
                depth = _current_lineage_depth.get() + 1
                _current_lineage_depth.set(depth)
            else:
                # 顶层调用 — 创建新 trace_id
                trace_id = str(uuid.uuid4())
                depth = 0
                _current_trace_id.set(trace_id)
                _current_lineage_depth.set(0)

            # Step 2: 执行原函数
            result = None
            try:
                result = await func(*args, **kwargs)
            finally:
                # 恢复上下文（仅在顶层调用时清理）
                if not parent_trace:
                    _current_trace_id.set(None)
                    _current_lineage_depth.set(0)
                elif parent_trace:
                    _current_lineage_depth.set(depth - 1)

            # Step 3: 静默记录血缘事件
            if result is not None:
                await _record_lineage_event(
                    func=func,
                    args=args,
                    kwargs=kwargs,
                    result=result,
                    trace_id=trace_id,
                    depth=depth,
                    transformation=transformation,
                    source_type=source_type,
                    target_type=target_type,
                    extract_context=extract_context,
                )

            return result

        return wrapper
    return decorator


async def _record_lineage_event(
    func,
    args,
    kwargs,
    result,
    trace_id: str,
    depth: int,
    transformation: str,
    source_type: str,
    target_type: str,
    extract_context: Optional[Callable],
):
    """静默记录一条血缘事件 — 失败不影响主流程"""
    from modules.lineage.models import LineageEvent

    try:
        # 提取 db session — 通常是第一个位置参数
        db = None
        for a in args:
            # 检查是否有 add/flush 方法（AsyncSession 特征）
            if hasattr(a, 'add') and hasattr(a, 'flush'):
                db = a
                break
        if db is None:
            db = kwargs.get('db')

        if db is None:
            return  # 没有 db session，无法记录

        # 提取 source_id / source_batch — 从 kwargs 或 extract_context
        sid = None
        sbatch = None
        stu_id = None
        sch_id = None

        # 从参数中提取常见字段
        for key in ('source_id', 'discipline_id', 'behavior_record_id'):
            if key in kwargs and kwargs[key]:
                sid = kwargs[key]
                break
        for key in ('student_id',):
            if key in kwargs and kwargs[key]:
                stu_id = kwargs[key]
                break
        for key in ('school_id',):
            if key in kwargs and kwargs[key]:
                sch_id = kwargs[key]
                break

        # 自定义上下文提取
        ctx = {}
        if extract_context:
            try:
                ctx = extract_context(result, *args, **kwargs) or {}
            except Exception:
                pass
        else:
            # 默认上下文：捕获关键参数
            ctx = _default_extract_context(args, kwargs, result)

        # 覆盖/补充 source_type/target_type
        st = ctx.pop('_source_type', source_type)
        tt = ctx.pop('_target_type', target_type)
        sid = ctx.pop('_source_id', sid) or sid
        stu_id = ctx.pop('_student_id', stu_id) or stu_id
        sch_id = ctx.pop('_school_id', sch_id) or sch_id
        sbatch = ctx.pop('_source_batch', None) or sbatch

        # 从 result 提取 target_id
        tid_val = None
        if hasattr(result, 'id'):
            tid_val = result.id

        event = LineageEvent(
            school_id=sch_id or 1,
            trace_id=trace_id,
            source_type=st or "unknown",
            source_id=sid,
            source_batch=sbatch,
            target_type=tt or "unknown",
            target_id=tid_val,
            transformation=transformation,
            context=ctx if ctx else None,
            triggered_by=_extract_trigger(args, kwargs),
            lineage_depth=depth,
            student_id=stu_id,
        )
        db.add(event)
        await db.flush()

    except Exception as e:
        # 静默失败 — 绝对不影响主流程
        logger.debug(f"[lineage] 记录血缘事件失败 (非致命): {e}")


def _default_extract_context(args, kwargs, result) -> dict:
    """默认上下文提取 — 捕获学生、学期等关键参数"""
    ctx = {}
    for key in ('student_id', 'semester', 'class_id', 'grade_id',
                'indicator_id', 'discipline_type', 'source_type',
                'policy_tag', 'exam_id'):
        if key in kwargs and kwargs[key] is not None:
            ctx[key] = kwargs[key]
    if hasattr(result, 'total_score'):
        ctx['result_total_score'] = result.total_score
    if hasattr(result, 'before_score') and hasattr(result, 'after_score'):
        ctx['before_score'] = result.before_score
        ctx['after_score'] = result.after_score
        ctx['change_amount'] = result.change_amount
    return ctx


def _extract_trigger(args, kwargs) -> str:
    """提取触发者标识"""
    for key in ('scorer_id', 'created_by', 'operator_id'):
        if key in kwargs and kwargs[key]:
            return f"user:{kwargs[key]}"
    return "system"


# ═══════════════════════════════════════════════════════════
# #1193 @audit_score_log — 轻量级审计装饰器
# ═══════════════════════════════════════════════════════════

def audit_score_log(
    operator_key: str = "operator_id",
    operator_name_key: str = "operator_name",
):
    """
    轻量级审计装饰器 — 为 ScoreLog 的 4 个血缘增强字段提供上下文。

    从函数 kwargs 中提取操作者信息（operator_id / created_by），设置审计 ContextVar，
    让已有的 ScoreLog 创建代码通过 get_audit_context() 获取 actor_id / source_ip / trace_context_id。

    用法:
        # 默认提取 operator_id + operator_name
        @audit_score_log
        async def upload_scores(self, db, ..., operator_id=None, operator_name=None):
            ...

        # 自定义键名（如 apply_deduction 用 created_by）
        @audit_score_log(operator_key="created_by")
        async def apply_deduction(self, db, ..., created_by, ...):
            ...

        # 在被装饰函数内部，ScoreLog 创建处只需:
        ctx = get_audit_context()
        log = ScoreLog(
            ...,
            actor_id=ctx["actor_id"],
            source_ip=ctx["source_ip"],
            trace_context_id=ctx["trace_context_id"],
        )

    与 @audit_lineage 的关系:
        - @audit_lineage: 写入 lineage_events 表（重量级血缘追踪）
        - @audit_score_log: 只设置 ContextVars（轻量级审计），为 ScoreLog 新字段提供数据源
        - 二者可以叠加使用：先 @audit_score_log 设置上下文，再 @audit_lineage 记录血缘

    设计原则:
        1. 绝对不阻断主流程 — 提取/设置失败时静默忽略
        2. 轻量级 — 不写 DB，不创建任何记录
        3. 自动补全 trace_id — 如果当前无 trace_id，自动生成新的
        4. 零侵入 — 对已有代码完全透明
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 提取操作者信息并设置审计上下文
            try:
                actor_id = kwargs.get(operator_key)
                actor_name = kwargs.get(operator_name_key)

                if actor_id is not None:
                    # 尝试提取 source_ip（来自 HTTP request 对象）
                    source_ip = None
                    request = kwargs.get("request")
                    if request and hasattr(request, "client"):
                        try:
                            source_ip = request.client.host if request.client else None
                        except Exception:
                            pass

                    set_audit_context(
                        actor_id=int(actor_id),
                        source_ip=source_ip,
                    )

                    # 确保 trace_id 也已设置（未设置则生成新的，保证 trace_context_id 不空）
                    if not _current_trace_id.get():
                        set_trace_context(str(uuid.uuid4()))

            except Exception:
                # 静默失败 — 绝对不影响主流程
                pass

            return await func(*args, **kwargs)

        return wrapper
    return decorator
