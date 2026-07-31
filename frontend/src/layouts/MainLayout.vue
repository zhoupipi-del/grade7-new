<template>
  <!-- 启动会话验证 — 防止过期token闪烁旧侧边栏 -->
  <div v-if="isSessionLoading" class="session-loading">
    <el-skeleton :rows="8" animated />
  </div>

  <el-container v-else class="main-layout">
    <!-- Sidebar: dark theme, grouped + role-filtered menu -->
    <el-aside :width="isCollapsed ? '64px' : '240px'" class="sidebar">
      <div class="logo-section">
        <img src="/favicon.svg" alt="logo" class="logo-icon" v-if="!isCollapsed" />
        <h1 v-if="!isCollapsed" class="logo-text">Wings 3.0</h1>
        <img src="/favicon.svg" alt="logo" class="logo-icon-collapsed" v-else />
      </div>

      <el-menu
        v-if="visibleGroups.length > 0"
        :default-active="activeMenu"
        :collapse="isCollapsed"
        :collapse-transition="false"
        :unique-opened="true"
        router
        class="sidebar-menu"
        background-color="#1f2c3f"
        text-color="#bfcbd9"
        active-text-color="#ffffff"
      >
        <el-sub-menu
          v-for="group in visibleGroups"
          :key="group.title"
          :index="group.title"
        >
          <template #title>
            <el-icon><component :is="group.icon" /></el-icon>
            <span>{{ group.title }}</span>
          </template>

          <el-menu-item
            v-for="item in group.items"
            :key="item.menuCode"
            :index="routePathMap[item.routeName] ?? '/' + item.menuCode"
          >
            <el-icon><component :is="item.icon" /></el-icon>
            <template #title>
              <span class="menu-title-text">{{ item.title }}</span>
              <el-badge
                v-if="item.routeName === 'ApprovalCenter' && pendingCount > 0"
                :value="pendingCount"
                :max="99"
                class="approval-badge"
              />
            </template>
          </el-menu-item>
        </el-sub-menu>
      </el-menu>

      <!-- Empty state for roles with no menu items -->
      <div v-else class="empty-menu">
        <el-icon class="empty-icon"><WarningFilled /></el-icon>
        <p v-if="!isCollapsed" class="empty-text">
          当前角色（{{ userStore.currentRoleLabel }}）暂无可访问的功能模块
        </p>
        <p v-if="!isCollapsed && userStore.currentRole === 'PARENT'" class="empty-hint">
          家长请使用微信小程序或<a href="/parent" class="empty-link">家长门户</a>
        </p>
      </div>
    </el-aside>

    <!-- Main area -->
    <el-container class="main-container">
      <!-- Header: school name highlight + user dropdown -->
      <el-header class="header" height="60px">
        <div class="header-left">
          <el-icon class="collapse-btn" @click="toggleSidebar">
            <Fold v-if="!isCollapsed" />
            <Expand v-else />
          </el-icon>
          <div class="school-highlight">
            <el-icon><School /></el-icon>
            <span class="school-name">{{ tenantStore.currentSchoolName }}</span>
            <el-tag
              size="small"
              :type="(phaseTagTypes[userStore.currentPhase] || 'info') as any"
              effect="dark"
              class="school-tag"
            >
              {{ phaseLabels[userStore.currentPhase] || '未知学段' }}
            </el-tag>
          </div>
        </div>

        <div class="header-right">
          <!-- 通知铃铛 — 未读 Badge + Popover 下拉 -->
          <NotificationBell @view-all="handleViewAllNotifications" />

          <el-dropdown trigger="click" @command="handleCommand">
            <div class="user-info">
              <el-avatar :size="32" class="user-avatar">
                {{ userStore.userInfo?.real_name?.charAt(0) || 'U' }}
              </el-avatar>

              <div class="user-detail">
                <span class="user-name">{{ userStore.userInfo?.real_name || '未登录' }}</span>
                <el-tag size="small" :type="roleTagType" class="role-tag">
                  {{ userStore.currentRoleLabel }}
                </el-tag>
              </div>
              <el-icon class="dropdown-arrow"><ArrowDown /></el-icon>
            </div>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="profile">
                  <el-icon><User /></el-icon> 个人信息
                </el-dropdown-item>
                <el-dropdown-item command="settings">
                  <el-icon><Setting /></el-icon> 系统设置
                </el-dropdown-item>
                <el-dropdown-item divided command="logout">
                  <el-icon><SwitchButton /></el-icon> 退出登录
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>

      <!-- Content area with transition animation -->
      <el-main class="content-area">
        <router-view v-slot="{ Component }">
          <transition name="fade-transform" mode="out-in">
            <keep-alive>
              <component :is="Component" />
            </keep-alive>
          </transition>
        </router-view>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessageBox, ElMessage } from 'element-plus'
