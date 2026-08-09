<template>
  <div class="student-radar-container">
    <!-- ═══ 顶部筛选栏 ═══ -->
    <el-card shadow="never" class="filter-bar">
      <el-row :gutter="16" align="middle">
        <el-col :span="5">
          <el-select v-model="selectedClassId" placeholder="选择班级" clearable @change="onClassChange">
            <el-option v-for="c in classList" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
        </el-col>
        <el-col :span="5">
          <el-select
            v-model="selectedStudentId"
            placeholder="选择学生"
            filterable
            :disabled="!selectedClassId"
            @change="onStudentChange"
          >
            <el-option
              v-for="s in studentList"
              :key="s.student_id"
              :label="`${s.name} (${s.class_name})`"
              :value="s.student_id"
            />
          </el-select>
        </el-col>
        <el-col :span="5">
          <el-select v-model="selectedExamId" placeholder="选择考试" @change="onExamChange">
            <el-option v-for="e in examList" :key="e.id" :label="e.name" :value="e.id" />
          </el-select>
        </el-col>
        <el-col :span="4">
          <el-tag v-if="currentStudent" :type="studentRiskTag" effect="dark" size="large">
            RDI {{ currentRdi.toFixed(1) }} — {{ currentRiskLabel }}
          </el-tag>
          <el-tag v-else type="info" effect="plain" size="large">未选中学生</el-tag>
        </el-col>
        <el-col :span="5" style="text-align: right">
          <el-button-group>
            <el-button :type="radarMode === 'overlay' ? 'primary' : 'default'" size="small" @click="radarMode = 'overlay'">
              双模态叠加
            </el-button>
            <el-button :type="radarMode === 'academic' ? 'primary' : 'default'" size="small" @click="radarMode = 'academic'">
              仅学业
            </el-button>
            <el-button :type="radarMode === 'behavior' ? 'primary' : 'default'" size="small" @click="radarMode = 'behavior'">
              仅行为
            </el-button>
          </el-button-group>
        </el-col>
      </el-row>
    </el-card>

    <!-- ═══ 主体：双模态雷达 ═══ -->
    <el-row :gutter="20" style="margin-top: 16px">
      <!-- 左侧：雷达主图 -->
      <el-col :span="15">
        <el-card shadow="never" class="radar-card">
          <template #header>
            <div class="card-header">
              <span class="title">{{ radarTitle }}</span>
              <div class="legend-group">
                <span class="legend-item" style="color: #3b82f6">● 学业成绩</span>
                <span v-if="radarMode !== 'academic'" class="legend-item" style="color: #ef4444">● 行为评价</span>
              </div>
            </div>
          </template>

          <div v-if="currentStudent" ref="radarChartRef" class="echart-dom"></div>
          <el-empty v-else description="请选择班级和学生，查看双模态全息雷达" />
        </el-card>
      </el-col>

      <!-- 右侧：维度对比详情 + 学业雷达 -->
      <el-col :span="9">
        <!-- 维度对比卡片 -->
        <el-card shadow="never" class="dimension-card" v-if="currentStudent">
          <template #header>
            <span class="title">五维对比明细</span>
          </template>
          <div class="dimension-list">
            <div
              v-for="dim in dimensionDetails"
              :key="dim.key"
              class="dim-row"
            >
              <div class="dim-label">
                <span class="dim-dot" :style="{ backgroundColor: dim.evalColor }"></span>
                {{ dim.label }}
              </div>
              <div class="dim-scores">
                <div class="score-item academic">
                  <span class="score-label">学业</span>
                  <span class="score-value">{{ dim.academicScore ?? '--' }}</span>
                </div>
                <div class="score-item behavior">
                  <span class="score-label">行为</span>
                  <span class="score-value">{{ dim.behaviorScore ?? '--' }}</span>
                </div>
                <div class="score-item delta">
                  <span class="score-label">Δ</span>
                  <span
                    class="score-value"
                    :style="{ color: (dim.delta ?? 0) >= 0 ? '#10b981' : '#ef4444' }"
                  >
                    {{ dim.delta !== null ? (dim.delta >= 0 ? '+' : '') + dim.delta.toFixed(1) : '--' }}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </el-card>

        <!-- RDI 偏离度迷你雷达 -->
        <el-card shadow="never" class="mini-radar-card" v-if="currentStudent && rdiData" style="margin-top: 16px">
          <template #header>
            <span class="title">RDI 三维偏离度</span>
          </template>
          <div ref="miniRadarRef" class="mini-echart-dom"></div>
        </el-card>

        <!-- 学业各科柱状图 -->
        <el-card shadow="never" class="subject-bar-card" v-if="currentStudent && academicData" style="margin-top: 16px">
          <template #header>
            <span class="title">各科成绩偏离年级均值</span>
          </template>
          <div ref="subjectDevRef" class="mini-echart-dom"></div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts/core'
