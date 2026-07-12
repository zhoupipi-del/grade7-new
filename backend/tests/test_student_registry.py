# -*- coding: utf-8 -*-
"""
tests/test_student_registry.py — 学籍管理模块单元测试

BOSS 要求：单元测试先行，每个新接口都要有测试。
覆盖：学号生成/创建学籍/状态机/批量导入/统计等核心逻辑。

运行方式：
    cd backend
    python -m pytest tests/test_student_registry.py -v
"""

import pytest
import asyncio
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

# ── 测试学号生成 ──

class TestStudentNoGeneration:
    """学号生成规则测试"""

    @pytest.mark.asyncio
    async def test_generate_student_no_format(self):
        """学号格式：入学年(4) + 年级(1) + 班序(2) + 序号(2)"""
        from modules.student_registry.services import StudentRegistryService

        # Mock db
        db = MagicMock()
        grade = MagicMock()
        grade.sort_order = 7
        grade.name = "七年级"
        db.get = AsyncMock(side_effect=[grade, None])  # grade found, class not found

        cls = MagicMock()
        cls.name = "2501"
        db.get = AsyncMock(side_effect=[grade, cls])

        # Mock count query
        result_mock = MagicMock()
        result_mock.scalar = MagicMock(return_value=0)
        db.execute = AsyncMock(return_value=result_mock)

        student_no = await StudentRegistryService.generate_student_no(db, 1, 1, 1)

        # 验证格式
        assert len(student_no) == 9
        assert student_no[:4] == str(date.today().year - (7 - 7))  # enrollment_year
        assert student_no[4] == "7"  # grade
        assert int(student_no[5:7]) == 1  # class seq (01 from 2501 % 100 = 1)
        assert int(student_no[7:9]) == 1  # seq (first student)

    @pytest.mark.asyncio
    async def test_generate_student_no_increments(self):
        """学号序号递增"""
        from modules.student_registry.services import StudentRegistryService

        db = MagicMock()
        grade = MagicMock()
        grade.sort_order = 7
        cls = MagicMock()
        cls.name = "01"
        db.get = AsyncMock(side_effect=[grade, cls])

        result_mock = MagicMock()
        result_mock.scalar = MagicMock(return_value=15)  # 已有15人
        db.execute = AsyncMock(return_value=result_mock)

        student_no = await StudentRegistryService.generate_student_no(db, 1, 1, 1)
        assert int(student_no[7:9]) == 16  # 第16人


# ── 测试状态机 ──

class TestStatusMachine:
    """学籍状态机测试"""

    def test_valid_transitions(self):
        """合法状态转换"""
        from modules.student_registry.models import VALID_TRANSITIONS

        # active 可以转到所有其他状态
        assert "suspended" in VALID_TRANSITIONS["active"]
        assert "transferred" in VALID_TRANSITIONS["active"]
        assert "graduated" in VALID_TRANSITIONS["active"]
        assert "inactive" in VALID_TRANSITIONS["active"]

        # suspended 可以复学或注销
        assert "active" in VALID_TRANSITIONS["suspended"]
        assert "inactive" in VALID_TRANSITIONS["suspended"]

        # 终态不能转换
        assert len(VALID_TRANSITIONS["transferred"]) == 0
        assert len(VALID_TRANSITIONS["graduated"]) == 0
        assert len(VALID_TRANSITIONS["inactive"]) == 0

    def test_invalid_transitions(self):
        """非法状态转换"""
        from modules.student_registry.models import VALID_TRANSITIONS

        # active 不能直接转回 active（无意义）
        assert "active" not in VALID_TRANSITIONS["active"]

        # transferred 不能复学
        assert "active" not in VALID_TRANSITIONS["transferred"]

        # graduated 不能转学
        assert "transferred" not in VALID_TRANSITIONS["graduated"]

    @pytest.mark.asyncio
    async def test_change_status_valid(self):
        """合法状态变更"""
        from modules.student_registry.services import StudentRegistryService
        from modules.student_registry.models import StudentRegistryExt
        from modules.student_registry.schemas import StatusChangeCreate

        db = MagicMock()

        # Mock 扩展记录
        ext = MagicMock()
        ext.registry_status = "active"
        ext.student_id = 1
        ext.school_id = 1

        result_mock = MagicMock()
        result_mock.scalar_one_or_none = MagicMock(return_value=ext)
        db.execute = AsyncMock(return_value=result_mock)

        # Mock student
        student = MagicMock()
        student.is_active = True
        student.class_id = 1
        db.get = AsyncMock(side_effect=[student, MagicMock()])  # student, class

        # Mock class
        cls = MagicMock()
        cls.student_count = 40

        db.add = MagicMock()
        db.flush = AsyncMock()

        change = await StudentRegistryService.change_status(
            db, 1, 1,
            StatusChangeCreate(change_type="suspend", reason="病休"),
            operated_by=1, operator_name="管理员",
        )

        assert change.from_status == "active"
        assert change.to_status == "suspended"
        assert change.change_type == "suspend"

    @pytest.mark.asyncio
    async def test_change_status_invalid(self):
        """非法状态变更应抛 ValueError"""
        from modules.student_registry.services import StudentRegistryService
        from modules.student_registry.schemas import StatusChangeCreate

        db = MagicMock()

        # Mock 扩展记录 — 已毕业
        ext = MagicMock()
        ext.registry_status = "graduated"
        ext.student_id = 1
        ext.school_id = 1

        result_mock = MagicMock()
        result_mock.scalar_one_or_none = MagicMock(return_value=ext)
        db.execute = AsyncMock(return_value=result_mock)

        # 尝试从 graduated 转到 active（非法）
        with pytest.raises(ValueError, match="非法状态转换"):
            await StudentRegistryService.change_status(
                db, 1, 1,
                StatusChangeCreate(change_type="resume"),
                operated_by=1, operator_name="管理员",
            )


