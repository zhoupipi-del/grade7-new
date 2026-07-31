"""
modules/student_registry/services.py — 学籍管理业务逻辑

纯 Static Method 类，接收 db: AsyncSession 作为第一参数。
操作 core.models.Student + student_registry.models.StudentRegistryExt/StudentStatusChange。
"""

import logging
from datetime import date, datetime
from typing import Optional, List, Tuple

from sqlalchemy import select, func, update, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.models import Student, Class, Grade, User, UserRole
from modules.student_registry.models import (
    StudentStatusChange, StudentRegistryExt,
    STUDENT_STATUS, VALID_TRANSITIONS,
)
from modules.student_registry.schemas import (
    StudentCreate, StudentUpdate, StatusChangeCreate,
)

logger = logging.getLogger(__name__)


class StudentRegistryService:
    """学籍管理服务 — 全系统学生数据的 Single Source of Truth"""

    # ═══════════════════════════════════════════════════════════
    # 学号生成
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def generate_student_no(
        db: AsyncSession,
        school_id: int,
        grade_id: int,
        class_id: int,
    ) -> str:
        """
        生成学号：入学年(4位) + 年级(1位) + 班序(2位) + 序号(2位)
        示例：2026 7 01 01 = 202670101
        """
        # 获取年级信息
        grade = await db.get(Grade, grade_id)
        if not grade:
            raise ValueError(f"年级不存在: {grade_id}")

        # 获取班级信息
        cls = await db.get(Class, class_id)
        if not cls:
            raise ValueError(f"班级不存在: {class_id}")

        # 入学年：从年级名称推断或用当前年
        current_year = datetime.now().year
        # 简单逻辑：七年级=今年，八年级=去年，九年级=前年
        grade_sort = grade.sort_order or 7
        enrollment_year = current_year - (grade_sort - 7) if grade_sort >= 7 else current_year

        # 班序号
        class_name = cls.name or ""
        # 从班级名提取数字，如 "2501" -> 01
        class_num = 0
        for ch in class_name:
            if ch.isdigit():
                class_num = class_num * 10 + int(ch)
        class_seq = class_num % 100 if class_num > 0 else 1

        # 查找当前班级已有最大序号
        result = await db.execute(
            select(func.count(Student.id)).where(
                Student.class_id == class_id,
                Student.school_id == school_id,
            )
        )
        current_count = result.scalar() or 0
        seq = current_count + 1

        student_no = f"{enrollment_year}{grade_sort}{class_seq:02d}{seq:02d}"
        return student_no

    # ═══════════════════════════════════════════════════════════
    # 创建学籍
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def create_student(
        db: AsyncSession,
        school_id: int,
        data: StudentCreate,
        created_by: int,
        sync_status: str = "native",
    ) -> Student:
        """创建学籍 — 同时创建 Student + StudentRegistryExt"""

        # 校验班级存在且属于该校
        cls = await db.get(Class, data.class_id)
        if not cls or cls.school_id != school_id:
            raise ValueError("班级不存在或不属于当前学校")

        # 校验年级存在
        grade = await db.get(Grade, data.grade_id)
        if not grade or grade.school_id != school_id:
            raise ValueError("年级不存在或不属于当前学校")

        # 生成学号
        student_no = None
        if data.auto_generate_no:
            student_no = await StudentRegistryService.generate_student_no(
                db, school_id, data.grade_id, data.class_id
            )
        else:
            if not data.national_student_no:
                raise ValueError("未自动生成学号时必须提供全国学籍号")
            student_no = data.national_student_no

        # 检查学号唯一
        existing = await db.execute(
            select(Student).where(Student.student_no == student_no)
        )
        if existing.scalar_one_or_none():
            raise ValueError(f"学号已存在: {student_no}")

        # 创建 Student 记录
        student = Student(
            name=data.name,
            student_no=student_no,
            school_id=school_id,
            class_id=data.class_id,
            grade_id=data.grade_id,
            gender=data.gender,
            id_card=data.id_card,
            nationality=data.nationality,
            birth_date=data.birth_date,
            address=data.address,
            parent1_name=data.parent1_name,
            parent1_phone=data.parent1_phone,
            parent1_relation=data.parent1_relation,
            parent2_name=data.parent2_name,
            parent2_phone=data.parent2_phone,
            parent2_relation=data.parent2_relation,
            is_active=True,
            enrolled_at=data.enrolled_at or date.today(),
        )
        db.add(student)
        await db.flush()  # 获取 student.id

        # 创建扩展记录
        ext = StudentRegistryExt(
            student_id=student.id,
            school_id=school_id,
            registry_status="active",
            national_student_no=data.national_student_no,
            enrollment_type=data.enrollment_type or "normal",
            sync_status=sync_status,
        )
        db.add(ext)

        # 更新班级人数
        cls.student_count = (cls.student_count or 0) + 1

        logger.info(f"学籍创建成功: student_id={student.id} student_no={student_no}")
        return student

    # ═══════════════════════════════════════════════════════════
    # 查询学籍
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def get_student(db: AsyncSession, student_id: int) -> Optional[dict]:
        """获取学籍详情（含扩展信息）"""
        result = await db.execute(
            select(Student, StudentRegistryExt)
            .outerjoin(StudentRegistryExt, Student.id == StudentRegistryExt.student_id)
            .options(selectinload(Student.class_), selectinload(Student.grade))
            .where(Student.id == student_id)
        )
        row = result.first()
        if not row:
            return None

        student, ext = row
        return {
            "id": student.id,
            "name": student.name,
            "student_no": student.student_no,
            "school_id": student.school_id,
            "class_id": student.class_id,
            "grade_id": student.grade_id,
            "gender": student.gender,
            "id_card": student.id_card,
            "nationality": student.nationality,
            "birth_date": student.birth_date,
            "address": student.address,
            "parent1_name": student.parent1_name,
            "parent1_phone": student.parent1_phone,
            "parent1_relation": student.parent1_relation,
            "parent2_name": student.parent2_name,
            "parent2_phone": student.parent2_phone,
            "parent2_relation": student.parent2_relation,
            "is_active": student.is_active,
            "enrolled_at": student.enrolled_at,
            "tags": student.tags,
            "created_at": student.created_at,
            "registry_status": ext.registry_status if ext else "active",
            "national_student_no": ext.national_student_no if ext else None,
            "enrollment_type": ext.enrollment_type if ext else None,
            "sync_status": ext.sync_status if ext else "native",
            "class_name": student.class_.name if student.class_ else None,
            "grade_name": student.grade.name if student.grade else None,
        }

    @staticmethod
    async def list_students(
        db: AsyncSession,
        school_id: int,
        page: int = 1,
        page_size: int = 20,
        class_id: Optional[int] = None,
        grade_id: Optional[int] = None,
        status: Optional[str] = None,
        keyword: Optional[str] = None,
    ) -> Tuple[List[dict], int]:
        """分页查询学籍列表"""
        # 构建基础查询
        conditions = [Student.school_id == school_id]
        if class_id:
            conditions.append(Student.class_id == class_id)
        if grade_id:
            conditions.append(Student.grade_id == grade_id)
        if keyword:
            conditions.append(
                or_(
                    Student.name.like(f"%{keyword}%"),
                    Student.student_no.like(f"%{keyword}%"),
                )
            )

        # 扩展表条件
        if status:
            conditions.append(StudentRegistryExt.registry_status == status)

        # 查询总数
        count_query = (
            select(func.count(Student.id))
            .outerjoin(StudentRegistryExt, Student.id == StudentRegistryExt.student_id)
            .where(and_(*conditions))
        )
        total = (await db.execute(count_query)).scalar() or 0

        # 分页查询
        query = (
            select(Student, StudentRegistryExt)
            .outerjoin(StudentRegistryExt, Student.id == StudentRegistryExt.student_id)
            .options(selectinload(Student.class_), selectinload(Student.grade))
            .where(and_(*conditions))
            .order_by(Student.class_id, Student.student_no)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await db.execute(query)

        items = []
        for student, ext in result:
            items.append({
                "id": student.id,
                "name": student.name,
                "student_no": student.student_no,
                "school_id": student.school_id,
                "class_id": student.class_id,
                "grade_id": student.grade_id,
                "gender": student.gender,
                "is_active": student.is_active,
                "enrolled_at": student.enrolled_at,
                "registry_status": ext.registry_status if ext else "active",
                "sync_status": ext.sync_status if ext else "native",
                "class_name": student.class_.name if student.class_ else None,
                "grade_name": student.grade.name if student.grade else None,
                "created_at": student.created_at,
            })

        return items, total

    # ═══════════════════════════════════════════════════════════
    # 更新学籍
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def update_student(
        db: AsyncSession,
        student_id: int,
        data: StudentUpdate,
    ) -> Student:
        """更新学籍基本信息"""
        student = await db.get(Student, student_id)
        if not student:
            raise ValueError(f"学生不存在: {student_id}")

        update_fields = data.model_dump(exclude_unset=True)
        for field, value in update_fields.items():
            setattr(student, field, value)

        logger.info(f"学籍更新: student_id={student_id} fields={list(update_fields.keys())}")
        return student

    # ═══════════════════════════════════════════════════════════
    # 状态变更（核心状态机）
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def change_status(
        db: AsyncSession,
        school_id: int,
        student_id: int,
        data: StatusChangeCreate,
        operated_by: int,
        operator_name: str = "",
    ) -> StudentStatusChange:
        """
        学籍状态变更 — 状态机核心方法。
        校验状态转换合法性，更新 registry_status，记录变更日志。
        """

        # 获取扩展记录
        result = await db.execute(
            select(StudentRegistryExt).where(
                StudentRegistryExt.student_id == student_id,
                StudentRegistryExt.school_id == school_id,
            )
        )
        ext = result.scalar_one_or_none()
        if not ext:
            raise ValueError(f"学籍扩展记录不存在: student_id={student_id}")

        current_status = ext.registry_status
        change_type = data.change_type

        # 确定目标状态
        type_to_status = {
            "transfer": "transferred",
            "suspend": "suspended",
            "resume": "active",
            "graduate": "graduated",
            "inactive": "inactive",
        }
        target_status = type_to_status.get(change_type)
        if not target_status:
            raise ValueError(f"无效的变更类型: {change_type}")

        # 校验状态转换合法性
        allowed = VALID_TRANSITIONS.get(current_status, [])
        if target_status not in allowed:
            raise ValueError(
                f"非法状态转换: {current_status} -> {target_status}. "
                f"允许的转换: {allowed}"
            )

        # 创建变更记录
        change = StudentStatusChange(
            student_id=student_id,
            school_id=school_id,
            from_status=current_status,
            to_status=target_status,
            change_type=change_type,
            reason=data.reason,
            target_school=data.target_school,
            expected_resume_date=data.expected_resume_date,
            operated_by=operated_by,
            operator_name=operator_name,
            sync_status="native",
            remark=data.remark,
        )
        db.add(change)

        # 更新扩展表状态
        ext.registry_status = target_status

        # 更新 Student.is_active
        student = await db.get(Student, student_id)
        if student:
            if target_status == "active":
                student.is_active = True
            elif target_status in ("transferred", "graduated", "inactive"):
                student.is_active = False
            # suspended 保持 is_active=True（学籍仍在）

            # 转学/毕业/注销时减少班级人数
            if target_status in ("transferred", "graduated", "inactive"):
                cls = await db.get(Class, student.class_id)
                if cls:
                    cls.student_count = max(0, (cls.student_count or 1) - 1)

            # 毕业时记录毕业信息
            if target_status == "graduated":
                ext.graduation_date = date.today()
                if data.target_school:
                    ext.graduation_school = data.target_school

        logger.info(
            f"学籍状态变更: student_id={student_id} "
            f"{current_status} -> {target_status} ({change_type}) "
            f"by={operated_by}"
        )
        return change

    # ═══════════════════════════════════════════════════════════
    # 批量导入
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def batch_import(
        db: AsyncSession,
        school_id: int,
        students_data: List[dict],
        imported_by: int,
    ) -> dict:
        """
        批量导入学籍 — 从 Excel/CSV 解析后的字典列表。
        每条记录需包含: name, class_id, grade_id, 其他字段可选。
        """
        total = len(students_data)
        success = 0
        failed = 0
        errors = []
        imported_ids = []

        for i, row in enumerate(students_data):
            try:
                # 解析数据
                data = StudentCreate(
                    name=row.get("name", "").strip(),
                    gender=row.get("gender"),
                    birth_date=row.get("birth_date"),
                    id_card=row.get("id_card"),
                    nationality=row.get("nationality"),
                    class_id=int(row.get("class_id", 0)),
                    grade_id=int(row.get("grade_id", 0)),
                    address=row.get("address"),
                    parent1_name=row.get("parent1_name"),
                    parent1_phone=row.get("parent1_phone"),
                    parent1_relation=row.get("parent1_relation"),
                    parent2_name=row.get("parent2_name"),
                    parent2_phone=row.get("parent2_phone"),
                    parent2_relation=row.get("parent2_relation"),
                    national_student_no=row.get("national_student_no"),
                    enrolled_at=row.get("enrolled_at"),
                    auto_generate_no=True,
                )
                student = await StudentRegistryService.create_student(
                    db, school_id, data, imported_by, sync_status="imported"
                )
                imported_ids.append(student.id)
                success += 1
            except Exception as e:
                failed += 1
                errors.append({
                    "row": i + 2,  # Excel 行号（从第2行开始有数据）
                    "name": row.get("name", ""),
                    "error": str(e),
                })
                logger.warning(f"批量导入第{i+1}行失败: {e}")

        logger.info(f"批量导入完成: total={total} success={success} failed={failed}")
        return {
            "total": total,
            "success": success,
            "failed": failed,
            "errors": errors,
            "imported_ids": imported_ids,
        }

    # ═══════════════════════════════════════════════════════════
    # 统计
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def get_stats(db: AsyncSession, school_id: int) -> dict:
        """学籍统计"""
        # 按状态统计
        status_query = (
            select(StudentRegistryExt.registry_status, func.count())
            .where(StudentRegistryExt.school_id == school_id)
            .group_by(StudentRegistryExt.registry_status)
        )
        status_result = await db.execute(status_query)
        by_status = {row[0]: row[1] for row in status_result}

        # 按年级统计
        grade_query = (
            select(Grade.name, func.count(Student.id))
            .join(Student, Student.grade_id == Grade.id)
            .where(Student.school_id == school_id)
            .group_by(Grade.name)
        )
        grade_result = await db.execute(grade_query)
        by_grade = {row[0]: row[1] for row in grade_result}

        # 按性别统计
        gender_query = (
            select(Student.gender, func.count())
            .where(Student.school_id == school_id)
            .group_by(Student.gender)
        )
        gender_result = await db.execute(gender_query)
        by_gender = {row[0] or "unknown": row[1] for row in gender_result}

        # 同步来源统计
        sync_query = (
            select(StudentRegistryExt.sync_status, func.count())
            .where(StudentRegistryExt.school_id == school_id)
            .group_by(StudentRegistryExt.sync_status)
        )
        sync_result = await db.execute(sync_query)
        sync_summary = {row[0]: row[1] for row in sync_result}

        # 总数
        total = await db.execute(
            select(func.count(Student.id)).where(Student.school_id == school_id)
        )
        total_count = total.scalar() or 0

        return {
            "total_students": total_count,
            "by_status": by_status,
            "by_grade": by_grade,
            "by_gender": by_gender,
            "sync_summary": sync_summary,
        }

    # ═══════════════════════════════════════════════════════════
    # 状态变更历史
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def get_status_history(
        db: AsyncSession,
        student_id: int,
    ) -> List[StudentStatusChange]:
        """获取学籍状态变更历史"""
        result = await db.execute(
            select(StudentStatusChange)
            .where(StudentStatusChange.student_id == student_id)
            .order_by(StudentStatusChange.created_at.desc())
        )
        return list(result.scalars().all())