import {
  listExams, getExamResults, getDemoExams, getDemoExamResults,
  type ExamItem, type ExamResultPage, type StudentExamResult, type StudentScoreOut,
  SUBJECT_COLORS,
} from '@/api/grades'
import {
  getStudentScores, getDemoStudentScores,
  type EvalDimension, DIMENSION_LABELS, DIMENSION_COLORS, type StudentScoreOut as EvalStudentScoreOut,
} from '@/api/evaluation'
import {
  getHighRiskStudents, type StudentRiskRecord, type RDIDiagnosis,
} from '@/api/rdi'
import { useUserStore } from '@/store/user'

// ═══ 状态变量 ═══

const userStore = useUserStore()
const selectedClassId = ref<number | null>(null)
const selectedStudentId = ref<number | null>(null)
const selectedExamId = ref<number | null>(null)
const radarMode = ref<'overlay' | 'academic' | 'behavior'>('overlay')

// 数据缓存
const classList = ref<{ id: number; name: string }[]>([])
const studentList = ref<{ student_id: number; name: string; class_name: string }[]>([])
const examList = ref<ExamItem[]>([])
const examResultPage = ref<ExamResultPage | null>(null)
const evalScores = ref<EvalStudentScoreOut | null>(null)
const rdiRecords = ref<StudentRiskRecord[]>([])
const currentRdi = ref(0)

// ECharts refs
const radarChartRef = ref<HTMLDivElement | null>(null)
const miniRadarRef = ref<HTMLDivElement | null>(null)
const subjectDevRef = ref<HTMLDivElement | null>(null)

let radarInstance: ReturnType<typeof echarts.init> | null = null
let miniRadarInstance: ReturnType<typeof echarts.init> | null = null
let subjectDevInstance: ReturnType<typeof echarts.init> | null = null
let resizeObserver: ResizeObserver | null = null

// ═══ 维度映射 ═══
// 中文科目名 → 英文代码 反向映射 (API 返回 subject_name 是中文，但 SUBJECT_DIMENSION_MAP key 是英文)
const SUBJECT_NAME_TO_CODE: Record<string, string> = {
  '语文': 'chinese', '数学': 'math', '英语': 'english',
  '政治': 'politics', '历史': 'history', '地理': 'geography',
  '生物': 'biology', '物理': 'physics', '化学': 'chemistry',
  '体育': 'pe', '美术': 'art', '音乐': 'music',
}

// 学业科目 → 评价维度 的映射 (双模态融合的核心)
const SUBJECT_DIMENSION_MAP: Record<string, EvalDimension> = {
  chinese: 'moral',      // 语文 → 道德品质
  math: 'academic',      // 数学 → 学业水平
  english: 'social',     // 英语 → 社会实践
  politics: 'moral',     // 政治 → 道德品质
  history: 'social',     // 历史 → 社会实践
  geography: 'social',   // 地理 → 社会实践
  biology: 'health',     // 生物 → 身心健康
  physics: 'academic',   // 物理 → 学业水平
  chemistry: 'academic', // 化学 → 学业水平
  pe: 'health',          // 体育 → 身心健康
  art: 'art',            // 美术 → 艺术素养
  music: 'art',          // 音乐 → 艺术素养
}

// 评价五维的科目权重映射 (当多个科目映射到同一维度时取平均)
const DIMENSION_SUBJECTS: Record<EvalDimension, string[]> = {
  moral: ['chinese', 'politics'],
  academic: ['math', 'physics', 'chemistry'],
  health: ['biology', 'pe'],
  art: ['art', 'music'],
  social: ['english', 'history', 'geography'],
}

