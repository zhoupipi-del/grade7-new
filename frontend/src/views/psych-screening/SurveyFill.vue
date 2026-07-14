<template>
  <div class="survey-fill">
    <!-- 顶部进度 -->
    <div class="fill-header">
      <div class="fill-meta">
        <h2 class="fill-title">MSSMHS-55 心理健康筛查</h2>
        <p class="fill-desc">中学生心理健康量表 · 55题 · 10个维度</p>
      </div>
      <div class="fill-progress">
        <el-steps :active="currentStep" align-center finish-status="success">
          <el-step title="选择学生" />
          <el-step title="填写量表" />
          <el-step title="提交完成" />
        </el-steps>
      </div>
    </div>

    <!-- Step 1: 选择学生 -->
    <el-card v-if="currentStep === 0" shadow="hover" class="fill-card">
      <template #header><span class="card-title">选择筛查学生</span></template>
      <div class="student-select">
        <el-input
          v-model="searchKeyword"
          placeholder="搜索学生姓名或学号..."
          :prefix-icon="Search"
          clearable
          style="width: 320px"
          @input="doSearch"
        />
        <el-select v-model="filterGradeId" placeholder="年级" style="width: 140px; margin-left: 8px" @change="doSearch">
          <el-option v-for="g in grades" :key="g.id" :label="g.name" :value="g.id" />
        </el-select>
      </div>
      <el-table
        :data="students"
        border stripe
        v-loading="searchLoading"
        highlight-current-row
        @current-change="selectStudent"
        max-height="400"
        style="margin-top: 12px"
      >
        <el-table-column type="index" width="50" />
        <el-table-column prop="name" label="姓名" width="100" />
        <el-table-column prop="class_name" label="班级" width="100" />
        <el-table-column prop="risk_level" label="当前风险" width="100">
          <template #default="{ row }">
            <el-tag v-if="row.risk_level" :type="riskTagType(row.risk_level)" size="small">
              {{ RISK_LABELS[row.risk_level] || row.risk_level }}
            </el-tag>
            <span v-else class="no-risk">未筛查</span>
          </template>
        </el-table-column>
      </el-table>
      <div style="margin-top: 16px; text-align: right">
        <el-button type="warning" :disabled="!selectedStudent" @click="currentStep = 1">
          开始填写 ({{ selectedStudent ? selectedStudent.name : '未选择' }})
        </el-button>
      </div>
    </el-card>

    <!-- Step 2: 填写量表 -->
    <el-card v-if="currentStep === 1" shadow="hover" class="fill-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">学生: {{ selectedStudent?.name }}</span>
          <span class="card-progress">{{ completedCount }} / {{ questions.length }} 题</span>
        </div>
      </template>

      <div class="question-scroll">
        <div
          v-for="(q, idx) in paginatedQuestions"
          :key="q.id"
          class="question-item"
          :class="{ answered: answers[q.id] !== undefined }"
        >
          <div class="q-header">
            <span class="q-num">Q{{ q.order_no }}</span>
            <el-tag size="small" type="warning" effect="plain">{{ q.dimension_name }}</el-tag>
            <span v-if="q.is_reverse" class="reverse-badge">反向</span>
          </div>
          <div class="q-text">{{ q.text }}</div>
          <el-radio-group
            v-model="answers[q.id]"
            class="q-options"
            @change="onAnswer(q.id)"
          >
            <el-radio
              v-for="opt in scoreOptions"
              :key="opt.value"
              :value="opt.value"
              :label="opt.value"
              border
            >
              {{ opt.label }}
            </el-radio>
          </el-radio-group>
        </div>
      </div>

      <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 16px">
        <el-button @click="currentStep = 0">返回选择</el-button>
        <el-pagination
          small
          layout="prev, pager, next"
          :total="questions.length"
          :page-size="pageSize"
          v-model:current-page="currentPage"
        />
        <el-button
          type="warning"
          :disabled="completedCount < questions.length"
          :loading="submitting"
          @click="submitAll"
        >
          提交问卷 ({{ completedCount }}/{{ questions.length }})
        </el-button>
      </div>
    </el-card>

    <!-- Step 3: 提交成功 -->
    <el-card v-if="currentStep === 2" shadow="hover" class="fill-card success-card">
      <div class="success-content">
        <el-icon :size="64" color="#ff9a56"><CircleCheckFilled /></el-icon>
        <h2>问卷提交成功</h2>
        <div class="result-summary">
          <div class="result-item">
            <span>总分</span>
            <span :style="{ color: scoreColor(submitResult.total_score), fontSize: '32px', fontWeight: 700 }">
              {{ submitResult.total_score }}
            </span>
          </div>
          <div class="result-item">
            <span>风险等级</span>
            <el-tag :type="riskTagType(submitResult.risk_level)" size="large">
              {{ RISK_LABELS[submitResult.risk_level] || submitResult.risk_level }}
            </el-tag>
          </div>
        </div>
        <div class="result-actions">
          <el-button type="warning" @click="$router.push({ path: '/psych-screening/result', query: { survey_id: submitResult.survey_id } })">
            查看详细结果
          </el-button>
          <el-button @click="reset">再次筛查</el-button>
          <el-button @click="$router.push('/psych-screening')">返回总览</el-button>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { Search, CircleCheckFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { searchStudents, listQuestions, submitSurvey, RISK_LABELS, type RiskLevel, type PsychQuestion } from '@/api/psychScreening'
import { getGrades, getClassStudents } from '@/api/classes'

// ── 状态 ──
const currentStep = ref(0)
const searchKeyword = ref('')
const filterGradeId = ref<number | ''>('')
const searchLoading = ref(false)
const students = ref<any[]>([])
const selectedStudent = ref<any>(null)
const grades = ref<Array<{ id: number; name: string }>>([])

const questions = ref<PsychQuestion[]>([])
const answers = ref<Record<string, number>>({})
const currentPage = ref(1)
const pageSize = 10
const submitting = ref(false)
const submitResult = ref<any>({})

const scoreOptions = [
  { value: 1, label: '1-无' },
  { value: 2, label: '2-轻度' },
  { value: 3, label: '3-中度' },
  { value: 4, label: '4-偏重' },
  { value: 5, label: '5-严重' },
]

// ── 计算 ──
const completedCount = computed(() => Object.keys(answers.value).length)

const paginatedQuestions = computed(() => {
  const start = (currentPage.value - 1) * pageSize
  return questions.value.slice(start, start + pageSize)
})

// ── 方法 ──
async function doSearch() {
  searchLoading.value = true
  try {
    const params: any = { q: searchKeyword.value || undefined }
    if (filterGradeId.value) params.grade_id = filterGradeId.value
    const res = await searchStudents(params)
    students.value = (res as any)?.items || res || []
  } catch (e) {
    console.error('Search students error:', e)
  } finally {
    searchLoading.value = false
  }
}

function selectStudent(row: any) {
  selectedStudent.value = row
}

function riskTagType(level: string) {
  const map: Record<string, string> = { low: 'success', medium: 'warning', high: 'danger', critical: 'danger' }
  return map[level] || 'info'
}

function scoreColor(score: number) {
  if (score >= 160) return '#ff4444'
  if (score >= 120) return '#e6a23c'
  return '#67c23a'
}

function onAnswer(qId: number) {
  // 自动记录
}

async function submitAll() {
  if (!selectedStudent.value) return
  submitting.value = true
  try {
    const answerList = Object.entries(answers.value).map(([qId, score]) => {
      const q = questions.value.find(x => x.id === Number(qId))
      return {
        question_no: q?.order_no || Number(qId),
        score,
      }
    })
    const res = await submitSurvey({
      student_id: selectedStudent.value.id,
      survey_type: 'MSSMHS-55',
      answers: answerList,
    })
    submitResult.value = res || {}
    currentStep.value = 2
  } catch (e: any) {
    ElMessage.error(e?.message || '提交失败')
  } finally {
    submitting.value = false
  }
}

function reset() {
  currentStep.value = 0
  selectedStudent.value = null
  answers.value = {}
  currentPage.value = 1
  submitResult.value = {}
}

// ── 生命周期 ──
onMounted(async () => {
  try {
    const [qRes, gRes] = await Promise.all([
      listQuestions().catch(() => ({ data: [] })),
      getGrades().catch(() => ({ data: [] })),
    ])
    questions.value = (qRes as any)?.data || qRes || []
    // 如果题目为空，尝试种子初始化
    if (!questions.value.length) {
      try {
        const { seedQuestions } = await import('@/api/psychScreening')
        await seedQuestions()
        const retry = await listQuestions()
        questions.value = (retry as any)?.data || retry || []
      } catch {}
    }
    grades.value = (gRes as any)?.data || gRes || []
  } catch (e) {
    console.error('Init survey fill error:', e)
  }
})
</script>

<style scoped>
.survey-fill {
  padding: 20px;
  color: #c9d1d9;
}

.fill-header {
  margin-bottom: 20px;
}
.fill-title {
  font-size: 20px;
  font-weight: 700;
  color: #f0f6fc;
  margin: 0 0 4px;
}
.fill-desc {
  font-size: 13px;
  color: #8b949e;
  margin: 0 0 12px;
}

.fill-card {
  background: #161b22 !important;
  border: 1px solid #30363d !important;
}
.fill-card :deep(.el-card__header) {
  border-bottom: 1px solid #30363d;
}
.card-title {
  font-size: 15px;
  font-weight: 600;
  color: #f0f6fc;
}
.card-header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.card-progress {
  font-size: 13px;
  color: #ff9a56;
  font-weight: 600;
}

.student-select {
  display: flex;
  align-items: center;
}
.no-risk {
  color: #6e7681;
  font-size: 13px;
}

.question-scroll {
  max-height: 520px;
  overflow-y: auto;
  padding-right: 8px;
}
.question-item {
  padding: 16px 0;
  border-bottom: 1px solid #21262d;
  transition: background 0.2s;
}
.question-item.answered {
  background: rgba(255, 154, 86, 0.05);
  border-radius: 6px;
  padding: 16px 12px;
}
.q-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.q-num {
  font-weight: 700;
  color: #ff9a56;
  font-size: 14px;
}
.reverse-badge {
  font-size: 11px;
  color: #e6a23c;
  border: 1px solid #e6a23c;
  border-radius: 3px;
  padding: 0 6px;
}
.q-text {
  font-size: 15px;
  color: #f0f6fc;
  margin-bottom: 10px;
  line-height: 1.6;
}
.q-options {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.success-card {
  text-align: center;
}
.success-content {
  padding: 40px 20px;
}
.success-content h2 {
  color: #ff9a56;
  margin: 16px 0 24px;
}
.result-summary {
  display: flex;
  justify-content: center;
  gap: 48px;
  margin-bottom: 24px;
}
.result-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  color: #8b949e;
  font-size: 14px;
}
.result-actions {
  display: flex;
  justify-content: center;
  gap: 12px;
}
</style>
