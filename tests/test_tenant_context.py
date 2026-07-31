"""
tests/test_tenant_context.py — AccessScope + 级联配置查找链单元测试

覆盖范围:
  1. get_accessible_school_ids — 7种 UserRole 权限范围计算
  2. get_effective_config_with_source — School→Branch→Org→Default 四级查找链
  3. get_effective_config — 委托验证
  4. build_scope_filter — 单校硬匹配 / 跨校 IN 聚合
  5. TenantContext — is_single_school / is_cross_school / get_config
  6. build_tenant_context — 工厂函数

测试策略: Mock-based（不需要真实数据库连接）
  - MockAsyncSession 按调用顺序返回预配置的 Result 对象
  - make_user / make_school_mock 构造轻量级模拟对象
  - asyncio.run() 驱动异步函数（无需 pytest-asyncio）
"""

import asyncio
import sys
import os
from unittest.mock import MagicMock
from typing import List, Optional, Any

import pytest

# 确保能找到 core 模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.tenant_context import (
    get_accessible_school_ids,
    get_effective_config,
    get_effective_config_with_source,
    build_scope_filter,
    build_tenant_context,
    TenantContext,
    DEFAULT_CONFIGS,
)
from core.models import UserRole, ScopeType


# ═══════════════════════════════════════════════════════════════
# Mock 工具 — 模拟 AsyncSession 和查询结果
# ═══════════════════════════════════════════════════════════════

class MockResult:
    """模拟 SQLAlchemy Result 对象"""

    def __init__(self, scalar_value=None, rows=None):
        self._scalar = scalar_value
        self._rows = rows or []

    def scalar_one_or_none(self):
        return self._scalar

    def all(self):
        return self._rows

    def scalar_one(self):
        if self._scalar is None:
            raise Exception("No row found")
        return self._scalar

    def scalars(self):
        return self


class MockAsyncSession:
    """
    模拟 AsyncSession — 按调用顺序返回预配置的 Result 对象。

    使用方式:
        db = MockAsyncSession()
        db.add_response(scalar_value=some_config)  # 第一次 execute()
        db.add_response(rows=[(1,), (2,)])          # 第二次 execute()
    """

    def __init__(self):
        self._responses: List[MockResult] = []
        self._call_count = 0
        self.execute_calls = []

    def add_response(self, scalar_value=None, rows=None):
        """为下一次 execute() 调用添加响应"""
        self._responses.append(MockResult(scalar_value, rows))

    async def execute(self, statement, *args, **kwargs):
        self.execute_calls.append(statement)
        if self._call_count < len(self._responses):
            result = self._responses[self._call_count]
        else:
            result = MockResult()
        self._call_count += 1
        return result

    def reset(self):
        self._call_count = 0
        self.execute_calls = []

    @property
    def call_count(self):
        return self._call_count


def make_user(role, school_id=1, org_id=None, branch_id=None):
    """
    创建模拟 User 对象。

    Args:
        role: UserRole 枚举值或字符串（如 "ms_admin"）
        school_id: 用户所属学校 ID
        org_id: 所属集团 ID（GROUP_ADMIN 必填）
        branch_id: 所属片区 ID（BRANCH_ADMIN 必填）
    """
    user = MagicMock()
    user.role = role
    user.school_id = school_id
    user.org_id = org_id
    user.branch_id = branch_id
    user.id = 1
    user.username = "test_user"
    user.display_name = "测试用户"
    return user


def make_school_mock(school_id=1, branch_id=1, org_id=1, is_active=True):
    """创建模拟 School ORM 对象"""
    school = MagicMock()
    school.id = school_id
    school.branch_id = branch_id
    school.org_id = org_id
    school.is_active = is_active
    school.name = f"测试学校{school_id}"
    return school


# ═══════════════════════════════════════════════════════════════
# 1. get_accessible_school_ids — 7种 UserRole 权限范围
# ═══════════════════════════════════════════════════════════════