// ═══ 计算属性 ═══

const currentStudent = computed(() => {
  if (!selectedStudentId.value || !examResultPage.value) return null
  return examResultPage.value.results.find(s => s.student_id === selectedStudentId.value)
})

const academicData = computed(() => currentStudent.value)

const behaviorData = computed(() => evalScores.value)

const rdiData = computed(() => {
  if (!selectedStudentId.value) return null
  return rdiRecords.value.find(r => r.student_id === selectedStudentId.value)
})

const currentRiskLabel = computed(() => {
  if (currentRdi.value >= 6) return '干预'
  if (currentRdi.value >= 3) return '预警'
  return '正常'
})

const studentRiskTag = computed(() => {
  if (currentRdi.value >= 6) return 'danger'
  if (currentRdi.value >= 3) return 'warning'
  return 'success'
})

const radarTitle = computed(() => {
  if (!currentStudent.value) return '双模态全息雷达'
  const name = currentStudent.value.student_name
  if (radarMode.value === 'overlay') return `${name} — 学业×行为 双模态雷达`
  if (radarMode.value === 'academic') return `${name} — 学业偏离雷达`
  return `${name} — 行为评价雷达`
})

// 五维对比明细
const dimensionDetails = computed(() => {
  const dims: EvalDimension[] = ['moral', 'academic', 'health', 'art', 'social']

  // 计算学业映射分 (各科目成绩按满分百分比映射到维度，维度内多科目取平均)
  const academicDimScores: Record<string, number | null> = {}
  if (academicData.value?.subjects) {
    const dimScoresMap: Record<string, number[]> = {}
    for (const sub of academicData.value.subjects) {
      // 用中文科目名→英文代码反向映射，再查 SUBJECT_DIMENSION_MAP
      const code = SUBJECT_NAME_TO_CODE[sub.subject_name] ?? sub.subject_name.toLowerCase()
      const dim = SUBJECT_DIMENSION_MAP[code] ?? 'academic' // fallback
      if (sub.score !== null) {
        const pct = (sub.score / sub.full_score) * 100 // 归一化到100分制
        if (!dimScoresMap[dim]) dimScoresMap[dim] = []
        dimScoresMap[dim].push(pct)
      }
    }
    for (const dim of dims) {
      const arr = dimScoresMap[dim]
      academicDimScores[dim] = arr && arr.length > 0
        ? Number((arr.reduce((a, b) => a + b, 0) / arr.length).toFixed(1))
        : null
    }
  }

  // 行为评价分 (直接从 evaluation API)
  const behaviorDimScores: Record<string, number | null> = {}
  if (behaviorData.value) {
    behaviorDimScores.moral = behaviorData.value.moral_score
    behaviorDimScores.academic = behaviorData.value.academic_score
    behaviorDimScores.health = behaviorData.value.health_score
    behaviorDimScores.art = behaviorData.value.art_score
    behaviorDimScores.social = behaviorData.value.social_score
  }

  return dims.map(dim => {
    const aScore = academicDimScores[dim]
    const bScore = behaviorDimScores[dim]
    const delta = aScore !== null && bScore !== null ? aScore - bScore : null
    return {
      key: dim,
      label: DIMENSION_LABELS[dim],
      evalColor: DIMENSION_COLORS[dim],
      academicScore: aScore,
      behaviorScore: bScore,
      delta,
    }
  })
})

// ═══ 数据加载 ═══

const loadExamList = async () => {
  try {
    examList.value = await listExams()
  } catch {
    examList.value = getDemoExams()
  }
  if (examList.value.length > 0 && !selectedExamId.value) {
    selectedExamId.value = examList.value[0].id
  }
}

const loadExamResults = async () => {
  if (!selectedExamId.value) return
  try {
    examResultPage.value = await getExamResults({
      exam_id: selectedExamId.value,
      class_id: selectedClassId.value ?? undefined,
      page: 1,
      page_size: 100,
    })
  } catch {
    examResultPage.value = getDemoExamResults()
  }
  // 从结果中提取班级和学生列表
  extractClassAndStudents()
}

