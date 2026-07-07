<template>
  <!-- 🔪 Fix #3: 启动会话验证 — 防止过期token闪烁旧侧边栏 -->
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
        active-text-color="#409eff"
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
            :key="item.index"
            :index="item.index"
          >
            <el-icon><component :is="item.icon" /></el-icon>
            <template #title>
              <span class="menu-title-text">{{ item.title }}</span>
              <el-badge
                v-if="item.index === '/approval-center' && pendingCount > 0"
                :value="pendingCount"
                :max="99"
                class="approval-badge"
              />
            </template>
          </el-menu-item>
        </el-sub-menu>
      </el-menu>

      <!-- Empty state for PARENT (no accessible menu items) -->
      <div v-else class="empty-menu">
        <el-icon class="empty-icon"><WarningFilled /></el-icon>
        <p v-if="!isCollapsed" class="empty-text">
          当前角色（{{ userStore.currentRoleLabel }}）暂无可访问的功能模块
        </p>
        <p v-if="!isCollapsed" class="empty-hint">
          家长请使用微信小程序或<a href="/" class="empty-link">家长门户</a>
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
            <el-tag size="small" type="info" effect="dark" class="school-tag">
              多租户
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
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessageBox, ElMessage } from 'element-plus'
import { useUserStore } from '@/store/user'
import { useTenantStore } from '@/store/tenant'
import { getPendingCount } from '@/api/approval'
import { getCurrentUser } from '@/api/auth'
import NotificationBell from '@/views/notifications/NotificationBell.vue'
import type { UserRole } from '@/types'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const tenantStore = useTenantStore()

const isCollapsed = ref(false)
const pendingCount = ref(0)

// 🔪 Fix #3: 启动会话验证状态 — 防止过期token闪烁旧侧边栏
const isSessionLoading = ref(true)

const activeMenu = computed(() => route.path)

const roleTagType = computed(() => {
  switch (userStore.currentRole) {
    case 'MS_ADMIN':
      return 'danger'
    case 'GRADE_LEADER':
      return 'warning'
    case 'CLASS_TEACHER':
      return 'success'
    case 'PARENT':
      return 'info'
    default:
      return 'info'
  }
})

interface MenuItem {
  index: string
  title: string
  icon: string
  roles: UserRole[]
}

interface MenuGroup {
  title: string
  icon: string
  items: MenuItem[]
}

