<template>
  <div class="home-workstation">
    <!-- ════════════════════════════════════════ -->
    <!-- 工作台头部：2501班 · 今日工作台          -->
    <!-- ════════════════════════════════════════ -->
    <div class="ws-header">
      <div class="ws-header-title">
        <el-icon :size="22"><HomeFilled /></el-icon>
        <h2 class="ws-title">{{ scopeName }} · 今日工作台</h2>
      </div>
      <el-tag v-if="summary" type="info" effect="plain" size="small">
        {{ studentCountText }}
      </el-tag>
    </div>

    <!-- ════════════════════════════════════════ -->
    <!-- ① 今日需要关注 / 今日重点                -->
    <!-- ════════════════════════════════════════ -->
    <el-card shadow="never" class="ws-card attention-card">
      <template #header>
        <span class="card-title">
          <el-icon><BellFilled /></el-icon>
          {{ isGradeLeader ? '今日重点' : '今日需要关注' }}
        </span>
      </template>
      <div v-if="summary && summary.attention.length > 0" class="attention-list">
        <div
          v-for="(item, i) in summary.attention"
          :key="i"
          class="attention-item"
          :class="'level-' + item.level"
        >
          <el-icon><WarningFilled /></el-icon>
          <div class="attention-body">
            <div class="attention-title">{{ item.title }}</div>
            <div class="attention-hint">{{ item.hint }}</div>
          </div>
        </div>
      </div>
      <el-empty
        v-else
        description="暂无可信异常"
        :image-size="60"
        class="attention-empty"
      >
        <span class="empty-hint">有真实可信异常后这里会自动出现</span>
      </el-empty>
    </el-card>

    <!-- ════════════════════════════════════════ -->
    <!-- ② 年级概览（年级组长专属）              -->
    <!-- ════════════════════════════════════════ -->
    <el-card v-if="isGradeLeader" shadow="never" class="ws-card">
      <template #header>
        <span class="card-title">
          <el-icon><DataAnalysis /></el-icon> 年级概览
        </span>
      </template>
      <el-row :gutter="12" class="overview-grid">
        <el-col :span="6" class="overview-col">
          <div class="overview-card">
            <div class="overview-label">学生数</div>
            <div class="overview-value">{{ summary?.cards.student_count ?? '—' }}</div>
          </div>
        </el-col>
        <el-col :span="6" class="overview-col">
          <div class="overview-card">
            <div class="overview-label">班级数</div>
            <div class="overview-value">{{ summary?.cards.class_count ?? '—' }}</div>
          </div>
        </el-col>
        <el-col :span="6" class="overview-col">
          <div class="overview-card" @click="go('/behavior')">
            <div class="overview-label">可信行为数</div>
            <div class="overview-value">{{ summary?.cards.trusted_behavior_count ?? '—' }}</div>
            <el-tag :type="qualityTag(summary?.data_quality.behavior)" size="small" effect="plain">
              {{ qualityText(summary?.data_quality.behavior) }}
            </el-tag>
          </div>
        </el-col>
        <el-col :span="6" class="overview-col">
          <div class="overview-card" @click="go('/evaluation/positive-entry')">
            <div class="overview-label">可信表扬数</div>
            <div class="overview-value">{{ summary?.cards.trusted_praise_count ?? '—' }}</div>
            <el-tag :type="qualityTag(summary?.data_quality.praise)" size="small" effect="plain">
              {{ qualityText(summary?.data_quality.praise) }}
            </el-tag>
          </div>
        </el-col>
      </el-row>
      <div v-if="(summary?.cards.trusted_behavior_count ?? 0) === 0 && (summary?.cards.trusted_praise_count ?? 0) === 0" class="trusted-empty-note">
        本学期暂无可信人工行为记录 · 暂无可信正向表扬记录（仅统计 teacher_manual）
      </div>
    </el-card>

    <!-- ════════════════════════════════════════ -->
    <!-- ②/③ 本班动态 / 班级对比                  -->
    <!-- ════════════════════════════════════════ -->
    <el-card v-if="!isGradeLeader" shadow="never" class="ws-card">
      <template #header>
        <span class="card-title">
          <el-icon><TrendCharts /></el-icon> 本班动态
        </span>
      </template>
      <el-row :gutter="12" class="dynamic-grid">
        <!-- 可信行为记录 -->
        <el-col :span="6" class="dynamic-col">
          <div class="dynamic-card" @click="go('/behavior')">
            <div class="dynamic-label">可信行为记录</div>
            <div class="dynamic-value">{{ summary?.cards.trusted_behavior_count ?? '—' }}</div>
            <el-tag :type="qualityTag(summary?.data_quality.behavior)" size="small" effect="plain">
              {{ qualityText(summary?.data_quality.behavior) }}
            </el-tag>
          </div>
        </el-col>
        <!-- 正向表扬记录 -->
        <el-col :span="6" class="dynamic-col">
          <div class="dynamic-card" @click="go('/evaluation/positive-entry')">
            <div class="dynamic-label">正向表扬</div>
            <div class="dynamic-value">{{ summary?.cards.trusted_praise_count ?? '—' }}</div>
            <el-tag :type="qualityTag(summary?.data_quality.praise)" size="small" effect="plain">
              {{ qualityText(summary?.data_quality.praise) }}
            </el-tag>
          </div>
        </el-col>
        <!-- 考勤（来源未核验，诚实标注） -->
        <el-col :span="6" class="dynamic-col">
          <div class="dynamic-card" @click="go('/attendance')">
            <div class="dynamic-label">考勤</div>
            <div class="dynamic-value dynamic-value-note">待核验</div>
            <el-tag type="warning" size="small" effect="plain">来源未核验</el-tag>
          </div>
        </el-col>
        <!-- 成绩变化 -->
        <el-col :span="6" class="dynamic-col">
          <div class="dynamic-card" @click="go('/grades/dashboard')">
            <div class="dynamic-label">成绩变化</div>
            <div class="dynamic-value dynamic-value-note">建设中</div>
            <el-tag type="info" size="small" effect="plain">待接入</el-tag>
          </div>
        </el-col>
      </el-row>
    </el-card>

    <!-- ════════════════════════════════════════ -->
    <!-- ③ 班级对比（年级组长专属）              -->
    <!-- ════════════════════════════════════════ -->
    <el-card v-if="isGradeLeader" shadow="never" class="ws-card">
      <template #header>
        <span class="card-title">
          <el-icon><Histogram /></el-icon> 班级对比
          <span class="card-hint">仅可信口径（teacher_manual）· 考勤/成绩来源未核验</span>
        </span>
      </template>
      <el-table
        :data="summary?.class_compare ?? []"
        v-loading="loading"
        style="width: 100%"
        size="default"
        stripe
      >
        <el-table-column prop="class_name" label="班级" width="140">
          <template #default="{ row }">
            <span class="class-link" @click="goClass(row.class_id)">{{ row.class_name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="student_count" label="学生数" width="100" align="center" />
        <el-table-column label="可信行为" width="120" align="center">
          <template #default="{ row }">
            <el-tag :type="row.trusted_behavior_count > 0 ? 'danger' : 'info'" size="small">
              {{ row.trusted_behavior_count }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="正向表扬" width="120" align="center">
          <template #default="{ row }">
            <el-tag :type="row.trusted_praise_count > 0 ? 'success' : 'info'" size="small">
              {{ row.trusted_praise_count }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="考勤" align="center">
          <template #default>
            <el-tag type="warning" size="small" effect="plain">来源未核验</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="成绩" align="center">
          <template #default>
            <el-tag type="info" size="small" effect="plain">待接入</el-tag>
          </template>
        </el-table-column>
      </el-table>
      <el-empty
        v-if="!summary?.class_compare?.length && !loading"
        description="暂无班级数据"
        :image-size="50"
      />
    </el-card>

    <!-- ════════════════════════════════════════ -->
    <!-- ④ 我的快捷操作                           -->
    <!-- ════════════════════════════════════════ -->
    <el-card shadow="never" class="ws-card">
      <template #header>
        <span class="card-title">
          <el-icon><EditPen /></el-icon> 我的快捷操作
        </span>
      </template>
      <div class="quick-actions">
        <template v-if="isGradeLeader">
          <el-button type="primary" size="large" class="quick-btn" @click="go('/class-mgmt')">
            <el-icon><School /></el-icon> 查看班级
            <span class="quick-sub">班级管理</span>
          </el-button>
          <el-button type="warning" size="large" class="quick-btn" @click="askAI()">
            <el-icon><MagicStick /></el-icon> AI 分析年级
            <span class="quick-sub">一句话了解年级情况</span>
          </el-button>
        </template>
        <template v-else>
          <el-button type="danger" size="large" class="quick-btn" @click="go('/behavior')">
            <el-icon><EditPen /></el-icon> 行为登记
            <span class="quick-sub">15 秒违纪记录</span>
          </el-button>
          <el-button type="success" size="large" class="quick-btn" @click="go('/evaluation/positive-entry')">
            <el-icon><Plus /></el-icon> 正向表扬
            <span class="quick-sub">15 秒表扬记录</span>
          </el-button>
        </template>
      </div>
    </el-card>

    <!-- ════════════════════════════════════════ -->
    <!-- ④ AI 助手                                -->
    <!-- ════════════════════════════════════════ -->
    <el-card shadow="never" class="ws-card">
      <template #header>
        <span class="card-title">
          <el-icon><MagicStick /></el-icon> AI 助手
        </span>
      </template>
      <div class="ai-box">
        <el-input
          v-model="aiQuestion"
          placeholder="帮我看看{{ scopeName }}最近有什么值得关注"
          size="large"
          @keyup.enter="askAI"
        >
          <template #append>
            <el-button type="primary" @click="askAI">
              <el-icon><Search /></el-icon> 问 AI
            </el-button>
          </template>
        </el-input>
        <div class="ai-hint">AI 仅基于可信数据（teacher_manual）分析，不臆造</div>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * HomeWorkstation.vue — 班主任工作台 V1（2026-08-13）
 *
 * 2501 班主任登录后第一屏：
 *   ① 今日需要关注（真实可信数据聚合，空 → 暂无可信数据）
 *   ② 本班动态（可信行为/正向表扬/考勤[来源未核验]/成绩[待接入]）
 *   ③ 快捷操作（行为登记/正向表扬）
 *   ④ AI 助手（一句话提问 → ai-copilot）
 *   ⑤ 更多（MainLayout 侧边栏已收纳 56 个旧菜单）
 *
 * 数据源：GET /api/v1/me/workspace-summary（后端验权 + 组装 ViewModel）
 * 铁律：不假造待办；open_tasks=None 时绝不显示假任务。
 */

import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  HomeFilled, BellFilled, TrendCharts, EditPen, Plus, MagicStick, Search, WarningFilled,
  DataAnalysis, Histogram, School,
} from '@element-plus/icons-vue'
import { useUserStore } from '@/store/user'
import { getWorkspaceSummary, type WorkspaceSummary } from '@/api/workstation'

const router = useRouter()
const userStore = useUserStore()

const summary = ref<WorkspaceSummary | null>(null)
const loading = ref(false)
const aiQuestion = ref('')

const isGradeLeader = computed(() => userStore.currentIdentity === 'grade_leader')
const scopeName = computed(() => summary.value?.scope?.name ?? userStore.currentWorkstationTitle ?? '本班')
const studentCountText = computed(() => {
  const n = summary.value?.cards?.student_count
  return n !== null && n !== undefined ? `${n} 名学生` : ''
})

const QUALITY_TEXT: Record<string, string> = {
  trusted: '可信',
  ready_but_no_real_data: '就绪·无真实数据',
  source_unverified: '来源未核验',
}
const QUALITY_TAG: Record<string, string> = {
  trusted: 'success',
  ready_but_no_real_data: 'info',
  source_unverified: 'warning',
}

function qualityText(q?: string) {
  return (q && QUALITY_TEXT[q]) || '未知'
}
function qualityTag(q?: string) {
  return (q && QUALITY_TAG[q]) || 'info'
}

onMounted(async () => {
  await loadSummary()
})

async function loadSummary() {
  const ws = userStore.currentWorkstation
  if (!ws) return
  loading.value = true
  try {
    summary.value = await getWorkspaceSummary({
      identity: ws.identity,
      scope_type: ws.scope_type,
      scope_id: ws.scope_id,
    })
  } catch (err: any) {
    ElMessage.error(`加载工作台失败: ${err.message || err}`)
  } finally {
    loading.value = false
  }
}

function go(path: string) {
  router.push(path)
}

function goClass(classId: number) {
  // 班级对比 → 查看具体班级（年级组长视角）
  router.push({ path: '/student-registry', query: { class_id: String(classId) } })
}

function askAI() {
  const q = aiQuestion.value.trim() || `帮我看看${scopeName.value}最近有什么值得关注`
  router.push({ path: '/ai-copilot', query: { goal: q } })
}
</script>

<style scoped>
.home-workstation {
  padding: 16px;
  background: #f5f7fa;
  min-height: calc(100vh - 64px);
}

.ws-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
  padding: 14px 18px;
  background: linear-gradient(135deg, #1e6091 0%, #184d74 100%);
  border-radius: 10px;
  color: #fff;
}

.ws-header-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.ws-title {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
}

.ws-card {
  margin-bottom: 14px;
  border-radius: 10px;
}

.card-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
  font-size: 15px;
}

/* ① 今日需要关注 */
.attention-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 8px;
  margin-bottom: 8px;
  background: #f0f9eb;
  color: #529b2e;
}
.attention-item.level-success { background: #f0f9eb; color: #529b2e; }
.attention-item.level-info { background: #ecf5ff; color: #409eff; }
.attention-item.level-warning { background: #fdf6ec; color: #e6a23c; }
.attention-body { flex: 1; }
.attention-title { font-weight: 600; font-size: 14px; }
.attention-hint { font-size: 12px; opacity: 0.75; margin-top: 2px; }
.attention-empty :deep(.el-empty__description p) { color: #909399; }
.empty-hint { font-size: 12px; color: #c0c4cc; }

/* ② 本班动态 */
.dynamic-grid { margin: 0; }.dynamic-col { padding-bottom: 4px; }

/* ② 年级概览（年级组长） */
.overview-grid { margin: 0; }
.overview-col { padding-bottom: 4px; }
.overview-card {
  padding: 14px;
  border-radius: 8px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  text-align: center;
  cursor: default;
}
.overview-card:hover { border-color: #409eff; }
.overview-label { font-size: 13px; color: #909399; }
.overview-value {
  font-size: 26px;
  font-weight: 700;
  color: #303133;
  margin: 6px 0;
}
.trusted-empty-note {
  margin-top: 10px;
  font-size: 13px;
  color: #909399;
  text-align: center;
}

/* ③ 班级对比 */
.card-hint {
  margin-left: 10px;
  font-size: 12px;
  font-weight: 400;
  color: #909399;
}
.class-link {
  color: #409eff;
  cursor: pointer;
  font-weight: 500;
}
.class-link:hover { text-decoration: underline; }

.dynamic-card {
  padding: 14px;
  border-radius: 8px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  cursor: pointer;
  transition: all 0.2s;
  text-align: center;
}
.dynamic-card:hover {
  border-color: #409eff;
  box-shadow: 0 2px 8px rgba(64, 158, 255, 0.15);
}
.dynamic-label { font-size: 13px; color: #909399; }
.dynamic-value {
  font-size: 26px;
  font-weight: 700;
  color: #303133;
  margin: 6px 0;
}
.dynamic-value-note { font-size: 18px; color: #909399; }

/* ③ 快捷操作 */
.quick-actions {
  display: flex;
  gap: 14px;
}
.quick-btn {
  flex: 1;
  height: 64px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  border-radius: 10px;
}
.quick-sub {
  font-size: 12px;
  font-weight: 400;
  opacity: 0.85;
}

/* ④ AI 助手 */
.ai-box { display: flex; flex-direction: column; gap: 8px; }
.ai-hint { font-size: 12px; color: #c0c4cc; }
</style>
