/**
 * WINGS 3.0 Frontend Role Access Policy (RBAC-B)
 *
 * Single source of truth for: role → routes + menus + default home
 * DO NOT duplicate role lists in router/index.ts or MainLayout.vue —
 * import from this file instead.
 *
 * Access rules:
 *   meta.public = true      → no auth needed (login, 404, 403)
 *   meta.hidden = true      → sub-route still checked via ROUTE_ACCESS (must have entry)
 *   ROUTE_ACCESS entry      → only listed roles can access
 *   no entry + not public/hidden → DENY (fail closed, prevents accidental omission)
 *
 * Constrained by: real routes that exist in the codebase.
 * No placeholder routes for unimplemented pages.
 */

import type { UserRole } from '@/types'

// ─────────────────────────────────────────────────────────────
// Role default routes — must point to REAL existing route names
// ─────────────────────────────────────────────────────────────
export const ROLE_DEFAULT_ROUTES: Record<UserRole, string> = {
  MS_ADMIN:       'DashboardOverview',
  GROUP_ADMIN:    'DashboardOverview',     // 指挥舱看板 (scope-filtered by cache key)
  BRANCH_ADMIN:   'DashboardOverview',     // 指挥舱看板 (scope-filtered)
  GRADE_LEADER:   'DashboardOverview',
  CLASS_TEACHER:  'DashboardOverview',
  TEACHER:        'Timetable',             // 课程表 — teacher's daily starting point
  COUNSELOR:      'PsychScreening',        // 心理筛查 — counselor's primary workspace
  PARENT:         'ParentPortal',
  STUDENT:        'PositiveScoreStudentView',
}

