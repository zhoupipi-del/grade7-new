<template>
  <div class="nexus-board-container">
    <!-- ═══════════════════════════════════════════════════════ -->
    <!-- 顶格: 核心战损数字看板                                      -->
    <!-- ═══════════════════════════════════════════════════════ -->
    <el-row :gutter="12" class="stats-row">
      <el-col :span="4">
        <div class="stat-card stat-critical-glow" @click="filterByPriority('CRITICAL')">
          <div class="stat-value" :style="{ color: '#f85149' }">
            {{ dashboard?.co_trigger_count ?? '--' }}
          </div>
          <div class="stat-label">双轨并发危机</div>
          <div class="stat-sub" v-if="dashboard && dashboard.total_academic_alerts > 0">
            {{ ((dashboard.co_trigger_count / dashboard.total_academic_alerts) * 100).toFixed(1) }}% 并发率
          </div>
        </div>
      </el-col>
      <el-col :span="4">
        <div class="stat-card stat-academic-red" @click="filterByPriority('WATCH')">
          <div class="stat-value" :style="{ color: '#f85149' }">
            {{ dashboard?.academic_red_count ?? '--' }}
          </div>
          <div class="stat-label">学业红灯</div>
          <div class="stat-sub">Z-Score 极度弱势</div>
        </div>
      </el-col>
      <el-col :span="4">
        <div class="stat-card" @click="filterByPriority('WATCH')">
          <div class="stat-value" :style="{ color: '#d29922' }">
            {{ dashboard?.academic_yellow_count ?? '--' }}
          </div>
          <div class="stat-label">学业黄灯</div>
          <div class="stat-sub">趋势异常待观察</div>
        </div>
      </el-col>
      <el-col :span="4">
        <div class="stat-card">
          <div class="stat-value" :style="{ color: '#a371f7' }">
            {{ dashboard?.total_rdi_warnings ?? '--' }}
          </div>
          <div class="stat-label">RDI 四维预警</div>
          <div class="stat-sub">行为/考勤/学业/心理</div>
        </div>
      </el-col>
      <el-col :span="4">
        <div class="stat-card" @click="filterByPriority('WATCH')">
          <div class="stat-value" :style="{ color: '#58a6ff' }">
            {{ nexus?.watch_count ?? '--' }}
          </div>
          <div class="stat-label">关注 (WATCH)</div>
          <div class="stat-sub">单轨预警待干预</div>
        </div>
      </el-col>
      <el-col :span="4">
        <div class="stat-card">
          <div class="stat-value" :style="{ color: '#8b949e' }">
            {{ nexus?.total ?? '--' }}
          </div>
          <div class="stat-label">预警学生总数</div>
          <div class="stat-sub">{{ dashboard?.total_profiles ?? '--' }} 心理档案</div>
        </div>
      </el-col>
    </el-row>

    <!-- ═══════════════════════════════════════════════════════ -->
    <!-- 双环形进度条: 学业红灯 vs 心理高危                          -->
    <!-- ═══════════════════════════════════════════════════════ -->
    <el-row :gutter="12" class="rings-row">
      <el-col :span="12">
        <div class="ring-card">
          <div class="ring-header">
            <span class="ring-title">
              <span class="ring-dot" :style="{ background: '#f85149' }"></span>
              学业红灯雷达
            </span>
            <span class="ring-meta">{{ dashboard?.academic_red_count ?? 0 }} / {{ dashboard?.total_academic_alerts ?? 0 }} 人触发</span>
          </div>
          <div ref="academicRingRef" class="ring-chart"></div>
        </div>
      </el-col>
      <el-col :span="12">
        <div class="ring-card">
          <div class="ring-header">
            <span class="ring-title">
              <span class="ring-dot" :style="{ background: '#d29922' }"></span>
              心理防线预警
            </span>
            <span class="ring-meta">{{ psyHighRiskCount }} / {{ dashboard?.total_profiles ?? 0 }} 档案</span>
          </div>
          <div ref="psyRingRef" class="ring-chart"></div>
        </div>
      </el-col>
    </el-row>

    <!-- ═══════════════════════════════════════════════════════ -->
    <!-- 战术雷达数据矩阵                                           -->
    <!-- ═══════════════════════════════════════════════════════ -->
    <div class="matrix-card">
      <!-- 筛选条 -->
      <div class="filter-bar">
        <div class="filter-left">
          <el-switch
            v-model="coTriggerOnly"
            active-text="仅看并发"
            inactive-text=""
            :style="{ '--el-switch-on-color': '#f85149' }"
          />
          <el-select v-model="minPriority" placeholder="优先级" clearable size="small" style="width: 120px">
            <el-option label="危急" value="CRITICAL" />
            <el-option label="紧急" value="URGENT" />
            <el-option label="关注" value="WATCH" />
          </el-select>
          <el-select v-model="selectedClassId" placeholder="全部班级" clearable size="small" style="width: 160px">
            <el-option
              v-for="c in classList"
              :key="c.id"
              :label="c.name"
              :value="c.id"
            />
          </el-select>
        </div>
        <div class="filter-right">
          <el-button :icon="Refresh" size="small" @click="loadData" :loading="loading">
            刷新
          </el-button>
        </div>
      </div>

      <!-- 数据表 -->
      <el-table
        :data="nexus?.items ?? []"
        v-loading="loading"
        :row-class-name="rowClassName"
        @row-click="openDetail"
        style="width: 100%; cursor: pointer"
        size="small"
        :header-cell-style="{ background: '#161b22', color: '#8b949e', borderBottom: '1px solid #30363d' }"
        :cell-style="{ borderBottom: '1px solid #21262d' }"
      >
        <el-table-column label="学生" min-width="120">
          <template #default="{ row }">
            <div class="student-cell">
              <span class="student-name">{{ (row as NexusRiskItem).student_name }}</span>
              <span class="student-class">{{ (row as NexusRiskItem).class_name }}</span>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="并发" width="70" align="center">
          <template #default="{ row }">
            <span v-if="(row as NexusRiskItem).co_trigger" class="co-trigger-badge">
              <span class="pulse-dot"></span>
              并发
            </span>
            <span v-else class="text-muted">—</span>
          </template>
        </el-table-column>

        <el-table-column label="学业风险" width="140">
          <template #default="{ row }">
            <div class="risk-cell">
              <el-tag
                :type="academicRiskLevelTag((row as NexusRiskItem).academic_risk.level)"
                size="small"
                effect="dark"
              >
                {{ academicRiskLevelLabel((row as NexusRiskItem).academic_risk.level) }}
              </el-tag>
              <span
                v-if="(row as NexusRiskItem).academic_risk.z_score !== null"
                class="zscore-badge"
                :style="{ color: zScoreColor((row as NexusRiskItem).academic_risk.z_score) }"
              >
                {{ formatDeviation((row as NexusRiskItem).academic_risk.z_score) }}
              </span>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="心理风险" width="120">
          <template #default="{ row }">
            <el-tag
              :type="psyRiskLevelTag((row as NexusRiskItem).psy_risk.level)"
              size="small"
              effect="dark"
            >
              {{ psyRiskLevelLabel((row as NexusRiskItem).psy_risk.level) }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="RDI" width="90" align="center">
          <template #default="{ row }">
            <div class="rdi-cell">
              <span
                v-if="(row as NexusRiskItem).rdi_risk.score !== null"
                class="rdi-score"
                :style="{ color: rdiColor((row as NexusRiskItem).rdi_risk.score) }"
              >
                {{ (row as NexusRiskItem).rdi_risk.score!.toFixed(2) }}
              </span>
              <span v-else class="text-muted">—</span>
              <span
                v-if="(row as NexusRiskItem).rdi_risk.is_escalating"
                class="escalating-icon"
                title="风险上升趋势"
              >↑</span>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="触发学科" min-width="120">
          <template #default="{ row }">
            <div class="subjects-cell">
              <span
                v-for="subj in (row as NexusRiskItem).academic_risk.trigger_subjects.slice(0, 3)"
                :key="subj"
                class="subject-tag"
              >
                {{ subj }}
              </span>
              <span
                v-if="(row as NexusRiskItem).academic_risk.trigger_subjects.length > 3"
                class="text-muted"
              >
                +{{ (row as NexusRiskItem).academic_risk.trigger_subjects.length - 3 }}
              </span>
              <span v-if="(row as NexusRiskItem).academic_risk.trigger_subjects.length === 0" class="text-muted">—</span>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="行动优先级" width="100" align="center">
          <template #default="{ row }">
            <el-tag
              :type="priorityTag((row as NexusRiskItem).action_priority)"
              size="small"
              effect="dark"
              :style="{ borderWidth: '1px', fontWeight: 600 }"
            >
              {{ priorityLabel((row as NexusRiskItem).action_priority) }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="推荐行动" min-width="200">
          <template #default="{ row }">
            <div class="actions-cell">
              <span
                v-for="(act, i) in (row as NexusRiskItem).recommended_actions.slice(0, 2)"
                :key="i"
                class="action-item"
              >
                {{ act }}
              </span>
              <span
                v-if="(row as NexusRiskItem).recommended_actions.length > 2"
                class="text-muted"
              >
                +{{ (row as NexusRiskItem).recommended_actions.length - 2 }} 项
              </span>
            </div>
          </template>
        </el-table-column>
      </el-table>

      <!-- 空状态 -->
      <div v-if="!loading && (!nexus || nexus.items.length === 0)" class="empty-state">
        <el-empty description="暂无预警数据" :image-size="80" />
      </div>
    </div>

    <!-- ═══════════════════════════════════════════════════════ -->
    <!-- 抽屉: 单学生双轨透视画像                                    -->
    <!-- ═══════════════════════════════════════════════════════ -->
    <el-drawer
      v-model="drawerVisible"
      size="55%"
      :with-header="false"
      direction="rtl"
      class="nexus-drawer"
    >
      <div class="drawer-content" v-loading="detailLoading">
        <template v-if="studentDetail">
          <!-- 抽屉头部 -->
          <div class="drawer-header">
            <div class="drawer-title-row">
              <h2 class="drawer-title">{{ studentDetail.student_name }}</h2>
              <span class="drawer-class">{{ studentDetail.class_name }}</span>
              <el-tag
                v-if="studentDetail.co_trigger"
                type="danger"
                effect="dark"
                size="small"
                style="margin-left: 8px"
              >
                双轨并发
              </el-tag>
            </div>
            <div class="drawer-priority">
              <el-tag
                :type="priorityTag(studentDetail.action_priority)"
                effect="dark"
                size="large"
              >
                {{ priorityLabel(studentDetail.action_priority) }}
              </el-tag>
            </div>
          </div>

          <!-- 推荐行动 -->
          <div class="drawer-section" v-if="studentDetail.recommended_actions.length > 0">
            <div class="section-title">
              <span class="section-icon">!</span>
              推荐干预行动
            </div>
            <div class="action-list">
              <div
                v-for="(act, i) in studentDetail.recommended_actions"
                :key="i"
                class="action-row"
              >
                <span class="action-num">{{ i + 1 }}</span>
                <span class="action-text">{{ act }}</span>
              </div>
            </div>
          </div>

          <!-- 学业风险 -->
          <div class="drawer-section">
            <div class="section-title">
              <span class="section-dot" :style="{ background: academicRiskLevelColor(studentDetail.academic_risk.level) }"></span>
              学业风险画像
            </div>
            <div class="detail-grid">
              <div class="detail-item">
                <span class="detail-label">风险等级</span>
                <el-tag :type="academicRiskLevelTag(studentDetail.academic_risk.level)" effect="dark" size="small">
                  {{ academicRiskLevelLabel(studentDetail.academic_risk.level) }}
                </el-tag>
              </div>
              <div class="detail-item">
                <span class="detail-label">Z-Score</span>
                <span
                  class="detail-value"
                  :style="{ color: zScoreColor(studentDetail.academic_risk.z_score) }"
                >
                  {{ formatDeviation(studentDetail.academic_risk.z_score) }}
                </span>
              </div>
              <div class="detail-item" v-if="studentDetail.academic_risk.trigger_subjects.length > 0">
                <span class="detail-label">触发学科</span>
                <div class="tag-cluster">
                  <span
                    v-for="subj in studentDetail.academic_risk.trigger_subjects"
                    :key="subj"
                    class="subject-tag"
                  >
                    {{ subj }}
                  </span>
                </div>
              </div>
              <div class="detail-item" v-if="studentDetail.academic_risk.trigger_reason">
                <span class="detail-label">触发原因</span>
                <span class="detail-value">{{ studentDetail.academic_risk.trigger_reason }}</span>
              </div>
            </div>

            <!-- 学业历史 -->
            <div v-if="studentDetail.academic_history.length > 0" class="sub-section">
              <div class="sub-title">历次考试轨迹</div>
              <el-table :data="studentDetail.academic_history" size="small" style="width: 100%">
                <el-table-column prop="exam_name" label="考试" min-width="120" />
                <el-table-column label="Z-Score" width="90">
                  <template #default="{ row }">
                    <span :style="{ color: zScoreColor(row.z_score) }">
                      {{ formatDeviation(row.z_score) }}
                    </span>
                  </template>
                </el-table-column>
                <el-table-column label="班排" width="70">
                  <template #default="{ row }">
                    {{ row.rank_in_class ?? '—' }}
                  </template>
                </el-table-column>
                <el-table-column label="年级排" width="70">
                  <template #default="{ row }">
                    {{ row.rank_in_grade ?? '—' }}
                  </template>
                </el-table-column>
                <el-table-column label="风险" width="70">
                  <template #default="{ row }">
                    <el-tag :type="academicRiskLevelTag(row.risk_level)" size="small" effect="dark">
                      {{ academicRiskLevelLabel(row.risk_level) }}
                    </el-tag>
                  </template>
                </el-table-column>
              </el-table>
            </div>
          </div>

          <!-- 心理风险 -->
          <div class="drawer-section">
            <div class="section-title">
              <span class="section-dot" :style="{ background: psyRiskLevelColor(studentDetail.psy_risk.level) }"></span>
              心理防线透视
              <span class="desensitize-tag">脱敏视图</span>
            </div>
            <div class="detail-grid">
              <div class="detail-item">
                <span class="detail-label">风险等级</span>
                <el-tag :type="psyRiskLevelTag(studentDetail.psy_risk.level)" effect="dark" size="small">
                  {{ psyRiskLevelLabel(studentDetail.psy_risk.level) }}
                </el-tag>
              </div>
              <div class="detail-item" v-if="studentDetail.psy_risk.scale_name">
                <span class="detail-label">最近量表</span>
                <span class="detail-value">{{ studentDetail.psy_risk.scale_name }}</span>
              </div>
              <div class="detail-item" v-if="studentDetail.psy_risk.last_screening_date">
                <span class="detail-label">最近筛查</span>
                <span class="detail-value">{{ studentDetail.psy_risk.last_screening_date }}</span>
              </div>
              <div class="detail-item" v-if="studentDetail.psy_risk.factors.length > 0">
                <span class="detail-label">风险因子</span>
                <div class="tag-cluster">
                  <span
                    v-for="f in studentDetail.psy_risk.factors"
                    :key="f"
                    class="factor-tag"
                  >
                    {{ f }}
                  </span>
                </div>
              </div>
            </div>

            <!-- 心理档案 -->
            <div v-if="studentDetail.psy_profile" class="sub-section">
              <div class="sub-title">档案摘要</div>
              <div class="detail-grid">
                <div class="detail-item" v-if="studentDetail.psy_profile.personality_traits">
                  <span class="detail-label">人格特征</span>
                  <span class="detail-value">{{ studentDetail.psy_profile.personality_traits }}</span>
                </div>
                <div class="detail-item" v-if="studentDetail.psy_profile.family_background">
                  <span class="detail-label">家庭背景</span>
                  <span class="detail-value">{{ studentDetail.psy_profile.family_background }}</span>
                </div>
                <div class="detail-item" v-if="studentDetail.psy_profile.counseling_history_summary">
                  <span class="detail-label">咨询摘要</span>
                  <span class="detail-value">{{ studentDetail.psy_profile.counseling_history_summary }}</span>
                </div>
                <div class="detail-item" v-if="studentDetail.psy_profile.tags.length > 0">
                  <span class="detail-label">标签云</span>
                  <div class="tag-cluster">
                    <span
                      v-for="t in studentDetail.psy_profile.tags"
                      :key="t"
                      class="psy-tag"
                    >
                      {{ t }}
                    </span>
                  </div>
                </div>
              </div>
            </div>

            <!-- 筛查历史 -->
            <div v-if="studentDetail.psy_screening_history.length > 0" class="sub-section">
              <div class="sub-title">筛查历史</div>
              <el-table :data="studentDetail.psy_screening_history" size="small" style="width: 100%">
                <el-table-column prop="scale_name" label="量表" min-width="120" />
                <el-table-column prop="screening_date" label="日期" width="110" />
                <el-table-column label="风险" width="70">
                  <template #default="{ row }">
                    <el-tag :type="psyRiskLevelTag(row.risk_level)" size="small" effect="dark">
                      {{ psyRiskLevelLabel(row.risk_level) }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="核心发现" min-width="200">
                  <template #default="{ row }">
                    <span v-for="(f, i) in row.key_findings" :key="i" class="finding-text">
                      {{ f }}{{ i < row.key_findings.length - 1 ? '；' : '' }}
                    </span>
                  </template>
                </el-table-column>
              </el-table>
            </div>

            <!-- 咨询摘要 -->
            <div v-if="studentDetail.psy_counseling_summary" class="sub-section">
              <div class="sub-title">咨询趋势</div>
              <div class="detail-grid">
                <div class="detail-item">
                  <span class="detail-label">总次数</span>
                  <span class="detail-value">{{ studentDetail.psy_counseling_summary.total_sessions }} 次</span>
                </div>
                <div class="detail-item" v-if="studentDetail.psy_counseling_summary.last_session_date">
                  <span class="detail-label">最近咨询</span>
                  <span class="detail-value">{{ studentDetail.psy_counseling_summary.last_session_date }}</span>
                </div>
                <div class="detail-item">
                  <span class="detail-label">趋势</span>
                  <span
                    class="detail-value"
                    :style="{ color: riskTrendColor(studentDetail.psy_counseling_summary.risk_trend) }"
                  >
                    {{ riskTrendLabel(studentDetail.psy_counseling_summary.risk_trend) }}
                  </span>
                </div>
                <div class="detail-item" v-if="studentDetail.psy_counseling_summary.main_concerns.length > 0">
                  <span class="detail-label">主要关注</span>
                  <div class="tag-cluster">
                    <span
                      v-for="c in studentDetail.psy_counseling_summary.main_concerns"
                      :key="c"
                      class="concern-tag"
                    >
                      {{ c }}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- RDI 四维风险 -->
          <div class="drawer-section">
            <div class="section-title">
              <span class="section-dot" :style="{ background: rdiColor(studentDetail.rdi_risk.score) }"></span>
              RDI 四维偏离度
              <span
                v-if="studentDetail.rdi_risk.is_escalating"
                class="escalating-badge"
              >
                风险上升中
              </span>
            </div>
            <div class="rdi-grid">
              <div class="rdi-dim">
                <span class="rdi-dim-label">行为</span>
                <span
                  class="rdi-dim-value"
                  :style="{ color: deviationColor(studentDetail.rdi_risk.behavior_deviation) }"
                >
                  {{ formatDeviation(studentDetail.rdi_risk.behavior_deviation) }}
                </span>
              </div>
              <div class="rdi-dim">
                <span class="rdi-dim-label">考勤</span>
                <span
                  class="rdi-dim-value"
                  :style="{ color: deviationColor(studentDetail.rdi_risk.attendance_deviation) }"
                >
                  {{ formatDeviation(studentDetail.rdi_risk.attendance_deviation) }}
                </span>
              </div>
              <div class="rdi-dim">
                <span class="rdi-dim-label">学业</span>
                <span
                  class="rdi-dim-value"
                  :style="{ color: deviationColor(studentDetail.rdi_risk.score_deviation) }"
                >
                  {{ formatDeviation(studentDetail.rdi_risk.score_deviation) }}
                </span>
              </div>
              <div class="rdi-dim">
                <span class="rdi-dim-label">心理</span>
                <span
                  class="rdi-dim-value"
                  :style="{ color: deviationColor(studentDetail.rdi_risk.psych_deviation) }"
                >
                  {{ formatDeviation(studentDetail.rdi_risk.psych_deviation) }}
                </span>
              </div>
              <div class="rdi-dim rdi-total">
                <span class="rdi-dim-label">RDI</span>
                <span
                  class="rdi-dim-value"
                  :style="{ color: rdiColor(studentDetail.rdi_risk.score), fontSize: '20px', fontWeight: 700 }"
                >
                  {{ studentDetail.rdi_risk.score !== null ? studentDetail.rdi_risk.score.toFixed(2) : '—' }}
                </span>
              </div>
            </div>
          </div>
        </template>

        <!-- 空状态 -->
        <div v-else-if="!detailLoading" class="empty-state">
          <el-empty description="无法加载学生详情" :image-size="80" />
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, nextTick, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import * as echarts from 'echarts/core'
import '@/utils/echarts'
import {
  getDashboardStats,
  getComprehensiveRisks,
  getStudentNexusDetail,
  priorityLabel,
  priorityTag,
  academicRiskLevelLabel,
  academicRiskLevelTag,
  academicRiskLevelColor,
  psyRiskLevelLabel,
  psyRiskLevelTag,
  psyRiskLevelColor,
  riskTrendLabel,
  riskTrendColor,
  formatDeviation,
  type DashboardResponse,
  type NexusListResponse,
  type NexusStudentDetail,
  type NexusRiskItem,
  type ActionPriority,
} from '@/api/psychProfiles'
import { getClasses } from '@/api/classes'

// ═══════════════════════════════════════════════════
// 状态
// ═══════════════════════════════════════════════════
const loading = ref(false)
const detailLoading = ref(false)
const dashboard = ref<DashboardResponse | null>(null)
const nexus = ref<NexusListResponse | null>(null)
const studentDetail = ref<NexusStudentDetail | null>(null)
const drawerVisible = ref(false)

// 筛选
const coTriggerOnly = ref(false)
const minPriority = ref<ActionPriority | ''>('')
const selectedClassId = ref<number | undefined>(undefined)

// 班级列表
const classList = ref<{ id: number; name: string }[]>([])

// ECharts
const academicRingRef = ref<HTMLDivElement | null>(null)
const psyRingRef = ref<HTMLDivElement | null>(null)
let academicChart: echarts.ECharts | null = null
let psyChart: echarts.ECharts | null = null

// ═══════════════════════════════════════════════════
// 计算属性
// ═══════════════════════════════════════════════════

/** 学业红灯人数 (从dashboard统计获取，非items计算) */
const academicRedCount = computed(() => {
  return dashboard.value?.academic_red_count ?? 0
})

/** 心理高危人数 (RED + ORANGE) */
const psyHighRiskCount = computed(() => {
  if (!dashboard.value?.risk_distribution) return 0
  const dist = dashboard.value.risk_distribution
  return (dist.RED ?? 0) + (dist.ORANGE ?? 0)
})

// ═══════════════════════════════════════════════════
// 辅助函数
// ═══════════════════════════════════════════════════

function zScoreColor(z: number | null): string {
  if (z === null || z === undefined) return '#8b949e'
  if (z <= -1.5) return '#f85149'
  if (z <= -1.0) return '#d29922'
  return '#3fb950'
}

function rdiColor(score: number | null): string {
  if (score === null || score === undefined) return '#8b949e'
  if (score >= 2.5) return '#f85149'
  if (score >= 1.5) return '#d29922'
  return '#3fb950'
}

function deviationColor(d: number | null): string {
  if (d === null || d === undefined) return '#8b949e'
  if (d >= 2.0) return '#f85149'
  if (d >= 1.0) return '#d29922'
  return '#3fb950'
}

function rowClassName({ row }: { row: any }): string {
  if (row.co_trigger) return 'row-co-trigger'
  if (row.action_priority === 'CRITICAL') return 'row-critical'
  if (row.action_priority === 'URGENT') return 'row-urgent'
  return ''
}

// ═══════════════════════════════════════════════════
// 数据加载
// ═══════════════════════════════════════════════════

async function loadDashboard() {
  try {
    dashboard.value = await getDashboardStats()
  } catch (e: any) {
    console.error('[NexusBoard] dashboard load failed:', e)
  }
}

async function loadNexus() {
  loading.value = true
  try {
    const params: Record<string, any> = {
      page: 1,
      page_size: 200,
    }
    if (coTriggerOnly.value) params.co_trigger_only = true
    if (minPriority.value) params.min_priority = minPriority.value
    if (selectedClassId.value) params.class_id = selectedClassId.value

    nexus.value = await getComprehensiveRisks(params)
  } catch (e: any) {
    ElMessage.error('预警数据加载失败: ' + (e.message ?? '未知错误'))
    console.error('[NexusBoard] nexus load failed:', e)
  } finally {
    loading.value = false
  }
}

async function loadClassList() {
  try {
    const res = await getClasses({ page: 1, page_size: 100 })
    const data = res as any
    classList.value = (data.items ?? data ?? []).map((c: any) => ({
      id: c.id,
      name: c.name,
    }))
  } catch (e) {
    console.error('[NexusBoard] class list load failed:', e)
  }
}

async function loadData() {
  await Promise.all([loadDashboard(), loadNexus()])
  await nextTick()
  renderRings()
}

// ═══════════════════════════════════════════════════
// 筛选交互
// ═══════════════════════════════════════════════════

function filterByPriority(p: ActionPriority) {
  minPriority.value = p
  loadNexus()
}

watch([coTriggerOnly, minPriority, selectedClassId], () => {
  loadNexus()
})

// ═══════════════════════════════════════════════════
// 抽屉详情
// ═══════════════════════════════════════════════════

async function openDetail(row: any) {
  const item = row as NexusRiskItem
  drawerVisible.value = true
  detailLoading.value = true
  studentDetail.value = null
  try {
    studentDetail.value = await getStudentNexusDetail(item.student_id)
  } catch (e: any) {
    ElMessage.error('学生详情加载失败: ' + (e.message ?? '未知错误'))
    console.error('[NexusBoard] detail load failed:', e)
  } finally {
    detailLoading.value = false
  }
}

// ═══════════════════════════════════════════════════
// ECharts 环形图
// ═══════════════════════════════════════════════════

function renderRings() {
  // 学业红灯环
  if (academicRingRef.value) {
    if (academicChart) academicChart.dispose()
    academicChart = echarts.init(academicRingRef.value)

    const total = dashboard.value?.total_academic_alerts ?? nexus.value?.total ?? 0
    const red = dashboard.value?.academic_red_count ?? academicRedCount.value
    const redPct = total > 0 ? ((red / total) * 100).toFixed(1) : '0'

    academicChart.setOption({
      series: [
        {
          type: 'pie',
          radius: ['68%', '85%'],
          center: ['50%', '50%'],
          silent: true,
          label: {
            show: true,
            position: 'center',
            formatter: `{a|${red}}\n{b|学业红灯}\n{c|${redPct}%}`,
            rich: {
              a: { fontSize: 32, fontWeight: 700, color: '#f85149', lineHeight: 38 },
              b: { fontSize: 12, color: '#8b949e', lineHeight: 18 },
              c: { fontSize: 14, color: '#f85149', fontWeight: 600, lineHeight: 20 },
            },
          },
          data: [
            {
              value: red,
              itemStyle: { color: '#f85149', shadowBlur: 12, shadowColor: 'rgba(248,81,73,0.4)' },
            },
            {
              value: Math.max(total - red, 0),
              itemStyle: { color: '#21262d' },
            },
          ],
        },
      ],
    })
  }

  // 心理高危环
  if (psyRingRef.value) {
    if (psyChart) psyChart.dispose()
    psyChart = echarts.init(psyRingRef.value)

    const totalProfiles = dashboard.value?.total_profiles ?? 0
    const highRisk = psyHighRiskCount.value
    const highPct = totalProfiles > 0 ? ((highRisk / totalProfiles) * 100).toFixed(1) : '0'

    psyChart.setOption({
      series: [
        {
          type: 'pie',
          radius: ['68%', '85%'],
          center: ['50%', '50%'],
          silent: true,
          label: {
            show: true,
            position: 'center',
            formatter: `{a|${highRisk}}\n{b|心理高危}\n{c|${highPct}%}`,
            rich: {
              a: { fontSize: 32, fontWeight: 700, color: '#d29922', lineHeight: 38 },
              b: { fontSize: 12, color: '#8b949e', lineHeight: 18 },
              c: { fontSize: 14, color: '#d29922', fontWeight: 600, lineHeight: 20 },
            },
          },
          data: [
            {
              value: highRisk,
              itemStyle: { color: '#d29922', shadowBlur: 12, shadowColor: 'rgba(210,153,34,0.4)' },
            },
            {
              value: Math.max(totalProfiles - highRisk, 0),
              itemStyle: { color: '#21262d' },
            },
          ],
        },
      ],
    })
  }
}

// 窗口resize
function handleResize() {
  academicChart?.resize()
  psyChart?.resize()
}

// ═══════════════════════════════════════════════════
// 生命周期
// ═══════════════════════════════════════════════════

onMounted(async () => {
  await loadClassList()
  await loadData()
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  academicChart?.dispose()
  psyChart?.dispose()
})
</script>

<style scoped>
.nexus-board-container {
  padding: 16px;
  background: #0d1117;
  min-height: 100vh;
}

/* ═══ 统计卡片 ═══ */
.stats-row {
  margin-bottom: 12px;
}

.stat-card {
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 8px;
  padding: 16px 20px;
  cursor: pointer;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.stat-card:hover {
  border-color: #58a6ff;
  box-shadow: 0 0 0 1px rgba(88, 166, 255, 0.2);
}

.stat-critical-glow {
  border-color: #f85149;
  box-shadow: 0 0 12px rgba(248, 81, 73, 0.15);
}

.stat-critical-glow:hover {
  border-color: #f85149;
  box-shadow: 0 0 16px rgba(248, 81, 73, 0.3);
}

.stat-academic-red {
  border-color: rgba(248, 81, 73, 0.4);
  box-shadow: 0 0 8px rgba(248, 81, 73, 0.08);
}

.stat-academic-red:hover {
  border-color: #f85149;
  box-shadow: 0 0 12px rgba(248, 81, 73, 0.2);
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
  line-height: 1.2;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
}

.stat-label {
  font-size: 13px;
  color: #8b949e;
  margin-top: 4px;
}

.stat-sub {
  font-size: 11px;
  color: #6e7681;
  margin-top: 2px;
}

/* ═══ 环形图 ═══ */
.rings-row {
  margin-bottom: 12px;
}

.ring-card {
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 8px;
  padding: 12px 16px;
}

.ring-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.ring-title {
  font-size: 13px;
  color: #c9d1d9;
  display: flex;
  align-items: center;
  gap: 6px;
}

.ring-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
}

.ring-meta {
  font-size: 11px;
  color: #6e7681;
}

.ring-chart {
  height: 160px;
}

/* ═══ 矩阵表 ═══ */
.matrix-card {
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 8px;
  overflow: hidden;
}

.filter-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid #30363d;
  background: #161b22;
}

.filter-left {
  display: flex;
  gap: 12px;
  align-items: center;
}

.filter-right {
  display: flex;
  gap: 8px;
}

/* 表格行样式 */
:deep(.el-table) {
  background: transparent !important;
  color: #c9d1d9;
}

:deep(.el-table tr) {
  background: transparent !important;
}

:deep(.el-table tr:hover > td) {
  background: rgba(88, 166, 255, 0.06) !important;
}

:deep(.el-table--enable-row-transition .el-table__body td) {
  transition: background-color 0.2s;
}

:deep(.row-co-trigger) {
  background: rgba(248, 81, 73, 0.06) !important;
}

:deep(.row-co-trigger:hover > td) {
  background: rgba(248, 81, 73, 0.12) !important;
}

:deep(.row-critical) {
  background: rgba(248, 81, 73, 0.04) !important;
}

:deep(.row-urgent) {
  background: rgba(210, 153, 34, 0.04) !important;
}

/* 学生单元格 */
.student-cell {
  display: flex;
  flex-direction: column;
}

.student-name {
  color: #c9d1d9;
  font-weight: 600;
  font-size: 13px;
}

.student-class {
  color: #6e7681;
  font-size: 11px;
}

/* 并发徽章 */
.co-trigger-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: #f85149;
  font-size: 12px;
  font-weight: 600;
}

.pulse-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #f85149;
  animation: pulse-breath 1.5s ease-in-out infinite;
  box-shadow: 0 0 6px #f85149;
}

