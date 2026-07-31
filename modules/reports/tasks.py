"""
modules/reports/tasks.py — 重资产阵地：异步 PDF 生成核心任务

Celery Worker 进程独立运行，与 FastAPI Uvicorn 完全解耦。

优化架构 (2026-07-02):
  - 模块级 _sync_engine 替代 per-call create_engine (省 2s/次)
  - 夜间预计算 ReportSnapshot (2:30 AM) → 白天 PDF 渲染跳过 Stage 1
  - 快照优先策略: 24h 内有效快照直接读取，否则 fallback 到实时聚合
"""

import logging
import os
from datetime import datetime

from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy import create_engine as _create_engine
from sqlalchemy.orm import sessionmaker as _sm

from .celery_app import celery_engine

logger = logging.getLogger("reports.tasks")

# ── 输出目录 ──
# 安全修复: 报告含学生敏感数据, 从公开 static 目录迁至私有目录,
# 下载一律走带鉴权的 /api/v1/reports/tasks/{task_id}/download 端点
OUTPUT_DIR = os.environ.get("REPORTS_OUTPUT_DIR", "/root/backend/private/reports")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ═══════════════════════════════════════════════════════════════
# 模块级同步引擎 (替代 per-call create_engine)
# ═══════════════════════════════════════════════════════════════

from core.db_utils import require_sync_db_url

_SYNC_DB_URL = require_sync_db_url()
_sync_engine = _create_engine(_SYNC_DB_URL, pool_pre_ping=True, pool_recycle=300, pool_size=5)
_SyncSession = _sm(bind=_sync_engine)


def _get_sync_session():
    """获取模块级同步 Session"""
    return _SyncSession()


# ═══════════════════════════════════════════════════════════════
# 处分等级扣分映射（同步版本，从 discipline/models.py 复制）
# ═══════════════════════════════════════════════════════════════

# 处分等级 → 评价值扣减（阶梯熔断模型）
LEVEL_PENALTY_MAP = {
    "WARNING": -5,
    "SERIOUS_WARN": -10,
    "DEMERIT": -20,
    "PROBATION": None,  # None = 一票否决（不扣分，直接标记不合格）
    "EXPULSION": None,  # None = 开除（不在评价体系内）
}

# 触发一票否决的处分等级
VETO_LEVELS = {"PROBATION", "EXPULSION"}

# 处分等级 → 中文标签
LEVEL_LABELS = {
    "WARNING": "警告",
    "SERIOUS_WARN": "严重警告",
    "DEMERIT": "记过",
    "PROBATION": "留校察看",
    "EXPULSION": "开除学籍",
}

# 维度权重（默认）
DEFAULT_DIMENSION_WEIGHTS = {
    "moral": 0.25,
    "academic": 0.25,
    "health": 0.20,
    "art": 0.15,
    "social": 0.15,
}

SNAPSHOT_MAX_AGE_HOURS = 24