import { useUserStore } from '@/store/user'
import { useTenantStore } from '@/store/tenant'
import { getPendingCount } from '@/api/approval'
import { getCurrentUser } from '@/api/auth'
import NotificationBell from '@/views/notifications/NotificationBell.vue'
import { getMenuItemsForRole, MENU_GROUPS } from '@/rbac/access-policy'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const tenantStore = useTenantStore()

const isCollapsed = ref(false)
const pendingCount = ref(0)

// 🔪 Fix #3: 启动会话验证状态
const isSessionLoading = ref(true)

const activeMenu = computed(() => route.path)

// ── 9角色标签颜色 ──
const roleTagType = computed(() => {
  switch (userStore.currentRole) {
    case 'MS_ADMIN':       return 'danger'
    case 'GROUP_ADMIN':    return 'primary'
    case 'BRANCH_ADMIN':   return 'primary'
    case 'GRADE_LEADER':   return 'warning'
    case 'CLASS_TEACHER':  return 'success'
    case 'TEACHER':        return 'success'
    case 'COUNSELOR':      return 'warning'
    case 'PARENT':         return 'info'
    case 'STUDENT':        return 'info'
    default:               return 'info'
  }
})

// ── 学段标签映射 ──
const phaseLabels: Record<string, string> = {
  primary: '小学',
  junior: '初中',
  senior: '高中',
  integrated: '完中',
}

const phaseTagTypes: Record<string, string> = {
  primary: 'success',
  junior: 'warning',
  senior: 'danger',
  integrated: 'primary',
}

// ─────────────────────────────────────────────────────────────
// 菜单生成 — RBAC-B: 从 access-policy.ts 统一生成
// 不再使用内联 allMenuGroups，角色+学段+插件三重过滤
// ─────────────────────────────────────────────────────────────
const visibleGroups = computed(() => {
  const role = userStore.currentRole
  if (!role) return []
  return getMenuItemsForRole(
    role,
    userStore.currentPhase,
    userStore.pluginConfig,
    role === 'MS_ADMIN',
  )
})

// ── routeName → path 映射（用于 el-menu-item 的 index）──
// 从路由配置自动生成，避免硬编码
const routePathMap = computed<Record<string, string>>(() => {
  const map: Record<string, string> = {}
  const routes = router.getRoutes()
  for (const r of routes) {
    if (r.name && typeof r.name === 'string') {
      map[r.name] = r.path
    }
  }
  return map
})

function toggleSidebar() {
  isCollapsed.value = !isCollapsed.value
}

async function fetchPendingCount() {
  try {
    const res: any = await getPendingCount()
    pendingCount.value = res?.count ?? 0
  } catch {
    // Silent fail — badge is non-critical
  }
}

function handleViewAllNotifications() {
  router.push('/notifications')
}

function handleCommand(command: string) {
  switch (command) {
    case 'profile':
      ElMessage.info('个人信息页面开发中...')
      break
    case 'settings':
      ElMessage.info('系统设置页面开发中...')
      break
    case 'logout':
      ElMessageBox.confirm('确定要退出登录吗？', '提示', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning',
      }).then(() => {
        userStore.clearAuth()
        router.push('/login')
      }).catch(() => {})
      break
  }
}

/**
 * 🔪 Fix #3: 启动会话验证 — 刷新页面时调用 /auth/me 刷新 userInfo
 */
async function validateSession() {
  if (!userStore.isLoggedIn) {
    isSessionLoading.value = false
    return
  }

  try {
    const freshUserInfo = await getCurrentUser()
    userStore.setUserInfo(freshUserInfo)
    if (freshUserInfo.school_id && freshUserInfo.school_name) {
      tenantStore.setSchool(
        freshUserInfo.school_id,
        freshUserInfo.school_name,
        freshUserInfo.school_phase,
      )
    }
  } catch {
    // 401拦截器已自动 clearAuth + 硬跳转login
  } finally {
    isSessionLoading.value = false
  }
}

