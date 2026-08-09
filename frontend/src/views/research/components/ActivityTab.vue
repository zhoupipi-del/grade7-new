<template>
  <div class="activity-tab">
    <!-- 工具栏 -->
    <div class="toolbar">
      <el-select v-model="filters.activity_type" placeholder="活动类型" clearable style="width: 130px" @change="loadList">
        <el-option label="常规教研会" value="regular_meeting" />
        <el-option label="课例研究" value="lesson_study" />
        <el-option label="专题研讨" value="thematic_research" />
        <el-option label="年级组会" value="grade_meeting" />
        <el-option label="跨年级教研" value="cross_grade" />
        <el-option label="培训活动" value="training" />
      </el-select>
      <el-select v-model="filters.status" placeholder="状态" clearable style="width: 120px" @change="loadList">
        <el-option label="已计划" value="planned" />
        <el-option label="进行中" value="in_progress" />
        <el-option label="已完成" value="completed" />
        <el-option label="已取消" value="cancelled" />
      </el-select>
      <div class="flex-spacer" />
      <el-button type="primary" :icon="Plus" @click="showCreateDialog = true">新建活动</el-button>
    </div>

    <!-- 活动列表 -->
    <el-table :data="items" v-loading="loading" stripe @row-click="(row: any) => openDetail(row)" style="width: 100%">
      <el-table-column label="活动标题" min-width="220">
        <template #default="{ row }">
          <div class="act-title">{{ row.title }}</div>
          <div class="act-sub">{{ activityTypeLabel(row.activity_type) }}</div>
        </template>
      </el-table-column>
      <el-table-column label="学科" width="80" :formatter="(_, __, row) => subjectLabel(row.subject_code)" />
      <el-table-column label="状态" width="100" align="center">
        <template #default="{ row }">
          <el-tag :type="activityStatusTag(row.status)" size="small">{{ activityStatusLabel(row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="参与人" width="80" align="center" prop="participant_count" />
      <el-table-column label="议题" width="70" align="center" prop="agenda_count" />
      <el-table-column label="组织者" width="100" prop="organizer_name" />
      <el-table-column label="计划时间" width="160">
        <template #default="{ row }">{{ formatTime(row.planned_at) }}</template>
      </el-table-column>
      <el-table-column label="地点" width="120" prop="location" show-overflow-tooltip />
      <el-table-column label="操作" width="80" align="center">
        <template #default="{ row }">
          <el-button size="small" link type="primary" @click.stop="openDetail(row)">详情</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="pagination-row">
      <el-pagination
        v-model:current-page="filters.page"
        v-model:page-size="filters.page_size"
        :total="total"
        :page-sizes="[10, 20, 50]"
        layout="total, sizes, prev, pager, next"
        @size-change="loadList"
        @current-change="loadList"
      />
    </div>

    <!-- 详情抽屉 -->
    <el-drawer v-model="detailVisible" size="60%" :title="currentDetail?.title || '活动详情'" destroy-on-close>
      <template v-if="currentDetail">
        <div class="detail-content">
          <!-- 元信息 -->
          <div class="meta-bar">
            <el-tag>{{ activityTypeLabel(currentDetail.activity_type) }}</el-tag>
            <el-tag type="info">{{ subjectLabel(currentDetail.subject_code) }}</el-tag>
            <el-tag v-if="currentDetail.grade_level" type="info">{{ currentDetail.grade_level }}</el-tag>
            <el-tag v-if="currentDetail.location" type="info">{{ currentDetail.location }}</el-tag>
          </div>
          <div class="meta-info-row">
            <span>组织者: <strong>{{ currentDetail.organizer_name || '—' }}</strong></span>
            <span>计划时间: <strong>{{ formatTime(currentDetail.planned_at) }}</strong></span>
            <span v-if="currentDetail.planned_end_at">结束: <strong>{{ formatTime(currentDetail.planned_end_at) }}</strong></span>
          </div>
          <div v-if="currentDetail.description" class="act-description">{{ currentDetail.description }}</div>

          <!-- 状态流水线 -->
          <div class="pipeline-section">
            <el-steps :active="activityStep" align-center finish-status="success" process-status="process">
              <el-step title="已计划" :description="currentDetail.status === 'planned' ? '当前' : ''" />
              <el-step title="进行中" :description="currentDetail.status === 'in_progress' ? '当前' : ''" />
              <el-step title="已完成" :description="currentDetail.status === 'completed' ? '已完成' : ''" />
            </el-steps>
            <el-tag v-if="currentDetail.status === 'cancelled'" type="danger" class="cancelled-tag">已取消: {{ currentDetail.cancel_reason || '未说明' }}</el-tag>
          </div>

          <!-- 操作按钮 -->
          <div class="action-bar" v-if="canManageCurrent">
            <el-button v-if="currentDetail.status === 'planned'" type="primary" :icon="VideoPlay" @click="doStart">启动活动</el-button>
            <el-button v-if="currentDetail.status === 'in_progress'" type="success" :icon="CircleCheckFilled" @click="doComplete">完成活动</el-button>
            <el-button v-if="currentDetail.status === 'planned'" type="danger" plain :icon="CircleClose" @click="doCancel">取消活动</el-button>
            <el-button :icon="Plus" @click="showAgendaDialog = true">添加议题</el-button>
            <el-button :icon="User" @click="showParticipantDialog = true">添加参与人</el-button>
          </div>

          <!-- 双向血缘 -->
          <div v-if="currentDetail.linked_plan_ids?.length || currentDetail.linked_observation_ids?.length" class="link-section">
            <span class="link-label">关联资源:</span>
            <el-tag v-for="pid in currentDetail.linked_plan_ids" :key="'p'+pid" size="small" type="primary" effect="plain">教案#{{ pid }}</el-tag>
            <el-tag v-for="oid in currentDetail.linked_observation_ids" :key="'o'+oid" size="small" type="warning" effect="plain">听课#{{ oid }}</el-tag>
          </div>

          <!-- 议题列表 -->
          <div class="section">
            <h3 class="section-title">议题议程 ({{ currentDetail.agendas?.length || 0 }})</h3>
            <div v-if="currentDetail.agendas?.length" class="agenda-list">
              <div v-for="a in currentDetail.agendas" :key="a.id" class="agenda-item">
                <div class="agenda-head">
                  <span class="agenda-seq">#{{ a.seq }}</span>
                  <span class="agenda-title">{{ a.title }}</span>
                  <el-tag :type="agendaStatusTag(a.status)" size="small">{{ agendaStatusLabel(a.status) }}</el-tag>
                  <span v-if="a.planned_duration" class="agenda-duration">{{ a.planned_duration }}分钟</span>
                  <span v-if="a.actual_duration" class="agenda-actual">实际{{ a.actual_duration }}分钟</span>
                </div>
                <p v-if="a.content" class="agenda-content">{{ a.content }}</p>
                <p v-if="a.presenter_name" class="agenda-presenter">主讲: {{ a.presenter_name }}</p>
                <div v-if="a.decision" class="agenda-decision">
                  <el-icon><CircleCheck /></el-icon> {{ a.decision }}
                </div>
                <div v-if="a.linked_plan_id || a.linked_observation_id" class="agenda-links">
                  <el-tag v-if="a.linked_plan_id" size="small" effect="plain">教案#{{ a.linked_plan_id }}</el-tag>
                  <el-tag v-if="a.linked_observation_id" size="small" effect="plain">听课#{{ a.linked_observation_id }}</el-tag>
                </div>
              </div>
            </div>
            <el-empty v-else description="暂无议题" :image-size="60" />
          </div>

          <!-- 参与人员 -->
          <div class="section">
            <h3 class="section-title">参与人员 ({{ currentDetail.participants?.length || 0 }})</h3>
            <el-table v-if="currentDetail.participants?.length" :data="currentDetail.participants" border size="small">
              <el-table-column label="姓名" prop="user_name" width="100" />
              <el-table-column label="角色" width="90">
                <template #default="{ row }">
                  <el-tag :type="participantRoleTag(row.role)" size="small">{{ participantRoleLabel(row.role) }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="考勤" width="90" align="center">
                <template #default="{ row }">
                  <el-tag :type="attendanceStatusTag(row.attendance_status)" size="small">{{ attendanceStatusLabel(row.attendance_status) }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="签到时间" width="140">
                <template #default="{ row }">{{ formatTime(row.check_in_at) }}</template>
              </el-table-column>
              <el-table-column label="签退时间" width="140">
                <template #default="{ row }">{{ formatTime(row.check_out_at) }}</template>
              </el-table-column>
              <el-table-column label="贡献度" width="80" align="center">
                <template #default="{ row }">
                  <span v-if="row.contribution_score" class="contribution">{{ '★'.repeat(row.contribution_score) }}</span>
                  <span v-else>—</span>
                </template>
              </el-table-column>
              <el-table-column label="备注" prop="note" min-width="120" show-overflow-tooltip />
            </el-table>
            <el-empty v-else description="暂无参与人" :image-size="60" />
          </div>

          <!-- 决议 -->
          <div v-if="currentDetail.decisions?.length" class="section">
            <h3 class="section-title">活动决议</h3>
            <ul class="decisions-list">
              <li v-for="(d, i) in currentDetail.decisions" :key="i">{{ d }}</li>
            </ul>
          </div>
          <div v-if="currentDetail.summary" class="section">
            <h3 class="section-title">活动总结</h3>
            <p class="summary-text">{{ currentDetail.summary }}</p>
          </div>
        </div>
      </template>
    </el-drawer>

    <!-- 新建活动弹窗 -->
    <el-dialog v-model="showCreateDialog" title="新建教研活动" width="600px" destroy-on-close>
      <el-form :model="createForm" label-width="100px">
        <el-form-item label="标题" required>
          <el-input v-model="createForm.title" placeholder="活动标题" maxlength="200" />
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="活动类型">
              <el-select v-model="createForm.activity_type" style="width: 100%">
                <el-option label="常规教研会" value="regular_meeting" />
                <el-option label="课例研究" value="lesson_study" />
                <el-option label="专题研讨" value="thematic_research" />
                <el-option label="年级组会" value="grade_meeting" />
                <el-option label="跨年级教研" value="cross_grade" />
                <el-option label="培训活动" value="training" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="学科" required>
              <el-select v-model="createForm.subject_code" style="width: 100%">
                <el-option v-for="s in subjectOptions" :key="s.value" :label="s.label" :value="s.value" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="年级">
              <el-input v-model="createForm.grade_level" placeholder="如: 初一" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="地点">
              <el-input v-model="createForm.location" placeholder="活动地点" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="开始时间" required>
              <el-date-picker v-model="createForm.planned_at" type="datetime" placeholder="选择时间" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="结束时间">
              <el-date-picker v-model="createForm.planned_end_at" type="datetime" placeholder="选择时间" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="描述">
          <el-input v-model="createForm.description" type="textarea" :rows="2" placeholder="活动简介" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="doCreate">创建</el-button>
      </template>
    </el-dialog>

    <!-- 添加议题弹窗 -->
    <el-dialog v-model="showAgendaDialog" title="添加议题" width="500px" destroy-on-close>
      <el-form :model="agendaForm" label-width="100px">
        <el-form-item label="议题标题" required>
          <el-input v-model="agendaForm.title" placeholder="议题标题" />
        </el-form-item>
        <el-form-item label="主讲人ID">
          <el-input-number v-model="agendaForm.presenter_id" :min="1" />
        </el-form-item>
        <el-form-item label="计划时长">
          <el-input-number v-model="agendaForm.planned_duration" :min="1" :max="300" />
        </el-form-item>
        <el-form-item label="议题内容">
          <el-input v-model="agendaForm.content" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="关联教案ID">
          <el-input-number v-model="agendaForm.linked_plan_id" :min="1" />
        </el-form-item>
        <el-form-item label="关联听课ID">
          <el-input-number v-model="agendaForm.linked_observation_id" :min="1" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAgendaDialog = false">取消</el-button>
        <el-button type="primary" :loading="agendaSaving" @click="doAddAgenda">添加</el-button>
      </template>
    </el-dialog>

    <!-- 添加参与人弹窗 -->
    <el-dialog v-model="showParticipantDialog" title="添加参与人" width="400px" destroy-on-close>
      <el-form :model="participantForm" label-width="100px">
        <el-form-item label="用户ID" required>
          <el-input-number v-model="participantForm.user_id" :min="1" />
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="participantForm.role" style="width: 100%">
            <el-option label="组织者" value="organizer" />
            <el-option label="主讲人" value="presenter" />
            <el-option label="记录员" value="recorder" />
            <el-option label="参与者" value="participant" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showParticipantDialog = false">取消</el-button>
        <el-button type="primary" :loading="participantSaving" @click="doAddParticipant">添加</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, VideoPlay, CircleCheckFilled, CircleClose, CircleCheck, User } from '@element-plus/icons-vue'
import { useUserStore } from '@/store/user'
import * as actApi from '@/api/researchActivities'
import type { ActivityResponse, ActivityDetailResponse, ActivityStatus, ActivityType } from '@/api/researchActivities'
import { activityStatusTag, activityStatusLabel, activityTypeLabel, participantRoleLabel, participantRoleTag, attendanceStatusLabel, attendanceStatusTag, agendaStatusLabel, agendaStatusTag } from '@/api/researchActivities'

const userStore = useUserStore()
const userRole = computed(() => userStore.currentRole || '')
const canManage = computed(() => ['MS_ADMIN', 'GRADE_LEADER', 'CLASS_TEACHER'].includes(userRole.value as string))
const canManageCurrent = computed(() => {
  if (!currentDetail.value) return false
  if (['MS_ADMIN', 'GRADE_LEADER'].includes(userRole.value as string)) return true
  return currentDetail.value.organizer_id === userStore.userInfo?.id
})

/* ──── 列表 ──── */
const loading = ref(false)
const items = ref<ActivityResponse[]>([])
const total = ref(0)
const filters = reactive({ activity_type: '', status: '', page: 1, page_size: 20 })

async function loadList() {
  loading.value = true
  try {
    const params: actApi.ListParams = { page: filters.page, page_size: filters.page_size }
    if (filters.activity_type) params.activity_type = filters.activity_type as ActivityType
    if (filters.status) params.status = filters.status as ActivityStatus
    const res = await actApi.listActivities(params)
    items.value = res.items || []
    total.value = res.total || 0
  } catch (e: any) { ElMessage.error(e.message || '加载失败') }
  finally { loading.value = false }
}

/* ──── 详情 ──── */
const detailVisible = ref(false)
const currentDetail = ref<ActivityDetailResponse | null>(null)

const activityStep = computed(() => {
  if (!currentDetail.value) return 0
  const map: Record<ActivityStatus, number> = { planned: 0, in_progress: 1, completed: 2, cancelled: 0 }
  return map[currentDetail.value.status] ?? 0
})

async function openDetail(row: any) {
  detailVisible.value = true
  currentDetail.value = null
  try { currentDetail.value = await actApi.getActivity(row.id) }
  catch (e: any) { ElMessage.error(e.message || '加载详情失败') }
}

/* ──── 状态机操作 ──── */
async function doStart() {
  if (!currentDetail.value) return
  try {
    await ElMessageBox.confirm('确认启动此活动?', '启动', { type: 'info' })
    await actApi.startActivity(currentDetail.value.id)
    ElMessage.success('活动已启动')
    await refreshDetail()
  } catch (e: any) { if (e !== 'cancel') ElMessage.error(e.message || '操作失败') }
}

async function doComplete() {
  if (!currentDetail.value) return
  try {
    await ElMessageBox.confirm('确认完成此活动?', '完成', { type: 'success' })
    await actApi.completeActivity(currentDetail.value.id)
    ElMessage.success('活动已完成')
    await refreshDetail()
  } catch (e: any) { if (e !== 'cancel') ElMessage.error(e.message || '操作失败') }
}

async function doCancel() {
  if (!currentDetail.value) return
  try {
    const { value } = await ElMessageBox.prompt('请输入取消原因', '取消活动', {
      type: 'warning', inputPlaceholder: '取消原因（可选）',
    })
    await actApi.cancelActivity(currentDetail.value.id, { cancel_reason: value || '' })
    ElMessage.success('活动已取消')
    await refreshDetail()
  } catch (e: any) { if (e !== 'cancel') ElMessage.error(e.message || '操作失败') }
}

/* ──── 新建活动 ──── */
const showCreateDialog = ref(false)
const creating = ref(false)
const createForm = reactive({
  title: '', description: '', activity_type: 'regular_meeting' as ActivityType,
  subject_code: '', grade_level: '', planned_at: '', planned_end_at: '', location: '',
})

async function doCreate() {
  if (!createForm.title || !createForm.subject_code || !createForm.planned_at) {
    ElMessage.warning('请填写必填项')
    return
  }
  creating.value = true
  try {
    await actApi.createActivity({
      title: createForm.title,
      description: createForm.description || undefined,
      activity_type: createForm.activity_type,
      subject_code: createForm.subject_code,
      grade_level: createForm.grade_level || undefined,
      planned_at: createForm.planned_at,
      planned_end_at: createForm.planned_end_at || undefined,
      location: createForm.location || undefined,
    })
    ElMessage.success('活动已创建')
    showCreateDialog.value = false
    createForm.title = ''; createForm.description = ''; createForm.subject_code = ''
    createForm.grade_level = ''; createForm.planned_at = ''; createForm.planned_end_at = ''; createForm.location = ''
    await loadList()
  } catch (e: any) { ElMessage.error(e.message || '创建失败') }
  finally { creating.value = false }
}

/* ──── 议题 ──── */
const showAgendaDialog = ref(false)
const agendaSaving = ref(false)
const agendaForm = reactive({ title: '', presenter_id: 0, content: '', planned_duration: 30, linked_plan_id: 0, linked_observation_id: 0 })

async function doAddAgenda() {
  if (!currentDetail.value || !agendaForm.title) { ElMessage.warning('请填写议题标题'); return }
  agendaSaving.value = true
  try {
    await actApi.createAgenda(currentDetail.value.id, {
      title: agendaForm.title,
      presenter_id: agendaForm.presenter_id || undefined,
      content: agendaForm.content || undefined,
      planned_duration: agendaForm.planned_duration,
      linked_plan_id: agendaForm.linked_plan_id || undefined,
      linked_observation_id: agendaForm.linked_observation_id || undefined,
    })
    ElMessage.success('议题已添加')
    showAgendaDialog.value = false
    agendaForm.title = ''; agendaForm.content = ''; agendaForm.presenter_id = 0; agendaForm.linked_plan_id = 0; agendaForm.linked_observation_id = 0
    await refreshDetail()
  } catch (e: any) { ElMessage.error(e.message || '添加失败') }
  finally { agendaSaving.value = false }
}

/* ──── 参与人 ──── */
const showParticipantDialog = ref(false)
const participantSaving = ref(false)
const participantForm = reactive({ user_id: 0, role: 'participant' as const })

async function doAddParticipant() {
  if (!currentDetail.value || !participantForm.user_id) { ElMessage.warning('请填写用户ID'); return }
  participantSaving.value = true
  try {
    await actApi.addParticipant(currentDetail.value.id, {
      user_id: participantForm.user_id,
      role: participantForm.role,
    })
    ElMessage.success('参与人已添加')
    showParticipantDialog.value = false
    participantForm.user_id = 0
    await refreshDetail()
  } catch (e: any) { ElMessage.error(e.message || '添加失败') }
  finally { participantSaving.value = false }
}

/* ──── 工具 ──── */
async function refreshDetail() {
  if (!currentDetail.value) return
  try { currentDetail.value = await actApi.getActivity(currentDetail.value.id) } catch {}
  await loadList()
}
function formatTime(s: string): string { return s ? s.replace('T', ' ').slice(0, 16) : '—' }
function subjectLabel(code: string): string {
  const map: Record<string, string> = { chinese: '语文', math: '数学', english: '英语', physics: '物理', chemistry: '化学', biology: '生物', politics: '政治', history: '历史', geography: '地理' }
  return map[code] || code || '—'
}
const subjectOptions = Object.entries({ chinese: '语文', math: '数学', english: '英语', physics: '物理', chemistry: '化学', biology: '生物', politics: '政治', history: '历史', geography: '地理' }).map(([value, label]) => ({ value, label }))

onMounted(loadList)
</script>

<style scoped>
.activity-tab { padding: 0 4px; }
.toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.flex-spacer { flex: 1; }
.act-title { font-weight: 600; }
.act-sub { font-size: 12px; color: var(--el-text-color-secondary); }
.pagination-row { margin-top: 16px; display: flex; justify-content: flex-end; }

.detail-content { padding: 0 8px; }
.meta-bar { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
.meta-info-row { display: flex; gap: 24px; margin-bottom: 12px; font-size: 14px; color: var(--el-text-color-secondary); }
.act-description { margin-bottom: 16px; line-height: 1.6; color: var(--el-text-color-regular); }
.pipeline-section { margin-bottom: 20px; padding: 20px; background: var(--el-fill-color-light); border-radius: 8px; }
.cancelled-tag { margin-top: 12px; }
.action-bar { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 24px; padding-bottom: 20px; border-bottom: 1px solid var(--el-border-color-lighter); }
.link-section { display: flex; align-items: center; gap: 8px; margin-bottom: 20px; }
.link-label { font-size: 13px; color: var(--el-text-color-secondary); }

.section { margin-bottom: 28px; }
.section-title { font-size: 16px; font-weight: 600; margin: 0 0 12px; }

.agenda-list { display: flex; flex-direction: column; gap: 12px; }
.agenda-item { padding: 12px 16px; border-radius: 8px; background: var(--el-fill-color-light); border-left: 3px solid var(--el-color-primary); }
.agenda-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.agenda-seq { font-weight: 700; color: var(--el-color-primary); }
.agenda-title { font-weight: 600; }
.agenda-duration, .agenda-actual { font-size: 12px; color: var(--el-text-color-secondary); }
.agenda-content { margin: 8px 0; line-height: 1.6; }
.agenda-presenter { font-size: 13px; color: var(--el-text-color-secondary); }
.agenda-decision { display: flex; align-items: center; gap: 6px; font-size: 13px; color: var(--el-color-success); margin-top: 8px; }
.agenda-links { display: flex; gap: 6px; margin-top: 8px; }

.contribution { color: var(--el-color-warning); }
.decisions-list { margin: 0; padding-left: 20px; }
.decisions-list li { margin-bottom: 6px; line-height: 1.6; }
.summary-text { line-height: 1.8; }
</style>
