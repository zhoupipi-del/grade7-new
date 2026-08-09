<template>
  <div class="grade-dashboard-container" v-loading="pageLoading">
    <!-- ═══ 顶层：考试选择器 + KPI 指标卡 ═══ -->
    <el-row :gutter="20" class="selector-row">
      <el-col :span="24">
        <div class="selector-bar">
          <div class="selector-left">
            <el-icon :size="22" class="section-icon"><DataLine /></el-icon>
            <span class="section-title">成绩看板</span>
            <el-tag v-if="currentExam" type="success" effect="dark" size="small">
              {{ examTypeLabel(currentExam.exam_type) }} · {{ currentExam.semester }}
            </el-tag>
          </div>
          <div class="selector-right">
            <el-select
              v-model="selectedExamId"
              placeholder="选择考试"
              size="default"
              style="width: 280px"
              @change="onExamChange"
            >
              <el-option
                v-for="exam in examList"
                :key="exam.id"
                :label="`${exam.name} (${examTypeLabel(exam.exam_type)})`"
                :value="exam.id"
              >
                <div style="display:flex; justify-content:space-between; align-items:center">
                  <span>{{ exam.name }}</span>
                  <el-tag size="small" :type="examStatusTag(exam.status)" effect="plain">
                    {{ examStatusLabel(exam.status) }}
                  </el-tag>
                </div>
              </el-option>
            </el-select>
            <el-select
              v-model="selectedClassId"
              placeholder="全部班级"
              clearable
              size="default"
              style="width: 160px"
              @change="onClassChange"
            >
              <el-option
                v-for="cls in classOptions"
                :key="cls.class_id"
                :label="cls.class_name"
                :value="cls.class_id"
              />
            </el-select>
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- ═══ KPI 四指标卡 ═══ -->
    <el-row :gutter="20" class="kpi-row">
      <el-col :span="6" v-for="kpi in kpiCards" :key="kpi.key">
        <el-card shadow="hover" class="kpi-card" :class="`kpi-${kpi.tone}`">
          <div class="kpi-body">
            <div class="kpi-icon">
              <el-icon :size="28"><component :is="ICON_MAP[kpi.icon]" /></el-icon>
            </div>
            <div class="kpi-content">
              <div class="kpi-value">{{ kpi.value }}<span class="kpi-unit">{{ kpi.unit }}</span></div>
              <div class="kpi-label">{{ kpi.label }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- ═══ 中层：12:12 分屏 — 各科均分柱状图 + 分数段分布 ═══ -->
    <el-row :gutter="20" class="chart-row">
      <el-col :span="12">
        <el-card shadow="never" class="panel-card">
          <template #header>
            <div class="card-header">
              <span class="panel-title">
                <el-icon><Histogram /></el-icon>
                各科均分对比
              </span>
            </div>
          </template>
          <div ref="subjectBarRef" class="echart-dom bar-chart"></div>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card shadow="never" class="panel-card">
          <template #header>
            <div class="card-header">
              <span class="panel-title">
                <el-icon><PieChart /></el-icon>
                分数段分布 (总分)
              </span>
            </div>
          </template>
          <div ref="distributionRef" class="echart-dom pie-chart"></div>
        </el-card>
      </el-col>
    </el-row>

    <!-- ═══ 班级对比汇总表 ═══ -->
    <el-row :gutter="20" class="summary-row">
      <el-col :span="24">
        <el-card shadow="never" class="panel-card">
          <template #header>
            <div class="card-header">
              <span class="panel-title">
                <el-icon><Grid /></el-icon>
                班级成绩对比汇总
              </span>
            </div>
          </template>
          <el-table :data="classSummaries" stripe style="width: 100%" size="default">
            <el-table-column prop="class_name" label="班级" width="120" fixed />
            <el-table-column prop="student_count" label="人数" width="80" align="center" />
            <el-table-column prop="avg_total" label="平均总分" width="120" align="center">
              <template #default="{ row }">
                <span class="score-bold">{{ row.avg_total ?? '--' }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="max_total" label="最高总分" width="110" align="center" />
            <el-table-column prop="min_total" label="最低总分" width="110" align="center" />
            <el-table-column prop="pass_rate" label="及格率" width="100" align="center">
              <template #default="{ row }">
                <el-tag :type="normalizePercent(row.pass_rate) >= 80 ? 'success' : normalizePercent(row.pass_rate) >= 60 ? 'warning' : 'danger'" effect="plain" size="small">
                  {{ normalizePercent(row.pass_rate).toFixed(1) }}%
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="excellent_rate" label="优秀率" width="100" align="center">
              <template #default="{ row }">
                <el-tag :type="normalizePercent(row.excellent_rate) >= 30 ? 'success' : 'info'" effect="plain" size="small">
                  {{ normalizePercent(row.excellent_rate).toFixed(1) }}%
                </el-tag>
              </template>
            </el-table-column>
            <!-- 各科均分列 -->
            <el-table-column
              v-for="sub in summarySubjects"
              :key="sub.subject_id"
              :label="sub.subject_name"
              width="100"
              align="center"
            >
              <template #default="{ row }">
                {{ getSubjectAvg(row as ClassScoreSummary, sub.subject_id) ?? '--' }}
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>

    <!-- ═══ 成绩明细表格 ═══ -->
    <el-row :gutter="20" class="table-row">
      <el-col :span="24">
        <el-card shadow="never" class="panel-card">
          <template #header>
            <div class="card-header">
              <span class="panel-title">
                <el-icon><List /></el-icon>
                成绩明细
              </span>
              <div class="table-controls">
                <el-input
                  v-model="searchName"
                  placeholder="搜索学生姓名"
                  clearable
                  size="small"
                  style="width: 180px"
                  @input="onSearchChange"
                >
                  <template #prefix>
                    <el-icon><Search /></el-icon>
                  </template>
                </el-input>
                <el-select
                  v-model="sortBy"
                  size="small"
                  style="width: 130px"
                  @change="onSortChange"
                >
                  <el-option
                    v-for="opt in sortOptions"
                    :key="opt.key"
                    :label="opt.label"
                    :value="opt.key"
                  />
                </el-select>
              </div>
            </div>
          </template>
          <el-table :data="studentResults" stripe style="width: 100%" size="small">
            <el-table-column prop="class_name" label="班级" width="100" fixed />
            <el-table-column prop="student_name" label="姓名" width="100" fixed />
            <el-table-column prop="total_score" label="总分" width="90" align="center" sortable>
              <template #default="{ row }">
                <span class="score-bold">{{ row.total_score ?? '--' }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="avg_score" label="均分" width="80" align="center" />
            <el-table-column prop="class_rank" label="班级排名" width="100" align="center">
              <template #default="{ row }">
                <el-tag v-if="row.class_rank" :type="row.class_rank <= 3 ? 'danger' : row.class_rank <= 10 ? 'warning' : 'info'" effect="plain" size="small">
                  {{ row.class_rank }}
                </el-tag>
                <span v-else>--</span>
              </template>
            </el-table-column>
            <el-table-column prop="grade_rank" label="年级排名" width="100" align="center">
              <template #default="{ row }">
                <el-tag v-if="row.grade_rank" :type="row.grade_rank <= 10 ? 'danger' : row.grade_rank <= 50 ? 'warning' : 'info'" effect="plain" size="small">
                  {{ row.grade_rank }}
                </el-tag>
                <span v-else>--</span>
              </template>
            </el-table-column>
            <!-- 各科成绩列 -->
            <el-table-column
              v-for="sub in tableSubjects"
              :key="sub.subject_id"
              :label="sub.subject_name"
              width="90"
              align="center"
            >
              <template #default="{ row }">
                <template v-if="getSubjectScore(row as StudentExamResult, sub.subject_id) !== null">
                  <el-tag :type="scoreTagType(getSubjectScore(row as StudentExamResult, sub.subject_id), sub.full_score)" effect="plain" size="small">
                    {{ getSubjectScore(row as StudentExamResult, sub.subject_id) }}
                  </el-tag>
                </template>
                <el-tag v-else type="info" effect="plain" size="small">缺考</el-tag>
              </template>
            </el-table-column>
          </el-table>

          <!-- 分页 -->
          <div class="pagination-wrap">
            <el-pagination
              v-model:current-page="currentPage"
              v-model:page-size="pageSize"
              :total="totalCount"
              :page-sizes="[20, 50, 100]"
              layout="total, sizes, prev, pager, next"
              @size-change="onPageChange"
              @current-change="onPageChange"
            />
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, nextTick, watch } from 'vue'
import * as echarts from 'echarts/core'
import {
  DataLine, Histogram, PieChart, Grid, List, Search,
  TrendCharts, CircleCheck, Warning, Trophy,
} from '@element-plus/icons-vue'
import {
  listExams,
  getExamResults,
  getDemoExams,
  getDemoExamResults,
  examTypeLabel,
  examStatusLabel,
  examStatusTag,
  scoreTagType,
  SUBJECT_COLORS,
  EXAM_TYPE_COLORS,
  SORT_BY_LABELS,
  type ExamItem,
  type ExamOut,
  type ExamResultPage,
  type ClassScoreSummary,
  type StudentExamResult,
  type StudentScoreOut,
} from '@/api/grades'

// ─── 图标映射 ──
const ICON_MAP: Record<string, any> = {
  TrendCharts,
  CircleCheck,
  Warning,
  Trophy,
}

// ─── 响应式数据 ────────────────────────────────────────
const pageLoading = ref(true)
const examList = ref<ExamItem[]>([])
const examResultPage = ref<ExamResultPage | null>(null)
const selectedExamId = ref<number | null>(null)
const selectedClassId = ref<number | null>(null)
const searchName = ref('')
const sortBy = ref('total_score_desc')
const currentPage = ref(1)
const pageSize = ref(50)

// ─── 排序选项列表 ──
const sortOptions = computed(() =>
  Object.entries(SORT_BY_LABELS).map(([key, label]) => ({ key, label }))
)

// ─── 计算属性 ──────────────────────────────────────────
const currentExam = computed<ExamOut | null>(() =>
  examResultPage.value?.exam ?? null
)

const classSummaries = computed<ClassScoreSummary[]>(() =>
  examResultPage.value?.class_summaries ?? []
)

const classOptions = computed(() =>
  classSummaries.value.map(c => ({ class_id: c.class_id, class_name: c.class_name }))
)

const studentResults = computed<StudentExamResult[]>(() =>
  examResultPage.value?.results ?? []
)

const totalCount = computed(() =>
  examResultPage.value?.total ?? 0
)

/** 班级汇总表中使用的科目列 (取第一个班级的subjects) */
const summarySubjects = computed(() =>
  classSummaries.value[0]?.subjects ?? []
)

/** 成绩明细表中使用的科目列 (取第一个学生的subjects) */
const tableSubjects = computed(() =>
  studentResults.value[0]?.subjects ?? []
)

// ─── KPI 指标卡 ──
const kpiCards = computed(() => {
  const summaries = classSummaries.value
  if (summaries.length === 0) return []

  const totalStudents = summaries.reduce((s, c) => s + c.student_count, 0)
  const avgTotal = summaries.reduce((s, c) => s + (c.avg_total ?? 0), 0) / summaries.length
  const passRate = summaries.reduce((s, c) => s + normalizePercent(c.pass_rate), 0) / summaries.length
  const excellentRate = summaries.reduce((s, c) => s + normalizePercent(c.excellent_rate), 0) / summaries.length

  return [
    { key: 'students', value: totalStudents, unit: '人', label: '参考人数', icon: 'TrendCharts', tone: 'primary' },
    { key: 'avg', value: avgTotal.toFixed(1), unit: '分', label: '年级均分', icon: 'CircleCheck', tone: 'success' },
    { key: 'pass', value: passRate.toFixed(1), unit: '%', label: '及格率', icon: 'Warning', tone: passRate >= 60 ? 'success' : 'warning' },
    { key: 'excellent', value: excellentRate.toFixed(1), unit: '%', label: '优秀率', icon: 'Trophy', tone: excellentRate >= 20 ? 'success' : 'primary' },
  ]
})

// ─── 辅助函数 ──
/** 百分比归一化：后端返回的 pass_rate/excellent_rate 可能是百分比(36.15)或小数(0.3615)，统一转为百分比数值 */
function normalizePercent(val: number | null): number {
  if (val === null) return 0
  // 值 > 1 说明后端已经乘了100，直接用；值 ≤ 1 说明是小数比例，乘100
  return val > 1 ? val : val * 100
}

function getSubjectAvg(row: ClassScoreSummary, subjectId: number): number | null {
  const sub = row.subjects.find(s => s.subject_id === subjectId)
  return sub?.avg_score ?? null
}

function getSubjectScore(row: StudentExamResult, subjectId: number): number | null {
  const sub = row.subjects.find(s => s.subject_id === subjectId)
  return sub?.score ?? null
}

// ─── ECharts 实例 ──────────────────────────────────────
const subjectBarRef = ref<HTMLDivElement | null>(null)
const distributionRef = ref<HTMLDivElement | null>(null)

let subjectBarChart: ReturnType<typeof echarts.init> | null = null
let distributionChart: ReturnType<typeof echarts.init> | null = null
let resizeObserver: ResizeObserver | null = null

// ─── 各科均分柱状图 ──
const initSubjectBarChart = () => {
  if (!subjectBarRef.value) return
  if (!subjectBarChart) {
    subjectBarChart = echarts.init(subjectBarRef.value)
  }

  const summaries = classSummaries.value
  if (summaries.length === 0) {
    subjectBarChart.setOption({ title: { text: '暂无数据', left: 'center', top: 'center', textStyle: { color: '#909399', fontSize: 16 } } }, true)
    return
  }

  // 多班级 → 多系列柱状图; 单班级 → 单系列
  const firstSubjects = summaries[0]?.subjects ?? []
  const categories = firstSubjects.map(s => s.subject_name)

  const series = summaries.map((cls, ci) => ({
    name: cls.class_name,
    type: 'bar',
    data: cls.subjects.map(s => s.avg_score ?? 0),
    itemStyle: {
      color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
        { offset: 0, color: SUBJECT_COLORS[ci % SUBJECT_COLORS.length] },
        { offset: 1, color: SUBJECT_COLORS[ci % SUBJECT_COLORS.length] + '80' },
      ]),
      borderRadius: [4, 4, 0, 0],
    },
    barMaxWidth: 40,
  }))

  const option: any = {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { show: summaries.length > 1, bottom: 0 },
    grid: { left: '3%', right: '4%', bottom: summaries.length > 1 ? '12%' : '6%', top: '8%', containLabel: true },
    xAxis: { type: 'category', data: categories, axisLabel: { color: '#606266' } },
    yAxis: { type: 'value', name: '均分', splitLine: { lineStyle: { type: 'dashed', color: '#e4e7ed' } }, axisLabel: { color: '#606266' } },
    series,
  }
  subjectBarChart.setOption(option, true)
}

