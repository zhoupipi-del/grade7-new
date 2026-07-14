"""
modules/exam/services.py — 考试管理业务逻辑层

服务类:
- SubjectScheduleService: 考试科目安排 CRUD
- RoomService:            考场 CRUD + 从班级表批量生成
- ArrangementService:     排考 CRUD（科目×考场×时间段）
- SeatService:            座位编排（random/serpentine）+ 手动覆盖保护（补丁3）
- InvigilatorService:     监考指派 + 时间重叠冲突检测（补丁2）
- EntryWindowService:     录入窗口状态机 + 全校通开支持（补丁1）

三大补丁落地:
  补丁1: entry window class_id=NULL 全校通开，非NULL精确到班级
  补丁2: 监考时间重叠冲突在 assign_invigilator() 做前置校验，冲突抛 ValueError→409
  补丁3: 座位重排时 is_manual_override=1 的坑位跳过，保护特殊需求
"""

from __future__ import annotations

import logging
import random
from datetime import date, datetime
from decimal import Decimal

from core.models import Class as ClassModel
from core.models import Student, User
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    ExamArrangement,
    ExamInvigilator,
    ExamRoom,
    ExamScoreEntryWindow,
    ExamSeatAssignment,
    ExamSubject,
)
from .schemas import (
    ArrangementCreate,
    ArrangementUpdate,
    EntryWindowBulkCreateRequest,
    EntryWindowBulkCreateResult,
    EntryWindowCreate,
    InvigilatorCreate,
    RoomCreate,
    RoomSeedRequest,
    RoomSeedResult,
    RoomUpdate,
    SeatAssignRequest,
    SeatAssignResult,
    SeatOverrideUpdate,
    SubjectScheduleCreate,
    SubjectScheduleUpdate,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# SubjectScheduleService — 考试科目安排
# ═══════════════════════════════════════════════════════════════


class SubjectScheduleService:
    """考试科目安排 — 每场考试考哪些科目，每科的时间/满分"""

    @staticmethod
    async def create(
        db: AsyncSession,
        school_id: int,
        data: SubjectScheduleCreate,
    ) -> ExamSubject:
        """创建考试科目安排"""
        schedule = ExamSubject(
            school_id=school_id,
            exam_id=data.exam_id,
            subject_id=data.subject_id,
            exam_date=data.exam_date,
            start_time=data.start_time,
            end_time=data.end_time,
            full_score=data.full_score,
            sort_order=data.sort_order,
        )
        db.add(schedule)
        await db.commit()
        await db.refresh(schedule)
        return schedule

    @staticmethod
    async def list_by_exam(
        db: AsyncSession,
        school_id: int,
        exam_id: int,
        active_only: bool = False,
    ) -> list[ExamSubject]:
        """列出某场考试的科目安排"""
        stmt = (
            select(ExamSubject)
            .where(
                ExamSubject.school_id == school_id,
                ExamSubject.exam_id == exam_id,
            )
            .order_by(ExamSubject.sort_order.asc(), ExamSubject.exam_date.asc())
        )
        if active_only:
            stmt = stmt.where(ExamSubject.is_active == True)

        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get(
        db: AsyncSession,
        school_id: int,
        schedule_id: int,
    ) -> ExamSubject | None:
        """获取单个科目安排"""
        result = await db.execute(
            select(ExamSubject).where(
                ExamSubject.id == schedule_id,
                ExamSubject.school_id == school_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def update(
        db: AsyncSession,
        school_id: int,
        schedule_id: int,
        data: SubjectScheduleUpdate,
    ) -> ExamSubject:
        """更新科目安排"""
        schedule = await SubjectScheduleService.get(db, school_id, schedule_id)
        if not schedule:
            raise ValueError(f"科目安排不存在: id={schedule_id}")

        update_data = data.model_dump(exclude_unset=True)
        if not update_data:
            raise ValueError("无有效更新字段")

        for key, value in update_data.items():
            setattr(schedule, key, value)

        schedule.updated_at = datetime.now()
        await db.commit()
        await db.refresh(schedule)
        return schedule

    @staticmethod
    async def delete(
        db: AsyncSession,
        school_id: int,
        schedule_id: int,
    ) -> bool:
        """删除科目安排"""
        schedule = await SubjectScheduleService.get(db, school_id, schedule_id)
        if not schedule:
            raise ValueError(f"科目安排不存在: id={schedule_id}")

        await db.delete(schedule)
        await db.commit()
        return True


# ═══════════════════════════════════════════════════════════════
# RoomService — 考场管理
# ═══════════════════════════════════════════════════════════════


class RoomService:
    """考场 CRUD + 从班级表批量生成"""

    @staticmethod
    async def create(
        db: AsyncSession,
        school_id: int,
        data: RoomCreate,
    ) -> ExamRoom:
        """创建考场"""
        room = ExamRoom(
            school_id=school_id,
            room_name=data.room_name,
            room_code=data.room_code,
            building=data.building,
            floor=data.floor,
            capacity=data.capacity,
            room_type=data.room_type,
            class_id=data.class_id,
        )
        db.add(room)
        await db.commit()
        await db.refresh(room)
        return room

    @staticmethod
    async def list(
        db: AsyncSession,
        school_id: int,
        room_type: str | None = None,
        active_only: bool = False,
    ) -> list[ExamRoom]:
        """列出考场"""
        stmt = (
            select(ExamRoom)
            .where(ExamRoom.school_id == school_id)
            .order_by(ExamRoom.room_code.asc(), ExamRoom.id.asc())
        )
        if room_type:
            stmt = stmt.where(ExamRoom.room_type == room_type)
        if active_only:
            stmt = stmt.where(ExamRoom.is_active == True)

        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get(
        db: AsyncSession,
        school_id: int,
        room_id: int,
    ) -> ExamRoom | None:
        """获取单个考场"""
        result = await db.execute(
            select(ExamRoom).where(
                ExamRoom.id == room_id,
                ExamRoom.school_id == school_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def update(
        db: AsyncSession,
        school_id: int,
        room_id: int,
        data: RoomUpdate,
    ) -> ExamRoom:
        """更新考场"""
        room = await RoomService.get(db, school_id, room_id)
        if not room:
            raise ValueError(f"考场不存在: id={room_id}")

        update_data = data.model_dump(exclude_unset=True)
        if not update_data:
            raise ValueError("无有效更新字段")

        for key, value in update_data.items():
            setattr(room, key, value)

        room.updated_at = datetime.now()
        await db.commit()
        await db.refresh(room)
        return room

    @staticmethod
    async def toggle_active(
        db: AsyncSession,
        school_id: int,
        room_id: int,
    ) -> ExamRoom:
        """切换考场启用状态"""
        room = await RoomService.get(db, school_id, room_id)
        if not room:
            raise ValueError(f"考场不存在: id={room_id}")

        room.is_active = not room.is_active
        room.updated_at = datetime.now()
        await db.commit()
        await db.refresh(room)
        return room

    @staticmethod
    async def seed_from_classes(
        db: AsyncSession,
        school_id: int,
        data: RoomSeedRequest,
    ) -> RoomSeedResult:
        """从班级表自动生成考场记录

        把 classes 表中的教室初始化为考场，已存在的跳过。
        """
        # 查询班级
        stmt = select(ClassModel).where(
            ClassModel.school_id == school_id,
            ClassModel.is_active == True,
        )
        if data.class_ids:
            stmt = stmt.where(ClassModel.id.in_(data.class_ids))

        result = await db.execute(stmt)
        classes = list(result.scalars().all())

        # 查询已有的 class_id 对应考场
        existing_result = await db.execute(
            select(ExamRoom.class_id).where(
                ExamRoom.school_id == school_id,
                ExamRoom.class_id.isnot(None),
            )
        )
        existing_class_ids = {row[0] for row in existing_result.all()}

        created = 0
        skipped = 0
        room_ids: list[int] = []

        for cls in classes:
            if cls.id in existing_class_ids:
                skipped += 1
                continue

            room = ExamRoom(
                school_id=school_id,
                room_name=f"{cls.name}教室",
                room_code=f"R-{cls.id}",
                capacity=data.capacity,
                room_type="classroom",
                class_id=cls.id,
            )
            db.add(room)
            created += 1

        if created > 0:
            await db.commit()
            # 获取新创建的考场 ID
            for cls in classes:
                r = await db.execute(
                    select(ExamRoom.id).where(
                        ExamRoom.school_id == school_id,
                        ExamRoom.class_id == cls.id,
                    )
                )
                row = r.scalar_one_or_none()
                if row:
                    room_ids.append(row)

        return RoomSeedResult(
            created=created,
            skipped=skipped,
            room_ids=room_ids,
        )


# ═══════════════════════════════════════════════════════════════
# ArrangementService — 考试安排（排考）
# ═══════════════════════════════════════════════════════════════


class ArrangementService:
    """排考 — 科目×考场×时间段"""

    @staticmethod
    async def create(
        db: AsyncSession,
        school_id: int,
        data: ArrangementCreate,
    ) -> ExamArrangement:
        """创建考试安排"""
        # 前置校验：开始时间 < 结束时间
        if data.start_time >= data.end_time:
            raise ValueError("开始时间必须早于结束时间")

        arrangement = ExamArrangement(
            school_id=school_id,
            exam_id=data.exam_id,
            subject_id=data.subject_id,
            room_id=data.room_id,
            exam_date=data.exam_date,
            start_time=data.start_time,
            end_time=data.end_time,
            notes=data.notes,
        )
        db.add(arrangement)
        await db.commit()
        await db.refresh(arrangement)
        return arrangement

    @staticmethod
    async def list(
        db: AsyncSession,
        school_id: int,
        exam_id: int | None = None,
        subject_id: int | None = None,
        room_id: int | None = None,
        exam_date: date | None = None,
    ) -> list[ExamArrangement]:
        """列出考试安排（多维度过滤）"""
        stmt = (
            select(ExamArrangement)
            .where(ExamArrangement.school_id == school_id)
            .order_by(
                ExamArrangement.exam_date.asc(),
                ExamArrangement.start_time.asc(),
                ExamArrangement.id.asc(),
            )
        )
        if exam_id is not None:
            stmt = stmt.where(ExamArrangement.exam_id == exam_id)
        if subject_id is not None:
            stmt = stmt.where(ExamArrangement.subject_id == subject_id)
        if room_id is not None:
            stmt = stmt.where(ExamArrangement.room_id == room_id)
        if exam_date is not None:
            stmt = stmt.where(ExamArrangement.exam_date == exam_date)

        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get(
        db: AsyncSession,
        school_id: int,
        arrangement_id: int,
    ) -> ExamArrangement | None:
        """获取单个考试安排"""
        result = await db.execute(
            select(ExamArrangement).where(
                ExamArrangement.id == arrangement_id,
                ExamArrangement.school_id == school_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def update(
        db: AsyncSession,
        school_id: int,
        arrangement_id: int,
        data: ArrangementUpdate,
    ) -> ExamArrangement:
        """更新考试安排"""
        arrangement = await ArrangementService.get(db, school_id, arrangement_id)
        if not arrangement:
            raise ValueError(f"考试安排不存在: id={arrangement_id}")

        update_data = data.model_dump(exclude_unset=True)
        if not update_data:
            raise ValueError("无有效更新字段")

        for key, value in update_data.items():
            setattr(arrangement, key, value)

        # 校验时间
        if arrangement.start_time >= arrangement.end_time:
            raise ValueError("开始时间必须早于结束时间")

        arrangement.updated_at = datetime.now()
        await db.commit()
        await db.refresh(arrangement)
        return arrangement

    @staticmethod
    async def delete(
        db: AsyncSession,
        school_id: int,
        arrangement_id: int,
    ) -> bool:
        """删除考试安排"""
        arrangement = await ArrangementService.get(db, school_id, arrangement_id)
        if not arrangement:
            raise ValueError(f"考试安排不存在: id={arrangement_id}")

        await db.delete(arrangement)
        await db.commit()
        return True


# ═══════════════════════════════════════════════════════════════
# SeatService — 座位编排（含补丁3: 人工覆盖保护）
# ═══════════════════════════════════════════════════════════════


class SeatService:
    """座位编排 — random / serpentine / manual

    ⚠️ 补丁3: is_manual_override=1 的座位在算法重排时跳过，保护特殊需求。
    """

    @staticmethod
    async def assign_seats(
        db: AsyncSession,
        school_id: int,
        data: SeatAssignRequest,
    ) -> SeatAssignResult:
        """批量编排座位

        流程:
        1. 查询已有 is_manual_override=1 的座位 → 保留
        2. 删除该 exam+subject 的所有非覆盖座位
        3. 获取待分配学生（排除已在覆盖座位中的）
        4. 获取考场列表及剩余容量
        5. 按 arrangement_method 分配座位
        """
        # ── 1. 查询已有的人工覆盖座位 ──────────────
        override_result = await db.execute(
            select(ExamSeatAssignment).where(
                ExamSeatAssignment.school_id == school_id,
                ExamSeatAssignment.exam_id == data.exam_id,
                ExamSeatAssignment.subject_id == data.subject_id,
                ExamSeatAssignment.is_manual_override == True,
            )
        )
        override_seats = list(override_result.scalars().all())
        override_student_ids = {s.student_id for s in override_seats}
        override_room_seats: dict[int, set[int]] = {}  # room_id -> {seat_numbers}
        for s in override_seats:
            override_room_seats.setdefault(s.room_id, set()).add(s.seat_number)

        # ── 2. 删除非覆盖座位 ──────────────────────
        await db.execute(
            delete(ExamSeatAssignment).where(
                ExamSeatAssignment.school_id == school_id,
                ExamSeatAssignment.exam_id == data.exam_id,
                ExamSeatAssignment.subject_id == data.subject_id,
                ExamSeatAssignment.is_manual_override == False,
            )
        )

        # ── 3. 获取待分配学生 ──────────────────────
        student_stmt = select(Student).where(
            Student.school_id == school_id,
            Student.is_active == True,
        )
        if data.class_ids:
            student_stmt = student_stmt.where(Student.class_id.in_(data.class_ids))

        # 排除已在覆盖座位中的学生
        if override_student_ids:
            student_stmt = student_stmt.where(Student.id.notin_(override_student_ids))

        student_result = await db.execute(student_stmt)
        students = list(student_result.scalars().all())

        if not students:
            await db.commit()
            return SeatAssignResult(
                exam_id=data.exam_id,
                subject_id=data.subject_id,
                method=data.arrangement_method,
                total_assigned=0,
                rooms_used=0,
                manual_overrides_preserved=len(override_seats),
            )

        # ── 4. 获取考场列表 ────────────────────────
        if data.room_ids:
            room_stmt = (
                select(ExamRoom)
                .where(
                    ExamRoom.school_id == school_id,
                    ExamRoom.id.in_(data.room_ids),
                    ExamRoom.is_active == True,
                )
                .order_by(ExamRoom.id.asc())
            )
        else:
            # 从 exam_arrangements 获取该科目已安排的考场
            room_stmt = (
                select(ExamRoom)
                .join(ExamArrangement, ExamArrangement.room_id == ExamRoom.id)
                .where(
                    ExamArrangement.school_id == school_id,
                    ExamArrangement.exam_id == data.exam_id,
                    ExamArrangement.subject_id == data.subject_id,
                    ExamRoom.is_active == True,
                )
                .order_by(ExamRoom.id.asc())
            )

        room_result = await db.execute(room_stmt)
        rooms = list(room_result.scalars().all())

        if not rooms:
            await db.commit()
            return SeatAssignResult(
                exam_id=data.exam_id,
                subject_id=data.subject_id,
                method=data.arrangement_method,
                total_assigned=0,
                rooms_used=0,
                manual_overrides_preserved=len(override_seats),
            )

        # ── 5. 按编排方式分配 ──────────────────────
        if data.arrangement_method == "serpentine":
            # 蛇形编排：按总分排名蛇形分配
            students = await SeatService._sort_students_by_score(db, school_id, students)

        elif data.arrangement_method == "random":
            # 随机编排
            random.shuffle(students)

        # 分配座位（蛇形/随机都是同一种填入逻辑，区别只是学生排序）
        assignments = SeatService._distribute_seats(
            students,
            rooms,
            override_room_seats,
            data.exam_id,
            data.subject_id,
            school_id,
            data.arrangement_method,
        )

        for a in assignments:
            db.add(a)

        await db.commit()

        return SeatAssignResult(
            exam_id=data.exam_id,
            subject_id=data.subject_id,
            method=data.arrangement_method,
            total_assigned=len(assignments),
            rooms_used=len({a.room_id for a in assignments}),
            manual_overrides_preserved=len(override_seats),
        )

    @staticmethod
    async def list_by_exam_subject(
        db: AsyncSession,
        school_id: int,
        exam_id: int,
        subject_id: int,
        room_id: int | None = None,
    ) -> list[dict]:
        """查询座位分配（含学生姓名、考场名）"""
        stmt = (
            select(
                ExamSeatAssignment,
                Student.name.label("student_name"),
                ExamRoom.room_name.label("room_name"),
            )
            .join(Student, ExamSeatAssignment.student_id == Student.id)
            .join(ExamRoom, ExamSeatAssignment.room_id == ExamRoom.id)
            .where(
                ExamSeatAssignment.school_id == school_id,
                ExamSeatAssignment.exam_id == exam_id,
                ExamSeatAssignment.subject_id == subject_id,
            )
            .order_by(ExamSeatAssignment.room_id.asc(), ExamSeatAssignment.seat_number.asc())
        )
        if room_id is not None:
            stmt = stmt.where(ExamSeatAssignment.room_id == room_id)

        result = await db.execute(stmt)
        rows = result.all()

        return [
            {
                "id": row[0].id,
                "exam_id": row[0].exam_id,
                "subject_id": row[0].subject_id,
                "student_id": row[0].student_id,
                "room_id": row[0].room_id,
                "seat_number": row[0].seat_number,
                "arrangement_method": row[0].arrangement_method,
                "is_manual_override": row[0].is_manual_override,
                "remark": row[0].remark,
                "created_at": row[0].created_at,
                "student_name": row[1],
                "room_name": row[2],
            }
            for row in rows
        ]

    @staticmethod
    async def manual_override(
        db: AsyncSession,
        school_id: int,
        assignment_id: int,
        data: SeatOverrideUpdate,
    ) -> ExamSeatAssignment:
        """手动修改座位（补丁3: 设为 is_manual_override=1）

        用于特殊需求：伤残/视力障碍/靠门第一排等。
        修改后算法重排时跳过此座位。
        """
        # 查找原有座位
        result = await db.execute(
            select(ExamSeatAssignment).where(
                ExamSeatAssignment.id == assignment_id,
                ExamSeatAssignment.school_id == school_id,
            )
        )
        assignment = result.scalar_one_or_none()
        if not assignment:
            raise ValueError(f"座位分配不存在: id={assignment_id}")

        # 检查目标位置是否已被占用
        conflict_result = await db.execute(
            select(ExamSeatAssignment).where(
                ExamSeatAssignment.school_id == school_id,
                ExamSeatAssignment.exam_id == assignment.exam_id,
                ExamSeatAssignment.subject_id == assignment.subject_id,
                ExamSeatAssignment.room_id == data.room_id,
                ExamSeatAssignment.seat_number == data.seat_number,
                ExamSeatAssignment.student_id != assignment.student_id,
            )
        )
        if conflict_result.scalar_one_or_none():
            raise ValueError(
                f"目标座位已被其他学生占用: room_id={data.room_id}, seat={data.seat_number}"
            )

        # 更新座位信息并标记为人工覆盖
        assignment.room_id = data.room_id
        assignment.seat_number = data.seat_number
        assignment.is_manual_override = True
        assignment.arrangement_method = "manual"
        if data.remark:
            assignment.remark = data.remark

        await db.commit()
        await db.refresh(assignment)
        return assignment

    @staticmethod
    async def _sort_students_by_score(
        db: AsyncSession,
        school_id: int,
        students: list[Student],
    ) -> list[Student]:
        """按最近一次考试总分降序排序（用于蛇形编排）

        如果没有历史成绩，则按学号排序（退化为确定性排序）。
        """
        if not students:
            return students

        student_ids = [s.id for s in students]

        # 查询每个学生最近一次考试的总分
        score_result = await db.execute(
            text("""
                SELECT gr.student_id, COALESCE(SUM(gr.score), 0) AS total
                FROM grades_records gr
                WHERE gr.school_id = :school_id
                  AND gr.student_id IN :student_ids
                  AND gr.score IS NOT NULL
                  AND gr.is_absent = 0
                  AND gr.exam_id = (
                      SELECT MAX(id) FROM grades_exams
                      WHERE school_id = :school_id AND status = 'published'
                  )
                GROUP BY gr.student_id
            """),
            {"school_id": school_id, "student_ids": tuple(student_ids)},
        )
        score_map = {row[0]: row[1] for row in score_result.all()}

        # 按总分降序，无成绩的排最后
        students.sort(
            key=lambda s: (score_map.get(s.id, Decimal("-1")), s.id),
            reverse=True,
        )
        return students

    @staticmethod
    def _distribute_seats(
        students: list[Student],
        rooms: list[ExamRoom],
        override_room_seats: dict[int, set[int]],
        exam_id: int,
        subject_id: int,
        school_id: int,
        method: str,
    ) -> list[ExamSeatAssignment]:
        """将学生分配到考场座位

        蛇形/随机通用逻辑：
        - 按 rooms 顺序依次填充
        - 每个考场从座位号 1 开始，跳过已被 override 占用的座位
        - 蛇形模式下：偶数轮（第2/4/6...个考场批次）反向填充座位号

        实际上蛇形的核心在于学生排序（已由调用方完成），
        这里只需要按顺序填入即可。
        """
        assignments: list[ExamSeatAssignment] = []
        student_idx = 0
        total_students = len(students)

        for room in rooms:
            if student_idx >= total_students:
                break

            occupied = override_room_seats.get(room.id, set())
            seat = 1

            while student_idx < total_students and seat <= room.capacity:
                # 跳过已被人工覆盖占用的座位
                if seat in occupied:
                    seat += 1
                    continue

                student = students[student_idx]
                assignments.append(
                    ExamSeatAssignment(
                        school_id=school_id,
                        exam_id=exam_id,
                        subject_id=subject_id,
                        student_id=student.id,
                        room_id=room.id,
                        seat_number=seat,
                        arrangement_method=method,
                        is_manual_override=False,
                    )
                )
                student_idx += 1
                seat += 1

        return assignments


# ═══════════════════════════════════════════════════════════════
# InvigilatorService — 监考安排（含补丁2: 时间重叠冲突检测）
# ═══════════════════════════════════════════════════════════════


class InvigilatorService:
    """监考指派 — 主/副监考×冲突检测

    ⚠️ 补丁2: UNIQUE KEY 只能防同一考场重复指派，无法防时间重叠冲突
       (同一教师同一时段被指派到两个不同考场)
       时间重叠冲突在此做前置校验：查 teacher_id 在 (exam_date, start_time, end_time)
       范围内是否已有活跃监考记录，有则抛 ValueError → 路由层转 409 Conflict
    """

    @staticmethod
    async def assign(
        db: AsyncSession,
        school_id: int,
        data: InvigilatorCreate,
    ) -> ExamInvigilator:
        """指派监考教师

        前置校验:
        1. 开始时间 < 结束时间
        2. ⚠️ 补丁2: 时间重叠冲突检测 — 同一教师同一日期的时间段不可重叠
        """
        # ── 校验1: 时间合法性 ──────────────────────
        if data.start_time >= data.end_time:
            raise ValueError("开始时间必须早于结束时间")

        # ── ⚠️ 补丁2: 时间重叠冲突检测 ─────────────
        # 查询该教师在该日期是否已有时间段重叠的监考记录
        # 重叠条件: existing.start_time < new.end_time AND existing.end_time > new.start_time
        conflict_result = await db.execute(
            select(ExamInvigilator).where(
                ExamInvigilator.school_id == school_id,
                ExamInvigilator.user_id == data.user_id,
                ExamInvigilator.exam_date == data.exam_date,
                ExamInvigilator.start_time < data.end_time,
                ExamInvigilator.end_time > data.start_time,
            )
        )
        existing = conflict_result.scalar_one_or_none()

        if existing:
            raise ValueError(
                f"TIME_OVERLAP_CONFLICT: 教师 user_id={data.user_id} "
                f"在 {data.exam_date} {existing.start_time}~{existing.end_time} "
                f"已有监考安排 (room_id={existing.room_id})，"
                f"与新安排 {data.start_time}~{data.end_time} 时间重叠"
            )

        # ── 创建监考记录 ────────────────────────────
        invigilator = ExamInvigilator(
            school_id=school_id,
            exam_id=data.exam_id,
            subject_id=data.subject_id,
            room_id=data.room_id,
            user_id=data.user_id,
            role=data.role,
            exam_date=data.exam_date,
            start_time=data.start_time,
            end_time=data.end_time,
            notes=data.notes,
        )
        db.add(invigilator)
        await db.commit()
        await db.refresh(invigilator)
        return invigilator

    @staticmethod
    async def list(
        db: AsyncSession,
        school_id: int,
        exam_id: int | None = None,
        subject_id: int | None = None,
        room_id: int | None = None,
        user_id: int | None = None,
        exam_date: date | None = None,
    ) -> list[dict]:
        """查询监考安排（含教师姓名、考场名）"""
        stmt = (
            select(
                ExamInvigilator,
                User.display_name.label("user_name"),
                ExamRoom.room_name.label("room_name"),
            )
            .join(User, ExamInvigilator.user_id == User.id)
            .join(ExamRoom, ExamInvigilator.room_id == ExamRoom.id)
            .where(ExamInvigilator.school_id == school_id)
            .order_by(
                ExamInvigilator.exam_date.asc(),
                ExamInvigilator.start_time.asc(),
                ExamInvigilator.room_id.asc(),
            )
        )
        if exam_id is not None:
            stmt = stmt.where(ExamInvigilator.exam_id == exam_id)
        if subject_id is not None:
            stmt = stmt.where(ExamInvigilator.subject_id == subject_id)
        if room_id is not None:
            stmt = stmt.where(ExamInvigilator.room_id == room_id)
        if user_id is not None:
            stmt = stmt.where(ExamInvigilator.user_id == user_id)
        if exam_date is not None:
            stmt = stmt.where(ExamInvigilator.exam_date == exam_date)

        result = await db.execute(stmt)
        rows = result.all()

        return [
            {
                "id": row[0].id,
                "exam_id": row[0].exam_id,
                "subject_id": row[0].subject_id,
                "room_id": row[0].room_id,
                "user_id": row[0].user_id,
                "role": row[0].role,
                "exam_date": row[0].exam_date,
                "start_time": row[0].start_time,
                "end_time": row[0].end_time,
                "notes": row[0].notes,
                "created_at": row[0].created_at,
                "updated_at": row[0].updated_at,
                "user_name": row[1],
                "room_name": row[2],
            }
            for row in rows
        ]

    @staticmethod
    async def delete(
        db: AsyncSession,
        school_id: int,
        invigilator_id: int,
    ) -> bool:
        """取消监考安排"""
        result = await db.execute(
            select(ExamInvigilator).where(
                ExamInvigilator.id == invigilator_id,
                ExamInvigilator.school_id == school_id,
            )
        )
        invigilator = result.scalar_one_or_none()
        if not invigilator:
            raise ValueError(f"监考安排不存在: id={invigilator_id}")

        await db.delete(invigilator)
        await db.commit()
        return True

    @staticmethod
    async def check_conflicts(
        db: AsyncSession,
        school_id: int,
        user_id: int,
    ) -> list[dict]:
        """查询某教师的监考时间冲突列表

        扫描该教师所有监考安排，找出存在时间段重叠的记录对。
        """
        result = await db.execute(
            text("""
                SELECT
                    a.id AS id_a, a.exam_id AS exam_a, a.room_id AS room_a,
                    a.exam_date AS date_a, a.start_time AS start_a, a.end_time AS end_a,
                    b.id AS id_b, b.exam_id AS exam_b, b.room_id AS room_b,
                    b.start_time AS start_b, b.end_time AS end_b
                FROM exam_invigilators a
                JOIN exam_invigilators b ON a.user_id = b.user_id
                    AND a.exam_date = b.exam_date
                    AND a.id < b.id
                    AND a.start_time < b.end_time
                    AND a.end_time > b.start_time
                WHERE a.school_id = :school_id
                  AND a.user_id = :user_id
                ORDER BY a.exam_date, a.start_time
            """),
            {"school_id": school_id, "user_id": user_id},
        )
        rows = result.all()

        conflicts = []
        for row in rows:
            conflicts.append(
                {
                    "existing_id": row[0],
                    "existing_exam_id": row[1],
                    "existing_room_id": row[2],
                    "existing_room_name": f"room_{row[2]}",
                    "existing_start_time": row[4],
                    "existing_end_time": row[5],
                    "conflict_with_id": row[6],
                    "conflict_exam_id": row[7],
                    "conflict_room_id": row[8],
                    "conflict_start_time": row[9],
                    "conflict_end_time": row[10],
                }
            )

        return conflicts


# ═══════════════════════════════════════════════════════════════
# EntryWindowService — 成绩录入窗口（含补丁1: class_id=NULL全校通开）
# ═══════════════════════════════════════════════════════════════


class EntryWindowService:
    """成绩录入窗口 — pending → open → closed 状态机

    ⚠️ 补丁1: class_id 可为 NULL
       NULL = 全校该科目通开（粗粒度场景）
       非NULL = 精确到班级，防止跨班级篡改和进度不一

    查询录入权限时：
    1. 先查 class-specific 窗口 (class_id = 指定班级)
    2. 如无，再查 school-wide 窗口 (class_id IS NULL)
    3. 任一 open 即可录入
    """

    @staticmethod
    async def create(
        db: AsyncSession,
        school_id: int,
        data: EntryWindowCreate,
    ) -> ExamScoreEntryWindow:
        """创建录入窗口

        ⚠️ 补丁1: class_id=NULL 表示全校通开
        """
        # 如果指定了 class_id，自动填充 expected_count
        expected_count = None
        if data.class_id is not None:
            count_result = await db.execute(
                select(func.count(Student.id)).where(
                    Student.school_id == school_id,
                    Student.class_id == data.class_id,
                    Student.is_active == True,
                )
            )
            expected_count = count_result.scalar() or 0

        window = ExamScoreEntryWindow(
            school_id=school_id,
            exam_id=data.exam_id,
            subject_id=data.subject_id,
            class_id=data.class_id,
            expected_count=expected_count,
        )
        db.add(window)
        await db.commit()
        await db.refresh(window)
        return window

    @staticmethod
    async def bulk_create(
        db: AsyncSession,
        school_id: int,
        data: EntryWindowBulkCreateRequest,
    ) -> EntryWindowBulkCreateResult:
        """批量创建录入窗口 — 为一场考试的所有科目×所有班级批量创建"""
        # 获取该考试的所有科目
        subject_result = await db.execute(
            select(ExamSubject.subject_id)
            .where(
                ExamSubject.school_id == school_id,
                ExamSubject.exam_id == data.exam_id,
                ExamSubject.is_active == True,
            )
            .distinct()
        )
        subject_ids = [row[0] for row in subject_result.all()]

        if not subject_ids:
            raise ValueError(f"考试 {data.exam_id} 没有已安排的科目")

        # 获取班级列表
        class_ids = data.class_ids
        if not class_ids and not data.school_wide:
            class_result = await db.execute(
                select(ClassModel.id).where(
                    ClassModel.school_id == school_id,
                    ClassModel.is_active == True,
                )
            )
            class_ids = [row[0] for row in class_result.all()]

        # 查询已有窗口，避免重复
        existing_result = await db.execute(
            select(
                ExamScoreEntryWindow.subject_id,
                ExamScoreEntryWindow.class_id,
            ).where(
                ExamScoreEntryWindow.school_id == school_id,
                ExamScoreEntryWindow.exam_id == data.exam_id,
            )
        )
        existing_set = {(row[0], row[1]) for row in existing_result.all()}

        created = 0
        skipped = 0
        window_ids: list[int] = []

        # 为每个科目创建窗口
        for subject_id in subject_ids:
            if data.school_wide:
                # 全校通开窗口
                key = (subject_id, None)
                if key in existing_set:
                    skipped += 1
                    continue

                window = ExamScoreEntryWindow(
                    school_id=school_id,
                    exam_id=data.exam_id,
                    subject_id=subject_id,
                    class_id=None,
                )
                db.add(window)
                created += 1
            else:
                # 按班级创建
                for class_id in class_ids or []:
                    key = (subject_id, class_id)
                    if key in existing_set:
                        skipped += 1
                        continue

                    # 获取班级人数
                    count_result = await db.execute(
                        select(func.count(Student.id)).where(
                            Student.school_id == school_id,
                            Student.class_id == class_id,
                            Student.is_active == True,
                        )
                    )
                    expected = count_result.scalar() or 0

                    window = ExamScoreEntryWindow(
                        school_id=school_id,
                        exam_id=data.exam_id,
                        subject_id=subject_id,
                        class_id=class_id,
                        expected_count=expected,
                    )
                    db.add(window)
                    created += 1

        if created > 0:
            await db.commit()
            # 获取新创建的窗口 ID
            new_result = await db.execute(
                select(ExamScoreEntryWindow.id).where(
                    ExamScoreEntryWindow.school_id == school_id,
                    ExamScoreEntryWindow.exam_id == data.exam_id,
                )
            )
            window_ids = [row[0] for row in new_result.all()]

        return EntryWindowBulkCreateResult(
            exam_id=data.exam_id,
            created=created,
            skipped=skipped,
            window_ids=window_ids,
        )

    @staticmethod
    async def list(
        db: AsyncSession,
        school_id: int,
        exam_id: int | None = None,
        subject_id: int | None = None,
        class_id: int | None = None,
        status: str | None = None,
    ) -> list[ExamScoreEntryWindow]:
        """查询录入窗口列表"""
        stmt = (
            select(ExamScoreEntryWindow)
            .where(ExamScoreEntryWindow.school_id == school_id)
            .order_by(
                ExamScoreEntryWindow.exam_id.asc(),
                ExamScoreEntryWindow.subject_id.asc(),
                ExamScoreEntryWindow.class_id.is_(None).asc(),  # NULL 排最后
                ExamScoreEntryWindow.class_id.asc(),
            )
        )
        if exam_id is not None:
            stmt = stmt.where(ExamScoreEntryWindow.exam_id == exam_id)
        if subject_id is not None:
            stmt = stmt.where(ExamScoreEntryWindow.subject_id == subject_id)
        if class_id is not None:
            stmt = stmt.where(ExamScoreEntryWindow.class_id == class_id)
        if status:
            stmt = stmt.where(ExamScoreEntryWindow.status == status)

        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def open_window(
        db: AsyncSession,
        school_id: int,
        window_id: int,
        user_id: int,
    ) -> ExamScoreEntryWindow:
        """开放录入窗口 (pending → open)"""
        result = await db.execute(
            select(ExamScoreEntryWindow).where(
                ExamScoreEntryWindow.id == window_id,
                ExamScoreEntryWindow.school_id == school_id,
            )
        )
        window = result.scalar_one_or_none()
        if not window:
            raise ValueError(f"录入窗口不存在: id={window_id}")

        if window.status != "pending":
            raise ValueError(f"窗口状态为 {window.status}，只有 pending 状态才能 open")

        window.status = "open"
        window.opened_at = datetime.now()
        window.opened_by = user_id
        window.updated_at = datetime.now()

        await db.commit()
        await db.refresh(window)
        return window

    @staticmethod
    async def close_window(
        db: AsyncSession,
        school_id: int,
        window_id: int,
        user_id: int,
    ) -> ExamScoreEntryWindow:
        """关闭录入窗口 (open → closed)"""
        result = await db.execute(
            select(ExamScoreEntryWindow).where(
                ExamScoreEntryWindow.id == window_id,
                ExamScoreEntryWindow.school_id == school_id,
            )
        )
        window = result.scalar_one_or_none()
        if not window:
            raise ValueError(f"录入窗口不存在: id={window_id}")

        if window.status != "open":
            raise ValueError(f"窗口状态为 {window.status}，只有 open 状态才能 close")

        window.status = "closed"
        window.closed_at = datetime.now()
        window.closed_by = user_id
        window.updated_at = datetime.now()

        await db.commit()
        await db.refresh(window)
        return window

    @staticmethod
    async def get_progress(
        db: AsyncSession,
        school_id: int,
        exam_id: int,
        subject_id: int | None = None,
    ) -> dict:
        """查询录入进度"""
        stmt = select(
            func.count().label("total_windows"),
            func.sum(ExamScoreEntryWindow.status == "open").label("open_count"),
            func.sum(ExamScoreEntryWindow.status == "closed").label("closed_count"),
            func.sum(ExamScoreEntryWindow.status == "pending").label("pending_count"),
            func.sum(ExamScoreEntryWindow.entry_count).label("total_entry"),
            func.sum(ExamScoreEntryWindow.expected_count).label("total_expected"),
        ).where(
            ExamScoreEntryWindow.school_id == school_id,
            ExamScoreEntryWindow.exam_id == exam_id,
        )
        if subject_id is not None:
            stmt = stmt.where(ExamScoreEntryWindow.subject_id == subject_id)

        result = await db.execute(stmt)
        row = result.one()

        total_windows = row[0] or 0
        open_windows = row[1] or 0
        closed_windows = row[2] or 0
        pending_windows = row[3] or 0
        total_entry = row[4] or 0
        total_expected = row[5]

        completion_rate = None
        if total_expected and total_expected > 0:
            completion_rate = round(total_entry / total_expected * 100, 1)

        return {
            "exam_id": exam_id,
            "subject_id": subject_id,
            "total_windows": total_windows,
            "open_windows": open_windows,
            "closed_windows": closed_windows,
            "pending_windows": pending_windows,
            "total_entry_count": total_entry,
            "total_expected_count": total_expected,
            "completion_rate": completion_rate,
        }

    @staticmethod
    async def check_entry_permission(
        db: AsyncSession,
        school_id: int,
        exam_id: int,
        subject_id: int,
        class_id: int,
    ) -> bool:
        """检查某班级某科目是否可以录入成绩

        ⚠️ 补丁1: 双重检查
        1. 先查 class-specific 窗口 (class_id = 指定班级)
        2. 如无，再查 school-wide 窗口 (class_id IS NULL)
        3. 任一 open 即可录入
        """
        # 查 class-specific 窗口
        class_result = await db.execute(
            select(ExamScoreEntryWindow).where(
                ExamScoreEntryWindow.school_id == school_id,
                ExamScoreEntryWindow.exam_id == exam_id,
                ExamScoreEntryWindow.subject_id == subject_id,
                ExamScoreEntryWindow.class_id == class_id,
                ExamScoreEntryWindow.status == "open",
            )
        )
        if class_result.scalar_one_or_none():
            return True

        # 查 school-wide 窗口 (class_id IS NULL)
        school_result = await db.execute(
            select(ExamScoreEntryWindow).where(
                ExamScoreEntryWindow.school_id == school_id,
                ExamScoreEntryWindow.exam_id == exam_id,
                ExamScoreEntryWindow.subject_id == subject_id,
                ExamScoreEntryWindow.class_id.is_(None),
                ExamScoreEntryWindow.status == "open",
            )
        )
        if school_result.scalar_one_or_none():
            return True

        return False

    @staticmethod
    async def increment_entry_count(
        db: AsyncSession,
        school_id: int,
        exam_id: int,
        subject_id: int,
        class_id: int,
        count: int = 1,
    ) -> None:
        """增加录入计数（成绩录入时调用）"""
        # 更新 class-specific 窗口
        result = await db.execute(
            select(ExamScoreEntryWindow).where(
                ExamScoreEntryWindow.school_id == school_id,
                ExamScoreEntryWindow.exam_id == exam_id,
                ExamScoreEntryWindow.subject_id == subject_id,
                ExamScoreEntryWindow.class_id == class_id,
            )
        )
        window = result.scalar_one_or_none()

        if window:
            window.entry_count += count
            window.updated_at = datetime.now()
            await db.commit()
            return

        # 如果没有 class-specific 窗口，更新 school-wide 窗口
        result = await db.execute(
            select(ExamScoreEntryWindow).where(
                ExamScoreEntryWindow.school_id == school_id,
                ExamScoreEntryWindow.exam_id == exam_id,
                ExamScoreEntryWindow.subject_id == subject_id,
                ExamScoreEntryWindow.class_id.is_(None),
            )
        )
        window = result.scalar_one_or_none()
        if window:
            window.entry_count += count
            window.updated_at = datetime.now()
            await db.commit()
