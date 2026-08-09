<template>
  <div class="holistic-profile">
    <!-- ═══ 顶部筛选栏 ═══ -->
    <div class="profile-controls">
      <el-row :gutter="16" align="middle">
        <el-col :span="6">
          <el-select v-model="selectedClassId" placeholder="选择班级" @change="onClassChange" clearable>
            <el-option v-for="c in classList" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
        </el-col>
        <el-col :span="6">
          <el-select v-model="selectedStudentId" placeholder="选择学生" @change="onStudentChange" :disabled="!selectedClassId" filterable>
            <el-option v-for="s in studentList" :key="s.id" :label="s.name" :value="s.id" />
          </el-select>
        </el-col>
        <el-col :span="4">
          <el-select v-model="selectedExamId" placeholder="选择考试" @change="fetchGradesData" clearable>
            <el-option v-for="e in examList" :key="e.id" :label="e.name" :value="e.id" />
          </el-select>
        </el-col>
        <el-col :span="4">
          <el-button @click="useDemoData" type="warning" plain size="small">
            <el-icon><MagicStick /></el-icon> Demo数据
          </el-button>
        </el-col>
        <el-col :span="10" style="text-align: right;">
          <el-tag v-if="rdiInfo" :type="rdiTagType" effect="dark" size="large" class="rdi-badge-inline">
            RDI {{ rdiInfo.total_rdi ?? rdiInfo.rdi_score ?? '--' }}
          </el-tag>
        </el-col>
      </el-row>
    </div>

    <!-- ═══ 学生信息卡 ═══ -->
    <div v-if="currentStudent" class="student-header-card">
      <div class="avatar-wrapper">
        <div class="avatar-circle" :style="{ background: avatarGradient }">
          {{ currentStudent.name?.charAt(0) ?? '?' }}
        </div>
      </div>
      <div class="student-meta">
        <h2 class="student-name">{{ currentStudent.name }}</h2>
        <div class="student-tags">
          <el-tag size="small" type="primary">{{ currentStudent.class_name ?? `班级${currentStudent.class_id}` }}</el-tag>
          <el-tag v-if="rdiInfo" size="small" :type="rdiTagType" effect="plain">
            RDI {{ rdiInfo.total_rdi ?? rdiInfo.rdi_score ?? '--' }}
          </el-tag>
          <el-tag v-if="currentStudent.gender" size="small" effect="plain">{{ currentStudent.gender }}</el-tag>
        </div>
      </div>
      <!-- RDI 大数字面板 -->
      <div v-if="rdiInfo" class="rdi-panel">
        <div class="rdi-big-number">
          {{ rdiInfo.total_rdi ?? rdiInfo.rdi_score ?? '--' }}
        </div>
        <div class="rdi-label">偏离指数</div>
        <div class="rdi-progress-track">
          <div class="rdi-progress-fill" :style="{ width: rdiProgressWidth, background: rdiProgressColor }"></div>
        </div>
      </div>
    </div>

    <!-- ═══ 核心内容区 ═══ -->
    <div v-if="currentStudent" class="profile-body">
      <!-- ── 左栏: 双模态雷达 + 五维对比 + RDI迷你雷达 ── -->
      <div class="profile-left">
        <!-- 雷达模式切换 -->
        <div class="radar-mode-switch">
          <el-button-group>
            <el-button :type="radarMode === 'overlay' ? 'primary' : 'default'" @click="radarMode = 'overlay'">叠加模式</el-button>
            <el-button :type="radarMode === 'academic' ? 'primary' : 'default'" @click="radarMode = 'academic'">仅学业</el-button>
            <el-button :type="radarMode === 'behavior' ? 'primary' : 'default'" @click="radarMode = 'behavior'">仅行为</el-button>
          </el-button-group>
        </div>

        <!-- 主雷达图 -->
        <div class="chart-card">
          <h3 class="card-title">双模态全息雷达</h3>
          <div ref="radarChartRef" class="chart-container radar-chart"></div>
        </div>

        <!-- 五维对比明细 -->
        <div class="detail-card">
          <h3 class="card-title">五维对比明细</h3>
          <div class="dimension-comparison-grid">
            <div v-for="d in dimensionDetails" :key="d.key" class="dimension-row">
              <div class="dim-label" :style="{ color: d.color }">{{ d.label }}</div>
              <div class="dim-values">
                <span class="dim-academic">{{ d.academicScore }}</span>
                <span class="dim-separator">vs</span>
                <span class="dim-behavior">{{ d.behaviorScore }}</span>
                <span class="dim-delta" :class="{ 'delta-pos': d.delta > 0, 'delta-neg': d.delta < 0 }">
                  Δ{{ d.delta > 0 ? '+' : '' }}{{ d.delta }}
                </span>
              </div>
              <div class="dim-bar-wrapper">
                <div class="dim-bar academic-bar" :style="{ width: Math.min(d.academicScore, 100) + '%', background: d.color }"></div>
                <div class="dim-bar behavior-bar" :style="{ width: Math.min(d.behaviorScore, 100) + '%', background: d.behaviorColor }"></div>
              </div>
            </div>
          </div>
        </div>

        <!-- RDI 迷你雷达 -->
        <div v-if="rdiInfo" class="chart-card mini-radar-card">
          <h3 class="card-title">RDI 三维偏离</h3>
          <div ref="miniRadarRef" class="chart-container mini-radar"></div>
        </div>

        <!-- 各科偏离柱状图 -->
        <div class="chart-card">
          <h3 class="card-title">各科偏离年级均值</h3>
          <div ref="subjectDeviationRef" class="chart-container subject-deviation"></div>
        </div>
      </div>

      <!-- ── 右栏: 成长时间轴 + AI处方 ── -->
      <div class="profile-right">
        <!-- 事件类型过滤 -->
        <div class="timeline-filter">
          <el-radio-group v-model="timelineFilter" size="small">
            <el-radio-button label="all">全部</el-radio-button>
            <el-radio-button label="behavior">违纪</el-radio-button>
            <el-radio-button label="sanction">处分</el-radio-button>
            <el-radio-button label="attendance">考勤</el-radio-button>
            <el-radio-button label="score_log">成绩</el-radio-button>
            <el-radio-button label="recovery">回血</el-radio-button>
          </el-radio-group>
        </div>

        <!-- 成长时间轴 -->
        <div class="timeline-card">
          <h3 class="card-title">成长时间轴</h3>
          <div class="timeline-track">
            <template v-for="(group, date) in groupedTimeline" :key="date">
              <div class="date-divider">
                <span class="date-dot"></span>
                <span class="date-text">{{ date }}</span>
              </div>
              <div v-for="evt in group" :key="evt.event_id" class="timeline-event" :class="'severity-' + evt.severity">
                <div class="event-node" :style="{ background: eventTypeColor(evt.event_type) }"></div>
                <div class="event-card">
                  <div class="event-header">
                    <span class="event-type-tag" :style="{ background: eventTypeColor(evt.event_type), color: '#fff' }">
                      {{ eventTypeLabel(evt.event_type) }}
                    </span>
                    <span class="event-time">{{ formatTime(evt.occurred_at) }}</span>
                  </div>
                  <div class="event-title">{{ evt.title }}</div>
                  <div v-if="evt.description" class="event-desc">{{ evt.description }}</div>
                </div>
              </div>
            </template>
            <div v-if="filteredTimeline.length === 0" class="timeline-empty">暂无时间轴数据</div>
          </div>
        </div>

        <!-- AI 处方卡片 (V2 三段式: 事实研判→交叉归因→成长处方) -->
        <div v-if="prescription" class="prescription-card">
          <h3 class="card-title">
            <el-icon><FirstAidKit /></el-icon> AI德育处方
            <el-tag v-if="breakerActive" type="danger" effect="dark" size="small" class="breaker-tag">
              熔断 {{ breakerRemaining }}h
            </el-tag>
          </h3>
          <!-- 处方元信息 -->
          <div class="prescription-meta">
            <span class="meta-student">{{ prescription.student_name }}</span>
            <span class="meta-divider">|</span>
            <span>{{ prescription.class_name }}</span>
            <span class="meta-divider">|</span>
            <span>RDI {{ prescription.rdi_score.toFixed(1) }}</span>
            <el-tag :type="riskTagType(prescription.risk_level)" size="small" effect="plain" class="meta-risk-tag">
              {{ riskLabel(prescription.risk_level) }}
            </el-tag>
          </div>
          <div class="prescription-summary">{{ prescription.analysis_summary }}</div>
          <!-- V2 三段式渲染 -->
          <div class="prescription-segments">
            <div class="prescription-segment segment-fact">
              <div class="segment-label">事实研判</div>
              <div class="segment-content" v-html="renderSegmentMarkdown(prescription.fact)"></div>
            </div>
            <div class="prescription-segment segment-analysis">
              <div class="segment-label">交叉归因</div>
              <div class="segment-content" v-html="renderSegmentMarkdown(prescription.analysis)"></div>
            </div>
            <div class="prescription-segment segment-growth">
              <div class="segment-label">成长处方</div>
              <div class="segment-content" v-html="renderSegmentMarkdown(prescription.growth)"></div>
            </div>
          </div>
        </div>
        <div v-else-if="!prescriptionLoading" class="prescription-empty">
          <el-button @click="triggerPrescription" type="primary" plain size="small" :disabled="!currentStudent">
            <el-icon><FirstAidKit /></el-icon> 触发AI处方
          </el-button>
        </div>
        <div v-if="prescriptionLoading" class="prescription-loading">
          <el-icon class="is-loading"><Loading /></el-icon> 处方生成中...
        </div>
      </div>
    </div>

    <!-- ═══ 空状态 ═══ -->
    <div v-if="!currentStudent && !dataLoading" class="empty-state">
      <el-icon :size="64" color="#c0c4cc"><User /></el-icon>
      <p>请选择班级和学生查看全息档案</p>
    </div>

    <!-- ═══ 全局加载 ═══ -->
    <div v-if="dataLoading" class="loading-overlay">
      <el-icon class="is-loading" :size="48"><Loading /></el-icon>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import * as echarts from 'echarts/core'