// ─── 分数段饼图 ──
const initDistributionChart = () => {
  if (!distributionRef.value) return
  if (!distributionChart) {
    distributionChart = echarts.init(distributionRef.value)
  }

  const results = studentResults.value
  if (results.length === 0) {
    distributionChart.setOption({ title: { text: '暂无数据', left: 'center', top: 'center', textStyle: { color: '#909399', fontSize: 16 } } }, true)
    return
  }

  // 计算各分数段人数 (基于满分 700 = 7科×100)
  const totalFull = tableSubjects.value.reduce((s, sub) => s + sub.full_score, 0)
  // 安全守卫：如果 totalFull 为 0（无科目数据），使用默认满分 700
  const effectiveFull = totalFull > 0 ? totalFull : 700
  const segments = [
    { label: `优秀 (≥${(effectiveFull * 0.9).toFixed(0)})`, min: effectiveFull * 0.9, max: effectiveFull + 1, color: '#67c23a' },
    { label: `良好 (${(effectiveFull * 0.8).toFixed(0)}~${(effectiveFull * 0.9).toFixed(0)})`, min: effectiveFull * 0.8, max: effectiveFull * 0.9, color: '#409eff' },
    { label: `及格 (${(effectiveFull * 0.6).toFixed(0)}~${(effectiveFull * 0.8).toFixed(0)})`, min: effectiveFull * 0.6, max: effectiveFull * 0.8, color: '#e6a23c' },
    { label: `不及格 (<${(effectiveFull * 0.6).toFixed(0)})`, min: 0, max: effectiveFull * 0.6, color: '#f56c6c' },
  ]

  const data = segments.map(seg => ({
    name: seg.label,
    value: results.filter(r => r.total_score !== null && r.total_score >= seg.min && r.total_score < seg.max).length,
    itemStyle: { color: seg.color },
  }))

  const option: any = {
    tooltip: { trigger: 'item', formatter: '{b}: {c}人 ({d}%)' },
    legend: { orient: 'vertical', left: 'left', top: 'center', textStyle: { fontSize: 13 } },
    series: [{
      type: 'pie',
      radius: ['35%', '65%'],
      center: ['55%', '50%'],
      data,
      label: { formatter: '{b}\n{d}%', fontSize: 12 },
      emphasis: { itemStyle: { shadowBlur: 10, shadowOffsetX: 0, shadowColor: 'rgba(0, 0, 0, 0.2)' } },
    }],
  }
  distributionChart.setOption(option, true)
}