// ─────────────────────────────────────────────────────────────
// Route-level access matrix
// Maps each route name → roles that can access it
// This replaces scattered meta.roles arrays in router/index.ts
//
// GROUP_ADMIN scope: 集团总览、组织架构、片区与学校管理、跨校统计、集团报表
//   禁止: 心理咨询正文(CounselorConsole)、处分审批(DisciplineCenter)、学生事件直接修改(BehaviorCenter)
// BRANCH_ADMIN scope: 所属片区总览、片区学校、片区统计、风险汇总
//   禁止: 集团配置、其他片区、心理咨询正文、处分审批
// TEACHER scope: 任教班级、课程表、作业、成绩、课堂评价、本人记录与教研
//   禁止: 班主任专属页、全校风险、心理模块、系统配置
// COUNSELOR scope: 心理筛查、风险核查、咨询预约、本人个案、转介跟进
//   禁止: 成绩作业、德育处分、系统配置、无关个案正文
// ─────────────────────────────────────────────────────────────
export const ROUTE_ACCESS: Record<string, UserRole[]> = {
  // ── 公共底座 ──
  DashboardOverview:       ['MS_ADMIN', 'GROUP_ADMIN', 'BRANCH_ADMIN', 'GRADE_LEADER', 'CLASS_TEACHER'],
  NotificationCenter:      ['MS_ADMIN', 'GROUP_ADMIN', 'BRANCH_ADMIN', 'GRADE_LEADER', 'CLASS_TEACHER', 'TEACHER', 'COUNSELOR', 'PARENT'],
  GrowthTimeline:          ['MS_ADMIN', 'GRADE_LEADER', 'CLASS_TEACHER', 'PARENT'],
  GradesProfile:           ['MS_ADMIN', 'GRADE_LEADER', 'CLASS_TEACHER'],
  StudentRegistry:         ['MS_ADMIN', 'GROUP_ADMIN', 'BRANCH_ADMIN', 'GRADE_LEADER', 'CLASS_TEACHER'],
  ClassManagement:         ['MS_ADMIN', 'GROUP_ADMIN', 'BRANCH_ADMIN', 'GRADE_LEADER'],
  TeacherManagement:       ['MS_ADMIN', 'GROUP_ADMIN', 'BRANCH_ADMIN', 'GRADE_LEADER'],

  // ── 德育管理中心 ──
  RdiRadar:                ['MS_ADMIN', 'GROUP_ADMIN', 'BRANCH_ADMIN', 'GRADE_LEADER', 'CLASS_TEACHER'],
  RdiDashboard:            ['MS_ADMIN', 'GROUP_ADMIN', 'BRANCH_ADMIN', 'GRADE_LEADER', 'CLASS_TEACHER'],
  ApprovalCenter:          ['MS_ADMIN', 'GROUP_ADMIN', 'BRANCH_ADMIN', 'GRADE_LEADER'],
  BehaviorCenter:          ['MS_ADMIN', 'GRADE_LEADER', 'CLASS_TEACHER'],          // GROUP/BRANCH_ADMIN禁止: 学生事件直接修改
  DisciplineCenter:        ['MS_ADMIN', 'GRADE_LEADER'],                            // GROUP/BRANCH_ADMIN禁止: 处分审批
  AiPrescription:          ['MS_ADMIN', 'GRADE_LEADER', 'CLASS_TEACHER'],
  EvaluationDashboard:     ['MS_ADMIN', 'GRADE_LEADER', 'CLASS_TEACHER'],
  PositiveScoreEntry:      ['MS_ADMIN', 'GRADE_LEADER', 'CLASS_TEACHER'],
  PositiveScoreStudentView: ['STUDENT', 'PARENT'],
  PositiveRanking:         ['MS_ADMIN', 'GRADE_LEADER', 'CLASS_TEACHER', 'STUDENT', 'PARENT'],
  ReportCenter:            ['MS_ADMIN', 'GROUP_ADMIN', 'BRANCH_ADMIN', 'GRADE_LEADER', 'CLASS_TEACHER'],
  AttendanceCenter:        ['MS_ADMIN', 'GRADE_LEADER', 'CLASS_TEACHER'],
  ClassHistoryDashboard:   ['MS_ADMIN', 'GRADE_LEADER', 'CLASS_TEACHER'],
  RedFlagCenter:           ['MS_ADMIN', 'GRADE_LEADER', 'CLASS_TEACHER'],
  CardSystem:              ['MS_ADMIN', 'GRADE_LEADER', 'CLASS_TEACHER'],

  // ── 教导管理中心 ──
  GradesDashboard:         ['MS_ADMIN', 'GROUP_ADMIN', 'BRANCH_ADMIN', 'GRADE_LEADER', 'CLASS_TEACHER'],
  GradesRadar:             ['MS_ADMIN', 'GRADE_LEADER', 'CLASS_TEACHER'],
  PrescriptionCenter:      ['MS_ADMIN', 'GRADE_LEADER', 'CLASS_TEACHER'],
  GaokaoDashboard:         ['MS_ADMIN', 'GROUP_ADMIN', 'GRADE_LEADER'],
  DataAdapter:             ['MS_ADMIN', 'GRADE_LEADER'],
  Timetable:               ['MS_ADMIN', 'GRADE_LEADER', 'CLASS_TEACHER', 'TEACHER'],
  HabitCards:              ['MS_ADMIN', 'GRADE_LEADER', 'CLASS_TEACHER'],
  HomeworkConsole:         ['MS_ADMIN', 'GRADE_LEADER', 'CLASS_TEACHER', 'TEACHER'],
  ErrorFunnel:             ['MS_ADMIN', 'GRADE_LEADER', 'CLASS_TEACHER', 'TEACHER'],

  // ── 教研工具 ──
  StudentCoach:            ['MS_ADMIN', 'GRADE_LEADER', 'CLASS_TEACHER', 'TEACHER'],
  TeacherReport:           ['MS_ADMIN', 'GRADE_LEADER', 'CLASS_TEACHER', 'TEACHER'],
  ResearchConsole:         ['MS_ADMIN', 'GRADE_LEADER', 'CLASS_TEACHER', 'TEACHER'],

  // ── 心理关怀 ──
  PsychScreening:          ['MS_ADMIN', 'GRADE_LEADER', 'CLASS_TEACHER', 'COUNSELOR'],
  PsychSurveyFill:         ['MS_ADMIN', 'GRADE_LEADER', 'CLASS_TEACHER', 'COUNSELOR'],
  PsychResultView:         ['MS_ADMIN', 'GRADE_LEADER', 'CLASS_TEACHER', 'COUNSELOR'],
  PsychIntervention:       ['MS_ADMIN', 'GRADE_LEADER', 'CLASS_TEACHER', 'COUNSELOR'],
  PsychPortrait:           ['MS_ADMIN', 'GRADE_LEADER', 'COUNSELOR'],               // CLASS_TEACHER: aggregate only; COUNSELOR: assigned cases
  CounselorConsole:        ['MS_ADMIN', 'GRADE_LEADER', 'COUNSELOR'],               // GROUP/BRANCH_ADMIN禁止: 心理咨询正文
  NexusBoard:              ['MS_ADMIN', 'GRADE_LEADER'],

  // ── 家长门户 ──
  ParentPortal:            ['PARENT'],
  ParentFeedback:          ['PARENT'],
  ParentAppeal:            ['PARENT'],
  ParentBlindbox:          ['PARENT'],
  AppointmentPicker:       ['PARENT', 'COUNSELOR'],

  // ── Hidden sub-routes (same ROUTE_ACCESS check as visible routes) ──
  StudentDetail:           ['MS_ADMIN', 'GROUP_ADMIN', 'BRANCH_ADMIN', 'GRADE_LEADER', 'CLASS_TEACHER'],
  TeacherDetail:           ['MS_ADMIN', 'GROUP_ADMIN', 'BRANCH_ADMIN', 'GRADE_LEADER'],
  TeacherWorkload:         ['MS_ADMIN', 'GROUP_ADMIN', 'BRANCH_ADMIN', 'GRADE_LEADER'],
  TimetableWeekView:       ['MS_ADMIN', 'GRADE_LEADER', 'CLASS_TEACHER', 'TEACHER'],
  TeacherWeekView:         ['MS_ADMIN', 'GRADE_LEADER', 'CLASS_TEACHER', 'TEACHER'],
  TimetableConflicts:      ['MS_ADMIN', 'GRADE_LEADER', 'CLASS_TEACHER', 'TEACHER'],
}