import { RadarChart, BarChart } from 'echarts/charts'
import { TitleComponent, TooltipComponent, LegendComponent, GridComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { ComposeOption } from 'echarts/core'
import type { RadarSeriesOption, BarSeriesOption } from 'echarts/charts'
import type { TitleComponentOption, TooltipComponentOption, LegendComponentOption, GridComponentOption } from 'echarts/components'

import {
  getExamList, getScoreResults, getSubjectList, getDemoExamList, getDemoScoreResults, getDemoSubjectList,
  type ExamOut, type ExamItem, type ScoreResultItem, type SubjectItem,
  SUBJECT_COLORS, SUBJECT_DIMENSION_MAP, subjectColor
} from '@/api/grades'
import {
  getStudentScores, getDemoStudentScores,
  DIMENSION_LABELS, DIMENSION_COLORS,
  type EvalDimension, type StudentScoreOut
} from '@/api/evaluation'
import {
  calculateRDI, getRiskMonitorPanel, getDemoRDI, getDemoRiskMonitorPanel,
  type RDIDiagnosis
} from '@/api/rdi'
import {
  getGrowthTimeline, getDemoTimeline,
  type GrowthTimelineResponse, type TimelineItem, type GrowthEventType, type EventSeverity,
  EVENT_TYPE_META
} from '@/api/growth'
import {
  getAIPrescriptionV2, getDemoPrescriptionV2, isBreakerActive, getBreakerRemaining, activateBreaker,
  renderSegmentMarkdown, type AIPrescriptionPayloadV2
} from '@/api/prescription'
import { getClasses, getStudents } from '@/api/classes'
import { MagicStick, FirstAidKit, Loading, User } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

// ── ECharts 注册 ──
echarts.use([RadarChart, BarChart, TitleComponent, TooltipComponent, LegendComponent, GridComponent, CanvasRenderer])
type ECOption = ComposeOption<RadarSeriesOption | BarSeriesOption | TitleComponentOption | TooltipComponentOption | LegendComponentOption | GridComponentOption>

// ═══════════════════════════════════════════════════
// 常量
// ═══════════════════════════════════════════════════

const RADAR_MAX = 100

/** 维度→科目反向映射 */
const DIMENSION_SUBJECTS: Record<EvalDimension, string[]> = {
  moral: ['chinese', 'politics'],
  academic: ['math', 'physics', 'chemistry'],
  health: ['biology', 'pe'],
  art: ['art', 'music'],
  social: ['english', 'history', 'geography']
}

// ═══════════════════════════════════════════════════
// 状态
// ═══════════════════════════════════════════════════

const selectedClassId = ref<number | null>(null)
const selectedStudentId = ref<number | null>(null)
const selectedExamId = ref<number | null>(null)
const radarMode = ref<'overlay' | 'academic' | 'behavior'>('overlay')
const timelineFilter = ref<string>('all')

const classList = ref<any[]>([])
const studentList = ref<any[]>([])
const examList = ref<ExamItem[]>([])
const subjectList = ref<SubjectItem[]>([])

const scoresData = ref<ScoreResultItem[]>([])
const evalData = ref<StudentScoreOut | null>(null)
const rdiInfo = ref<RDIDiagnosis | null>(null)
const timelineData = ref<TimelineItem[]>([])
const prescription = ref<AIPrescriptionPayloadV2 | null>(null)

const dataLoading = ref(false)
const prescriptionLoading = ref(false)
// 🔪 Fix: isDemoMode flag — 防止 useDemoData() 设置 selectedExamId 时触发 watcher 冲刷 Demo 数据
const isDemoMode = ref(false)
const breakerActive = ref(false)
const breakerRemaining = ref(0)
let breakerTimer: ReturnType<typeof setInterval> | null = null

// ── 图表 refs ──
const radarChartRef = ref<HTMLElement | null>(null)
const miniRadarRef = ref<HTMLElement | null>(null)
const subjectDeviationRef = ref<HTMLElement | null>(null)

let radarChart: echarts.ECharts | null = null
let miniRadarChart: echarts.ECharts | null = null
let subjectDeviationChart: echarts.ECharts | null = null
let resizeObserver: ResizeObserver | null = null

// ═══════════════════════════════════════════════════
// 计算属性
// ═══════════════════════════════════════════════════

const currentStudent = computed(() => {
  if (!selectedStudentId.value) return null
  return studentList.value.find(s => s.id === selectedStudentId.value) ?? null
})

/** 头像确定性渐变 */
const avatarGradient = computed(() => {
  if (!currentStudent.value) return 'linear-gradient(135deg, #667eea, #764ba2)'
  const name = currentStudent.value.name ?? ''
  const hash = name.split('').reduce((a: number, c: string) => a + c.charCodeAt(0), 0)
  const hue1 = (hash * 7) % 360
  const hue2 = (hue1 + 40) % 360
  return `linear-gradient(135deg, hsl(${hue1}, 70%, 55%), hsl(${hue2}, 60%, 45%))`
})

/** RDI 标签配色 */
const rdiTagType = computed(() => {
  if (!rdiInfo.value) return 'info'
  const score = rdiInfo.value.total_rdi ?? rdiInfo.value.rdi_score ?? 0
  if (score >= 5.0) return 'danger'
  if (score >= 4.0) return 'warning'
  return 'success'
})

const rdiProgressWidth = computed(() => {
  if (!rdiInfo.value) return '0%'
  const score = rdiInfo.value.total_rdi ?? rdiInfo.value.rdi_score ?? 0
  return Math.min(score / 10 * 100, 100) + '%'
})

const rdiProgressColor = computed(() => {
  if (!rdiInfo.value) return '#10b981'
  const score = rdiInfo.value.total_rdi ?? rdiInfo.value.rdi_score ?? 0
  if (score >= 5.0) return '#ef4444'
  if (score >= 4.0) return '#f59e0b'
  return '#10b981'
})

/** 五维对比明细 */
const dimensionDetails = computed(() => {
  const dims: EvalDimension[] = ['moral', 'academic', 'health', 'art', 'social']
  return dims.map(dim => {
    // 学业映射分: 归一化到100分制取平均
    const subjects = DIMENSION_SUBJECTS[dim] ?? []
    let academicScore = 0
    let count = 0
    subjects.forEach(code => {
      const subj = subjectList.value.find(s => s.code === code)
      const score = scoresData.value.find((sc: ScoreResultItem) => sc.subject_code === code)
      if (subj && score) {
        academicScore += ((score.score ?? 0) / subj.full_score) * 100
        count++
      }
    })
    if (count > 0) academicScore = Math.round(academicScore / count)

    // 行为评价原始分: StudentScoreOut 属性名带 '_score' 后缀
    const behaviorScore = evalData.value ? Math.round(
      (evalData.value as any)[dim + '_score'] ?? evalData.value.total_score ?? 0
    ) : 0

    const delta = academicScore - behaviorScore
    return {
      key: dim,
      label: DIMENSION_LABELS[dim],
      color: DIMENSION_COLORS[dim],
      behaviorColor: DIMENSION_COLORS[dim] + '80',
      academicScore,
      behaviorScore,
      delta
    }
  })
})

/** 时间轴按日期分组 */
const groupedTimeline = computed(() => {
  const items = filteredTimeline.value
  const groups: Record<string, TimelineItem[]> = {}
  items.forEach(evt => {
    const dateKey = evt.event_date ?? evt.occurred_at?.slice(0, 10) ?? '未知日期'
    if (!groups[dateKey]) groups[dateKey] = []
    groups[dateKey].push(evt)
  })
  // 按日期倒序
  const sortedKeys = Object.keys(groups).sort((a, b) => b.localeCompare(a))
  const result: Record<string, TimelineItem[]> = {}
  sortedKeys.forEach(k => result[k] = groups[k])
  return result
})

const filteredTimeline = computed(() => {
  if (timelineFilter.value === 'all') return timelineData.value
  return timelineData.value.filter(evt => evt.event_type === timelineFilter.value)
})

// ═══════════════════════════════════════════════════
// 数据获取
// ═══════════════════════════════════════════════════

async function fetchClasses() {
  try {
    // Axios interceptor 已自动解包 response.data，res 是裸数据（TS 仍认为 AxiosResponse，故标注 any）
    const res: any = await getClasses()
    classList.value = res?.items ?? (Array.isArray(res) ? res : [])
  } catch {
    classList.value = []
  }
}

async function onClassChange() {
  selectedStudentId.value = null
  if (!selectedClassId.value) { studentList.value = []; return }
  try {
    const res: any = await getStudents({ class_id: selectedClassId.value, page: 1, page_size: 100 })
    // Axios interceptor 已自动解包；加括号修正 ?? vs ? : 优先级
    studentList.value = res?.items ?? (Array.isArray(res) ? res : [])
  } catch {
    studentList.value = []
  }
}

async function onStudentChange() {
  if (!selectedStudentId.value) return
  await fetchAllData()
}

async function fetchExamList() {
  try {
    const res = await getExamList()
    examList.value = Array.isArray(res) ? res : []
  } catch {
    examList.value = await getDemoExamList()
  }
}

async function fetchSubjectList() {
  try {
    const res = await getSubjectList()
    subjectList.value = Array.isArray(res) ? res : []
  } catch {
    subjectList.value = await getDemoSubjectList()
  }
}

async function fetchGradesData() {
  if (!selectedExamId.value || !selectedStudentId.value) return
  try {
    const res = await getScoreResults({
      exam_id: selectedExamId.value,
      page_size: 100
    })
    scoresData.value = res?.results?.flatMap(r => r.subjects.map(s => {
      // 🔪 Fix: subject_code 必须用英文代码(s.code)，不能用中文科目名(s.subject_name)
      // 中文科目名→英文代码: 优先用API返回的s.code(如果有)，否则用subjectList反查
      const code = (s as any).code
        ?? subjectList.value.find(sl => sl.name === s.subject_name)?.code
        ?? s.subject_name  // 最后兜底：既无code又查不到，保留原始值(查不到时会降级Demo)
      return {
        ...s,
        student_id: r.student_id,
        student_name: r.student_name,
        subject_code: code,
        subject_name: s.subject_name,
      }
    })) ?? []
  } catch {
    scoresData.value = await getDemoScoreResults()
  }
}

async function fetchEvalData() {
  if (!selectedStudentId.value) return
  try {
    const res = await getStudentScores(selectedStudentId.value)
    evalData.value = res ?? null
  } catch {
    evalData.value = await getDemoStudentScores(selectedStudentId.value)
  }
}

async function fetchRDI() {
  if (!selectedStudentId.value) return
  try {
    const res: any = await calculateRDI({ student_id: selectedStudentId.value })
    // Axios interceptor 已自动解包 response.data
    rdiInfo.value = res ?? null
  } catch {
    rdiInfo.value = await getDemoRDI()
  }
}

async function fetchTimeline() {
  if (!selectedStudentId.value) return
  try {
    const res = await getGrowthTimeline(selectedStudentId.value)
    timelineData.value = (res as GrowthTimelineResponse)?.timeline ?? res ?? []
  } catch {
    const demoRes = await getDemoTimeline(selectedStudentId.value)
    timelineData.value = (demoRes as GrowthTimelineResponse)?.timeline ?? demoRes ?? []
  }
}

async function fetchPrescription() {
  if (!selectedStudentId.value) return
  // 先检查熔断器
  const active = isBreakerActive(selectedStudentId.value)
  if (active) {
    breakerActive.value = true
    breakerRemaining.value = getBreakerRemaining(selectedStudentId.value)
    startBreakerTimer()
    return
  }
  // 🔧 P4 Fix: 字段名 warning_id → latest_warning_id
  try {
    const monitorRes = await getRiskMonitorPanel({ student_id: selectedStudentId.value ?? undefined })
    const warningId = (monitorRes as any)?.students?.[0]?.latest_warning_id ?? 1
    await loadPrescriptionV2(warningId)
  } catch {
    // 降级: 尝试 demo 处方
    try {
      const demo = await getDemoPrescriptionV2(selectedStudentId.value ?? 1)
      prescription.value = demo as AIPrescriptionPayloadV2
    } catch {
      prescription.value = null
    }
  }
}

async function loadPrescriptionV2(warningId: number) {
  try {
    // 🔧 P3 Fix: V1→V2 getAIPrescriptionV2，直接从llm_output提取三段
    const res = await getAIPrescriptionV2(warningId, selectedStudentId.value ?? undefined)
    prescription.value = res as AIPrescriptionPayloadV2
    activateBreaker(warningId)
    breakerActive.value = true
    breakerRemaining.value = 72
    startBreakerTimer()
  } catch {
    try {
      const demo = await getDemoPrescriptionV2(selectedStudentId.value ?? 1)
      prescription.value = demo as AIPrescriptionPayloadV2
    } catch {
      prescription.value = null
    }
  }
}

async function triggerPrescription() {
  if (!selectedStudentId.value) return
  prescriptionLoading.value = true
  try {
    await fetchPrescription()
  } finally {
    prescriptionLoading.value = false
  }
}

async function fetchAllData() {
  dataLoading.value = true
  try {
    // 🔧 P2 Fix: fetchPrescription移出Promise.all — Celery异步轮询约12s不阻塞其余5个API
    await Promise.all([
      fetchExamList(),
      fetchSubjectList(),
      fetchEvalData(),
      fetchRDI(),
      fetchTimeline(),
    ])
    // 自动选最近考试
    if (examList.value.length > 0 && !selectedExamId.value) {
      selectedExamId.value = examList.value[0].id
    }
    await fetchGradesData()
    await nextTick()
    initAllCharts()
    // 🔧 处方后台异步加载，不阻塞主渲染
    fetchPrescription().catch(() => {})
  } catch (e: any) {
    ElMessage.error('数据加载失败: ' + (e.message ?? '未知错误'))
  } finally {
    dataLoading.value = false
  }
}

function useDemoData() {
  // 🔪 Fix: 标记 Demo 模式，防止 watcher 冲刷
  isDemoMode.value = true
  selectedClassId.value = 2501
  selectedStudentId.value = 1
  classList.value = [
    { id: 2501, name: '初一(1)班' },
    { id: 2502, name: '初一(2)班' }
  ]
  studentList.value = [
    { id: 1, name: '陈博裕', class_id: 2501, class_name: '初一(1)班', gender: '男' },
    { id: 2, name: '黎梓萱', class_id: 2501, class_name: '初一(1)班', gender: '女' }
  ]
  // 用 Demo 数据填充所有
  examList.value = getDemoExamList()
  subjectList.value = getDemoSubjectList()
  scoresData.value = getDemoScoreResults()
  evalData.value = getDemoStudentScores(1)
  rdiInfo.value = getDemoRDI()
  const growthRes = getDemoTimeline(1) as GrowthTimelineResponse
  timelineData.value = growthRes?.timeline ?? []
  prescription.value = getDemoPrescriptionV2(1) as AIPrescriptionPayloadV2
  selectedExamId.value = examList.value[0]?.id ?? null
  nextTick(() => initAllCharts())
}

// ═══════════════════════════════════════════════════
// 图表初始化
// ═══════════════════════════════════════════════════

function initAllCharts() {
  initDualRadar()
  initMiniRadar()
  initSubjectDeviation()
}

function initDualRadar() {
  if (!radarChartRef.value) return
  if (radarChart) radarChart.dispose()
  radarChart = echarts.init(radarChartRef.value)

  const dims: EvalDimension[] = ['moral', 'academic', 'health', 'art', 'social']
  const indicator = dims.map(d => ({
    name: DIMENSION_LABELS[d],
    max: RADAR_MAX
  }))

  // 学业映射数据
  const academicData = dimensionDetails.value.map(d => d.academicScore)
  // 行为评价数据
  const behaviorData = dimensionDetails.value.map(d => d.behaviorScore)

  const series: any[] = []
  if (radarMode.value === 'overlay' || radarMode.value === 'academic') {
    series.push({
      type: 'radar',
      name: '学业映射',
      data: [{ value: academicData, name: '学业映射' }],
      lineStyle: { color: '#3b82f6', width: 2 },
      areaStyle: { color: 'rgba(59, 130, 246, 0.2)' },
      itemStyle: { color: '#3b82f6' },
      symbol: 'circle',
      symbolSize: 6
    })
  }
  if (radarMode.value === 'overlay' || radarMode.value === 'behavior') {
    series.push({
      type: 'radar',
      name: '行为评价',
      data: [{ value: behaviorData, name: '行为评价' }],
      lineStyle: { color: '#ef4444', width: 2 },
      areaStyle: { color: 'rgba(239, 68, 68, 0.15)' },
      itemStyle: { color: '#ef4444' },
      symbol: 'circle',
      symbolSize: 6
    })
  }

  const option: ECOption = {
    tooltip: { trigger: 'item' },
    legend: { data: series.map(s => s.name), bottom: 0 },
    radar: {
      indicator,
      shape: 'polygon',
      radius: '65%',
      axisName: { color: '#666', fontSize: 12 },
      splitArea: { areaStyle: { color: ['rgba(255,255,255,0.05)', 'rgba(255,255,255,0.1)'] } }
    },
    series
  }
  radarChart.setOption(option)
}

function initMiniRadar() {
  if (!miniRadarRef.value || !rdiInfo.value) return
  if (miniRadarChart) miniRadarChart.dispose()
  miniRadarChart = echarts.init(miniRadarRef.value)

  const rdi = rdiInfo.value
  const indicator = [
    { name: '行为偏离', max: 10 },
    { name: '考勤偏离', max: 10 },
    { name: '学业偏离', max: 10 }
  ]
  const values = [
    rdi.behavior_deviation ?? 0,
    rdi.attendance_deviation ?? 0,
    rdi.score_deviation ?? 0
  ]

  const option: ECOption = {
    tooltip: { trigger: 'item' },
    radar: {
      indicator,
      shape: 'polygon',
      radius: '60%',
      axisName: { color: '#666', fontSize: 11 },
      splitArea: { areaStyle: { color: ['rgba(255,255,255,0.05)', 'rgba(255,255,255,0.1)'] } }
    },
    series: [{
      type: 'radar',
      data: [{ value: values, name: 'RDI偏离度' }],
      lineStyle: { color: '#ef4444', width: 2 },
      areaStyle: { color: 'rgba(239, 68, 68, 0.25)' },
      itemStyle: { color: '#ef4444' },
      symbol: 'circle',
      symbolSize: 5
    }]
  }
  miniRadarChart.setOption(option)
}

function initSubjectDeviation() {
  if (!subjectDeviationRef.value) return
  if (subjectDeviationChart) subjectDeviationChart.dispose()
  subjectDeviationChart = echarts.init(subjectDeviationRef.value)

  // 计算各科偏离
  const deviations: { name: string; value: number; color: string }[] = []
  scoresData.value.forEach((sc: ScoreResultItem) => {
    const subj = subjectList.value.find(s => s.code === sc.subject_code)
    if (!subj) return
    // 简化偏离计算: (个人分 - 期望均值) / 满分 * 100
    // 期望均值 ≈ 满分 * 0.7（年级均值估算）
    const meanEstimate = subj.full_score * 0.7
    const deviationPct = (((sc.score ?? 0) - meanEstimate) / subj.full_score) * 100
    const colorIdx = subjectList.value.findIndex((s: SubjectItem) => s.code === sc.subject_code)
    deviations.push({
      name: subj.name,
      value: Math.round(deviationPct * 10) / 10,
      color: subjectColor(colorIdx >= 0 ? colorIdx : 0)
    })
  })

  const positiveData = deviations.map(d => d.value > 0 ? d.value : 0)
  const negativeData = deviations.map(d => d.value < 0 ? Math.abs(d.value) : 0)

  const option: ECOption = {
    tooltip: {
      trigger: 'axis',
      formatter: (params: any) => {
        const idx = params[0]?.dataIndex ?? 0
        const name = deviations[idx]?.name ?? ''
        const rawVal = deviations[idx]?.value ?? 0
        return `${name}<br/>偏离: ${rawVal > 0 ? '+' : ''}${rawVal}%`
      }
    },
    grid: { left: '10%', right: '10%', bottom: '15%', top: '5%' },
    xAxis: {
      type: 'category',
      data: deviations.map(d => d.name),
      axisLabel: { fontSize: 11, rotate: 30 }
    },
    yAxis: {
      type: 'value',
      name: '偏离%',
      axisLabel: { formatter: '{value}%' }
    },
    series: [
      {
        type: 'bar',
        name: '高于均值',
        data: positiveData,
        itemStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: '#67c23a' },
            { offset: 1, color: '#409eff' }
          ])
        },
        barWidth: '40%'
      },
      {
        type: 'bar',
        name: '低于均值',
        data: negativeData,
        itemStyle: {
          color: new echarts.graphic.LinearGradient(0, 1, 0, 0, [
            { offset: 0, color: '#e6a23c' },
            { offset: 1, color: '#f56c6c' }
          ])
        },
        barWidth: '40%'
      }
    ]
  }
  subjectDeviationChart.setOption(option)
}