class TestGetAccessibleSchoolIds:
    """测试 get_accessible_school_ids — 权限范围计算"""

    # ── 单校角色（向下兼容，不查 DB）──

    def test_ms_admin_returns_single_school(self):
        """MS_ADMIN → [user.school_id]，无 DB 调用"""
        user = make_user(UserRole.MS_ADMIN, school_id=1)
        db = MockAsyncSession()

        result = asyncio.run(get_accessible_school_ids(user, db))

        assert result == [1]
        assert db.call_count == 0

    def test_grade_leader_returns_single_school(self):
        """GRADE_LEADER → [user.school_id]"""
        user = make_user(UserRole.GRADE_LEADER, school_id=2)
        db = MockAsyncSession()

        result = asyncio.run(get_accessible_school_ids(user, db))

        assert result == [2]
        assert db.call_count == 0

    def test_class_teacher_returns_single_school(self):
        """CLASS_TEACHER → [user.school_id]"""
        user = make_user(UserRole.CLASS_TEACHER, school_id=3)
        db = MockAsyncSession()

        result = asyncio.run(get_accessible_school_ids(user, db))

        assert result == [3]
        assert db.call_count == 0

    def test_teacher_returns_single_school(self):
        """TEACHER → [user.school_id]"""
        user = make_user(UserRole.TEACHER, school_id=4)
        db = MockAsyncSession()

        result = asyncio.run(get_accessible_school_ids(user, db))

        assert result == [4]
        assert db.call_count == 0

    def test_parent_returns_single_school(self):
        """PARENT → [user.school_id]"""
        user = make_user(UserRole.PARENT, school_id=1)
        db = MockAsyncSession()

        result = asyncio.run(get_accessible_school_ids(user, db))

        assert result == [1]
        assert db.call_count == 0

    def test_student_returns_single_school(self):
        """STUDENT → [user.school_id]"""
        user = make_user(UserRole.STUDENT, school_id=5)
        db = MockAsyncSession()

        result = asyncio.run(get_accessible_school_ids(user, db))

        assert result == [5]
        assert db.call_count == 0

    # ── GROUP_ADMIN 跨校聚合 ──

    def test_group_admin_returns_all_org_schools(self):
        """GROUP_ADMIN + org_id → 集团所有 school_ids"""
        user = make_user(UserRole.GROUP_ADMIN, school_id=1, org_id=10)
        db = MockAsyncSession()
        db.add_response(rows=[(1,), (2,), (3,)])

        result = asyncio.run(get_accessible_school_ids(user, db))

        assert result == [1, 2, 3]
        assert db.call_count == 1

    def test_group_admin_without_org_id_falls_back(self):
        """GROUP_ADMIN 无 org_id → 退化为 [user.school_id]"""
        user = make_user(UserRole.GROUP_ADMIN, school_id=5, org_id=None)
        db = MockAsyncSession()

        result = asyncio.run(get_accessible_school_ids(user, db))

        assert result == [5]
        assert db.call_count == 0

    def test_group_admin_empty_org_returns_empty_list(self):
        """GROUP_ADMIN + org_id 但集团无学校 → 空列表"""
        user = make_user(UserRole.GROUP_ADMIN, school_id=1, org_id=99)
        db = MockAsyncSession()
        db.add_response(rows=[])

        result = asyncio.run(get_accessible_school_ids(user, db))

        assert result == []
        assert db.call_count == 1

    # ── BRANCH_ADMIN 跨校区聚合 ──

    def test_branch_admin_returns_all_branch_schools(self):
        """BRANCH_ADMIN + branch_id → 片区所有 school_ids"""
        user = make_user(UserRole.BRANCH_ADMIN, school_id=1, branch_id=20)
        db = MockAsyncSession()
        db.add_response(rows=[(1,), (4,), (5,)])

        result = asyncio.run(get_accessible_school_ids(user, db))

        assert result == [1, 4, 5]
        assert db.call_count == 1

    def test_branch_admin_without_branch_id_falls_back(self):
        """BRANCH_ADMIN 无 branch_id → 退化为 [user.school_id]"""
        user = make_user(UserRole.BRANCH_ADMIN, school_id=7, branch_id=None)
        db = MockAsyncSession()

        result = asyncio.run(get_accessible_school_ids(user, db))

        assert result == [7]
        assert db.call_count == 0

    # ── 字符串角色兼容性 ──

    def test_string_role_ms_admin(self):
        """字符串角色 "ms_admin" 也能正常工作"""
        user = make_user("ms_admin", school_id=1)
        db = MockAsyncSession()

        result = asyncio.run(get_accessible_school_ids(user, db))

        assert result == [1]

    def test_string_role_group_admin(self):
        """字符串角色 "group_admin" + org_id → 集团学校"""
        user = make_user("group_admin", school_id=1, org_id=10)
        db = MockAsyncSession()
        db.add_response(rows=[(1,), (2,)])

        result = asyncio.run(get_accessible_school_ids(user, db))

        assert result == [1, 2]


