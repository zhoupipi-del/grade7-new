<template>
  <div class="growth-console">
    <!-- ═══════════════════════════════════════════════ -->
    <!-- Page Header                                     -->
    <!-- ═══════════════════════════════════════════════ -->
    <div class="page-header">
      <h2 class="page-title">
        <el-icon><TrendCharts /></el-icon>
        成长档案
      </h2>
      <div class="header-actions" v-if="!isParent">
        <el-button size="small" @click="refreshAll" :loading="anyLoading">
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>
      </div>
    </div>

    <!-- ═══════════════════════════════════════════════ -->
    <!-- Tabs                                            -->
    <!-- ═══════════════════════════════════════════════ -->
    <el-tabs v-model="activeTab" class="main-tabs" @tab-change="onTabChange">

      <!-- ── Tab 1: 成长看板 ── -->
      <el-tab-pane v-if="!isParent" label="成长看板" name="dashboard">
        <!-- KPI Row -->
        <el-row :gutter="16" class="kpi-row">
          <el-col :span="4">
            <el-card shadow="hover" class="kpi-card">
              <div class="kpi-value" style="color: #409eff">{{ dash.total_students }}</div>
              <div class="kpi-label">在校学生</div>
            </el-card>
          </el-col>
          <el-col :span="4">
            <el-card shadow="hover" class="kpi-card">
              <div class="kpi-value" style="color: #8b5cf6">{{ dash.total_events }}</div>
              <div class="kpi-label">成长事件</div>
            </el-card>
          </el-col>
          <el-col :span="4">
            <el-card shadow="hover" class="kpi-card">
              <div class="kpi-value" style="color: #67c23a">{{ dash.total_snapshots }}</div>
              <div class="kpi-label">周期快照</div>
            </el-card>
          </el-col>
          <el-col :span="4">
            <el-card shadow="hover" class="kpi-card">
              <div class="kpi-value" style="color: #f56c6c">{{ dash.critical_count }}</div>
              <div class="kpi-label">危机事件</div>
            </el-card>
          </el-col>
          <el-col :span="4">
            <el-card shadow="hover" class="kpi-card">
              <div class="kpi-value" style="color: #e6a23c">{{ dash.warning_count }}</div>
              <div class="kpi-label">预警事件</div>
            </el-card>
          </el-col>
          <el-col :span="4">
            <el-card shadow="hover" class="kpi-card">
              <div class="kpi-value" style="color: #67c23a">{{ dash.bonus_count }}</div>
              <div class="kpi-label">荣誉表彰</div>
            </el-card>
          </el-col>
        </el-row>

        <!-- Dimension Distribution + Recent Critical -->
        <el-row :gutter="16" style="margin-top: 16px">
          <el-col :span="10">
            <el-card shadow="hover">
              <template #header>
                <span style="font-weight: 600">维度分布</span>
              </template>
              <div class="dim-distribution">
                <div
                  v-for="dim in DIMENSION_OPTIONS"
                  :key="dim.value"
                  class="dim-bar-row"
                >
                  <span class="dim-bar-label">
                    <span class="dim-dot" :style="{ background: dim.color }"></span>
                    {{ dim.label }}
                  </span>
                  <div class="dim-bar-track">
                    <div
                      class="dim-bar-fill"
                      :style="{
                        width: dimBarWidth(dash.dimension_distribution[dim.value] || 0),
                        background: dim.color,
                      }"
                    ></div>
                  </div>
                  <span class="dim-bar-count">{{ dash.dimension_distribution[dim.value] || 0 }}</span>
                </div>
              </div>
            </el-card>
          </el-col>

          <el-col :span="14">
            <el-card shadow="hover">
              <template #header>
                <span style="font-weight: 600">近期危机事件</span>
              </template>
              <el-table
                :data="dash.recent_critical"
                stripe
                size="small"
                :max-height="280"
                @row-click="(row: any) => goToProfile(row.student_id)"
                style="cursor: pointer"
              >
                <el-table-column prop="student_name" label="学生" width="90" />
                <el-table-column prop="class_name" label="班级" width="90" />
                <el-table-column prop="dimension" label="维度" width="70">
                  <template #default="{ row }">
                    <el-tag size="small" :type="dimensionTagType(row.dimension) as any">
                      {{ dimensionLabel(row.dimension) }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column prop="title" label="事件" show-overflow-tooltip />
                <el-table-column prop="occurred_at" label="时间" width="140">
                  <template #default="{ row }">
                    {{ formatDateTime(row.occurred_at) }}
                  </template>
                </el-table-column>
              </el-table>
              <el-empty v-if="dash.recent_critical.length === 0" description="暂无危机事件" :image-size="60" />
            </el-card>
          </el-col>
        </el-row>
      </el-tab-pane>

      <!-- ── Tab 2: 时光轴 ── -->
      <el-tab-pane label="时光轴" name="timeline">
        <!-- Timeline sub-header -->
        <div class="tab-toolbar">
          <div class="toolbar-left">
            <span class="selector-label" v-if="!isParent">学生ID：</span>
            <el-input
              v-if="!isParent"
              v-model="studentIdInput"
              placeholder="输入学生ID"
              size="small"
              style="width: 120px"
              @keyup.enter="fetchTimeline"
            />
            <el-button v-if="!isParent" size="small" type="primary" @click="fetchTimeline" :loading="loading.timeline">
              查询
            </el-button>
            <el-select
              v-model="timelineSemester"
              placeholder="全部学期"
              size="small"
              clearable
              style="width: 160px"
              @change="fetchTimeline"
            >
              <el-option label="2025-2026-2 (当前)" value="2025-2026-2" />
              <el-option label="2025-2026-1" value="2025-2026-1" />
            </el-select>
          </div>
          <div class="toolbar-right" v-if="!isParent">
            <el-button size="small" type="success" @click="showEventDialog = true">
              <el-icon><Plus /></el-icon>
              记录事件
            </el-button>
          </div>
        </div>

        <!-- Student info card -->
        <div v-if="timelineData" class="student-card">
          <div class="student-avatar">
            <span class="avatar-text">{{ timelineData.student_name?.charAt(0) || '?' }}</span>
          </div>
          <div class="student-info">
            <h3>{{ timelineData.student_name }}</h3>
            <p>{{ timelineData.class_name }} · 共 {{ timelineData.total_events }} 个成长记录</p>
          </div>
        </div>

        <!-- Event type filter -->
        <div v-if="timelineData" class="event-filters">
          <el-radio-group v-model="timelineFilter" size="small">
            <el-radio-button value="all">全部 ({{ timelineData.total_events }})</el-radio-button>
            <el-radio-button
              v-for="opt in EVENT_TYPE_OPTIONS"
              :key="opt.value"
              :value="opt.value"
            >
              <span class="filter-dot" :style="{ background: opt.color }"></span>
              {{ opt.label }}
            </el-radio-button>
          </el-radio-group>
        </div>

        <!-- Loading -->
        <div v-if="loading.timeline" class="loading-state">
          <el-icon class="is-loading" :size="32"><Loading /></el-icon>
          <p>正在加载成长时间轴...</p>
        </div>

        <!-- Empty prompt -->
        <div v-else-if="!timelineData" class="empty-prompt">
          <el-icon class="prompt-icon"><UserFilled /></el-icon>
          <p v-if="isParent">正在加载孩子的成长记录...</p>
          <p v-else>输入学生 ID 查看成长时间轴</p>
        </div>

        <!-- Timeline -->
        <div v-else-if="filteredTimeline.length > 0" class="timeline-container">
          <div class="timeline-track">
            <div
              v-for="group in groupedTimeline"
              :key="group.date"
              class="timeline-group"
            >
              <div class="date-divider">
                <span class="date-badge">{{ formatDateLabel(group.date) }}</span>
              </div>
              <div
                v-for="item in group.events"
                :key="item.event_id"
                class="timeline-event"
                :class="`severity-${item.severity}`"
              >
                <div class="timeline-node" :style="{ background: eventTypeColor(item.event_type) }">
                  <el-icon :size="14">
                    <component :is="eventTypeIcon(item.event_type)" />
                  </el-icon>
                </div>
                <div class="event-card">
                  <div class="event-header">
                    <el-tag :type="severityTagType(item.severity)" size="small" effect="dark">
                      {{ eventTypeLabel(item.event_type) }}
                    </el-tag>
                    <span class="event-time">{{ formatTime(item.occurred_at) }}</span>
                  </div>
                  <h4 class="event-title">{{ item.title }}</h4>
                  <p v-if="item.description" class="event-desc">{{ item.description }}</p>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Empty timeline -->
        <div v-else-if="timelineData && !loading.timeline" class="empty-timeline">
          <el-empty description="该学生暂无成长记录" :image-size="120" />
        </div>
      </el-tab-pane>

      <!-- ── Tab 3: 全息画像 ── -->
      <el-tab-pane v-if="!isParent" label="全息画像" name="profile">
        <!-- Profile search -->
        <div class="tab-toolbar">
          <div class="toolbar-left">
            <span class="selector-label">学生ID：</span>
            <el-input
              v-model="profileStudentId"
              placeholder="输入学生ID"
              size="small"
              style="width: 120px"
              @keyup.enter="fetchProfile"
            />
            <el-button size="small" type="primary" @click="fetchProfile" :loading="loading.profile">
              查询画像
            </el-button>
          </div>
          <div class="toolbar-right">
            <el-button
              size="small"
              type="warning"
              @click="generateSnapshotFromProfile"
              :loading="loading.generate"
              :disabled="!profileData"
            >
              <el-icon><MagicStick /></el-icon>
              生成快照
            </el-button>
          </div>
        </div>

        <!-- Loading -->
        <div v-if="loading.profile" class="loading-state">
          <el-icon class="is-loading" :size="32"><Loading /></el-icon>
          <p>正在加载全息画像...</p>
        </div>

        <!-- Profile content -->
        <div v-else-if="profileData" class="profile-content">
          <!-- Student header -->
          <div class="profile-student-header">
            <div class="student-avatar large">
              <span class="avatar-text">{{ profileData.student.name?.charAt(0) || '?' }}</span>
            </div>
            <div>
              <h3 class="profile-name">{{ profileData.student.name }}</h3>
              <p class="profile-meta">
                {{ profileData.student.class_name || '未分班' }}
                <span v-if="profileData.student.grade_name"> · {{ profileData.student.grade_name }}</span>
              </p>
            </div>
          </div>

          <el-row :gutter="16" style="margin-top: 16px">
            <!-- Radar Chart -->
            <el-col :span="12">
              <el-card shadow="hover">
                <template #header>
                  <span style="font-weight: 600">五维雷达图</span>
                  <span v-if="profileData.current_snapshot" class="snapshot-period">
                    {{ snapshotTypeLabel(profileData.current_snapshot.snapshot_type) }} · {{ profileData.current_snapshot.period_label }}
                  </span>
                </template>
                <div ref="radarChartRef" class="radar-chart-container"></div>
                <el-empty v-if="!profileData.current_snapshot" description="暂无快照数据，请先生成周期快照" :image-size="60" />
              </el-card>
            </el-col>

            <!-- Snapshot Scores -->
            <el-col :span="12">
              <el-card shadow="hover">
                <template #header>
                  <span style="font-weight: 600">维度评分</span>
                </template>
                <div v-if="profileData.current_snapshot" class="score-list">
                  <div v-for="dim in scoreDimensions" :key="dim.key" class="score-row">
                    <span class="score-label">
                      <span class="dim-dot" :style="{ background: dim.color }"></span>
                      {{ dim.label }}
                    </span>
                    <div class="score-bar-track">
                      <div
                        class="score-bar-fill"
                        :style="{
                          width: scoreBarWidth(dim.value),
                          background: dim.color,
                        }"
                      ></div>
                    </div>
                    <span class="score-value">{{ dim.value.toFixed(1) }}</span>
                    <el-tag size="small" :type="scoreLevelTag(dim.value) as any" style="margin-left: 8px">
                      {{ scoreLevelLabel(dim.value) }}
                    </el-tag>
                  </div>

                  <!-- Summary Metrics -->
                  <el-divider content-position="left">统计概要</el-divider>
                  <div class="metrics-grid">
                    <div class="metric-item">
                      <span class="metric-label">缺勤</span>
                      <span class="metric-value">{{ profileData.current_snapshot.summary_metrics?.absence_count ?? 0 }} 次</span>
                    </div>
                    <div class="metric-item">
                      <span class="metric-label">断层</span>
                      <span class="metric-value">{{ profileData.current_snapshot.summary_metrics?.gap_count ?? 0 }} 个</span>
                    </div>
                    <div class="metric-item">
                      <span class="metric-label">违纪</span>
                      <span class="metric-value">{{ profileData.current_snapshot.summary_metrics?.violation_count ?? 0 }} 次</span>
                    </div>
                    <div class="metric-item">
                      <span class="metric-label">荣誉</span>
                      <span class="metric-value">{{ profileData.current_snapshot.summary_metrics?.honor_count ?? 0 }} 次</span>
                    </div>
                  </div>
                </div>
                <el-empty v-else description="暂无快照数据" :image-size="60" />
              </el-card>
            </el-col>
          </el-row>

          <!-- Teacher Comment -->
          <el-card shadow="hover" style="margin-top: 16px" v-if="profileData.current_snapshot">
            <template #header>
              <div style="display: flex; justify-content: space-between; align-items: center">
                <span style="font-weight: 600">班主任评语</span>
                <el-button
                  size="small"
                  type="primary"
                  @click="saveTeacherComment"
                  :loading="loading.comment"
                  v-if="canEditComment"
                >
                  保存评语
                </el-button>
              </div>
            </template>
            <el-input
              v-model="teacherCommentText"
              type="textarea"
              :rows="4"
              placeholder="输入班主任评语（5-2000字）..."
              :disabled="!canEditComment"
              maxlength="2000"
              show-word-limit
            />
          </el-card>

          <!-- AI Growth Prescription -->
          <el-card shadow="hover" style="margin-top: 16px" v-if="profileData.current_snapshot?.ai_growth_prescription">
            <template #header>
              <span style="font-weight: 600">
                <el-icon><MagicStick /></el-icon>
                AI 成长处方
              </span>
            </template>
            <div class="ai-prescription" v-html="formatAiPrescription(profileData.current_snapshot.ai_growth_prescription)"></div>
          </el-card>

          <!-- Recent Events -->
          <el-card shadow="hover" style="margin-top: 16px">
            <template #header>
              <span style="font-weight: 600">近期成长事件</span>
            </template>
            <el-table :data="profileData.recent_events" stripe size="small" :max-height="300">
              <el-table-column prop="dimension" label="维度" width="70">
                <template #default="{ row }">
                  <el-tag size="small" :type="dimensionTagType(row.dimension) as any">
                    {{ dimensionLabel(row.dimension) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="severity" label="级别" width="70">
                <template #default="{ row }">
                  <el-tag size="small" :type="severityTagType(row.severity)" effect="plain">
                    {{ severityLabel(row.severity) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="title" label="事件" show-overflow-tooltip />
              <el-table-column prop="occurred_at" label="时间" width="140">
                <template #default="{ row }">
                  {{ formatDateTime(row.occurred_at) }}
                </template>
              </el-table-column>
              <el-table-column prop="reporter_name" label="记录人" width="90" />
            </el-table>
            <el-empty v-if="profileData.recent_events.length === 0" description="暂无事件" :image-size="60" />
          </el-card>
        </div>

        <!-- Empty prompt -->
        <div v-else class="empty-prompt">
          <el-icon class="prompt-icon"><UserFilled /></el-icon>
          <p>输入学生 ID 查看全息成长画像</p>
        </div>
      </el-tab-pane>

      <!-- ── Tab 4: 快照管理 ── -->
      <el-tab-pane v-if="!isParent" label="快照管理" name="snapshots">
        <!-- Snapshot toolbar -->
        <div class="tab-toolbar">
          <div class="toolbar-left">
            <span class="selector-label">学生ID：</span>
            <el-input
              v-model="snapshotStudentId"
              placeholder="输入学生ID"
              size="small"
              style="width: 120px"
              @keyup.enter="fetchSnapshots"
            />
            <el-button size="small" @click="fetchSnapshots" :loading="loading.snapshots">查询</el-button>
          </div>
          <div class="toolbar-right">
            <el-select v-model="snapshotTypeSelect" size="small" style="width: 120px">
              <el-option label="月度快照" value="monthly" />
              <el-option label="学期快照" value="semester" />
            </el-select>
            <el-input
              v-model="snapshotPeriodLabel"
              placeholder="如 2026-07"
              size="small"
              style="width: 140px"
            />
            <el-button
              size="small"
              type="warning"
              @click="generateSnapshot"
              :loading="loading.generate"
              :disabled="!snapshotStudentId || !snapshotPeriodLabel"
            >
              <el-icon><MagicStick /></el-icon>
              生成快照
            </el-button>
          </div>
        </div>

        <!-- Snapshots table -->
        <el-table :data="snapshotList" stripe v-loading="loading.snapshots" style="margin-top: 12px">
          <el-table-column prop="period_label" label="周期" width="120" />
          <el-table-column prop="snapshot_type" label="类型" width="90">
            <template #default="{ row }">
              <el-tag size="small">{{ snapshotTypeLabel(row.snapshot_type) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="学术" width="70" align="center">
            <template #default="{ row }">
              <span :style="{ color: scoreColor(row.academic_score) }">{{ row.academic_score.toFixed(1) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="考勤" width="70" align="center">
            <template #default="{ row }">
              <span :style="{ color: scoreColor(row.attendance_score) }">{{ row.attendance_score.toFixed(1) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="行为" width="70" align="center">
            <template #default="{ row }">
              <span :style="{ color: scoreColor(row.behavior_score) }">{{ row.behavior_score.toFixed(1) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="心理" width="70" align="center">
            <template #default="{ row }">
              <span :style="{ color: scoreColor(row.psych_score) }">{{ row.psych_score.toFixed(1) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="活动" width="70" align="center">
            <template #default="{ row }">
              <span :style="{ color: scoreColor(row.activity_score) }">{{ row.activity_score.toFixed(1) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="teacher_comment" label="评语" show-overflow-tooltip>
            <template #default="{ row }">
              {{ row.teacher_comment || '-' }}
            </template>
          </el-table-column>
          <el-table-column prop="created_at" label="生成时间" width="140">
            <template #default="{ row }">
              {{ formatDateTime(row.created_at) }}
            </template>
          </el-table-column>
        </el-table>
        <el-empty v-if="!loading.snapshots && snapshotList.length === 0" description="暂无快照记录" :image-size="80" />
      </el-tab-pane>
    </el-tabs>

    <!-- ═══════════════════════════════════════════════ -->
    <!-- Event Creation Dialog                           -->
    <!-- ═══════════════════════════════════════════════ -->
    <el-dialog v-model="showEventDialog" title="记录成长事件" width="560px">
      <el-form :model="eventForm" label-width="80px">
        <el-form-item label="学生ID">
          <el-input v-model="eventForm.student_id" placeholder="如 3" />
        </el-form-item>
        <el-form-item label="维度">
          <el-select v-model="eventForm.dimension" style="width: 100%">
            <el-option
              v-for="opt in DIMENSION_OPTIONS"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="级别">
          <el-select v-model="eventForm.severity" style="width: 100%">
            <el-option label="信息" value="info" />
            <el-option label="提醒" value="warning" />
            <el-option label="严重" value="danger" />
            <el-option label="进步" value="success" />
          </el-select>
        </el-form-item>
        <el-form-item label="事件类型">
          <el-input v-model="eventForm.event_type" placeholder="如 honor, gap_critical" />
        </el-form-item>
        <el-form-item label="标题">
          <el-input v-model="eventForm.title" placeholder="事件标题" />
        </el-form-item>
        <el-form-item label="发生时间">
          <el-date-picker
            v-model="eventForm.occurred_at"
            type="datetime"
            placeholder="选择时间（留空=当前）"
            style="width: 100%"
            format="YYYY-MM-DD HH:mm"
            value-format="YYYY-MM-DDTHH:mm:ss"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEventDialog = false">取消</el-button>
        <el-button type="primary" @click="submitEvent" :loading="loading.createEvent">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
/**
 * GrowthConsole — 成长档案全息视图
 *
 * 四Tab控制台: 看板 | 时光轴 | 全息画像 | 快照管理
 * PARENT角色: 仅显示时光轴Tab
 */

import { ref, reactive, computed, onMounted, onBeforeUnmount, nextTick, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Plus, Refresh, Loading, TrendCharts, UserFilled, MagicStick,
} from '@element-plus/icons-vue'
import * as echarts from 'echarts/core'
import '@/utils/echarts'
import { useUserStore } from '@/store/user'
import {
  getGrowthDashboard,
  getGrowthTimeline,
  getMyTimeline,
  createTimelineEvent,
  listTimelineEvents,
  getHolisticProfile,
  generateSnapshot,
  listSnapshots,
  updateTeacherComment,
  EVENT_TYPE_OPTIONS,
  DIMENSION_OPTIONS,
  eventTypeLabel,
  eventTypeIcon,
  eventTypeColor,
  severityTagType,
  dimensionLabel,
  dimensionColor,
  snapshotTypeLabel,
  scoreLevelLabel,
  scoreLevelTag,
  type GrowthDashboard,
  type GrowthTimelineResponse,
  type TimelineItem,
  type EventSeverity,
  type TimelineEventResponse,
  type StudentHolisticProfile,
  type GrowthSnapshotResponse,
  type SnapshotType,
  type GrowthDimension,
} from '@/api/growth'

const userStore = useUserStore()

// ── Tab State ──────────────────────────────

const isParent = computed(() => userStore.currentRole === 'PARENT')
const activeTab = ref(isParent.value ? 'timeline' : 'dashboard')

// ── Dashboard ──────────────────────────────

const dash = ref<GrowthDashboard>({
  total_students: 0,
  total_events: 0,
  total_snapshots: 0,
  critical_count: 0,
  warning_count: 0,
  bonus_count: 0,
  dimension_distribution: {},
  recent_critical: [],
})

const loading = reactive({
  dashboard: false,
  timeline: false,
  profile: false,
  snapshots: false,
  generate: false,
  comment: false,
  createEvent: false,
})

const anyLoading = computed(() => Object.values(loading).some(v => v))

// ── Timeline ───────────────────────────────

const studentIdInput = ref('3')
const timelineSemester = ref('')
const timelineFilter = ref('all')
const timelineData = ref<GrowthTimelineResponse | null>(null)

const filteredTimeline = computed(() => {
  if (!timelineData.value) return []
  if (timelineFilter.value === 'all') return timelineData.value.timeline
  return timelineData.value.timeline.filter(e => e.event_type === timelineFilter.value)
})

interface TimelineGroup { date: string; events: TimelineItem[] }

const groupedTimeline = computed(() => {
  const groups: TimelineGroup[] = []
  const seen = new Set<string>()
  for (const event of filteredTimeline.value) {
    if (!seen.has(event.event_date)) {
      seen.add(event.event_date)
      groups.push({ date: event.event_date, events: [event] })
    } else {
      const g = groups.find(g => g.date === event.event_date)
      if (g) g.events.push(event)
    }
  }
  return groups
})

// ── Profile ────────────────────────────────

const profileStudentId = ref('3')
const profileData = ref<StudentHolisticProfile | null>(null)
const teacherCommentText = ref('')
const radarChartRef = ref<HTMLDivElement | null>(null)
let radarChart: echarts.ECharts | null = null

const canEditComment = computed(() => {
  const role = userStore.currentRole
  return role === 'MS_ADMIN' || role === 'GRADE_LEADER' || role === 'CLASS_TEACHER'
})

const scoreDimensions = computed(() => {
  const snap = profileData.value?.current_snapshot
  if (!snap) return []
  return [
    { key: 'academic', label: '学术', color: '#409eff', value: snap.academic_score },
    { key: 'attendance', label: '考勤', color: '#67c23a', value: snap.attendance_score },
    { key: 'behavior', label: '行为', color: '#e6a23c', value: snap.behavior_score },
    { key: 'psych', label: '心理', color: '#8b5cf6', value: snap.psych_score },
    { key: 'activity', label: '活动', color: '#f56c6c', value: snap.activity_score },
  ]
})

// ── Snapshots ──────────────────────────────

const snapshotStudentId = ref('3')
const snapshotTypeSelect = ref<SnapshotType>('monthly')
const snapshotPeriodLabel = ref('')
const snapshotList = ref<GrowthSnapshotResponse[]>([])

// ── Event Dialog ───────────────────────────

const showEventDialog = ref(false)
const eventForm = reactive({
  student_id: '3',
  dimension: 'academic' as GrowthDimension,
  severity: 'info' as EventSeverity,
  event_type: 'honor',
  title: '',
  occurred_at: '',
})

// ═══════════════════════════════════════════════════
// Data Fetching
// ═══════════════════════════════════════════════════

async function fetchDashboard() {
  loading.dashboard = true
  try {
    dash.value = await getGrowthDashboard()
  } catch {
    // silent
  } finally {
    loading.dashboard = false
  }
}

async function fetchTimeline() {
  const sid = isParent.value ? undefined : parseInt(studentIdInput.value, 10)
  if (!isParent.value && (!sid || isNaN(sid))) {
    ElMessage.warning('请输入有效学生ID')
    return
  }
  loading.timeline = true
  try {
    let res: GrowthTimelineResponse
    if (isParent.value) {
      res = await getMyTimeline(timelineSemester.value || undefined)
    } else {
      res = await getGrowthTimeline(sid!, timelineSemester.value || undefined)
    }
    timelineData.value = res
  } catch {
    ElMessage.error('加载时间轴失败')
  } finally {
    loading.timeline = false
  }
}

async function fetchProfile() {
  const sid = parseInt(profileStudentId.value, 10)
  if (!sid || isNaN(sid)) {
    ElMessage.warning('请输入有效学生ID')
    return
  }
  loading.profile = true
  try {
    profileData.value = await getHolisticProfile(sid)
    teacherCommentText.value = profileData.value?.current_snapshot?.teacher_comment || ''
    // Render radar after data loaded
    await nextTick()
    renderRadar()
  } catch {
    ElMessage.error('加载画像失败')
  } finally {
    loading.profile = false
  }
}

async function fetchSnapshots() {
  const sid = parseInt(snapshotStudentId.value, 10)
  if (!sid || isNaN(sid)) {
    ElMessage.warning('请输入有效学生ID')
    return
  }
  loading.snapshots = true
  try {
    const res = await listSnapshots({ student_id: sid, page: 1, page_size: 50 })
    snapshotList.value = res.items
  } catch {
    ElMessage.error('加载快照列表失败')
  } finally {
    loading.snapshots = false
  }
}

async function submitEvent() {
  const sid = parseInt(eventForm.student_id, 10)
  if (!sid || isNaN(sid)) {
    ElMessage.warning('请输入有效学生ID')
    return
  }
  if (!eventForm.title.trim()) {
    ElMessage.warning('请输入事件标题')
    return
  }
  loading.createEvent = true
  try {
    await createTimelineEvent({
      student_id: sid,
      dimension: eventForm.dimension,
      severity: eventForm.severity,
      event_type: eventForm.event_type,
      title: eventForm.title,
      occurred_at: eventForm.occurred_at || undefined,
    })
    ElMessage.success('成长事件已记录')
    showEventDialog.value = false
    eventForm.title = ''
    // Refresh timeline if same student
    if (String(sid) === studentIdInput.value) {
      fetchTimeline()
    }
  } catch {
    ElMessage.error('创建事件失败')
  } finally {
    loading.createEvent = false
  }
}

async function generateSnapshot() {
  const sid = parseInt(snapshotStudentId.value, 10)
  if (!sid || isNaN(sid)) {
    ElMessage.warning('请输入有效学生ID')
    return
  }
  if (!snapshotPeriodLabel.value.trim()) {
    ElMessage.warning('请输入周期标签')
    return
  }
  loading.generate = true
  try {
    const res = await generateSnapshot({
      student_id: sid,
      snapshot_type: snapshotTypeSelect.value,
      period_label: snapshotPeriodLabel.value,
    })
    ElMessage.success(`快照已生成: ${res.period_label}`)
    fetchSnapshots()
  } catch {
    ElMessage.error('生成快照失败')
  } finally {
    loading.generate = false
  }
}

async function generateSnapshotFromProfile() {
  const sid = parseInt(profileStudentId.value, 10)
  if (!sid || isNaN(sid)) return

  const now = new Date()
  const periodLabel = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`

  loading.generate = true
  try {
    const res = await generateSnapshot({
      student_id: sid,
      snapshot_type: 'monthly',
      period_label: periodLabel,
    })
    ElMessage.success(`月度快照已生成: ${periodLabel}`)
    // Refresh profile
    fetchProfile()
  } catch {
    ElMessage.error('生成快照失败')
  } finally {
    loading.generate = false
  }
}

async function saveTeacherComment() {
  const snap = profileData.value?.current_snapshot
  if (!snap) return

  if (teacherCommentText.value.trim().length < 5) {
    ElMessage.warning('评语至少5个字')
    return
  }

  loading.comment = true
  try {
    await updateTeacherComment(snap.id, { teacher_comment: teacherCommentText.value.trim() })
    ElMessage.success('评语已保存')
    // Update local data
    if (profileData.value?.current_snapshot) {
      profileData.value.current_snapshot.teacher_comment = teacherCommentText.value.trim()
    }
  } catch {
    ElMessage.error('保存评语失败')
  } finally {
    loading.comment = false
  }
}

// ── Tab Change Handler ─────────────────────

function onTabChange(name: string | number) {
  if (name === 'dashboard' && dash.value.total_students === 0) {
    fetchDashboard()
  } else if (name === 'timeline' && !timelineData.value && isParent.value) {
    fetchTimeline()
  } else if (name === 'snapshots' && snapshotList.value.length === 0) {
    fetchSnapshots()
  }
}

function refreshAll() {
  if (activeTab.value === 'dashboard') fetchDashboard()
  if (activeTab.value === 'timeline') fetchTimeline()
  if (activeTab.value === 'profile') fetchProfile()
  if (activeTab.value === 'snapshots') fetchSnapshots()
}

function goToProfile(studentId: number) {
  profileStudentId.value = String(studentId)
  activeTab.value = 'profile'
  fetchProfile()
}

// ── Radar Chart ────────────────────────────

function renderRadar() {
  const snap = profileData.value?.current_snapshot
  if (!snap || !radarChartRef.value) return

  if (radarChart) {
    radarChart.dispose()
  }

  radarChart = echarts.init(radarChartRef.value)
  radarChart.setOption({
    tooltip: {
      trigger: 'item',
      formatter: (params: any) => {
        const values = params.value
        return `<b>${snap.student_name || '学生'} - ${snap.period_label}</b><br/>` +
          `学术: ${values[0].toFixed(1)}<br/>` +
          `考勤: ${values[1].toFixed(1)}<br/>` +
          `行为: ${values[2].toFixed(1)}<br/>` +
          `心理: ${values[3].toFixed(1)}<br/>` +
          `活动: ${values[4].toFixed(1)}`
      },
    },
    radar: {
      indicator: [
        { name: '学术', max: 100 },
        { name: '考勤', max: 100 },
        { name: '行为', max: 100 },
        { name: '心理', max: 100 },
        { name: '活动', max: 100 },
      ],
      shape: 'polygon',
      splitNumber: 5,
      axisName: {
        color: '#606266',
        fontSize: 13,
        fontWeight: 600,
      },
      splitLine: {
        lineStyle: { color: '#e4e7ed' },
      },
      splitArea: {
        show: true,
        areaStyle: {
          color: ['rgba(64,158,255,0.02)', 'rgba(64,158,255,0.05)', 'rgba(64,158,255,0.08)', 'rgba(64,158,255,0.05)', 'rgba(64,158,255,0.02)'],
        },
      },
      axisLine: {
        lineStyle: { color: '#dcdfe6' },
      },
    },
    series: [{
      type: 'radar',
      data: [{
        value: [
          snap.academic_score,
          snap.attendance_score,
          snap.behavior_score,
          snap.psych_score,
          snap.activity_score,
        ],
        name: snap.period_label,
        areaStyle: {
          color: 'rgba(64,158,255,0.2)',
        },
        lineStyle: {
          color: '#409eff',
          width: 2,
        },
        itemStyle: {
          color: '#409eff',
        },
      }],
    }],
  })
}

function handleResize() {
  radarChart?.resize()
}

// ── Helpers ────────────────────────────────

function formatDateLabel(dateStr: string): string {
  const d = new Date(dateStr)
  const now = new Date()
  const diffDays = Math.floor((now.getTime() - d.getTime()) / 86400000)
  const month = d.getMonth() + 1
  const day = d.getDate()
  const weekday = ['日', '一', '二', '三', '四', '五', '六'][d.getDay()]
  if (diffDays === 0) return `今天 · ${month}月${day}日`
  if (diffDays === 1) return `昨天 · ${month}月${day}日`
  return `${month}月${day}日 星期${weekday}`
}

function formatTime(dateStr: string): string {
  const d = new Date(dateStr)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

function formatDateTime(dateStr: string): string {
  if (!dateStr) return '-'
  const d = new Date(dateStr)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

function severityLabel(s: EventSeverity): string {
  return { info: '信息', warning: '提醒', danger: '严重', success: '进步' }[s] || s
}

function dimBarWidth(count: number): string {
  const max = Math.max(...Object.values(dash.value.dimension_distribution || { 0: 1 }), 1)
  return `${Math.min(100, (count / max) * 100)}%`
}

function scoreBarWidth(score: number): string {
  return `${Math.min(100, Math.max(0, score))}%`
}

function scoreColor(score: number): string {
  if (score >= 90) return '#67c23a'
  if (score >= 75) return '#409eff'
  if (score >= 60) return '#e6a23c'
  return '#f56c6c'
}

function dimensionTagType(dim: string): string {
  const meta: Record<string, string> = {
    academic: 'primary',
    attendance: 'success',
    behavior: 'warning',
    psych: 'info',
    activity: 'danger',
  }
  return meta[dim] || 'info'
}

function formatAiPrescription(text: string): string {
  // Simple markdown-like formatting
  return text
    .replace(/\n/g, '<br/>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
}

// ── Lifecycle ──────────────────────────────

onMounted(() => {
  if (isParent.value) {
    fetchTimeline()
  } else {
    fetchDashboard()
  }
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  radarChart?.dispose()
  window.removeEventListener('resize', handleResize)
})
</script>

<style scoped>
.growth-console {
  max-width: 1200px;
  margin: 0 auto;
}

/* ── Page Header ── */

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.page-title {
  font-size: 20px;
  font-weight: 700;
  color: #303133;
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
}

.header-actions {
  display: flex;
  gap: 8px;
}

/* ── KPI Cards ── */

.kpi-row {
  margin-bottom: 4px;
}

.kpi-card {
  text-align: center;
  border-radius: 10px;
  transition: transform 0.2s;
}

.kpi-card:hover {
  transform: translateY(-2px);
}

.kpi-value {
  font-size: 28px;
  font-weight: 700;
  line-height: 1.2;
}

.kpi-label {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}

/* ── Dimension Distribution ── */

.dim-distribution {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 8px 0;
}

.dim-bar-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.dim-bar-label {
  width: 50px;
  font-size: 13px;
  color: #606266;
  display: flex;
  align-items: center;
  gap: 4px;
}

.dim-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.dim-bar-track {
  flex: 1;
  height: 18px;
  background: #f0f2f5;
  border-radius: 9px;
  overflow: hidden;
}

.dim-bar-fill {
  height: 100%;
  border-radius: 9px;
  transition: width 0.4s ease;
}

.dim-bar-count {
  width: 28px;
  text-align: right;
  font-size: 13px;
  font-weight: 600;
  color: #303133;
}

/* ── Tab Toolbar ── */

.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  flex-wrap: wrap;
  gap: 8px;
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.selector-label {
  font-size: 13px;
  color: #909399;
  white-space: nowrap;
}

/* ── Student Card ── */

.student-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 20px 24px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-radius: 12px;
  margin-bottom: 16px;
  color: #fff;
}

.student-avatar {
  width: 56px;
  height: 56px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.2);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.student-avatar.large {
  width: 64px;
  height: 64px;
}

.avatar-text {
  font-size: 24px;
  font-weight: 700;
  color: #fff;
}

.student-info h3 {
  font-size: 18px;
  font-weight: 600;
  margin: 0 0 4px;
}

.student-info p {
  font-size: 13px;
  opacity: 0.85;
  margin: 0;
}

/* ── Event Filters ── */

.event-filters {
  margin-bottom: 20px;
  overflow-x: auto;
  white-space: nowrap;
  padding-bottom: 4px;
}

.filter-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-right: 4px;
  vertical-align: middle;
}

/* ── Loading / Empty ── */

.loading-state,
.empty-prompt {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 20px;
  color: #909399;
  gap: 16px;
}

.prompt-icon {
  font-size: 48px;
  color: #c0c4cc;
}

.loading-state p,
.empty-prompt p {
  margin: 0;
  font-size: 14px;
}

/* ── Timeline ── */

.timeline-container {
  position: relative;
}

.timeline-track {
  position: relative;
  padding-left: 36px;
}

.timeline-track::before {
  content: '';
  position: absolute;
  left: 15px;
  top: 8px;
  bottom: 8px;
  width: 2px;
  background: #e4e7ed;
  border-radius: 1px;
}

.date-divider {
  position: relative;
  display: flex;
  align-items: center;
  margin: 24px 0 12px -36px;
  padding-left: 36px;
}

.date-divider::before {
  content: '';
  position: absolute;
  left: 8px;
  width: 16px;
  height: 16px;
  background: #409eff;
  border-radius: 50%;
  border: 3px solid #ecf5ff;
  z-index: 1;
}

.date-badge {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
  background: #f0f2f5;
  padding: 3px 12px;
  border-radius: 12px;
}

.timeline-event {
  position: relative;
  display: flex;
  gap: 16px;
  margin-bottom: 16px;
}

.timeline-node {
  position: absolute;
  left: -26px;
  top: 16px;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  flex-shrink: 0;
  z-index: 1;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.15);
}

.event-card {
  flex: 1;
  background: #fff;
  border-radius: 10px;
  padding: 16px 20px;
  box-shadow: 0 1px 4px rgba(0, 21, 41, 0.06);
  transition: box-shadow 0.2s, transform 0.15s;
  border-left: 3px solid #e4e7ed;
}

.timeline-event.severity-danger .event-card { border-left-color: #f56c6c; }
.timeline-event.severity-warning .event-card { border-left-color: #e6a23c; }
.timeline-event.severity-success .event-card { border-left-color: #67c23a; }
.timeline-event.severity-info .event-card { border-left-color: #409eff; }

.event-card:hover {
  box-shadow: 0 4px 16px rgba(0, 21, 41, 0.1);
  transform: translateX(4px);
}

.event-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.event-time {
  font-size: 12px;
  color: #c0c4cc;
  margin-left: auto;
}

.event-title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
  margin: 0 0 6px;
  line-height: 1.4;
}

.event-desc {
  font-size: 13px;
  color: #606266;
  line-height: 1.65;
  margin: 0;
}

/* ── Profile ── */

.profile-student-header {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 20px 24px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-radius: 12px;
  color: #fff;
}

.profile-name {
  font-size: 20px;
  font-weight: 700;
  margin: 0 0 4px;
}

.profile-meta {
  font-size: 13px;
  opacity: 0.85;
  margin: 0;
}

.snapshot-period {
  margin-left: 12px;
  font-size: 12px;
  color: #909399;
}

.radar-chart-container {
  width: 100%;
  height: 360px;
}

/* ── Score List ── */

.score-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 8px 0;
}

.score-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.score-label {
  width: 50px;
  font-size: 13px;
  color: #606266;
  display: flex;
  align-items: center;
  gap: 4px;
}

.score-bar-track {
  flex: 1;
  height: 16px;
  background: #f0f2f5;
  border-radius: 8px;
  overflow: hidden;
}

.score-bar-fill {
  height: 100%;
  border-radius: 8px;
  transition: width 0.4s ease;
}

.score-value {
  width: 40px;
  text-align: right;
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}

.metric-item {
  text-align: center;
  padding: 8px 4px;
  background: #f8f9fa;
  border-radius: 8px;
}

.metric-label {
  display: block;
  font-size: 12px;
  color: #909399;
  margin-bottom: 4px;
}

.metric-value {
  display: block;
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}

/* ── AI Prescription ── */

.ai-prescription {
  font-size: 14px;
  line-height: 1.8;
  color: #606266;
  padding: 8px 4px;
}

.ai-prescription :deep(strong) {
  color: #303133;
}
</style>
