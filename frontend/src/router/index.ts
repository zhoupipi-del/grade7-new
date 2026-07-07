import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { useUserStore } from '@/store/user'
import type { UserRole } from '@/types'

/**
 * RBAC Dynamic Route Guards
 *
 * Routes are organized by business domain, 1:1 aligned with backend modules.
 * Role-based access control: MS_ADMIN / GRADE_LEADER / CLASS_TEACHER / PARENT
 */

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    component: () => import('@/layouts/AuthLayout.vue'),
    children: [
      {
        path: '',
        name: 'Login',
        component: () => import('@/views/Login.vue'),
        meta: { title: '登录', public: true },
      },
    ],
  },
  {
    path: '/',
    component: () => import('@/layouts/MainLayout.vue'),
    redirect: '/dashboard',
    children: [
      // 多校区大数据指挥舱 (默认首页)
      {
        path: 'dashboard',
        name: 'DashboardOverview',
        component: () => import('@/views/dashboard/DashboardOverview.vue'),
        meta: {
          title: '指挥舱看板',
          icon: 'DataLine',
          roles: ['MS_ADMIN', 'GRADE_LEADER'] as UserRole[],
        },
      },
      // RDI 风险雷达
      {
        path: 'rdi-radar',
        name: 'RdiRadar',
        component: () => import('@/views/rdi-radar/Index.vue'),
        meta: {
          title: 'RDI 风险雷达',
          icon: 'Monitor',
          roles: ['MS_ADMIN', 'GRADE_LEADER', 'CLASS_TEACHER'] as UserRole[],
        },
      },
      // 审批工作台
      {
        path: 'approval-center',
        name: 'ApprovalCenter',
        component: () => import('@/views/approval-center/Index.vue'),
        meta: {
          title: '审批工作台',
          icon: 'Checked',
          roles: ['MS_ADMIN', 'GRADE_LEADER'] as UserRole[],
        },
      },
      // 德育与处分中心
      {
        path: 'behavior',
        name: 'BehaviorCenter',
        component: () => import('@/views/behavior/Index.vue'),
        meta: {
          title: '德育与处分中心',
          icon: 'Warning',
          roles: ['MS_ADMIN', 'GRADE_LEADER', 'CLASS_TEACHER'] as UserRole[],
        },
      },
      // 惩戒流转中心
      {
        path: 'discipline',
        name: 'DisciplineCenter',
        component: () => import('@/views/discipline/DisciplineCenter.vue'),
        meta: {
          title: '惩戒流转中心',
          icon: 'Stamp',
          roles: ['MS_ADMIN', 'GRADE_LEADER', 'CLASS_TEACHER'] as UserRole[],
        },
      },
      // AI 德育处方
      {
        path: 'ai-prescription',
        name: 'AiPrescription',
        component: () => import('@/views/ai-prescription/Index.vue'),
        meta: {
          title: 'AI 德育处方',
          icon: 'MagicStick',
          roles: ['MS_ADMIN', 'GRADE_LEADER', 'CLASS_TEACHER'] as UserRole[],
        },
      },
      // 审题助手 — 数学题翻译引擎
      {
        path: 'teach-math/coach',
        name: 'StudentCoach',
        component: () => import('@/views/teach-math/StudentCoach.vue'),
        meta: {
          title: '审题助手',
          icon: 'Reading',
          roles: ['MS_ADMIN', 'GRADE_LEADER', 'CLASS_TEACHER'] as UserRole[],
        },
      },
      // 审题诊断 — 教师端学情仪表盘
      {
        path: 'teach-math/report',
        name: 'TeacherReport',
        component: () => import('@/views/teach-math/TeacherReport.vue'),
        meta: {
          title: '审题诊断',
          icon: 'DataAnalysis',
          roles: ['MS_ADMIN', 'GRADE_LEADER', 'CLASS_TEACHER'] as UserRole[],
        },
      },
      // ── 新增模块路由 (Phase A 割接) ──
      // 素质评价仪表盘
      {
        path: 'evaluation',
        name: 'EvaluationDashboard',
        component: () => import('@/views/evaluation/Index.vue'),
        meta: {
          title: '素质评价',
          icon: 'TrendCharts',
          roles: ['MS_ADMIN', 'GRADE_LEADER', 'CLASS_TEACHER'] as UserRole[],
        },
      },
      // 正向加分录入
      {
        path: 'evaluation/positive-entry',
        name: 'PositiveScoreEntry',
        component: () => import('@/views/evaluation/PositiveScoreEntry.vue'),
        meta: {
          title: '正向加分',
          icon: 'Plus',
          roles: ['MS_ADMIN', 'GRADE_LEADER', 'CLASS_TEACHER'] as UserRole[],
        },
      },
      // 学生正向加分查看
      {
        path: 'evaluation/positive-view',
        name: 'PositiveScoreStudentView',
        component: () => import('@/views/evaluation/PositiveScoreStudentView.vue'),
        meta: {
          title: '我的正能量',
          icon: 'Trophy',
          roles: ['STUDENT', 'PARENT'] as UserRole[],
        },
      },
      // 正能量排行榜
      {
        path: 'evaluation/positive-ranking',
        name: 'PositiveRanking',
        component: () => import('@/views/evaluation/PositiveRanking.vue'),
        meta: {
          title: '正能量排行榜',
          icon: 'Histogram',
          roles: ['MS_ADMIN', 'GRADE_LEADER', 'CLASS_TEACHER', 'STUDENT', 'PARENT'] as UserRole[],
        },
      },
      // 报告导出工作台
      {
        path: 'reports',
        name: 'ReportCenter',
        component: () => import('@/views/reports/Index.vue'),
        meta: {
          title: '报告工作台',
          icon: 'Document',
          roles: ['MS_ADMIN', 'GRADE_LEADER', 'CLASS_TEACHER'] as UserRole[],
        },
      },
      // 通知中心
      {
        path: 'notifications',
        name: 'NotificationCenter',
        component: () => import('@/views/notifications/Index.vue'),
        meta: {
          title: '通知中心',
          icon: 'Bell',
          roles: ['MS_ADMIN', 'GRADE_LEADER', 'CLASS_TEACHER', 'PARENT'] as UserRole[],
        },
      },
      // 成长时间轴
      {
        path: 'growth',
        name: 'GrowthTimeline',
        component: () => import('@/views/growth/Index.vue'),
        meta: {
          title: '成长时间轴',
          icon: 'Timer',
          roles: ['MS_ADMIN', 'GRADE_LEADER', 'CLASS_TEACHER', 'PARENT'] as UserRole[],
        },
      },
      // ── 成绩管理模块路由 ──
      // 成绩看板（宏观成绩概览）
      {
        path: 'grades/dashboard',
        name: 'GradesDashboard',
        component: () => import('@/views/grades/GradeDashboard.vue'),
        meta: {
          title: '成绩看板',
          icon: 'DataLine',
          roles: ['MS_ADMIN', 'GRADE_LEADER', 'CLASS_TEACHER'] as UserRole[],
        },
      },
      // 双模态全息雷达（学业+行为五维映射）
      {
        path: 'grades/radar',
        name: 'GradesRadar',
        component: () => import('@/views/grades/StudentRadarChart.vue'),
        meta: {
          title: '成绩雷达',
          icon: 'Aim',
          roles: ['MS_ADMIN', 'GRADE_LEADER', 'CLASS_TEACHER'] as UserRole[],
        },
      },
      // 全息档案容器（雷达+时间轴+AI处方）
      {
        path: 'grades/profile',
        name: 'GradesProfile',
        component: () => import('@/views/grades/HolisticProfileCard.vue'),
        meta: {
          title: '全息档案',
          icon: 'UserFilled',
          roles: ['MS_ADMIN', 'GRADE_LEADER', 'CLASS_TEACHER'] as UserRole[],
        },
      },
      // ── 家长门户路由 ──
      // 家长仪表盘（家长首页）
      {
        path: 'parent',
        name: 'ParentPortal',
        component: () => import('@/views/parent/ParentPortal.vue'),
        meta: {
          title: '家长门户',
          icon: 'HomeFilled',
          roles: ['PARENT'] as UserRole[],
        },
      },
      // 家校反馈
      {
        path: 'parent/feedback',
        name: 'ParentFeedback',
        component: () => import('@/views/parent/ParentFeedback.vue'),
        meta: {
          title: '家校反馈',
          icon: 'ChatLineSquare',
          roles: ['PARENT'] as UserRole[],
        },
      },
      // 在线申诉
      {
        path: 'parent/appeal',
        name: 'ParentAppeal',
        component: () => import('@/views/parent/ParentAppeal.vue'),
        meta: {
          title: '在线申诉',
          icon: 'WarningFilled',
          roles: ['PARENT'] as UserRole[],
        },
      },
    ],
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    component: () => import('@/views/NotFound.vue'),
    meta: { title: '404', public: true },
  },
]