// ─── 数据加载 ──────────────────────────────────────────
const loadExamList = async () => {
  try {
    examList.value = await listExams()
  } catch {
    examList.value = getDemoExams()
  }
  // 默认选中第一场 published 考试
  const firstPublished = examList.value.find(e => e.status === 'published')
  if (firstPublished) {
    selectedExamId.value = firstPublished.id
  } else if (examList.value.length > 0) {
    selectedExamId.value = examList.value[0].id
  }
}

const loadExamResults = async () => {
  if (!selectedExamId.value) return

  try {
    examResultPage.value = await getExamResults({
      exam_id: selectedExamId.value,
      class_id: selectedClassId.value ?? undefined,
      student_name: searchName.value || undefined,
      sort_by: sortBy.value,
      page: currentPage.value,
      page_size: pageSize.value,
    })
  } catch {
    examResultPage.value = getDemoExamResults()
  }

  await nextTick()
  initSubjectBarChart()
  initDistributionChart()
}

// ─── 事件处理 ──
const onExamChange = () => {
  currentPage.value = 1
  selectedClassId.value = null
  loadExamResults()
}

const onClassChange = () => {
  currentPage.value = 1
  loadExamResults()
}

const onSearchChange = () => {
  currentPage.value = 1
  loadExamResults()
}

