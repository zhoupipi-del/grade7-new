<template>
  <div class="research-console">
    <!-- 顶部统计看板 -->
    <div class="dashboard-section">
      <el-row :gutter="16">
        <el-col :span="8">
          <div class="stat-card stat-lesson" @click="activeTab = 'lesson'">
            <div class="stat-icon-wrap">
              <el-icon :size="28"><Document /></el-icon>
            </div>
            <div class="stat-body">
              <div class="stat-value">{{ planStats?.total_plans ?? '--' }}</div>
              <div class="stat-label">集体备课</div>
              <div class="stat-sub">
                <span class="sub-item">草稿 {{ planStats?.draft_count ?? 0 }}</span>
                <span class="sub-dot">·</span>
                <span class="sub-item">评议 {{ planStats?.review_count ?? 0 }}</span>
                <span class="sub-dot">·</span>
                <span class="sub-item">已发布 {{ planStats?.published_count ?? 0 }}</span>
              </div>
            </div>
          </div>
        </el-col>
        <el-col :span="8">
          <div class="stat-card stat-observation" @click="activeTab = 'observation'">
            <div class="stat-icon-wrap">
              <el-icon :size="28"><View /></el-icon>
            </div>
            <div class="stat-body">
              <div class="stat-value">{{ obsStats?.total_observations ?? '--' }}</div>
              <div class="stat-label">听课评课</div>
              <div class="stat-sub">
                <span class="sub-item">待确认 {{ obsStats?.pending_feedback ?? 0 }}</span>
                <span class="sub-dot">·</span>
                <span class="sub-item">已确认 {{ obsStats?.confirmed ?? 0 }}</span>
                <span class="sub-dot">·</span>
                <span class="sub-item">均分 {{ obsStats?.avg_score != null ? obsStats.avg_score.toFixed(1) : '--' }}</span>
              </div>
            </div>
          </div>
        </el-col>
        <el-col :span="8">
          <div class="stat-card stat-activity" @click="activeTab = 'activity'">
            <div class="stat-icon-wrap">
              <el-icon :size="28"><Calendar /></el-icon>
            </div>
            <div class="stat-body">
              <div class="stat-value">{{ actStats?.total_activities ?? '--' }}</div>
              <div class="stat-label">教研活动</div>
              <div class="stat-sub">
                <span class="sub-item">计划 {{ actStats?.planned ?? 0 }}</span>
                <span class="sub-dot">·</span>
                <span class="sub-item">进行中 {{ actStats?.in_progress ?? 0 }}</span>
                <span class="sub-dot">·</span>
                <span class="sub-item">已完成 {{ actStats?.completed ?? 0 }}</span>
              </div>
            </div>
          </div>
        </el-col>
      </el-row>
    </div>

    <!-- Tab导航 -->
    <el-tabs v-model="activeTab" class="research-tabs" @tab-change="onTabChange">
      <el-tab-pane label="集体备课" name="lesson">
        <LessonPrepTab v-if="loaded.lesson" />
      </el-tab-pane>
      <el-tab-pane label="听课评课" name="observation">
        <ObservationTab v-if="loaded.observation" />
      </el-tab-pane>
      <el-tab-pane label="教研活动" name="activity">
        <ActivityTab v-if="loaded.activity" />
      </el-tab-pane>
      <el-tab-pane label="教师画像" name="profile">
        <TeacherProfileCard v-if="loaded.profile" />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { Document, View, Calendar } from '@element-plus/icons-vue'
import LessonPrepTab from './components/LessonPrepTab.vue'
import ObservationTab from './components/ObservationTab.vue'
import ActivityTab from './components/ActivityTab.vue'
import TeacherProfileCard from './components/TeacherProfileCard.vue'
import * as lpApi from '@/api/researchLessonPrep'
import * as obsApi from '@/api/researchObservation'
import * as actApi from '@/api/researchActivities'

const activeTab = ref('lesson')
const loaded = reactive({ lesson: true, observation: false, activity: false, profile: false })

const planStats = ref<lpApi.DashboardStats | null>(null)
const obsStats = ref<obsApi.DashboardStats | null>(null)
const actStats = ref<actApi.DashboardStats | null>(null)

async function loadAllDashboards() {
  const results = await Promise.allSettled([
    lpApi.getDashboard(),
    obsApi.getDashboard(),
    actApi.getDashboard(),
  ])
  if (results[0].status === 'fulfilled') planStats.value = results[0].value
  if (results[1].status === 'fulfilled') obsStats.value = results[1].value
  if (results[2].status === 'fulfilled') actStats.value = results[2].value
}

function onTabChange(name: string | number) {
  const key = String(name)
  if (key === 'observation') loaded.observation = true
  if (key === 'activity') loaded.activity = true
  if (key === 'profile') loaded.profile = true
}

onMounted(loadAllDashboards)
</script>

<style scoped>
.research-console {
  padding: 16px;
}

.dashboard-section {
  margin-bottom: 16px;
}

.stat-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 20px 24px;
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.3s;
  border: 1px solid var(--el-border-color-light);
  background: var(--el-bg-color);
}

.stat-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08);
}

.stat-icon-wrap {
  width: 56px;
  height: 56px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.stat-lesson .stat-icon-wrap { background: #e8f4fd; color: #409eff; }
.stat-observation .stat-icon-wrap { background: #fdf6ec; color: #e6a23c; }
.stat-activity .stat-icon-wrap { background: #f0f9eb; color: #67c23a; }

.stat-value {
  font-size: 28px;
  font-weight: 700;
  line-height: 1.2;
  color: var(--el-text-color-primary);
}

.stat-label {
  font-size: 14px;
  color: var(--el-text-color-secondary);
  margin-top: 2px;
}

.stat-sub {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
  margin-top: 6px;
}

.sub-dot {
  margin: 0 4px;
}

.research-tabs {
  min-height: 500px;
}

.research-tabs :deep(.el-tabs__header) {
  margin-bottom: 16px;
}
</style>