const loadEvalScores = async () => {
  if (!selectedStudentId.value) return
  try {
    evalScores.value = await getStudentScores(selectedStudentId.value)
  } catch {
    evalScores.value = getDemoStudentScores(selectedStudentId.value)
  }
}

const loadRdiRecords = async () => {
  try {
    const params: { class_id?: number } = {}
    if (selectedClassId.value) params.class_id = selectedClassId.value
    rdiRecords.value = await getHighRiskStudents(params)
  } catch {
    rdiRecords.value = []
  }
  // 更新当前学生的 RDI
  updateCurrentRdi()
}

const extractClassAndStudents = () => {
  if (!examResultPage.value) return
  // 从结果提取班级列表
  const classMap = new Map<number, string>()
  const studentArr: { student_id: number; name: string; class_name: string }[] = []

  for (const r of examResultPage.value.results) {
    if (!classMap.has(r.class_id)) classMap.set(r.class_id, r.class_name)
    studentArr.push({
      student_id: r.student_id,
      name: r.student_name,
      class_name: r.class_name,
    })
  }

  classList.value = Array.from(classMap, ([id, name]) => ({ id, name }))
  studentList.value = studentArr
}

const updateCurrentRdi = () => {
  if (!selectedStudentId.value) { currentRdi.value = 0; return }
  const record = rdiRecords.value.find(r => r.student_id === selectedStudentId.value)
  currentRdi.value = record ? record.rdi_score : 0
}

// ═══ 事件处理 ═══

const onClassChange = async () => {
  selectedStudentId.value = null
  await loadExamResults()
  await loadRdiRecords()
}

const onStudentChange = async () => {
  await loadEvalScores()
  updateCurrentRdi()
  await nextTick()
  renderAllCharts()
}

const onExamChange = async () => {
  await loadExamResults()
  await loadRdiRecords()
  // 如果之前选了学生，重新加载
  if (selectedStudentId.value) {
    await loadEvalScores()
  }
  await nextTick()
  renderAllCharts()
}

// ═══ 图表渲染 ═══

const renderAllCharts = () => {
  initDualRadar()
  initMiniRadar()
  initSubjectDeviation()
}

const initDualRadar = () => {
  if (!radarChartRef.value || !currentStudent.value) return
  if (!radarInstance) {
    radarInstance = echarts.init(radarChartRef.value)
  }

  const dims: EvalDimension[] = ['moral', 'academic', 'health', 'art', 'social']
  const indicators = dims.map(dim => ({
    name: DIMENSION_LABELS[dim],
    max: 100,
  }))

  // 学业映射数据
  const academicValues = dimensionDetails.value.map(d => d.academicScore ?? 0)
  // 行为评价数据
  const behaviorValues = dimensionDetails.value.map(d => d.behaviorScore ?? 0)

  const series: any[] = []

  if (radarMode.value === 'overlay' || radarMode.value === 'academic') {
    series.push({
      value: academicValues,
      name: '学业成绩',
      areaStyle: {
        color: 'rgba(59, 130, 246, 0.25)',
      },
      lineStyle: { color: '#3b82f6', width: 2 },
      itemStyle: { color: '#3b82f6' },
      symbol: 'circle',
      symbolSize: 6,
    })
  }

  if (radarMode.value === 'overlay' || radarMode.value === 'behavior') {
    series.push({
      value: behaviorValues,
      name: '行为评价',
      areaStyle: {
        color: 'rgba(239, 68, 68, 0.15)',
      },
      lineStyle: { color: '#ef4444', width: 2 },
      itemStyle: { color: '#ef4444' },
      symbol: 'diamond',
      symbolSize: 6,
    })
  }

  const option: any = {
    tooltip: {
      trigger: 'item',
      formatter: (params: any) => {
        const idx = params.dataIndex // 0=学业 or 1=行为
        const vals = params.value
        const source = idx === 0 ? '学业' : '行为'
        let html = `<div style="font-weight:600;margin-bottom:4px">${currentStudent.value!.student_name} (${source})</div>`
        dims.forEach((dim, i) => {
          html += `<div>${DIMENSION_LABELS[dim]}: ${vals[i]?.toFixed(1)}</div>`
        })
        return html
      },
    },
    legend: {
      data: radarMode.value === 'overlay' ? ['学业成绩', '行为评价'] : [radarMode.value === 'academic' ? '学业成绩' : '行为评价'],
      bottom: 10,
    },
    radar: {
      indicator: indicators,
      shape: 'polygon',
      splitNumber: 5,
      axisName: {
        color: '#606266',
        fontSize: 13,
        fontWeight: 500,
      },
      splitArea: {
        areaStyle: {
          color: ['#f5f7fa', '#ebedf0', '#e4e7ed', '#dcdfe6', '#d3d6db'],
        },
      },
      splitLine: { lineStyle: { color: '#e4e7ed' } },
      axisLine: { lineStyle: { color: '#dcdfe6' } },
    },
    series: [{
      type: 'radar',
      data: series,
      emphasis: {
        lineStyle: { width: 4 },
      },
    }],
  }

  radarInstance.setOption(option, true)
}

