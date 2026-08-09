<template>
  <div class="red-flag-center">
    <!-- Header -->
    <div class="page-header">
      <div class="header-left">
        <h2 class="page-title">
          <el-icon><Flag /></el-icon>
          流动红旗
        </h2>
        <span class="page-subtitle">常规评分 · 自动聚合 · 排行榜 · 归档历史</span>
      </div>
      <div class="header-right">
        <el-select v-model="selectedGradeId" placeholder="选择年级" style="width: 140px" @change="onGradeChange">
          <el-option v-for="g in grades" :key="g.id" :label="g.name" :value="g.id" />
        </el-select>
      </div>
    </div>

    <!-- Tabs -->
    <el-tabs v-model="activeTab" @tab-change="onTabChange">
      <!-- Tab 1: Leaderboard -->
      <el-tab-pane label="排行榜" name="leaderboard">
        <div class="leaderboard-toolbar">
          <el-select v-model="leaderboardPeriod" placeholder="周期类型" style="width: 120px" @change="fetchLeaderboard">
            <el-option value="weekly" label="周评" />
            <el-option value="monthly" label="月评" />
          </el-select>
          <el-input v-model="leaderboardLabel" placeholder="周期标签 (如: 第8周)" style="width: 160px" @change="fetchLeaderboard" />
          <el-button type="primary" :icon="Refresh" @click="fetchLeaderboard">刷新</el-button>
        </div>

        <div v-loading="loading.leaderboard">
          <!-- Top 3 Podium -->
          <div v-if="leaderboard.length >= 3" class="podium">
            <div class="podium-item second">
              <el-icon class="podium-medal"><Trophy /></el-icon>
              <div class="podium-class">{{ leaderboard[1]?.class_name }}</div>
              <div class="podium-score">{{ leaderboard[1]?.final_score?.toFixed(1) }}</div>
              <div class="podium-rank">No.2</div>
            </div>
            <div class="podium-item first">
              <el-icon class="podium-medal gold"><Trophy /></el-icon>
              <div class="podium-class">{{ leaderboard[0]?.class_name }}</div>
              <div class="podium-score">{{ leaderboard[0]?.final_score?.toFixed(1) }}</div>
              <div class="podium-rank">No.1</div>
            </div>
            <div class="podium-item third">
              <el-icon class="podium-medal"><Trophy /></el-icon>
              <div class="podium-class">{{ leaderboard[2]?.class_name }}</div>
              <div class="podium-score">{{ leaderboard[2]?.final_score?.toFixed(1) }}</div>
              <div class="podium-rank">No.3</div>
            </div>
          </div>

          <!-- Full Table -->
          <el-table :data="leaderboard" stripe style="width: 100%; margin-top: 16px">
            <el-table-column prop="rank" label="名次" width="80" align="center">
              <template #default="{ row }">
                <el-tag v-if="row.has_flag" type="danger" size="small" round>
                  <el-icon><Flag /></el-icon> {{ row.rank }}
                </el-tag>
                <span v-else class="rank-num">{{ row.rank }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="class_name" label="班级" width="120" />
            <el-table-column prop="final_score" label="最终得分" width="100" align="center">
              <template #default="{ row }">
                <span class="score-highlight">{{ row.final_score?.toFixed(1) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="卫生" width="80" align="center">
              <template #default="{ row }">{{ row.routine_hygiene?.toFixed(1) }}</template>
            </el-table-column>
            <el-table-column label="纪律" width="80" align="center">
              <template #default="{ row }">{{ row.routine_discipline?.toFixed(1) }}</template>
            </el-table-column>
            <el-table-column label="两操" width="80" align="center">
              <template #default="{ row }">{{ row.routine_exercise?.toFixed(1) }}</template>
            </el-table-column>
            <el-table-column label="违纪扣分" width="100" align="center">
              <template #default="{ row }">
                <span class="deduction">-{{ row.discipline_deduction?.toFixed(1) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="考勤扣分" width="100" align="center">
              <template #default="{ row }">
                <span class="deduction">-{{ row.attendance_deduction?.toFixed(1) }}</span>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-if="!loading.leaderboard && leaderboard.length === 0" description="暂无排行榜数据，请先生成并发布评价" />
        </div>
      </el-tab-pane>

      <!-- Tab 2: Routine Scores -->
      <el-tab-pane label="评分录入" name="routines">
        <!-- Quick Entry Form -->
        <el-card shadow="never" class="entry-card">
          <template #header>快速录入评分</template>
          <el-form :model="entryForm" label-width="80px" inline>
            <el-form-item label="班级">
              <el-select v-model="entryForm.class_id" placeholder="选择班级" style="width: 160px" filterable>
                <el-option v-for="c in classes" :key="c.id" :label="c.name" :value="c.id" />
              </el-select>
            </el-form-item>
            <el-form-item label="维度">
              <el-select v-model="entryForm.category" style="width: 100px">
                <el-option v-for="(label, key) in CATEGORY_LABELS" :key="key" :label="label" :value="key" />
              </el-select>
            </el-form-item>
            <el-form-item label="评分">
              <el-input-number v-model="entryForm.score" :min="0" :max="100" :precision="1" style="width: 120px" />
            </el-form-item>
            <el-form-item label="日期">
              <el-date-picker v-model="entryForm.record_date" type="date" format="YYYY-MM-DD" value-format="YYYY-MM-DD" style="width: 150px" />
            </el-form-item>
            <el-form-item label="备注">
              <el-input v-model="entryForm.note" placeholder="可选" style="width: 200px" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :icon="Plus" @click="handleAddRoutine" :loading="submitting">提交</el-button>
            </el-form-item>
          </el-form>
        </el-card>

        <!-- Routine List -->
        <div class="routines-toolbar" style="margin-top: 16px">
          <el-date-picker v-model="routineDateRange" type="daterange" start-placeholder="开始" end-placeholder="结束"
            format="YYYY-MM-DD" value-format="YYYY-MM-DD" style="width: 260px" @change="fetchRoutines" />
          <el-button type="primary" :icon="Refresh" @click="fetchRoutines">刷新</el-button>
        </div>
        <el-table :data="routines" v-loading="loading.routines" stripe style="width: 100%">
          <el-table-column prop="class_name" label="班级" width="120" />
          <el-table-column prop="category" label="维度" width="80">
            <template #default="{ row }">
              <el-tag :color="CATEGORY_COLORS[row.category as RoutineCategory]" effect="dark" size="small" style="border: none">
                {{ CATEGORY_LABELS[row.category as RoutineCategory] }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="score" label="评分" width="80" align="center" />
          <el-table-column prop="scorer_type" label="评分人" width="100">
            <template #default="{ row }">
              {{ SCORER_LABELS[row.scorer_type as ScorerType] || row.scorer_type }}
            </template>
          </el-table-column>
          <el-table-column prop="record_date" label="日期" width="120" />
          <el-table-column prop="inspector" label="检查人" width="100" />
          <el-table-column prop="note" label="备注" min-width="150" show-overflow-tooltip />
          <el-table-column label="操作" width="80" fixed="right">
            <template #default="{ row }">
              <el-button type="danger" size="small" :icon="Delete" circle @click="handleDeleteRoutine(row.id)" />
            </template>
          </el-table-column>
        </el-table>
        <el-empty v-if="!loading.routines && routines.length === 0" description="暂无评分记录" />
      </el-tab-pane>

      <!-- Tab 3: Generate & Publish (MS_ADMIN only) -->
      <el-tab-pane v-if="isAdmin" label="生成与发布" name="publish">
        <el-card shadow="never" class="entry-card">
          <template #header>生成评价草稿</template>
          <el-form :model="genForm" label-width="100px">
            <el-row :gutter="16">
              <el-col :span="8">
                <el-form-item label="周期类型">
                  <el-select v-model="genForm.period_type" style="width: 100%">
                    <el-option value="weekly" label="周评" />
                    <el-option value="monthly" label="月评" />
                  </el-select>
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item label="周期标签">
                  <el-input v-model="genForm.period_label" placeholder="如: 第8周" />
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item label="日期范围">
                  <el-date-picker v-model="genDateRange" type="daterange" start-placeholder="开始" end-placeholder="结束"
                    format="YYYY-MM-DD" value-format="YYYY-MM-DD" style="width: 100%" />
                </el-form-item>
              </el-col>
            </el-row>
            <el-form-item>
              <el-button type="primary" :icon="MagicStick" @click="handleGenerate" :loading="generating">生成草稿</el-button>
              <el-button type="success" :icon="Promotion" @click="handlePublish" :loading="publishing" :disabled="!drafts.length">发布</el-button>
              <el-button type="warning" :icon="Box" @click="handleArchive" :loading="archiving" :disabled="!drafts.length">归档</el-button>
            </el-form-item>
          </el-form>
        </el-card>

        <!-- Drafts -->
        <el-card shadow="never" style="margin-top: 16px" v-if="drafts.length">
          <template #header>
            <span>草稿列表 ({{ drafts.length }})</span>
          </template>
          <el-table :data="drafts" stripe size="small">
            <el-table-column prop="class_name" label="班级" width="100" />
            <el-table-column prop="final_score" label="得分" width="80" align="center">
              <template #default="{ row }">{{ row.final_score?.toFixed(1) }}</template>
            </el-table-column>
            <el-table-column prop="weighted_base" label="加权底分" width="100" align="center">
              <template #default="{ row }">{{ row.weighted_base?.toFixed(1) }}</template>
            </el-table-column>
            <el-table-column prop="discipline_deduction" label="违纪扣分" width="100" align="center">
              <template #default="{ row }">-{{ row.discipline_deduction?.toFixed(1) }}</template>
            </el-table-column>
            <el-table-column prop="attendance_deduction" label="考勤扣分" width="100" align="center">
              <template #default="{ row }">-{{ row.attendance_deduction?.toFixed(1) }}</template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>

      <!-- Tab 4: Archive History -->
      <el-tab-pane label="归档历史" name="history">
        <div class="history-toolbar">
          <el-select v-model="historyPeriodType" placeholder="周期类型" clearable style="width: 120px" @change="fetchHistory">
            <el-option value="weekly" label="周评" />
            <el-option value="monthly" label="月评" />
          </el-select>
          <el-button type="primary" :icon="Refresh" @click="fetchHistory">刷新</el-button>
        </div>
        <el-table :data="history" v-loading="loading.history" stripe style="width: 100%">
          <el-table-column prop="class_name" label="班级" width="120" />
          <el-table-column prop="period_type" label="类型" width="80">
            <template #default="{ row }">{{ row.period_type === 'weekly' ? '周评' : '月评' }}</template>
          </el-table-column>
          <el-table-column prop="period_label" label="周期" width="120" />
          <el-table-column prop="final_score" label="得分" width="80" align="center">
            <template #default="{ row }">{{ row.final_score?.toFixed(1) }}</template>
          </el-table-column>
          <el-table-column prop="rank" label="名次" width="80" align="center">
            <template #default="{ row }">
              <el-tag v-if="row.has_flag" type="danger" size="small" round>
                <el-icon><Flag /></el-icon> {{ row.rank }}
              </el-tag>
              <span v-else>{{ row.rank }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="archived_at" label="归档时间" min-width="160">
            <template #default="{ row }">{{ row.archived_at?.replace('T', ' ').slice(0, 16) }}</template>
          </el-table-column>
        </el-table>
        <el-empty v-if="!loading.history && history.length === 0" description="暂无归档历史" />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Flag, Trophy, Refresh, Plus, Delete, MagicStick, Promotion, Box } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useUserStore } from '@/store/user'
import { getGrades, getClasses } from '@/api/classes'
import {
  getLeaderboard, addRoutine, listRoutines, deleteRoutine,
  generateEvaluations, viewDrafts, publishEvaluations, archiveEvaluations, getArchiveHistory,
  CATEGORY_LABELS, CATEGORY_COLORS, SCORER_LABELS,
  type RoutineCategory, type ScorerType, type FlagLeaderboardItem, type RoutineScore, type ArchiveHistoryItem,
} from '@/api/redFlag'

const userStore = useUserStore()
const isAdmin = ref(userStore.currentRole === 'MS_ADMIN')

// ── 筛选 ──
const grades = ref<any[]>([])
const classes = ref<any[]>([])
const selectedGradeId = ref<number | null>(null)

// ── Tab ──
const activeTab = ref('leaderboard')

// ── 数据 ──
const leaderboard = ref<FlagLeaderboardItem[]>([])
const routines = ref<RoutineScore[]>([])
const drafts = ref<any[]>([])
const history = ref<ArchiveHistoryItem[]>([])

const loading = ref({
  leaderboard: false,
  routines: false,
  history: false,
})

// ── 表单 ──
const leaderboardPeriod = ref('weekly')
const leaderboardLabel = ref('')
const routineDateRange = ref<[string, string] | null>(null)
const historyPeriodType = ref('')

const entryForm = ref({
  class_id: null as number | null,
  category: 'hygiene' as RoutineCategory,
  score: 90,
  record_date: new Date().toISOString().slice(0, 10),
  note: '',
})

const genForm = ref({
  period_type: 'weekly' as 'weekly' | 'monthly',
  period_label: '',
})
const genDateRange = ref<[string, string] | null>(null)

const submitting = ref(false)
const generating = ref(false)
const publishing = ref(false)
const archiving = ref(false)

// ═══════════════════════════════════════════════════
// 初始化
// ═══════════════════════════════════════════════════

onMounted(async () => {
  try {
    const res: any = await getGrades()
    grades.value = res?.items || res || []
    if (grades.value.length > 0) {
      const userGradeId = (userStore.userInfo as any)?.grade_id
      selectedGradeId.value = userGradeId || grades.value[0].id
      await onGradeChange()
    }
  } catch {
    // silent
  }
})

async function onGradeChange() {
  if (!selectedGradeId.value) return
  try {
    const res: any = await getClasses({ grade_id: selectedGradeId.value })
    classes.value = res?.items || res || []
  } catch {
    classes.value = []
  }
  fetchData()
}

function fetchData() {
  if (activeTab.value === 'leaderboard') fetchLeaderboard()
  else if (activeTab.value === 'routines') fetchRoutines()
  else if (activeTab.value === 'history') fetchHistory()
}

function onTabChange() {
  fetchData()
}

// ═══════════════════════════════════════════════════
// Leaderboard
// ═══════════════════════════════════════════════════

async function fetchLeaderboard() {
  loading.value.leaderboard = true
  try {
    const params: any = { grade_id: selectedGradeId.value }
    if (leaderboardPeriod.value) params.period_type = leaderboardPeriod.value
    if (leaderboardLabel.value) params.period_label = leaderboardLabel.value
    const res: any = await getLeaderboard(params)
    leaderboard.value = res || []
  } catch {
    leaderboard.value = []
  } finally {
    loading.value.leaderboard = false
  }
}

// ═══════════════════════════════════════════════════
// Routines
// ═══════════════════════════════════════════════════

async function fetchRoutines() {
  loading.value.routines = true
  try {
    const params: any = {
      grade_id: selectedGradeId.value,
      limit: 100,
    }
    if (routineDateRange.value) {
      params.start_date = routineDateRange.value[0]
      params.end_date = routineDateRange.value[1]
    }
    const res: any = await listRoutines(params)
    routines.value = res?.items || res || []
  } catch {
    routines.value = []
  } finally {
    loading.value.routines = false
  }
}

async function handleAddRoutine() {
  if (!entryForm.value.class_id) {
    ElMessage.warning('请选择班级')
    return
  }
  submitting.value = true
  try {
    const role = userStore.currentRole
    const scorerType = role === 'MS_ADMIN' ? 'ms_admin' : role === 'GRADE_LEADER' ? 'grade_leader' : 'class_teacher'
    await addRoutine({
      class_id: entryForm.value.class_id,
      grade_id: selectedGradeId.value || undefined,
      category: entryForm.value.category,
      score: entryForm.value.score,
      scorer_type: scorerType as ScorerType,
      record_date: entryForm.value.record_date,
      note: entryForm.value.note || undefined,
    })
    ElMessage.success('评分录入成功')
    entryForm.value.note = ''
    fetchRoutines()
  } catch {
    // handled by interceptor
  } finally {
    submitting.value = false
  }
}

async function handleDeleteRoutine(id: number) {
  try {
    await ElMessageBox.confirm('确定删除这条评分记录？', '提示', { type: 'warning' })
    await deleteRoutine(id)
    ElMessage.success('已删除')
    fetchRoutines()
  } catch {
    // cancelled or error
  }
}

// ═══════════════════════════════════════════════════
// Generate / Publish / Archive
// ═══════════════════════════════════════════════════

async function handleGenerate() {
  if (!selectedGradeId.value || !genForm.value.period_label || !genDateRange.value) {
    ElMessage.warning('请填写完整的年级、周期标签和日期范围')
    return
  }
  const gid = selectedGradeId.value
  generating.value = true
  try {
    await generateEvaluations({
      grade_id: gid,
      period_type: genForm.value.period_type,
      period_label: genForm.value.period_label,
      start_date: genDateRange.value[0],
      end_date: genDateRange.value[1],
    })
    ElMessage.success('草稿生成成功')
    fetchDrafts()
  } catch {
    // handled
  } finally {
    generating.value = false
  }
}

async function fetchDrafts() {
  try {
    const res: any = await viewDrafts({ grade_id: selectedGradeId.value || undefined })
    drafts.value = res?.drafts || res || []
  } catch {
    drafts.value = []
  }
}

async function handlePublish() {
  if (!selectedGradeId.value || !genForm.value.period_label) {
    ElMessage.warning('请确保年级和周期标签已填写')
    return
  }
  const gid = selectedGradeId.value
  publishing.value = true
  try {
    await publishEvaluations({
      grade_id: gid,
      period_type: genForm.value.period_type,
      period_label: genForm.value.period_label,
    })
    ElMessage.success('发布成功')
    drafts.value = []
    fetchLeaderboard()
  } catch {
    // handled
  } finally {
    publishing.value = false
  }
}

async function handleArchive() {
  if (!selectedGradeId.value || !genForm.value.period_label) {
    ElMessage.warning('请确保年级和周期标签已填写')
    return
  }
  const gid = selectedGradeId.value
  archiving.value = true
  try {
    await archiveEvaluations({
      grade_id: gid,
      period_type: genForm.value.period_type,
      period_label: genForm.value.period_label,
    })
    ElMessage.success('归档成功')
    drafts.value = []
    fetchHistory()
  } catch {
    // handled
  } finally {
    archiving.value = false
  }
}

// ═══════════════════════════════════════════════════
// History
// ═══════════════════════════════════════════════════

async function fetchHistory() {
  loading.value.history = true
  try {
    const params: any = {
      grade_id: selectedGradeId.value,
      limit: 50,
    }
    if (historyPeriodType.value) params.period_type = historyPeriodType.value
    const res: any = await getArchiveHistory(params)
    history.value = res?.items || res || []
  } catch {
    history.value = []
  } finally {
    loading.value.history = false
  }
}
</script>

<style scoped>
.red-flag-center {
  padding: 0 0 20px 0;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  flex-wrap: wrap;
  gap: 12px;
}

.page-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 20px;
  margin: 0;
  color: #303133;
}

.page-subtitle {
  font-size: 12px;
  color: #909399;
  margin-left: 12px;
}

/* Podium */
.podium {
  display: flex;
  justify-content: center;
  align-items: flex-end;
  gap: 20px;
  padding: 20px 0;
}

.podium-item {
  text-align: center;
  padding: 16px 20px;
  border-radius: 12px 12px 0 0;
  min-width: 120px;
  transition: transform 0.2s;
}

.podium-item:hover {
  transform: translateY(-4px);
}

.podium-item.first {
  background: linear-gradient(135deg, #ffd700, #ffa500);
  height: 140px;
  color: #fff;
}

.podium-item.second {
  background: linear-gradient(135deg, #c0c0c0, #a8a8a8);
  height: 110px;
  color: #fff;
}

.podium-item.third {
  background: linear-gradient(135deg, #cd7f32, #b87333);
  height: 90px;
  color: #fff;
}

.podium-medal {
  font-size: 28px;
  margin-bottom: 4px;
}

.podium-medal.gold {
  font-size: 32px;
}

.podium-class {
  font-size: 16px;
  font-weight: 600;
}

.podium-score {
  font-size: 24px;
  font-weight: 700;
  margin: 4px 0;
}

.podium-rank {
  font-size: 13px;
  opacity: 0.9;
}

/* Score highlight */
.score-highlight {
  font-size: 18px;
  font-weight: 700;
  color: #f56c6c;
}

.deduction {
  color: #e6a23c;
  font-weight: 600;
}

.rank-num {
  font-size: 16px;
  font-weight: 600;
  color: #606266;
}

.entry-card {
  margin-bottom: 4px;
}

.leaderboard-toolbar,
.routines-toolbar,
.history-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
}
</style>