// 菜单分组定义 — 与 router/index.ts 的 meta.roles 保持 1:1 对齐
// 分组解决"审题助手割裂感"：德育管理 vs 教学辅助物理隔离
const allMenuGroups: MenuGroup[] = [
  {
    title: '德育管理中心',
    icon: 'Shield',
    items: [
      {
        index: '/dashboard',
        title: '指挥舱看板',
        icon: 'DataLine',
        roles: ['MS_ADMIN', 'GRADE_LEADER'],
      },
      {
        index: '/rdi-radar',
        title: 'RDI 风险雷达',
        icon: 'Monitor',
        roles: ['MS_ADMIN', 'GRADE_LEADER', 'CLASS_TEACHER'],
      },
      {
        index: '/approval-center',
        title: '审批工作台',
        icon: 'Checked',
        roles: ['MS_ADMIN', 'GRADE_LEADER'],
      },
      {
        index: '/behavior',
        title: '德育与处分中心',
        icon: 'Warning',
        roles: ['MS_ADMIN', 'GRADE_LEADER', 'CLASS_TEACHER'],
      },
      {
        index: '/discipline',
        title: '惩戒流转中心',
        icon: 'Stamp',
        roles: ['MS_ADMIN', 'GRADE_LEADER', 'CLASS_TEACHER'],
      },
      {
        index: '/ai-prescription',
        title: 'AI 德育处方',
        icon: 'MagicStick',
        roles: ['MS_ADMIN', 'GRADE_LEADER', 'CLASS_TEACHER'],
      },
      {
        index: '/evaluation',
        title: '素质评价',
        icon: 'TrendCharts',
        roles: ['MS_ADMIN', 'GRADE_LEADER', 'CLASS_TEACHER'],
      },
      {
        index: '/evaluation/positive-entry',
        title: '正向加分',
        icon: 'Plus',
        roles: ['MS_ADMIN', 'GRADE_LEADER', 'CLASS_TEACHER'],
      },
      {
        index: '/evaluation/positive-ranking',
        title: '正能量排行榜',
        icon: 'Histogram',
        roles: ['MS_ADMIN', 'GRADE_LEADER', 'CLASS_TEACHER', 'STUDENT', 'PARENT'],
      },
      {
        index: '/evaluation/positive-view',
        title: '我的正能量',
        icon: 'Trophy',
        roles: ['STUDENT', 'PARENT'],
      },
      {
        index: '/reports',
        title: '报告工作台',
        icon: 'Document',
        roles: ['MS_ADMIN', 'GRADE_LEADER', 'CLASS_TEACHER'],
      },
      {
        index: '/notifications',
        title: '通知中心',
        icon: 'Bell',
        roles: ['MS_ADMIN', 'GRADE_LEADER', 'CLASS_TEACHER', 'PARENT'],
      },
      {
        index: '/growth',
        title: '成长时间轴',
        icon: 'Timer',
        roles: ['MS_ADMIN', 'GRADE_LEADER', 'CLASS_TEACHER', 'PARENT'],
      },
      {
        index: '/grades/dashboard',
        title: '成绩看板',
        icon: 'DataLine',
        roles: ['MS_ADMIN', 'GRADE_LEADER', 'CLASS_TEACHER'],
      },
      {
        index: '/grades/radar',
        title: '成绩雷达',
        icon: 'Aim',
        roles: ['MS_ADMIN', 'GRADE_LEADER', 'CLASS_TEACHER'],
      },
      {
        index: '/grades/profile',
        title: '全息档案',
        icon: 'UserFilled',
        roles: ['MS_ADMIN', 'GRADE_LEADER', 'CLASS_TEACHER'],
      },
    ],
  },
  {
    title: '教学辅助工具',
    icon: 'Tools',
    items: [
      {
        index: '/teach-math/coach',
        title: '审题助手',
        icon: 'Reading',
        roles: ['MS_ADMIN', 'GRADE_LEADER', 'CLASS_TEACHER'],
      },
      {
        index: '/teach-math/report',
        title: '审题诊断',
        icon: 'DataAnalysis',
        roles: ['MS_ADMIN', 'GRADE_LEADER', 'CLASS_TEACHER'],
      },
    ],
  },
  {
    title: '家长门户',
    icon: 'HomeFilled',
    items: [
      {
        index: '/parent',
        title: '家长首页',
        icon: 'HomeFilled',
        roles: ['PARENT'],
      },
      {
        index: '/parent/feedback',
        title: '家校反馈',
        icon: 'ChatLineSquare',
        roles: ['PARENT'],
      },
      {
        index: '/parent/appeal',
        title: '在线申诉',
        icon: 'WarningFilled',
        roles: ['PARENT'],
      },
      {
        index: '/notifications',
        title: '通知中心',
        icon: 'Bell',
        roles: ['PARENT'],
      },
      {
        index: '/growth',
        title: '成长时间轴',
        icon: 'Timer',
        roles: ['PARENT'],
      },
      {
        index: '/evaluation/positive-view',
        title: '我的正能量',
        icon: 'Trophy',
        roles: ['PARENT'],
      },
      {
        index: '/evaluation/positive-ranking',
        title: '正能量排行榜',
        icon: 'Histogram',
        roles: ['PARENT'],
      },
    ],
  },
]

// 按当前用户角色过滤菜单组与菜单项
// PARENT 角色会被过滤掉所有项 → 触发空状态提示
const visibleGroups = computed<MenuGroup[]>(() => {
  const role = userStore.currentRole
  if (!role) return []
  return allMenuGroups
    .map((g) => ({
      ...g,
      items: g.items.filter((item) => item.roles.includes(role)),
    }))
    .filter((g) => g.items.length > 0)
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
 *
 * 解决 localStorage 有过期token → 侧边栏短暂闪烁旧数据 → 401踢出 的UX问题
 * 流程: 骨架屏 → /auth/me → 成功(刷新userInfo+渲染) / 失败(401拦截器自动跳login)
 */
async function validateSession() {
  if (!userStore.isLoggedIn) {
    // 无token → 路由守卫已拦截到/login，不会渲染MainLayout
    isSessionLoading.value = false
    return
  }

  try {
    const freshUserInfo = await getCurrentUser()
    // setUserInfo 归一化: display_name→real_name, role→大写UserRole
    userStore.setUserInfo(freshUserInfo)
    // 同步租户信息
    if (freshUserInfo.school_id && freshUserInfo.school_name) {
      tenantStore.setSchool(freshUserInfo.school_id, freshUserInfo.school_name)
    }
  } catch {
    // 401拦截器已自动 clearAuth + 硬跳转login；此处不重复处理
  } finally {
    isSessionLoading.value = false
  }
}

onMounted(() => {
  validateSession()
  // Poll pending approval count every 60s
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
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
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

.menu-title-text {
  display: inline-block;
}

.approval-badge {
  margin-left: 8px;
}

/* 空状态 — PARENT 角色无可用菜单 */
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
  color: #409eff;
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
  color: #409eff;
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
  background-color: #409eff;
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

/* 🔪 Fix #3: 启动会话验证骨架屏 — 防止旧数据闪烁 */
.session-loading {
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f0f2f5;
  padding: 40px;
}
</style>
