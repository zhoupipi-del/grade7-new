"""
timetable 业务逻辑层 — 适配生产DB列结构

提供: 教室/课程/课节 CRUD + 冲突检测 + 周视图生成
"""

import logging
from typing import Optional
from sqlalchemy import select, func, desc, and_
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import User, Class, Grade
from core.event_bus import EventBus
from modules.timetable.models import Classroom, Course, CourseSlot, ScheduleConflict
from modules.timetable.schemas import (
    ClassroomCreate, ClassroomOut,
    CourseCreate, CourseOut,
    CourseSlotCreate, CourseSlotOut,
    WeeklySlotOut, WeeklyScheduleOut,
    ConflictDetail, ConflictCheckResult, ConflictOut,
    TeacherWeeklySlotOut, TeacherWeeklyScheduleOut,
)

logger = logging.getLogger("timetable.services")


class TimetableService:

    # ── 教室管理 ──

    @staticmethod
    async def list_classrooms(
        db: AsyncSession, school_id: int,
        room_type: Optional[str] = None,
    ) -> list[ClassroomOut]:
        conditions = [Classroom.school_id == school_id, Classroom.is_active == True]
        if room_type:
            conditions.append(Classroom.room_type == room_type)

        result = await db.execute(
            select(Classroom)
            .where(and_(*conditions))
            .order_by(Classroom.building.asc(), Classroom.floor.asc(), Classroom.name.asc())
        )
        return [ClassroomOut.model_validate(r) for r in result.scalars().all()]

    @staticmethod
    async def create_classroom(
        db: AsyncSession, data: ClassroomCreate, school_id: int,
    ) -> ClassroomOut:
        cr = Classroom(school_id=school_id, **data.model_dump())
        db.add(cr)
        await db.commit()
        await db.refresh(cr)
        return ClassroomOut.model_validate(cr)

    # ── 课程管理 ──

    @staticmethod
    async def list_courses(
        db: AsyncSession, school_id: int,
        subject_category: Optional[str] = None,
    ) -> list[CourseOut]:
        conditions = [Course.school_id == school_id, Course.is_active == True]
        if subject_category:
            conditions.append(Course.subject_category == subject_category)

        result = await db.execute(
            select(Course)
            .where(and_(*conditions))
            .order_by(Course.weekly_slots.desc())
        )
        return [CourseOut.model_validate(c) for c in result.scalars().all()]

    @staticmethod
    async def create_course(
        db: AsyncSession, data: CourseCreate, school_id: int,
    ) -> CourseOut:
        c = Course(school_id=school_id, **data.model_dump())
        db.add(c)
        await db.commit()
        await db.refresh(c)
        return CourseOut.model_validate(c)

    # ── 课节管理 + 冲突检测 ──

    @staticmethod
    async def _check_conflicts(
        db: AsyncSession, slot: CourseSlotCreate, exclude_slot_id: Optional[int] = None,
        school_id: int = 1,
    ) -> ConflictCheckResult:
        conflicts: list[ConflictDetail] = []

        time_cond = and_(
            CourseSlot.day_of_week == slot.day_of_week,
            CourseSlot.slot_number == slot.slot_number,
            CourseSlot.semester == slot.semester,
            CourseSlot.is_active == True,
            CourseSlot.school_id == school_id,
        )

        # 1. 教师冲突
        teacher_cond = and_(time_cond, CourseSlot.teacher_id == slot.teacher_id)
        if exclude_slot_id:
            teacher_cond = and_(teacher_cond, CourseSlot.id != exclude_slot_id)
        t_result = await db.execute(select(CourseSlot).where(teacher_cond))
        for tc in t_result.scalars().all():
            if tc.class_id != slot.class_id:
                conflicts.append(ConflictDetail(
                    conflict_type="teacher", severity="error",
                    entity_a={"teacher_id": slot.teacher_id},
                    entity_b={"slot_id": tc.id, "class_id": tc.class_id},
                    conflict_detail=f"教师冲突: 教师在周{slot.day_of_week} 第{slot.slot_number}节已有排课",
                ))

        # 2. 教室冲突
        if slot.classroom_id:
            room_cond = and_(time_cond, CourseSlot.classroom_id == slot.classroom_id)
            if exclude_slot_id:
                room_cond = and_(room_cond, CourseSlot.id != exclude_slot_id)
            r_result = await db.execute(select(CourseSlot).where(room_cond))
            for rc in r_result.scalars().all():
                if rc.class_id != slot.class_id:
                    conflicts.append(ConflictDetail(
                        conflict_type="classroom", severity="error",
                        entity_a={"classroom_id": slot.classroom_id},
                        entity_b={"slot_id": rc.id, "class_id": rc.class_id},
                        conflict_detail=f"教室冲突: 教室在周{slot.day_of_week} 第{slot.slot_number}节已被占用",
                    ))

        # 3. 班级冲突
        class_cond = and_(time_cond, CourseSlot.class_id == slot.class_id)
        if exclude_slot_id:
            class_cond = and_(class_cond, CourseSlot.id != exclude_slot_id)
        c_result = await db.execute(select(CourseSlot).where(class_cond))
        for cc in c_result.scalars().all():
            if cc.course_id != slot.course_id:
                conflicts.append(ConflictDetail(
                    conflict_type="class", severity="error",
                    entity_a={"class_id": slot.class_id},
                    entity_b={"slot_id": cc.id, "course_id": cc.course_id},
                    conflict_detail=f"班级冲突: 班级在周{slot.day_of_week} 第{slot.slot_number}节已有其他课程",
                ))

        return ConflictCheckResult(
            has_conflicts=len(conflicts) > 0,
            conflict_count=len(conflicts),
            conflicts=conflicts,
        )

    @staticmethod
    async def create_slot(
        db: AsyncSession, data: CourseSlotCreate, school_id: int,
        auto_resolve: bool = False,
    ) -> dict:
        check = await TimetableService._check_conflicts(db, data, school_id=school_id)

        if check.has_conflicts and not auto_resolve:
            return {"created": False, "conflicts": check}

        slot = CourseSlot(school_id=school_id, **data.model_dump())
        db.add(slot)
        await db.commit()
        await db.refresh(slot)

        # ⚡ Wings 3.2 CEP: 课表变轨事件广播
        bus = EventBus()
        bus.publish("timetable.schedule_change", {
            "school_id": school_id,
            "slot_id": slot.id,
            "class_id": slot.class_id,
            "course_id": slot.course_id,
            "teacher_id": slot.teacher_id,
            "course_id": slot.course_id,
            "day_of_week": slot.day_of_week,
            "slot_number": slot.slot_number,
            "change_type": "slot_created",
            "has_conflicts": check.has_conflicts,
            "title": f"课表变动: 周{slot.day_of_week}第{slot.slot_number}节新增课程",
        })
        logger.info(
            f"[timetable] CEP published: slot={slot.id} "
            f"class={slot.class_id} week={slot.day_of_week} "
            f"period={slot.slot_number}"
        )

        if check.has_conflicts:
            for cf in check.conflicts:
                sc = ScheduleConflict(
                    school_id=school_id,
                    conflict_type=cf.conflict_type,
                    severity=cf.severity,
                    slot_id_1=slot.id,
                    slot_id_2=cf.entity_b.get("slot_id", 0) if cf.entity_b else 0,
                    description=cf.conflict_detail,
                )
                db.add(sc)
            await db.commit()

        return {"created": True, "slot_id": slot.id, "conflicts": check}

    @staticmethod
    async def list_slots(
        db: AsyncSession, school_id: int,
        class_id: Optional[int] = None,
        teacher_id: Optional[int] = None,
        semester: Optional[str] = None,
    ) -> list[CourseSlotOut]:
        conditions = [CourseSlot.school_id == school_id, CourseSlot.is_active == True]
        if class_id:
            conditions.append(CourseSlot.class_id == class_id)
        if teacher_id:
            conditions.append(CourseSlot.teacher_id == teacher_id)
        if semester:
            conditions.append(CourseSlot.semester == semester)

        result = await db.execute(
            select(CourseSlot)
            .where(and_(*conditions))
            .order_by(CourseSlot.day_of_week.asc(), CourseSlot.slot_number.asc())
        )
        slots = result.scalars().all()

        # 批量查询关联名称
        course_ids = list({s.course_id for s in slots})
        teacher_ids = list({s.teacher_id for s in slots})
        classroom_ids = list({s.classroom_id for s in slots if s.classroom_id})

        courses_map, teachers_map, classrooms_map = {}, {}, {}
        if course_ids:
            c_result = await db.execute(select(Course).where(Course.id.in_(course_ids)))
            courses_map = {c.id: c.name for c in c_result.scalars().all()}
        if teacher_ids:
            t_result = await db.execute(select(User).where(User.id.in_(teacher_ids)))
            teachers_map = {t.id: t.display_name for t in t_result.scalars().all()}
        if classroom_ids:
            r_result = await db.execute(select(Classroom).where(Classroom.id.in_(classroom_ids)))
            classrooms_map = {r.id: r.name for r in r_result.scalars().all()}

        return [
            CourseSlotOut(
                **{k: getattr(s, k) for k in CourseSlotOut.model_fields if hasattr(s, k)},
                course_name=courses_map.get(s.course_id, ""),
                teacher_name=teachers_map.get(s.teacher_id, ""),
                classroom_name=classrooms_map.get(s.classroom_id, "") if s.classroom_id else "",
            )
            for s in slots
        ]

    @staticmethod
    async def delete_slot(db: AsyncSession, slot_id: int) -> bool:
        result = await db.execute(select(CourseSlot).where(CourseSlot.id == slot_id))
        slot = result.scalar_one_or_none()
        if not slot:
            return False
        slot.is_active = False
        await db.commit()

        # ⚡ Wings 3.2 CEP: 课表变轨事件广播 (slot删除)
        bus = EventBus()
        bus.publish("timetable.schedule_change", {
            "school_id": slot.school_id,
            "slot_id": slot.id,
            "class_id": slot.class_id,
            "course_id": slot.course_id,
            "teacher_id": slot.teacher_id,
            "day_of_week": slot.day_of_week,
            "slot_number": slot.slot_number,
            "change_type": "slot_removed",
            "title": f"课表变动: 周{slot.day_of_week}第{slot.slot_number}节课程已移除",
        })
        logger.info(f"[timetable] CEP published (delete): slot={slot.id}")

        return True

    # ── 周视图 ──

    @staticmethod
    async def get_weekly_schedule(
        db: AsyncSession, class_id: int, semester: str, school_id: int,
    ) -> Optional[WeeklyScheduleOut]:
        cls_result = await db.execute(select(Class).where(Class.id == class_id))
        cls = cls_result.scalar_one_or_none()
        if not cls:
            return None

        grade_result = await db.execute(select(Grade).where(Grade.id == cls.grade_id))
        grade = grade_result.scalar_one_or_none()

        slots = await TimetableService.list_slots(db, school_id, class_id=class_id, semester=semester)

        schedule: dict[str, list[WeeklySlotOut]] = {str(d): [] for d in range(1, 8)}
        for s in slots:
            course_result = await db.execute(select(Course).where(Course.id == s.course_id))
            course = course_result.scalar_one_or_none()
            wso = WeeklySlotOut(
                id=s.id, course_name=s.course_name,
                subject_category=course.subject_category if course else "",
                teacher_name=s.teacher_name, classroom_name=s.classroom_name,
                slot_number=s.slot_number, week_pattern=s.week_pattern,
            )
            schedule[str(s.day_of_week)].append(wso)

        return WeeklyScheduleOut(
            class_id=class_id, class_name=cls.name,
            grade_name=grade.name if grade else "",
            semester=semester, schedule=schedule,
        )

    @staticmethod
    async def get_teacher_weekly_schedule(
        db: AsyncSession, teacher_id: int, semester: str, school_id: int,
    ) -> Optional[TeacherWeeklyScheduleOut]:
        user_result = await db.execute(select(User).where(User.id == teacher_id))
        user = user_result.scalar_one_or_none()
        if not user:
            return None

        slots = await TimetableService.list_slots(db, school_id, teacher_id=teacher_id, semester=semester)

        class_ids = list({s.class_id for s in slots})
        classes_map = {}
        if class_ids:
            c_result = await db.execute(select(Class).where(Class.id.in_(class_ids)))
            classes_map = {c.id: c.name for c in c_result.scalars().all()}

        schedule: dict[str, list[TeacherWeeklySlotOut]] = {str(d): [] for d in range(1, 8)}
        for s in slots:
            tws = TeacherWeeklySlotOut(
                id=s.id, class_name=classes_map.get(s.class_id, ""),
                course_name=s.course_name, classroom_name=s.classroom_name,
                slot_number=s.slot_number,
            )
            schedule[str(s.day_of_week)].append(tws)

        return TeacherWeeklyScheduleOut(
            teacher_id=teacher_id, teacher_name=user.display_name,
            semester=semester, schedule=schedule,
        )

    # ── 冲突记录查询 ──

    @staticmethod
    async def list_conflicts(
        db: AsyncSession, school_id: int,
        is_resolved: Optional[bool] = None, page: int = 1, page_size: int = 20,
    ) -> dict:
        conditions = [ScheduleConflict.school_id == school_id]
        if is_resolved is not None:
            conditions.append(ScheduleConflict.is_resolved == is_resolved)

        base = select(ScheduleConflict).where(and_(*conditions))

        count_q = select(func.count()).select_from(base.subquery())
        total_result = await db.execute(count_q)
        total = total_result.scalar() or 0

        result = await db.execute(
            base.order_by(desc(ScheduleConflict.created_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )

        return {
            "total": total, "page": page, "page_size": page_size,
            "items": [ConflictOut.model_validate(c) for c in result.scalars().all()],
        }

    @staticmethod
    async def resolve_conflict(
        db: AsyncSession, conflict_id: int, resolution: str, resolved_by: int,
    ) -> Optional[ConflictOut]:
        result = await db.execute(
            select(ScheduleConflict).where(ScheduleConflict.id == conflict_id)
        )
        sc = result.scalar_one_or_none()
        if not sc:
            return None

        from datetime import datetime
        sc.is_resolved = True
        sc.resolved_by = resolved_by
        sc.resolved_at = datetime.now()
        await db.commit()
        await db.refresh(sc)
        return ConflictOut.model_validate(sc)
