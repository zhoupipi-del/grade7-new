"""
德育声呐事件总线 — 统一业务事件广播入口
业务代码调用 publish()，由 cockpit.broadcast_sonar() 负责 Redis 发布 + 内存回放。

设计原则：
  1. 懒加载 cockpit.broadcast_sonar，避免循环导入
  2. 异常静默失败，不中断主流程
  3. operator 由调用方传 session.get("display_name", "系统")
"""
import time
from datetime import datetime

# ── 事件类型枚举（与 cockpit.broadcast_sonar 对齐）──
EVENT_TYPES = {
    "discipline": "违纪记录",
    "score":      "五翼评分",
    "risk":       "AI风险预警",
    "task":       "任务流转",
    "attendance": "考勤异常",
    "leave":      "请假审批",
    "quality":    "综合素质",
    "briefing":   "AI面谈简报",
    "general":    "通用消息",
}

# ── 等级 → CSS 颜色映射（供前端直接使用）──
LEVEL_COLORS = {
    "info":    "secondary",
    "success": "success",
    "warning": "warning",
    "danger":  "danger",
}


def publish(event_type, module, operator, message, level="info",
            student_id=None, class_id=None, extra=None):
    """
    统一声呐广播入口

    Args:
        event_type: 事件类型（见 EVENT_TYPES）
        module:     来源模块名（wings / class_ / ai_analysis / cockpit ...）
        operator:   操作人姓名（传入 session.get("display_name", "系统")）
        message:    展示文本（如 "张三 扣 2 分（打架）"）
        level:      事件等级 info/success/warning/danger
        student_id: 关联学生 ID（可选，供前端点击穿透）
        class_id:   关联班级 ID（可选）
        extra:       额外字典（会合并进 payload['data']）
    """
    payload = {
        "type":        event_type,
        "module":      module,
        "operator":    operator,
        "message":     message,
        "level":       level,
        "timestamp":   time.time(),
        "iso_time":    datetime.now().strftime("%H:%M:%S"),
        "student_id":  student_id,
        "class_id":    class_id,
    }
    if extra and isinstance(extra, dict):
        payload.update(extra)

    try:
        # 懒加载 — 避免启动时的循环导入
        from blueprints.cockpit import broadcast_sonar as _broadcast
        _broadcast(payload)
    except Exception:
        # 声呐失败绝不中断主流程
        pass


# ═══════════════════════════════════════════════════════
#  业务便捷函数 — 各 Blueprint 直接调用
# ═══════════════════════════════════════════════════════

def publish_discipline(record, operator_name):
    """
    违纪记录创建时调用
    record: DisciplineRecord 实例（需已 flush 有 id）
    """
    student_name = record.student.name if record.student else f"学生{record.student_id}"
    cat = record.category or "未分类"
    msg = f"✍️ 违纪登记 — {student_name}（{cat}）"
    publish(
        event_type="discipline",
        module="class_",
        operator=operator_name,
        message=msg,
        level="warning" if record.type in ("major", "serious") else "info",
        student_id=record.student_id,
        class_id=record.class_id,
        extra={"discipline_id": record.id, "discipline_type": record.type},
    )


def publish_score(score, operator_name):
    """
    WingsScore 保存后调用
    score: WingsScore 实例（需已 flush 有 id）
    """
    dim_label = score.dimension or "未知"
    msg = f"⭐ 五翼评分 — {score.student.name if score.student else ''}（{dim_label} {score.score}分）"
    publish(
        event_type="score",
        module="wings",
        operator=operator_name,
        message=msg,
        level="success",
        student_id=score.student_id,
        class_id=score.class_id,
        extra={"dimension": score.dimension, "score": score.score, "scorer_type": score.scorer_type},
    )


def publish_risk(record, operator_name):
    """
    RiskRecord 创建/更新时调用
    record: RiskRecord 实例
    """
    level_zh = {"red": "高危", "yellow": "中危", "green": "低危"}.get(record.risk_level, record.risk_level)
    student_name = record.student.name if record.student else f"学生{record.student_id}"
    msg = f"🚨 AI预警 — {student_name}（{level_zh}）"
    publish(
        event_type="risk",
        module="ai_analysis",
        operator=operator_name,
        message=msg,
        level="danger" if record.risk_level == "red" else ("warning" if record.risk_level == "yellow" else "info"),
        student_id=record.student_id,
        class_id=record.class_id,
        extra={"risk_level": record.risk_level, "warning_count": record.warning_count},
    )


def publish_briefing(student_name, operator_name, highlights):
    """
    AI 面谈简报生成时调用
    highlights: list[str] 关键要点（前3条会展示在声呐流）
    """
    hl_text = "；".join(highlights[:3])
    msg = f"🤖 AI面谈简报 — {student_name}（{hl_text}）"
    publish(
        event_type="briefing",
        module="ai_analysis",
        operator=operator_name,
        message=msg,
        level="info",
        extra={"highlights": highlights[:3]},
    )