const initMiniRadar = () => {
  if (!miniRadarRef.value || !rdiData.value) return
  if (!miniRadarInstance) {
    miniRadarInstance = echarts.init(miniRadarRef.value)
  }

  const diag = rdiData.value.diagnosis
  const isIntervention = rdiData.value.risk_level === '干预'
  const areaColor = isIntervention ? 'rgba(245, 108, 108, 0.3)' : 'rgba(230, 162, 60, 0.3)'
  const lineColor = isIntervention ? '#f56c6c' : '#e6a23c'

  const option: any = {
    tooltip: {
      trigger: 'item',
      formatter: (params: any) => {
        const v = params.value
        return `<div style="font-weight:600">${rdiData.value!.name}</div>
          <div>行为偏离: ${v[0]?.toFixed(2)}σ</div>
          <div>考勤偏离: ${v[1]?.toFixed(2)}σ</div>
          <div>学业偏离: ${v[2]?.toFixed(2)}σ</div>`
      },
    },
    radar: {
      indicator: [
        { name: '行为偏离度', max: 10 },
        { name: '考勤偏离度', max: 10 },
        { name: '学业偏离度', max: 10 },
      ],
      shape: 'polygon',
      splitArea: { show: false },
      axisLine: { lineStyle: { color: '#dcdfe6' } },
      splitLine: { lineStyle: { color: '#e4e7ed' } },
      axisName: { color: '#606266', fontSize: 11 },
    },
    series: [{
      type: 'radar',
      data: [{
        value: [diag.behavior_deviation, diag.attendance_deviation, diag.score_deviation],
        name: rdiData.value.name,
        areaStyle: { color: areaColor },
        lineStyle: { color: lineColor, width: 2 },
        itemStyle: { color: lineColor },
      }],
    }],
  }

  miniRadarInstance.setOption(option, true)
}

const initSubjectDeviation = () => {
  if (!subjectDevRef.value || !academicData.value) return
  if (!subjectDevInstance) {
    subjectDevInstance = echarts.init(subjectDevRef.value)
  }

  // 计算各科偏离年级均值的程度
  const subjects = academicData.value.subjects
  const classSummary = examResultPage.value?.class_summaries?.[0]
  const classSubjectMap = new Map<number, { avg: number; full: number }>()

  if (classSummary) {
    for (const cs of classSummary.subjects) {
      classSubjectMap.set(cs.subject_id, {
        avg: cs.avg_score ?? 0,
        full: cs.full_score,
      })
    }
  }

  const devData = subjects.map((sub, i) => {
    const avgInfo = classSubjectMap.get(sub.subject_id)
    const deviation = sub.score !== null && avgInfo
      ? Number(((sub.score - avgInfo.avg) / avgInfo.full * 100).toFixed(1))
      : 0
    return {
      name: sub.subject_name,
      deviation,
      color: SUBJECT_COLORS[i % SUBJECT_COLORS.length],
    }
  })

  const option: any = {
    tooltip: {
      trigger: 'axis',
      formatter: (params: any) => {
        const p = Array.isArray(params) ? params[0] : params
        const sign = p.value >= 0 ? '+' : ''
        return `<div style="font-weight:600">${p.name}</div>偏离均值: ${sign}${p.value}%`
      },
    },
    grid: { left: 50, right: 20, top: 20, bottom: 40 },
    xAxis: {
      type: 'category',
      data: devData.map(d => d.name),
      axisLabel: { color: '#606266', fontSize: 11 },
    },
    yAxis: {
      type: 'value',
      name: '偏离(%)',
      axisLabel: { color: '#606266' },
      splitLine: { lineStyle: { type: 'dashed', color: '#e4e7ed' } },
    },
    series: [{
      type: 'bar',
      data: devData.map(d => ({
        value: d.deviation,
        itemStyle: {
          color: d.deviation >= 0
            ? new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: d.color },
              { offset: 1, color: d.color + '80' },
            ])
            : new echarts.graphic.LinearGradient(0, 1, 0, 0, [
              { offset: 0, color: '#ef4444' },
              { offset: 1, color: '#ef444480' },
            ]),
          borderRadius: [4, 4, 0, 0],
        },
      })),
      barWidth: '40%',
      label: {
        show: true,
        position: 'top',
        formatter: (params: any) => {
          const v = params.value
          return v >= 0 ? `+${v}%` : `${v}%`
        },
        fontSize: 11,
        color: '#606266',
      },
    }],
  }

  subjectDevInstance.setOption(option, true)
}

