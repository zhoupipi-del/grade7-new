<template>
  <div class="intervention-page">
    <!-- 页头 -->
    <div class="page-hero">
      <div class="hero-left">
        <el-button :icon="ArrowLeft" size="small" text @click="$router.push('/psych-screening')" class="back-btn">
          返回总览
        </el-button>
        <h1 class="hero-title">干预记录与危机管理</h1>
      </div>
      <el-button type="warning" :icon="Plus" size="large" round @click="showCreateDialog">
        新建干预记录
      </el-button>
    </div>

    <!-- KPI 条 -->
    <div class="stats-bar">
      <div class="stat-chip total">
        <span class="chip-val">{{ stats.total }}</span>
        <span class="chip-lbl">干预总数</span>
      </div>
      <div class="stat-chip pending">
        <span class="chip-val">{{ stats.pending }}</span>
        <span class="chip-lbl">待处理</span>
      </div>
      <div class="stat-chip progress">
        <span class="chip-val">{{ stats.inProgress }}</span>
        <span class="chip-lbl">进行中</span>
      </div>
      <div class="stat-chip done">
        <span class="chip-val">{{ stats.completed }}</span>
        <span class="chip-lbl">已完成</span>
      </div>
      <div class="stat-chip crisis">
        <span class="chip-val">{{ stats.crisis }}</span>
        <span class="chip-lbl">危机个案</span>
      </div>
    </div>

    <!-- 筛选 + 列表 -->
    <div class="content-card">
      <div class="filter-bar">
        <el-radio-group v-model="filterStatus" size="small" @change="loadList">
          <el-radio-button value="">全部</el-radio-button>
          <el-radio-button value="pending">待处理</el-radio-button>
          <el-radio-button value="tracking">进行中</el-radio-button>
          <el-radio-button value="completed">已完成</el-radio-button>
        </el-radio-group>
        <el-input v-model="searchKeyword" placeholder="搜索学生姓名..." size="small" clearable style="width: 200px; margin-left: 12px" @input="loadList" />
      </div>

      <div class="intervention-grid" v-loading="loading">
        <div
          v-for="item in displayList"
          :key="item.id"
          class="intv-card"
          :class="'card-' + (item.mh_risk_before || 'low')"
        >
          <div class="card-top">
            <div class="card-student">
              <span class="student-name">{{ item.student_name }}</span>
              <span class="student-class">{{ item.class_name }}</span>
            </div>
            <div class="card-badges">
              <span class="badge-risk" :class="'risk-' + (item.mh_risk_before || 'low')">
                {{ (RISK_LABELS as any)[item.mh_risk_before] || item.mh_risk_before }}
              </span>
              <span class="badge-status" :class="'status-' + (item.status || 'pending')">
                {{ STATUS_LABELS[item.status] || item.status }}
              </span>
            </div>
          </div>

          <div class="card-body">
            <div class="card-row">
              <span class="row-label">干预类型</span>
              <span class="row-value">{{ TYPE_LABELS[item.intervention_type] || item.intervention_type }}</span>
            </div>
            <div class="card-row" v-if="item.teacher_name">
              <span class="row-label">负责人</span>
              <span class="row-value">{{ item.teacher_name }}</span>
            </div>
            <div class="card-row" v-if="item.intervention_date">
              <span class="row-label">日期</span>
              <span class="row-value">{{ item.intervention_date }}</span>
            </div>
            <div class="card-notes" v-if="item.notes">
              {{ item.notes }}
            </div>
            <div class="card-row" v-if="item.effect_rating">
              <span class="row-label">效果</span>
              <span class="effect-badge" :class="'effect-' + item.effect_rating">
                {{ EFFECT_LABELS[item.effect_rating] || item.effect_rating }}
              </span>
            </div>
          </div>

          <div class="card-actions">
            <el-button size="small" type="primary" link @click="showFollowup(item)" class="action-link">随访</el-button>
            <el-button size="small" type="info" link @click="showTimeline(item)" class="action-link">时间线</el-button>
            <el-button
              v-if="item.status === 'pending'"
              size="small" type="warning"
              @click="startIntervention(item)"
            >开始干预</el-button>
            <el-button
              v-if="item.status === 'tracking'"
              size="small" type="success"
              @click="completeIntervention(item)"
            >标记完成</el-button>
          </div>
        </div>

        <div v-if="!loading && displayList.length === 0" class="empty-placeholder">
          <el-icon :size="48" class="empty-icon"><FirstAidKit /></el-icon>
          <div class="empty-text">暂无干预记录</div>
          <div class="empty-sub">高危/中危筛查会自动触发干预建议</div>
        </div>
      </div>
    </div>

    <!-- 新建干预弹窗 -->
    <el-dialog v-model="createVisible" title="新建干预记录" width="520px" destroy-on-close class="dark-dialog">
      <el-form :model="createForm" label-width="85px" label-position="left">
        <el-form-item label="学生">
          <el-select v-model="createForm.student_id" filterable remote :remote-method="searchStudents" placeholder="搜索学生姓名" style="width: 100%" :loading="searchingStudent">
            <el-option v-for="s in studentOptions" :key="s.id" :label="`${s.name} - ${s.class_name}`" :value="s.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="风险等级">
          <el-select v-model="createForm.severity" style="width: 100%">
            <el-option label="低风险" value="low" />
            <el-option label="中风险" value="medium" />
            <el-option label="高风险" value="high" />
            <el-option label="极高风险" value="critical" />
          </el-select>
        </el-form-item>
        <el-form-item label="干预类型">
          <el-select v-model="createForm.intervention_type" style="width: 100%">
            <el-option v-for="t in interventionTypes" :key="t.value" :label="t.label" :value="t.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="负责人">
          <el-input v-model="createForm.assigned_to" placeholder="输入姓名" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="createForm.description" type="textarea" :rows="3" placeholder="干预措施详细描述" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="warning" :loading="creating" @click="doCreate">确认创建</el-button>
      </template>
    </el-dialog>

    <!-- 随访弹窗 -->
    <el-dialog v-model="followupVisible" title="新增随访记录" width="460px" destroy-on-close class="dark-dialog">
      <div class="followup-student">
        <span>学生: <strong>{{ currentItem?.student_name }}</strong></span>
        <span class="badge-risk" :class="'risk-' + (currentItem?.mh_risk_before || 'low')">
          {{ (RISK_LABELS as any)[currentItem?.mh_risk_before] || '' }}
        </span>
      </div>
      <el-form :model="followupForm" label-width="75px" label-position="left" style="margin-top: 16px">
        <el-form-item label="效果评定">
          <el-select v-model="followupForm.effect_rating" style="width: 100%">
            <el-option label="好转" value="improved" />
            <el-option label="稳定" value="stable" />
            <el-option label="恶化" value="worsened" />
            <el-option label="待观察" value="pending" />
          </el-select>
        </el-form-item>
        <el-form-item label="随访内容">
          <el-input v-model="followupForm.content" type="textarea" :rows="4" placeholder="记录随访谈话内容..." />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="followupVisible = false">取消</el-button>
        <el-button type="warning" :loading="followupSubmitting" @click="doFollowup">提交</el-button>
      </template>
    </el-dialog>

    <!-- 时间线抽屉 -->
    <el-drawer v-model="timelineVisible" title="干预时间线" size="420px" direction="rtl" class="dark-drawer">
      <el-timeline v-if="timeline.length">
        <el-timeline-item
          v-for="t in timeline"
          :key="t.id"
          :timestamp="t.created_at ? new Date(t.created_at).toLocaleString('zh-CN') : ''"
          :color="timelineColor(t)"
          placement="top"
        >
          <div class="tl-card">
            <div class="tl-content">{{ t.content || t.notes || '-' }}</div>
            <div v-if="t.effect_rating" class="tl-effect">
              效果: {{ EFFECT_LABELS[t.effect_rating] || t.effect_rating }}
            </div>
          </div>
        </el-timeline-item>
      </el-timeline>
      <div v-else class="empty-placeholder">
        <el-icon :size="48" class="empty-icon"><Clock /></el-icon>
        <div class="empty-text">暂无随访时间线</div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ArrowLeft, Plus, FirstAidKit, Clock } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  listInterventions, createIntervention, followupIntervention, getInterventionTimeline,
  searchStudents as apiSearchStudents, RISK_LABELS,
  type RiskLevel, type InterventionType, type EffectRating,
} from '@/api/psychScreening'

