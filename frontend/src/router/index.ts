import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { useUserStore } from '@/store/user'
import { canAccessRoute, getDefaultRouteName, ROUTE_ACCESS } from '@/rbac/access-policy'
import type { UserRole } from '@/types'

/**
 * WINGS 3.0 Router — RBAC-B: Centralized Access Policy
 *
 * Routes no longer carry inline `meta.roles` arrays.
 * Role-based access is controlled by ROUTE_ACCESS in rbac/access-policy.ts.
 * Only meta.public and meta.hidden are used locally.
 *
 * Guard logic:
 *   1. Public route → allow
 *   2. Not logged in → login page
 *   3. Role invalid (isRoleValid=false) → 403
 *   4. Hidden sub-route → allow (inherits parent access)
 *   5. Route name not in ROUTE_ACCESS → DENY (fail closed)
 *   6. Role not in ROUTE_ACCESS[routeName] → 403
 *   7. Phase filter (MS_ADMIN bypasses)
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
    path: '/403',
    name: 'Forbidden',
    component: () => import('@/views/Forbidden.vue'),
    meta: { title: '无权访问', public: true },
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
        meta: { title: '指挥舱看板', icon: 'DataLine' },
      },
      // RDI 风险雷达
      {
        path: 'rdi-radar',
        name: 'RdiRadar',
        component: () => import('@/views/rdi-radar/Index.vue'),
        meta: { title: 'RDI 风险雷达', icon: 'Monitor' },
      },
      // RDI 四维风险看板
      {
        path: 'rdi-dashboard',
        name: 'RdiDashboard',
        component: () => import('@/views/rdi-radar/RdiDashboard.vue'),
        meta: { title: 'RDI 风险看板', icon: 'Odometer' },
      },
      // 审批工作台
      {
        path: 'approval-center',
        name: 'ApprovalCenter',
        component: () => import('@/views/approval-center/Index.vue'),
        meta: { title: '审批工作台', icon: 'Checked' },
      },
      // 德育与处分中心
      {
        path: 'behavior',
        name: 'BehaviorCenter',
        component: () => import('@/views/behavior/Index.vue'),
        meta: { title: '德育与处分中心', icon: 'Warning' },
      },
      // 惩戒流转中心
      {
        path: 'discipline',
        name: 'DisciplineCenter',
        component: () => import('@/views/discipline/DisciplineCenter.vue'),
        meta: { title: '惩戒流转中心', icon: 'Stamp' },
      },
      // AI 德育处方
      {
        path: 'ai-prescription',
        name: 'AiPrescription',
        component: () => import('@/views/ai-prescription/Index.vue'),
        meta: { title: 'AI 德育处方', icon: 'MagicStick', phases: ['junior', 'senior', 'integrated'] },
      },
      // 审题助手
      {
        path: 'teach-math/coach',
        name: 'StudentCoach',
        component: () => import('@/views/teach-math/StudentCoach.vue'),
        meta: { title: '审题助手', icon: 'Reading' },
      },
      // 审题诊断
      {
        path: 'teach-math/report',
        name: 'TeacherReport',
        component: () => import('@/views/teach-math/TeacherReport.vue'),
        meta: { title: '审题诊断', icon: 'DataAnalysis' },
      },
      // 教研协同
      {
        path: 'research',
        name: 'ResearchConsole',
        component: () => import('@/views/research/Index.vue'),
        meta: { title: '教研协同', icon: 'Coordinate' },
      },
      // 作业管理
      {
        path: 'homework',
        name: 'HomeworkConsole',
        component: () => import('@/views/homework/Index.vue'),
        meta: { title: '作业管理', icon: 'EditPen' },
      },
      // 错题断层
      {
        path: 'error-funnel',
        name: 'ErrorFunnel',
        component: () => import('@/views/error-funnel/Index.vue'),
        meta: { title: '错题断层', icon: 'Filter' },
      },
      // ── 新增模块路由 (Phase A) ──
      // 素质评价仪表盘
      {
        path: 'evaluation',
        name: 'EvaluationDashboard',
        component: () => import('@/views/evaluation/Index.vue'),
        meta: { title: '素质评价', icon: 'TrendCharts' },
      },
      // 正向加分录入
      {
        path: 'evaluation/positive-entry',
        name: 'PositiveScoreEntry',
        component: () => import('@/views/evaluation/PositiveScoreEntry.vue'),
        meta: { title: '正向加分', icon: 'Plus' },
      },
      // 学生正向加分查看
      {
        path: 'evaluation/positive-view',
        name: 'PositiveScoreStudentView',
        component: () => import('@/views/evaluation/PositiveScoreStudentView.vue'),
        meta: { title: '我的正能量', icon: 'Trophy' },
      },
      // 正能量排行榜
      {
        path: 'evaluation/positive-ranking',
        name: 'PositiveRanking',
        component: () => import('@/views/evaluation/PositiveRanking.vue'),
        meta: { title: '正能量排行榜', icon: 'Histogram' },
      },
      // 报告导出工作台
      {
        path: 'reports',
        name: 'ReportCenter',
        component: () => import('@/views/reports/Index.vue'),
        meta: { title: '报告工作台', icon: 'Document' },
      },
      // 通知中心
      {
        path: 'notifications',
        name: 'NotificationCenter',
        component: () => import('@/views/notifications/Index.vue'),
        meta: { title: '通知中心', icon: 'Bell' },
      },
      // 成长档案
      {
        path: 'growth',
        name: 'GrowthTimeline',
        component: () => import('@/views/growth/Index.vue'),
        meta: { title: '成长档案', icon: 'TrendCharts' },
      },
      // ── 成绩管理模块 ──
      {
        path: 'grades/dashboard',
        name: 'GradesDashboard',
        component: () => import('@/views/grades/GradeDashboard.vue'),
        meta: { title: '成绩看板', icon: 'DataLine' },
      },
      {
        path: 'grades/radar',
        name: 'GradesRadar',
        component: () => import('@/views/grades/StudentRadarChart.vue'),
        meta: { title: '成绩雷达', icon: 'Aim' },
      },
      {
        path: 'grades/profile',
        name: 'GradesProfile',
        component: () => import('@/views/grades/HolisticProfileCard.vue'),
        meta: { title: '全息档案', icon: 'UserFilled' },
      },
      {
        path: 'grades/prescriptions',
        name: 'PrescriptionCenter',
        component: () => import('@/views/grades/PrescriptionCenter.vue'),
        meta: { title: 'AI 处方中心', icon: 'MagicStick', phases: ['junior', 'senior', 'integrated'] },
      },
      // ── 考勤管理 ──
      {
        path: 'attendance',
        name: 'AttendanceCenter',
        component: () => import('@/views/attendance/Index.vue'),
        meta: { title: '考勤管理', icon: 'Calendar' },
      },
      {
        path: 'attendance/class-history',
        name: 'ClassHistoryDashboard',
        component: () => import('@/views/attendance/ClassHistoryDashboard.vue'),
        meta: { title: '考勤历史大盘', icon: 'TrendCharts' },
      },
      // ── 流动红旗 ──
      {
        path: 'red-flag',
        name: 'RedFlagCenter',
        component: () => import('@/views/red-flag/Index.vue'),
        meta: { title: '流动红旗', icon: 'Flag' },
      },
      // ── 萌卡系统 ──
      {
        path: 'card-system',
        name: 'CardSystem',
        component: () => import('@/views/card-system/Index.vue'),
        meta: { title: '萌卡系统', icon: 'Box', phases: ['primary', 'integrated'] },
      },
      // ── 高考学情大盘 ──
      {
        path: 'gaokao-dashboard',
        name: 'GaokaoDashboard',
        component: () => import('@/views/gaokao-dashboard/Index.vue'),
        meta: { title: '高考学情大盘', icon: 'TrophyBase', phases: ['senior', 'integrated'] },
      },
      // ── 数据并网 ──
      {
        path: 'data-adapter',
        name: 'DataAdapter',
        component: () => import('@/views/data-adapter/Index.vue'),
        meta: { title: '数据并网', icon: 'Connection', phases: ['junior', 'senior', 'integrated'] },
      },
      // ── 心理筛查与干预 ──
      {
        path: 'psych-screening',
        name: 'PsychScreening',
        component: () => import('@/views/psych-screening/Index.vue'),
        meta: { title: '心理筛查', icon: 'Sunny' },
      },
      {
        path: 'psych-screening/fill',
        name: 'PsychSurveyFill',
        component: () => import('@/views/psych-screening/SurveyFill.vue'),
        meta: { title: '量表填写', icon: 'EditPen' },
      },
      {
        path: 'psych-screening/result',
        name: 'PsychResultView',
        component: () => import('@/views/psych-screening/ResultView.vue'),
        meta: { title: '筛查结果', icon: 'DataAnalysis' },
      },
      {
        path: 'psych-screening/intervention',
        name: 'PsychIntervention',
        component: () => import('@/views/psych-screening/Intervention.vue'),
        meta: { title: '干预管理', icon: 'FirstAidKit' },
      },
      {
        path: 'psych-screening/portrait',
        name: 'PsychPortrait',
        component: () => import('@/views/psych-screening/PortraitView.vue'),
        meta: { title: '心理画像与交叉分析', icon: 'PieChart' },
      },
      // ── 心理咨询工作台 ──
      {
        path: 'counselor-console',
        name: 'CounselorConsole',
        component: () => import('@/views/counselor-console/Index.vue'),
        meta: { title: '心理咨询工作台', icon: 'ChatDotRound' },
      },
      // ── NexusBoard 双轨预警 ──
      {
        path: 'nexus-board',
        name: 'NexusBoard',
        component: () => import('@/views/nexus-board/Index.vue'),
        meta: { title: '双轨预警决策看板', icon: 'DataLine' },
      },
      // ── 学籍管理 ──
      {
        path: 'student-registry',
        name: 'StudentRegistry',
        component: () => import('@/views/student-registry/Index.vue'),
        meta: { title: '学籍管理', icon: 'User' },
      },
      {
        path: 'student-registry/detail',
        name: 'StudentDetail',
        component: () => import('@/views/student-registry/Detail.vue'),
        meta: { title: '学籍详情', hidden: true },
      },
      // ── 班级管理 ──
      {
        path: 'class-mgmt',
        name: 'ClassManagement',
        component: () => import('@/views/class-mgmt/Index.vue'),
        meta: { title: '班级管理', icon: 'Grid' },
      },
      // ── 教师管理 ──
      {
        path: 'teacher-mgmt',
        name: 'TeacherManagement',
        component: () => import('@/views/teacher-mgmt/Index.vue'),
        meta: { title: '教师管理', icon: 'Avatar' },
      },
      {
        path: 'teacher-mgmt/detail/:id',
        name: 'TeacherDetail',
        component: () => import('@/views/teacher-mgmt/Detail.vue'),
        meta: { title: '教师详情', hidden: true },
      },
      {
        path: 'teacher-mgmt/workload/:id',
        name: 'TeacherWorkload',
        component: () => import('@/views/teacher-mgmt/Workload.vue'),
        meta: { title: '工作量统计', hidden: true },
      },
      // ── 课程表管理 ──
      {
        path: 'timetable',
        name: 'Timetable',
        component: () => import('@/views/timetable/Index.vue'),
        meta: { title: '课程表管理', icon: 'Calendar' },
      },
      {
        path: 'timetable/week/:classId',
        name: 'TimetableWeekView',
        component: () => import('@/views/timetable/WeekView.vue'),
        meta: { title: '班级周课表', hidden: true },
      },
      {
        path: 'timetable/week/teacher/:teacherId',
        name: 'TeacherWeekView',
        component: () => import('@/views/timetable/WeekView.vue'),
        meta: { title: '教师周课表', hidden: true },
      },
      {
        path: 'timetable/conflicts',
        name: 'TimetableConflicts',
        component: () => import('@/views/timetable/Conflicts.vue'),
        meta: { title: '排课冲突', hidden: true },
      },
      // ── 小学萌卡激励 ──
      {
        path: 'habit-cards',
        name: 'HabitCards',
        component: () => import('@/views/habit-cards/Index.vue'),
        meta: { title: '萌卡荣誉生态', icon: 'Medal', phases: ['primary', 'integrated'] },
      },
      // ── 家长门户 ──
      {
        path: 'parent',
        name: 'ParentPortal',
        component: () => import('@/views/parent/ParentPortal.vue'),
        meta: { title: '家长门户', icon: 'HomeFilled' },
      },
      {
        path: 'parent/feedback',
        name: 'ParentFeedback',
        component: () => import('@/views/parent/ParentFeedback.vue'),
        meta: { title: '家校反馈', icon: 'ChatLineSquare' },
      },
      {
        path: 'parent/appeal',
        name: 'ParentAppeal',
        component: () => import('@/views/parent/ParentAppeal.vue'),
        meta: { title: '在线申诉', icon: 'WarningFilled' },
      },
      {
        path: 'parent/blindbox',
        name: 'ParentBlindbox',
        component: () => import('@/views/parent/ParentBlindbox.vue'),
        meta: { title: '金色盲盒', icon: 'Present', phases: ['primary', 'integrated'] },
      },
      {
        path: 'parent/appointment',
        name: 'AppointmentPicker',
        component: () => import('@/views/parent/AppointmentPicker.vue'),
        meta: { title: '心理咨询预约', icon: 'Clock' },
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
 * Global Navigation Guard — RBAC-B: Centralized Access Policy
 *
 * Fail-closed design:
 * - Public routes: no auth needed
 * - Not logged in: redirect to login
 * - Invalid role (isRoleValid=false): redirect to /403
 * - Hidden sub-routes: allow (parent route already validated access)
 * - Route name not in ROUTE_ACCESS: DENY → /403
 * - Role not in ROUTE_ACCESS[routeName]: /403
 * - Phase mismatch: redirect to role's default route
 */
