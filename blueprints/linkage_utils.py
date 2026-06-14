"""联动幂等性辅助模块

防止同一条业务数据被重复联动（重复扣分、重复生成预警、重复发通知等）。
核心机制：在 LinkageLog 表上建 (linkage_type, source_key, target_key) 唯一键，
每次联动前先 try insert，插入成功 → 首次联动，继续执行；重复键冲突 → 跳过。

用法：
    from blueprints.linkage_utils import try_linkage
    if not try_linkage("discipline_to_quality", f"discipline:{rid}", f"quality:{sid}:{sid}"):
        return  # 已处理过，跳过
    # ... 执行联动逻辑 ...
"""

import logging
from datetime import datetime

logger = logging.getLogger("grade7")


def try_linkage(linkage_type, source_key, target_key, extra_info=None):
    """尝试登记一次联动操作（幂等性守卫）

    Args:
        linkage_type: 联动类型字符串 (见 LinkageLog 文档)
        source_key: 来源唯一标识，如 "discipline:42"
        target_key: 目标唯一标识，如 "quality:15:2025-2026-1"
        extra_info: 补充信息 (dict 或 str)

    Returns:
        True  — 首次联动，可以继续执行
        False — 已存在（重复触发），应跳过
    """
    from models import LinkageLog, db

    try:
        entry = LinkageLog(
            linkage_type=linkage_type,
            source_key=source_key,
            target_key=target_key,
            extra_info=str(extra_info) if extra_info else None,
        )
        db.session.add(entry)
        db.session.flush()  # 触发唯一键约束检查
        return True
    except Exception:
        # 唯一键冲突 (IntegrityError) 或其他数据库异常 → 已处理过
        db.session.rollback()
        logger.info(
            f"linkage_skip: type={linkage_type} source={source_key} "
            f"target={target_key} (already processed)"
        )
        return False


def dedup_notify(student_id, notify_type, date_str, from_user_id=None):
    """消息通知幂等性检查（较轻量）

    同一学生在同一天的同类型通知只发一次。
    使用 LinkageLog 唯一键实现去重。

    Args:
        student_id: 学生 ID
        notify_type: 通知类型 (如 "score_publish", "attendance_anomaly", "discipline_alert")
        date_str: 日期字符串 "2026-06-09"
        from_user_id: 发送者 ID（可选，用于区分不同老师重复发送）

    Returns:
        True  — 可以发送
        False — 今天已发过同类型，跳过
    """
    source_key = f"student:{student_id}:{notify_type}:{date_str}"
    if from_user_id:
        source_key += f":from:{from_user_id}"
    target_key = f"notify:{date_str}"
    return try_linkage("dedup_notify", source_key, target_key)


# ── 便捷工具：生成标准 source_key / target_key ──

def sk_discipline(record_id):
    """违纪记录 source_key"""
    return f"discipline:{record_id}"


def sk_score(exam_id, student_id):
    """成绩变更 source_key"""
    return f"score:{exam_id}:{student_id}"


def sk_survey(survey_id):
    """问卷 source_key"""
    return f"survey:{survey_id}"


def sk_student_scan(student_id, scan_date):
    """AI扫描 source_key"""
    date_str = scan_date.strftime("%Y-%m-%d") if hasattr(scan_date, "strftime") else str(scan_date)
    return f"scan:{student_id}:{date_str}"


def tk_quality(student_id, indicator_id, semester):
    """素质分 target_key"""
    return f"quality:{student_id}:{indicator_id}:{semester}"


def tk_assessment(student_id, scale_name):
    """心理评估 target_key"""
    return f"assessment:{student_id}:{scale_name}"


def tk_risk(student_id, scan_date):
    """AI风险 target_key"""
    date_str = scan_date.strftime("%Y-%m-%d") if hasattr(scan_date, "strftime") else str(scan_date)
    return f"risk:{student_id}:{date_str}"


def tk_escalation(student_id, dtype):
    """违纪升级 target_key"""
    return f"escalation:{student_id}:{dtype}"