@keyframes pulse-breath {
  0%, 100% {
    opacity: 1;
    transform: scale(1);
  }
  50% {
    opacity: 0.4;
    transform: scale(1.3);
  }
}

/* Z-Score 徽章 */
.zscore-badge {
  font-size: 12px;
  font-family: 'JetBrains Mono', monospace;
  font-weight: 600;
  margin-left: 4px;
}

.risk-cell {
  display: flex;
  align-items: center;
  gap: 2px;
}

/* RDI */
.rdi-cell {
  display: flex;
  align-items: center;
  gap: 4px;
  justify-content: center;
}

.rdi-score {
  font-family: 'JetBrains Mono', monospace;
  font-weight: 700;
  font-size: 14px;
}

.escalating-icon {
  color: #f85149;
  font-size: 14px;
  font-weight: 700;
}

/* 学科标签 */
.subjects-cell {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
}

.subject-tag {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 4px;
  background: rgba(248, 81, 73, 0.12);
  color: #f85149;
  border: 1px solid rgba(248, 81, 73, 0.2);
}

/* 行动列表 */
.actions-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.action-item {
  font-size: 11px;
  color: #8b949e;
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.text-muted {
  color: #6e7681;
  font-size: 11px;
}

/* 空状态 */
.empty-state {
  padding: 40px 0;
}

/* ═══ 抽屉 ═══ */
:deep(.nexus-drawer) {
  background: #0d1117 !important;
}

:deep(.nexus-drawer .el-drawer__body) {
  background: #0d1117;
  padding: 0;
}

.drawer-content {
  padding: 20px 24px;
  height: 100%;
  overflow-y: auto;
}

.drawer-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding-bottom: 16px;
  border-bottom: 1px solid #30363d;
  margin-bottom: 20px;
}