router.beforeEach((to, _from, next) => {
  const userStore = useUserStore()
  const isPublic = to.meta.public === true

  // Set page title
  const title = (to.meta.title as string) || 'Wings 3.0'
  document.title = `${title} - Wings 3.0`

  // 1. Public route (login, 404, 403)
  if (isPublic) {
    if (to.name === 'Login' && userStore.isLoggedIn) {
      // Already logged in going to /login → redirect to role's default home
      const defaultRoute = getDefaultRouteName(userStore.currentRole)
      next({ name: defaultRoute })
      return
    }
    next()
    return
  }

  // 2. Not logged in → login page
  if (!userStore.isLoggedIn) {
    next({ path: '/login', query: { redirect: to.fullPath } })
    return
  }

  // 3. Invalid role → 403 (fail closed, no auto-downgrade)
  if (!userStore.isRoleValid) {
    next({ name: 'Forbidden' })
    return
  }

  const role = userStore.currentRole
  const routeName = to.name as string

  // 4. Default redirect: '/' or '/dashboard' → role-specific home
  if (to.path === '/' || to.path === '/dashboard') {
    const defaultRoute = getDefaultRouteName(role)
    if (routeName !== defaultRoute && to.path === '/') {
      next({ name: defaultRoute })
      return
    }
    // /dashboard access: check if role can access DashboardOverview
    if (to.path === '/dashboard' && role && !canAccessRoute(role, 'DashboardOverview')) {
      next({ name: defaultRoute })
      return
    }
  }

  // 5. Route name not in ROUTE_ACCESS → DENY (fail closed, includes hidden sub-routes)
  if (!routeName || !(routeName in ROUTE_ACCESS)) {
    next({ name: 'Forbidden' })
    return
  }

  // 6. Role not in ROUTE_ACCESS[routeName] → 403
  if (role && !canAccessRoute(role, routeName)) {
    next({ name: 'Forbidden' })
    return
  }

  // 7. Phase filter (MS_ADMIN bypasses)
  const requiredPhases = to.meta.phases as string[] | undefined
  if (requiredPhases && requiredPhases.length > 0 && role !== 'MS_ADMIN') {
    const currentPhase = userStore.currentPhase
    if (currentPhase && !requiredPhases.includes(currentPhase)) {
      const defaultRoute = getDefaultRouteName(role)
      next({ name: defaultRoute })
      return
    }
  }

  next()
})

export default router
