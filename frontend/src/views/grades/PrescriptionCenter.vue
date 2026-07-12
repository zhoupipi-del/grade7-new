<template>
  <div class="rx-center" v-loading="pageLoading">
    <!-- ═══ 顶层：过滤器 + 统计 ═══ -->
    <div class="rx-top-bar">
      <div class="rx-title-row">
        <el-icon :size="24" class="rx-icon"><MagicStick /></el-icon>
        <span class="rx-title">AI 处方全景中心</span>
        <el-tag v-if="filters.examId" type="success" effect="dark" size="small">
          {{ currentExamName }}
        </el-tag>
        <el-tag type="warning" effect="plain" size="small">
          {{ totalCount }} 条处方 · {{ stats.studentCount }} 名学生 · {{ stats.subjectCount }} 科
        </el-tag>
      </div>
      <div class="rx-filters">
        <el-select
          v-model="filters.examId"
          placeholder="选择考试"
          size="default"
          style="width:240px"
          @change="onFilterChange"
        >
          <el-option
            v-for="e in examList"
            :key="e.id"
            :label="e.name"
            :value="e.id"
          />
        </el-select>
        <el-select
          v-model="filters.subjectCode"
          placeholder="全部学科"
          clearable
          size="default"
          style="width:130px"
          @change="onFilterChange"
        >
          <el-option
            v-for="s in subjectOptions"
            :key="s.code"
            :label="s.name"
            :value="s.code"
          />
        </el-select>
        <el-select
          v-model="filters.riskLevel"
          placeholder="全部等级"
          clearable
          size="default"
          style="width:120px"
          @change="onFilterChange"
        >
          <el-option label="🔴 红灯 (Z≤-1.5)" value="red" />
          <el-option label="🟡 黄灯 (-1.5<Z≤-1.0)" value="yellow" />
        </el-select>
        <el-input
          v-model="filters.studentName"
          placeholder="搜索学生姓名"
          clearable
          size="default"
          style="width:180px"
          @input="onSearchDebounce"
        >
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
      </div>
    </div>

    <!-- ═══ 提示信息 ═══ -->
    <el-alert
      v-if="totalCount === 0 && !pageLoading"
      title="暂无AI处方数据"
      type="info"
      :closable="false"
      show-icon
      style="margin-bottom:20px"
    >
      选择一场已发布成绩且有RDI预警的考试，或等待AI处方引擎生成完成。
    </el-alert>

    <!-- ═══ 处方卡片网格 ═══ -->
    <div class="rx-grid" v-if="totalCount > 0">
      <div
        v-for="rx in prescriptions"
        :key="rx.id"
        class="rx-card"
        :class="{ 'rx-expanded': expandedId === rx.id, [`rx-${rx.riskLabel}`]: true }"
        @click="toggleExpand(rx.id)"
      >
        <!-- 卡片头部 -->
        <div class="rx-card-header">
          <div class="rx-student-avatar" :style="{ background: avatarColor(rx.student_name) }">
            {{ rx.student_name?.charAt(0) || '?' }}
          </div>
          <div class="rx-card-info">
            <div class="rx-card-name">
              {{ rx.student_name }}
              <el-tag size="small" effect="plain">{{ rx.class_name }}</el-tag>
            </div>
            <div class="rx-card-meta">
              <span class="rx-subject-badge" :style="{ background: subjectColor(rx.subject_code), color: '#fff' }">
                {{ subjectLabel(rx.subject_code) }}
              </span>
              <span class="rx-score">得分 {{ rx.raw_score ?? '--' }}</span>
            </div>
          </div>
          <div class="rx-zscore-badge" :class="rx.riskLabel">
            <div class="rx-z-val">Z={{ formatZ(rx.z_score) }}</div>
            <div class="rx-z-bar">
              <div class="rx-z-fill" :style="{ width: zBarWidth(rx.z_score), background: zColor(rx.z_score) }"></div>
            </div>
          </div>
          <el-icon class="rx-expand-icon" :class="{ rotated: expandedId === rx.id }"><ArrowRight /></el-icon>
        </div>

        <!-- 展开详情 — 三维诊断 -->
        <transition name="rx-slide">
          <div v-if="expandedId === rx.id" class="rx-card-body">
            <!-- 学术诊断层 -->
            <div class="rx-seg" v-if="rx.weakness_analysis">
              <div class="rx-seg-header seg-academic">
                <el-icon><Notebook /></el-icon>
                <span>学术诊断</span>
              </div>
              <div class="rx-seg-content" v-html="renderMd(rx.weakness_analysis)"></div>
            </div>
            <!-- 行动处方层 -->
            <div class="rx-seg" v-if="rx.action_prescription">
              <div class="rx-seg-header seg-action">
                <el-icon><Guide /></el-icon>
                <span>干预处方</span>
              </div>
              <div class="rx-seg-content" v-html="renderMd(rx.action_prescription)"></div>
            </div>
            <!-- 习惯诊断层 V3 -->
            <div class="rx-seg" v-if="rx.habit_diagnosis">
              <div class="rx-seg-header seg-habit">
                <el-icon><Clock /></el-icon>
                <span>习惯诊断</span>
              </div>
              <div class="rx-seg-content">{{ rx.habit_diagnosis }}</div>
            </div>
            <!-- 分周计划层 V3 -->
            <div class="rx-seg" v-if="weeklyPlanItems(rx).length > 0">
              <div class="rx-seg-header seg-plan">
                <el-icon><Calendar /></el-icon>
                <span>分周行动计划</span>
              </div>
              <div class="rx-weekly-plan">
                <div
                  v-for="(week, wi) in weeklyPlanItems(rx)"
                  :key="wi"
                  class="rx-week-item"
                >
                  <el-tag size="small" type="primary" effect="dark" round>第{{ wi + 1 }}周</el-tag>
                  <ul class="rx-week-tasks">
                    <li v-for="(task, ti) in week.tasks || [week]" :key="ti">{{ typeof task === 'string' ? task : task.task || task }}</li>
                  </ul>
                </div>
              </div>
            </div>
            <!-- 情绪锚点 V3 -->
            <div class="rx-seg" v-if="rx.emotion_anchor">
              <div class="rx-seg-header seg-emotion">
                <el-icon><Sunny /></el-icon>
                <span>情绪激励</span>
              </div>
              <div class="rx-seg-content rx-emotion-text">{{ rx.emotion_anchor }}</div>
            </div>
            <!-- 家长指南 V3 -->
            <div class="rx-seg" v-if="rx.parent_guide">
              <div class="rx-seg-header seg-parent">
                <el-icon><HomeFilled /></el-icon>
                <span>家长配合指南</span>
              </div>
              <div class="rx-seg-content">{{ rx.parent_guide }}</div>
            </div>
          </div>
        </transition>
      </div>
    </div>

    <!-- 分页 -->
    <div class="rx-pagination" v-if="totalCount > 0">
      <el-pagination
        v-model:current-page="filters.page"
        v-model:page-size="filters.pageSize"
        :total="totalCount"
        :page-sizes="[12, 24, 48]"
        layout="total, sizes, prev, pager, next"
        @size-change="onFilterChange"
        @current-change="onFilterChange"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, watch } from 'vue'
