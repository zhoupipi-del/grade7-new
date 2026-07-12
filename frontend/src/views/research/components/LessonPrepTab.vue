<template>
  <div class="lesson-prep-tab">
    <!-- 工具栏 -->
    <div class="toolbar">
      <el-select v-model="filters.subject_code" placeholder="学科" clearable style="width: 120px" @change="loadList">
        <el-option label="语文" value="chinese" />
        <el-option label="数学" value="math" />
        <el-option label="英语" value="english" />
        <el-option label="物理" value="physics" />
        <el-option label="化学" value="chemistry" />
        <el-option label="生物" value="biology" />
        <el-option label="政治" value="politics" />
        <el-option label="历史" value="history" />
        <el-option label="地理" value="geography" />
      </el-select>
      <el-select v-model="filters.status" placeholder="状态" clearable style="width: 120px" @change="loadList">
        <el-option label="草稿" value="DRAFT" />
        <el-option label="集体评议" value="COLLECTIVE_REVIEW" />
        <el-option label="待发布" value="ADMIN_APPROVE" />
        <el-option label="已发布" value="PUBLISHED" />
      </el-select>
      <el-input v-model="searchText" placeholder="搜索教案标题" clearable style="width: 200px" @input="onSearch" />
      <div class="flex-spacer" />
      <el-button type="primary" :icon="Plus" @click="showCreateDialog = true">新建教案</el-button>
    </div>

    <!-- 教案列表 -->
    <el-table :data="filteredItems" v-loading="loading" stripe @row-click="(row: any) => openDetail(row)" style="width: 100%">
      <el-table-column label="标题" min-width="220">
        <template #default="{ row }">
          <div class="plan-title-cell">
            <span class="plan-title-text">{{ row.title }}</span>
            <el-tag v-if="row.forked_from_id" size="small" type="info" effect="plain">Fork</el-tag>
          </div>
          <div class="plan-desc">{{ row.description || '—' }}</div>
        </template>
      </el-table-column>
      <el-table-column label="学科" prop="subject_code" width="80" :formatter="(_, __, val) => subjectLabel(val)" />
      <el-table-column label="年级" prop="grade_level" width="80" />
      <el-table-column label="课型" width="90" :formatter="(_, __, row) => lessonTypeLabel(row.lesson_type)" />
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="planStatusTag(row.status)" size="small">{{ planStatusLabel(row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="版本" width="70" align="center">
        <template #default="{ row }">
          <span class="version-badge">V{{ row.current_version }}</span>
        </template>
      </el-table-column>
      <el-table-column label="创建人" prop="creator_name" width="100" show-overflow-tooltip />
      <el-table-column label="更新时间" width="160">
        <template #default="{ row }">
          {{ formatTime(row.updated_at) }}
        </template>
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
    <el-drawer v-model="detailVisible" size="65%" :title="currentPlan?.title || '教案详情'" destroy-on-close>
      <template v-if="currentPlan">
        <div class="detail-content">
          <!-- 元信息栏 -->
          <div class="meta-bar">
            <el-tag>{{ subjectLabel(currentPlan.subject_code) }}</el-tag>
            <el-tag type="info">{{ currentPlan.grade_level }}</el-tag>
            <el-tag type="info">{{ lessonTypeLabel(currentPlan.lesson_type) }}</el-tag>
            <el-tag type="info">{{ currentPlan.duration }}分钟</el-tag>
            <el-tag v-for="tag in currentPlan.tags" :key="tag" size="small" effect="plain">{{ tag }}</el-tag>
            <span class="meta-spacer" />
            <span class="meta-info">创建: {{ currentPlan.creator_name || '—' }}</span>
          </div>

          <!-- 状态流水线 -->
          <div class="pipeline-section">
            <el-steps :active="pipelineActive" align-center finish-status="success" process-status="process">
              <el-step title="草稿" :description="currentPlan.status === 'DRAFT' ? '当前' : ''" />
              <el-step title="集体评议" :description="currentPlan.status === 'COLLECTIVE_REVIEW' ? '当前' : ''" />
              <el-step title="待发布" :description="currentPlan.status === 'ADMIN_APPROVE' ? '当前' : ''" />
              <el-step title="已发布" :description="currentPlan.status === 'PUBLISHED' ? '已锁定' : ''" />
            </el-steps>
          </div>

          <!-- 操作按钮区 -->
          <div class="action-bar">
            <el-button
              v-if="currentPlan.status === 'DRAFT' && canManage"
              type="primary" :icon="Promotion"
              @click="doSubmit"
            >提交评议</el-button>
            <el-button
              v-if="currentPlan.status === 'COLLECTIVE_REVIEW' && canReview"
              type="success" :icon="Check"
              @click="doApprove"
            >审核通过</el-button>
            <el-button
              v-if="currentPlan.status === 'ADMIN_APPROVE' && canReview"
              type="success" :icon="Upload"
              @click="doPublish"
            >发布锁定</el-button>
            <el-button
              v-if="(currentPlan.status === 'COLLECTIVE_REVIEW' || currentPlan.status === 'ADMIN_APPROVE') && canReview"
              type="danger" :icon="RefreshLeft"
              @click="doReject"
            >打回草稿</el-button>
            <el-button
              v-if="currentPlan.status === 'PUBLISHED'"
              type="primary" :icon="CopyDocument"
              @click="doFork"
            >Fork派生</el-button>
            <el-button
              v-if="canManage && (currentPlan.status === 'DRAFT' || currentPlan.status === 'COLLECTIVE_REVIEW')"
              :icon="EditPen"
              @click="showVersionDialog = true"
            >保存新版本</el-button>
            <el-button
              v-if="canReview && currentPlan.status === 'COLLECTIVE_REVIEW'"
              :icon="ChatDotRound"
              @click="showReviewDialog = true"
            >添加批注</el-button>
            <el-button
              v-if="canManage && currentPlan.status !== 'PUBLISHED'"
              type="danger" plain :icon="Delete"
              @click="doDelete"
            >删除</el-button>
          </div>

          <!-- 教案内容 -->
          <div v-if="currentPlan.latest_content" class="content-section">
            <h3 class="section-title">教案内容 (V{{ currentPlan.latest_version_number }})</h3>
            <el-collapse v-model="activeCollapse">
              <el-collapse-item title="教学目标" name="objectives">
                <ul class="content-list">
                  <li v-for="(item, i) in currentPlan.latest_content.teaching_objectives" :key="i">{{ item }}</li>
                </ul>
              </el-collapse-item>
              <el-collapse-item title="教学重点" name="key_points">
                <ul class="content-list">
                  <li v-for="(item, i) in currentPlan.latest_content.key_points" :key="i">{{ item }}</li>
                </ul>
              </el-collapse-item>
              <el-collapse-item title="教学难点" name="difficulties">
                <ul class="content-list">
                  <li v-for="(item, i) in currentPlan.latest_content.difficulties" :key="i">{{ item }}</li>
                </ul>
              </el-collapse-item>
              <el-collapse-item title="教学方法" name="methods">
                <el-tag v-for="(m, i) in currentPlan.latest_content.teaching_methods" :key="i" class="method-tag" effect="plain">{{ m }}</el-tag>
              </el-collapse-item>
              <el-collapse-item title="教学过程" name="process">
                <el-timeline>
                  <el-timeline-item
                    v-for="(step, i) in currentPlan.latest_content.teaching_process"
                    :key="i"
                    :type="phaseColor(step.phase)"
                    :timestamp="`${step.duration}分钟`"
                    placement="top"
                  >
                    <div class="process-step">
                      <el-tag :type="phaseColor(step.phase)" size="small">{{ step.phase }}</el-tag>
                      <p class="process-content">{{ step.content }}</p>
                      <div v-if="step.activities?.length" class="process-activities">
                        <span class="label">活动:</span>
                        <el-tag v-for="(a, j) in step.activities" :key="j" size="small" effect="plain">{{ a }}</el-tag>
                      </div>
                      <div v-if="step.resources?.length" class="process-resources">
                        <span class="label">资源:</span>
                        <span class="resource-text">{{ step.resources.join('、') }}</span>
                      </div>
                    </div>
                  </el-timeline-item>
                </el-timeline>
              </el-collapse-item>
              <el-collapse-item title="作业设计" name="homework">
                <ul class="content-list">
                  <li v-for="(item, i) in currentPlan.latest_content.homework" :key="i">{{ item }}</li>
                </ul>
              </el-collapse-item>
              <el-collapse-item title="板书设计" name="blackboard">
                <pre class="blackboard-pre">{{ currentPlan.latest_content.blackboard_design || '—' }}</pre>
              </el-collapse-item>
              <el-collapse-item v-if="currentPlan.latest_content.reflection" title="教学反思" name="reflection">
                <p class="reflection-text">{{ currentPlan.latest_content.reflection }}</p>
              </el-collapse-item>
            </el-collapse>
          </div>

          <!-- 版本历史 -->
          <div class="version-section">
            <div class="section-header">
              <h3 class="section-title">版本快照轴</h3>
              <el-button text size="small" @click="loadVersions" :loading="versionLoading">刷新</el-button>
            </div>
            <el-timeline v-if="versions.length" class="version-timeline">
              <el-timeline-item
                v-for="v in versions"
                :key="v.id"
                :type="v.version_number === currentPlan.current_version ? 'primary' : 'info'"
                :hollow="v.version_number !== currentPlan.current_version"
                :timestamp="formatTime(v.created_at)"
                placement="top"
              >
                <div class="version-item">
                  <div class="version-head">
                    <span class="version-num">V{{ v.version_number }}</span>
                    <el-tag v-if="v.is_major" size="small" type="danger" effect="plain">大版本</el-tag>
                    <el-tag v-if="v.version_number === currentPlan.current_version" size="small" type="primary">当前</el-tag>
                    <span class="version-editor">{{ v.editor_name || '—' }}</span>
                  </div>
                  <div class="version-log">{{ v.change_log || '无变更说明' }}</div>
                </div>
              </el-timeline-item>
            </el-timeline>
            <el-empty v-else description="暂无版本记录" :image-size="60" />
          </div>

          <!-- 批注面板 -->
          <div class="review-section">
            <div class="section-header">
              <h3 class="section-title">
                组长批注
                <el-badge v-if="unresolvedCount > 0" :value="unresolvedCount" type="danger" />
              </h3>
              <el-radio-group v-model="reviewFilter" size="small">
                <el-radio-button label="all">全部 {{ reviews.length }}</el-radio-button>
                <el-radio-button label="unresolved">未解决 {{ unresolvedCount }}</el-radio-button>
              </el-radio-group>
            </div>
            <div v-if="filteredReviews.length" class="review-list">
              <div v-for="r in filteredReviews" :key="r.id" class="review-item" :class="{ resolved: r.is_resolved }">
                <div class="review-head">
                  <el-tag :type="severityTag(r.severity)" size="small">{{ severityLabel(r.severity) }}</el-tag>
                  <span class="review-section-name">{{ r.target_section }}</span>
                  <span v-if="r.target_anchor" class="review-anchor">@ {{ r.target_anchor }}</span>
                  <span class="review-reviewer">{{ r.reviewer_name || '—' }}</span>
                  <span class="review-time">{{ formatTime(r.created_at) }}</span>
                  <el-tag v-if="r.is_resolved" size="small" type="success">已解决</el-tag>
                </div>
                <div class="review-comment">{{ r.comment }}</div>
                <div v-if="r.resolution_note" class="review-resolution">
                  <el-icon><CircleCheck /></el-icon>
                  {{ r.resolution_note }}
                </div>
                <el-button
                  v-if="!r.is_resolved && canReview"
                  size="small" type="success" plain
                  @click="doResolveReview(r)"
                >标记已解决</el-button>
              </div>
            </div>
            <el-empty v-else description="暂无批注" :image-size="60" />
          </div>
        </div>
      </template>
    </el-drawer>

    <!-- 新建教案弹窗 -->
    <el-dialog v-model="showCreateDialog" title="新建教案" width="700px" destroy-on-close>
      <el-form :model="createForm" label-width="100px" label-position="right">
        <el-form-item label="标题" required>
          <el-input v-model="createForm.title" placeholder="教案标题" maxlength="200" />
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item label="学科" required>
              <el-select v-model="createForm.subject_code" placeholder="选择学科" style="width: 100%">
                <el-option v-for="s in subjectOptions" :key="s.value" :label="s.label" :value="s.value" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="年级" required>
              <el-input v-model="createForm.grade_level" placeholder="如: 初一" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="课型">
              <el-select v-model="createForm.lesson_type" style="width: 100%">
                <el-option label="新授课" value="new" />
                <el-option label="复习课" value="review" />
                <el-option label="测验课" value="exam" />
                <el-option label="考试课" value="test" />
                <el-option label="活动课" value="activity" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="课时">
          <el-input-number v-model="createForm.duration" :min="1" :max="10" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="createForm.description" type="textarea" :rows="2" placeholder="教案简介" />
        </el-form-item>
        <el-form-item label="教学目标">
          <div class="dynamic-list">
            <div v-for="(_, i) in createForm.content.teaching_objectives" :key="i" class="dynamic-item">
              <el-input v-model="createForm.content.teaching_objectives[i]" placeholder="教学目标" />
              <el-button :icon="Delete" circle size="small" @click="createForm.content.teaching_objectives.splice(i, 1)" />
            </div>
            <el-button size="small" :icon="Plus" @click="createForm.content.teaching_objectives.push('')">添加目标</el-button>
          </div>
        </el-form-item>
        <el-form-item label="教学重点">
          <div class="dynamic-list">
            <div v-for="(_, i) in createForm.content.key_points" :key="i" class="dynamic-item">
              <el-input v-model="createForm.content.key_points[i]" placeholder="教学重点" />
              <el-button :icon="Delete" circle size="small" @click="createForm.content.key_points.splice(i, 1)" />
            </div>
            <el-button size="small" :icon="Plus" @click="createForm.content.key_points.push('')">添加重点</el-button>
          </div>
        </el-form-item>
        <el-form-item label="教学难点">
          <div class="dynamic-list">
            <div v-for="(_, i) in createForm.content.difficulties" :key="i" class="dynamic-item">
              <el-input v-model="createForm.content.difficulties[i]" placeholder="教学难点" />
              <el-button :icon="Delete" circle size="small" @click="createForm.content.difficulties.splice(i, 1)" />
            </div>
            <el-button size="small" :icon="Plus" @click="createForm.content.difficulties.push('')">添加难点</el-button>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="doCreate">创建</el-button>
      </template>
    </el-dialog>

    <!-- 新版本弹窗 -->
    <el-dialog v-model="showVersionDialog" title="保存新版本" width="500px" destroy-on-close>
      <el-form :model="versionForm" label-width="100px">
        <el-form-item label="变更说明">
          <el-input v-model="versionForm.change_log" type="textarea" :rows="3" placeholder="本次修改的变更说明" />
        </el-form-item>
        <el-form-item label="大版本">
          <el-switch v-model="versionForm.is_major" />
          <span class="form-hint">标记为重大修订版本</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showVersionDialog = false">取消</el-button>
        <el-button type="primary" :loading="versionSaving" @click="doCreateVersion">保存版本</el-button>
      </template>
    </el-dialog>

    <!-- 批注弹窗 -->
    <el-dialog v-model="showReviewDialog" title="添加批注" width="500px" destroy-on-close>
      <el-form :model="reviewForm" label-width="100px">
        <el-form-item label="批注位置">
          <el-select v-model="reviewForm.target_section" placeholder="选择教案组件" style="width: 100%">
            <el-option label="教学目标" value="teaching_objectives" />
            <el-option label="教学重点" value="key_points" />
            <el-option label="教学难点" value="difficulties" />
            <el-option label="教学方法" value="teaching_methods" />
            <el-option label="教学过程" value="teaching_process" />
            <el-option label="作业设计" value="homework" />
            <el-option label="板书设计" value="blackboard_design" />
            <el-option label="教学反思" value="reflection" />
          </el-select>
        </el-form-item>
        <el-form-item label="锚点(可选)">
          <el-input v-model="reviewForm.target_anchor" placeholder="如: 第2条目标" />
        </el-form-item>
        <el-form-item label="严重程度">
          <el-radio-group v-model="reviewForm.severity">
            <el-radio value="suggestion">建议</el-radio>
            <el-radio value="issue">问题</el-radio>
            <el-radio value="critical">严重</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="批注内容" required>
          <el-input v-model="reviewForm.comment" type="textarea" :rows="4" placeholder="批注正文" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showReviewDialog = false">取消</el-button>
        <el-button type="primary" :loading="reviewSaving" @click="doCreateReview">提交批注</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Plus, Delete, Promotion, Check, Upload, RefreshLeft, CopyDocument,
  EditPen, ChatDotRound, CircleCheck,
} from '@element-plus/icons-vue'
import { useUserStore } from '@/store/user'
import * as lpApi from '@/api/researchLessonPrep'
import type { PlanResponse, PlanDetailResponse, VersionResponse, ReviewResponse, PlanStatus, LessonContent } from '@/api/researchLessonPrep'

const userStore = useUserStore()
const userRole = computed(() => userStore.currentRole || '')
const canReview = computed(() => ['MS_ADMIN', 'GRADE_LEADER'].includes(userRole.value as string))
const canManage = computed(() => ['MS_ADMIN', 'GRADE_LEADER', 'CLASS_TEACHER'].includes(userRole.value as string))

/* ──── 列表 ──── */
const loading = ref(false)
const items = ref<PlanResponse[]>([])
const total = ref(0)
const searchText = ref('')
const filters = reactive({
  subject_code: '',
  status: '',
  page: 1,
  page_size: 20,
})

const filteredItems = computed(() => {
  if (!searchText.value) return items.value
  const q = searchText.value.toLowerCase()
  return items.value.filter(p => p.title.toLowerCase().includes(q))
})

async function loadList() {
  loading.value = true
  try {
    const params: lpApi.ListParams = { page: filters.page, page_size: filters.page_size }
    if (filters.subject_code) params.subject_code = filters.subject_code
    if (filters.status) params.status = filters.status as PlanStatus
    const res = await lpApi.listPlans(params)
    items.value = res.items || []
    total.value = res.total || 0
  } catch (e: any) {
    ElMessage.error(e.message || '加载列表失败')
  } finally {
    loading.value = false
  }
}

let searchTimer: ReturnType<typeof setTimeout> | null = null
function onSearch() {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => { filters.page = 1 }, 300)
}

/* ──── 详情 ──── */
const detailVisible = ref(false)
const currentPlan = ref<PlanDetailResponse | null>(null)
const activeCollapse = ref(['objectives', 'process'])

const pipelineActive = computed(() => {
  if (!currentPlan.value) return 0
  const map: Record<PlanStatus, number> = { DRAFT: 0, COLLECTIVE_REVIEW: 1, ADMIN_APPROVE: 2, PUBLISHED: 3 }
  return map[currentPlan.value.status] ?? 0
})

async function openDetail(row: any) {
  detailVisible.value = true
  currentPlan.value = null
  try {
    currentPlan.value = await lpApi.getPlan(row.id)
    loadVersions()
    loadReviews()
  } catch (e: any) {
    ElMessage.error(e.message || '加载详情失败')
  }
}

/* ──── 版本 ──── */
const versions = ref<VersionResponse[]>([])
const versionLoading = ref(false)

async function loadVersions() {
  if (!currentPlan.value) return
  versionLoading.value = true
  try {
    const res = await lpApi.listVersions(currentPlan.value.id)
    versions.value = res.items || []
  } catch { versions.value = [] }
  finally { versionLoading.value = false }
}

/* ──── 批注 ──── */
const reviews = ref<ReviewResponse[]>([])
const reviewFilter = ref('all')
const unresolvedCount = computed(() => reviews.value.filter(r => !r.is_resolved).length)
const filteredReviews = computed(() =>
  reviewFilter.value === 'unresolved' ? reviews.value.filter(r => !r.is_resolved) : reviews.value
)

async function loadReviews() {
  if (!currentPlan.value) return
  try {
    const res = await lpApi.listReviews(currentPlan.value.id)
    reviews.value = res.items || []
  } catch { reviews.value = [] }
}

/* ──── 状态机操作 ──── */
async function doSubmit() {
  if (!currentPlan.value) return
  try {
    await ElMessageBox.confirm('确认提交进入集体评议?', '提交评议', { type: 'info' })
    await lpApi.submitPlan(currentPlan.value.id)
    ElMessage.success('已提交评议')
    await refreshDetail()
  } catch (e: any) { if (e !== 'cancel') ElMessage.error(e.message || '操作失败') }
}

async function doApprove() {
  if (!currentPlan.value) return
  try {
    await ElMessageBox.confirm('确认审核通过?', '审核', { type: 'success' })
    await lpApi.approvePlan(currentPlan.value.id)
    ElMessage.success('审核通过')
    await refreshDetail()
  } catch (e: any) { if (e !== 'cancel') ElMessage.error(e.message || '操作失败') }
}

async function doPublish() {
  if (!currentPlan.value) return
  try {
    await ElMessageBox.confirm('发布后将锁定当前版本，不可再修改。确认发布?', '发布', { type: 'warning' })
    await lpApi.publishPlan(currentPlan.value.id)
    ElMessage.success('已发布')
    await refreshDetail()
  } catch (e: any) { if (e !== 'cancel') ElMessage.error(e.message || '操作失败') }
}

async function doReject() {
  if (!currentPlan.value) return
  try {
    const { value } = await ElMessageBox.prompt('请输入打回原因', '打回草稿', {
      type: 'warning', inputPlaceholder: '打回原因（可选）',
    })
    await lpApi.rejectPlan(currentPlan.value.id, { reject_reason: value || '' })
    ElMessage.success('已打回草稿')
    await refreshDetail()
  } catch (e: any) { if (e !== 'cancel') ElMessage.error(e.message || '操作失败') }
}

async function doDelete() {
  if (!currentPlan.value) return
  try {
    await ElMessageBox.confirm('确认删除此教案? 此操作不可逆!', '删除', { type: 'error' })
    await lpApi.deletePlan(currentPlan.value.id)
    ElMessage.success('已删除')
    detailVisible.value = false
    await loadList()
  } catch (e: any) { if (e !== 'cancel') ElMessage.error(e.message || '操作失败') }
}

async function doFork() {
  if (!currentPlan.value) return
  try {
    const { value } = await ElMessageBox.prompt('请输入派生教案标题', 'Fork派生', {
      type: 'info', inputPlaceholder: '新教案标题', inputValue: `${currentPlan.value.title} (派生)`,
    })
    if (!value) return
    await lpApi.forkPlan(currentPlan.value.id, { title: value })
    ElMessage.success('派生成功')
    await loadList()
  } catch (e: any) { if (e !== 'cancel') ElMessage.error(e.message || '操作失败') }
}

/* ──── 新建教案 ──── */
const showCreateDialog = ref(false)
const creating = ref(false)
const createForm = reactive({
  title: '',
  description: '',
  subject_code: '',
  grade_level: '',
  lesson_type: 'new' as const,
  duration: 1,
  content: {
    teaching_objectives: [''] as string[],
    key_points: [''] as string[],
    difficulties: [] as string[],
    teaching_methods: [] as string[],
    teaching_process: [] as any[],
    homework: [] as string[],
    blackboard_design: '',
    reflection: '',
  } as LessonContent,
})

function resetCreateForm() {
  createForm.title = ''
  createForm.description = ''
  createForm.subject_code = ''
  createForm.grade_level = ''
  createForm.lesson_type = 'new'
  createForm.duration = 1
  createForm.content = {
    teaching_objectives: [''],
    key_points: [''],
    difficulties: [],
    teaching_methods: [],
    teaching_process: [],
    homework: [],
    blackboard_design: '',
    reflection: '',
  }
}

async function doCreate() {
  if (!createForm.title || !createForm.subject_code || !createForm.grade_level) {
    ElMessage.warning('请填写标题、学科和年级')
    return
  }
  creating.value = true
  try {
    const payload: lpApi.PlanCreatePayload = {
      title: createForm.title,
      description: createForm.description || undefined,
      subject_code: createForm.subject_code,
      grade_level: createForm.grade_level,
      lesson_type: createForm.lesson_type,
      duration: createForm.duration,
      content: createForm.content,
    }
    await lpApi.createPlan(payload)
    ElMessage.success('教案创建成功')
    showCreateDialog.value = false
    resetCreateForm()
    await loadList()
  } catch (e: any) {
    ElMessage.error(e.message || '创建失败')
  } finally {
    creating.value = false
  }
}

/* ──── 新版本 ──── */
const showVersionDialog = ref(false)
const versionSaving = ref(false)
const versionForm = reactive({ change_log: '', is_major: false })

async function doCreateVersion() {
  if (!currentPlan.value) return
  versionSaving.value = true
  try {
    await lpApi.createVersion(currentPlan.value.id, {
      content: currentPlan.value.latest_content || {} as LessonContent,
      change_log: versionForm.change_log || '内容更新',
      is_major: versionForm.is_major,
    })
    ElMessage.success('版本已保存')
    showVersionDialog.value = false
    versionForm.change_log = ''
    versionForm.is_major = false
    await refreshDetail()
  } catch (e: any) {
    ElMessage.error(e.message || '保存失败')
  } finally {
    versionSaving.value = false
  }
}

/* ──── 批注 ──── */
const showReviewDialog = ref(false)
const reviewSaving = ref(false)
const reviewForm = reactive({
  target_section: '',
  target_anchor: '',
  comment: '',
  severity: 'suggestion' as const,
})

async function doCreateReview() {
  if (!currentPlan.value) return
  if (!reviewForm.target_section || !reviewForm.comment) {
    ElMessage.warning('请选择批注位置并填写内容')
    return
  }
  reviewSaving.value = true
  try {
    await lpApi.createReview(currentPlan.value.id, {
      version_number: currentPlan.value.latest_version_number || currentPlan.value.current_version,
      target_section: reviewForm.target_section,
      target_anchor: reviewForm.target_anchor || undefined,
      comment: reviewForm.comment,
      severity: reviewForm.severity,
    })
    ElMessage.success('批注已添加')
    showReviewDialog.value = false
    reviewForm.target_section = ''
    reviewForm.target_anchor = ''
    reviewForm.comment = ''
    reviewForm.severity = 'suggestion'
    await loadReviews()
    await refreshDetail()
  } catch (e: any) {
    ElMessage.error(e.message || '添加批注失败')
  } finally {
    reviewSaving.value = false
  }
}

async function doResolveReview(r: ReviewResponse) {
  if (!currentPlan.value) return
  try {
    const { value } = await ElMessageBox.prompt('解决说明（可选）', '标记已解决', {
      type: 'success', inputPlaceholder: '解决说明',
    })
    await lpApi.resolveReview(currentPlan.value.id, r.id, { resolution_note: value || '' })
    ElMessage.success('批注已解决')
    await loadReviews()
    await refreshDetail()
  } catch (e: any) { if (e !== 'cancel') ElMessage.error(e.message || '操作失败') }
}

/* ──── 工具函数 ──── */
async function refreshDetail() {
  if (!currentPlan.value) return
  try {
    currentPlan.value = await lpApi.getPlan(currentPlan.value.id)
  } catch {}
}

function formatTime(s: string): string {
  if (!s) return '—'
  return s.replace('T', ' ').slice(0, 16)
}

function subjectLabel(code: string): string {
  const map: Record<string, string> = {
    chinese: '语文', math: '数学', english: '英语', physics: '物理',
    chemistry: '化学', biology: '生物', politics: '政治', history: '历史', geography: '地理',
  }
  return map[code] || code || '—'
}

const subjectOptions = Object.entries({
  chinese: '语文', math: '数学', english: '英语', physics: '物理',
  chemistry: '化学', biology: '生物', politics: '政治', history: '历史', geography: '地理',
}).map(([value, label]) => ({ value, label }))

function phaseColor(phase: string): 'primary' | 'success' | 'warning' | 'danger' | 'info' {
  const map: Record<string, 'primary' | 'success' | 'warning' | 'danger' | 'info'> = {
    '导入': 'primary', '新授': 'success', '练习': 'warning', '小结': 'info', '作业': 'danger',
  }
  return map[phase] || 'info'
}

import { planStatusTag, planStatusLabel, lessonTypeLabel, severityTag, severityLabel } from '@/api/researchLessonPrep'

onMounted(loadList)
</script>

<style scoped>
.lesson-prep-tab { padding: 0 4px; }

.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}
.flex-spacer { flex: 1; }