.drawer-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.drawer-title {
  font-size: 20px;
  font-weight: 700;
  color: #f0f6fc;
  margin: 0;
}

.drawer-class {
  font-size: 13px;
  color: #8b949e;
  background: #21262d;
  padding: 2px 8px;
  border-radius: 4px;
}

.drawer-section {
  margin-bottom: 24px;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 600;
  color: #c9d1d9;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid #21262d;
}

.section-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
}

.section-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #f85149;
  color: #fff;
  font-size: 11px;
  font-weight: 700;
}

.desensitize-tag {
  font-size: 10px;
  color: #6e7681;
  background: #21262d;
  padding: 1px 6px;
  border-radius: 3px;
  margin-left: auto;
}

/* 详情网格 */
.detail-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px 20px;
  margin-bottom: 12px;
}

.detail-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.detail-label {
  font-size: 11px;
  color: #6e7681;
}

.detail-value {
  font-size: 13px;
  color: #c9d1d9;
}

/* 标签集群 */
.tag-cluster {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.factor-tag {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 4px;
  background: rgba(210, 153, 34, 0.12);
  color: #d29922;
  border: 1px solid rgba(210, 153, 34, 0.2);
}

.psy-tag {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 4px;
  background: rgba(88, 166, 255, 0.1);
  color: #58a6ff;
  border: 1px solid rgba(88, 166, 255, 0.2);
}

.concern-tag {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 4px;
  background: rgba(139, 148, 158, 0.12);
  color: #8b949e;
  border: 1px solid rgba(139, 148, 158, 0.2);
}

/* 子区块 */
.sub-section {
  margin-top: 16px;
  padding: 12px;
  background: #0d1117;
  border: 1px solid #21262d;
  border-radius: 6px;
}

.sub-title {
  font-size: 12px;
  color: #8b949e;
  margin-bottom: 8px;
  font-weight: 600;
}

.finding-text {
  font-size: 12px;
  color: #c9d1d9;
}

/* 行动列表 */
.action-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.action-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 12px;
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 6px;
}

