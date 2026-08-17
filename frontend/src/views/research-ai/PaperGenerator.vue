<!--
  WINGS 教研 · AI 试卷命制
  ==========================
  路径：frontend/src/views/research-ai/PaperGenerator.vue
  路由：/research-ai/paper
  - Celery 异步生成（15-60 秒），前端轮询
  - 题型配置（选择题-填空题-解答题）默认 6-4-3，难易比例默认 4-4-2
  - 输出 Word（试卷 + 答案与解析）
  request 封装在 @/api/request（baseURL=/api/v1，interceptor 已 return response.data）
-->
<template>
  <div class="paper-container">
    <el-card class="form-card">
      <template #header>
        <div class="card-header">
          <span>📄 AI 试卷命制</span>
          <el-tag type="info" size="small">AI 生成 · Word 输出</el-tag>
        </div>
      </template>

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-width="110px"
        label-position="right"
      >
        <el-row :gutter="20">
          <el-col :span="8">
            <el-form-item label="学科" prop="subject">
              <el-select v-model="form.subject" placeholder="选择学科" style="width: 100%">
                <el-option label="数学" value="数学" />
                <el-option label="语文" value="语文" />
                <el-option label="英语" value="英语" />
                <el-option label="物理" value="物理" />
                <el-option label="化学" value="化学" />
                <el-option label="生物" value="生物" />
                <el-option label="历史" value="历史" />
                <el-option label="地理" value="地理" />
                <el-option label="道德与法治" value="道德与法治" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="年级" prop="grade">
              <el-select v-model="form.grade" placeholder="选择年级" style="width: 100%">
                <el-option label="七年级上册" value="七年级上册" />
                <el-option label="七年级下册" value="七年级下册" />
                <el-option label="八年级上册" value="八年级上册" />
                <el-option label="八年级下册" value="八年级下册" />
                <el-option label="九年级上册" value="九年级上册" />
                <el-option label="九年级下册" value="九年级下册" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="教材版本" prop="textbook">
              <el-input v-model="form.textbook" placeholder="如：人教版" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="20">
          <el-col :span="8">
            <el-form-item label="单元/章节" prop="unit">
              <el-input v-model="form.unit" placeholder="如：第十二章 全等三角形" />
            </el-form-item>
          </el-col>
          <el-col :span="16">
            <el-form-item label="考查主题" prop="topic">
              <el-input v-model="form.topic" placeholder="如：全等三角形的判定综合" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item label="知识点" prop="knowledge_points">
          <el-input
            v-model="form.knowledge_points"
            type="textarea"
            :rows="2"
            placeholder="逗号分隔，如：SSS判定，SAS判定，AAS判定"
          />
        </el-form-item>

        <el-row :gutter="20">
          <el-col :span="8">
            <el-form-item label="题型配置" prop="question_types">
              <el-input v-model="form.question_types" placeholder="选择-填空-解答，如 6-4-3" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="卷面总分" prop="total_score">
              <el-input-number v-model="form.total_score" :min="50" :max="150" :step="10" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="难易比例" prop="difficulty">
              <el-input v-model="form.difficulty" placeholder="易-中-难，如 4-4-2" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="20">
          <el-col :span="8">
            <el-form-item label="含答案解析">
              <el-switch v-model="form.include_answers" />
            </el-form-item>
          </el-col>
          <el-col :span="16">
            <el-form-item label="额外要求" prop="extra_requirements">
              <el-input v-model="form.extra_requirements" placeholder="如：多出一些实际应用情境题" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item>
          <el-button type="primary" :loading="submitting" @click="handleSubmit">
            {{ submitting ? '生成中…' : '生成试卷' }}
          </el-button>
          <el-button @click="handleReset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card v-if="currentTask" class="result-card">
      <template #header>
        <div class="card-header">
          <span>生成结果</span>
          <el-tag :type="statusType" size="small">{{ statusText }}</el-tag>
        </div>
      </template>
      <template v-if="currentTask.status === 'success'">
        <div class="result-success">
          <p>试卷已生成，耗时 {{ currentTask.elapsed_sec || '-' }} 秒。</p>
          <div class="result-actions">
            <el-button type="primary" @click="handleDownload(currentTask.id)">下载试卷 Word</el-button>
            <el-button @click="handleRetry">按此配置再生成一版</el-button>
          </div>
        </div>
      </template>
      <div v-else-if="currentTask.status === 'processing'" class="result-processing">
        <el-icon class="is-loading"><i class="el-icon-loading" /></el-icon>
        <span>AI 正在命制试卷，约 15-60 秒…</span>
      </div>
      <div v-else-if="currentTask.status === 'failed'" class="result-failed">
        <el-alert :title="currentTask.error_msg || '生成失败'" type="error" :closable="false" />
        <el-button style="margin-top: 12px" @click="handleRetry">重试</el-button>
      </div>
    </el-card>

    <el-card class="history-card">
      <template #header>
        <div class="card-header">
          <span>历史试卷</span>
          <el-button size="small" @click="loadHistory">刷新</el-button>
        </div>
      </template>
      <el-table :data="history" v-loading="loadingHistory" size="small">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="subject" label="学科" width="80" />
        <el-table-column prop="grade" label="年级" width="100" />
        <el-table-column prop="topic" label="考查主题" min-width="160" show-overflow-tooltip />
        <el-table-column prop="question_types" label="题型" width="110" />
        <el-table-column prop="total_score" label="总分" width="70" />
        <el-table-column prop="status" label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.status === 'success' ? 'success' : row.status === 'failed' ? 'danger' : 'warning'" size="small">
              {{ statusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200">
          <template #default="{ row }">
            <el-button size="small" @click="viewTask(row as PaperTask)">查看</el-button>
            <el-button
              v-if="row.status === 'success'"
              size="small"
              type="primary"
              @click="handleDownload(row.id)"
            >
              下载
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import request from '@/api/request'

interface PaperTask {
  id: number
  subject: string
  grade: string
  textbook?: string | null
  unit?: string | null
  topic: string
  knowledge_points?: string | null
  question_types: string
  total_score: number
  difficulty: string
  include_answers: boolean
  extra_requirements?: string | null
  status: string
  error_msg?: string | null
  elapsed_sec?: number | null
}

const formRef = ref()
const submitting = ref(false)
const currentTask = ref<PaperTask | null>(null)
const loadingHistory = ref(false)
const history = ref<PaperTask[]>([])
let pollTimer: ReturnType<typeof setInterval> | null = null

const form = reactive({
  subject: '数学',
  grade: '八年级上册',
  textbook: '',
  unit: '',
  topic: '',
  knowledge_points: '',
  question_types: '6-4-3',
  total_score: 100,
  difficulty: '4-4-2',
  include_answers: true,
  extra_requirements: '',
})

const rules = {
  subject: [{ required: true, message: '请选择学科', trigger: 'change' }],
  grade: [{ required: true, message: '请选择年级', trigger: 'change' }],
  topic: [{ required: true, message: '请输入考查主题', trigger: 'blur' }],
  question_types: [
    {
      validator: (_: unknown, value: string, cb: (e?: Error) => void) => {
        const parts = String(value || '').split('-')
        if (parts.length !== 3 || parts.some((p) => !/^\d+$/.test(p))) {
          return cb(new Error('格式：选择-填空-解答，如 6-4-3'))
        }
        cb()
      },
      trigger: 'blur',
    },
  ],
  difficulty: [
    {
      validator: (_: unknown, value: string, cb: (e?: Error) => void) => {
        const parts = String(value || '').split('-')
        if (parts.length !== 3 || parts.some((p) => !/^\d+$/.test(p))) {
          return cb(new Error('格式：易-中-难，如 4-4-2'))
        }
        cb()
      },
      trigger: 'blur',
    },
  ],
}

const statusType = computed(() => {
  const s = currentTask.value?.status
  if (s === 'success') return 'success'
  if (s === 'failed') return 'danger'
  return 'warning'
})

const statusText = computed(() => {
  const s = currentTask.value?.status
  const map: Record<string, string> = {
    pending: '排队中',
    processing: '生成中',
    success: '已完成',
    failed: '失败',
  }
  return s ? map[s] || s : ''
})

function statusLabel(s: string) {
  const map: Record<string, string> = {
    pending: '排队中',
    processing: '生成中',
    success: '成功',
    failed: '失败',
  }
  return map[s] || s
}

async function handleSubmit() {
  if (!formRef.value) return
  await formRef.value.validate(async (valid: boolean) => {
    if (!valid) return
    submitting.value = true
    currentTask.value = null
    try {
      const data = await request.post<any>('/research_ai/paper', { ...form })
      currentTask.value = data
      ElMessage.success('试卷生成任务已提交')
      startPolling(data.id)
    } catch (e: any) {
      ElMessage.error(e?.response?.data?.detail || e?.message || '提交失败')
    } finally {
      submitting.value = false
    }
  })
}

function handleReset() {
  formRef.value?.resetFields()
  currentTask.value = null
  stopPolling()
}

function startPolling(taskId: number) {
  stopPolling()
  pollTimer = setInterval(async () => {
    try {
      const data = await request.get<any>(`/research_ai/paper/${taskId}`)
      currentTask.value = data
      if (data.status === 'success' || data.status === 'failed') {
        stopPolling()
        loadHistory()
      }
    } catch {
      /* ignore */
    }
  }, 3000)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

async function loadHistory() {
  loadingHistory.value = true
  try {
    const data = await request.get<any[]>('/research_ai/paper', {
      params: { limit: 20, offset: 0 },
    })
    history.value = data || []
  } catch {
    // 静默
  } finally {
    loadingHistory.value = false
  }
}

async function handleDownload(id: number) {
  try {
    const resp = await request.get(`/research_ai/paper/${id}/download`, {
      responseType: 'blob',
    })
    const blob =
      resp instanceof Blob
        ? resp
        : new Blob([resp], {
            type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
          })
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `paper_${id}.docx`
    a.click()
    window.URL.revokeObjectURL(url)
    ElMessage.success('下载已开始')
  } catch {
    ElMessage.error('下载失败')
  }
}

function viewTask(row: PaperTask) {
  currentTask.value = row
}

function handleRetry() {
  if (currentTask.value) {
    // V2.2.1：按原任务完整配置恢复（含教材/单元/知识点/是否含答案），
    // 不再只恢复部分字段导致重试偏离原意图
    const t = currentTask.value
    Object.assign(form, {
      subject: t.subject,
      grade: t.grade,
      textbook: t.textbook || '',
      unit: t.unit || '',
      topic: t.topic,
      knowledge_points: t.knowledge_points || '',
      question_types: t.question_types,
      total_score: t.total_score,
      difficulty: t.difficulty,
      include_answers: t.include_answers ?? true,
      extra_requirements: t.extra_requirements || '',
    })
    handleSubmit()
  }
}

onMounted(() => {
  loadHistory()
})
</script>

<style scoped>
.paper-container {
  padding: 20px;
  max-width: 1100px;
  margin: 0 auto;
}
.form-card,
.result-card,
.history-card {
  margin-bottom: 20px;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.result-success .result-actions {
  margin-top: 16px;
}
.result-processing {
  display: flex;
  align-items: center;
  gap: 12px;
  color: #666;
  padding: 20px 0;
}
.result-failed {
  padding: 8px 0;
}
</style>