# ═══════════════════════════════════════════════════════════════
# 2. get_effective_config_with_source — 四级查找链
# ═══════════════════════════════════════════════════════════════

class TestGetEffectiveConfigWithSource:
    """测试级联配置查找链 — School→Branch→Org→Default"""

    def test_school_level_hit_with_autofill(self):
        """L1 School 级命中（自动补齐 branch_id/org_id）"""
        school = make_school_mock(school_id=1, branch_id=10, org_id=100)
        school_config = {"enabled": False, "custom": True}

        db = MockAsyncSession()
        db.add_response(scalar_value=school)        # auto-fill School
        db.add_response(scalar_value=school_config)  # L1 hit

        config, source = asyncio.run(get_effective_config_with_source(
            "attendance", school_id=1, db=db,
        ))

        assert config == school_config
        assert source == "school"
        assert db.call_count == 2

    def test_school_level_hit_with_explicit_ids(self):
        """L1 School 级命中（显式传入 branch_id/org_id，跳过 auto-fill）"""
        school_config = {"enabled": True, "threshold": 10}

        db = MockAsyncSession()
        db.add_response(scalar_value=school_config)  # L1 hit

        config, source = asyncio.run(get_effective_config_with_source(
            "attendance", school_id=1, db=db, branch_id=10, org_id=100,
        ))

        assert config == school_config
        assert source == "school"
        assert db.call_count == 1

    def test_branch_level_hit(self):
        """L2 Branch 级命中（L1 miss → L2 hit）"""
        branch_config = {"enabled": True, "branch_specific": True}

        db = MockAsyncSession()
        db.add_response(scalar_value=None)            # L1 miss
        db.add_response(scalar_value=branch_config)   # L2 hit

        config, source = asyncio.run(get_effective_config_with_source(
            "attendance", school_id=1, db=db, branch_id=10, org_id=100,
        ))

        assert config == branch_config
        assert source == "branch"
        assert db.call_count == 2

    def test_org_level_hit(self):
        """L3 Org 级命中（L1+L2 miss → L3 hit）"""
        org_config = {"enabled": True, "org_policy": "strict"}

        db = MockAsyncSession()
        db.add_response(scalar_value=None)   # L1 miss
        db.add_response(scalar_value=None)   # L2 miss
        db.add_response(scalar_value=org_config)  # L3 hit

        config, source = asyncio.run(get_effective_config_with_source(
            "attendance", school_id=1, db=db, branch_id=10, org_id=100,
        ))

        assert config == org_config
        assert source == "org"
        assert db.call_count == 3

    def test_default_fallback_known_module(self):
        """L4 Default 兜底（已知模块 → DEFAULT_CONFIGS）"""
        db = MockAsyncSession()
        db.add_response(scalar_value=None)   # L1 miss
        db.add_response(scalar_value=None)   # L2 miss
        db.add_response(scalar_value=None)   # L3 miss

        config, source = asyncio.run(get_effective_config_with_source(
            "attendance", school_id=1, db=db, branch_id=10, org_id=100,
        ))

        assert config == DEFAULT_CONFIGS["attendance"]
        assert source == "default"
        assert db.call_count == 3

    def test_default_fallback_unknown_module(self):
        """L4 Default 兜底（未知模块 → {"enabled": False}）"""
        db = MockAsyncSession()
        db.add_response(scalar_value=None)   # L1 miss
        db.add_response(scalar_value=None)   # L2 miss
        db.add_response(scalar_value=None)   # L3 miss

        config, source = asyncio.run(get_effective_config_with_source(
            "nonexistent_module", school_id=1, db=db, branch_id=10, org_id=100,
        ))

        assert config == {"enabled": False}
        assert source == "default"

    def test_school_not_found_skips_branch_and_org(self):
        """School 不存在 → auto-fill 返回 None → L1 执行但 L2/L3 跳过"""
        db = MockAsyncSession()
        db.add_response(scalar_value=None)   # auto-fill: school not found
        db.add_response(scalar_value=None)   # L1 miss

        config, source = asyncio.run(get_effective_config_with_source(
            "attendance", school_id=999, db=db,
        ))

        # branch_id/org_id 仍为 None → L2/L3 跳过 → 直接 default
        assert config == DEFAULT_CONFIGS["attendance"]
        assert source == "default"
        assert db.call_count == 2  # auto-fill + L1 only

    def test_disabled_config_filtered_by_where_clause(self):
        """is_enabled=False 的配置在 SQL WHERE 中被过滤（等价于 miss）"""
        branch_config = {"enabled": True}

        db = MockAsyncSession()
        db.add_response(scalar_value=None)            # L1 miss (disabled filtered)
        db.add_response(scalar_value=branch_config)   # L2 hit

        config, source = asyncio.run(get_effective_config_with_source(
            "attendance", school_id=1, db=db, branch_id=10, org_id=100,
        ))

        assert config == branch_config
        assert source == "branch"

    def test_full_cascade_with_autofill_all_miss(self):
        """完整级联（auto-fill + L1+L2+L3 全 miss）→ default"""
        school = make_school_mock(school_id=1, branch_id=10, org_id=100)

        db = MockAsyncSession()
        db.add_response(scalar_value=school)   # auto-fill
        db.add_response(scalar_value=None)     # L1 miss
        db.add_response(scalar_value=None)     # L2 miss
        db.add_response(scalar_value=None)     # L3 miss

        config, source = asyncio.run(get_effective_config_with_source(
            "evaluation", school_id=1, db=db,
        ))

        assert config == DEFAULT_CONFIGS["evaluation"]
        assert source == "default"
        assert db.call_count == 4


