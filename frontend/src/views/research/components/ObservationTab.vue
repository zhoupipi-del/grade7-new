<template>
  <div class="observation-tab">
    <!-- 工具栏 -->
    <div class="toolbar">
      <el-select v-model="filters.feedback_status" placeholder="反馈状态" clearable style="width: 120px" @change="loadList">
        <el-option label="待确认" value="pending" />
        <el-option label="已确认" value="confirmed" />
        <el-option label="申诉中" value="appealed" />
        <el-option label="已裁决" value="resolved" />
      </el-select>
      <el-select v-model="filters.observation_type" placeholder="听课类型" clearable style="width: 120px" @change="loadList">
        <el-option label="常规听课" value="routine" />
        <el-option label="专题听课" value="thematic" />
        <el-option label="跟踪听课" value="follow_up" />
        <el-option label="公开课" value="open_class" />
      </el-select>
      <el-select v-model="filters.subject_code" placeholder="学科" clearable style="width: 120px" @change="loadList">
        <el-option v-for="s in subjectOptions" :key="s.value" :label="s.label" :value="s.value" />
      </el-select>
      <div class="flex-spacer" />
      <el-button type="primary" :icon="Plus" @click="showCreateDialog = true">新建听课</el-button>
    </div>

    <!-- 听课列表 -->
    <el-table :data="items" v-loading="loading" stripe @row-click="(row: any) => openDetail(row)" style="width: 100%">
      <el-table-column label="课题" min-width="180">
        <template #default="{ row }">
          <div class="obs-title">{{ row.lesson_title || '未填写课题' }}</div>
          <div class="obs-sub">{{ observationTypeLabel(row.observation_type) }}</div>
        </template>
      </el-table-column>
      <el-table-column label="被听课教师" width="120">
        <template #default="{ row }">{{ row.teacher_name || '—' }}</template>
      </el-table-column>
      <el-table-column label="班级" width="100">
        <template #default="{ row }">{{ row.class_name || row.class_id }}</template>
      </el-table-column>
      <el-table-column label="学科" width="80" :formatter="(_, __, row) => subjectLabel(row.subject_code)" />
      <el-table-column label="评分" width="100" align="center">
        <template #default="{ row }">
          <span v-if="row.score_percentage != null" :class="scoreClass(row.score_percentage)">
            {{ row.score_percentage.toFixed(1) }}%
          </span>
          <span v-else class="no-score">未评分</span>
        </template>
      </el-table-column>
      <el-table-column label="反馈状态" width="100" align="center">
        <template #default="{ row }">
          <el-tag :type="feedbackStatusTag(row.feedback_status)" size="small">
            {{ feedbackStatusLabel(row.feedback_status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="听课人" width="100">
        <template #default="{ row }">{{ row.observer_name || '—' }}</template>
      </el-table-column>
      <el-table-column label="听课时间" width="150">
        <template #default="{ row }">{{ formatTime(row.observed_at) }}</template>
      </el-table-column>
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
    <el-drawer v-model="detailVisible" size="60%" :title="currentDetail?.lesson_title || '听课详情'" destroy-on-close>
      <template v-if="currentDetail">
        <div class="detail-content">
          <!-- 元信息 -->
          <div class="meta-bar">
            <el-tag>{{ subjectLabel(currentDetail.subject_code) }}</el-tag>
            <el-tag type="info">{{ observationTypeLabel(currentDetail.observation_type) }}</el-tag>
            <el-tag type="info">{{ currentDetail.class_name || `班级#${currentDetail.class_id}` }}</el-tag>
            <el-tag type="info">{{ currentDetail.duration_minutes }}分钟</el-tag>
            <el-tag v-if="currentDetail.plan_adherence" :type="planAdherenceTag(currentDetail.plan_adherence)" size="small">
              {{ planAdherenceLabel(currentDetail.plan_adherence) }}
            </el-tag>
          </div>
          <div class="meta-info-row">
            <span>被听课: <strong>{{ currentDetail.teacher_name || '—' }}</strong></span>
            <span>听课人: <strong>{{ currentDetail.observer_name || '—' }}</strong></span>
            <span>时间: <strong>{{ formatTime(currentDetail.observed_at) }}</strong></span>
          </div>

          <!-- 反馈状态流水线 -->
          <div class="pipeline-section">
            <el-steps :active="feedbackStep" align-center>
              <el-step title="待确认" :description="currentDetail.feedback_status === 'pending' ? '当前' : ''" />
              <el-step title="已确认" :description="currentDetail.feedback_status === 'confirmed' ? '已完成' : ''" />
              <el-step title="申诉" :description="currentDetail.feedback_status === 'appealed' ? '当前' : ''" />
              <el-step title="已裁决" :description="currentDetail.feedback_status === 'resolved' ? '已完成' : ''" />
            </el-steps>
          </div>

          <!-- 操作按钮 -->
          <div class="action-bar">
            <el-button
              v-if="isObservedTeacher && currentDetail.feedback_status === 'pending'"
              type="success" :icon="Check"
              @click="doConfirm"
            >确认评课</el-button>
            <el-button
              v-if="isObservedTeacher && currentDetail.feedback_status === 'pending'"
              type="warning" :icon="WarningFilled"
              @click="showAppealDialog = true"
            >提出申诉</el-button>
            <el-button
              v-if="canManage && !currentDetail.rubric && currentDetail.feedback_status === 'pending'"
              type="primary" :icon="EditPen"
              @click="showRubricDialog = true"
            >提交评分</el-button>
            <el-button
              v-if="canResolve && currentDetail.feedback_status === 'appealed'"
              type="success" :icon="Checked"
              @click="showResolveDialog = true"
            >处理申诉</el-button>
          </div>

          <!-- 评分矩阵 -->
          <div class="section">
            <h3 class="section-title">量化评分矩阵</h3>
            <template v-if="currentDetail.rubric">
              <el-table :data="rubricDimensions" border size="small">
                <el-table-column label="评价维度" prop="name" min-width="140" />
                <el-table-column label="得分" width="80" align="center">
                  <template #default="{ row }">
                    <span :class="scoreTextClass(row.score, row.max)">{{ row.score }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="满分" prop="max" width="70" align="center" />
                <el-table-column label="权重" width="70" align="center">
                  <template #default="{ row }">{{ row.weight != null ? (row.weight * 100).toFixed(0) + '%' : '—' }}</template>
                </el-table-column>
                <el-table-column label="评语" prop="comment" min-width="200" show-overflow-tooltip />
              </el-table>
              <div class="rubric-summary">
                <div class="rubric-total">
                  总分: <strong>{{ currentDetail.rubric.total_score.toFixed(1) }}</strong> / {{ currentDetail.rubric.max_score }}
                  <el-tag :type="scoreGrade(currentDetail.rubric.percentage).tag" size="small" style="margin-left: 12px">
                    {{ currentDetail.rubric.percentage?.toFixed(1) }}% · {{ scoreGrade(currentDetail.rubric.percentage).label }}
                  </el-tag>
                </div>
                <div class="rubric-scorer">评分人: {{ currentDetail.rubric.scorer_name || '—' }}</div>
              </div>
            </template>
            <el-empty v-else description="暂未提交评分" :image-size="60" />
          </div>

          <!-- 文本反馈 -->
          <div v-if="currentDetail.text_feedback" class="section">
            <h3 class="section-title">听课反馈</h3>
            <div v-if="currentDetail.text_feedback.highlights?.length" class="feedback-block">
              <div class="feedback-label success">闪光点</div>
              <ul class="feedback-list">
                <li v-for="(h, i) in currentDetail.text_feedback.highlights" :key="i">{{ h }}</li>
              </ul>
            </div>
            <div v-if="currentDetail.text_feedback.suggestions?.length" class="feedback-block">
              <div class="feedback-label warning">改进建议</div>
              <ul class="feedback-list">
                <li v-for="(s, i) in currentDetail.text_feedback.suggestions" :key="i">{{ s }}</li>
              </ul>
            </div>
            <div v-if="currentDetail.text_feedback.overall_comment" class="feedback-block">
              <div class="feedback-label">总体评价</div>
              <p class="feedback-text">{{ currentDetail.text_feedback.overall_comment }}</p>
            </div>
          </div>

          <!-- 教案关联 -->
          <div v-if="currentDetail.lesson_plan_id" class="section">
            <h3 class="section-title">教案关联</h3>
            <div class="plan-link">
              <el-icon><Link /></el-icon>
              <span>{{ currentDetail.plan_title || `教案#${currentDetail.lesson_plan_id}` }}</span>
              <el-tag v-if="currentDetail.plan_status" size="small" type="info">{{ currentDetail.plan_status }}</el-tag>
              <span v-if="currentDetail.plan_version_number" class="plan-version">V{{ currentDetail.plan_version_number }}</span>
            </div>
          </div>

          <!-- 申诉历史 -->
          <div class="section">
            <h3 class="section-title">反馈/申诉历史</h3>
            <el-timeline v-if="currentDetail.appeals?.length">
              <el-timeline-item
                v-for="a in currentDetail.appeals"
                :key="a.id"
                :type="appealType(a.action_type)"
                :timestamp="formatTime(a.created_at)"
                placement="top"
              >
                <div class="appeal-item">
                  <el-tag :type="appealType(a.action_type)" size="small">{{ appealLabel(a.action_type) }}</el-tag>
                  <span class="appeal-teacher">{{ a.teacher_name || '—' }}</span>
                  <p v-if="a.appeal_reason" class="appeal-text">{{ a.appeal_reason }}</p>
                  <div v-if="a.appealed_dimensions?.length" class="appeal-dims">
                    申诉维度: {{ a.appealed_dimensions.join('、') }}
                  </div>
                  <div v-if="a.resolution" class="appeal-resolution">
                    <el-icon><CircleCheck /></el-icon>
                    {{ a.resolution }}
                    <span v-if="a.score_adjusted" class="adjusted-score">分数调整: {{ a.adjusted_total_score }}</span>
                  </div>
                </div>
              </el-timeline-item>
            </el-timeline>
            <el-empty v-else description="暂无反馈记录" :image-size="60" />
          </div>
        </div>
      </template>
    </el-drawer>

    <!-- 新建听课弹窗 -->
    <el-dialog v-model="showCreateDialog" title="新建听课记录" width="600px" destroy-on-close>
      <el-form :model="createForm" label-width="100px">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="被听课教师" required>
              <el-input-number v-model="createForm.teacher_id" :min="1" placeholder="教师ID" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="班级" required>
              <el-input-number v-model="createForm.class_id" :min="1" placeholder="班级ID" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="学科" required>
              <el-select v-model="createForm.subject_code" style="width: 100%">
                <el-option v-for="s in subjectOptions" :key="s.value" :label="s.label" :value="s.value" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="听课类型">
              <el-select v-model="createForm.observation_type" style="width: 100%">
                <el-option label="常规听课" value="routine" />
                <el-option label="专题听课" value="thematic" />
                <el-option label="跟踪听课" value="follow_up" />
                <el-option label="公开课" value="open_class" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="课题">
          <el-input v-model="createForm.lesson_title" placeholder="听课课题" />
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="听课时间" required>
              <el-date-picker v-model="createForm.observed_at" type="datetime" placeholder="选择时间" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="时长(分钟)">
              <el-input-number v-model="createForm.duration_minutes" :min="10" :max="240" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="教案执行度">
          <el-radio-group v-model="createForm.plan_adherence">
            <el-radio value="full">完全执行</el-radio>
            <el-radio value="partial">部分执行</el-radio>
            <el-radio value="deviated">偏离教案</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="doCreate">创建</el-button>
      </template>
    </el-dialog>

    <!-- 评分弹窗 -->
    <el-dialog v-model="showRubricDialog" title="提交评分矩阵" width="700px" destroy-on-close>
      <el-form label-width="80px">
        <el-form-item label="评分模板">
          <el-input v-model="rubricForm.template_name" placeholder="如: 常规听课评分表" />
        </el-form-item>
        <div class="rubric-editor">
          <div class="rubric-editor-header">
            <span>评价维度</span>
            <el-button size="small" :icon="Plus" @click="addDimension">添加维度</el-button>
          </div>
          <div v-for="(d, i) in rubricForm.dimensions" :key="i" class="rubric-dim-row">
            <el-input v-model="d.name" placeholder="维度名称" style="width: 160px" />
            <el-input-number v-model="d.score" :min="0" :precision="1" placeholder="得分" style="width: 100px" />
            <el-input-number v-model="d.max" :min="0.1" :precision="1" placeholder="满分" style="width: 100px" />
            <el-input v-model="d.comment" placeholder="评语(可选)" style="flex: 1" />
            <el-button :icon="Delete" circle size="small" @click="rubricForm.dimensions.splice(i, 1)" />
          </div>
        </div>
      </el-form>
      <template #footer>
        <el-button @click="showRubricDialog = false">取消</el-button>
        <el-button type="primary" :loading="rubricSaving" @click="doSubmitRubric">提交评分</el-button>
      </template>
    </el-dialog>

    <!-- 申诉弹窗 -->
    <el-dialog v-model="showAppealDialog" title="提出申诉" width="500px" destroy-on-close>
      <el-form :model="appealForm" label-width="100px">
        <el-form-item label="申诉理由" required>
          <el-input v-model="appealForm.appeal_reason" type="textarea" :rows="4" placeholder="申诉理由" />
        </el-form-item>
        <el-form-item label="申诉维度">
          <el-input v-model="appealDimsInput" placeholder="如: 教学引入,重难点突出" />
          <span class="form-hint">用逗号分隔多个维度</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAppealDialog = false">取消</el-button>
        <el-button type="warning" :loading="appealSaving" @click="doAppeal">提交申诉</el-button>
      </template>
    </el-dialog>

    <!-- 处理申诉弹窗 -->
    <el-dialog v-model="showResolveDialog" title="处理申诉" width="500px" destroy-on-close>
      <el-form :model="resolveForm" label-width="100px">
        <el-form-item label="裁决说明" required>
          <el-input v-model="resolveForm.resolution" type="textarea" :rows="4" placeholder="裁决说明" />
        </el-form-item>
        <el-form-item label="是否调分">
          <el-switch v-model="resolveForm.score_adjusted" />
        </el-form-item>
        <el-form-item v-if="resolveForm.score_adjusted" label="调整后分数">
          <el-input-number v-model="resolveForm.adjusted_total_score" :min="0" :precision="1" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showResolveDialog = false">取消</el-button>
        <el-button type="success" :loading="resolveSaving" @click="doResolve">裁决</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Delete, Check, WarningFilled, EditPen, Checked, Link, CircleCheck } from '@element-plus/icons-vue'
import { useUserStore } from '@/store/user'
import * as obsApi from '@/api/researchObservation'
import type { ObservationResponse, ObservationDetailResponse, FeedbackStatus, ObservationType, PlanAdherence, RubricDimension } from '@/api/researchObservation'
import { feedbackStatusTag, feedbackStatusLabel, observationTypeLabel, planAdherenceLabel, planAdherenceTag, scoreGrade } from '@/api/researchObservation'

const userStore = useUserStore()
const userRole = computed(() => userStore.currentRole || '')
const userId = computed(() => userStore.userInfo?.id || 0)
const canManage = computed(() => ['MS_ADMIN', 'GRADE_LEADER', 'CLASS_TEACHER'].includes(userRole.value as string))
const canResolve = computed(() => ['MS_ADMIN', 'GRADE_LEADER'].includes(userRole.value as string))

/* ──── 列表 ──── */
const loading = ref(false)
const items = ref<ObservationResponse[]>([])
const total = ref(0)
const filters = reactive({
  feedback_status: '',
  observation_type: '',
  subject_code: '',
  page: 1,
  page_size: 20,
})

async function loadList() {
  loading.value = true
  try {
    const params: obsApi.ListParams = { page: filters.page, page_size: filters.page_size }
    if (filters.feedback_status) params.feedback_status = filters.feedback_status as FeedbackStatus
    if (filters.observation_type) params.observation_type = filters.observation_type as ObservationType
    if (filters.subject_code) params.subject_code = filters.subject_code
    const res = await obsApi.listObservations(params)
    items.value = res.items || []
    total.value = res.total || 0
  } catch (e: any) { ElMessage.error(e.message || '加载失败') }
  finally { loading.value = false }
}

/* ──── 详情 ──── */
const detailVisible = ref(false)
const currentDetail = ref<ObservationDetailResponse | null>(null)

const isObservedTeacher = computed(() => currentDetail.value?.teacher_id === userId.value)
const feedbackStep = computed(() => {
  if (!currentDetail.value) return 0
  const map: Record<FeedbackStatus, number> = { pending: 0, confirmed: 1, appealed: 2, resolved: 3 }
  return map[currentDetail.value.feedback_status] ?? 0
})
const rubricDimensions = computed<RubricDimension[]>(() => {
  if (!currentDetail.value?.rubric) return []
  const metrics = currentDetail.value.rubric.rubric_metrics
  if (Array.isArray(metrics) && metrics.length > 0 && 'name' in metrics[0]) {
    return metrics as unknown as RubricDimension[]
  }
  return []
})

async function openDetail(row: any) {
  detailVisible.value = true
  currentDetail.value = null
  try {
    currentDetail.value = await obsApi.getObservation(row.id)
  } catch (e: any) { ElMessage.error(e.message || '加载详情失败') }
}

/* ──── 新建听课 ──── */
const showCreateDialog = ref(false)
const creating = ref(false)
const createForm = reactive({
  teacher_id: 0,
  class_id: 0,
  subject_code: '',
  lesson_title: '',
  observation_type: 'routine' as ObservationType,
  observed_at: '',
  duration_minutes: 45,
  plan_adherence: '' as PlanAdherence | '',
})

async function doCreate() {
  if (!createForm.teacher_id || !createForm.class_id || !createForm.subject_code || !createForm.observed_at) {
    ElMessage.warning('请填写必填项')
    return
  }
  creating.value = true
  try {
    await obsApi.createObservation({
      teacher_id: createForm.teacher_id,
      class_id: createForm.class_id,
      subject_code: createForm.subject_code,
      lesson_title: createForm.lesson_title || undefined,
      observation_type: createForm.observation_type,
      observed_at: createForm.observed_at,
      duration_minutes: createForm.duration_minutes,
      plan_adherence: createForm.plan_adherence || undefined,
    })
    ElMessage.success('听课记录已创建')
    showCreateDialog.value = false
    await loadList()
  } catch (e: any) { ElMessage.error(e.message || '创建失败') }
  finally { creating.value = false }
}

/* ──── 评分 ──── */
const showRubricDialog = ref(false)
const rubricSaving = ref(false)
const rubricForm = reactive({
  template_name: '常规听课评分表',
  dimensions: [
    { name: '教学引入', score: 0, max: 10, weight: null, comment: '' },
    { name: '重难点突出', score: 0, max: 10, weight: null, comment: '' },
    { name: '板书设计', score: 0, max: 10, weight: null, comment: '' },
    { name: '生生互动', score: 0, max: 10, weight: null, comment: '' },
    { name: '教学效果', score: 0, max: 10, weight: null, comment: '' },
  ] as RubricDimension[],
})

function addDimension() {
  rubricForm.dimensions.push({ name: '', score: 0, max: 10, weight: null, comment: '' })
}

async function doSubmitRubric() {
  if (!currentDetail.value || rubricForm.dimensions.length === 0) return
  rubricSaving.value = true
  try {
    await obsApi.submitRubric(currentDetail.value.id, {
      template_name: rubricForm.template_name,
      dimensions: rubricForm.dimensions,
    })
    ElMessage.success('评分已提交')
    showRubricDialog.value = false
    await refreshDetail()
  } catch (e: any) { ElMessage.error(e.message || '提交失败') }
  finally { rubricSaving.value = false }
}

/* ──── 确认/申诉/裁决 ──── */
async function doConfirm() {
  if (!currentDetail.value) return
  try {
    await ElMessageBox.confirm('确认接受评课结果?', '确认评课', { type: 'success' })
    await obsApi.teacherConfirm(currentDetail.value.id)
    ElMessage.success('已确认')
    await refreshDetail()
  } catch (e: any) { if (e !== 'cancel') ElMessage.error(e.message || '操作失败') }
}

const showAppealDialog = ref(false)
const appealSaving = ref(false)
const appealForm = reactive({ appeal_reason: '' })
const appealDimsInput = ref('')

async function doAppeal() {
  if (!currentDetail.value || !appealForm.appeal_reason) {
    ElMessage.warning('请填写申诉理由')
    return
  }
  appealSaving.value = true
  try {
    const dims = appealDimsInput.value ? appealDimsInput.value.split(',').map(s => s.trim()).filter(Boolean) : []
    await obsApi.teacherAppeal(currentDetail.value.id, {
      appeal_reason: appealForm.appeal_reason,
      appealed_dimensions: dims,
    })
    ElMessage.success('申诉已提交')
    showAppealDialog.value = false
    appealForm.appeal_reason = ''
    appealDimsInput.value = ''
    await refreshDetail()
  } catch (e: any) { ElMessage.error(e.message || '操作失败') }
  finally { appealSaving.value = false }
}

const showResolveDialog = ref(false)
const resolveSaving = ref(false)
const resolveForm = reactive({ resolution: '', score_adjusted: false, adjusted_total_score: 0 })

async function doResolve() {
  if (!currentDetail.value || !resolveForm.resolution) {
    ElMessage.warning('请填写裁决说明')
    return
  }
  resolveSaving.value = true
  try {
    await obsApi.resolveAppeal(currentDetail.value.id, {
      resolution: resolveForm.resolution,
      score_adjusted: resolveForm.score_adjusted,
      adjusted_total_score: resolveForm.score_adjusted ? resolveForm.adjusted_total_score : undefined,
    })
    ElMessage.success('申诉已裁决')
    showResolveDialog.value = false
    resolveForm.resolution = ''
    resolveForm.score_adjusted = false
    await refreshDetail()
  } catch (e: any) { ElMessage.error(e.message || '操作失败') }
  finally { resolveSaving.value = false }
}

/* ──── 工具 ──── */
async function refreshDetail() {
  if (!currentDetail.value) return
  try { currentDetail.value = await obsApi.getObservation(currentDetail.value.id) } catch {}
}
function formatTime(s: string): string { return s ? s.replace('T', ' ').slice(0, 16) : '—' }
function subjectLabel(code: string): string {
  const map: Record<string, string> = { chinese: '语文', math: '数学', english: '英语', physics: '物理', chemistry: '化学', biology: '生物', politics: '政治', history: '历史', geography: '地理' }
  return map[code] || code || '—'
}
const subjectOptions = Object.entries({ chinese: '语文', math: '数学', english: '英语', physics: '物理', chemistry: '化学', biology: '生物', politics: '政治', history: '历史', geography: '地理' }).map(([value, label]) => ({ value, label }))
function scoreClass(pct: number): string { return pct >= 90 ? 'score-excellent' : pct >= 70 ? 'score-pass' : 'score-fail' }
function scoreTextClass(score: number, max: number): string { return score / max >= 0.9 ? 'score-excellent' : score / max >= 0.7 ? 'score-pass' : 'score-fail' }
function appealType(action: string): 'primary' | 'success' | 'warning' | 'danger' | 'info' {
  if (action === 'confirm') return 'success'
  if (action === 'appeal') return 'danger'
  if (action === 'resolve') return 'primary'
  return 'info'
}
function appealLabel(action: string): string {
  const map: Record<string, string> = { confirm: '确认', appeal: '申诉', resolve: '裁决' }
  return map[action] || action
}

onMounted(loadList)
</script>

<style scoped>
.observation-tab { padding: 0 4px; }
.toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.flex-spacer { flex: 1; }
.obs-title { font-weight: 600; }
.obs-sub { font-size: 12px; color: var(--el-text-color-secondary); }
.no-score { color: var(--el-text-color-placeholder); }
.score-excellent { color: var(--el-color-success); font-weight: 700; }
.score-pass { color: var(--el-text-color-primary); font-weight: 600; }
.score-fail { color: var(--el-color-danger); font-weight: 700; }
.pagination-row { margin-top: 16px; display: flex; justify-content: flex-end; }

.detail-content { padding: 0 8px; }
.meta-bar { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
.meta-info-row { display: flex; gap: 24px; margin-bottom: 16px; font-size: 14px; color: var(--el-text-color-secondary); }
.pipeline-section { margin-bottom: 20px; padding: 20px; background: var(--el-fill-color-light); border-radius: 8px; }
.action-bar { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 24px; padding-bottom: 20px; border-bottom: 1px solid var(--el-border-color-lighter); }
.section { margin-bottom: 28px; }
.section-title { font-size: 16px; font-weight: 600; margin: 0 0 12px; }
.rubric-summary { display: flex; justify-content: space-between; align-items: center; margin-top: 12px; }
.rubric-total { font-size: 15px; }
.rubric-scorer { font-size: 13px; color: var(--el-text-color-secondary); }

.feedback-block { margin-bottom: 16px; }
.feedback-label { font-weight: 600; margin-bottom: 6px; }
.feedback-label.success { color: var(--el-color-success); }
.feedback-label.warning { color: var(--el-color-warning); }
.feedback-list { margin: 0; padding-left: 20px; }
.feedback-text { line-height: 1.8; margin: 0; }

.plan-link { display: flex; align-items: center; gap: 8px; }
.plan-version { font-size: 12px; color: var(--el-text-color-secondary); }

.appeal-item { padding: 4px 0; }
.appeal-teacher { font-size: 13px; color: var(--el-text-color-secondary); margin-left: 8px; }
.appeal-text { margin: 8px 0; line-height: 1.6; }
.appeal-dims { font-size: 13px; color: var(--el-text-color-secondary); }
.appeal-resolution { display: flex; align-items: center; gap: 6px; font-size: 13px; color: var(--el-color-success); margin-top: 8px; }
.adjusted-score { margin-left: 12px; font-weight: 600; }

.rubric-editor { margin-top: 12px; }
.rubric-editor-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.rubric-dim-row { display: flex; gap: 8px; align-items: center; margin-bottom: 8px; }
.form-hint { font-size: 12px; color: var(--el-text-color-secondary); }
</style>