const STATUS_LABELS: Record<string, string> = {
  pending: '待处理', tracking: '进行中', in_progress: '进行中', completed: '已完成', cancelled: '已取消',
}
const TYPE_LABELS: Record<string, string> = {
  counseling: '心理咨询', parent_notify: '家长告知', crisis: '危机干预', referral: '转介', followup: '跟踪随访', other: '其他',
}
const EFFECT_LABELS: Record<string, string> = {
  improved: '好转', stable: '稳定', worsened: '恶化', pending: '待观察',
}
const interventionTypes = [
  { value: 'counseling', label: '心理咨询' },
  { value: 'parent_notify', label: '家长告知' },
  { value: 'crisis', label: '危机干预' },
  { value: 'referral', label: '转介' },
  { value: 'followup', label: '跟踪随访' },
  { value: 'other', label: '其他' },
]

const loading = ref(false)
const interventions = ref<any[]>([])
const filterStatus = ref('')
const searchKeyword = ref('')

const displayList = computed(() => {
  let list = interventions.value
  if (searchKeyword.value) {
    const k = searchKeyword.value.toLowerCase()
    list = list.filter(i => (i.student_name || '').toLowerCase().includes(k))
  }
  return list
})

const stats = computed(() => {
  const all = interventions.value
  const risk = all.filter(i => i.intervention_type === 'crisis' || i.mh_risk_before === 'high')
  return {
    total: all.length,
    pending: all.filter(i => i.status === 'pending').length,
    inProgress: all.filter(i => i.status === 'tracking' || i.status === 'in_progress').length,
    completed: all.filter(i => i.status === 'completed').length,
    crisis: risk.length,
  }
})