const onSortChange = () => {
  loadExamResults()
}

const onPageChange = () => {
  loadExamResults()
}

// ─── 生命周期 ──────────────────────────────────────────
onMounted(async () => {
  pageLoading.value = true
  try {
    await loadExamList()
    if (selectedExamId.value) {
      await loadExamResults()
    }

    resizeObserver = new ResizeObserver(() => {
      subjectBarChart?.resize()
      distributionChart?.resize()
    })
    if (subjectBarRef.value) resizeObserver.observe(subjectBarRef.value)
    if (distributionRef.value) resizeObserver.observe(distributionRef.value)
  } catch (err) {
    console.error('[GradeDashboard] onMounted error:', err)
  } finally {
    pageLoading.value = false
  }
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  resizeObserver = null
  subjectBarChart?.dispose()
  distributionChart?.dispose()
  subjectBarChart = null
  distributionChart = null
})
</script>

<style scoped>
.grade-dashboard-container {
  background-color: #f0f2f5;
  min-height: calc(100vh - 100px);
  padding: 4px;
}

/* ═══ 选择器栏 ═══ */
.selector-row {
  margin-bottom: 16px;
}

.selector-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: #fff;
  padding: 14px 20px;
  border-radius: 8px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.04);
}

.selector-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.section-icon {
  color: #409eff;
}