@celery_engine.task(bind=True, name="generate_class_moral_report")
def generate_class_moral_report(
    self, school_id: int, class_id: int, semester: str, created_by: int = None
):
    """
    【核心重资产任务】班级期末德育综合报告 PDF

    优化架构 (2026-07-02):
      阶段 0: 快照探测 — 查 ReportSnapshot，24h 内有效则直接用，跳过 Stage 1
      阶段 1 (10%): 吃数据 — 跨模块同步 evaluation + red_flag + behavior + attendance 预计算快照
      阶段 2 (30%): 矩阵计算 — 全班五维排名 + 红旗历史 + 违纪汇总
      阶段 3 (70%): 渲染 HTML → PDF — ReportLab + matplotlib 双引擎编译
      阶段 4 (95%): 归档输出 → 静态文件服务器，返回下载 URL
    """
    total_steps = 4
    t0 = datetime.now()

    def progress(step: int, text: str):
        """更新 Celery 任务状态（供前端轮询消费）"""
        self.update_state(
            state="PROGRESS",
            meta={
                "current": step,
                "total": total_steps,
                "progress": int(step / total_steps * 100),
                "status_text": text,
            },
        )

    try:
        # ═══ 阶段 0: 快照探测 ═══
        from .models import ReportSnapshot

        report_data = None
        snapshot_used = False

        session = _get_sync_session()
        try:
            snapshot = (
                session.query(ReportSnapshot)
                .filter(
                    ReportSnapshot.class_id == class_id,
                    ReportSnapshot.semester == semester,
                    ReportSnapshot.school_id == school_id,
                    ReportSnapshot.is_stale.is_(False),
                )
                .order_by(ReportSnapshot.computed_at.desc())
                .first()
            )

            if snapshot and snapshot.computed_at:
                age = datetime.now() - snapshot.computed_at
                if age.total_seconds() < SNAPSHOT_MAX_AGE_HOURS * 3600:
                    report_data = snapshot.snapshot_data
                    snapshot_used = True
                    logger.info(
                        "[Reports] 快照命中 | class=%s semester=%s age=%sh",
                        class_id,
                        semester,
                        round(age.total_seconds() / 3600, 1),
                    )
        finally:
            session.close()

        # ═══ 阶段 1: 聚合跨模块数据 (仅无快照时执行) ═══
        if not snapshot_used:
            progress(0, "正在连接数据源并聚合跨模块快照...")
            report_data = _aggregate_class_data(school_id, class_id, semester)
        else:
            progress(0, "使用夜间预计算快照，跳过数据聚合...")

        # ═══ 阶段 2: 矩阵计算与排名 ═══
        progress(1, "正在动态计算全班五维加权排名及红旗历史...")
        report_data = _compute_rankings(report_data)

        # ═══ 阶段 3: PDF 渲染 ═══
        progress(2, "正在注入德育评语并编译 PDF 文档...")
        from .pdf_utils import generate_class_moral_report_pdf

        pdf_bytes, filename = generate_class_moral_report_pdf(report_data)

        # ═══ 阶段 4: 归档输出 ═══
        progress(3, "PDF 编译完成，正在归档至静态文件服务器...")

        output_path = os.path.join(OUTPUT_DIR, filename)
        with open(output_path, "wb") as f:
            f.write(pdf_bytes)

        relative_url = f"/api/v1/reports/tasks/{self.request.id}/download"
        file_size_kb = round(len(pdf_bytes) / 1024, 1)
        elapsed = round((datetime.now() - t0).total_seconds(), 2)

        logger.info(
            "[Reports] PDF 生成成功: %s (%sKB) 耗时=%ss 快照=%s",
            filename,
            file_size_kb,
            elapsed,
            "命中" if snapshot_used else "实时",
        )

        return {
            "status": "SUCCESS",
            "progress": 100,
            "filename": filename,
            "download_url": relative_url,
            "file_size_kb": file_size_kb,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "elapsed_s": elapsed,
            "snapshot_used": snapshot_used,
            # 鉴权下载端点校验归属所需的元数据
            "school_id": school_id,
            "created_by": created_by,
            "stored_filename": filename,
        }

    except SoftTimeLimitExceeded:
        logger.error(f"[Reports] 任务超时: class_id={class_id}, semester={semester}")
        return {
            "status": "TIMEOUT",
            "progress": 0,
            "error": "报告生成超时（超过 15 分钟限制），请检查数据量或联系管理员",
        }

    except Exception as e:
        logger.error(f"[Reports] PDF 生成失败: {e}", exc_info=True)
        raise