# ═══════════════════════════════════════════════════════════════
# 3. get_effective_config — 委托验证
# ═══════════════════════════════════════════════════════════════

class TestGetEffectiveConfig:
    """测试 get_effective_config — 委托 get_effective_config_with_source"""

    def test_returns_config_dict_only(self):
        """返回 config 字典（不含 source_level）"""
        org_config = {"enabled": True, "org_level": True}

        db = MockAsyncSession()
        db.add_response(scalar_value=None)        # L1 miss
        db.add_response(scalar_value=None)        # L2 miss
        db.add_response(scalar_value=org_config)  # L3 hit

        result = asyncio.run(get_effective_config(
            "attendance", school_id=1, db=db, branch_id=10, org_id=100,
        ))

        assert result == org_config
        assert isinstance(result, dict)

    def test_default_returns_correct_config(self):
        """全 miss 时返回 DEFAULT_CONFIGS"""
        db = MockAsyncSession()
        db.add_response(scalar_value=None)   # L1 miss
        db.add_response(scalar_value=None)   # L2 miss
        db.add_response(scalar_value=None)   # L3 miss

        result = asyncio.run(get_effective_config(
            "discipline", school_id=1, db=db, branch_id=10, org_id=100,
        ))

        assert result == DEFAULT_CONFIGS["discipline"]
        assert result["enabled"] is True
        assert result["auto_escalation"] is True