.section-title {
  font-size: 18px;
  font-weight: 600;
  color: #303133;
}

.selector-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

/* ═══ KPI 指标卡 ═══ */
.kpi-row {
  margin-bottom: 20px;
}

.kpi-card {
  border-radius: 8px;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.kpi-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.08);
}

.kpi-body {
  display: flex;
  align-items: center;
  gap: 16px;
}

.kpi-icon {
  width: 56px;
  height: 56px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.kpi-primary .kpi-icon { background: rgba(64, 158, 255, 0.12); color: #409eff; }
.kpi-success .kpi-icon { background: rgba(103, 194, 58, 0.12); color: #67c23a; }
.kpi-warning .kpi-icon { background: rgba(230, 162, 60, 0.12); color: #e6a23c; }

.kpi-content {
  flex: 1;
  min-width: 0;
}

.kpi-value {
  font-size: 28px;
  font-weight: 700;
  color: #303133;
  line-height: 1.2;
  font-family: 'DIN Alternate', 'Helvetica Neue', sans-serif;
}

.kpi-unit {
  font-size: 14px;
  font-weight: 500;
  color: #909399;
  margin-left: 4px;
}

.kpi-label {
  font-size: 13px;
  color: #606266;
  margin-top: 4px;
}

/* ═══ 面板卡 ═══ */
.chart-row,
.summary-row,
.table-row {
  margin-bottom: 20px;
}

.panel-card {
  border-radius: 8px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.panel-title {
  font-weight: 600;
  color: #303133;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.panel-title .el-icon {
  color: #409eff;
}

.table-controls {
  display: flex;
  align-items: center;
  gap: 10px;
}

/* ═══ ECharts ═══ */
.echart-dom {
  width: 100%;
}

.bar-chart {
  height: 380px;
}

.pie-chart {
  height: 380px;
}

/* ═══ 表格样式 ═══ */
.score-bold {
  font-weight: 600;
  color: #303133;
}

.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  padding: 16px 0 4px;
}
</style>