import {
  MagicStick, Search, Notebook, Guide, Clock, Calendar, Sunny, HomeFilled, ArrowRight,
} from '@element-plus/icons-vue'
import { listExams, type ExamItem } from '@/api/grades'
import request from '@/api/request'

// ─── 类型 ──────────────────────────
interface PrescriptionV3 {
  id: number
  alert_id: number
  student_id: number
  student_name: string
  class_name: string
  subject_code: string
  raw_score: number | null
  scaled_score: number | null
  z_score: number | null
  weakness_analysis: string
  action_prescription: string
  habit_diagnosis: string
  emotion_anchor: string
  weekly_plan_json: any
  parent_guide: string
  model_metadata: any
  created_at: string | null
  riskLabel?: string
}

interface RxPage {
  status: string
  total: number
  page: number
  page_size: number
  prescriptions: PrescriptionV3[]
}

// ─── 响应式数据 ────────────────────
const pageLoading = ref(true)
const examList = ref<ExamItem[]>([])
const prescriptions = ref<PrescriptionV3[]>([])
const totalCount = ref(0)
const expandedId = ref<number | null>(null)
let searchTimer: ReturnType<typeof setTimeout> | null = null

const filters = reactive({
  examId: null as number | null,
  subjectCode: null as string | null,
  riskLevel: null as string | null,
  studentName: '',
  page: 1,
  pageSize: 12,
})

const stats = reactive({
  studentCount: 0,
  subjectCount: 0,
})

// ─── 科目映射 ──────────────────────
const SUBJECT_MAP: Record<string, string> = {
  chinese: '语文', math: '数学', english: '英语',
  physics: '物理', chemistry: '化学', biology: '生物',
  history: '历史', geography: '地理', politics: '政治',
  pe: '体育', art: '美术', music: '音乐',
}

const SUBJECT_OPTIONS = Object.entries(SUBJECT_MAP).map(([code, name]) => ({ code, name }))

