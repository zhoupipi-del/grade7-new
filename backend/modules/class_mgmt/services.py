"""
modules/class_mgmt/services.py — 班级管理业务逻辑
"""

import logging
from typing import Optional, List, Tuple

from sqlalchemy import select, func, update, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.models import Student, Class, Grade, User
from modules.class_mgmt.models import ClassChangeLog, ClassProfileExt
from modules.class_mgmt.schemas import (
    ClassCreate, ClassUpdate, AssignStudentsRequest,
    TransferStudentRequest, MergeClassesRequest, SplitClassRequest,
)

logger = logging.getLogger(__name__)


class ClassMgmtService:
    """班级管理服务"""

    # ═══════════════════════════════════════════════════════════
    # 班级 CRUD
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def create_class(
        db: AsyncSession,
        school_id: int,
        data: ClassCreate,
    ) -> Class:
        """创建班级"""
        # 校验年级
        grade = await db.get(Grade, data.grade_id)
        if not grade or grade.school_id != school_id:
            raise ValueError("年级不存在或不属于当前学校")

        # 检查班级名重复
        existing = await db.execute(
            select(Class).where(
                Class.school_id == school_id,
                Class.name == data.name,
                Class.is_active == True,
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError(f"班级名已存在: {data.name}")

        cls = Class(
            name=data.name,
            school_id=school_id,
            grade_id=data.grade_id,
            head_teacher_id=data.head_teacher_id,
            student_count=0,
            is_active=True,
        )
        db.add(cls)
        await db.flush()

        # 创建扩展记录
        ext = ClassProfileExt(
            class_id=cls.id,
            school_id=school_id,
            class_slogan=data.class_slogan,
        )
        db.add(ext)

        logger.info(f"班级创建: class_id={cls.id} name={data.name}")
        return cls

    @staticmethod
    async def get_class(db: AsyncSession, class_id: int) -> Optional[dict]:
        """获取班级详情"""
        result = await db.execute(
            select(Class, ClassProfileExt)
            .outerjoin(ClassProfileExt, Class.id == ClassProfileExt.class_id)
            .options(selectinload(Class.head_teacher), selectinload(Class.grade))
            .where(Class.id == class_id)
        )
        row = result.first()
        if not row:
            return None

        cls, ext = row
        return {
            "id": cls.id,
            "name": cls.name,
            "school_id": cls.school_id,
            "grade_id": cls.grade_id,
            "head_teacher_id": cls.head_teacher_id,
            "head_teacher_name": cls.head_teacher.display_name if cls.head_teacher else None,
            "student_count": cls.student_count or 0,
            "is_active": cls.is_active,
            "class_slogan": ext.class_slogan if ext else None,
            "class_features": ext.class_features if ext else None,
        }

    @staticmethod
    async def list_classes(
        db: AsyncSession,
        school_id: int,
        grade_id: Optional[int] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> Tuple[List[dict], int]:
        """班级列表"""
        conditions = [Class.school_id == school_id, Class.is_active == True]
        if grade_id:
            conditions.append(Class.grade_id == grade_id)

        # 总数
        count_q = select(func.count(Class.id)).where(and_(*conditions))
        total = (await db.execute(count_q)).scalar() or 0

        # 列表
        query = (
            select(Class, ClassProfileExt)
            .outerjoin(ClassProfileExt, Class.id == ClassProfileExt.class_id)
            .options(selectinload(Class.head_teacher), selectinload(Class.grade))
            .where(and_(*conditions))
            .order_by(Class.grade_id, Class.name)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await db.execute(query)

        items = []
        for cls, ext in result:
            items.append({
                "id": cls.id,
                "name": cls.name,
                "school_id": cls.school_id,
                "grade_id": cls.grade_id,
                "head_teacher_id": cls.head_teacher_id,
                "head_teacher_name": cls.head_teacher.display_name if cls.head_teacher else None,
                "student_count": cls.student_count or 0,
                "is_active": cls.is_active,
                "class_slogan": ext.class_slogan if ext else None,
            })

        return items, total

    @staticmethod
    async def update_class(
        db: AsyncSession,
        class_id: int,
        data: ClassUpdate,
    ) -> Class:
        """更新班级信息"""
        cls = await db.get(Class, class_id)
        if not cls:
            raise ValueError(f"班级不存在: {class_id}")

        if data.name is not None:
            cls.name = data.name
        if data.head_teacher_id is not None:
            cls.head_teacher_id = data.head_teacher_id
        if data.is_active is not None:
            cls.is_active = data.is_active

        # 更新扩展表
        if data.class_slogan is not None:
            result = await db.execute(
                select(ClassProfileExt).where(ClassProfileExt.class_id == class_id)
            )
            ext = result.scalar_one_or_none()
            if ext:
                ext.class_slogan = data.class_slogan
            else:
                ext = ClassProfileExt(class_id=class_id, school_id=cls.school_id, class_slogan=data.class_slogan)
                db.add(ext)

        return cls

    # ═══════════════════════════════════════════════════════════
    # 学生分班 / 调班
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def assign_students(
        db: AsyncSession,
        school_id: int,
        class_id: int,
        student_ids: List[int],
        operated_by: int,
        operator_name: str = "",
    ) -> dict:
        """学生分班 — 将学生分配到指定班级"""
        cls = await db.get(Class, class_id)
        if not cls or cls.school_id != school_id:
            raise ValueError("班级不存在或不属于当前学校")

        assigned = []
        failed = []
        for sid in student_ids:
            student = await db.get(Student, sid)
            if not student or student.school_id != school_id:
                failed.append({"student_id": sid, "error": "学生不存在"})
                continue

            old_class_id = student.class_id
            student.class_id = class_id
            student.grade_id = cls.grade_id
            assigned.append(sid)

            # 记录变更日志
            log = ClassChangeLog(
                class_id=class_id,
                school_id=school_id,
                change_type="assign",
                affected_students=[sid],
                from_class_id=old_class_id,
                to_class_id=class_id,
                operated_by=operated_by,
                operator_name=operator_name,
            )
            db.add(log)

        # 更新班级人数
        cls.student_count = (cls.student_count or 0) + len(assigned)

        logger.info(f"分班完成: class_id={class_id} assigned={len(assigned)} failed={len(failed)}")
        return {"assigned": assigned, "failed": failed, "total": len(student_ids)}

    @staticmethod
    async def transfer_student(
        db: AsyncSession,
        school_id: int,
        student_id: int,
        target_class_id: int,
        operated_by: int,
        operator_name: str = "",
        reason: Optional[str] = None,
    ) -> dict:
        """学生调班 — 从当前班级调到目标班级"""
        student = await db.get(Student, student_id)
        if not student or student.school_id != school_id:
            raise ValueError("学生不存在")

        from_class_id = student.class_id
        target_cls = await db.get(Class, target_class_id)
        if not target_cls or target_cls.school_id != school_id:
            raise ValueError("目标班级不存在")

        # 更新学生班级
        student.class_id = target_class_id
        student.grade_id = target_cls.grade_id

        # 更新班级人数
        from_cls = await db.get(Class, from_class_id)
        if from_cls:
            from_cls.student_count = max(0, (from_cls.student_count or 1) - 1)
        target_cls.student_count = (target_cls.student_count or 0) + 1

        # 记录日志
        log = ClassChangeLog(
            class_id=target_class_id,
            school_id=school_id,
            change_type="transfer",
            affected_students=[student_id],
            from_class_id=from_class_id,
            to_class_id=target_class_id,
            operated_by=operated_by,
            operator_name=operator_name,
            remark=reason,
        )
        db.add(log)

        logger.info(f"调班: student_id={student_id} {from_class_id} -> {target_class_id}")
        return {
            "student_id": student_id,
            "from_class_id": from_class_id,
            "to_class_id": target_class_id,
        }

    # ═══════════════════════════════════════════════════════════
    # 班主任分配
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def assign_head_teacher(
        db: AsyncSession,
        school_id: int,
        class_id: int,
        teacher_user_id: int,
        operated_by: int,
        operator_name: str = "",
    ) -> Class:
        """分配班主任"""
        cls = await db.get(Class, class_id)
        if not cls or cls.school_id != school_id:
            raise ValueError("班级不存在")

        teacher = await db.get(User, teacher_user_id)
        if not teacher or teacher.school_id != school_id:
            raise ValueError("教师不存在")

        old_teacher = cls.head_teacher_id
        cls.head_teacher_id = teacher_user_id

        # 记录日志
        log = ClassChangeLog(
            class_id=class_id,
            school_id=school_id,
            change_type="teacher_change",
            operated_by=operated_by,
            operator_name=operator_name,
            remark=f"班主任变更: {old_teacher} -> {teacher_user_id}",
        )
        db.add(log)

        logger.info(f"班主任分配: class_id={class_id} teacher={teacher_user_id}")
        return cls

    # ═══════════════════════════════════════════════════════════
    # 班级学生名单
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def get_class_students(
        db: AsyncSession,
        class_id: int,
    ) -> List[dict]:
        """获取班级学生名单"""
        result = await db.execute(
            select(Student)
            .where(Student.class_id == class_id, Student.is_active == True)
            .order_by(Student.student_no)
        )
        students = result.scalars().all()
        return [
            {
                "id": s.id,
                "name": s.name,
                "student_no": s.student_no,
                "gender": s.gender,
                "class_id": s.class_id,
            }
            for s in students
        ]

    # ═══════════════════════════════════════════════════════════
    # 统计
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def get_stats(db: AsyncSession, school_id: int) -> dict:
        """班级统计"""
        # 总班级数
        total_classes = (await db.execute(
            select(func.count(Class.id)).where(
                Class.school_id == school_id, Class.is_active == True
            )
        )).scalar() or 0

        # 总学生数
        total_students = (await db.execute(
            select(func.count(Student.id)).where(
                Student.school_id == school_id, Student.is_active == True
            )
        )).scalar() or 0

        # 平均班级人数
        avg_size = total_students / total_classes if total_classes > 0 else 0

        # 按年级统计
        grade_query = (
            select(
                Grade.name,
                func.count(Class.id),
                func.coalesce(func.sum(Class.student_count), 0),
            )
            .join(Class, Class.grade_id == Grade.id)
            .where(Class.school_id == school_id, Class.is_active == True)
            .group_by(Grade.name)
        )
        grade_result = await db.execute(grade_query)
        by_grade = {}
        for name, cls_count, stu_count in grade_result:
            by_grade[name] = {"classes": cls_count, "students": stu_count}

        # 最大/最小班级
        all_classes = await db.execute(
            select(Class, Grade.name)
            .join(Grade, Class.grade_id == Grade.id)
            .where(Class.school_id == school_id, Class.is_active == True)
            .order_by(Class.student_count.desc())
        )
        class_list = list(all_classes)
        largest = None
        smallest = None
        if class_list:
            cls_max, grade_max = class_list[0]
            largest = {"id": cls_max.id, "name": cls_max.name, "count": cls_max.student_count, "grade": grade_max}
            cls_min, grade_min = class_list[-1]
            smallest = {"id": cls_min.id, "name": cls_min.name, "count": cls_min.student_count, "grade": grade_min}

        return {
            "total_classes": total_classes,
            "total_students": total_students,
            "avg_class_size": round(avg_size, 1),
            "by_grade": by_grade,
            "largest_class": largest,
            "smallest_class": smallest,
        }