// ─────────────────────────────────────────────────────────────
// Menu definition — single source for sidebar generation
// ─────────────────────────────────────────────────────────────
export interface MenuItemDef {
  menuCode: string
  title: string
  icon: string
  routeName: string
  /** 学段限制 (缺省=全学段) */
  phases?: string[]
  /** 插件开关依赖 */
  plugin?: string
}

export interface MenuGroupDef {
  title: string
  icon: string
  items: MenuItemDef[]
}

export const MENU_GROUPS: MenuGroupDef[] = [
  // ── 1. 公共底座 ──
  {
    title: '公共底座',
    icon: 'Platform',
    items: [
      { menuCode: 'dashboard', title: '指挥舱看板', icon: 'DataLine', routeName: 'DashboardOverview' },
      { menuCode: 'notifications', title: '通知中心', icon: 'Bell', routeName: 'NotificationCenter' },
      { menuCode: 'growth', title: '成长档案', icon: 'TrendCharts', routeName: 'GrowthTimeline' },
      { menuCode: 'grades-profile', title: '全息档案', icon: 'UserFilled', routeName: 'GradesProfile' },
      { menuCode: 'student-registry', title: '学籍管理', icon: 'User', routeName: 'StudentRegistry' },
      { menuCode: 'class-mgmt', title: '班级管理', icon: 'Grid', routeName: 'ClassManagement' },
      { menuCode: 'teacher-mgmt', title: '教师管理', icon: 'Avatar', routeName: 'TeacherManagement' },
    ],
  },
  // ── 2. 德育管理中心 ──
  {
    title: '德育管理中心',
    icon: 'Shield',
    items: [
      { menuCode: 'rdi-radar', title: 'RDI 风险雷达', icon: 'Monitor', routeName: 'RdiRadar', phases: ['junior', 'senior', 'integrated'], plugin: 'enable_rdi' },
      { menuCode: 'rdi-dashboard', title: 'RDI 风险看板', icon: 'Odometer', routeName: 'RdiDashboard', phases: ['junior', 'senior', 'integrated'], plugin: 'enable_rdi' },
      { menuCode: 'approval-center', title: '审批工作台', icon: 'Checked', routeName: 'ApprovalCenter' },
      { menuCode: 'behavior', title: '德育与处分中心', icon: 'Warning', routeName: 'BehaviorCenter' },
      { menuCode: 'discipline', title: '惩戒流转中心', icon: 'Stamp', routeName: 'DisciplineCenter' },
      { menuCode: 'ai-prescription', title: 'AI 德育处方', icon: 'MagicStick', routeName: 'AiPrescription', phases: ['junior', 'senior', 'integrated'] },
      { menuCode: 'evaluation', title: '素质评价', icon: 'TrendCharts', routeName: 'EvaluationDashboard' },
      { menuCode: 'positive-entry', title: '正向加分', icon: 'Plus', routeName: 'PositiveScoreEntry' },
      { menuCode: 'positive-ranking', title: '正能量排行榜', icon: 'Histogram', routeName: 'PositiveRanking' },
      { menuCode: 'reports', title: '报告工作台', icon: 'Document', routeName: 'ReportCenter' },
      { menuCode: 'attendance', title: '考勤管理', icon: 'Calendar', routeName: 'AttendanceCenter' },
      { menuCode: 'attendance-history', title: '考勤历史大盘', icon: 'TrendCharts', routeName: 'ClassHistoryDashboard' },
      { menuCode: 'red-flag', title: '流动红旗', icon: 'Flag', routeName: 'RedFlagCenter' },
      { menuCode: 'card-system', title: '萌卡系统', icon: 'Box', routeName: 'CardSystem', phases: ['primary'], plugin: 'enable_card' },
    ],
  },
  // ── 3. 教导管理中心 ──
  {
    title: '教导管理中心',
    icon: 'School',
    items: [
      { menuCode: 'grades-dashboard', title: '成绩看板', icon: 'DataLine', routeName: 'GradesDashboard', phases: ['junior', 'senior', 'integrated'] },
      { menuCode: 'grades-radar', title: '成绩雷达', icon: 'Aim', routeName: 'GradesRadar', phases: ['junior', 'senior', 'integrated'] },
      { menuCode: 'prescriptions', title: 'AI 处方中心', icon: 'MagicStick', routeName: 'PrescriptionCenter', phases: ['junior', 'senior', 'integrated'] },
      { menuCode: 'gaokao', title: '高考学情大盘', icon: 'TrophyBase', routeName: 'GaokaoDashboard', phases: ['senior', 'integrated'] },
      { menuCode: 'data-adapter', title: '数据并网', icon: 'Connection', routeName: 'DataAdapter', phases: ['junior', 'senior', 'integrated'] },
      { menuCode: 'timetable', title: '课程表管理', icon: 'Calendar', routeName: 'Timetable' },
      { menuCode: 'habit-cards', title: '萌卡荣誉生态', icon: 'Medal', routeName: 'HabitCards', phases: ['primary', 'integrated'] },
      { menuCode: 'homework', title: '作业管理', icon: 'EditPen', routeName: 'HomeworkConsole', phases: ['junior', 'senior', 'integrated'] },
      { menuCode: 'error-funnel', title: '错题断层', icon: 'Filter', routeName: 'ErrorFunnel', phases: ['junior', 'senior', 'integrated'] },
    ],
  },
  // ── 4. 教研工具 ──
  {
    title: '教研工具',
    icon: 'Tools',
    items: [
      { menuCode: 'research', title: '教研协同', icon: 'Coordinate', routeName: 'ResearchConsole' },
      { menuCode: 'teach-coach', title: '审题助手', icon: 'Reading', routeName: 'StudentCoach', phases: ['junior', 'senior', 'integrated'] },
      { menuCode: 'teach-report', title: '审题诊断', icon: 'DataAnalysis', routeName: 'TeacherReport', phases: ['junior', 'senior', 'integrated'] },
    ],
  },
  // ── 5. 心理关怀 ──
  {
    title: '心理关怀',
    icon: 'Sunrise',
    items: [
      { menuCode: 'psych-screening', title: '心理筛查', icon: 'Sunny', routeName: 'PsychScreening' },
      { menuCode: 'psych-fill', title: '量表填写', icon: 'EditPen', routeName: 'PsychSurveyFill' },
      { menuCode: 'psych-result', title: '筛查结果', icon: 'DataAnalysis', routeName: 'PsychResultView' },
      { menuCode: 'psych-intervention', title: '干预管理', icon: 'FirstAidKit', routeName: 'PsychIntervention' },
      { menuCode: 'psych-portrait', title: '画像与交叉分析', icon: 'PieChart', routeName: 'PsychPortrait' },
      { menuCode: 'counselor-console', title: '心理咨询工作台', icon: 'ChatDotRound', routeName: 'CounselorConsole' },
      { menuCode: 'nexus-board', title: '双轨预警决策看板', icon: 'DataLine', routeName: 'NexusBoard' },
    ],
  },
  // ── 6. 家长门户 ──
  {
    title: '家长门户',
    icon: 'HomeFilled',
    items: [
      { menuCode: 'parent-home', title: '家长首页', icon: 'HomeFilled', routeName: 'ParentPortal' },
      { menuCode: 'parent-feedback', title: '家校反馈', icon: 'ChatLineSquare', routeName: 'ParentFeedback' },
      { menuCode: 'parent-appeal', title: '在线申诉', icon: 'WarningFilled', routeName: 'ParentAppeal' },
      { menuCode: 'parent-notifications', title: '通知中心', icon: 'Bell', routeName: 'NotificationCenter' },
      { menuCode: 'parent-growth', title: '成长时间轴', icon: 'TrendCharts', routeName: 'GrowthTimeline' },
      { menuCode: 'parent-positive', title: '我的正能量', icon: 'Trophy', routeName: 'PositiveScoreStudentView' },
      { menuCode: 'parent-ranking', title: '正能量排行榜', icon: 'Histogram', routeName: 'PositiveRanking' },
      { menuCode: 'parent-appointment', title: '心理咨询预约', icon: 'Clock', routeName: 'AppointmentPicker' },
    ],
  },
]

