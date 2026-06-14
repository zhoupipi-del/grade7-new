# 权限系统迁移指南

## 📋 概述

本指南帮助你将现有蓝图逐步迁移到**全局权限防护系统**。

---

## 🚀 快速开始（3分钟）

### 方式1：装饰器模式（推荐，灵活性高）

```python
# 在蓝图文件中
from decorators import login_required, require_role, require_permission

@bp.route('/add')
@login_required
@require_permission('manage_discipline')  # ← 新增：细粒度权限
def add_discipline():
    ...

@bp.route('/edit/<int:id>')
@login_required
@require_permission('edit_discipline')
def edit_discipline(id):
    ...
```

### 方式2：蓝图级保护（适合整站统一权限）

```python
# 在蓝图文件中
from decorators import protect_blueprint

bp = Blueprint('discipline', __name__)

# 所有路由都需要 'manage_discipline' 权限
protect_blueprint(bp, 'manage_discipline')

@bp.route('/add')
@login_required  # 只需登录检查，权限由 before_request 处理
def add_discipline():
    ...
```

---

## 📊 权限标识清单

在 `decorators.py` 的 `PermissionRegistry.PERMISSIONS` 中定义，当前支持的权限：

| 权限标识 | 描述 | 适用角色 |
|---------|------|----------|
| `view_scores` | 查看成绩 | ms_admin, grade_leader, class_teacher, teacher, parent, student |
| `edit_scores` | 编辑成绩 | ms_admin, grade_leader, class_teacher |
| `manage_discipline` | 管理违纪记录 | ms_admin, grade_leader, class_teacher |
| `view_mental_health` | 查看心理健康评估 | ms_admin, grade_leader, class_teacher |
| `export_data` | 导出数据 | ms_admin, grade_leader |
| ... | ... | ... |

**查看完整列表**：
```bash
python3 -c "from decorators import PermissionRegistry; [print(f'{k}: {v}') for k,v in PermissionRegistry.PERMISSIONS.items()]"
```

---

## 🔄 迁移步骤

### 步骤1：检查当前权限状态

```bash
cd /opt/grade7-new
python3 scripts/check_permission_guards.py
```

**输出示例**：
```
🔴 high_risk_route_1  (缺少权限保护)
🟡 medium_risk_route_2  (仅有登录检查)
```

### 步骤2：按优先级迁移

**优先级排序**：
1. 🔴 **高危路由**（无任何权限保护）→ 立即修复
2. 🟡 **中危路由**（仅有登录检查）→ 本周内修复
3. 🟢 **低危路由**（已有完整保护）→ 无需修改

### 步骤3：选择迁移方式

#### 选项A：保留现有 `@require_role`（向后兼容）

如果你的代码已经使用了 `@require_role(...)`，可以**逐步迁移**：

```python
# 现有代码（保留，仍能工作）
@bp.route('/add')
@login_required
@require_role('ms_admin', 'grade_leader')
def add_discipline():
    ...

# 逐步添加细粒度权限（可选）
@bp.route('/add')
@login_required
@require_role('ms_admin', 'grade_leader')
@require_permission('manage_discipline')  # ← 新增
def add_discipline():
    ...
```

#### 选项B：直接使用 `@require_permission`（推荐新代码）

```python
@bp.route('/add')
@login_required
@require_permission('manage_discipline')
def add_discipline():
    ...
```

**区别**：
- `@require_role`：检查角色（如 `ms_admin`）
- `@require_permission`：检查权限（如 `manage_discipline`）
- **推荐**：新代码用 `@require_permission`，因为它更灵活（角色 → 权限的映射在 `PermissionRegistry` 中集中管理）

### 步骤4：批量迁移脚本（可选）

如果你想**一次性为所有路由添加权限守卫**，可以使用以下脚本：

```python
# scripts/batch_add_permission_guards.py
import ast
import sys

def add_permission_decorator(filepath):
    """自动为路由添加 @require_permission 装饰器"""
    # 注意：这是一个示例脚本，实际使用前请仔细测试！
    # 建议手动迁移重要的路由
    pass
```

