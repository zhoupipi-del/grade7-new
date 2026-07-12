"""
modules/reports/services.py — 全校 RDI 聚合引擎 + 高危花名册 + 班主任报告

三核能力:
  1. get_school_wide_rdi_summary — 全校德育/风险态势白皮书数据
     从 risk_warnings + students + classes 聚合四维偏离 → risk_distribution + 热力排行
  2. get_high_risk_students — 高危学生花名册（intervention级）
     四维breakdown + AI处方摘要，为"暑期靶向家访指南"供弹
  3. get_class_teacher_report — 班主任一键生成本班德育工作图表
     本班RDI分布 + 本班高危清单 + 本班考勤/违纪/学业概览
"""

import logging
from datetime import datetime
from typing import Dict, List, Any, Optional

from sqlalchemy import select, func, case, and_, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

logger = logging.getLogger("reports.services")


# ═══════════════════════════════════════════════════════════════
# 风险等级映射 — DB存储值 → BOSS白皮书层级
# ═══════════════════════════════════════════════════════════════

# risk_warnings.risk_level 存储值: intervention / attention / normal / elevated
# 白皮书输出映射: intervention→红(干预) / attention→黄(关注) / normal→绿(正常)
RISK_LEVEL_MAP = {
    "intervention": "red_intervention",
    "attention": "yellow_attention",
    "normal": "green_normal",
    "elevated": "yellow_attention",  # elevated 视为关注级
}

RISK_LEVEL_CN = {
    "red_intervention": "红灯·干预",
    "yellow_attention": "黄灯·关注",
    "green_normal": "绿灯·正常",
}


# ═══════════════════════════════════════════════════════════════
# 1. 全校 RDI 态势白皮书
# ═══════════════════════════════════════════════════════════════