.plan-title-cell { display: flex; align-items: center; gap: 8px; }
.plan-title-text { font-weight: 600; }
.plan-desc { font-size: 12px; color: var(--el-text-color-secondary); margin-top: 4px; }
.version-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  background: var(--el-fill-color-light);
  font-size: 12px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
}
.pagination-row { margin-top: 16px; display: flex; justify-content: flex-end; }

/* 详情抽屉 */
.detail-content { padding: 0 8px; }
.meta-bar { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 20px; }
.meta-spacer { flex: 1; }
.meta-info { font-size: 13px; color: var(--el-text-color-secondary); }

.pipeline-section {
  margin-bottom: 20px;
  padding: 20px;
  background: var(--el-fill-color-light);
  border-radius: 8px;
}

.action-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 24px;
  padding-bottom: 20px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.section-title { font-size: 16px; font-weight: 600; margin: 0 0 12px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }

.content-section { margin-bottom: 28px; }
.content-list { margin: 0; padding-left: 20px; }
.content-list li { margin-bottom: 6px; line-height: 1.6; }
.method-tag { margin-right: 8px; margin-bottom: 4px; }
.blackboard-pre { white-space: pre-wrap; font-family: monospace; background: var(--el-fill-color); padding: 12px; border-radius: 6px; }
.reflection-text { line-height: 1.8; }