**⚠️ 警告**：自动迁移脚本有风险，建议**手动迁移**重要路由。

---

## 🛡️ 审计日志

迁移完成后，所有越权访问尝试都会被**自动记录**：

### 日志位置

1. **应用日志**（`/var/log/grade7-new.log` 或 systemd journal）：
   ```
   WARNING [SECURITY] Unauthorized access attempt: {"timestamp": "...", "user_id": 123, ...}
   ```

2. **未来扩展**（可选）：
   - 写入数据库 `audit_log` 表
   - 发送安全告警邮件
   - 集成到 ELK / Splunk

### 测试审计日志

```bash
# 用一个低权限用户尝试访问高权限路由
curl -X POST https://lijiangschool.online/discipline/add \
  -H "Cookie: session=low_privilege_user_session"

# 检查日志
journalctl -u grade7-new -f | grep SECURITY
```

---

## 📈 权限矩阵报告

生成所有角色的权限矩阵（Markdown格式）：

```bash
cd /opt/grade7-new
python3 -c "
from decorators import generate_permission_matrix
print(generate_permission_matrix())
" > permission_matrix.md
```

**输出示例**：
```markdown
# 权限矩阵报告

| 权限标识 | ms_admin | grade_leader | class_teacher | ... |
|----------|----------|--------------|--------------|-----|
| view_scores | ✅ | ✅ | ✅ | ... |
| edit_scores | ✅ | ✅ | ✅ | ... |
| manage_discipline | ✅ | ✅ | ✅ | ... |
```

---

## 🔧 常见问题

### Q1：我应该选 `@require_role` 还是 `@require_permission`？

**推荐**：
- **新代码**：用 `@require_permission`（更灵活）
- **旧代码**：保留 `@require_role`，逐步迁移

**原因**：
- 角色是"粗粒度"（如 `ms_admin` 能做任何事）
- 权限是"细粒度"（如 `manage_discipline` 只能管理违纪）
- 未来如果需要调整权限，只需修改 `PermissionRegistry.ROLE_PERMISSIONS`，无需改代码

### Q2：如何为现有角色添加新权限？

编辑 `decorators.py` 中的 `PermissionRegistry.ROLE_PERMISSIONS`：

```python
"grade_leader": [
    # ... 现有权限 ...
    "new_permission",  # ← 新增
],
```

### Q3：如何创建自定义权限？

1. 在 `PermissionRegistry.PERMISSIONS` 中定义：
   ```python
   "custom_permission": "自定义权限描述",
   ```

2. 分配给角色：
   ```python
   "ms_admin": [
       # ... 现有权限 ...
       "custom_permission",
   ],
   ```

3. 在视图函数中使用：
   ```python
   @require_permission('custom_permission')
   def my_view():
       ...
   ```

### Q4：`protect_blueprint` 和 `@require_permission` 可以混用吗？

**可以**！但需要注意优先级：

1. **蓝图级 `before_request`** 先执行
2. **装饰器** 后执行

如果两者都配置了，**装饰器会覆盖蓝图级设置**（即路由可以有更严格的权限要求）。

**推荐做法**：
- 大多数路由用**蓝图级保护**（统一权限）
- 特殊路由用**装饰器**（覆盖默认权限）

---

## ✅ 迁移完成检查清单

- [ ] 运行 `check_permission_guards.py`，确认无高危路由
- [ ] 测试所有角色的访问权限（用不同账号登录测试）
- [ ] 检查审计日志，确认越权访问被正确记录
- [ ] 生成权限矩阵报告，审查角色权限分配是否合理
- [ ] 更新文档，记录新增的权限标识

---

## 📞 需要帮助？

如果遇到问题，请检查：
1. `decorators.py` 是否正确导入
2. 权限标识是否拼写正确
3. 角色的权限列表是否包含所需权限

**也可以问我** 😊