// ─────────────────────────────────────────────────────────────
// Validation & helper functions
// ─────────────────────────────────────────────────────────────

/**
 * Check if a role can access a given route name.
 * - ROUTE_ACCESS entry exists → only listed roles can access
 * - No entry → DENY (fail closed, prevents accidental omission)
 *   Exception: hidden routes (meta.hidden) skip this check in the guard
 */
export function canAccessRoute(role: UserRole | null, routeName: string): boolean {
  if (!role) return false
  const allowed = ROUTE_ACCESS[routeName]
  // Fail closed: no entry = no access (hidden routes are handled separately in the guard)
  if (!allowed) return false
  return allowed.includes(role)
}

/** Get the default route name for a role */
export function getDefaultRouteName(role: UserRole | null): string {
  if (!role) return 'DashboardOverview'
  return ROLE_DEFAULT_ROUTES[role] ?? 'DashboardOverview'
}

/** Get all menu groups visible to a role (after phase + plugin filtering) */
export function getMenuItemsForRole(
  role: UserRole | null,
  currentPhase: string,
  pluginConfig: Record<string, any> | null,
  isSuperAdmin: boolean,
): MenuGroupDef[] {
  if (!role) return []
  return MENU_GROUPS
    .map(g => ({
      ...g,
      items: g.items.filter(item => {
        // 1. Role filter via ROUTE_ACCESS
        if (!canAccessRoute(role, item.routeName)) return false
        // 2. Phase filter (MS_ADMIN skips)
        if (!isSuperAdmin && item.phases && !item.phases.includes(currentPhase)) return false
        // 3. Plugin filter
        if (item.plugin && pluginConfig?.[item.plugin] !== true) return false
        return true
      }),
    }))
    .filter(g => g.items.length > 0)
}