.process-step { padding-bottom: 8px; }
.process-content { margin: 8px 0; color: var(--el-text-color-primary); }
.process-activities, .process-resources { font-size: 13px; margin-top: 4px; }
.process-activities .label, .process-resources .label { color: var(--el-text-color-secondary); margin-right: 6px; }
.resource-text { color: var(--el-text-color-secondary); }

/* 版本轴 */
.version-section { margin-bottom: 28px; }
.version-timeline { padding: 8px 0 0 8px; }
.version-item { padding: 4px 0; }
.version-head { display: flex; align-items: center; gap: 8px; }
.version-num { font-weight: 700; font-size: 14px; }
.version-editor { font-size: 12px; color: var(--el-text-color-secondary); margin-left: auto; }
.version-log { font-size: 13px; color: var(--el-text-color-secondary); margin-top: 4px; }

/* 批注面板 */
.review-section { margin-bottom: 28px; }
.review-list { display: flex; flex-direction: column; gap: 12px; }
.review-item {
  padding: 12px 16px;
  border-radius: 8px;
  background: var(--el-fill-color-light);
  border-left: 3px solid var(--el-color-warning);
}
.review-item.resolved {
  border-left-color: var(--el-color-success);
  opacity: 0.7;
}
.review-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 8px; }
.review-section-name { font-weight: 600; font-size: 13px; }
.review-anchor { font-size: 12px; color: var(--el-text-color-secondary); }
.review-reviewer { font-size: 12px; color: var(--el-text-color-secondary); }
.review-time { font-size: 12px; color: var(--el-text-color-placeholder); margin-left: auto; }
.review-comment { line-height: 1.6; margin-bottom: 8px; }
.review-resolution {
  display: flex; align-items: center; gap: 6px;
  font-size: 13px; color: var(--el-color-success);
  margin-bottom: 8px;
}

/* 表单 */
.dynamic-list { display: flex; flex-direction: column; gap: 8px; width: 100%; }
.dynamic-item { display: flex; gap: 8px; align-items: center; }
.form-hint { margin-left: 8px; font-size: 12px; color: var(--el-text-color-secondary); }
</style>