.action-num {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  min-width: 20px;
  border-radius: 50%;
  background: #f85149;
  color: #fff;
  font-size: 11px;
  font-weight: 700;
}

.action-text {
  font-size: 13px;
  color: #c9d1d9;
  line-height: 1.5;
}

/* RDI 四维 */
.rdi-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 8px;
}

.rdi-dim {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 12px 8px;
  background: #0d1117;
  border: 1px solid #21262d;
  border-radius: 6px;
}

.rdi-total {
  border-color: #30363d;
  background: #161b22;
}

.rdi-dim-label {
  font-size: 11px;
  color: #6e7681;
}

.rdi-dim-value {
  font-size: 16px;
  font-weight: 700;
  font-family: 'JetBrains Mono', monospace;
}

.escalating-badge {
  font-size: 10px;
  color: #f85149;
  background: rgba(248, 81, 73, 0.12);
  padding: 1px 6px;
  border-radius: 3px;
  margin-left: auto;
  border: 1px solid rgba(248, 81, 73, 0.2);
}

/* 暗色 el-table 全局覆盖 */
:deep(.el-table),
:deep(.el-table__expanded-cell) {
  background-color: transparent !important;
}

:deep(.el-table th.el-table__cell) {
  background-color: #161b22 !important;
}

:deep(.el-table__body tr > td.el-table__cell) {
  background-color: transparent !important;
}

:deep(.el-table__inner-wrapper::before) {
  background-color: #30363d !important;
}

:deep(.el-table__border-left-patch) {
  background-color: #30363d !important;
}

:deep(.el-table--border .el-table__cell) {
  border-right: 1px solid #30363d !important;
}

/* el-select / el-switch 暗色 */
:deep(.el-select .el-input__wrapper) {
  background: #0d1117;
  box-shadow: 0 0 0 1px #30363d inset;
}

:deep(.el-select .el-input__inner) {
  color: #c9d1d9;
}

:deep(.el-button) {
  background: #21262d;
  border-color: #30363d;
  color: #c9d1d9;
}

:deep(.el-button:hover) {
  background: #30363d;
  border-color: #58a6ff;
  color: #58a6ff;
}

/* 抽屉内表格暗色 */
:deep(.el-table__body-wrapper) {
  background: transparent !important;
}
</style>