const SUBJECT_COLORS: Record<string, string> = {
  chinese: '#ef4444', math: '#3b82f6', english: '#10b981',
  physics: '#ec4899', biology: '#14b8a6', chemistry: '#8b5cf6',
  history: '#f59e0b', geography: '#84cc16', politics: '#f97316',
}

const subjectOptions = SUBJECT_OPTIONS
const subjectLabel = (code: string) => SUBJECT_MAP[code] || code
const subjectColor = (code: string) => SUBJECT_COLORS[code] || '#64748b'

// ─── 计算属性 ──────────────────────
const currentExamName = (() => {
  const e = examList.value.find(x => x.id === filters.examId)
  return e?.name || ''
})()

// ─── 辅助函数 ──────────────────────
function formatZ(z: number | null): string {
  if (z === null || z === undefined) return '--'
  return z.toFixed(2)
}

function zColor(z: number | null): string {
  if (z === null) return '#909399'
  if (z <= -1.5) return '#f56c6c'
  if (z <= -1.0) return '#e6a23c'
  return '#67c23a'
}

function zBarWidth(z: number | null): string {
  if (z === null) return '0%'
  const pct = Math.min(Math.abs(z) / 4 * 100, 100)
  return `${pct}%`
}

function avatarColor(name: string): string {
  const colors = ['#409eff', '#67c23a', '#e6a23c', '#f56c6c', '#8b5cf6', '#14b8a6', '#ec4899', '#f97316']
  let hash = 0
  for (let i = 0; i < (name || '').length; i++) hash = name.charCodeAt(i) + ((hash << 5) - hash)
  return colors[Math.abs(hash) % colors.length]
}

function weeklyPlanItems(rx: PrescriptionV3): any[] {
  if (!rx.weekly_plan_json) return []
  try {
    const plan = typeof rx.weekly_plan_json === 'string'
      ? JSON.parse(rx.weekly_plan_json)
      : rx.weekly_plan_json
    return Array.isArray(plan) ? plan : []
  } catch { return [] }
}

function renderMd(text: string): string {
  if (!text) return ''
  let html = text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n\n/g, '</p><p>')
    .replace(/\n/g, '<br>')
  html = `<p>${html}</p>`
  return html
}

// ─── 数据加载 ──────────────────────
async function loadExamList() {
  try {
    examList.value = await listExams()
  } catch { /* keep empty */ }
  // 默认选中第一场 published 考试
  const first = examList.value.find(e => e.status === 'published')
  if (first) filters.examId = first.id
}

async function loadPrescriptions() {
  if (!filters.examId) return
  pageLoading.value = true
  try {
    const params: any = {
      exam_id: filters.examId,
      page: filters.page,
      page_size: filters.pageSize,
    }
    if (filters.subjectCode) params.subject_code = filters.subjectCode
    if (filters.riskLevel) params.risk_level = filters.riskLevel
    if (filters.studentName) params.student_name = filters.studentName

    const res = await request.get<any, RxPage>('/data_adapter/prescriptions', { params })
    totalCount.value = res.total

    // 附上 riskLabel
    const rxList = res.prescriptions.map(p => ({
      ...p,
      riskLabel: (p.z_score !== null && p.z_score <= -1.5) ? 'red'
        : (p.z_score !== null && p.z_score <= -1.0) ? 'yellow' : 'green',
    }))
    prescriptions.value = rxList

    // 统计
    stats.studentCount = new Set(rxList.map(p => p.student_id)).size
    stats.subjectCount = new Set(rxList.map(p => p.subject_code)).size
  } catch {
    prescriptions.value = []
    totalCount.value = 0
  } finally {
    pageLoading.value = false
  }
}

// ─── 事件处理 ──────────────────────
function onFilterChange() {
  filters.page = 1
  expandedId.value = null
  loadPrescriptions()
}

function onSearchDebounce() {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => onFilterChange(), 400)
}

function toggleExpand(id: number) {
  expandedId.value = expandedId.value === id ? null : id
}

// ─── 生命周期 ──────────────────────
onMounted(async () => {
  await loadExamList()
  if (filters.examId) await loadPrescriptions()
})
</script>

<style scoped>
.rx-center {
  background: #f5f7fa;
  min-height: calc(100vh - 100px);
  padding: 16px;
}

/* ═══ 顶部栏 ═══ */
.rx-top-bar {
  background: #fff;
  border-radius: 10px;
  padding: 18px 22px;
  margin-bottom: 20px;
  box-shadow: 0 1px 6px rgba(0,0,0,0.04);
}

.rx-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 14px;
}

.rx-icon {
  color: #8b5cf6;
}

