"""
modules/student_registry/rollover.py — 新学年滚动晋升引擎

开学前最大的一颗雷：把「毕业出档 + 年级晋升 + 新生导入」做成
一个**单事务、幂等、可预览**的原子操作。

设计铁律（与 Wings 3.0 保守演进一致）:
- 全端点即一个数据库事务（app.py 的 get_db_override 正常返回自动 commit，
  异常自动 rollback）。引擎内部**绝不调用 db.commit()**，保证原子性。
- 仅有 ms_admin 能触发（路由层 require_role 守卫）。
- 幂等：rollover_lock(school_id, school_year) 唯一约束，重复/并发调用被拦截。
- 旧班归档 + 同名同校建新班（用户拍板策略），毕业生 class_id 保留不置空。
- 执行顺序 P3(毕业) → P4(自顶向下晋升 8->9 先于 7->8) → P5(新生)，
  避免新班建好后被二次晋升。
- 家长账号创建不在本引擎范围（属 parent 模块），留作后续独立流程。

阶段:
  P0  幂等锁检查 + 加锁
  P1  预检（目标 grade 行存在、活跃学生计数）
  P2  冷冻快照（student_year_history）
  P3  毕业出档（最高年级 graduate + 班级改名归档）
  P4  自顶向下晋升（旧班改名归档 + 同名建新班 + 学生平移）
  P5  新生导入（可选 freshmen 列表）
"""

import logging
from collections import defaultdict
from datetime import date