const router = createRouter({
  history: createWebHistory('/app/'),
  routes,
})

/**
 * Global Navigation Guard — RBAC + Auth Check
 */
router.beforeEach((to, _from, next) => {
  const userStore = useUserStore()
  const isPublic = to.meta.public === true

  // Set page title
  const title = (to.meta.title as string) || 'Wings 3.0'
  document.title = `${title} - Wings 3.0`

  // Public route (login, 404)
  if (isPublic) {
    // Already logged in and going to /login → redirect to home
    if (to.name === 'Login' && userStore.isLoggedIn) {
      next({ path: '/' })
      return
    }
    next()
    return
  }

  // Not logged in → redirect to login
  if (!userStore.isLoggedIn) {
    next({ path: '/login', query: { redirect: to.fullPath } })
    return
  }

  // PARENT 角色默认跳转到家长门户（而非 /dashboard）
  if (to.path === '/' || to.path === '/dashboard') {
    if (userStore.currentRole === 'PARENT') {
      next({ path: '/parent' })
      return
    }
  }

  // Role-based access control
  const requiredRoles = to.meta.roles as UserRole[] | undefined
  if (requiredRoles && requiredRoles.length > 0) {
    const userRole = userStore.currentRole
    if (!userRole || !requiredRoles.includes(userRole)) {
      // 角色不匹配时，PARENT → /parent，其他 → /
      next({ path: userStore.currentRole === 'PARENT' ? '/parent' : '/' })
      return
    }
  }

  next()
})

export default router
