"""
modules/lineage/decorators.py — 零侵入审计装饰器

提供 @audit_lineage 装饰器，自动捕获函数调用参数和返回值，
写入 lineage_events 表，实现跨模块数据血缘追踪。

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