from core.models import Class, Grade, Student, User
from modules.student_registry.models import RolloverLock, StudentYearHistory
from modules.student_registry.schemas import StatusChangeCreate
from modules.student_registry.services import StudentRegistryService
from sqlalchemy import (
    func,
    insert,
    select,
    update,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class RolloverError(Exception):
    """引擎级可控异常 — 携带 HTTP 状态码，由路由层转换为 HTTPException。"""

    def __init__(self, detail: str, status_code: int = 400):
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


class RolloverEngine:
    """新学年滚动晋升引擎 — 纯 Static Method，db 为第一参数。"""

    # ═══════════════════════════════════════════════════════════
    # 工具
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def _compute_school_year(explicit: str | None) -> str:
        """学年标识：默认当年-次年（7-8 月滚动即筹备当年秋季学期）。"""
        if explicit:
            return explicit.strip()
        today = date.today()
        start = today.year
        return f"{start}-{start + 1}"

    @staticmethod
    async def _load_grades(db: AsyncSession, school_id: int) -> list[Grade]:
        result = await db.execute(
            select(Grade)
            .where(Grade.school_id == school_id, Grade.is_active == True)  # noqa: E712
            .order_by(Grade.sort_order)
        )
        return list(result.scalars().all())

    @staticmethod
    async def _count_active_students(
        db: AsyncSession, school_id: int, grade_id: int | None = None
    ) -> int:
        stmt = select(func.count(Student.id)).where(
            Student.school_id == school_id,
            Student.is_active == True,  # noqa: E712
        )
        if grade_id is not None:
            stmt = stmt.where(Student.grade_id == grade_id)
        return (await db.execute(stmt)).scalar() or 0

    # ═══════════════════════════════════════════════════════════
    # P0 幂等锁
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def _acquire_lock(
        db: AsyncSession, school_id: int, school_year: str, operator: User, note: str | None
    ) -> RolloverLock:
        # 已存在且未释放 -> 幂等拦截（含并发重复插入由唯一约束兜底）
        existing = (
            (
                await db.execute(
                    select(RolloverLock).where(
                        RolloverLock.school_id == school_id,
                        RolloverLock.school_year == school_year,
                    )
                )
            )
            .scalars()
            .first()
        )
        if existing and existing.released_at is None:
            raise RolloverError(
                f"该校 {school_year} 学年已执行滚动晋升（锁ID={existing.id}），"
                f"重复执行被幂等护栏拦截。如需重跑请先释放该锁。",
                status_code=409,
            )

        lock = RolloverLock(
            school_id=school_id,
            school_year=school_year,
            locked_by=operator.id,
            note=note or f"rollover {school_year}",
            released_at=None,
        )
        db.add(lock)
        try:
            await db.flush()
        except IntegrityError:
            # 并发竞争：另一请求已抢先加锁
            raise RolloverError(
                f"该校 {school_year} 学年滚动晋升正在进行（并发竞争锁失败），请稍后重试。",
                status_code=409,
            )
        return lock

    # ═══════════════════════════════════════════════════════════
    # P2 冷冻快照
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def _snapshot(db: AsyncSession, school_id: int, school_year: str) -> int:
        rows = (
            await db.execute(
                select(Student.id, Student.grade_id, Student.class_id).where(
                    Student.school_id == school_id,
                    Student.is_active == True,  # noqa: E712
                )
            )
        ).all()
        if not rows:
            return 0
        payload = [
            {
                "school_id": school_id,
                "student_id": r[0],
                "school_year": school_year,
                "grade_id": r[1],
                "class_id": r[2],
            }
            for r in rows
        ]
        await db.execute(insert(StudentYearHistory), payload)
        return len(payload)

    # ═══════════════════════════════════════════════════════════
    # P3 毕业出档（最高年级）
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def _graduate_grade(
        db: AsyncSession, school_id: int, grade: Grade, school_year: str, operator: User
    ) -> int:
        students = (
            (
                await db.execute(
                    select(Student).where(
                        Student.grade_id == grade.id,
                        Student.school_id == school_id,
                        Student.is_active == True,  # noqa: E712
                    )
                )
            )
            .scalars()
            .all()
        )

        for stu in students:
            await StudentRegistryService.change_status(
                db,
                school_id,
                stu.id,
                StatusChangeCreate(
                    change_type="graduate",
                    reason=f"新学年滚动晋升 - {school_year} 毕业出档",
                ),
                operator.id,
                operator.display_name or "",
            )

        # 该年级班级改名归档（class_id 保留，不置空）
        classes = (
            (
                await db.execute(
                    select(Class).where(
                        Class.grade_id == grade.id,
                        Class.school_id == school_id,
                        Class.is_active == True,  # noqa: E712
                    )
                )
            )
            .scalars()
            .all()
        )
        for cls in classes:
            cls.name = f"{cls.name}（{school_year}归档）"
            cls.is_active = False
            cls.student_count = 0

        logger.info(f"[rollover] 毕业出档 grade={grade.name} 人数={len(students)}")
        return len(students)

    # ═══════════════════════════════════════════════════════════
    # P4 晋升（from_grade -> to_grade）
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def _promote_grade(
        db: AsyncSession,
        school_id: int,
        from_grade: Grade,
        to_grade: Grade,
        school_year: str,
    ) -> tuple[int, list[dict]]:
        classes = (
            (
                await db.execute(
                    select(Class).where(
                        Class.grade_id == from_grade.id,
                        Class.school_id == school_id,
                        Class.is_active == True,  # noqa: E712
                    )
                )
            )
            .scalars()
            .all()
        )

        moved_total = 0
        created = []

        for cls in classes:
            # 同名同校新建高一年级班
            new_cls = Class(
                name=cls.name,
                school_id=school_id,
                grade_id=to_grade.id,
                head_teacher_id=cls.head_teacher_id,
                student_count=0,
                class_type=cls.class_type or "administrative",
                is_active=True,
            )
            db.add(new_cls)
            await db.flush()
            created.append({"grade_id": to_grade.id, "class_id": new_cls.id, "name": new_cls.name})

            # 统计并平移活跃学生
            cnt = (
                await db.execute(
                    select(func.count(Student.id)).where(
                        Student.class_id == cls.id,
                        Student.school_id == school_id,
                        Student.is_active == True,  # noqa: E712
                    )
                )
            ).scalar() or 0

            if cnt > 0:
                stmt = (
                    update(Student)
                    .where(
                        Student.class_id == cls.id,
                        Student.school_id == school_id,
                        Student.is_active == True,  # noqa: E712
                    )
                    .values(grade_id=to_grade.id, class_id=new_cls.id)
                )
                await db.execute(stmt)

            new_cls.student_count = cnt
            moved_total += cnt

            # 旧班改名归档（保留 grade_id 与 class_id，仅停用并改名释放名称）
            cls.name = f"{cls.name}（{school_year}归档）"
            cls.is_active = False
            cls.student_count = 0

        logger.info(
            f"[rollover] 晋升 {from_grade.name} -> {to_grade.name} "
            f"班级数={len(classes)} 平移学生={moved_total}"
        )
        return moved_total, created

    # ═══════════════════════════════════════════════════════════
    # P5 新生导入（可选）
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def _import_freshmen(
        db: AsyncSession,
        school_id: int,
        operator: User,
        grade: Grade,
        freshmen: list[dict],
    ) -> tuple[dict | None, list[dict]]:
        by_class: dict[str, list[dict]] = defaultdict(list)
        for row in freshmen:
            cname = str(row.get("class_name") or row.get("className") or "未知班")
            by_class[cname].append(row)

        created = []
        resolved: list[dict] = []
        for cname, rows in by_class.items():
            new_cls = Class(
                name=cname,
                school_id=school_id,
                grade_id=grade.id,
                student_count=0,
                class_type="administrative",
                is_active=True,
            )
            db.add(new_cls)
            await db.flush()
            created.append({"grade_id": grade.id, "class_id": new_cls.id, "name": cname})
            for r in rows:
                r2 = dict(r)
                r2["class_id"] = new_cls.id
                r2["grade_id"] = grade.id
                resolved.append(r2)

        if not resolved:
            return None, created

        result = await StudentRegistryService.batch_import(db, school_id, resolved, operator.id)
        return result, created

    # ═══════════════════════════════════════════════════════════
    # 主入口
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def run(
        db: AsyncSession,
        school_id: int,
        operator: User,
        school_year: str | None = None,
        dry_run: bool = False,
        freshmen: list[dict] | None = None,
        note: str | None = None,
    ) -> dict:
        school_year = RolloverEngine._compute_school_year(school_year)
        grades = await RolloverEngine._load_grades(db, school_id)
        if not grades:
            raise RolloverError(f"学校 {school_id} 未配置任何年级（grades），无法滚动晋升。")

        by_sort = {g.sort_order: g for g in grades}
        sort_orders = sorted(by_sort.keys())
        min_so, max_so = sort_orders[0], sort_orders[-1]
        min_grade = by_sort[min_so]
        max_grade = by_sort[max_so]

        warnings: list[str] = []

        # 预检：各年级活跃学生计数
        grade_counts = {}
        for g in grades:
            grade_counts[g.id] = await RolloverEngine._count_active_students(db, school_id, g.id)
        total_active = sum(grade_counts.values())

        if total_active == 0:
            warnings.append("该校当前没有活跃在校生，滚动晋升将仅执行空操作。")

        # P1 预检：晋升目标的下一层级年级必须存在
        for so in sort_orders[:-1]:
            if (so + 1) not in by_sort:
                warnings.append(
                    f"年级 {by_sort[so].name} 的下一层级（sort_order={so + 1}）不存在，"
                    f"该年级学生将无法晋升。"
                )

        # ── 干跑：仅返回计划，不做任何写入 ──
        if dry_run:
            plan = {
                "school_year": school_year,
                "status": "dry_run",
                "school_id": school_id,
                "total_active_students": total_active,
                "grade_active_counts": {g.name: grade_counts[g.id] for g in grades},
                "will_graduate_grade": max_grade.name,
                "will_graduate_count": grade_counts.get(max_grade.id, 0),
                "will_promote": [
                    f"{by_sort[so].name} -> {by_sort[so + 1].name}"
                    for so in sort_orders[:-1]
                    if (so + 1) in by_sort
                ],
                "freshmen_provided": bool(freshmen),
                "warnings": warnings,
                "message": "预览模式：未执行任何写操作。",
            }
            return plan

        # ── 正式执行 ──
        # P0 加锁（幂等护栏）
        lock = await RolloverEngine._acquire_lock(db, school_id, school_year, operator, note)

        # P2 冷冻快照
        snapshot_count = await RolloverEngine._snapshot(db, school_id, school_year)

        # P3 毕业出档（最高年级）
        graduated_count = await RolloverEngine._graduate_grade(
            db, school_id, max_grade, school_year, operator
        )

        # P4 自顶向下晋升（8->9 先于 7->8）
        promoted_detail: dict[str, int] = {}
        created_classes: list[dict] = []
        promoted_total = 0
        for so in reversed(sort_orders[:-1]):
            target_so = so + 1
            if target_so not in by_sort:
                continue
            moved, created = await RolloverEngine._promote_grade(
                db, school_id, by_sort[so], by_sort[target_so], school_year
            )
            promoted_detail[f"{by_sort[so].name}->{by_sort[target_so].name}"] = moved
            created_classes.extend(created)
            promoted_total += moved

        # P5 新生导入（可选）
        freshmen_count = 0
        freshmen_result = None
        if freshmen:
            freshmen_result, fresh_created = await RolloverEngine._import_freshmen(
                db, school_id, operator, min_grade, freshmen
            )
            created_classes.extend(fresh_created)
            if freshmen_result:
                freshmen_count = freshmen_result.get("success", 0)

        return {
            "school_year": school_year,
            "status": "success",
            "school_id": school_id,
            "lock_id": lock.id,
            "snapshot_count": snapshot_count,
            "graduated_count": graduated_count,
            "promoted_count": promoted_total,
            "promoted_detail": promoted_detail,
            "freshmen_count": freshmen_count,
            "created_classes": created_classes,
            "warnings": warnings,
            "message": (
                f"滚动晋升完成：快照 {snapshot_count} 人，毕业 {graduated_count} 人，"
                f"晋升 {promoted_total} 人，新生 {freshmen_count} 人。"
            ),
        }