async def get_school_wide_rdi_summary(
    db: AsyncSession,
    school_id: int,
    grade_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    全校德育/风险态势白皮书聚合

    数据流:
      risk_warnings (active/latest) → 四维偏离聚合 → risk_distribution
      + classes → department_heat_ranking (各班平均RDI排行)
      + top intervention → top_critical_list (高危花名册)

    Args:
        db: AsyncSession
        school_id: 学校ID（多租户隔离）
        grade_id: 可选年级ID过滤
    """
    from modules.risk_models.models import RiskWarning
    from core.models import Student, Class, Grade

    # ── Step 1: 获取全校最新 active risk_warnings ──
    # 每个 student_id 只取最新一条 (子查询去重)
    subq = (
        select(
            RiskWarning.student_id,
            func.max(RiskWarning.id).label("max_id"),
        )
        .where(
            RiskWarning.school_id == school_id,
            RiskWarning.status == "active",
        )
    )
    if grade_id:
        subq = subq.where(RiskWarning.grade_id == grade_id)
    subq = subq.group_by(RiskWarning.student_id).subquery()

    warnings_q = (
        select(RiskWarning)
        .where(RiskWarning.id.in_(select(subq.c.max_id)))
    )
    result = await db.execute(warnings_q)
    warnings = result.scalars().all()

    # ── Step 2: 统计 risk_distribution ──
    risk_dist: Dict[str, int] = {
        "red_intervention": 0,
        "yellow_attention": 0,
        "green_normal": 0,
    }

    for w in warnings:
        mapped = RISK_LEVEL_MAP.get(w.risk_level, "green_normal")
        if mapped in risk_dist:
            risk_dist[mapped] += 1

    # 全校学生总数（有risk_warning的 + 没有的都算 normal）
    total_q = select(func.count(Student.id)).where(
        Student.school_id == school_id,
        Student.is_active == True,
    )
    if grade_id:
        total_q = total_q.where(Student.grade_id == grade_id)
    total_result = await db.execute(total_q)
    total_students = total_result.scalar() or 0

    # 补齐绿灯数：没有 warning 的学生全是 normal
    warned_students = len(warnings)
    risk_dist["green_normal"] = total_students - risk_dist["red_intervention"] - risk_dist["yellow_attention"]
    if risk_dist["green_normal"] < 0:
        risk_dist["green_normal"] = total_students - warned_students

    # ── Step 3: 各班级风险均值排行 (department_heat_ranking) ──
    # 查出每个班的平均 RDI 分数
    class_avg_q = (
        select(
            Class.id,
            Class.name,
            Class.grade_id,
            func.avg(RiskWarning.rdi_score).label("avg_rdi"),
            func.count(RiskWarning.id).label("warned_count"),
        )
        .join(Student, Student.class_id == Class.id)
        .join(RiskWarning, and_(
            RiskWarning.student_id == Student.id,
            RiskWarning.id.in_(select(subq.c.max_id)),
        ))
        .where(
            Class.school_id == school_id,
            Student.is_active == True,
        )
    )
    if grade_id:
        class_avg_q = class_avg_q.where(Class.grade_id == grade_id)
    class_avg_q = class_avg_q.group_by(Class.id, Class.name, Class.grade_id)

    class_result = await db.execute(class_avg_q)
    class_rows = class_result.all()

    # 查年级名称映射
    grade_names_q = select(Grade.id, Grade.name).where(Grade.school_id == school_id)
    grade_result = await db.execute(grade_names_q)
    grade_name_map = {g[0]: g[1] for g in grade_result.all()}

    # 组装 heat_ranking（按 avg_rdi 降序 — RDI越高风险越重）
    heat_ranking = []
    for row in sorted(class_rows, key=lambda r: (r[3] or 0), reverse=True):
        heat_ranking.append({
            "class_id": row[0],
            "class_name": row[1],
            "grade_name": grade_name_map.get(row[2], "未知年级"),
            "avg_rdi": round(float(row[3] or 0), 2),
            "warned_count": int(row[4] or 0),
        })

    # ── Step 4: 高危花名册 top_critical_list ──
    critical_list = await _build_risk_student_summaries(
        db, school_id,
        filter_risk_levels=["intervention"],
        grade_id=grade_id,
        limit=50,
    )

    return {
        "generated_at": datetime.now().isoformat(),
        "total_students_scanned": total_students,
        "risk_distribution": risk_dist,
        "department_heat_ranking": heat_ranking,
        "top_critical_list": critical_list,
    }


# ═══════════════════════════════════════════════════════════════
# 2. 高危学生花名册
# ═══════════════════════════════════════════════════════════════

async def get_high_risk_students(
    db: AsyncSession,
    school_id: int,
    grade_id: Optional[int] = None,
    risk_levels: Optional[List[str]] = None,
    export_format: str = "json",
) -> Dict[str, Any]:
    """
    高危学生花名册导出（暑期靶向家访指南）

    Args:
        db: AsyncSession
        school_id: 学校ID
        grade_id: 可选年级过滤
        risk_levels: 风险等级过滤，默认 ["intervention"]
        export_format: "json" | "excel" | "pdf"
    """
    levels = risk_levels or ["intervention"]
    summaries = await _build_risk_student_summaries(
        db, school_id,
        filter_risk_levels=levels,
        grade_id=grade_id,
        limit=None,
    )

    return {
        "generated_at": datetime.now().isoformat(),
        "total_high_risk": len(summaries),
        "risk_levels_filtered": levels,
        "students": summaries,
        "export_format": export_format,
    }


# ═══════════════════════════════════════════════════════════════
# 3. 班主任一键班级报告
# ═══════════════════════════════════════════════════════════════

async def get_class_teacher_report(
    db: AsyncSession,
    school_id: int,
    class_id: int,
) -> Dict[str, Any]:
    """
    班主任一键生成本班德育工作图表数据

    包含:
      - 本班RDI分布（红/黄/绿人数）
      - 本班高危学生清单
      - 本班考勤概览（出勤率/迟到/缺勤统计）
      - 本班违纪概览（违纪人次/处分统计）
      - 本班学业概览（平均分/科目偏离）
    """
    from modules.risk_models.models import RiskWarning
    from core.models import Student, Class

    # ── 班级信息 ──
    cls_q = select(Class).where(
        Class.id == class_id,
        Class.school_id == school_id,
    )
    cls_result = await db.execute(cls_q)
    cls = cls_result.scalar_one_or_none()
    if not cls:
        raise ValueError(f"班级 {class_id} 不存在或不属于当前学校")

    # ── 本班学生数 ──
    student_count_q = select(func.count(Student.id)).where(
        Student.class_id == class_id,
        Student.school_id == school_id,
        Student.is_active == True,
    )
    count_result = await db.execute(student_count_q)
    student_count = count_result.scalar() or 0

    # ── 本班RDI分布 ──
    subq = (
        select(
            RiskWarning.student_id,
            func.max(RiskWarning.id).label("max_id"),
        )
        .where(
            RiskWarning.school_id == school_id,
            RiskWarning.status == "active",
        )
        .group_by(RiskWarning.student_id).subquery()
    )

    class_warnings_q = (
        select(RiskWarning)
        .join(Student, Student.id == RiskWarning.student_id)
        .where(
            Student.class_id == class_id,
            Student.school_id == school_id,
            Student.is_active == True,
            RiskWarning.id.in_(select(subq.c.max_id)),
        )
    )
    warn_result = await db.execute(class_warnings_q)
    class_warnings = warn_result.scalars().all()

    # 统计分布
    class_risk_dist: Dict[str, int] = {
        "red_intervention": 0,
        "yellow_attention": 0,
        "green_normal": student_count,
    }
    for w in class_warnings:
        mapped = RISK_LEVEL_MAP.get(w.risk_level, "green_normal")
        if mapped in class_risk_dist:
            class_risk_dist[mapped] += 1
    # 减去有warning的normal人数
    class_risk_dist["green_normal"] -= class_risk_dist["red_intervention"] + class_risk_dist["yellow_attention"]
    if class_risk_dist["green_normal"] < 0:
        class_risk_dist["green_normal"] = 0

    # ── 本班高危学生清单 ──
    high_risk = await _build_risk_student_summaries(
        db, school_id,
        filter_risk_levels=["intervention", "attention"],
        class_id=class_id,
        limit=20,
    )

    # ── 本班考勤概览 ──
    attendance_summary = await _get_class_attendance_summary(db, school_id, class_id)

    # ── 本班违纪概览 ──
    discipline_summary = await _get_class_discipline_summary(db, school_id, class_id)

    # ── 本班学业概览 ──
    academic_summary = await _get_class_academic_summary(db, school_id, class_id)

    return {
        "generated_at": datetime.now().isoformat(),
        "class_id": class_id,
        "class_name": cls.name,
        "student_count": student_count,
        "risk_distribution": class_risk_dist,
        "high_risk_students": high_risk,
        "attendance_summary": attendance_summary,
        "discipline_summary": discipline_summary,
        "academic_summary": academic_summary,
    }


# ═══════════════════════════════════════════════════════════════
# 内部工具函数
# ═══════════════════════════════════════════════════════════════

async def _build_risk_student_summaries(
    db: AsyncSession,
    school_id: int,
    filter_risk_levels: List[str],
    class_id: Optional[int] = None,
    grade_id: Optional[int] = None,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    构建 RiskStudentSummary 列表

    核心逻辑:
      1. 从 risk_warnings 取指定 risk_level 的最新记录
      2. JOIN students + classes 获取姓名和班级名
      3. 从 ai_prescriptions 取最新处方摘要
    """
    from modules.risk_models.models import RiskWarning
    from modules.ai_prescription.models import AIPrescription
    from core.models import Student, Class, Grade

    # 每个 student 的最新 warning
    subq = (
        select(
            RiskWarning.student_id,
            func.max(RiskWarning.id).label("max_id"),
        )
        .where(
            RiskWarning.school_id == school_id,
            RiskWarning.status == "active",
            RiskWarning.risk_level.in_(filter_risk_levels),
        )
    )
    if grade_id:
        subq = subq.where(RiskWarning.grade_id == grade_id)
    subq = subq.group_by(RiskWarning.student_id).subquery()

    # 主查询: warning + student + class
    main_q = (
        select(RiskWarning, Student, Class)
        .join(Student, Student.id == RiskWarning.student_id)
        .join(Class, Class.id == Student.class_id)
        .where(
            RiskWarning.id.in_(select(subq.c.max_id)),
            Student.school_id == school_id,
            Student.is_active == True,
        )
    )
    if class_id:
        main_q = main_q.where(Student.class_id == class_id)
    if school_id:
        main_q = main_q.where(Class.school_id == school_id)

    # 按 rdi_score 降序 — 最危险的排最前
    main_q = main_q.order_by(RiskWarning.rdi_score.desc())
    if limit:
        main_q = main_q.limit(limit)

    result = await db.execute(main_q)
    rows = result.all()

    summaries = []
    for row in rows:
        w: RiskWarning = row[0]
        s: Student = row[1]
        c: Class = row[2]

        # ── 四维 breakdown ──
        breakdown = {
            "behavior": round(float(w.behavior_deviation or 0), 2),
            "attendance": round(float(w.attendance_deviation or 0), 2),
            "score": round(float(w.score_deviation or 0), 2),
            "psych": round(float(w.psych_deviation or 0), 2),
        }

        # ── 触发事件原因 ──
        trigger_type = w.trigger_event_type or ""
        handling_note = w.handling_note or ""
        warning_reason = f"{trigger_type}" if trigger_type else ""
        if handling_note:
            warning_reason = f"{trigger_type}: {handling_note[:80]}" if trigger_type else handling_note[:80]

        # ── AI 处方摘要 ──
        prescription_snippet = ""
        try:
            rx_q = (
                select(AIPrescription.summary)
                .where(
                    AIPrescription.target_id == s.id,
                    AIPrescription.target_type == "student",
                    AIPrescription.school_id == school_id,
                )
                .order_by(AIPrescription.created_at.desc())
                .limit(1)
            )
            rx_result = await db.execute(rx_q)
            rx_row = rx_result.first()
            if rx_row and rx_row[0]:
                prescription_snippet = rx_row[0][:200]  # 截取前200字
        except Exception as e:
            logger.warning("处方摘要查询失败 student=%s: %s", s.id, e)

        mapped_level = RISK_LEVEL_MAP.get(w.risk_level, w.risk_level or "unknown")

        summaries.append({
            "student_id": s.id,
            "student_name": s.name,
            "class_name": c.name,
            "current_rdi": round(float(w.rdi_score or 0), 2),
            "risk_level": mapped_level,
            "breakdown": breakdown,
            "latest_warning_reason": warning_reason,
            "ai_prescription_snippet": prescription_snippet,
        })

    return summaries


async def _get_class_attendance_summary(
    db: AsyncSession,
    school_id: int,
    class_id: int,
) -> Dict[str, Any]:
    """本班考勤概览"""
    try:
        q = text("""
            SELECT
                COUNT(DISTINCT ar.student_id) as covered_students,
                SUM(CASE WHEN ar.status = 'present' THEN 1 ELSE 0 END) as present_count,
                SUM(CASE WHEN ar.status = 'late' THEN 1 ELSE 0 END) as late_count,
                SUM(CASE WHEN ar.status = 'absent' THEN 1 ELSE 0 END) as absent_count,
                SUM(CASE WHEN ar.status = 'leave' THEN 1 ELSE 0 END) as leave_count,
                COUNT(*) as total_records
            FROM attendance_records ar
            JOIN students s ON ar.student_id = s.id
            WHERE s.class_id = :cid AND s.school_id = :sid AND s.is_active = 1
        """)
        result = await db.execute(q, {"cid": class_id, "sid": school_id})
        row = result.first()
        if not row:
            return {"status": "no_data"}

        total = int(row[5] or 0)
        present = int(row[1] or 0)
        attendance_rate = round(present / total * 100, 1) if total > 0 else 0

        return {
            "attendance_rate": attendance_rate,
            "present_count": present,
            "late_count": int(row[2] or 0),
            "absent_count": int(row[3] or 0),
            "leave_count": int(row[4] or 0),
            "total_records": total,
            "covered_students": int(row[0] or 0),
        }
    except Exception as e:
        logger.warning("考勤概览查询失败 class=%s: %s", class_id, e)
        return {"status": "error", "message": str(e)}


async def _get_class_discipline_summary(
    db: AsyncSession,
    school_id: int,
    class_id: int,
) -> Dict[str, Any]:
    """本班违纪概览"""
    try:
        q = text("""
            SELECT
                COUNT(*) as total_incidents,
                COUNT(DISTINCT dr.student_id) as involved_students,
                SUM(dr.points) as total_points,
                COUNT(CASE WHEN ds.status = 'ACTIVE' THEN 1 END) as active_sanctions
            FROM discipline_records dr
            JOIN students s ON dr.student_id = s.id
            LEFT JOIN discipline_sanctions ds ON ds.student_id = s.id AND ds.school_id = :sid
            WHERE s.class_id = :cid AND s.school_id = :sid AND s.is_active = 1
              AND dr.verify_status = 'VERIFIED'
        """)
        result = await db.execute(q, {"cid": class_id, "sid": school_id})
        row = result.first()
        if not row:
            return {"status": "no_data"}

        return {
            "total_incidents": int(row[0] or 0),
            "involved_students": int(row[1] or 0),
            "total_penalty_points": float(row[2] or 0),
            "active_sanctions": int(row[3] or 0),
        }
    except Exception as e:
        logger.warning("违纪概览查询失败 class=%s: %s", class_id, e)
        return {"status": "error", "message": str(e)}


async def _get_class_academic_summary(
    db: AsyncSession,
    school_id: int,
    class_id: int,
) -> Dict[str, Any]:
    """本班学业概览"""
    try:
        q = text("""
            SELECT
                COUNT(DISTINCT gr.student_id) as covered_students,
                AVG(gr.std_value) as avg_std_value,
                COUNT(CASE WHEN gr.std_value < -1.0 THEN 1 END) as below_avg_count,
                COUNT(CASE WHEN gr.std_value >= 1.0 THEN 1 END) as above_avg_count
            FROM grades_records gr
            JOIN students s ON gr.student_id = s.id
            WHERE s.class_id = :cid AND s.school_id = :sid AND s.is_active = 1
        """)
        result = await db.execute(q, {"cid": class_id, "sid": school_id})
        row = result.first()
        if not row:
            return {"status": "no_data"}

        return {
            "covered_students": int(row[0] or 0),
            "avg_std_value": round(float(row[1] or 0), 2),
            "below_avg_count": int(row[2] or 0),
            "above_avg_count": int(row[3] or 0),
        }
    except Exception as e:
        logger.warning("学业概览查询失败 class=%s: %s", class_id, e)
        return {"status": "error", "message": str(e)}