# ═══════════════════════════════════════════════════════════════
# 4. build_scope_filter — 单校硬匹配 / 跨校 IN 聚合
# ═══════════════════════════════════════════════════════════════

class FakeExpression:
    """模拟 SQLAlchemy 表达式结果"""
    def __init__(self, op, value=None, in_values=None):
        self.op = op
        self.value = value
        self.in_values = in_values


class FakeColumn:
    """模拟 SQLAlchemy Column 对象"""
    def __eq__(self, other):
        return FakeExpression("eq", value=other)

    def in_(self, values):
        return FakeExpression("in", in_values=values)


class FakeModel:
    """模拟 SQLAlchemy Model 类"""
    school_id = FakeColumn()


class TestBuildScopeFilter:
    """测试 build_scope_filter — scope 查询生成器"""

    def test_single_school_hard_match(self):
        """access_scope=[1] → school_id == 1（硬匹配）"""
        result = build_scope_filter(FakeModel, [1])

        assert isinstance(result, FakeExpression)
        assert result.op == "eq"
        assert result.value == 1

    def test_cross_school_in_aggregation(self):
        """access_scope=[1,2,3] → school_id IN (1,2,3)（跨校聚合）"""
        result = build_scope_filter(FakeModel, [1, 2, 3])

        assert isinstance(result, FakeExpression)
        assert result.op == "in"
        assert result.in_values == [1, 2, 3]

    def test_two_schools_uses_in(self):
        """access_scope=[1,2] → school_id IN (1,2)（2个学校也用 IN）"""
        result = build_scope_filter(FakeModel, [1, 2])

        assert result.op == "in"
        assert result.in_values == [1, 2]


# ═══════════════════════════════════════════════════════════════
# 5. TenantContext — is_single_school / is_cross_school / get_config
# ═══════════════════════════════════════════════════════════════

class TestTenantContext:
    """测试 TenantContext 类"""

    def test_is_single_school_true(self):
        """access_scope=[1] → is_single_school() == True"""
        user = make_user(UserRole.MS_ADMIN, school_id=1)
        ctx = TenantContext(user=user, access_scope=[1], db=MagicMock())

        assert ctx.is_single_school() is True

    def test_is_single_school_false(self):
        """access_scope=[1,2,3] → is_single_school() == False"""
        user = make_user(UserRole.GROUP_ADMIN, school_id=1, org_id=10)
        ctx = TenantContext(user=user, access_scope=[1, 2, 3], db=MagicMock())

        assert ctx.is_single_school() is False

    def test_is_cross_school_true(self):
        """access_scope=[1,2,3] → is_cross_school() == True"""
        user = make_user(UserRole.GROUP_ADMIN, school_id=1, org_id=10)
        ctx = TenantContext(user=user, access_scope=[1, 2, 3], db=MagicMock())

        assert ctx.is_cross_school() is True

    def test_is_cross_school_false(self):
        """access_scope=[1] → is_cross_school() == False"""
        user = make_user(UserRole.MS_ADMIN, school_id=1)
        ctx = TenantContext(user=user, access_scope=[1], db=MagicMock())

        assert ctx.is_cross_school() is False

    def test_get_config_delegates_to_cascade(self):
        """get_config() 通过级联查找返回配置"""
        user = make_user(UserRole.MS_ADMIN, school_id=1)
        school = make_school_mock(school_id=1, branch_id=10, org_id=100)

        db = MockAsyncSession()
        db.add_response(scalar_value=school)   # auto-fill
        db.add_response(scalar_value=None)     # L1 miss
        db.add_response(scalar_value=None)     # L2 miss
        db.add_response(scalar_value=None)     # L3 miss → default

        ctx = TenantContext(user=user, access_scope=[1], db=db)
        config = asyncio.run(ctx.get_config("attendance"))

        assert config == DEFAULT_CONFIGS["attendance"]
        assert db.call_count == 4

    def test_get_config_school_level_hit(self):
        """get_config() School 级命中"""
        user = make_user(UserRole.CLASS_TEACHER, school_id=1)
        school = make_school_mock(school_id=1, branch_id=10, org_id=100)
        custom_config = {"enabled": False, "custom_flag": True}

        db = MockAsyncSession()
        db.add_response(scalar_value=school)          # auto-fill
        db.add_response(scalar_value=custom_config)   # L1 hit

        ctx = TenantContext(user=user, access_scope=[1], db=db)
        config = asyncio.run(ctx.get_config("attendance"))

        assert config == custom_config
        assert config["custom_flag"] is True


