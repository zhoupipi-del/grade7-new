import request from './request'

export interface ActiveTeacher {
  id: number
  real_name: string
  subject_code: string | null
}

export interface ResearchMetrics {
  plans_count: number
  versions_count: number
  published_count: number
  comments_count: number
  activities_count: number
  observations_count: number
  observed_count: number
  timeline_marks_count: number
  ai_integration_count: number
  ai_published_count: number
  avg_versions_per_plan: number
  // V3.2 质量维度
  observed_avg_score: number
  scoring_avg: number
  scoring_count: number
  school_avg_score: number
  rubric_count: number
}

export interface ResearchScores {
  intensity: number
  social: number
  rigor: number
  ai_integration: number
}

export interface TeacherResearchProfile {
  teacher_id: number
  metrics: ResearchMetrics
  scores: ResearchScores
}

/** 获取学校所有活跃的教研教师 */
export function getActiveTeachers(): Promise<ActiveTeacher[]> {
  return request.get('/research/teachers')
}

/** 抓取指定教师的教研效能四维画像 */
export function getTeacherProfile(teacherId: number): Promise<TeacherResearchProfile> {
  return request.get(`/research/teachers/${teacherId}/profile`)
}

// ══════════════════════════════════════════════════════════════
// 错题断层归因（dim5 独立诊断维度，不计入四维综合分）
// ══════════════════════════════════════════════════════════════

export interface ErrorGapBreakdown {
  total: number
  unresolved: number
  by_error_type: Record<string, number>
}

export interface KnowledgeGapBreakdown {
  total: number
  critical: number
  active: number
  resolved: number
}

export interface TeacherErrorGap {
  teacher_id: number
  attributed_students: number
  attribution: 'precise' | 'fallback' | 'none'
  error_book: ErrorGapBreakdown
  knowledge_gap: KnowledgeGapBreakdown
  score: number
}

/** 抓取指定教师的任教范围学生错题断层归因（教学盲区关注度诊断信号） */
export function getTeacherErrorGap(teacherId: number): Promise<TeacherErrorGap> {
  return request.get(`/research/teachers/${teacherId}/error-gap`)
}