const createVisible = ref(false)
const creating = ref(false)
const createForm = ref({
  student_id: null as number | null,
  severity: 'medium' as RiskLevel,
  intervention_type: 'counseling' as InterventionType,
  description: '',
  assigned_to: '',
})
const studentOptions = ref<any[]>([])
const searchingStudent = ref(false)

const followupVisible = ref(false)
const followupSubmitting = ref(false)
const followupForm = ref({ content: '', effect_rating: 'stable' as EffectRating })
const currentItem = ref<any>(null)

const timelineVisible = ref(false)
const timeline = ref<any[]>([])

function timelineColor(item: any) {
  if (item.effect_rating === 'improved') return '#3fb950'
  if (item.effect_rating === 'worsened') return '#f85149'
  if (item.effect_rating === 'stable') return '#58a6ff'
  return '#d29922'
}

async function loadList() {
  loading.value = true
  try {
    const params: any = { limit: 200, offset: 0 }
    if (filterStatus.value) params.status = filterStatus.value
    const res: any = await listInterventions(params)
    interventions.value = res?.records || res?.items || res || []
  } catch (e) {
    console.error('Load interventions error:', e)
  } finally {
    loading.value = false
  }
}

async function searchStudents(query: string) {
  if (!query || query.length < 1) return
  searchingStudent.value = true
  try {
    const res: any = await apiSearchStudents({ keyword: query })
    studentOptions.value = res?.items || res || []
  } catch {} finally {
    searchingStudent.value = false
  }
}

function showCreateDialog() {
  createForm.value = {
    student_id: null,
    severity: 'medium',
    intervention_type: 'counseling',
    description: '',
    assigned_to: '',
  }
  studentOptions.value = []
  createVisible.value = true
}

