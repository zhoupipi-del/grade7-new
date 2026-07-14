"""
modules/grades/services.py — 成绩管理业务逻辑层

服务类:
- SubjectService: 科目 CRUD（创建/列表/更新/启停）
- ExamService:   考试 CRUD（创建/列表/更新/状态变更）
- ScoreService:  成绩录入（批量 upsert + 排名计算）+ 查询（分页/汇总/排名）
- AuditService:  审计日志（记录 + 查询）
"""

import logging
from collections import defaultdict
from datetime import datetime
from decimal import Decimal

from core.models import Class as ClassModel
from core.models import Student
from modules.lineage.decorators import audit_score_log
from sqlalchemy import and_, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from .models import GradeAuditLog, GradeExam, GradeRecord, GradeSubject
from .schemas import (
    AuditLogQuery,
    ClassScoreSummary,
    ExamCreate,
    ExamResultPage,
    ExamResultQuery,
    ExamUpdate,
    ScoreUploadRequest,
    ScoreUploadResult,
    StudentExamResult,
    StudentScoreOut,
    SubjectCreate,
    SubjectSummary,
    SubjectUpdate,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# SubjectService — 科目管理
# ═══════════════════════════════════════════════════════════════


class SubjectService:
    """科目 CRUD — 定义学校开设的考试科目（语文/数学/英语...）"""

    @staticmethod
    async def create_subject(
        db: AsyncSession,
        school_id: int,
        data: SubjectCreate,
    ) -> GradeSubject:
        """创建科目"""
        subject = GradeSubject(
            school_id=school_id,
            name=data.name,
            code=data.code,
            full_score=data.full_score,
            sort_order=data.sort_order,
        )
        db.add(subject)
        await db.commit()
        await db.refresh(subject)
        return subject

    @staticmethod
    async def list_subjects(
        db: AsyncSession,
        school_id: int,
        active_only: bool = False,
    ) -> list[GradeSubject]:
        """列出科目（可按启用状态过滤）"""
        stmt = (
            select(GradeSubject)
            .where(GradeSubject.school_id == school_id)
            .order_by(GradeSubject.sort_order.asc(), GradeSubject.id.asc())
        )
        if active_only:
            stmt = stmt.where(GradeSubject.is_active == True)

        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_subject(
        db: AsyncSession,
        school_id: int,
        subject_id: int,
    ) -> GradeSubject | None:
        """获取单个科目"""
        result = await db.execute(
            select(GradeSubject).where(
                GradeSubject.id == subject_id,
                GradeSubject.school_id == school_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def update_subject(
        db: AsyncSession,
        school_id: int,
        subject_id: int,
        data: SubjectUpdate,
    ) -> GradeSubject:
        """更新科目信息（部分更新，只改传入的字段）"""
        subject = await SubjectService.get_subject(db, school_id, subject_id)
        if not subject:
            raise ValueError(f"科目不存在: id={subject_id}")

        update_data = data.model_dump(exclude_unset=True)
        if not update_data:
            raise ValueError("无有效更新字段")

        for key, value in update_data.items():
            setattr(subject, key, value)

        await db.commit()
        await db.refresh(subject)
        return subject

    @staticmethod
    async def toggle_subject_active(
        db: AsyncSession,
        school_id: int,
        subject_id: int,
    ) -> GradeSubject:
        """切换科目启用状态（翻转 is_active）"""
        subject = await SubjectService.get_subject(db, school_id, subject_id)
        if not subject:
            raise ValueError(f"科目不存在: id={subject_id}")

        subject.is_active = not subject.is_active
        await db.commit()
        await db.refresh(subject)
        return subject


# ═══════════════════════════════════════════════════════════════
# ExamService — 考试管理
# ═══════════════════════════════════════════════════════════════


class ExamService:
    """考试管理 — 创建/查询/修改考试元信息"""

    @staticmethod
    async def create_exam(
        db: AsyncSession,
        school_id: int,
        data: ExamCreate,
        user_id: int,
    ) -> GradeExam:
        """创建考试"""
        exam = GradeExam(
            school_id=school_id,
            name=data.name,
            exam_type=data.exam_type,
            grade_id=data.grade_id,
            semester=data.semester,
            exam_date=data.exam_date,
            created_by=user_id,
        )
        db.add(exam)
        await db.commit()
        await db.refresh(exam)
        return exam

    @staticmethod
    async def get_exam(
        db: AsyncSession,
        school_id: int,
        exam_id: int,
    ) -> GradeExam | None:
        """获取单个考试"""
        result = await db.execute(
            select(GradeExam).where(
                GradeExam.id == exam_id,
                GradeExam.school_id == school_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_exams(
        db: AsyncSession,
        school_id: int,
        grade_id: int | None = None,
        semester: str | None = None,
        status: str | None = None,
    ) -> list[GradeExam]:
        """列出考试（可按年级/学期/状态过滤）

        MySQL 不支持 nullslast()，用 is_(None) asc 将 NULL 排到末尾。
        """
        stmt = (
            select(GradeExam)
            .where(GradeExam.school_id == school_id)
            .order_by(
                GradeExam.exam_date.is_(None).asc(),
                GradeExam.exam_date.desc(),
                GradeExam.id.desc(),
            )
        )
        if grade_id is not None:
            stmt = stmt.where(GradeExam.grade_id == grade_id)
        if semester:
            stmt = stmt.where(GradeExam.semester == semester)
        if status:
            stmt = stmt.where(GradeExam.status == status)

        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def update_exam(
        db: AsyncSession,
        school_id: int,
        exam_id: int,
        data: ExamUpdate,
    ) -> GradeExam:
        """更新考试信息（部分更新）"""
        exam = await ExamService.get_exam(db, school_id, exam_id)
        if not exam:
            raise ValueError(f"考试不存在: id={exam_id}")

        update_data = data.model_dump(exclude_unset=True)
        if not update_data:
            raise ValueError("无有效更新字段")

        for key, value in update_data.items():
            setattr(exam, key, value)

        exam.updated_at = datetime.now()
        await db.commit()
        await db.refresh(exam)
        return exam

    @staticmethod
    async def change_exam_status(
        db: AsyncSession,
        school_id: int,
        exam_id: int,
        new_status: str,
    ) -> GradeExam:
        """变更考试状态（draft → published → archived）"""
        valid_statuses = {"draft", "published", "archived"}
        if new_status not in valid_statuses:
            raise ValueError(f"无效状态: {new_status}，合法值: {valid_statuses}")

        exam = await ExamService.get_exam(db, school_id, exam_id)
        if not exam:
            raise ValueError(f"考试不存在: id={exam_id}")

        exam.status = new_status
        exam.updated_at = datetime.now()
        await db.commit()
        await db.refresh(exam)
        return exam


# ═══════════════════════════════════════════════════════════════
# ScoreService — 成绩录入 + 查询
# ═══════════════════════════════════════════════════════════════


class ScoreService:
    """成绩管理核心服务 — 批量录入、排名计算、多维度查询"""

    @staticmethod
    @audit_score_log(operator_key="operator_id", operator_name_key="operator_name")
    async def upload_scores(
        db: AsyncSession,
        school_id: int,
        data: ScoreUploadRequest,
        operator_id: int | None = None,
        operator_name: str | None = None,
    ) -> ScoreUploadResult:
        """批量成绩录入 — 两趟扫描模式

        扫描 1: 逐条 upsert（新增或覆盖），记录变更审计
        扫描 2: 统一计算排名（class_rank + grade_rank）

        Args:
            db: 数据库会话
            school_id: 学校 ID
            data: 批量录入请求（exam_id + scores[]）
            operator_id: 操作者 user_id
            operator_name: 操作者姓名

        Returns:
            ScoreUploadResult: 录入结果摘要
        """
        # ── 前置校验：考试存在 ────────────────────
        exam = await ExamService.get_exam(db, school_id, data.exam_id)
        if not exam:
            return ScoreUploadResult(
                exam_id=data.exam_id,
                total=len(data.scores),
                success=0,
                failed=len(data.scores),
                errors=["考试不存在"],
                ranks_computed=False,
            )

        # ── 预取所有已有记录（减少 N+1）────────────
        existing_result = await db.execute(
            select(GradeRecord).where(
                GradeRecord.school_id == school_id,
                GradeRecord.exam_id == data.exam_id,
            )
        )
        existing_map = {(r.student_id, r.subject_id): r for r in existing_result.scalars().all()}

        # ── 扫描 1: 逐条 upsert ────────────────────
        errors: list[str] = []
        success = 0
        audit_logs: list[GradeAuditLog] = []

        for entry in data.scores:
            try:
                key = (entry.student_id, entry.subject_id)
                existing = existing_map.get(key)

                old_score = None
                if existing:
                    old_score = existing.score
                    existing.score = entry.score
                    existing.is_absent = entry.is_absent
                    existing.remark = entry.remark
                    existing.updated_at = datetime.now()
                    # 重置排名（等下趟重新算）
                    existing.class_rank = None
                    existing.grade_rank = None
                else:
                    record = GradeRecord(
                        school_id=school_id,
                        exam_id=data.exam_id,
                        student_id=entry.student_id,
                        subject_id=entry.subject_id,
                        score=entry.score,
                        is_absent=entry.is_absent,
                        remark=entry.remark,
                    )
                    db.add(record)
                    existing_map[key] = record  # 缓存供后续审计查询

                # 审计日志：分数发生变化才记录
                if _scores_differ(old_score, entry.score):
                    audit_logs.append(
                        GradeAuditLog(
                            school_id=school_id,
                            exam_id=data.exam_id,
                            student_id=entry.student_id,
                            subject_id=entry.subject_id,
                            old_score=old_score,
                            new_score=entry.score,
                            action="upsert",
                            operator_id=operator_id,
                            operator_name=operator_name,
                        )
                    )

                success += 1
            except Exception as e:
                errors.append(
                    f"student_id={entry.student_id}, subject_id={entry.subject_id}: {str(e)}"
                )
                logger.warning(f"成绩录入失败: {e}")

        # ── 批量写入审计日志 ──────────────────────
        for a in audit_logs:
            db.add(a)

        try:
            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.error(f"成绩批量提交失败: {e}")
            return ScoreUploadResult(
                exam_id=data.exam_id,
                total=len(data.scores),
                success=0,
                failed=len(data.scores),
                errors=[f"数据库提交失败: {str(e)}"],
                ranks_computed=False,
            )

        # ── 扫描 2: 统一计算排名 ────────────────────
        ranks_computed = False
        if success > 0:
            try:
                await _compute_ranks(db, school_id, data.exam_id)
                ranks_computed = True
            except Exception as e:
                logger.error(f"排名计算失败: {e}")
                errors.append(f"排名计算失败: {str(e)}")

        return ScoreUploadResult(
            exam_id=data.exam_id,
            total=len(data.scores),
            success=success,
            failed=len(data.scores) - success,
            errors=errors,
            ranks_computed=ranks_computed,
        )

    @staticmethod
    async def get_exam_results(
        db: AsyncSession,
        school_id: int,
        query: ExamResultQuery,
    ) -> ExamResultPage:
        """查询考试成绩 — 分页 + 排名 + 班级汇总

        返回每位学生的全科成绩、总分、班级/年级排名，以及班级统计。
        """
        # ── 第1步：获取考试信息 ────────────────────
        exam = await ExamService.get_exam(db, school_id, query.exam_id)
        if not exam:
            raise ValueError(f"考试不存在: id={query.exam_id}")

        # ── 第2步：拉取所有成绩记录（含关联数据）────
        stmt = (
            select(GradeRecord, Student, ClassModel, GradeSubject)
            .join(Student, GradeRecord.student_id == Student.id)
            .join(ClassModel, Student.class_id == ClassModel.id)
            .join(
                GradeSubject,
                and_(
                    GradeRecord.subject_id == GradeSubject.id,
                    GradeSubject.school_id == school_id,
                ),
            )
            .where(
                GradeRecord.school_id == school_id,
                GradeRecord.exam_id == query.exam_id,
                Student.is_active == True,
            )
        )

        if query.class_id:
            stmt = stmt.where(Student.class_id == query.class_id)

        result = await db.execute(stmt)
        all_rows = result.all()

        if not all_rows:
            return ExamResultPage(
                exam=_exam_to_out(exam),
                total=0,
                page=query.page,
                page_size=query.page_size,
                results=[],
                class_summaries=[],
            )

        # ── 第3步：按学生聚合 ──────────────────────
        # student_map: student_id -> {student, class, subjects[], total, scored_count}
        student_map: dict = {}
        for record, student, cls, subject in all_rows:
            sid = student.id
            if sid not in student_map:
                student_map[sid] = {
                    "student": student,
                    "class": cls,
                    "subjects": [],
                    "total": Decimal("0"),
                    "scored_count": 0,
                }

            sd = student_map[sid]
            sd["subjects"].append(
                StudentScoreOut(
                    subject_id=subject.id,
                    subject_name=subject.name,
                    full_score=subject.full_score,
                    score=record.score,
                    is_absent=record.is_absent,
                    class_rank=record.class_rank,
                    grade_rank=record.grade_rank,
                )
            )
            if record.score is not None and not record.is_absent:
                sd["total"] += record.score
                sd["scored_count"] += 1

        # ── 第4步：按总分排序 + 计算整体排名 ───────
        sorted_students = sorted(
            student_map.values(),
            key=lambda x: x["total"] if x["scored_count"] > 0 else Decimal("-1"),
            reverse=True,
        )

        # 整体班级排名: class_id -> [(index, student_data)]
        class_lists: dict = defaultdict(list)
        for idx, sd in enumerate(sorted_students):
            class_lists[sd["class"].id].append((idx, sd))

        # 计算排名（处理并列：同分别同排名，DENSE_RANK 语义）
        class_ranks = {}  # (student_id, class_id) -> rank
        for cid, entries in class_lists.items():
            rank = 1
            prev_total = None
            for pos, (idx, sd) in enumerate(entries):
                total = sd["total"] if sd["scored_count"] > 0 else None
                if total is None:
                    class_ranks[(sd["student"].id, cid)] = None
                    continue
                if prev_total is not None and total < prev_total:
                    rank = pos + 1
                class_ranks[(sd["student"].id, cid)] = rank
                prev_total = total

        # 整体年级排名
        grade_ranks = {}
        rank = 1
        prev_total = None
        for pos, sd in enumerate(sorted_students):
            total = sd["total"] if sd["scored_count"] > 0 else None
            if total is None:
                grade_ranks[sd["student"].id] = None
                continue
            if prev_total is not None and total < prev_total:
                rank = pos + 1
            grade_ranks[sd["student"].id] = rank
            prev_total = total

        # ── 第5步：按学生姓名模糊搜索 ──────────────
        if query.student_name:
            keyword = query.student_name.strip()
            sorted_students = [sd for sd in sorted_students if keyword in sd["student"].name]

        # ── 第6步：分页 ────────────────────────────
        total_count = len(sorted_students)
        start = (query.page - 1) * query.page_size
        end = start + query.page_size
        page_students = sorted_students[start:end]

        # ── 第7步：组装 StudentExamResult ──────────
        results = []
        for sd in page_students:
            student = sd["student"]
            cls = sd["class"]
            total = sd["total"] if sd["scored_count"] > 0 else None
            avg = float(total) / sd["scored_count"] if sd["scored_count"] > 0 else None

            results.append(
                StudentExamResult(
                    student_id=student.id,
                    student_name=student.name,
                    class_id=cls.id,
                    class_name=cls.name,
                    total_score=total,
                    avg_score=round(avg, 2) if avg else None,
                    class_rank=class_ranks.get((student.id, cls.id)),
                    grade_rank=grade_ranks.get(student.id),
                    subjects=sd["subjects"],
                )
            )

        # ── 第8步：班级汇总 ────────────────────────
        class_summaries = _build_class_summaries(student_map, sorted_students)

        return ExamResultPage(
            exam=_exam_to_out(exam),
            total=total_count,
            page=query.page,
            page_size=query.page_size,
            results=results,
            class_summaries=class_summaries,
        )

    @staticmethod
    async def get_student_result(
        db: AsyncSession,
        school_id: int,
        exam_id: int,
        student_id: int,
    ) -> StudentExamResult | None:
        """查询单个学生在某次考试中的全科成绩"""
        exam = await ExamService.get_exam(db, school_id, exam_id)
        if not exam:
            return None

        # ── 获取成绩记录 ──────────────────────────
        stmt = (
            select(GradeRecord, Student, ClassModel, GradeSubject)
            .join(Student, GradeRecord.student_id == Student.id)
            .join(ClassModel, Student.class_id == ClassModel.id)
            .join(
                GradeSubject,
                and_(
                    GradeRecord.subject_id == GradeSubject.id,
                    GradeSubject.school_id == school_id,
                ),
            )
            .where(
                GradeRecord.school_id == school_id,
                GradeRecord.exam_id == exam_id,
                GradeRecord.student_id == student_id,
            )
            .order_by(GradeSubject.sort_order.asc())
        )
        result = await db.execute(stmt)
        rows = result.all()

        if not rows:
            return None

        # ── 组装科目列表 ──────────────────────────
        student = rows[0][1]  # Student
        cls = rows[0][2]  # ClassModel
        subjects = []
        total = Decimal("0")
        scored_count = 0

        for record, _, _, subject in rows:
            subjects.append(
                StudentScoreOut(
                    subject_id=subject.id,
                    subject_name=subject.name,
                    full_score=subject.full_score,
                    score=record.score,
                    is_absent=record.is_absent,
                    class_rank=record.class_rank,
                    grade_rank=record.grade_rank,
                )
            )
            if record.score is not None and not record.is_absent:
                total += record.score
                scored_count += 1

        avg = float(total) / scored_count if scored_count > 0 else None

        # ── 计算整体排名（查询所有学生总分）────────
        class_rank, grade_rank = await _get_student_overall_ranks(
            db, school_id, exam_id, student_id, total, scored_count
        )

        return StudentExamResult(
            student_id=student.id,
            student_name=student.name,
            class_id=cls.id,
            class_name=cls.name,
            total_score=total if scored_count > 0 else None,
            avg_score=round(avg, 2) if avg else None,
            class_rank=class_rank,
            grade_rank=grade_rank,
            subjects=subjects,
        )


# ═══════════════════════════════════════════════════════════════
# AuditService — 审计日志
# ═══════════════════════════════════════════════════════════════


class AuditService:
    """成绩变更审计 — 不可篡改的操作记录"""

    @staticmethod
    async def query_logs(
        db: AsyncSession,
        school_id: int,
        query: AuditLogQuery,
    ) -> tuple[list[GradeAuditLog], int]:
        """分页查询审计日志"""
        stmt = select(GradeAuditLog).where(GradeAuditLog.school_id == school_id)

        if query.exam_id:
            stmt = stmt.where(GradeAuditLog.exam_id == query.exam_id)
        if query.student_id:
            stmt = stmt.where(GradeAuditLog.student_id == query.student_id)
        if query.action:
            stmt = stmt.where(GradeAuditLog.action == query.action)

        # 总数
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_result = await db.execute(count_stmt)
        total = total_result.scalar() or 0

        # 分页
        stmt = stmt.order_by(GradeAuditLog.created_at.desc())
        stmt = stmt.offset((query.page - 1) * query.page_size).limit(query.page_size)
        result = await db.execute(stmt)
        logs = list(result.scalars().all())

        return logs, total


# ═══════════════════════════════════════════════════════════════
# 内部辅助函数
# ═══════════════════════════════════════════════════════════════


async def _compute_ranks(
    db: AsyncSession,
    school_id: int,
    exam_id: int,
) -> None:
    """计算单科班级排名和年级排名（DENSE_RANK 语义：同分同名次）

    使用 SQL 窗口函数 ROW_NUMBER() OVER (PARTITION BY ... ORDER BY score DESC)
    在 MySQL 8.0+ 上一趟完成，避免 Python 侧 O(N²) 循环。
    """
    await db.execute(
        text("""
            UPDATE grades_records gr
            JOIN (
                SELECT
                    gr2.id,
                    DENSE_RANK() OVER (
                        PARTITION BY gr2.subject_id, s.class_id
                        ORDER BY gr2.score DESC
                    ) AS c_rank,
                    DENSE_RANK() OVER (
                        PARTITION BY gr2.subject_id
                        ORDER BY gr2.score DESC
                    ) AS g_rank
                FROM grades_records gr2
                JOIN students s ON gr2.student_id = s.id
                WHERE gr2.exam_id = :exam_id
                  AND gr2.school_id = :school_id
                  AND gr2.score IS NOT NULL
                  AND gr2.is_absent = 0
            ) ranks ON gr.id = ranks.id
            SET gr.class_rank = ranks.c_rank,
                gr.grade_rank = ranks.g_rank
        """),
        {"exam_id": exam_id, "school_id": school_id},
    )
    await db.commit()


async def _get_student_overall_ranks(
    db: AsyncSession,
    school_id: int,
    exam_id: int,
    student_id: int,
    student_total: Decimal,
    scored_count: int,
) -> tuple[int | None, int | None]:
    """计算单个学生的整体班级排名和年级排名（基于总分）"""
    if scored_count == 0:
        return None, None

    # ── 获取该学生所在班级 ──────────────────────
    student_row = await db.execute(select(Student.class_id).where(Student.id == student_id))
    class_id = student_row.scalar()

    # ── 班级排名：同班中有多少人总分 > 该生 ──────
    c_rank_row = await db.execute(
        text("""
            SELECT COUNT(*) + 1 FROM (
                SELECT gr.student_id, COALESCE(SUM(gr.score), 0) AS total
                FROM grades_records gr
                JOIN students s ON gr.student_id = s.id
                WHERE gr.exam_id = :exam_id
                  AND gr.school_id = :school_id
                  AND gr.score IS NOT NULL
                  AND gr.is_absent = 0
                  AND s.class_id = :class_id
                GROUP BY gr.student_id
                HAVING total > :student_total
            ) t
        """),
        {
            "exam_id": exam_id,
            "school_id": school_id,
            "class_id": class_id,
            "student_total": float(student_total),
        },
    )
    class_rank = c_rank_row.scalar()

    # ── 年级排名：全年级中有多少人总分 > 该生 ────
    g_rank_row = await db.execute(
        text("""
            SELECT COUNT(*) + 1 FROM (
                SELECT gr.student_id, COALESCE(SUM(gr.score), 0) AS total
                FROM grades_records gr
                JOIN students s ON gr.student_id = s.id
                WHERE gr.exam_id = :exam_id
                  AND gr.school_id = :school_id
                  AND gr.score IS NOT NULL
                  AND gr.is_absent = 0
                GROUP BY gr.student_id
                HAVING total > :student_total
            ) t
        """),
        {
            "exam_id": exam_id,
            "school_id": school_id,
            "student_total": float(student_total),
        },
    )
    grade_rank = g_rank_row.scalar()

    return class_rank, grade_rank


def _build_class_summaries(
    student_map: dict,
    sorted_students: list,
) -> list[ClassScoreSummary]:
    """从已聚合的学生数据构建班级成绩汇总"""
    # 按班级分组
    class_groups: dict = defaultdict(list)
    for sd in student_map.values():
        class_groups[sd["class"].id].append(sd)

    summaries = []
    for cid, members in class_groups.items():
        if not members:
            continue

        cls = members[0]["class"]
        totals = [float(m["total"]) for m in members if m["scored_count"] > 0]

        if not totals:
            summaries.append(
                ClassScoreSummary(
                    class_id=cid,
                    class_name=cls.name,
                    student_count=0,
                )
            )
            continue

        n = len(totals)
        avg_total = round(sum(totals) / n, 2) if n > 0 else None
        max_total = round(max(totals), 2)
        min_total = round(min(totals), 2)

        # 及格率（总分 >= 60% 满分）和优秀率（总分 >= 90% 满分）
        # 满分 = 各科满分之和（从第一个学生的科目推算）
        full_total = sum(float(s.full_score) for s in members[0]["subjects"]) if members else 100

        pass_count = sum(1 for t in totals if t >= full_total * 0.6)
        excellent_count = sum(1 for t in totals if t >= full_total * 0.9)

        # ── 单科统计 ─────────────────────────────
        subject_summaries = _build_subject_summaries(members)

        summaries.append(
            ClassScoreSummary(
                class_id=cid,
                class_name=cls.name,
                student_count=n,
                avg_total=avg_total,
                max_total=max_total,
                min_total=min_total,
                pass_rate=round(pass_count / n * 100, 1) if n > 0 else None,
                excellent_rate=round(excellent_count / n * 100, 1) if n > 0 else None,
                subjects=subject_summaries,
            )
        )

    # 按班级名排序
    summaries.sort(key=lambda x: x.class_name)
    return summaries


def _build_subject_summaries(members: list) -> list[SubjectSummary]:
    """构建单科班级统计"""
    # 按 subject_id 聚合
    subject_scores: dict = defaultdict(list)
    subject_info: dict = {}

    for sd in members:
        for sub in sd["subjects"]:
            sid = sub.subject_id
            subject_info[sid] = (sub.subject_name, sub.full_score)
            if sub.score is not None and not sub.is_absent:
                subject_scores[sid].append(float(sub.score))

    summaries = []
    for sid, scores in subject_scores.items():
        name, full = subject_info.get(sid, ("未知", Decimal("100")))
        if not scores:
            continue

        n = len(scores)
        avg_s = round(sum(scores) / n, 2)
        max_s = round(max(scores), 2)
        min_s = round(min(scores), 2)
        full_f = float(full)
        pass_r = round(sum(1 for s in scores if s >= full_f * 0.6) / n * 100, 1)
        excel_r = round(sum(1 for s in scores if s >= full_f * 0.9) / n * 100, 1)

        summaries.append(
            SubjectSummary(
                subject_id=sid,
                subject_name=name,
                full_score=full,
                avg_score=avg_s,
                max_score=max_s,
                min_score=min_s,
                pass_rate=pass_r,
                excellent_rate=excel_r,
            )
        )

    summaries.sort(key=lambda x: x.subject_name)
    return summaries


def _scores_differ(a: Decimal | None, b: Decimal | None) -> bool:
    """判断两个分数是否不同（处理 None vs Decimal 比较）"""
    if a is None and b is None:
        return False
    if a is None or b is None:
        return True
    return a != b


def _exam_to_out(exam: GradeExam) -> "ExamOut":
    """ORM → Pydantic（避免循环导入）"""
    from .schemas import ExamOut

    return ExamOut(
        id=exam.id,
        name=exam.name,
        exam_type=exam.exam_type,
        grade_id=exam.grade_id,
        semester=exam.semester,
        exam_date=exam.exam_date,
        status=exam.status,
        created_by=exam.created_by,
        created_at=exam.created_at,
        updated_at=exam.updated_at,
    )
