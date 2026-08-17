<!--
  WINGS 教研 · AI 学情分析报告
  ==============================
  路径：frontend/src/views/research-ai/LearningAnalysis.vue
  路由：/research-ai/analysis
  - Celery 异步生成（15-60 秒），前端轮询
  - 输入：班级/年级 + 学科 + 学情数据摘要（分数段/知识点正确率等）
  - 输出 Word 学情分析报告
  request 封装在 @/api/request（baseURL=/api/v1，interceptor 已 return response.data）
-->
<template>
  <div class="analysis-container">
    <el-card class="form-card">
      <template #header>
        <div class="card-header">
          <span>📊 AI 学情分析报告</span>
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
            <el-form-item label="分析对象" prop="scope_name">
              <el-input v-model="form.scope_name" placeholder="如：2501班 / 2025级初一" />
            </el-form-item>
          </el-col>
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
                <el-option label="七年级" value="七年级" />
                <el-option label="八年级" value="八年级" />
                <el-option label="九年级" value="九年级" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item label="考试名称" prop="exam_name">
          <el-input v-model="form.exam_name" placeholder="如：期中考试 / 单元测试" />
        </el-form-item>

        <el-form-item label="学情数据摘要" prop="data_summary">
          <el-input
            v-model="form.data_summary"
            type="textarea"
            :rows="6"
            placeholder="粘贴/填写成绩分布与学情数据，如：全班48人，平均分82.3，优秀率35%，及格率92%；第二章全等三角形正确率78%，其中SSS判定60%…（请勿包含学生姓名、学号等个人信息）"
          />
        </el-form-item>

        <el-form-item label="关注点" prop="analysis_focus">
          <el-input v-model="form.analysis_focus" placeholder="如：重点关注学困生转化与几何证明薄弱环节" />
        </el-form-item>

        <el-form-item>
          <el-button type="primary" :loading="submitting" @click="handleSubmit">
            {{ submitting ? '生成中…' : '生成分析报告' }}
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
          <p>报告已生成，耗时 {{ currentTask.elapsed_sec || '-' }} 秒。</p>
          <div class="result-actions">
            <el-button type="primary" @click="handleDownload(currentTask.id)">下载报告 Word</el-button>
          </div>
        </div>
      </template>
      <div v-else-if="currentTask.status === 'processing'" class="result-processing">
        <el-icon class="is-loading"><i class="el-icon-loading" /></el-icon>
        <span>AI 正在分析学情，约 15-60 秒…</span>
      </div>
      <div v-else-if="currentTask.status === 'failed'" class="result-failed">
        <el-alert :title="currentTask.error_msg || '生成失败'" type="error" :closable="false" />
        <el-button style="margin-top: 12px" @click="handleRetry">重试</el-button>
      </div>
    </el-card>

    <el-card class="history-card">
      <template #header>
        <div class="card-header">
          <span>历史报告</span>
          <el-button size="small" @click="loadHistory">刷新</el-button>
        </div>
      </template>
      <el-table :data="history" v-loading="loadingHistory" size="small">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="scope_name" label="分析对象" width="120" />
        <el-table-column prop="subject" label="学科" width="80" />
        <el-table-column prop="exam_name" label="考试" min-width="120" show-overflow-tooltip />
        <el-table-column prop="status" label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.status === 'success' ? 'success' : row.status === 'failed' ? 'danger' : 'warning'" size="small">
              {{ statusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200">
          <template #default="{ row }">
            <el-button size="small" @click="viewTask(row as AnalysisTask)">查看</el-button>
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

interface AnalysisTask {
  id: number
  scope_name: string
  subject: string
  grade: string
  exam_name?: string | null
  data_summary: string
  analysis_focus?: string | null
  status: string
  error_msg?: string | null
  elapsed_sec?: number | null
}

const formRef = ref()
const submitting = ref(false)
const currentTask = ref<AnalysisTask | null>(null)
const loadingHistory = ref(false)
const history = ref<AnalysisTask[]>([])
let pollTimer: ReturnType<typeof setInterval> | null = null

const form = reactive({
  scope_name: '',
  subject: '数学',
  grade: '八年级',
  exam_name: '',
  data_summary: '',
  analysis_focus: '',
})

const rules = {
  scope_name: [{ required: true, message: '请输入分析对象', trigger: 'blur' }],
  subject: [{ required: true, message: '请选择学科', trigger: 'change' }],
  grade: [{ required: true, message: '请选择年级', trigger: 'change' }],
  data_summary: [{ required: true, message: '请输入学情数据摘要', trigger: 'blur' }],
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
      const data = await request.post<any>('/research_ai/analysis', { ...form })
      currentTask.value = data
      ElMessage.success('学情分析任务已提交')
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
      const data = await request.get<any>(`/research_ai/analysis/${taskId}`)
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
    const data = await request.get<any[]>('/research_ai/analysis', {
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
    const resp = await request.get(`/research_ai/analysis/${id}/download`, {
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
    a.download = `analysis_${id}.docx`
    a.click()
    window.URL.revokeObjectURL(url)
    ElMessage.success('下载已开始')
  } catch {
    ElMessage.error('下载失败')
  }
}

function viewTask(row: AnalysisTask) {
  currentTask.value = row
}

function handleRetry() {
  if (currentTask.value) {
    // V2.2.1：按原任务完整配置恢复（含 grade/data_summary/analysis_focus），
    // 历史学情缺 data_summary 时重试将无法按原配置执行——必须补齐
    const t = currentTask.value
    Object.assign(form, {
      scope_name: t.scope_name,
      subject: t.subject,
      grade: t.grade,
      exam_name: t.exam_name || '',
      data_summary: t.data_summary || '',
      analysis_focus: t.analysis_focus || '',
    })
    handleSubmit()
  }
}

onMounted(() => {
  loadHistory()
})
</script>

<style scoped>
.analysis-container {
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