async function doCreate() {
  if (!createForm.value.student_id) { ElMessage.warning('请选择学生'); return }
  creating.value = true
  try {
    await createIntervention(createForm.value as any)
    ElMessage.success('干预记录已创建')
    createVisible.value = false
    loadList()
  } catch (e: any) {
    ElMessage.error(e?.message || '创建失败')
  } finally { creating.value = false }
}

function showFollowup(row: any) {
  currentItem.value = row
  followupForm.value = { content: '', effect_rating: 'stable' }
  followupVisible.value = true
}

async function doFollowup() {
  if (!followupForm.value.content) { ElMessage.warning('请填写随访内容'); return }
  followupSubmitting.value = true
  try {
    await followupIntervention(currentItem.value.id, followupForm.value)
    ElMessage.success('随访记录已提交')
    followupVisible.value = false
    loadList()
  } catch (e: any) {
    ElMessage.error(e?.message || '提交失败')
  } finally { followupSubmitting.value = false }
}

async function startIntervention(row: any) {
  await ElMessageBox.confirm(`确认对 "${row.student_name}" 开始干预？`, '开始干预', { type: 'warning' })
  ElMessage.success('已开始干预（需后端状态更新API）')
  loadList()
}

async function completeIntervention(row: any) {
  try {
    await followupIntervention(row.id, { content: '干预完成，效果需进一步评估', effect_rating: 'stable' })
    ElMessage.success('干预已标记完成')
    loadList()
  } catch (e: any) {
    ElMessage.error(e?.message || '操作失败')
  }
}

async function showTimeline(row: any) {
  currentItem.value = row
  try {
    const res: any = await getInterventionTimeline(row.student_id)
    timeline.value = res?.followups || res || []
  } catch { timeline.value = [] }
  timelineVisible.value = true
}

onMounted(loadList)
</script>

<style scoped>
.intervention-page {
  padding: 24px;
  max-width: 1400px;
  margin: 0 auto;
}

