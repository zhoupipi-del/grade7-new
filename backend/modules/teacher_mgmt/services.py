"""
teacher_mgmt 业务逻辑层

服务方法:
  list_teachers          — 教师列表（筛选+分页）
  get_teacher_detail     — 教师详情
  create_teacher         — 创建教师 (User+Teacher+Extension 一步到位)
  upsert_extension       — 更新扩展信息
  assign_subjects        — 分配任教学科
  add_workload           — 新增工作量
  list_workloads         — 查询工作量列表
  get_workload_stats     — 工作量统计

角色分配 CRUD (双重角色解耦 overlay):
  assign_role            — 分配角色
  list_roles             — 查询角色列表
  update_role            — 更新角色 (启用/停用/设过期)
  delete_role            — 删除角色分配

核心聚合:
  resolve_effective_roles — 解析教师有效角色集合 (排课+审批+大盘三切面)
"""

import logging
from datetime import datetime

from core.models import Class, Grade, Teacher, User
from core.services import AuthService
from modules.teacher_mgmt.models import (
    TeacherExtension,
    TeacherRoleAssignment,
    TeacherSubject,
    TeacherWorkload,
)
from modules.teacher_mgmt.schemas import (
    EffectiveRoleOut,
    EffectiveRolesOut,
    SubjectAssignment,
    SubjectAssignResponse,
    TeacherCreate,
    TeacherCreateOut,
    TeacherDetailOut,
    TeacherExtensionCreate,
    TeacherExtensionOut,
    TeacherListItem,
    TeacherRoleAssignmentCreate,
    TeacherRoleAssignmentOut,
    WorkloadCreate,
    WorkloadOut,
    WorkloadStatsOut,
)
from sqlalchemy import and_, delete, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("teacher_mgmt.services")