// ═══ 自适应缩放 ═══

const handleResize = () => {
  radarInstance?.resize()
  miniRadarInstance?.resize()
  subjectDevInstance?.resize()
}

// ═══ 生命周期 ═══

onMounted(async () => {
  await loadExamList()
  await loadExamResults()
  await loadRdiRecords()

  // 初始化 ResizeObserver
  resizeObserver = new ResizeObserver(() => {
    handleResize()
  })
  if (radarChartRef.value) resizeObserver.observe(radarChartRef.value)
  if (miniRadarRef.value) resizeObserver.observe(miniRadarRef.value)
  if (subjectDevRef.value) resizeObserver.observe(subjectDevRef.value)
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  radarInstance?.dispose()
  miniRadarInstance?.dispose()
  subjectDevInstance?.dispose()
  radarInstance = null
  miniRadarInstance = null
  subjectDevInstance = null
})

// ═══ watch: 模式切换时重绘雷达 ═══

watch(radarMode, () => {
  nextTick(() => initDualRadar())
})
</script>

<style scoped>
.student-radar-container {
  background-color: #f5f7fa;
  min-height: calc(100vh - 100px);
  padding: 16px;
}

.filter-bar {
  border-radius: 8px;
}

.filter-bar :deep(.el-card__body) {
  padding: 12px 16px;
}

.radar-card {
  border-radius: 8px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.title {
  font-weight: 600;
  color: #303133;
  font-size: 15px;
}

.legend-group {
  display: flex;
  gap: 12px;
}

.legend-item {
  font-size: 13px;
  font-weight: 500;
}

.echart-dom {
  width: 100%;
  height: 420px;
}

.mini-echart-dom {
  width: 100%;
  height: 200px;
}

/* ═══ 维度对比卡片 ═══ */

.dimension-card {
  border-radius: 8px;
}

.dimension-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.dim-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  background: #fafafa;
  border-radius: 6px;
  border: 1px solid #f0f0f0;
  transition: all 0.2s ease;
}

.dim-row:hover {
  background: #f5f7fa;
  border-color: #e4e7ed;
  transform: translateY(-1px);
}

.dim-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 500;
  color: #303133;
}

.dim-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  flex-shrink: 0;
}

.dim-scores {
  display: flex;
  gap: 16px;
}

.score-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  min-width: 50px;
}

.score-label {
  font-size: 11px;
  color: #909399;
}

.score-value {
  font-family: 'DIN Alternate', 'Courier New', monospace;
  font-size: 16px;
  font-weight: 700;
  color: #303133;
}

.score-item.academic .score-value {
  color: #3b82f6;
}

.score-item.behavior .score-value {
  color: #ef4444;
}

.score-item.delta .score-label {
  color: #c0c4cc;
}

.mini-radar-card {
  border-radius: 8px;
}

.subject-bar-card {
  border-radius: 8px;
}
</style>
