<!--
  WINGS 教研 · 批量教案 AI 生成
  ==============================
  路径：frontend/src/views/research-ai/LessonPlanBatch.vue
  路由：/research-ai/lesson-plans
  依赖：Vue 3 + Element Plus + TypeScript + <script setup lang="ts">
  request 封装在 @/api/request（baseURL=/api/v1，interceptor 已 return response.data）
-->
<template>
  <div class="lesson-plan-batch">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>📚 批量教案 AI 生成</span>
          <el-tag type="info" size="small">AI 辅助 · 教师审阅为准</el-tag>
        </div>
      </template>

      <el-form :model="form" label-width="100px" class="task-form">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="任务名称">
              <el-input v-model="form.taskName" placeholder="如：七上第二周备课" maxlength="200" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label=" ">
              <el-button type="primary" @click="addRow" :icon="Plus">添加课题</el-button>
              <el-button @click="loadSample">载入示例</el-button>
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>

      <el-table :data="form.items" border stripe size="small" style="margin-bottom:16px;">
        <el-table-column type="index" label="#" width="50" />
        <el-table-column label="学科" width="100">
          <template #default="{ row }">
            <el-select v-model="row.subject" placeholder="学科" size="small">
              <el-option v-for="s in subjects" :key="s" :label="s" :value="s" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="教材" width="160">
          <template #default="{ row }">
            <el-input v-model="row.textbook" size="small" placeholder="人教版2024" />
          </template>
        </el-table-column>
        <el-table-column label="年级" width="150">
          <template #default="{ row }">
            <el-select v-model="row.grade" size="small">
              <el-option v-for="g in grades" :key="g" :label="g" :value="g" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="单元" width="180">
          <template #default="{ row }">
            <el-input v-model="row.unit" size="small" />
          </template>
        </el-table-column>
        <el-table-column label="课题" min-width="180">
          <template #default="{ row }">
            <el-input v-model="row.topic" size="small" placeholder="必填" />
          </template>
        </el-table-column>
        <el-table-column label="课时" width="80">
          <template #default="{ row }">
            <el-input-number v-model="row.periods" :min="1" :max="6" size="small" controls-position="right" />
          </template>
        </el-table-column>
        <el-table-column label="重点" width="140">
          <template #default="{ row }">
            <el-input v-model="row.key_point" size="small" placeholder="可空" />
          </template>
        </el-table-column>
        <el-table-column label="难点" width="140">
          <template #default="{ row }">
            <el-input v-model="row.diff_point" size="small" placeholder="可空" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="70" fixed="right">
          <template #default="{ $index }">
            <el-button type="danger" link size="small" @click="removeRow($index)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="actions">
        <el-button type="primary" size="large" @click="submitTask" :loading="submitting">
          🚀 提交批量生成（{{ form.items.length }}课）
        </el-button>
      </div>
    </el-card>

    <el-card shadow="never" style="margin-top:16px;">
      <template #header>
        <div class="card-header">
          <span>📋 生成任务记录</span>
          <el-button size="small" @click="loadTasks" :icon="Refresh">刷新</el-button>
        </div>
      </template>
      <el-table :data="tasks" border stripe size="small">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="task_name" label="任务名称" min-width="160" />
        <el-table-column label="进度" width="160">
          <template #default="{ row }">
            <el-progress :percentage="progressPct(row)" :status="progressStatus(row)" />
          </template>
        </el-table-column>
        <el-table-column label="数量" width="120">
          <template #default="{ row }">
            共{{ row.total_count }} · 成{{ row.success_count }} · 败{{ row.fail_count }}
          </template>
        </el-table-column>
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="170">
          <template #default="{ row }">{{ fmt(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="viewTask(row)">查看详情</el-button>
            <el-button v-if="row.status === 'completed' || row.status === 'partial_failed'"
                       type="primary" size="small" @click="downloadAll(row)">
              全部下载
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="detailVisible" :title="`任务详情 #${currentTask?.id}`" width="80%" top="5vh">
      <el-table :data="currentTask?.items || []" border size="small" max-height="500">
        <el-table-column prop="subject" label="学科" width="80" />
        <el-table-column prop="grade" label="年级" width="110" />
        <el-table-column prop="topic" label="课题" min-width="180" />
        <el-table-column prop="periods" label="课时" width="60" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="itemStatusType(row.status)" size="small">{{ itemStatusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="tokens" width="120">
          <template #default="{ row }">
            {{ row.prompt_tokens || '-' }} / {{ row.completion_tokens || '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="elapsed_sec" label="耗时(s)" width="80" />
        <el-table-column prop="error_msg" label="错误" min-width="200" show-overflow-tooltip />
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <el-button v-if="row.status === 'success'" type="primary" link size="small"
                       @click="downloadItem(row)">下载</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { Plus, Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import request from '@/api/request'

const subjects = ['语文', '数学', '英语', '物理', '化学', '生物', '历史', '地理', '道德与法治']
const grades = ['七年级上册', '七年级下册', '八年级上册', '八年级下册', '九年级上册', '九年级下册']

interface LessonItem {
  subject: string
  textbook?: string
  grade: string
  unit?: string
  topic: string
  periods: number
  key_point?: string
  diff_point?: string
}

const form = reactive({
  taskName: '',
  items: [] as LessonItem[],
})
const submitting = ref(false)
const tasks = ref<any[]>([])
const detailVisible = ref(false)
const currentTask = ref<any>(null)

function addRow() {
  form.items.push({
    subject: '数学',
    textbook: '人教版（2024版）',
    grade: '七年级上册',
    unit: '',
    topic: '',
    periods: 1,
    key_point: '',
    diff_point: '',
  })
}
function removeRow(i: number) {
  form.items.splice(i, 1)
}
function loadSample() {
  form.taskName = '示例备课任务'
  form.items = [
    { subject: '数学', textbook: '人教版（2024版）', grade: '七年级上册', unit: '第二章 有理数', topic: '有理数的乘方', periods: 1, key_point: '乘方的意义', diff_point: '符号法则' },
    { subject: '英语', textbook: '人教版 Go for it!', grade: '八年级上册', unit: 'Unit 3', topic: 'Section A 1a-2d', periods: 1, key_point: '形容词比较级', diff_point: '不规则变化' },
    { subject: '语文', textbook: '统编版', grade: '八年级上册', unit: '第三单元', topic: '背影', periods: 2, key_point: '朴实语言中的深情', diff_point: '以小见大' },
  ]
}

async function submitTask() {
  if (!form.taskName.trim()) {
    ElMessage.warning('请填写任务名称')
    return
  }
  if (!form.items.length) {
    ElMessage.warning('请至少添加一个课题')
    return
  }
  for (const it of form.items) {
    if (!it.topic.trim()) {
      ElMessage.warning('课题名不能为空')
      return
    }
  }
  submitting.value = true
  try {
    // request 已 return response.data，直接拿到任务对象
    await request.post('/research_ai/lesson-plans/batch', {
      task_name: form.taskName,
      items: form.items,
    })
    ElMessage.success('任务已提交，后台生成中…')
    form.taskName = ''
    form.items = []
    await loadTasks()
    pollTasks()
  } catch (e: any) {
    ElMessage.error(e?.message || '提交失败')
  } finally {
    submitting.value = false
  }
}

let pollTimer: any = null
function pollTasks() {
  if (pollTimer) clearInterval(pollTimer)
  let count = 0
  pollTimer = setInterval(async () => {
    count++
    await loadTasks()
    const allDone = tasks.value.every((t) =>
      ['completed', 'partial_failed', 'failed'].includes(t.status)
    )
    if (allDone || count >= 60) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }, 5000)
}

async function loadTasks() {
  try {
    // 后端返回 list[LessonTaskOut]
    const data = await request.get<any[]>('/research_ai/lesson-plans/batch', {
      params: { limit: 20 },
    })
    tasks.value = data || []
  } catch {
    /* ignore */
  }
}

async function viewTask(row: any) {
  try {
    const data = await request.get<any>(`/research_ai/lesson-plans/batch/${row.id}`)
    currentTask.value = data
    detailVisible.value = true
  } catch (e: any) {
    ElMessage.error(e?.message || '加载失败')
  }
}

function downloadItem(row: any) {
  // 下载端点带 JWT，需走 blob
  request
    .get(`/research_ai/lesson-plans/items/${row.id}/download`, {
      responseType: 'blob',
    })
    .then((resp: any) => {
      // interceptor 返回 response.data（即 Blob）
      const blob = resp instanceof Blob ? resp : new Blob([resp])
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${row.subject}_${row.grade}_${row.topic}.docx`
      a.click()
      URL.revokeObjectURL(url)
    })
}

function downloadAll(row: any) {
  row.items
    ?.filter((i: any) => i.status === 'success')
    .forEach((i: any, idx: number) => {
      setTimeout(() => downloadItem(i), idx * 800)
    })
}

function progressPct(row: any) {
  if (!row.total_count) return 0
  return Math.round(((row.success_count + row.fail_count) / row.total_count) * 100)
}
function progressStatus(row: any) {
  if (row.status === 'failed') return 'exception'
  if (row.status === 'partial_failed') return 'warning'
  if (row.status === 'completed') return 'success'
  return undefined
}
function statusType(s: string) {
  return (
    {
      pending: 'info',
      processing: 'warning',
      completed: 'success',
      partial_failed: 'warning',
      failed: 'danger',
    } as any
  )[s] || 'info'
}
function statusLabel(s: string) {
  return (
    {
      pending: '等待中',
      processing: '生成中',
      completed: '已完成',
      partial_failed: '部分失败',
      failed: '失败',
    } as any
  )[s] || s
}
function itemStatusType(s: string) {
  return ({ pending: 'info', processing: 'warning', success: 'success', failed: 'danger' } as any)[s]
}
function itemStatusLabel(s: string) {
  return ({ pending: '等待', processing: '生成中', success: '成功', failed: '失败' } as any)[s]
}
function fmt(s: string) {
  return s ? new Date(s).toLocaleString('zh-CN') : ''
}

onMounted(loadTasks)
</script>

<style scoped>
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.task-form {
  margin-bottom: 8px;
}
.actions {
  text-align: center;
  margin: 16px 0 8px;
}
</style>