def _aggregate_class_data(school_id: int, class_id: int, semester: str) -> dict:
    """
    阶段 1: 聚合跨模块数据。

    使用模块级 _sync_engine (不再 per-call create_engine)。
    数据来源: evaluation_scores, student_scores, flag_archive_reports,
              discipline_records, attendance_records, students
    """
    from sqlalchemy import text

    session = _get_sync_session()

    try:
        # ── 1. 班级基本信息 ──
        cls = session.execute(
            text("SELECT id, name, grade_id FROM classes WHERE id = :id AND school_id = :sid"),
            {"id": class_id, "sid": school_id},
        ).fetchone()
        if not cls:
            raise ValueError(f"班级 {class_id} 不存在")

        class_name = cls[1]

        # ── 2. 学生列表 ──
        students_raw = session.execute(
            text("""
                SELECT id, name, student_no, gender
                FROM students
                WHERE class_id = :cid AND school_id = :sid AND is_active = 1
                ORDER BY student_no
            """),
            {"cid": class_id, "sid": school_id},
        ).fetchall()

        students = [
            {"id": s[0], "name": s[1], "student_no": s[2] or "", "gender": s[3] or ""}
            for s in students_raw
        ]

        if not students:
            raise ValueError(f"班级 {class_id} 无活跃学生")

        student_ids = [s["id"] for s in students]
        {s["id"]: s for s in students}

        # ── 3. 素质评价五维分（读模型 StudentScore 快照）─
        scores_raw = session.execute(
            text("""
                SELECT student_id,
                       moral_score, academic_score, health_score, art_score, social_score, total_score
                FROM student_scores
                WHERE student_id IN :stids AND semester = :sem AND school_id = :sid
            """),
            {"stids": tuple(student_ids), "sem": semester, "sid": school_id},
        ).fetchall()

        score_map = {}
        for sr in scores_raw:
            score_map[sr[0]] = {
                "moral": float(sr[1] or 0),
                "academic": float(sr[2] or 0),
                "health": float(sr[3] or 0),
                "art": float(sr[4] or 0),
                "social": float(sr[5] or 0),
                "total": float(sr[6] or 0),
            }

        # ── 4. 流动红旗历史 ──
        flags_raw = session.execute(
            text("""
                SELECT class_id, period_type, period_label, final_score, `rank`, has_flag
                FROM flag_archive_reports
                WHERE class_id = :cid AND school_id = :sid
                ORDER BY period_label DESC
                LIMIT 10
            """),
            {"cid": class_id, "sid": school_id},
        ).fetchall()

        flag_history = [
            {
                "period_type": f[1],
                "period_label": f[2],
                "final_score": float(f[3] or 0),
                "rank": int(f[4] or 0),
                "has_flag": bool(f[5]),
            }
            for f in flags_raw
        ]

        # ── 5. 违纪汇总 ──
        disc_raw = session.execute(
            text("""
                SELECT student_id, COUNT(*) as cnt, SUM(points) as total_points
                FROM discipline_records
                WHERE student_id IN :stids AND school_id = :sid
                  AND verify_status = 'VERIFIED'
                GROUP BY student_id
            """),
            {"stids": tuple(student_ids), "sid": school_id},
        ).fetchall()

        discipline_map = {}
        for d in disc_raw:
            discipline_map[d[0]] = {"count": int(d[1]), "total_points": int(d[2] or 0)}

        # ── 5.5 处分查询与一票否决裁定（同步版本）──
        # 查询所有学生的 ACTIVE 处分
        sanctions_raw = session.execute(
            text("""
                SELECT student_id, level, reason, document_no, punish_date
                FROM discipline_sanctions
                WHERE student_id IN :stids AND school_id = :sid
                  AND status = 'ACTIVE'
            """),
            {"stids": tuple(student_ids), "sid": school_id},
        ).fetchall()

        # 构建学生 → 处分列表的映射
        sanctions_map = {}
        for s in sanctions_raw:
            sid = s[0]
            if sid not in sanctions_map:
                sanctions_map[sid] = []
            sanctions_map[sid].append(
                {
                    "level": s[1],
                    "label": LEVEL_LABELS.get(s[1], s[1]),
                    "reason": s[2][:100] if s[2] else "",
                    "document_no": s[3],
                    "punish_date": s[4].isoformat() if s[4] else None,
                }
            )

        # ── 6. 考勤汇总 ──
        att_raw = session.execute(
            text("""
                SELECT
                    student_id,
                    SUM(CASE WHEN status = 'present' THEN 1 ELSE 0 END) as present_days,
                    SUM(CASE WHEN status = 'late' THEN 1 ELSE 0 END) as late_count,
                    SUM(CASE WHEN status = 'absent' THEN 1 ELSE 0 END) as absent_count,
                    SUM(CASE WHEN status = 'leave' THEN 1 ELSE 0 END) as leave_count
                FROM attendance_records
                WHERE student_id IN :stids AND school_id = :sid
                GROUP BY student_id
            """),
            {"stids": tuple(student_ids), "sid": school_id},
        ).fetchall()

        attendance_map = {}
        for a in att_raw:
            attendance_map[a[0]] = {
                "present": int(a[1] or 0),
                "late": int(a[2] or 0),
                "absent": int(a[3] or 0),
                "leave": int(a[4] or 0),
            }

        # ── 组装 ──
        for s in students:
            sid = s["id"]
            s["scores"] = score_map.get(sid, {})
            s["discipline"] = discipline_map.get(sid, {"count": 0, "total_points": 0})
            s["attendance"] = attendance_map.get(
                sid, {"present": 0, "late": 0, "absent": 0, "leave": 0}
            )

            # ── 注入处分信息 + 一票否决裁定 + final_grade 判定 ──
            active_sanctions = sanctions_map.get(sid, [])
            s["sanctions"] = active_sanctions

            # 计算处分扣分
            penalty_total = 0.0
            is_veto = False
            for sanction in active_sanctions:
                pts = LEVEL_PENALTY_MAP.get(sanction["level"])
                if pts is not None:
                    penalty_total += pts
                else:
                    # PROBATION / EXPULSION → 一票否决
                    is_veto = True

            s["discipline_penalty"] = {
                "total_deduction": penalty_total,
                "is_veto": is_veto,
                "active_count": len(active_sanctions),
            }

            # 计算调整后总分和 final_grade
            base_total = s["scores"].get("total", 0.0)
            base_moral = s["scores"].get("moral", 0.0)

            # 处分调整后 moral 分（仅扣 moral 维度，保底 0）
            adjusted_moral = max(0.0, base_moral + penalty_total)

            # 计算调整后总分（使用默认权重）
            weights = DEFAULT_DIMENSION_WEIGHTS
            adjusted_total = round(
                adjusted_moral * weights.get("moral", 0.25)
                + s["scores"].get("academic", 0.0) * weights.get("academic", 0.25)
                + s["scores"].get("health", 0.0) * weights.get("health", 0.20)
                + s["scores"].get("art", 0.0) * weights.get("art", 0.15)
                + s["scores"].get("social", 0.0) * weights.get("social", 0.15),
                1,
            )

            # 最终等级判定
            if is_veto:
                final_grade = "D"
                grade_label = "不合格（一票否决）"
            else:
                t = adjusted_total
                if t >= 90:
                    final_grade = "A"
                    grade_label = "优秀"
                elif t >= 75:
                    final_grade = "B"
                    grade_label = "良好"
                elif t >= 60:
                    final_grade = "C"
                    grade_label = "合格"
                else:
                    final_grade = "D"
                    grade_label = "不合格"

            s["final_evaluation"] = {
                "base_total": base_total,
                "adjusted_total": adjusted_total,
                "penalty_total": penalty_total,
                "is_veto": is_veto,
                "final_grade": final_grade,
                "grade_label": grade_label,
            }

        return {
            "type": "class_moral",
            "school_id": school_id,
            "class_id": class_id,
            "class_name": class_name,
            "semester": semester,
            "students": students,
            "flag_history": flag_history,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    finally:
        session.close()


def _compute_rankings(report_data: dict) -> dict:
    """
    阶段 2: 排名计算

    为每位学生计算五维班级排名和总分排名。
    """
    students = report_data.get("students", [])

    if not students:
        return report_data

    # 总分排名
    students_with_total = [s for s in students if s["scores"].get("total", 0) > 0]
    students_with_total.sort(key=lambda s: s["scores"]["total"], reverse=True)
    for rank, s in enumerate(students_with_total, 1):
        s["rank_total"] = rank

    # 五维分项排名
    dimensions = ["moral", "academic", "health", "art", "social"]
    for dim in dimensions:
        ranked = sorted(
            [s for s in students if s["scores"].get(dim, 0) > 0],
            key=lambda s: s["scores"].get(dim, 0),
            reverse=True,
        )
        for rank, s in enumerate(ranked, 1):
            if "ranks" not in s:
                s["ranks"] = {}
            s["ranks"][dim] = rank

    report_data["students"] = students
    return report_data


# ═══════════════════════════════════════════════════════════════
# 夜间预计算任务 — PDF 渲染的"数据弹药库"
# ═══════════════════════════════════════════════════════════════


@celery_engine.task(name="reports.precompute_snapshots")
def precompute_snapshots(school_id: int = 1):
    """
    夜间预计算全校所有班级的 PDF 报告快照。

    Celery Beat: 每日 2:30 AM 执行
    队列: maintenance

    遍历全校所有班级 → 调用 _aggregate_class_data → 存入 ReportSnapshot
    白天用户触发 PDF 时直接读取快照，跳过 Stage 1。
    """
    from sqlalchemy import text as _sql_text

    from .models import ReportSnapshot

    t0 = datetime.now()
    session = _get_sync_session()

    try:
        # 获取当前学期
        now = datetime.now()
        if now.month >= 2 and now.month <= 7:
            semester = f"{now.year - 1}-{now.year}-2"
        else:
            semester = f"{now.year}-{now.year + 1}-1"

        # 查询全校所有班级
        classes_raw = session.execute(
            _sql_text("SELECT id, name FROM classes WHERE school_id = :sid"),
            {"sid": school_id},
        ).fetchall()

        total = len(classes_raw)
        success = 0
        failed = 0

        for cls in classes_raw:
            class_id = cls[0]
            class_name = cls[1]
            try:
                # 聚合数据
                data = _aggregate_class_data(school_id, class_id, semester)

                # Upsert 快照
                existing = (
                    session.query(ReportSnapshot)
                    .filter(
                        ReportSnapshot.class_id == class_id,
                        ReportSnapshot.semester == semester,
                        ReportSnapshot.school_id == school_id,
                    )
                    .first()
                )

                if existing:
                    existing.snapshot_data = data
                    existing.student_count = len(data.get("students", []))
                    existing.is_stale = False
                    existing.computed_at = datetime.now()
                else:
                    snap = ReportSnapshot(
                        school_id=school_id,
                        class_id=class_id,
                        semester=semester,
                        snapshot_data=data,
                        student_count=len(data.get("students", [])),
                        is_stale=False,
                        computed_at=datetime.now(),
                    )
                    session.add(snap)

                session.commit()
                success += 1
                logger.info(
                    "[Reports] 快照预计算成功 | class=%s(%s) students=%s",
                    class_id,
                    class_name,
                    len(data.get("students", [])),
                )

            except Exception as exc:
                session.rollback()
                failed += 1
                logger.error(
                    "[Reports] 快照预计算失败 | class=%s(%s): %s",
                    class_id,
                    class_name,
                    exc,
                )

        elapsed = round((datetime.now() - t0).total_seconds(), 2)
        logger.info(
            "[Reports] 夜间预计算完成 | school=%s semester=%s total=%s success=%s failed=%s 耗时=%ss",
            school_id,
            semester,
            total,
            success,
            failed,
            elapsed,
        )

        return {
            "status": "SUCCESS",
            "school_id": school_id,
            "semester": semester,
            "total_classes": total,
            "success": success,
            "failed": failed,
            "elapsed_s": elapsed,
        }

    finally:
        session.close()


# ═══════════════════════════════════════════════════════════════
# 每日系统合规审计 — 原 Flask audit_report.py 迁移项
# ═══════════════════════════════════════════════════════════════


@celery_engine.task(name="reports.periodic_audit_report")
def periodic_audit_report():
    """
    每日凌晨 2:00 系统合规审计 — 原 Flask audit_report.py 迁移项

    检查项:
      1. 僵尸审批工单 (pending > 7天)
      2. 过期风险预警 (risk_warnings active 但 expires_at 已过)
      3. 孤儿处分记录 (discipline_sanctions.student_id 不存在)
      4. 无快照学生 (有学生但无 student_scores 记录)
      5. 积压未读通知 (> 30天未读)

    Celery Beat: 每日 2:00 AM
    队列: periodic
    """
    from sqlalchemy import text as _sql_text

    t0 = datetime.now()
    logger.info("[AUDIT] 启动系统全量合规审计...")

    session = _get_sync_session()
    audit_results = []

    try:
        # 1. 僵尸审批工单 (pending > 7天)
        stale_approvals = session.execute(
            _sql_text("""
                SELECT COUNT(*) as cnt
                FROM approval_requests
                WHERE current_status = 'pending'
                  AND created_at < DATE_SUB(NOW(), INTERVAL 7 DAY)
            """)
        ).fetchone()
        stale_count = stale_approvals[0] if stale_approvals else 0
        audit_results.append(
            {
                "check": "stale_approvals",
                "label": "僵尸审批工单 (pending>7天)",
                "count": stale_count,
                "status": "PASS" if stale_count == 0 else "WARN",
            }
        )

        # 2. 过期风险预警
        expired_warnings = session.execute(
            _sql_text("""
                SELECT COUNT(*) as cnt
                FROM risk_warnings
                WHERE status = 'active'
                  AND expires_at IS NOT NULL
                  AND expires_at < NOW()
            """)
        ).fetchone()
        expired_count = expired_warnings[0] if expired_warnings else 0
        audit_results.append(
            {
                "check": "expired_warnings",
                "label": "过期风险预警 (active但已过期)",
                "count": expired_count,
                "status": "PASS" if expired_count == 0 else "WARN",
            }
        )

        # 3. 孤儿处分记录
        orphan_sanctions = session.execute(
            _sql_text("""
                SELECT COUNT(*) as cnt
                FROM discipline_sanctions ds
                LEFT JOIN students s ON ds.student_id = s.id
                WHERE s.id IS NULL
            """)
        ).fetchone()
        orphan_count = orphan_sanctions[0] if orphan_sanctions else 0
        audit_results.append(
            {
                "check": "orphan_sanctions",
                "label": "孤儿处分记录 (student_id不存在)",
                "count": orphan_count,
                "status": "PASS" if orphan_count == 0 else "FAIL",
            }
        )

        # 4. 无快照学生
        no_snapshot = session.execute(
            _sql_text("""
                SELECT COUNT(*) as cnt
                FROM students s
                LEFT JOIN student_scores ss ON s.id = ss.student_id
                WHERE s.is_active = 1 AND ss.id IS NULL
            """)
        ).fetchone()
        no_snap_count = no_snapshot[0] if no_snapshot else 0
        audit_results.append(
            {
                "check": "no_snapshot",
                "label": "无评价快照学生",
                "count": no_snap_count,
                "status": "PASS" if no_snap_count == 0 else "WARN",
            }
        )

        # 5. 积压未读通知 (> 30天)
        stale_notifs = session.execute(
            _sql_text("""
                SELECT COUNT(*) as cnt
                FROM notifications
                WHERE is_read = 0
                  AND created_at < DATE_SUB(NOW(), INTERVAL 30 DAY)
            """)
        ).fetchone()
        stale_notif_count = stale_notifs[0] if stale_notifs else 0
        audit_results.append(
            {
                "check": "stale_notifications",
                "label": "积压未读通知 (>30天)",
                "count": stale_notif_count,
                "status": "PASS" if stale_notif_count == 0 else "WARN",
            }
        )

        elapsed = round((datetime.now() - t0).total_seconds(), 2)
        overall = "PASS" if all(r["status"] == "PASS" for r in audit_results) else "WARN"

        logger.info(
            "[AUDIT] 审计完成 | overall=%s checks=%s 耗时=%ss",
            overall,
            len(audit_results),
            elapsed,
        )
        for r in audit_results:
            log_level = logger.info if r["status"] == "PASS" else logger.warning
            log_level(
                "[AUDIT] %s: %s = %s (%s)",
                r["status"],
                r["label"],
                r["count"],
                r["check"],
            )

        return {
            "status": "SUCCESS",
            "overall": overall,
            "checks": audit_results,
            "elapsed_s": elapsed,
            "audited_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    except Exception as exc:
        logger.error("[AUDIT] 审计运行失败: %s", exc, exc_info=True)
        return {"status": "FAILURE", "error": str(exc)}

    finally:
        session.close()