// ═══════════════════════════════════════════════════
// 辅助函数
// ═══════════════════════════════════════════════════

function eventTypeColor(type: GrowthEventType): string {
  return EVENT_TYPE_META[type]?.color ?? '#409eff'
}

function eventTypeLabel(type: GrowthEventType): string {
  return EVENT_TYPE_META[type]?.label ?? type
}

function formatTime(timeStr: string): string {
  if (!timeStr) return ''
  try {
    const d = new Date(timeStr)
    return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`
  } catch {
    return timeStr.slice(11, 16)
  }
}

function measureIcon(iconName: string): any {
  const iconMap: Record<string, any> = {
    'FirstAidKit': FirstAidKit,
    'MagicStick': MagicStick
  }
  return iconMap[iconName] ?? FirstAidKit
}

// 🔧 V2 处方辅助函数
function riskTagType(level: string): 'primary' | 'success' | 'warning' | 'danger' {
  if (level === 'CRITICAL' || level === 'HIGH') return 'danger'
  if (level === 'MEDIUM') return 'warning'
  return 'success'
}

function riskLabel(level: string): string {
  const m: Record<string, string> = { CRITICAL: '极危', HIGH: '高危', MEDIUM: '中危', LOW: '低危' }
  return m[level] ?? level
}

function startBreakerTimer() {
  if (breakerTimer) clearInterval(breakerTimer)
  breakerTimer = setInterval(() => {
    if (breakerRemaining.value <= 0) {
      breakerActive.value = false
      if (breakerTimer) clearInterval(breakerTimer)
      breakerTimer = null
      return
    }
    breakerRemaining.value -= 1
  }, 3600000) // 1小时递减
}

// ═══════════════════════════════════════════════════
// 监听与生命周期
// ═══════════════════════════════════════════════════

watch(radarMode, () => {
  nextTick(() => initDualRadar())
})

watch(selectedExamId, () => {
  // 🔪 Fix: Demo 模式下跳过 fetchGradesData()，防止冲刷已填充的 Demo 数据
  if (isDemoMode.value) {
    isDemoMode.value = false  // 重置 flag，后续正常 exam 切换走 API
    nextTick(() => initAllCharts())
    return
  }
  fetchGradesData()
  nextTick(() => initAllCharts())
})

watch(timelineFilter, () => {
  // 仅过滤，无需重新获取
})

onMounted(async () => {
  await fetchClasses()
  // 🔧 P1 Fix: 自动选第一个班级 → 自动选第一个学生 → 触发 fetchAllData
  if (classList.value.length > 0) {
    selectedClassId.value = classList.value[0].id
    await onClassChange()
    if (studentList.value.length > 0) {
      selectedStudentId.value = studentList.value[0].id
      await fetchAllData()
    }
  }
  // 设置 ResizeObserver
  resizeObserver = new ResizeObserver(() => {
    radarChart?.resize()
    miniRadarChart?.resize()
    subjectDeviationChart?.resize()
  })
  if (radarChartRef.value) resizeObserver.observe(radarChartRef.value)
  if (miniRadarRef.value) resizeObserver.observe(miniRadarRef.value)
  if (subjectDeviationRef.value) resizeObserver.observe(subjectDeviationRef.value)
})

onBeforeUnmount(() => {
  radarChart?.dispose()
  miniRadarChart?.dispose()
  subjectDeviationChart?.dispose()
  resizeObserver?.disconnect()
  if (breakerTimer) clearInterval(breakerTimer)
})
</script>

<style scoped>
.holistic-profile {
  padding: 20px;
  min-height: 100vh;
  background: #f0f2f5;
}

/* ═══ 筛选栏 ═══ */
.profile-controls {
  background: #fff;
  border-radius: 12px;
  padding: 16px 20px;
  margin-bottom: 20px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
}
.rdi-badge-inline {
  font-size: 16px;
  font-weight: 700;
  letter-spacing: 1px;
}

/* ═══ 学生信息卡 ═══ */
.student-header-card {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-radius: 16px;
  padding: 24px;
  display: flex;
  align-items: center;
  gap: 20px;
  margin-bottom: 20px;
  color: #fff;
  box-shadow: 0 4px 20px rgba(102, 126, 234, 0.3);
  transition: transform 0.3s cubic-bezier(0.16, 1, 0.3, 1);
}
.student-header-card:hover {
  transform: translateY(-2px);
}
.avatar-wrapper {
  flex-shrink: 0;
}
.avatar-circle {
  width: 64px;
  height: 64px;
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 28px;
  font-weight: 700;
  color: #fff;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.15);
}
.student-meta {
  flex: 1;
}
.student-name {
  font-size: 22px;
  font-weight: 700;
  margin: 0 0 8px 0;
}
.student-tags {
  display: flex;
  gap: 8px;
}
.student-tags .el-tag {
  background: rgba(255, 255, 255, 0.2);
  border-color: rgba(255, 255, 255, 0.3);
  color: #fff;
}
.rdi-panel {
  flex-shrink: 0;
  text-align: center;
  padding: 0 20px;
}
.rdi-big-number {
  font-size: 36px;
  font-weight: 800;
  font-family: 'DIN Alternate', 'Helvetica Neue', monospace;
  line-height: 1;
}
.rdi-label {
  font-size: 12px;
  opacity: 0.8;
  margin: 4px 0 8px 0;
}
.rdi-progress-track {
  width: 80px;
  height: 6px;
  background: rgba(255, 255, 255, 0.2);
  border-radius: 3px;
  overflow: hidden;
}
.rdi-progress-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.5s ease, background 0.3s ease;
}

/* ═══ 内容区 ═══ */
.profile-body {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}
.profile-left {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.profile-right {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* ═══ 通用卡片 ═══ */
.chart-card, .detail-card, .timeline-card, .prescription-card {
  background: #fff;
  border-radius: 12px;
  padding: 20px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
  transition: transform 0.3s cubic-bezier(0.16, 1, 0.3, 1), box-shadow 0.3s ease;
}
.chart-card:hover, .detail-card:hover, .timeline-card:hover, .prescription-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1);
}
.card-title {
  font-size: 16px;
  font-weight: 600;
  margin: 0 0 16px 0;
  color: #303133;
  display: flex;
  align-items: center;
  gap: 8px;
}

/* ═══ 雷达模式切换 ═══ */
.radar-mode-switch {
  display: flex;
  justify-content: center;
  margin-bottom: 8px;
}

/* ═══ 图表容器 ═══ */
.chart-container {
  width: 100%;
}
.radar-chart {
  height: 350px;
}
.mini-radar {
  height: 200px;
}
.subject-deviation {
  height: 250px;
}

/* ═══ 五维对比 ═══ */
.dimension-comparison-grid {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.dimension-row {
  display: flex;
  align-items: center;
  gap: 12px;
}
.dim-label {
  font-size: 13px;
  font-weight: 600;
  width: 60px;
}
.dim-values {
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 6px;
  width: 140px;
}
.dim-academic { color: #3b82f6; font-weight: 600; }
.dim-behavior { color: #ef4444; font-weight: 600; }
.dim-separator { color: #999; font-size: 11px; }
.dim-delta { font-weight: 700; }
.delta-pos { color: #67c23a; }
.delta-neg { color: #f56c6c; }
.dim-bar-wrapper {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 3px;
  height: 16px;
}
.dim-bar {
  height: 6px;
  border-radius: 3px;
  transition: width 0.5s ease;
}

/* ═══ 时间轴 ═══ */
.timeline-filter {
  display: flex;
  justify-content: flex-start;
  margin-bottom: 8px;
}
.timeline-track {
  padding: 8px 0;
  position: relative;
  max-height: 500px;
  overflow-y: auto;
}
.date-divider {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 12px 0 8px 0;
  position: relative;
}
.date-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #409eff;
  flex-shrink: 0;
}
.date-text {
  font-size: 13px;
  font-weight: 600;
  color: #409eff;
}
.timeline-event {
  display: flex;
  gap: 12px;
  margin: 8px 0;
  transition: transform 0.2s ease;
}
.timeline-event:hover {
  transform: translateX(4px);
}
.event-node {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  flex-shrink: 0;
  margin-top: 8px;
}
.event-card {
  flex: 1;
  background: #fff;
  border-radius: 8px;
  padding: 10px 14px;
  box-shadow: 0 1px 6px rgba(0, 0, 0, 0.06);
  border-left: 3px solid transparent;
  transition: border-color 0.2s, box-shadow 0.2s;
}
.severity-danger .event-card { border-left-color: #f56c6c; }
.severity-warning .event-card { border-left-color: #e6a23c; }
.severity-success .event-card { border-left-color: #67c23a; }
.severity-info .event-card { border-left-color: #409eff; }
.timeline-event:hover .event-card {
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
}
.event-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}
.event-type-tag {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 4px;
  font-weight: 600;
}
.event-time {
  font-size: 11px;
  color: #999;
}
.event-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}
.event-desc {
  font-size: 12px;
  color: #666;
  margin-top: 4px;
  line-height: 1.5;
}
.timeline-empty {
  text-align: center;
  padding: 40px;
  color: #c0c4cc;
  font-size: 14px;
}

/* ═══ AI 处方 ═══ */
.prescription-summary {
  font-size: 13px;
  color: #666;
  line-height: 1.6;
  margin-bottom: 16px;
  padding: 12px;
  background: #f8f9fa;
  border-radius: 8px;
}
.breaker-tag {
  margin-left: 8px;
}
.measures-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.measure-card {
  background: #fff;
  border-radius: 10px;
  padding: 14px;
  display: flex;
  gap: 12px;
  box-shadow: 0 1px 8px rgba(0, 0, 0, 0.06);
  border: 1px solid transparent;
  transition: transform 0.2s, border-color 0.2s;
}
.measure-card:hover {
  transform: translateY(-2px);
}
.measure-danger { border-color: rgba(245, 108, 108, 0.3); }
.measure-warning { border-color: rgba(230, 162, 60, 0.3); }
.measure-success { border-color: rgba(103, 194, 58, 0.3); }
.measure-info { border-color: rgba(64, 158, 255, 0.3); }
.measure-icon-wrap {
  flex-shrink: 0;
  width: 40px;
  height: 40px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f0f2f5;
}
.measure-danger .measure-icon-wrap { background: rgba(245, 108, 108, 0.15); color: #f56c6c; }
.measure-warning .measure-icon-wrap { background: rgba(230, 162, 60, 0.15); color: #e6a23c; }
.measure-success .measure-icon-wrap { background: rgba(103, 194, 58, 0.15); color: #67c23a; }
.measure-info .measure-icon-wrap { background: rgba(64, 158, 255, 0.15); color: #409eff; }
.measure-body {
  flex: 1;
}
.measure-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}
.measure-category {
  font-size: 14px;
  font-weight: 600;
}
.measure-issue {
  font-size: 13px;
  color: #303133;
  margin-bottom: 6px;
  font-weight: 500;
}
.measure-actions {
  margin: 0;
  padding-left: 16px;
  font-size: 12px;
  color: #666;
  line-height: 1.6;
}
.prescription-empty {
  background: #fff;
  border-radius: 12px;
  padding: 20px;
  text-align: center;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
}
/* V2 处方三段式样式 */
.prescription-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #909399;
  margin-bottom: 8px;
  flex-wrap: wrap;
}
.prescription-meta .meta-student {
  font-weight: 600;
  color: #303133;
}
.prescription-meta .meta-divider {
  color: #c0c4cc;
}
.prescription-meta .meta-risk-tag {
  margin-left: 4px;
}
.prescription-segments {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-top: 12px;
}
.prescription-segment {
  background: #f9fafc;
  border-radius: 8px;
  padding: 12px 14px;
  border-left: 3px solid #409eff;
}
.segment-fact {
  border-left-color: #f56c6c;
}
.segment-analysis {
  border-left-color: #e6a23c;
}
.segment-growth {
  border-left-color: #67c23a;
}
.segment-label {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 6px;
  color: #303133;
}
.segment-content {
  font-size: 13px;
  line-height: 1.7;
  color: #606266;
}
.segment-content :deep(h4) {
  font-size: 13px;
  font-weight: 600;
  margin: 6px 0 4px;
  color: #303133;
}
.segment-content :deep(strong) {
  color: #303133;
}
.segment-content :deep(ul),
.segment-content :deep(ol) {
  margin: 4px 0;
  padding-left: 18px;
}
.segment-content :deep(li) {
  margin-bottom: 2px;
}
.prescription-loading {
  background: #fff;
  border-radius: 12px;
  padding: 20px;
  text-align: center;
  color: #409eff;
  font-size: 14px;
}

/* ═══ 空状态 ═══ */
.empty-state {
  text-align: center;
  padding: 80px 20px;
  color: #c0c4cc;
}
.empty-state p {
  font-size: 16px;
  margin-top: 16px;
}

/* ═══ 加载 ═══ */
.loading-overlay {
  position: fixed;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  z-index: 999;
  color: #409eff;
}

/* ═══ 响应式 ═══ */
@media (max-width: 900px) {
  .profile-body {
    grid-template-columns: 1fr;
  }
  .measures-grid {
    grid-template-columns: 1fr;
  }
  .student-header-card {
    flex-wrap: wrap;
  }
  .rdi-panel {
    width: 100%;
    padding: 12px 0 0 0;
  }
}
</style>
