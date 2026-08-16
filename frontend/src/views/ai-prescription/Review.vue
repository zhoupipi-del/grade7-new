<template>
  <div class="review-queue-container">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>待审核 AI 处方</span>
          <div class="header-actions">
            <el-tag size="small" type="warning" effect="plain">{{ pendingCount }} 条待审</el-tag>
            <el-button size="small" :loading="loading" @click="loadList">刷新</el-button>
          </div>
        </div>
      </template>

      <!-- 列表：仅处理所需摘要，不铺全量心理档案 -->
      <el-table :data="items" v-loading="loading" stripe empty-text="暂无待审核处方">
        <el-table-column label="学生" min-width="110">
          <template #default="{ row }">
            <span class="link-like" @click="openDetail(row)">{{ row.student_name || `#${row.target_id}` }}</span>
          </template>
        </el-table-column>
        <el-table-column label="风险" width="110">
          <template #default="{ row }">
            <el-tag :type="riskTagType(row.risk_level)" size="small">{{ riskLabel(row.risk_level) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="来源" width="100">
          <template #default="{ row }">RDI 桥接</template>
        </el-table-column>
        <el-table-column label="生成时间" width="160">
          <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="依据摘要" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">{{ row.summary || '--' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" plain :disabled="row._busy" @click="onConfirm(row)">确认</el-button>
            <el-button size="small" type="warning" plain :disabled="row._busy" @click="openModify(row)">修改</el-button>
            <el-button size="small" type="danger" plain :disabled="row._busy" @click="openReject(row)">拒绝</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 详情抽屉：完整 AI 建议（由后端 psych assignment 控制读取权限） -->
    <el-drawer v-model="detailVisible" :title="detailTitle" size="45%">
      <div v-loading="detailLoading">
        <div class="detail-body" v-html="detailHtml"></div>
      </div>
    </el-drawer>

    <!-- 修改后确认 -->
    <el-dialog v-model="modifyVisible" title="修改后确认" width="640px">
      <el-form label-width="90px">
        <el-form-item label="修改内容" required>
          <el-input
            v-model="modifyContent"
            type="textarea"
            :rows="8"
            placeholder="填写修改后的完整处方内容（必填，不能与原稿相同）"
          />
        </el-form-item>
        <el-form-item label="复核意见">
          <el-input v-model="modifyNote" type="textarea" :rows="2" placeholder="可选" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="modifyVisible = false">取消</el-button>
        <el-button type="warning" :loading="actionBusy" @click="submitModify">提交修改</el-button>
      </template>
    </el-dialog>

    <!-- 拒绝 -->
    <el-dialog v-model="rejectVisible" title="拒绝（AI 建议不采纳）" width="480px">
      <el-form label-width="90px">
        <el-form-item label="拒绝原因" required>
          <el-input v-model="rejectNote" type="textarea" :rows="3" placeholder="必须填写拒绝原因（审计留证）" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="rejectVisible = false">取消</el-button>
        <el-button type="danger" :loading="actionBusy" :disabled="!rejectNote.trim()" @click="submitReject">确认拒绝</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  listPendingReviews,
  getPrescriptionRecord,
  confirmPrescription,
  modifyPrescription,
  rejectPrescription,
  type PrescriptionHistoryItem,
} from '@/api/prescription'

const loading = ref(false)
const actionBusy = ref(false)
const items = ref<PrescriptionHistoryItem[]>([])
const pendingCount = computed(() => items.value.length)

// detail
const detailVisible = ref(false)
const detailLoading = ref(false)
const detailTitle = ref('')
const detailHtml = ref('')
let currentRow: PrescriptionHistoryItem | null = null

// modify
const modifyVisible = ref(false)
const modifyContent = ref('')
const modifyNote = ref('')

// reject
const rejectVisible = ref(false)
const rejectNote = ref('')

async function loadList() {
  loading.value = true
  try {
    const res = await listPendingReviews({ per_page: 100 })
    items.value = (res.items || []).map((it) => ({ ...it, _busy: false }))
  } catch (e) {
    ElMessage.error('加载待审核列表失败')
  } finally {
    loading.value = false
  }
}

function fmtTime(v?: string) {
  if (!v) return '--'
  return v.replace('T', ' ').slice(0, 19)
}
function riskTagType(level?: string): '' | 'success' | 'warning' | 'danger' {
  if (level === 'HIGH' || level === 'CRITICAL') return 'danger'
  if (level === 'MEDIUM') return 'warning'
  return 'success'
}
function riskLabel(level?: string) {
  return level || '--'
}

async function openDetail(row: PrescriptionHistoryItem) {
  currentRow = row
  detailVisible.value = true
  detailTitle.value = `处方详情 #${row.id}`
  detailHtml.value = '<p style="color:#999">加载中...</p>'
  detailLoading.value = true
  try {
    const detail = await getPrescriptionRecord(row.id)
    detailHtml.value = detail?.full_text
      ? `<pre style="white-space:pre-wrap;font-family:inherit">${escapeHtml(detail.full_text)}</pre>`
      : '<p style="color:#999">无内容</p>'
  } catch (e: any) {
    detailHtml.value = `<p style="color:#f56c6c">读取失败：${e?.message || '无权限或不存在'}</p>`
  } finally {
    detailLoading.value = false
  }
}
function escapeHtml(s: string) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

function setBusy(row: PrescriptionHistoryItem | null, v: boolean) {
  if (row) row._busy = v
  actionBusy.value = v
}

async function onConfirm(row: PrescriptionHistoryItem) {
  try {
    await ElMessageBox.confirm(
      `确认采用 AI 建议（处方 #${row.id}）？确认后进入正式流程。`,
      '确认审核',
      { confirmButtonText: '确认', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  setBusy(row, true)
  try {
    await confirmPrescription(row.id)
    ElMessage.success('已确认')
    await loadList()
  } catch (e: any) {
    handle409(e)
  } finally {
    setBusy(row, false)
  }
}

function openModify(row: PrescriptionHistoryItem) {
  currentRow = row
  modifyContent.value = ''
  modifyNote.value = ''
  modifyVisible.value = true
}

async function submitModify() {
  if (!currentRow) return
  const content = modifyContent.value.trim()
  if (!content) {
    ElMessage.warning('修改内容不能为空')
    return
  }
  setBusy(currentRow, true)
  try {
    await modifyPrescription(currentRow.id, { modified_content: content, review_note: modifyNote.value.trim() || undefined })
    ElMessage.success('修改后确认成功')
    modifyVisible.value = false
    await loadList()
  } catch (e: any) {
    handle409(e)
  } finally {
    setBusy(currentRow, false)
  }
}

function openReject(row: PrescriptionHistoryItem) {
  currentRow = row
  rejectNote.value = ''
  rejectVisible.value = true
}

async function submitReject() {
  if (!currentRow) return
  const note = rejectNote.value.trim()
  if (!note) {
    ElMessage.warning('必须填写拒绝原因')
    return
  }
  setBusy(currentRow, true)
  try {
    await rejectPrescription(currentRow.id, note)
    ElMessage.success('已拒绝')
    rejectVisible.value = false
    await loadList()
  } catch (e: any) {
    handle409(e)
  } finally {
    setBusy(currentRow, false)
  }
}

/** 409 = 已被其他人员处理（_ensure_pending 并发保护）→ 提示并刷新 */
function handle409(e: any) {
  if (e?.response?.status === 409) {
    ElMessage.warning('该处方已被其他人员处理，请刷新')
    loadList()
  } else if (e?.response?.status === 403) {
    ElMessage.error('无权限执行此操作')
  } else {
    ElMessage.error(e?.message || '操作失败')
  }
}

onMounted(loadList)
</script>

<style scoped>
.review-queue-container { padding: 16px; }
.card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 600; }
.header-actions { display: flex; gap: 8px; align-items: center; }
.link-like { color: var(--el-color-primary); cursor: pointer; }
.detail-body { line-height: 1.7; }
</style>
