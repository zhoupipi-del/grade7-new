"""纪律管理共享辅助函数"""
from models import db, DisciplineRecord, DisciplineAppeal, User, Message, Student, QualityIndicator, QualityScore
from blueprints.common import notify_parent, notify_class_teacher, send_notification
from datetime import datetime


TYPE_MAP = {
    "warning": "警告",
    "minor": "轻微",
    "major": "重大",
    "serious": "严重",
}

# 积分升级阈值：(累计分数, 升级类型, 中文名)
ESCALATION_THRESHOLDS = [
    (50, "serious", "严重"),
    (30, "major", "重大"),
    (20, "minor", "轻微"),
    (10, "warning", "警告"),
]


def check_escalation(student, created_by):
    """检查学生累计扣分是否触发自动升级

    异常安全：任何 DB 操作失败不会中断主记录流程，
    仅记录错误日志并跳过升级检查。
    """
    import logging
    from sqlalchemy import func as sa_func

    try:
        total = db.session.query(sa_func.coalesce(sa_func.sum(DisciplineRecord.points), 0)).filter(
            DisciplineRecord.student_id == student.id,
            DisciplineRecord.status == "active",
        ).scalar()
    except Exception as e:
        logging.getLogger("grade7").error(f"check_escalation 查询失败 (student: {student.id}): {e}")
        return

    for threshold, dtype, dname in ESCALATION_THRESHOLDS:
        if total >= threshold:
            try:
                # 幂等性守卫：同一学生的同一升级类型只触发一次
                from blueprints.linkage_utils import try_linkage, tk_escalation
                if not try_linkage(
                    "discipline_escalation",
                    f"student:{student.id}",
                    tk_escalation(student.id, dtype),
                ):
                    return

                auto = DisciplineRecord(
                    student_id=student.id,
                    class_id=student.class_id,
                    grade_id=student.grade_id,
                    type=dtype,
                    category="系统自动",
                    description=f"[自动升级] 累计扣分 {total} 分，系统自动生成{dname}级违纪",
                    action_taken="请班主任跟进处理",
                    points=0,
                    created_by=created_by,
                )
                db.session.add(auto)
            except Exception as e:
                logging.getLogger("grade7").error(
                    f"check_escalation 升级失败 (student: {student.id}, type: {dtype}): {e}"
                )
            return  # 最高级别已触发，不叠加


def send_discipline_notifications(record, student):
    """新增违纪后自动推送通知给班主任和家长（通过 send_notification 触发 SSE）"""
    type_name = TYPE_MAP.get(record.type, record.type)
    category = record.category or "违纪"
    desc = (record.description or "")[:100]
    from_user_id = record.created_by

    # 通知班主任（通过 notify_class_teacher 触发 SSE）
    notify_class_teacher(
        student,
        title=f"违纪通知 — {student.name}",
        content=f"{student.name} 因「{category}」被记录{type_name}违纪。\n详情：{desc}",
        from_user_id=from_user_id,
    )

    # 通知家长（通过 notify_parent 触发 SSE）
    notify_parent(
        student,
        title=f"孩子违纪提醒 — {student.name}",
        content=f"您的孩子 {student.name} 因「{category}」被记录{type_name}违纪，请登录系统查看详情。",
        from_user_id=from_user_id,
    )


def send_appeal_notifications(appeal, student, record):
    """申诉提交/处理后自动推送通知（通过 send_notification 触发 SSE）"""
    if appeal.status == "pending":
        # 新申诉 → 通知班主任和德育处
        notify_class_teacher(
            student,
            title=f"申诉提醒 — {student.name}",
            content=f"家长对 {student.name} 的违纪记录「{record.category or '违纪'}」提出了申诉，请关注。\n申诉理由：{(appeal.reason or '')[:100]}",
            from_user_id=None,
        )
        admins = User.query.filter_by(role="ms_admin", is_active=True).all()
        for admin in admins:
            send_notification(
                admin.id,
                title=f"新申诉 — {student.name}",
                content=f"{student.name}（{record.category or '违纪'}类）的家长提出申诉，请登录系统复核处理。",
            )

    elif appeal.status in ("approved", "rejected"):
        result_label = "已通过" if appeal.status == "approved" else "已驳回"
        review_text = (appeal.review_comment or "")[:100]

        # 通知家长
        notify_parent(
            student,
            title=f"申诉结果 — {student.name}",
            content=f"您对 {student.name} 违纪记录「{record.category or '违纪'}」的申诉已被德育处{result_label}。\n审核意见：{review_text or '无'}",
            from_user_id=None,
        )

        # 通知班主任
        notify_class_teacher(
            student,
            title=f"申诉结果 — {student.name}",
            content=f"{student.name} 的违纪申诉已被德育处{result_label}。\n审核意见：{review_text or '无'}",
            from_user_id=None,
        )


# 违纪类型 → 思想品德扣分映射
DISCIPLINE_QUALITY_DEDUCTION = {
    "warning": -1,
    "minor": -3,
    "major": -10,
    "serious": -20,
}


def deduct_quality_score(record, student, created_by):
    """违纪记录后自动扣减综合素质评价「思想品德」维度分数

    根据违纪类型按 DISCIPLINE_QUALITY_DEDUCTION 扣分，
    扣分记录写入 quality_scores 表，scorer_type='system'。
    
    注意：此函数调用前 add_discipline 已将违纪记录加入 db.session，
    此函数再将扣分加入同一 session，最终由调用方 safe_commit() 统一提交，
    保证事务原子性。异常被捕获不会中断违纪记录流程。
    """
    # 状态机守卫：只有 VERIFIED 的违纪记录才触发扣分
    if getattr(record, 'verify_status', None) != 'VERIFIED':
        return

    try:
        ded = DISCIPLINE_QUALITY_DEDUCTION.get(record.type, -1)
        if ded >= 0:   # 扣分为正（奖励）不处理
            return

        # 查找「思想品德」一级指标
        indicator = QualityIndicator.query.filter_by(
            dimension="moral", parent_id=0, is_active=True
        ).first()
        if not indicator:
            return

        # 当前学期
        now = datetime.utcnow()
        month = now.month
        if month >= 9:
            semester = f"{now.year}-{now.year + 1}-1"
        elif month <= 2:
            semester = f"{now.year - 1}-{now.year}-1"
        else:
            semester = f"{now.year - 1}-{now.year}-2"

        # 幂等性守卫：同一违纪记录对同一学生+指标的扣分只执行一次
        from blueprints.linkage_utils import try_linkage, sk_discipline, tk_quality
        if not try_linkage(
            "discipline_to_quality",
            sk_discipline(record.id),
            tk_quality(student.id, indicator.id, semester),
        ):
            return

        # 创建扣分记录
        qs = QualityScore(
            student_id=student.id,
            class_id=student.class_id,
            grade_id=student.grade_id,
            indicator_id=indicator.id,
            score=float(ded),
            scorer_type="system",
            scorer_id=created_by,
            semester=semester,
            comment=f"[违纪自动扣减] {record.category or '违纪'}({TYPE_MAP.get(record.type, record.type)})：{(record.description or '')[:80]}",
        )
        db.session.add(qs)
    except Exception as e:
        import logging
        logging.getLogger("grade7").error(f"deduct_quality_score failed for student {student.id}: {e}")
