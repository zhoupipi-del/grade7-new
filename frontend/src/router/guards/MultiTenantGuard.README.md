# MultiTenantGuard — 多校区沙箱穿透网关设计备忘

> **状态**: 设计阶段，未实施。需先后端与 UserStore 改造。
> **关联 Task**: #1034 (多校区集群 — school_id=2 沙箱搭建)

## 设计目标

集团总指挥（MS_ADMIN）在"一中本部"(school_id=1) 与"实验分校"(school_id=2)
之间切换时，看板图表与行级数据无感切流，且班主任/级组长无法越权穿透。

## 实施前置条件 (当前全部缺失)

### 1. UserStore 扩展 (`src/store/user.ts`)

当前 UserStore 只有 `token` + `userInfo`，缺少多租户字段。需新增：

```typescript
interface UserState {
  token: string
  userInfo: UserInfo | null
  // ↓↓↓ 新增 ↓↓↓
  currentTenantId: number          // 当前活跃校区 (默认 = userInfo.school_id)
  accessibleTenants: number[]      // 可穿透的校区列表 (MS_ADMIN = [1,2], 其他角色 = [自己school_id])
  tenantNameMap: Record<number, string>  // {1: '一中本部', 2: '实验分校'}
}

// 新增 actions:
async switchTenantContext(tenantId: number) {
  // 1. 校验 accessibleTenants 包含 tenantId
  // 2. 更新 currentTenantId
  // 3. (可选) 调用后端 /auth/switch-tenant 获取新短期 token
}
```

### 2. 后端端点支持 tenant_id 参数

当前所有后端端点基于 `current_user.school_id`（JWT 编码），**不接受 tenant_id 参数**：

```python
# backend/modules/risk_models/routers.py (当前)
async def get_monitor_panel(..., current_user: User = Depends(get_current_user)):
    panel = await RiskMonitorService.get_monitor_panel(
        db, current_user.school_id, ...  # ← 写死 JWT 里的 school_id
    )
```

需改造为：

```python
async def get_monitor_panel(
    ...,
    tenant_id: Optional[int] = Query(None, description="穿透校区 (仅 MS_ADMIN)"),
    current_user: User = Depends(get_current_user),
):
    # MS_ADMIN 可指定 tenant_id 穿透; 其他角色强制使用自己的 school_id
    effective_school_id = (
        tenant_id if (current_user.role == UserRole.MS_ADMIN and tenant_id)
        else current_user.school_id
    )
    panel = await RiskMonitorService.get_monitor_panel(
        db, effective_school_id, ...
    )
```

涉及端点（需逐个改造）：
- `/risk_models/monitor-panel`
- `/risk_models/dashboard`
- `/discipline/stats`
- `/dashboard/class-radar`
- `/dashboard/trends`
- `/dashboard/correlation-scatter`
- `/behavior/*`
- `/evaluation/*`
- `/attendance/*`

### 3. /403 路由

当前路由表无 `/403`，需在 `router/index.ts` 新增 403 视图。

### 4. accessibleTenants 来源

MS_ADMIN 的 `accessibleTenants` 从哪里获取？三种方案：
- **A. JWT claims** — 登录时后端在 JWT 中注入 `accessible_tenants: [1, 2]`
- **B. /auth/me 端点** — 登录后调用 `/auth/me` 返回该字段
- **C. 硬编码** — 前端硬编码 `{MS_ADMIN: [1, 2]}` (最简但不灵活)

推荐方案 B，与现有 `/auth/me` 模式一致。

## 实施后的守卫代码 (待 UserStore + 后端就绪后启用)

```typescript
// src/router/guards/MultiTenantGuard.ts
import type { NavigationGuardNext, RouteLocationNormalized } from 'vue-router'
import { useUserStore } from '@/store/user'
import { ElMessage } from 'element-plus'

export async function multiTenantGuard(
  to: RouteLocationNormalized,
  from: RouteLocationNormalized,
  next: NavigationGuardNext
) {
  const userStore = useUserStore()

  // 只对需要租户上下文的路由生效
  const requiresTenant = to.meta.requiresTenant === true
  if (!requiresTenant) {
    next()
    return
  }

  const targetTenant = to.query.tenant_id
    ? Number(to.query.tenant_id)
    : userStore.currentTenantId

  // 1. 安全拦截：校验穿透权限
  if (targetTenant && !userStore.accessibleTenants.includes(targetTenant)) {
    ElMessage.error({
      message: `【沙箱越权拦截】您无权调阅校区 ${targetTenant} 的德育及风控数据。`,
      duration: 4000,
    })
    next({ path: from.path || '/403' })
    return
  }

  // 2. 动态环境切流
  if (targetTenant && targetTenant !== userStore.currentTenantId) {
    await userStore.switchTenantContext(targetTenant)
    ElMessage.success(`已切换至【${userStore.tenantNameMap[targetTenant]}】校区沙箱`)
  }

  // 3. 行级权限注入 (供 Axios 拦截器读取)
  to.meta.tenantContext = targetTenant
  next()
}
```

## 当前替代方案 (单租户模式)

在后端与 UserStore 改造完成前，系统维持单租户模式：
- `school_id` 由 JWT 编码，后端 `current_user.school_id` 自动隔离
- 不同校区用户使用不同账号登录，天然隔离
- MS_ADMIN 若需查看另一校区，需用对应校区账号登录 (临时方案)

## 解封条件清单

- [ ] UserStore 扩展 currentTenantId / accessibleTenants / switchTenantContext
- [ ] 后端 9+ 端点接受 tenant_id 参数 (仅 MS_ADMIN 生效)
- [ ] /auth/me 返回 accessible_tenants 字段
- [ ] 新增 /403 路由视图
- [ ] 路由 meta 增加 requiresTenant 标记
- [ ] Axios 请求拦截器自动注入 X-Tenant-Id header
- [ ] Task #1034 (school_id=2 沙箱) 数据迁移完成

满足以上 7 项后，本守卫代码可直接启用。