class TeacherService:
    # ═══════════════════════════════════════════════════════════
    # 创建教师 (一步到位: User+Teacher+TeacherExtension)
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def create_teacher(
        db: AsyncSession,
        school_id: int,
        data: TeacherCreate,
    ) -> TeacherCreateOut:
        """
        创建教师 — 原子事务:
          1. 创建 User (role=class_teacher/teacher)
          2. 创建 Teacher (user_id + subject + employee_no)
          3. 创建 TeacherExtension (扩展信息)
        """
        # 检查 username 唯一性
        existing = await db.execute(select(User).where(User.username == data.username))
        if existing.scalar_one_or_none():
            raise ValueError(f"用户名 '{data.username}' 已存在")

        # 1. 创建 User
        user = User(
            school_id=school_id,
            username=data.username,
            display_name=data.display_name,
            password_hash=AuthService.hash_password(data.password),
            role=data.role,
            is_active=True,
        )
        db.add(user)
        await db.flush()  # 获取 user.id

        # 2. 创建 Teacher
        teacher = Teacher(
            user_id=user.id,
            school_id=school_id,
            subject=data.subject,
            employee_no=data.employee_no,
            title=data.title,
            is_homeroom=False,
        )
        db.add(teacher)
        await db.flush()  # 获取 teacher.id

        # 3. 创建 TeacherExtension — 修复: teacher_id 用 teacher.id 而非 user.id
        ext_data = {}
        if data.title:
            ext_data["title"] = data.title
        if data.hired_at:
            ext_data["hired_at"] = data.hired_at  # ORM属性名, DB列名hire_date
        if data.education:
            ext_data["education"] = data.education
        if data.major:
            ext_data["major"] = data.major
        if data.graduate_school:
            ext_data["graduate_school"] = data.graduate_school
        if data.employee_no:
            ext_data["employee_no"] = data.employee_no
        if data.contact_phone:
            ext_data["contact_phone"] = data.contact_phone
        if data.max_weekly_hours is not None:
            ext_data["max_weekly_hours"] = data.max_weekly_hours

        ext = TeacherExtension(
            school_id=school_id,
            user_id=user.id,
            teacher_id=teacher.id,  # ✅ 修复: 正确的 Teacher FK
            is_head_teacher=False,
            is_active=True,
            **ext_data,
        )
        db.add(ext)
        await db.commit()

        return TeacherCreateOut(
            user_id=user.id,
            teacher_id=teacher.id,
            extension_id=ext.id,
            username=user.username,
            display_name=user.display_name,
            role=user.role,
        )

    # ═══════════════════════════════════════════════════════════
    # 教师列表
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def list_teachers(
        db: AsyncSession,
        school_id: int,
        page: int = 1,
        page_size: int = 20,
        role: str | None = None,
        is_active: bool | None = None,
        keyword: str | None = None,
    ) -> dict:
        """查询教师列表（支持筛选：角色/状态/关键词搜索）"""
        conditions = [
            User.school_id == school_id,
            User.role.in_(["class_teacher", "teacher"]),
        ]

        if role:
            conditions.append(User.role == role)
        if is_active is not None:
            conditions.append(User.is_active == is_active)
        if keyword:
            conditions.append(User.display_name.ilike(f"%{keyword}%"))

        base = select(User).where(and_(*conditions))

        # 总数
        count_q = select(func.count()).select_from(base.subquery())
        total_result = await db.execute(count_q)
        total = total_result.scalar() or 0

        # 分页
        result = await db.execute(
            base.order_by(User.id.asc()).offset((page - 1) * page_size).limit(page_size)
        )
        users = result.scalars().all()

        # 批量查询关联数据
        user_ids = [u.id for u in users]
        teachers_map = {}
        extensions_map = {}
        subjects_map: dict[int, list[str]] = {}
        homeroom_map: dict[int, tuple] = {}

        if user_ids:
            # Teacher 表
            t_result = await db.execute(select(Teacher).where(Teacher.user_id.in_(user_ids)))
            for t in t_result.scalars().all():
                teachers_map[t.user_id] = t

            # TeacherExtension
            e_result = await db.execute(
                select(TeacherExtension).where(TeacherExtension.user_id.in_(user_ids))
            )
            for e in e_result.scalars().all():
                extensions_map[e.user_id] = e

            # TeacherSubject
            s_result = await db.execute(
                select(TeacherSubject).where(TeacherSubject.teacher_user_id.in_(user_ids))
            )
            for s in s_result.scalars().all():
                subjects_map.setdefault(s.teacher_user_id, []).append(s.subject_name)

            # 班主任班级
            class_result = await db.execute(
                select(Class).where(
                    and_(Class.head_teacher_id.in_(user_ids), Class.is_active == True)
                )
            )
            for c in class_result.scalars().all():
                homeroom_map[c.head_teacher_id] = (c.id, c.name)

        items = []
        for u in users:
            t = teachers_map.get(u.id)
            e = extensions_map.get(u.id)
            hr = homeroom_map.get(u.id)
            items.append(
                TeacherListItem(
                    id=u.id,
                    display_name=u.display_name,
                    username=u.username,
                    role=u.role,
                    phone=u.phone,
                    employee_no=t.employee_no if t else None,
                    subject=t.subject if t else None,
                    title=e.title if e else (t.title if t else None),
                    is_homeroom=(t.is_homeroom if t else False),
                    homeroom_class_id=hr[0] if hr else None,
                    homeroom_class_name=hr[1] if hr else None,
                    subjects_taught=subjects_map.get(u.id, []),
                    max_weekly_hours=e.max_weekly_hours if e else None,
                    is_active=u.is_active,
                    created_at=u.created_at,
                )
            )

        return {"teachers": items, "total": total, "page": page, "page_size": page_size}

    # ═══════════════════════════════════════════════════════════
    # 教师详情
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def get_teacher_detail(
        db: AsyncSession,
        user_id: int,
    ) -> TeacherDetailOut | None:
        """查询教师详情"""
        user_result = await db.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()
        if not user or user.role not in ("class_teacher", "teacher"):
            return None

        # Teacher
        t_result = await db.execute(select(Teacher).where(Teacher.user_id == user_id))
        teacher = t_result.scalar_one_or_none()

        # Extension
        e_result = await db.execute(
            select(TeacherExtension).where(TeacherExtension.user_id == user_id)
        )
        ext = e_result.scalar_one_or_none()

        # Subjects
        s_result = await db.execute(
            select(TeacherSubject).where(TeacherSubject.teacher_user_id == user_id)
        )
        subjects = [
            SubjectAssignment(
                id=s.id,
                subject_code=s.subject_code,
                subject_name=s.subject_name,
                is_primary=s.is_primary,
                grade_level=s.grade_level,
            )
            for s in s_result.scalars().all()
        ]

        # Homeroom class
        homeroom_class_id = None
        homeroom_class_name = None
        if teacher and teacher.is_homeroom:
            c_result = await db.execute(
                select(Class).where(and_(Class.head_teacher_id == user_id, Class.is_active == True))
            )
            cls = c_result.scalar_one_or_none()
            if cls:
                homeroom_class_id = cls.id
                homeroom_class_name = cls.name

        return TeacherDetailOut(
            user_id=user.id,
            display_name=user.display_name,
            username=user.username,
            role=user.role,
            phone=user.phone,
            employee_no=teacher.employee_no if teacher else None,
            subject=teacher.subject if teacher else None,
            extension=TeacherExtensionOut.model_validate(ext) if ext else None,
            subjects_taught=subjects,
            is_homeroom=teacher.is_homeroom if teacher else False,
            homeroom_class_id=homeroom_class_id,
            homeroom_class_name=homeroom_class_name,
            max_weekly_hours=ext.max_weekly_hours if ext else None,
            is_active=user.is_active,
        )

    # ═══════════════════════════════════════════════════════════
    # 教师扩展信息
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def upsert_extension(
        db: AsyncSession,
        user_id: int,
        data: TeacherExtensionCreate,
        school_id: int,
    ) -> TeacherExtensionOut:
        """创建或更新教师扩展信息"""
        # 先查 Teacher 记录获取 teacher.id (修复 teacher_id bug)
        t_result = await db.execute(select(Teacher).where(Teacher.user_id == user_id))
        teacher = t_result.scalar_one_or_none()

        result = await db.execute(
            select(TeacherExtension).where(
                and_(
                    TeacherExtension.user_id == user_id,
                    TeacherExtension.school_id == school_id,
                )
            )
        )
        ext = result.scalar_one_or_none()

        if not ext:
            ext = TeacherExtension(
                school_id=school_id,
                user_id=user_id,
                teacher_id=teacher.id if teacher else None,  # ✅ 修复: 用 Teacher.id
            )
            db.add(ext)

        for field, value in data.model_dump(exclude_unset=True).items():
            if value is not None:
                setattr(ext, field, value)

        # 如果 Teacher 记录后续创建, 回填 teacher_id
        if ext.teacher_id is None and teacher:
            ext.teacher_id = teacher.id

        await db.commit()
        await db.refresh(ext)
        return TeacherExtensionOut.model_validate(ext)

    # ═══════════════════════════════════════════════════════════
    # 任教学科分配
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def assign_subjects(
        db: AsyncSession,
        user_id: int,
        subjects: list[SubjectAssignment],
        school_id: int,
    ) -> SubjectAssignResponse:
        """分配教师任教学科（先删后插）"""
        # 删除旧映射
        await db.execute(
            delete(TeacherSubject).where(
                and_(
                    TeacherSubject.teacher_user_id == user_id,
                    TeacherSubject.school_id == school_id,
                )
            )
        )
        await db.flush()

        # 插入新映射
        new_subjects = []
        for sub in subjects:
            ts = TeacherSubject(
                school_id=school_id,
                teacher_user_id=user_id,
                subject_code=sub.subject_code,
                subject_name=sub.subject_name,
                is_primary=sub.is_primary,
                grade_level=sub.grade_level,
            )
            db.add(ts)
            new_subjects.append(ts)
        await db.commit()

        return SubjectAssignResponse(
            teacher_user_id=user_id,
            subjects=[
                SubjectAssignment(
                    id=s.id,
                    subject_code=s.subject_code,
                    subject_name=s.subject_name,
                    is_primary=s.is_primary,
                    grade_level=s.grade_level,
                )
                for s in new_subjects
            ],
        )

    # ═══════════════════════════════════════════════════════════
    # 工作量统计
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def add_workload(
        db: AsyncSession,
        user_id: int,
        data: WorkloadCreate,
        school_id: int,
    ) -> WorkloadOut:
        """新增/更新教师工作量记录"""
        result = await db.execute(
            select(TeacherWorkload).where(
                and_(
                    TeacherWorkload.teacher_user_id == user_id,
                    TeacherWorkload.semester == data.semester,
                    TeacherWorkload.school_id == school_id,
                )
            )
        )
        wl = result.scalar_one_or_none()

        if not wl:
            wl = TeacherWorkload(
                school_id=school_id,
                teacher_user_id=user_id,
                semester=data.semester,
                weekly_periods=data.weekly_periods,
                class_count=data.class_count,
                subject_count=data.subject_count,
                extra_duties=data.extra_duties,
            )
            db.add(wl)
        else:
            wl.weekly_periods = data.weekly_periods
            wl.class_count = data.class_count
            wl.subject_count = data.subject_count
            wl.extra_duties = data.extra_duties

        # 自动计算综合评分
        wl.total_workload_score = (
            wl.weekly_periods * 1.0 + wl.class_count * 2.0 + len(wl.extra_duties or []) * 5.0
        )

        await db.commit()
        await db.refresh(wl)
        return WorkloadOut.model_validate(wl)

    @staticmethod
    async def list_workloads(
        db: AsyncSession,
        user_id: int,
        school_id: int,
    ) -> list[WorkloadOut]:
        """查询教师所有学期工作量"""
        result = await db.execute(
            select(TeacherWorkload)
            .where(
                and_(
                    TeacherWorkload.teacher_user_id == user_id,
                    TeacherWorkload.school_id == school_id,
                )
            )
            .order_by(desc(TeacherWorkload.semester))
        )
        return [WorkloadOut.model_validate(w) for w in result.scalars().all()]

    @staticmethod
    async def get_workload_stats(
        db: AsyncSession,
        user_id: int,
        school_id: int,
    ) -> WorkloadStatsOut | None:
        """教师工作量统计汇总"""
        workloads = await TeacherService.list_workloads(db, user_id, school_id)
        if not workloads:
            return None

        user_result = await db.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()
        if not user:
            return None

        return WorkloadStatsOut(
            teacher_user_id=user_id,
            display_name=user.display_name,
            total_semesters=len(workloads),
            avg_weekly_periods=sum(w.weekly_periods for w in workloads) / len(workloads),
            avg_class_count=sum(w.class_count for w in workloads) / len(workloads),
            total_subjects=sum(w.subject_count for w in workloads),
            workloads=workloads,
        )

    # ═══════════════════════════════════════════════════════════
    # 角色分配 CRUD (双重角色解耦 overlay — BOSS 核心需求)
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def assign_role(
        db: AsyncSession,
        school_id: int,
        user_id: int,
        data: TeacherRoleAssignmentCreate,
        assigned_by: int,
    ) -> TeacherRoleAssignmentOut:
        """分配角色 — 幂等(uk_role_assignment保障唯一)"""
        # 检查教师存在性
        user_result = await db.execute(
            select(User).where(and_(User.id == user_id, User.school_id == school_id))
        )
        user = user_result.scalar_one_or_none()
        if not user or user.role not in ("class_teacher", "teacher", "grade_leader", "ms_admin"):
            raise ValueError(f"用户 {user_id} 不是教师角色")

        # school 级 scope_id 必须为 NULL
        scope_id = data.scope_id
        if data.scope_type == "school":
            scope_id = None

        assignment = TeacherRoleAssignment(
            school_id=school_id,
            teacher_user_id=user_id,
            role_type=data.role_type,
            scope_type=data.scope_type,
            scope_id=scope_id,
            is_active=True,
            assigned_by=assigned_by,
            expires_at=datetime.fromisoformat(data.expires_at) if data.expires_at else None,
            notes=data.notes,
        )
        db.add(assignment)
        await db.commit()
        await db.refresh(assignment)

        return TeacherRoleAssignmentOut.model_validate(assignment)

    @staticmethod
    async def list_roles(
        db: AsyncSession,
        school_id: int,
        user_id: int,
        is_active: bool | None = None,
    ) -> list[TeacherRoleAssignmentOut]:
        """查询教师角色分配列表"""
        conditions = [
            TeacherRoleAssignment.school_id == school_id,
            TeacherRoleAssignment.teacher_user_id == user_id,
        ]
        if is_active is not None:
            conditions.append(TeacherRoleAssignment.is_active == is_active)

        result = await db.execute(
            select(TeacherRoleAssignment)
            .where(and_(*conditions))
            .order_by(TeacherRoleAssignment.role_type.asc())
        )
        return [TeacherRoleAssignmentOut.model_validate(a) for a in result.scalars().all()]

    @staticmethod
    async def update_role(
        db: AsyncSession,
        school_id: int,
        assignment_id: int,
        is_active: bool | None = None,
        expires_at: str | None = None,
        notes: str | None = None,
    ) -> TeacherRoleAssignmentOut:
        """更新角色分配 (启用/停用/设过期/备注)"""
        result = await db.execute(
            select(TeacherRoleAssignment).where(
                and_(
                    TeacherRoleAssignment.id == assignment_id,
                    TeacherRoleAssignment.school_id == school_id,
                )
            )
        )
        assignment = result.scalar_one_or_none()
        if not assignment:
            raise ValueError(f"角色分配 {assignment_id} 不存在")

        if is_active is not None:
            assignment.is_active = is_active
        if expires_at is not None:
            assignment.expires_at = datetime.fromisoformat(expires_at)
        if notes is not None:
            assignment.notes = notes

        await db.commit()
        await db.refresh(assignment)
        return TeacherRoleAssignmentOut.model_validate(assignment)

    @staticmethod
    async def delete_role(
        db: AsyncSession,
        school_id: int,
        assignment_id: int,
    ) -> bool:
        """删除角色分配"""
        result = await db.execute(
            select(TeacherRoleAssignment).where(
                and_(
                    TeacherRoleAssignment.id == assignment_id,
                    TeacherRoleAssignment.school_id == school_id,
                )
            )
        )
        assignment = result.scalar_one_or_none()
        if not assignment:
            return False

        await db.delete(assignment)
        await db.commit()
        return True

    # ═══════════════════════════════════════════════════════════
    # 核心聚合: resolve_effective_roles — 排课+审批+大盘三切面
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def resolve_effective_roles(
        db: AsyncSession,
        school_id: int,
        user_id: int,
    ) -> EffectiveRolesOut | None:
        """
        解析教师有效角色集合 — BOSS 核心需求

        三个权限切面:
          - 排课引擎 (workload_profile): subject_teacher 角色决定课时负载
          - 审批流    (permission_scopes): grade_leader/moral_admin 角色决定审批权限
          - 大盘视角  (叠加所有角色决定数据可见范围)

        有效角色 = teacher_role_assignments 中 is_active=True 且未过期的角色
        + User.role 主角色作为兜底
        """
        # 查教师 User
        user_result = await db.execute(
            select(User).where(and_(User.id == user_id, User.school_id == school_id))
        )
        user = user_result.scalar_one_or_none()
        if not user:
            return None

        # 查所有活跃角色分配
        now = datetime.now()
        ra_result = await db.execute(
            select(TeacherRoleAssignment).where(
                and_(
                    TeacherRoleAssignment.school_id == school_id,
                    TeacherRoleAssignment.teacher_user_id == user_id,
                    TeacherRoleAssignment.is_active == True,
                )
            )
        )
        assignments = ra_result.scalars().all()

        # 过滤已过期
        effective_roles = []
        for a in assignments:
            if a.expires_at and a.expires_at < now:
                continue  # 已过期
            scope_name = await TeacherService._resolve_scope_name(
                db,
                a.scope_type,
                a.scope_id,
            )
            effective_roles.append(
                EffectiveRoleOut(
                    role_type=a.role_type,
                    scope_type=a.scope_type,
                    scope_id=a.scope_id,
                    scope_name=scope_name,
                    is_active=a.is_active,
                    assigned_at=a.assigned_at,
                    expires_at=a.expires_at,
                )
            )

        # 如果没有 overlay 角色, 用 User.role 作为兜底
        if not effective_roles:
            effective_roles.append(
                EffectiveRoleOut(
                    role_type="subject_teacher",  # 默认科任教师
                    scope_type="school",
                    scope_id=None,
                    scope_name="全校",
                    is_active=True,
                )
            )

        # ─── 排课引擎供给侧数据 ───
        # 查 TeacherExtension 获取 max_weekly_hours
        ext_result = await db.execute(
            select(TeacherExtension).where(
                and_(
                    TeacherExtension.user_id == user_id,
                    TeacherExtension.school_id == school_id,
                )
            )
        )
        ext = ext_result.scalar_one_or_none()

        # 查最近学期工作量
        wl_result = await db.execute(
            select(TeacherWorkload)
            .where(
                and_(
                    TeacherWorkload.teacher_user_id == user_id,
                    TeacherWorkload.school_id == school_id,
                )
            )
            .order_by(desc(TeacherWorkload.semester))
            .limit(1)
        )
        latest_workload = wl_result.scalar_one_or_none()

        workload_profile = {
            "max_weekly_hours": ext.max_weekly_hours if ext else None,
            "current_weekly_periods": latest_workload.weekly_periods if latest_workload else 0,
            "current_class_count": latest_workload.class_count if latest_workload else 0,
            "subject_teacher_roles": [
                r.dict() for r in effective_roles if r.role_type == "subject_teacher"
            ],
            "available_capacity": None,  # max - current, 排课引擎用
        }
        if workload_profile["max_weekly_hours"] is not None:
            workload_profile["available_capacity"] = (
                workload_profile["max_weekly_hours"] - workload_profile["current_weekly_periods"]
            )

        # ─── 审批流权限切面 ───
        permission_scopes = {
            "can_approve_discipline": any(
                r.role_type in ("grade_leader", "moral_admin", "ms_admin") for r in effective_roles
            ),
            "can_approve_leave": any(
                r.role_type in ("grade_leader", "moral_admin", "ms_admin") for r in effective_roles
            ),
            "visible_grades": [],  # 大盘可看年级
            "visible_classes": [],  # 大盘可看班级
        }

        for r in effective_roles:
            if r.role_type == "grade_leader" and r.scope_type == "grade" and r.scope_id:
                permission_scopes["visible_grades"].append(
                    {
                        "grade_id": r.scope_id,
                        "grade_name": r.scope_name,
                    }
                )
            if r.role_type == "homeroom_teacher" and r.scope_type == "class" and r.scope_id:
                permission_scopes["visible_classes"].append(
                    {
                        "class_id": r.scope_id,
                        "class_name": r.scope_name,
                    }
                )
            if r.role_type == "moral_admin" and r.scope_type == "school":
                # 德育处主任看全校
                permission_scopes["visible_grades"].append({"grade_id": None, "grade_name": "全校"})
                permission_scopes["visible_classes"].append(
                    {"class_id": None, "class_name": "全校"}
                )

        return EffectiveRolesOut(
            teacher_user_id=user_id,
            display_name=user.display_name,
            primary_role=user.role,
            effective_roles=effective_roles,
            workload_profile=workload_profile,
            permission_scopes=permission_scopes,
        )

    @staticmethod
    async def _resolve_scope_name(
        db: AsyncSession,
        scope_type: str,
        scope_id: int | None,
    ) -> str | None:
        """解析作用域名称 (scope_id → scope_name)"""
        if scope_type == "school":
            return "全校"
        if scope_type == "grade" and scope_id:
            result = await db.execute(select(Grade).where(Grade.id == scope_id))
            grade = result.scalar_one_or_none()
            return grade.name if grade else f"年级#{scope_id}"
        if scope_type == "class" and scope_id:
            result = await db.execute(select(Class).where(Class.id == scope_id))
            cls = result.scalar_one_or_none()
            return cls.name if cls else f"班级#{scope_id}"
        if scope_type == "subject_group" and scope_id:
            return f"学科组#{scope_id}"  # TODO: 学科组名称解析
        return None
