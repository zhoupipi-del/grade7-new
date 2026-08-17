<!--
  WINGS 教研 · 分层作业设计
  ==========================
  路径：frontend/src/views/research-ai/HomeworkDesign.vue
  路由：/research-ai/homework
  - Celery 异步生成（15-40 秒），前端轮询
  - 三层（基础/提高/拓展）题量默认 8-5-3，难易比例默认 4-4-2
  - 支持 9 学科，输出 Word
  request 封装在 @/api/request（baseURL=/api/v1，interceptor 已 return response.data）
-->
<template>
  <div class="homework-container">
    <el-card class="form-card">
      <template #header>
        <div class="card-header">
          <span>📐 分层作业设计</span>
          <el-tag type="info" size="small">AI 生成 · 三层分层</el-tag>
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
            <el-form-item label="章节/单元" prop="unit">
              <el-input v-model="form.unit" placeholder="如：第十二章 全等三角形" />
            </el-form-item>
          </el-col>
          <el-col :span="16">
            <el-form-item label="本节课主题" prop="topic">
              <el-input v-model="form.topic" placeholder="如：全等三角形的判定（SSS）" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item label="核心知识点" prop="knowledge_points">
          <el-input
            v-model="form.knowledge_points"
            type="textarea"
            :rows="2"
            placeholder="多个知识点用逗号分隔，如：全等三角形定义，SSS判定定理，对应边对应角"
          />
        </el-form-item>

        <el-form-item label="班级学情" prop="class_profile">
          <el-input
            v-model="form.class_profile"
            type="textarea"
            :rows="2"
            placeholder="描述班级整体情况，如：整体基础薄弱，计算能力差，但几何直观较好；约1/3学生可挑战拓展题"
          />
        </el-form-item>

        <el-row :gutter="20">
          <el-col :span="8">
            <el-form-item label="三层题量" prop="question_counts">
              <el-input v-model="form.question_counts" placeholder="基础-提高-拓展，如 8-5-3">
                <template #append>题</template>
              </el-input>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="难易比例" prop="difficulty_distribution">
              <el-input v-model="form.difficulty_distribution" placeholder="易-中-难，如 4-4-2" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="建议时长" prop="estimated_minutes">
              <el-input-number
                v-model="form.estimated_minutes"
                :min="10"
                :max="180"
                :step="5"
                style="width: 100%"
              />
              <span style="margin-left: 8px; color: #999">分钟</span>
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item label="附加要求" prop="extra_requirements">
          <el-input
            v-model="form.extra_requirements"
            type="textarea"
            :rows="2"
            placeholder="如：需要包含2道实际应用题；基础层不超过3步计算；拓展层可涉及竞赛题型"
          />
        </el-form-item>

        <el-form-item label="包含答案">
          <el-switch v-model="form.include_answers" />
          <span style="margin-left: 10px; color: #999; font-size: 12px">
            关闭后只输出题目，适合打印给学生
          </span>
        </el-form-item>

        <el-form-item>
          <el-button type="primary" size="large" :loading="submitting" @click="handleSubmit">
            {{ submitting ? '正在生成…' : '生成分层作业' }}
          </el-button>
          <el-button size="large" @click="handleReset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card v-if="currentTask" class="result-card">
      <template #header>
        <div class="card-header">
          <span>生成结果</span>
          <el-tag :type="statusType">{{ statusText }}</el-tag>
        </div>
      </template>

      <div v-if="currentTask.status === 'success'" class="result-success">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="学科">{{ currentTask.subject }}</el-descriptions-item>
          <el-descriptions-item label="年级">{{ currentTask.grade }}</el-descriptions-item>
          <el-descriptions-item label="主题" :span="2">{{ currentTask.topic }}</el-descriptions-item>
          <el-descriptions-item label="题量">{{ currentTask.question_counts }}</el-descriptions-item>
          <el-descriptions-item label="时长">{{ currentTask.estimated_minutes }}分钟</el-descriptions-item>
          <el-descriptions-item label="Token消耗">
            {{ currentTask.prompt_tokens || 0 }} + {{ currentTask.completion_tokens || 0 }}
          </el-descriptions-item>
          <el-descriptions-item label="耗时">{{ currentTask.elapsed_sec || '-' }}秒</el-descriptions-item>
        </el-descriptions>

        <div class="result-actions">
          <el-button type="success" @click="handleDownload(currentTask.id)">
            下载 Word 文档
          </el-button>
          <el-button @click="loadHistory">刷新列表</el-button>
        </div>
      </div>

      <div v-else-if="currentTask.status === 'failed'" class="result-failed">
        <el-alert
          type="error"
          :closable="false"
          :title="currentTask.error_msg || '生成失败'"
        />
        <el-button style="margin-top: 12px" @click="handleRetry">重新生成</el-button>
      </div>

      <div v-else class="result-processing">
        <el-icon class="is-loading" :size="24"><Loading /></el-icon>
        <span>AI 正在生成分层作业，预计 15-40 秒，请稍候…</span>
      </div>
    </el-card>

    <el-card class="history-card">
      <template #header>
        <div class="card-header">
          <span>历史作业</span>
          <el-button size="small" @click="loadHistory">刷新</el-button>
        </div>
      </template>

      <el-table :data="history" v-loading="loadingHistory" stripe>
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="subject" label="学科" width="80" />
        <el-table-column prop="grade" label="年级" width="110" />
        <el-table-column prop="topic" label="主题" min-width="200" show-overflow-tooltip />
        <el-table-column prop="question_counts" label="题量" width="90" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag
              :type="
                row.status === 'success'
                  ? 'success'
                  : row.status === 'failed'
                    ? 'danger'
                    : 'warning'
              "
              size="small"
            >
              {{ statusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="170">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="120">
          <template #default="{ row }">
            <el-button
              v-if="row.status === 'success'"
              type="primary"
              link
              size="small"
              @click="handleDownload(row.id)"
            >下载</el-button>
            <el-button link size="small" @click="viewTask(row as HomeworkTask)">查看</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed } from 'vue'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'
import request from '@/api/request'

interface HomeworkTask {
  id: number
  subject: string
  grade: string
  textbook?: string
  unit?: string
  topic: string
  knowledge_points?: string
  class_profile?: string
  question_counts: string
  difficulty_distribution: string
  estimated_minutes: number
  include_answers: boolean
  extra_requirements?: string
  status: string
  file_path?: string
  file_name?: string
  prompt_tokens?: number
  completion_tokens?: number
  error_msg?: string
  elapsed_sec?: number
  created_at: string
  finished_at?: string
}

const formRef = ref<FormInstance>()
const submitting = ref(false)
const loadingHistory = ref(false)
const currentTask = ref<HomeworkTask | null>(null)
const history = ref<HomeworkTask[]>([])
let pollTimer: ReturnType<typeof setInterval> | null = null

const form = reactive({
  subject: '数学',
  grade: '八年级上册',
  textbook: '人教版',
  unit: '',
  topic: '',
  knowledge_points: '',
  class_profile: '',
  question_counts: '8-5-3',
  difficulty_distribution: '4-4-2',
  estimated_minutes: 40,
  include_answers: true,
  extra_requirements: '',
})

const rules: FormRules = {
  subject: [{ required: true, message: '请选择学科', trigger: 'change' }],
  grade: [{ required: true, message: '请选择年级', trigger: 'change' }],
  topic: [{ required: true, message: '请输入本节课主题', trigger: 'blur' }],
  question_counts: [
    {
      validator: (_rule: any, value: string, cb: any) => {
        const parts = value.split('-')
        if (parts.length !== 3 || parts.some((p) => !/^\d+$/.test(p))) {
          return cb(new Error('格式：基础-提高-拓展，如 8-5-3'))
        }
        if (parts.reduce((s, p) => s + parseInt(p), 0) < 3) {
          return cb(new Error('总题量至少3题'))
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

function formatTime(t: string) {
  if (!t) return '-'
  return new Date(t).toLocaleString('zh-CN')
}

async function handleSubmit() {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    submitting.value = true
    currentTask.value = null
    try {
      // request 已 return response.data
      const data = await request.post<any>('/research_ai/homework', { ...form })
      currentTask.value = data
      ElMessage.success('作业生成任务已提交')
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
      const data = await request.get<any>(`/research_ai/homework/${taskId}`)
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
    const data = await request.get<any[]>('/research_ai/homework', {
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
    const resp = await request.get(`/research_ai/homework/${id}/download`, {
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
    a.download = `homework_${id}.docx`
    a.click()
    window.URL.revokeObjectURL(url)
    ElMessage.success('下载已开始')
  } catch {
    ElMessage.error('下载失败')
  }
}

function viewTask(row: HomeworkTask) {
  currentTask.value = row
}

function handleRetry() {
  if (currentTask.value) {
    Object.assign(form, {
      subject: currentTask.value.subject,
      grade: currentTask.value.grade,
      textbook: currentTask.value.textbook || '',
      unit: currentTask.value.unit || '',
      topic: currentTask.value.topic,
      knowledge_points: currentTask.value.knowledge_points || '',
      class_profile: currentTask.value.class_profile || '',
      question_counts: currentTask.value.question_counts,
      difficulty_distribution: currentTask.value.difficulty_distribution,
      estimated_minutes: currentTask.value.estimated_minutes,
      include_answers: currentTask.value.include_answers,
      extra_requirements: currentTask.value.extra_requirements || '',
    })
    handleSubmit()
  }
}

onMounted(() => {
  loadHistory()
})
</script>

<style scoped>
.homework-container {
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