.rx-title {
  font-size: 20px;
  font-weight: 700;
  color: #303133;
}

.rx-filters {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

/* ═══ 处方卡片网格 ═══ */
.rx-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
  gap: 14px;
  margin-bottom: 20px;
}

.rx-card {
  background: #fff;
  border-radius: 10px;
  border-left: 4px solid #909399;
  box-shadow: 0 1px 6px rgba(0,0,0,0.04);
  cursor: pointer;
  transition: all 0.2s ease;
}

.rx-card:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 16px rgba(0,0,0,0.08);
}

.rx-card.rx-red { border-left-color: #f56c6c; }
.rx-card.rx-yellow { border-left-color: #e6a23c; }
.rx-card.rx-green { border-left-color: #67c23a; }

.rx-card-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
}

.rx-student-avatar {
  width: 40px; height: 40px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 16px;
  font-weight: 700;
  flex-shrink: 0;
}

.rx-card-info {
  flex: 1;
  min-width: 0;
}

.rx-card-name {
  font-weight: 600;
  font-size: 15px;
  color: #303133;
  display: flex;
  align-items: center;
  gap: 6px;
}

.rx-card-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
}

.rx-subject-badge {
  font-size: 12px;
  padding: 1px 8px;
  border-radius: 4px;
  font-weight: 500;
}

.rx-score {
  font-size: 13px;
  color: #909399;
}

.rx-zscore-badge {
  text-align: center;
  min-width: 80px;
}

.rx-z-val {
  font-family: 'DIN Alternate', monospace;
  font-size: 18px;
  font-weight: 700;
}

.rx-red .rx-z-val { color: #f56c6c; }
.rx-yellow .rx-z-val { color: #e6a23c; }
.rx-green .rx-z-val { color: #67c23a; }

.rx-z-bar {
  height: 4px;
  background: #e4e7ed;
  border-radius: 2px;
  margin-top: 4px;
  overflow: hidden;
}

.rx-z-fill {
  height: 100%;
  border-radius: 2px;
  transition: width 0.3s;
}

.rx-expand-icon {
  color: #c0c4cc;
  transition: transform 0.2s;
}
.rx-expand-icon.rotated { transform: rotate(90deg); }

/* ═══ 展开详情 ═══ */
.rx-card-body {
  border-top: 1px solid #f0f0f0;
  padding: 14px 16px 16px;
}

.rx-seg {
  margin-bottom: 14px;
}
.rx-seg:last-child { margin-bottom: 0; }

.rx-seg-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
  font-size: 13px;
  margin-bottom: 8px;
  padding: 6px 10px;
  border-radius: 6px;
}

.seg-academic { background: rgba(64,158,255,0.08); color: #409eff; }
.seg-action { background: rgba(139,92,246,0.08); color: #8b5cf6; }
.seg-habit { background: rgba(230,162,60,0.08); color: #e6a23c; }
.seg-plan { background: rgba(103,194,58,0.08); color: #67c23a; }
.seg-emotion { background: rgba(236,72,153,0.08); color: #ec4899; }
.seg-parent { background: rgba(20,184,166,0.08); color: #14b8a6; }

.rx-seg-content {
  font-size: 13px;
  color: #606266;
  line-height: 1.7;
  padding: 0 4px;
}

.rx-emotion-text {
  font-style: italic;
  color: #ec4899;
  font-size: 14px;
  padding: 8px 12px;
  background: rgba(236,72,153,0.04);
  border-radius: 6px;
}

.rx-weekly-plan {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 4px;
}

.rx-week-item {
  padding: 8px 12px;
  background: #f8faf8;
  border-radius: 8px;
}

.rx-week-tasks {
  margin: 6px 0 0 0;
  padding-left: 20px;
  font-size: 13px;
  color: #606266;
}

.rx-week-tasks li {
  margin-bottom: 4px;
  line-height: 1.5;
}

/* ═══ 分页 ═══ */
.rx-pagination {
  display: flex;
  justify-content: center;
  padding: 20px 0;
}

/* ═══ Slide transition ═══ */
.rx-slide-enter-active,
.rx-slide-leave-active {
  transition: all 0.25s ease;
  overflow: hidden;
}
.rx-slide-enter-from,
.rx-slide-leave-to {
  opacity: 0;
  max-height: 0;
}
.rx-slide-enter-to,
.rx-slide-leave-from {
  opacity: 1;
  max-height: 2000px;
}

/* ═══ Rendered markdown ═══ */
.rx-seg-content :deep(strong) { color: #303133; }
.rx-seg-content :deep(p) { margin: 4px 0; }
</style>
