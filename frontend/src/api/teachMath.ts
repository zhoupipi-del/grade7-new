/**
 * teachMath.ts — 审题助手 API 契约层
 *
 * 对应后端模块: modules/teach_math (MODULE_CODE="teach_math" → URL前缀 /api/v1/teach_math)
 * 端点:
 *   POST  /api/v1/teach_math/translate                   — AI 逐句翻译数学应用题
 *   GET   /api/v1/teach_math/translations                — 翻译历史记录
 *   GET   /api/v1/teach_math/report/:classId/kpi         — 教师端班级KPI
 *   GET   /api/v1/teach_math/report/:classId/blind-spots — 审题盲区排行
 *   GET   /api/v1/teach_math/report/:classId/students    — 学生个体学情下钻
 */

import request from './request'

// ═══════════════════════════════════════════════════════
// 类型定义 (1:1 映射后端 Pydantic schemas)
// ═══════════════════════════════════════════════════════

/** 请求 AI 逐句翻译 */
export interface TranslateRequest {
  question_text: string
  grade_level: string
  knowledge_point?: string
}

/** 单句翻译结果 */
export interface TranslatedSentence {
  sentence: string
  math_expression: string
  explanation: string
}

/** 翻译完整响应 */
export interface TranslateResponse {
  translations: TranslatedSentence[]
  suggested_variables: Record<string, string>
  raw_llm_response: Record<string, unknown>
  translation_id: number | null
}

/** 翻译历史记录 */
export interface TranslationHistoryItem {
  id: number
  question_text: string
  grade_level: string
  knowledge_point: string | null
  llm_response: Record<string, unknown>
  created_at: string | null
}

// ═══════════════════════════════════════════════════════
// 教师端报表类型 (P1: 学情诊断仪表盘)
// ═══════════════════════════════════════════════════════

/** 班级整体 KPI 与趋势 */
export interface MathReportKPI {
  active_students: number
  total_translations: number
  avg_queries_per_student: number
  risk_students_count: number
  trend_data: { date: string; count: number }[]
}

/** 审题盲区实体 */
export interface BlindSpotItem {
  term: string
  frequency: number
  error_type: string
}

/** 学生个体学情画像 */
export interface StudentUsageItem {
  student_id: number
  student_name: string
  query_count: number
  top_blind_spot: string
  independence_score: number
  rdi_status: 'safe' | 'warning' | 'danger'
}

// ═══════════════════════════════════════════════════════
// Thin Wrapper Functions
// ═══════════════════════════════════════════════════════

/**
 * AI 逐句翻译数学应用题
 * RBAC: MS_ADMIN, GRADE_LEADER, CLASS_TEACHER
 */
export function translateQuestion(data: TranslateRequest) {
  return request.post<any, TranslateResponse>('/teach_math/translate', data)
}

/**
 * 获取翻译历史记录
 * RBAC: MS_ADMIN, GRADE_LEADER
 */
export function getTranslationHistory(limit: number = 20) {
  return request.get<any, TranslationHistoryItem[]>('/teach_math/translations', {
    params: { limit },
  })
}

/**
 * 教师端 — 班级 KPI 总览与趋势
 * RBAC: MS_ADMIN, GRADE_LEADER, CLASS_TEACHER
 */
export function getClassReportKPI(classId: number, timeRange: string) {
  return request.get<any, MathReportKPI>(`/teach_math/report/${classId}/kpi`, {
    params: { timeRange },
  })
}

/**
 * 教师端 — 审题盲区排行
 * RBAC: MS_ADMIN, GRADE_LEADER, CLASS_TEACHER
 */
export function getBlindSpots(classId: number, timeRange: string) {
  return request.get<any, BlindSpotItem[]>(`/teach_math/report/${classId}/blind-spots`, {
    params: { timeRange },
  })
}

/**
 * 教师端 — 学生个体学情下钻
 * RBAC: MS_ADMIN, GRADE_LEADER, CLASS_TEACHER
 */
export function getStudentUsageList(classId: number) {
  return request.get<any, StudentUsageItem[]>(`/teach_math/report/${classId}/students`)
}

// ═══════════════════════════════════════════════════════
// 业务常量
// ═══════════════════════════════════════════════════════

/** 年级选项 (初二重点) */
export const GRADE_OPTIONS = [
  { label: '七年级上', value: '七年级上' },
  { label: '七年级下', value: '七年级下' },
  { label: '八年级上', value: '八年级上' },
  { label: '八年级下', value: '八年级下' },
  { label: '九年级上', value: '九年级上' },
  { label: '九年级下', value: '九年级下' },
] as const

/** 知识点分类 (初二数学) */
export const KNOWLEDGE_CATEGORIES = {
  algebra: {
    label: '代数',
    points: ['一元一次方程', '二元一次方程组', '一元一次不等式', '整式运算', '因式分解'],
  },
  geometry: {
    label: '几何',
    points: ['三角形与全等', '勾股定理', '平行四边形', '几何证明', '面积计算'],
  },
  function: {
    label: '函数',
    points: ['一次函数', '函数图像', '函数应用题'],
  },
  word_problems: {
    label: '应用题',
    points: ['行程问题', '工程问题', '浓度问题', '利润问题', '年龄问题', '数字问题'],
  },
} as const

// ═══════════════════════════════════════════════════════
// 显示辅助函数
// ═══════════════════════════════════════════════════════

/** 年级全称 → 短标签 */
export function gradeShortLabel(grade: string): string {
  const map: Record<string, string> = {
    '七年级上': '七上',
    '七年级下': '七下',
    '八年级上': '八上',
    '八年级下': '八下',
    '九年级上': '九上',
    '九年级下': '九下',
  }
  return map[grade] || grade
}

/** 知识点 → 所属分类标签 */
export function knowledgeCategoryLabel(point: string): string {
  for (const cat of Object.values(KNOWLEDGE_CATEGORIES)) {
    if ((cat.points as readonly string[]).includes(point)) return cat.label
  }
  return '其他'
}
