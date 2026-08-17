<!--
  WINGS 教研 · AI 学生评语生成
  ==============================
  路径：frontend/src/views/research-ai/StudentComment.vue
  路由：/research-ai/comments
  - Celery 异步生成（15-60 秒），前端轮询
  - 批量学生（姓名+表现关键词）→ 学期/品德/家校评语
  - 隐私：学生姓名不发送给 LLM，生成后本地回填
  - 输出 Word（批量评语）
  request 封装在 @/api/request（baseURL=/api/v1，interceptor 已 return response.data）
-->
<template>
  <div class="comment-container">
    <el-card class="form-card">
      <template #header>
        <div class="card-header">
          <span>💬 AI 学生评语生成</span>
          <el-tag type="info" size="small">隐私安全 · 姓名不送 LLM</el-tag>
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
            <el-form-item label="班级" prop="class_name">
              <el-input v-model="form.class_name" placeholder="如：2501班" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="学期" prop="term">
              <el-input v-model="form.term" placeholder="如：2025-2026学年第一学期" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="评语类型" prop="comment_type">
              <el-select v-model="form.comment_type" style="width: 100%">
                <el-option label="学期评语" value="semester" />
                <el-option label="品德评语" value="moral" />
                <el-option label="家校沟通" value="parent" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item label="风格要求" prop="style">
          <el-input v-model="form.style" placeholder="如：亲切自然，60-100字，多肯定" />
        </el-form-item>

        <el-form-item label="学生名单" required>
          <div class="student-list">
            <div v-for="(s, idx) in form.students" :key="idx" class="student-row">
              <el-input
                v-model="s.name"
                :placeholder="`学生${idx + 1}姓名`"
                style="width: 180px"
              />
              <el-input
                v-model="s.keywords"
                :placeholder="`表现关键词（如：课堂积极，作业认真，进步明显）`"
                style="flex: 1"
              />
              <el-button
                type="danger"
                :icon="'Delete'"
                circle
                size="small"
                @click="removeStudent(idx)"
              />
            </div>
            <el-button type="primary" plain size="small" @click="addStudent">
              + 添加学生
            </el-button>
            <span class="student-count">{{ form.students.length }}/60 人</span>
          </div>
        </el-form-item>

        <el-form-item>
          <el-button type="primary" :loading="submitting" @click="handleSubmit">
            {{ submitting ? '生成中…' : '生成评语' }}
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
          <p>已为 {{ currentTask.student_count || '-' }} 名学生生成评语，耗时 {{ currentTask.elapsed_sec || '-' }} 秒。</p>
          <div class="result-actions">
            <el-button type="primary" @click="handleDownload(currentTask.id)">下载评语 Word</el-button>
          </div>
        </div>
      </template>
      <div v-else-if="currentTask.status === 'processing'" class="result-processing">
        <el-icon class="is-loading"><i class="el-icon-loading" /></el-icon>
        <span>AI 正在撰写评语，约 15-60 秒…</span>
      </div>
      <div v-else-if="currentTask.status === 'failed'" class="result-failed">
        <el-alert :title="currentTask.error_msg || '生成失败'" type="error" :closable="false" />
        <el-button style="margin-top: 12px" @click="handleRetry">重试</el-button>
      </div>
    </el-card>

    <el-card class="history-card">
      <template #header>
        <div class="card-header">
          <span>历史评语任务</span>
          <el-button size="small" @click="loadHistory">刷新</el-button>
        </div>
      </template>
      <el-table :data="history" v-loading="loadingHistory" size="small">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="class_name" label="班级" width="120" />
        <el-table-column prop="term" label="学期" min-width="160" show-overflow-tooltip />
        <el-table-column prop="student_count" label="人数" width="70" />
        <el-table-column prop="comment_type" label="类型" width="100">
          <template #default="{ row }">
            {{ typeLabel(row.comment_type) }}
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.status === 'success' ? 'success' : row.status === 'failed' ? 'danger' : 'warning'" size="small">
              {{ statusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200">
          <template #default="{ row }">
            <el-button size="small" @click="viewTask(row as CommentTask)">查看</el-button>
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

interface CommentTask {
  id: number
  class_name: string
  term: string
  comment_type: string
  students: Array<{
    name: string
    keywords?: string | null
  }>
  student_count?: number | null
  style?: string | null
  status: string
  error_msg?: string | null
  elapsed_sec?: number | null
}

const formRef = ref()
const submitting = ref(false)
const currentTask = ref<CommentTask | null>(null)
const loadingHistory = ref(false)
const history = ref<CommentTask[]>([])
let pollTimer: ReturnType<typeof setInterval> | null = null

const form = reactive({
  class_name: '',
  term: '2025-2026学年第一学期',
  comment_type: 'semester',
  style: '',
  students: [{ name: '', keywords: '' }],
})

const rules = {
  class_name: [{ required: true, message: '请输入班级', trigger: 'blur' }],
  term: [{ required: true, message: '请输入学期', trigger: 'blur' }],
  comment_type: [{ required: true, message: '请选择评语类型', trigger: 'change' }],
}

function addStudent() {
  if (form.students.length < 60) {
    form.students.push({ name: '', keywords: '' })
  }
}

function removeStudent(idx: number) {
  form.students.splice(idx, 1)
}

function typeLabel(t: string) {
  const map: Record<string, string> = {
    semester: '学期评语',
    moral: '品德评语',
    parent: '家校沟通',
  }
  return map[t] || t
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
  const students = form.students
    .filter((s) => s.name && s.name.trim())
    .map((s) => ({ name: s.name.trim(), keywords: s.keywords.trim() }))
  if (students.length === 0) {
    ElMessage.warning('请至少填写一名学生姓名')
    return
  }
  await formRef.value.validate(async (valid: boolean) => {
    if (!valid) return
    submitting.value = true
    currentTask.value = null
    try {
      const data = await request.post<any>('/research_ai/comments', {
        class_name: form.class_name,
        term: form.term,
        comment_type: form.comment_type,
        students,
        style: form.style,
      })
      currentTask.value = data
      ElMessage.success('评语生成任务已提交')
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
  form.students = [{ name: '', keywords: '' }]
  currentTask.value = null
  stopPolling()
}

function startPolling(taskId: number) {
  stopPolling()
  pollTimer = setInterval(async () => {
    try {
      const data = await request.get<any>(`/research_ai/comments/${taskId}`)
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
    const data = await request.get<any[]>('/research_ai/comments', {
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
    const resp = await request.get(`/research_ai/comments/${id}/download`, {
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
    a.download = `comments_${id}.docx`
    a.click()
    window.URL.revokeObjectURL(url)
    ElMessage.success('下载已开始')
  } catch {
    ElMessage.error('下载失败')
  }
}

function viewTask(row: CommentTask) {
  currentTask.value = row
}

function handleRetry() {
  if (currentTask.value) {
    // V2.2.1：按原任务完整配置恢复（含 students 名单 + style），
    // 历史评语缺 students/style 时重试将退化为空名单——必须补齐
    const t = currentTask.value
    const students = (t.students || [])
      .map((s) => ({
        name: (s.name || '').trim(),
        keywords: (s.keywords || '').trim(),
      }))
      .filter((s) => s.name)
    Object.assign(form, {
      class_name: t.class_name,
      term: t.term,
      comment_type: t.comment_type,
      style: t.style || '',
      students: students.length ? students : [{ name: '', keywords: '' }],
    })
    handleSubmit()
  }
}

onMounted(() => {
  loadHistory()
})
</script>

<style scoped>
.comment-container {
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
.student-list {
  width: 100%;
}
.student-row {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
  align-items: center;
}
.student-count {
  margin-left: 12px;
  color: #999;
  font-size: 12px;
}
</style>