onMounted(() => {
  validateSession()
  fetchPendingCount()
  setInterval(fetchPendingCount, 60000)
})
</script>

<style scoped>
.main-layout {
  height: 100vh;
  overflow: hidden;
}

.sidebar {
  background-color: #1f2c3f;
  transition: width 0.3s ease;
  overflow: hidden;
}

.logo-section {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  background: linear-gradient(135deg, #1e6091 0%, #184d74 100%);
}

.logo-icon {
  width: 28px;
  height: 28px;
}

.logo-icon-collapsed {
  width: 28px;
  height: 28px;
}

.logo-text {
  color: #fff;
  font-size: 18px;
  font-weight: 600;
  white-space: nowrap;
}

.sidebar-menu {
  border-right: none;
}

.sidebar-menu:not(.el-menu--collapse) {
  width: 240px;
}

/* ── 品牌化菜单项 ── */
.sidebar-menu :deep(.el-menu-item),
.sidebar-menu :deep(.el-sub-menu__title) {
  height: 44px;
  line-height: 44px;
  border-radius: 8px;
  margin: 4px 10px;
  color: #bfcbd9;
  transition: all 0.2s ease;
}

.sidebar-menu :deep(.el-sub-menu__title) {
  font-weight: 600;
}

/* hover */
.sidebar-menu :deep(.el-menu-item:hover),
.sidebar-menu :deep(.el-sub-menu__title:hover) {
  background: rgba(255, 255, 255, 0.1) !important;
  color: #fff !important;
}

/* 激活态 */
.sidebar-menu :deep(.el-menu-item) {
  position: relative;
}
.sidebar-menu :deep(.el-menu-item.is-active) {
  background: #1e6091 !important;
  color: #fff !important;
  font-weight: 600;
  box-shadow: 0 2px 8px rgba(30, 96, 145, 0.45);
}
.sidebar-menu :deep(.el-menu-item.is-active)::before {
  content: '';
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%);
  width: 4px;
  height: 22px;
  background: #fff;
  border-radius: 0 4px 4px 0;
}

.menu-title-text {
  display: inline-block;
}

.approval-badge {
  margin-left: 8px;
}

/* 空状态 */
.empty-menu {
  padding: 40px 16px;
  text-align: center;
  color: #909399;
}

.empty-icon {
  font-size: 40px;
  color: #5a5e66;
  margin-bottom: 12px;
}

.empty-text {
  font-size: 13px;
  line-height: 1.6;
  margin: 0 0 8px;
  color: #bfcbd9;
}

.empty-hint {
  font-size: 12px;
  line-height: 1.6;
  margin: 0;
  color: #7a8088;
}

.empty-link {
  color: #1e6091;
  text-decoration: none;
}

.empty-link:hover {
  text-decoration: underline;
}

.main-container {
  height: 100vh;
  overflow: hidden;
}

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fff;
  border-bottom: 1px solid #e4e7ed;
  box-shadow: 0 1px 4px rgba(0, 21, 41, 0.08);
  z-index: 10;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 20px;
}

.collapse-btn {
  font-size: 20px;
  cursor: pointer;
  color: #5a5e66;
  transition: color 0.2s;
}

.collapse-btn:hover {
  color: #1e6091;
}

.school-highlight {
  display: flex;
  align-items: center;
  gap: 8px;
}

.school-name {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}

.school-tag {
  margin-left: 4px;
}

.header-right {
  display: flex;
  align-items: center;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  padding: 0 12px;
  height: 60px;
  transition: background 0.2s;
  border-radius: 4px;
}

.user-info:hover {
  background: #f5f7fa;
}

.user-avatar {
  background-color: #1e6091;
  color: #fff;
  font-weight: 600;
}

.user-detail {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.user-name {
  font-size: 14px;
  font-weight: 500;
  color: #303133;
}

.role-tag {
  align-self: flex-start;
}

.dropdown-arrow {
  color: #909399;
  font-size: 12px;
}

.content-area {
  background: #f0f2f5;
  padding: 20px;
  overflow-y: auto;
  height: calc(100vh - 60px);
}

/* 启动会话验证骨架屏 */
.session-loading {
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f0f2f5;
  padding: 40px;
}
</style>