# ── 测试批量导入 ──

class TestBatchImport:
    """批量导入测试"""

    @pytest.mark.asyncio
    async def test_batch_import_success(self):
        """批量导入成功"""
        from modules.student_registry.services import StudentRegistryService

        db = MagicMock()

        # Mock create_student
        created_students = []

        async def mock_create(db, school_id, data, created_by, sync_status="native"):
            mock_student = MagicMock()
            mock_student.id = len(created_students) + 1
            created_students.append(mock_student)
            return mock_student

        with patch.object(StudentRegistryService, "create_student", mock_create):
            result = await StudentRegistryService.batch_import(
                db, 1,
                [
                    {"name": "张三", "class_id": 1, "grade_id": 1},
                    {"name": "李四", "class_id": 1, "grade_id": 1},
                    {"name": "王五", "class_id": 1, "grade_id": 1},
                ],
                imported_by=1,
            )

        assert result["total"] == 3
        assert result["success"] == 3
        assert result["failed"] == 0
        assert len(result["imported_ids"]) == 3

    @pytest.mark.asyncio
    async def test_batch_import_with_errors(self):
        """批量导入含错误"""
        from modules.student_registry.services import StudentRegistryService

        db = MagicMock()
        call_count = [0]

        async def mock_create(db, school_id, data, created_by, sync_status="native"):
            call_count[0] += 1
            if call_count[0] == 2:  # 第二条失败
                raise ValueError("班级不存在")
            mock_student = MagicMock()
            mock_student.id = call_count[0]
            return mock_student

        with patch.object(StudentRegistryService, "create_student", mock_create):
            result = await StudentRegistryService.batch_import(
                db, 1,
                [
                    {"name": "张三", "class_id": 1, "grade_id": 1},
                    {"name": "李四", "class_id": 999, "grade_id": 1},  # 错误数据
                    {"name": "王五", "class_id": 1, "grade_id": 1},
                ],
                imported_by=1,
            )

        assert result["total"] == 3
        assert result["success"] == 2
        assert result["failed"] == 1
        assert len(result["errors"]) == 1
        assert result["errors"][0]["name"] == "李四"


# ── 测试创建学籍 ──

class TestCreateStudent:
    """创建学籍测试"""

    @pytest.mark.asyncio
    async def test_create_student_success(self):
        """成功创建学籍"""
        from modules.student_registry.services import StudentRegistryService
        from modules.student_registry.schemas import StudentCreate

        db = MagicMock()

        # Mock 班级
        cls = MagicMock()
        cls.school_id = 1
        cls.student_count = 0

        # Mock 年级
        grade = MagicMock()
        grade.school_id = 1
        grade.sort_order = 7
        grade.name = "七年级"

        db.get = AsyncMock(side_effect=[cls, grade])

        # Mock 学号生成
        with patch.object(StudentRegistryService, "generate_student_no", AsyncMock(return_value="202670101")):
            # Mock 学号查重
            existing_mock = MagicMock()
            existing_mock.scalar_one_or_none = MagicMock(return_value=None)
            db.execute = AsyncMock(return_value=existing_mock)

            db.add = MagicMock()
            db.flush = AsyncMock()

            data = StudentCreate(
                name="张三",
                class_id=1,
                grade_id=1,
                gender="M",
            )

            student = await StudentRegistryService.create_student(db, 1, data, 1)

            assert student.name == "张三"
            assert student.student_no == "202670101"
            assert student.is_active == True

    @pytest.mark.asyncio
    async def test_create_student_class_not_found(self):
        """班级不存在"""
        from modules.student_registry.services import StudentRegistryService
        from modules.student_registry.schemas import StudentCreate

        db = MagicMock()
        db.get = AsyncMock(return_value=None)  # 班级不存在

        data = StudentCreate(name="张三", class_id=999, grade_id=1)

        with pytest.raises(ValueError, match="班级不存在"):
            await StudentRegistryService.create_student(db, 1, data, 1)

    @pytest.mark.asyncio
    async def test_create_student_duplicate_no(self):
        """学号重复"""
        from modules.student_registry.services import StudentRegistryService
        from modules.student_registry.schemas import StudentCreate

        db = MagicMock()

        cls = MagicMock()
        cls.school_id = 1
        grade = MagicMock()
        grade.school_id = 1
        grade.sort_order = 7
        db.get = AsyncMock(side_effect=[cls, grade])

        with patch.object(StudentRegistryService, "generate_student_no", AsyncMock(return_value="202670101")):
            # Mock 学号已存在
            existing_student = MagicMock()
            existing_mock = MagicMock()
            existing_mock.scalar_one_or_none = MagicMock(return_value=existing_student)
            db.execute = AsyncMock(return_value=existing_mock)

            data = StudentCreate(name="张三", class_id=1, grade_id=1)

            with pytest.raises(ValueError, match="学号已存在"):
                await StudentRegistryService.create_student(db, 1, data, 1)