/* 页头 */
.page-hero {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}
.hero-left {
  display: flex;
  align-items: center;
  gap: 12px;
}
.back-btn { color: #8b949e; }
.hero-title {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
  color: #f0f6fc;
}

/* 统计条 */
.stats-bar {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
}
.stat-chip {
  flex: 1;
  text-align: center;
  padding: 14px 8px;
  border-radius: 10px;
  background: #161b22;
  border: 1px solid #30363d;
}
.stat-chip.total { border-color: rgba(88,166,255,0.4); }
.stat-chip.total .chip-val { color: #58a6ff; }
.stat-chip.pending { border-color: rgba(210,153,34,0.4); }
.stat-chip.pending .chip-val { color: #d29922; }
.stat-chip.progress { border-color: rgba(31,111,235,0.4); }
.stat-chip.progress .chip-val { color: #1f6feb; }
.stat-chip.done { border-color: rgba(63,185,80,0.4); }
.stat-chip.done .chip-val { color: #3fb950; }
.stat-chip.crisis { border-color: rgba(248,81,73,0.4); }
.stat-chip.crisis .chip-val { color: #f85149; }
.chip-val {
  display: block;
  font-size: 26px;
  font-weight: 800;
}
.chip-lbl {
  display: block;
  font-size: 12px;
  color: #8b949e;
  margin-top: 2px;
}

/* 内容卡 */
.content-card {
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 12px;
  overflow: hidden;
}
.filter-bar {
  padding: 14px 20px;
  border-bottom: 1px solid #21262d;
  display: flex;
  align-items: center;
}

/* 卡片网格 */
.intervention-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
  gap: 14px;
  padding: 16px;
  min-height: 200px;
}

.intv-card {
  background: #0d1117;
  border: 1px solid #21262d;
  border-radius: 10px;
  overflow: hidden;
  transition: border-color 0.2s, transform 0.15s;
}
.intv-card:hover {
  transform: translateY(-1px);
}
.intv-card.card-high { border-color: rgba(248,81,73,0.35); }
.intv-card.card-medium { border-color: rgba(210,153,34,0.3); }
.card-top {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: 14px 16px 10px;
}
.student-name {
  font-size: 15px;
  font-weight: 600;
  color: #f0f6fc;
}
.student-class {
  font-size: 12px;
  color: #8b949e;
  margin-left: 8px;
}
.card-badges {
  display: flex;
  gap: 6px;
}

/* 自定义徽章 */
.badge-risk, .badge-status, .effect-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
}
.badge-risk.risk-low { background: rgba(63,185,80,0.12); color: #3fb950; border: 1px solid rgba(63,185,80,0.2); }
.badge-risk.risk-medium { background: rgba(210,153,34,0.12); color: #d29922; border: 1px solid rgba(210,153,34,0.2); }
.badge-risk.risk-high { background: rgba(248,81,73,0.12); color: #f85149; border: 1px solid rgba(248,81,73,0.2); }
.badge-risk.risk-critical { background: rgba(248,81,73,0.18); color: #f85149; border: 1px solid rgba(248,81,73,0.3); }

.badge-status.status-pending { background: rgba(210,153,34,0.12); color: #d29922; border: 1px solid rgba(210,153,34,0.2); }
.badge-status.status-tracking { background: rgba(88,166,255,0.12); color: #58a6ff; border: 1px solid rgba(88,166,255,0.2); }
.badge-status.status-in_progress { background: rgba(88,166,255,0.12); color: #58a6ff; border: 1px solid rgba(88,166,255,0.2); }
.badge-status.status-completed { background: rgba(63,185,80,0.12); color: #3fb950; border: 1px solid rgba(63,185,80,0.2); }
.badge-status.status-cancelled { background: rgba(139,148,158,0.12); color: #8b949e; border: 1px solid rgba(139,148,158,0.2); }

.effect-badge.effect-improved { background: rgba(63,185,80,0.12); color: #3fb950; border: 1px solid rgba(63,185,80,0.2); }
.effect-badge.effect-stable { background: rgba(88,166,255,0.12); color: #58a6ff; border: 1px solid rgba(88,166,255,0.2); }
.effect-badge.effect-worsened { background: rgba(248,81,73,0.12); color: #f85149; border: 1px solid rgba(248,81,73,0.2); }
.effect-badge.effect-pending { background: rgba(210,153,34,0.12); color: #d29922; border: 1px solid rgba(210,153,34,0.2); }

.card-body { padding: 0 16px 12px; }
.card-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 5px 0;
  font-size: 13px;
}
.row-label { color: #8b949e; }
.row-value { color: #c9d1d9; font-weight: 500; }
.card-notes {
  font-size: 12px;
  color: #6e7681;
  padding: 6px 0;
  line-height: 1.5;
  border-top: 1px solid #21262d;
  margin-top: 6px;
}
.card-actions {
  display: flex;
  gap: 4px;
  padding: 8px 16px 12px;
  border-top: 1px solid #21262d;
}
.action-link { color: #58a6ff; }

/* 空状态 */
.empty-placeholder {
  grid-column: 1 / -1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  color: #484f58;
}
.empty-icon {
  color: #30363d;
  margin-bottom: 12px;
}
.empty-text {
  font-size: 15px;
  font-weight: 500;
  color: #6e7681;
  margin-bottom: 4px;
}
.empty-sub {
  font-size: 12px;
  color: #484f58;
}

/* 弹窗 */
.followup-student {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 0 8px;
  border-bottom: 1px solid #30363d;
  font-size: 14px;
  color: #c9d1d9;
}

.tl-card {
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 8px;
  padding: 12px;
}
.tl-content {
  color: #c9d1d9;
  font-size: 13px;
  line-height: 1.5;
}
.tl-effect {
  margin-top: 6px;
  font-size: 12px;
  color: #8b949e;
}

/* 暗色覆盖 */
:deep(.el-radio-button__inner) {
  background: #0d1117;
  border-color: #30363d;
  color: #8b949e;
}
:deep(.el-radio-button__original-radio:checked + .el-radio-button__inner) {
  background: #1f6feb;
  border-color: #1f6feb;
  color: #fff;
}
:deep(.el-timeline-item__timestamp) {
  color: #8b949e;
  font-size: 11px;
}
</style>