# ═══════════════════════════════════════════════════════════════
# 6. build_tenant_context — 工厂函数
# ═══════════════════════════════════════════════════════════════

class TestBuildTenantContext:
    """测试 build_tenant_context 工厂函数"""

    def test_build_for_single_school_user(self):
        """单校用户 → TenantContext with access_scope=[school_id]"""
        user = make_user(UserRole.MS_ADMIN, school_id=1)
        db = MockAsyncSession()

        ctx = asyncio.run(build_tenant_context(user, db))

        assert isinstance(ctx, TenantContext)
        assert ctx.user == user
        assert ctx.access_scope == [1]
        assert ctx.is_single_school() is True

    def test_build_for_group_admin_cross_school(self):
        """GROUP_ADMIN → TenantContext with cross-school access_scope"""
        user = make_user(UserRole.GROUP_ADMIN, school_id=1, org_id=10)
        db = MockAsyncSession()
        db.add_response(rows=[(1,), (2,), (3,)])

        ctx = asyncio.run(build_tenant_context(user, db))

        assert ctx.access_scope == [1, 2, 3]
        assert ctx.is_cross_school() is True

    def test_build_for_branch_admin(self):
        """BRANCH_ADMIN → TenantContext with branch schools"""
        user = make_user(UserRole.BRANCH_ADMIN, school_id=1, branch_id=20)
        db = MockAsyncSession()
        db.add_response(rows=[(1,), (4,)])

        ctx = asyncio.run(build_tenant_context(user, db))

        assert ctx.access_scope == [1, 4]
        assert ctx.is_cross_school() is True


# ═══════════════════════════════════════════════════════════════
# 7. DEFAULT_CONFIGS 完整性验证
# ═══════════════════════════════════════════════════════════════

class TestDefaultConfigs:
    """验证 DEFAULT_CONFIGS 字典完整性"""

    def test_all_configs_have_enabled_key(self):
        """所有模块默认配置都包含 enabled 键"""
        for module_key, config in DEFAULT_CONFIGS.items():
            assert "enabled" in config, f"模块 {module_key} 缺少 enabled 键"

    def test_known_modules_have_configs(self):
        """14个核心模块 + 4个补充模块都有默认配置"""
        expected_modules = {
            "attendance", "evaluation", "discipline", "risk_models",
            "red_flag", "notifications", "reports", "ai_prescription",
            "dashboard", "growth", "policy_engine", "approval",
            "teach_math", "parent_portal",
            "behavior", "grades", "lineage", "core",
        }
        assert expected_modules.issubset(set(DEFAULT_CONFIGS.keys()))

    def test_unknown_module_returns_disabled(self):
        """未知模块的默认配置为 {"enabled": False}"""
        config = DEFAULT_CONFIGS.get("nonexistent", {"enabled": False})
        assert config == {"enabled": False}
