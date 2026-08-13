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
    <!-- ① 今日需要关注                           -->
    <!-- ════════════════════════════════════════ -->
    <el-card shadow="never" class="ws-card attention-card">
      <template #header>
        <span class="card-title">
          <el-icon><BellFilled /></el-icon> 今日需要关注
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
        description="暂无可信数据"
        :image-size="60"
        class="attention-empty"
      >
        <span class="empty-hint">待真实老师产生第一条可信记录后，这里会自动出现</span>
      </el-empty>
    </el-card>

    <!-- ════════════════════════════════════════ -->
    <!-- ② 本班动态                               -->
    <!-- ════════════════════════════════════════ -->
    <el-card shadow="never" class="ws-card">
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
    <!-- ③ 我的快捷操作                           -->
    <!-- ════════════════════════════════════════ -->
    <el-card shadow="never" class="ws-card">
      <template #header>
        <span class="card-title">
          <el-icon><EditPen /></el-icon> 我的快捷操作
        </span>
      </template>
      <div class="quick-actions">
        <el-button type="danger" size="large" class="quick-btn" @click="go('/behavior')">
          <el-icon><EditPen /></el-icon> 行为登记
          <span class="quick-sub">15 秒违纪记录</span>
        </el-button>
        <el-button type="success" size="large" class="quick-btn" @click="go('/evaluation/positive-entry')">
          <el-icon><Plus /></el-icon> 正向表扬
          <span class="quick-sub">15 秒表扬记录</span>
        </el-button>
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
} from '@element-plus/icons-vue'
import { useUserStore } from '@/store/user'
import { getWorkspaceSummary, type WorkspaceSummary } from '@/api/workstation'

const router = useRouter()
const userStore = useUserStore()

const summary = ref<WorkspaceSummary | null>(null)
const loading = ref(false)
const aiQuestion = ref('')

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
.dynamic-grid { margin: 0; }
.dynamic-col { padding-bottom: 4px; }
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
