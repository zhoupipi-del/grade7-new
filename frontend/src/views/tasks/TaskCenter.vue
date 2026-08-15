<template>
  <div class="task-center">
    <!-- 顶部：标题 + 新建任务 -->
    <div class="tc-header">
      <div>
        <h2>任务中心 <span class="tc-sub">责任闭环底座 V1</span></h2>
        <p class="tc-tip">任务责任由系统按显式责任关系解析（不猜人）；已完成≠已复核</p>
      </div>
      <el-button type="primary" @click="openCreate">
        <el-icon><Plus /></el-icon> 新建任务
      </el-button>
    </div>

    <!-- 状态筛选 -->
    <el-radio-group v-model="statusFilter" class="tc-filter" @change="load">
      <el-radio-button value="">全部</el-radio-button>
      <el-radio-button value="pending">待处理</el-radio-button>
      <el-radio-button value="in_progress">进行中</el-radio-button>
      <el-radio-button value="completed">已完成</el-radio-button>
      <el-radio-button value="cancelled">已取消</el-radio-button>
    </el-radio-group>

    <!-- 列表 -->
    <el-card shadow="never">
      <el-table :data="tasks" v-loading="loading" empty-text="暂无任务">
        <el-table-column prop="title" label="任务" min-width="220">
          <template #default="{ row }">
            <el-link type="primary" @click="openDetail(row)">{{ row.title }}</el-link>
            <div v-if="row.description" class="tc-desc">{{ row.description }}</div>
          </template>
        </el-table-column>
        <el-table-column label="负责人" width="140">
          <template #default="{ row }">
            <template v-if="row.owner_user_id">
              <div>{{ row.owner_name_snapshot || `用户#${row.owner_user_id}` }}</div>
              <el-tag size="small" type="info" effect="plain">{{ roleLabel(row.responsibility_role) }}</el-tag>
            </template>
            <el-tag v-else size="small" type="warning">未分派</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="责任范围" width="140">
          <template #default="{ row }">
            <span v-if="row.responsibility_scope_type">
              {{ scopeLabel(row.responsibility_scope_type, row.responsibility_scope_id) }}
            </span>
            <el-tag v-else size="small" type="warning">{{ row.unresolved_reason || 'resolution_required' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" effect="light">{{ statusLabel(row.status) }}</el-tag>
            <el-tag v-if="row.status === 'completed'" size="small" :type="row.closure_status === 'verified' ? 'success' : 'info'" effect="plain">
              {{ row.closure_status === 'verified' ? '已复核' : '待复核' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="priority" label="优先级" width="90">
          <template #default="{ row }">{{ priorityLabel(row.priority) }}</template>
        </el-table-column>
        <el-table-column label="创建时间" width="150">
          <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="openDetail(row)">详情</el-button>
            <el-button v-if="canAct(row)" size="small" type="primary" plain @click="fastAction(row)">
              {{ fastActionLabel(row) }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 新建任务对话框 -->
    <el-dialog v-model="createVisible" title="新建责任任务" width="560px">
      <el-form label-width="90px">
        <el-form-item label="任务标题" required>
          <el-input v-model="createForm.title" maxlength="200" placeholder="如：跟进某学生连续缺勤问题" />
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="createForm.description" type="textarea" :rows="3" maxlength="2000" />
        </el-form-item>
        <el-form-item label="目标学生" required>
          <el-select
            v-model="createForm.student_id"
            filterable
            remote
            :remote-method="searchStudents"
            :loading="studentLoading"
            placeholder="搜索学生（系统将解析其班主任为负责人）"
            style="width: 100%"
          >
            <el-option
              v-for="s in studentOptions"
              :key="s.id"
              :label="`${s.name}（${s.class_name || `班${s.class_id}`}）`"
              :value="s.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="学科">
          <el-input v-model="createForm.subject" maxlength="32" placeholder="可选：填了则解析任课教师，留空解析班主任" />
        </el-form-item>
        <el-form-item label="优先级">
          <el-select v-model="createForm.priority" style="width: 180px">
            <el-option label="低" value="low" />
            <el-option label="正常" value="normal" />
            <el-option label="高" value="high" />
            <el-option label="紧急" value="urgent" />
          </el-select>
        </el-form-item>

        <!-- 责任解析预览 / 未配置责任人拦截（创建前先问 Resolver，未配置禁止 INSERT） -->
        <el-alert
          v-if="resolveError"
          type="warning"
          :closable="false"
          show-icon
          class="tc-resolve-alert"
        >
          <template #title>当前未配置责任人，无法创建任务</template>
          <div class="tc-resolve-msg">{{ resolveError }}</div>
          <el-button size="small" type="primary" plain class="tc-resolve-btn" @click="goOrgConfig">
            去组织与责任配置
          </el-button>
        </el-alert>
        <el-alert
          v-else-if="resolvePreview && resolvePreview.resolved"
          type="success"
          :closable="false"
          show-icon
          class="tc-resolve-alert"
        >
          <template #title>
            系统将把任务分派给：{{ resolvePreview.owner_name }}（{{ roleLabel(resolvePreview.role_type) }}）
          </template>
          <div class="tc-resolve-msg">点击「创建」即确认该责任分派并写入待办，确认前不会创建任何任务。</div>
        </el-alert>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="submitCreate">创建</el-button>
      </template>
    </el-dialog>

    <!-- 任务详情抽屉 -->
    <el-drawer v-model="detailVisible" :title="current?.title || '任务详情'" size="560px">
      <template v-if="current">
        <!-- 责任快照 -->
        <div class="tc-snapshot">
          <div class="tc-snapshot-title">责任快照（创建时由系统解析，调岗不影响历史）</div>
          <el-descriptions :column="2" size="small" border>
            <el-descriptions-item label="负责人">
              {{ current.owner_name_snapshot || (current.owner_user_id ? `用户#${current.owner_user_id}` : '未分派') }}
            </el-descriptions-item>
            <el-descriptions-item label="岗位">
              {{ roleLabel(current.responsibility_role) || current.unresolved_reason || 'resolution_required' }}
            </el-descriptions-item>
            <el-descriptions-item label="责任范围">
              {{ scopeLabel(current.responsibility_scope_type, current.responsibility_scope_id) }}
            </el-descriptions-item>
            <el-descriptions-item label="解析来源">
              {{ current.resolution_source || '—' }} / {{ current.resolution_confidence || '—' }}
            </el-descriptions-item>
          </el-descriptions>
        </div>

        <!-- 状态 -->
        <div class="tc-status-line">
          <el-tag :type="statusType(current.status)" effect="dark" size="large">{{ statusLabel(current.status) }}</el-tag>
          <el-tag v-if="current.status === 'completed'" :type="current.closure_status === 'verified' ? 'success' : 'info'" size="large">
            {{ current.closure_status === 'verified' ? '已复核' : '待复核（completed≠verified）' }}
          </el-tag>
        </div>

        <!-- 操作 -->
        <div class="tc-actions">
          <el-button v-if="current.status === 'pending'" type="primary" @click="act('start')">开始处理</el-button>
          <el-button
            v-if="current.status === 'in_progress'"
            type="success"
            @click="act('complete')"
          >完成（标记待复核）</el-button>
          <el-button v-if="['pending', 'in_progress'].includes(current.status)" type="danger" plain @click="act('cancel')">取消任务</el-button>
        </div>

        <!-- 证据 -->
        <div class="tc-block">
          <div class="tc-block-title">处理证据</div>
          <el-input v-model="evContent" type="textarea" :rows="2" placeholder="沟通记录 / 处理说明" />
          <div class="tc-inline">
            <el-select v-model="evKind" size="small" style="width: 160px">
              <el-option label="沟通记录" value="communication_record" />
              <el-option label="说明备注" value="note" />
            </el-select>
            <el-button type="primary" size="small" :loading="savingEv" @click="submitEvidence">提交证据</el-button>
          </div>
          <div v-for="e in current.evidence" :key="e.id" class="tc-evidence-item">
            <el-tag size="small" type="info">{{ e.kind }}</el-tag>
            <span>{{ e.content }}</span>
            <span class="tc-meta">{{ fmtTime(e.created_at) }}</span>
          </div>
          <div v-if="current.evidence.length === 0" class="tc-empty-hint">暂无证据</div>
        </div>

        <!-- 评论 -->
        <div class="tc-block">
          <div class="tc-block-title">评论</div>
          <div class="tc-inline">
            <el-input v-model="commentText" size="small" placeholder="补充说明…" @keyup.enter="submitComment" />
            <el-button size="small" type="primary" @click="submitComment">评论</el-button>
          </div>
          <div v-for="c in current.comments" :key="c.id" class="tc-comment-item">
            <span class="tc-meta">{{ fmtTime(c.created_at) }}：</span>{{ c.content }}
          </div>
        </div>

        <!-- 事件流 -->
        <div class="tc-block">
          <div class="tc-block-title">事件流（责任证据链）</div>
          <el-timeline>
            <el-timeline-item
              v-for="ev in current.events"
              :key="ev.id"
              :timestamp="fmtTime(ev.created_at)"
              :type="timelineType(ev.event_type)"
            >
              {{ eventLabel(ev.event_type) }} — {{ ev.actor_name || `用户#${ev.actor_user_id}` }}
            </el-timeline-item>
          </el-timeline>
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import {
  addComment, addEvidence, cancelTask, completeTask, createTask,
  getTaskStudents, listTasks, resolveResponsibility,
  type TaskItem, type TaskStudentOption, type TaskResolveOut,
  startTask,
} from '@/api/tasks'
import { useUserStore } from '@/store/user'

const userStore = useUserStore()
const router = useRouter()

const tasks = ref<TaskItem[]>([])
const loading = ref(false)
const statusFilter = ref('')
const createVisible = ref(false)
const creating = ref(false)
const detailVisible = ref(false)
const current = ref<TaskItem | null>(null)

const createForm = ref({ title: '', description: '', student_id: undefined as number | undefined, subject: '', priority: 'normal' })
const resolvePreview = ref<TaskResolveOut | null>(null)
const resolveError = ref('')
const studentOptions = ref<TaskStudentOption[]>([])
const studentLoading = ref(false)
const evContent = ref('')
const evKind = ref('communication_record')
const savingEv = ref(false)
const commentText = ref('')

async function load() {
  loading.value = true
  try {
    const r = await listTasks({ status: statusFilter.value || undefined })
    tasks.value = r.items
  } finally {
    loading.value = false
  }
}

function openCreate() {
  createForm.value = { title: '', description: '', student_id: undefined, subject: '', priority: 'normal' }
  studentOptions.value = []
  resolvePreview.value = null
  resolveError.value = ''
  createVisible.value = true
}

function goOrgConfig() {
  router.push({ name: 'OrgResponsibility' })
}

async function searchStudents(kw: string) {
  studentLoading.value = true
  try {
    studentOptions.value = await getTaskStudents()
  } finally {
    studentLoading.value = false
  }
}

async function submitCreate() {
  if (!createForm.value.title || !createForm.value.student_id) {
    ElMessage.warning('请填写标题并选择学生')
    return
  }
  creating.value = true
  resolveError.value = ''
  try {
    // ① 先问 Resolver：这件事归谁（不猜人）
    const r = await resolveResponsibility({
      student_id: createForm.value.student_id,
      subject: createForm.value.subject || undefined,
    })
    resolvePreview.value = r

    // ② 未配置责任人 → 拦截，禁止创建（绝不智能兜底）
    if (!r.resolved) {
      const reason = r.unresolved_reason || 'unresolved'
      if (reason === 'no_access') {
        resolveError.value = '当前账号无权为该范围创建任务（越权）。'
      } else if (reason === 'conflict') {
        resolveError.value = '该范围存在多个候选责任人，系统无法自动判定，请先在「组织与责任配置」中明确唯一责任人。'
      } else if (reason === 'invalid_request') {
        resolveError.value = '请选择学生或年级后再创建。'
      } else {
        resolveError.value = '未找到对应的责任 Assignment（班主任/年级组长/任课教师未配置），请先在「组织与责任配置」中补齐后再创建。'
      }
      return
    }

    // ③ 已解析 → 用户确认责任分派后才 INSERT
    try {
      await ElMessageBox.confirm(
        `系统将把任务分派给：${r.owner_name}（${roleLabel(r.role_type)}）\n确认创建该责任任务？`,
        '责任预览 · 确认创建',
        { type: 'info', confirmButtonText: '确认创建', cancelButtonText: '再想想' },
      )
    } catch {
      return // 用户取消，不创建
    }

    const t = await createTask({
      title: createForm.value.title,
      description: createForm.value.description || undefined,
      priority: createForm.value.priority,
      student_id: createForm.value.student_id,
      subject: createForm.value.subject || undefined,
      source_type: 'student',
      source_id: createForm.value.student_id,
    })
    ElMessage.success(`已创建，负责人：${t.owner_name_snapshot || r.owner_name}`)
    createVisible.value = false
    load()
  } catch (e: any) {
    ElMessage.error(e?.detail || e?.message || '创建失败')
  } finally {
    creating.value = false
  }
}

async function openDetail(row: TaskItem) {
  const fresh = await import('@/api/tasks').then((m) => m.getTask(row.id))
  current.value = fresh
  detailVisible.value = true
}

function canAct(row: TaskItem): boolean {
  if (row.status === 'completed' || row.status === 'cancelled') return false
  const me = userStore.userInfo?.id
  return row.owner_user_id === me
}

function fastActionLabel(row: TaskItem): string {
  if (row.status === 'pending') return '开始'
  return '完成'
}

async function fastAction(row: TaskItem) {
  if (row.status === 'pending') await act('start', row.id)
  else await act('complete', row.id)
}

async function act(kind: string, id?: number) {
  const tid = id ?? current.value?.id
  if (!tid) return
  try {
    let msg = ''
    if (kind === 'start') { await startTask(tid); msg = '已开始处理' }
    if (kind === 'complete') {
      const { value } = await ElMessageBox.prompt('处理结果（必填，将写入任务并标记待复核）', '完成任务', { inputType: 'textarea' })
      if (!value || !value.trim()) { ElMessage.warning('请填写处理结果'); return }
      await completeTask(tid, value.trim()); msg = '已完成（待复核）'
    }
    if (kind === 'cancel') {
      const { value } = await ElMessageBox.prompt('取消原因', '取消任务')
      await cancelTask(tid, value); msg = '已取消'
    }
    ElMessage.success(msg)
    detailVisible.value = false
    load()
  } catch (e: any) {
    if (e === 'cancel' || e?.action === 'cancel') return
    ElMessage.error(e?.detail || '操作失败')
  }
}

async function submitEvidence() {
  const tid = current.value?.id
  if (!tid || !evContent.value.trim()) { ElMessage.warning('请填写证据内容'); return }
  savingEv.value = true
  try {
    current.value = await addEvidence(tid, { kind: evKind.value, content: evContent.value.trim() })
    evContent.value = ''
    ElMessage.success('证据已提交')
  } finally {
    savingEv.value = false
  }
}

async function submitComment() {
  const tid = current.value?.id
  if (!tid || !commentText.value.trim()) return
  current.value = await addComment(tid, commentText.value.trim())
  commentText.value = ''
}

function statusLabel(s: string): string {
  return ({ pending: '待处理', in_progress: '进行中', completed: '已完成', cancelled: '已取消' } as Record<string, string>)[s] || s
}
function statusType(s: string): any {
  return ({ pending: 'warning', in_progress: 'info', completed: 'success', cancelled: 'info' } as Record<string, any>)[s] || 'info'
}
function roleLabel(r: string | null): string {
  return ({ homeroom_teacher: '班主任', grade_leader: '年级组长', subject_teacher: '任课教师', counselor: '心理负责人', moral_admin: '德育处' } as Record<string, string>)[r || ''] || r || ''
}
function scopeLabel(t: string | null, id: number | null): string {
  if (!t) return '—'
  return `${({ class: '班级', grade: '年级', school: '全校' } as Record<string, string>)[t] || t} ${id ?? ''}`.trim()
}
function priorityLabel(p: string): string {
  return ({ low: '低', normal: '正常', high: '高', urgent: '紧急' } as Record<string, string>)[p] || p
}
function eventLabel(e: string): string {
  return ({ created: '创建', started: '开始处理', completed: '完成', cancelled: '取消', reassigned: '转交', evidence_added: '提交证据', comment_added: '评论' } as Record<string, string>)[e] || e
}
function timelineType(e: string): any {
  return ({ completed: 'success', cancelled: 'info', created: 'primary', started: 'primary', reassigned: 'warning' } as Record<string, any>)[e] || 'primary'
}
function fmtTime(t: string | null): string {
  return t ? t.replace('T', ' ').slice(0, 16) : '—'
}

onMounted(load)
</script>

<style scoped>
.task-center { padding: 4px 8px; }
.tc-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.tc-sub { font-size: 12px; color: #909399; font-weight: normal; margin-left: 6px; }
.tc-tip { font-size: 12px; color: #909399; margin: 4px 0 0; }
.tc-filter { margin-bottom: 12px; }
.tc-desc { font-size: 12px; color: #909399; margin-top: 2px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 360px; }
.tc-snapshot { background: #f5f7fa; border-radius: 6px; padding: 10px; margin-bottom: 12px; }
.tc-snapshot-title { font-size: 12px; color: #909399; margin-bottom: 8px; }
.tc-status-line { margin-bottom: 12px; }
.tc-actions { margin-bottom: 12px; }
.tc-block { margin-bottom: 16px; }
.tc-block-title { font-size: 13px; font-weight: 600; margin-bottom: 8px; color: #303133; }
.tc-inline { display: flex; gap: 8px; margin: 8px 0; }
.tc-evidence-item, .tc-comment-item { font-size: 13px; padding: 6px 0; border-bottom: 1px dashed #ebeef5; }
.tc-meta { color: #909399; font-size: 12px; }
.tc-empty-hint { color: #c0c4cc; font-size: 12px; padding: 6px 0; }
.tc-resolve-alert { margin-bottom: 0; }
.tc-resolve-msg { font-size: 12px; color: #606266; margin-top: 4px; }
.tc-resolve-btn { margin-top: 8px; }
</style>
