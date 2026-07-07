<template>
  <div class="positive-ranking">
    <!-- ════════════════════════════════════════ -->
    <!-- Page Header                              -->
    <!-- ════════════════════════════════════════ -->
    <div class="page-header">
      <div class="header-left">
        <h2 class="page-title">
          <el-icon :size="22"><Histogram /></el-icon>
          正能量排行榜
        </h2>
        <span class="page-subtitle">品德之星 · 助人为乐 · 志愿服务 · 劳动实践</span>
      </div>
      <div class="header-right">
        <el-radio-group v-model="rankingScope" size="default" @change="loadRanking">
          <el-radio-button label="class">班级排名</el-radio-button>
          <el-radio-button label="grade">年级排名</el-radio-button>
          <el-radio-button label="school">全校排名</el-radio-button>
        </el-radio-group>
      </div>
    </div>

    <!-- ════════════════════════════════════════ -->
    <!-- 维度筛选 + 搜索                         -->
    <!-- ════════════════════════════════════════ -->
    <el-card shadow="never" class="filter-card">
      <div class="filter-row">
        <div class="filter-item">
          <span class="filter-label">维度筛选:</span>
          <el-radio-group v-model="selectedDimension" size="small" @change="loadRanking">
            <el-radio-button label="all">全部</el-radio-button>
            <el-radio-button label="moral">道德品质</el-radio-button>
            <el-radio-button label="academic">学业水平</el-radio-button>
            <el-radio-button label="health">身心健康</el-radio-button>
            <el-radio-button label="art">艺术素养</el-radio-button>
            <el-radio-button label="social">社会实践</el-radio-button>
          </el-radio-group>
        </div>

        <div class="filter-item">
          <el-input
            v-model="searchKeyword"
            placeholder="搜索学生姓名..."
            clearable
            style="width: 250px"
            @input="handleSearch"
          >
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>
        </div>
      </div>
    </el-card>

    <!-- ════════════════════════════════════════ -->
    <!-- Top 3 领奖台                             -->
    <!-- ════════════════════════════════════════ -->
    <div class="podium-section" v-if="topThree.length > 0">
      <div class="podium">
        <!-- 第二名 -->
        <div class="podium-item second" v-if="topThree.length > 1">
          <div class="podium-avatar">
            <el-avatar :size="64" class="rank-avatar">
              {{ topThree[1].student_name?.charAt(0) || '?' }}
            </el-avatar>
            <div class="rank-badge silver">2</div>
          </div>
          <div class="podium-name">{{ topThree[1].student_name }}</div>
          <div class="podium-class">{{ topThree[1].class_name }}</div>
          <div class="podium-score">{{ topThree[1].positive_score }} 分</div>
          <div class="podium-bar silver-bar"></div>
        </div>

        <!-- 第一名 -->
        <div class="podium-item first" v-if="topThree.length > 0">
          <div class="podium-crown">👑</div>
          <div class="podium-avatar">
            <el-avatar :size="80" class="rank-avatar gold-avatar">
              {{ topThree[0].student_name?.charAt(0) || '?' }}
            </el-avatar>
            <div class="rank-badge gold">1</div>
          </div>
          <div class="podium-name">{{ topThree[0].student_name }}</div>
          <div class="podium-class">{{ topThree[0].class_name }}</div>
          <div class="podium-score">{{ topThree[0].positive_score }} 分</div>
          <div class="podium-bar gold-bar"></div>
        </div>

        <!-- 第三名 -->
        <div class="podium-item third" v-if="topThree.length > 2">
          <div class="podium-avatar">
            <el-avatar :size="64" class="rank-avatar">
              {{ topThree[2].student_name?.charAt(0) || '?' }}
            </el-avatar>
            <div class="rank-badge bronze">3</div>
          </div>
          <div class="podium-name">{{ topThree[2].student_name }}</div>
          <div class="podium-class">{{ topThree[2].class_name }}</div>
          <div class="podium-score">{{ topThree[2].positive_score }} 分</div>
          <div class="podium-bar bronze-bar"></div>
        </div>
      </div>
    </div>

    <!-- ════════════════════════════════════════ -->
    <!-- 排行榜表格                               -->
    <!-- ════════════════════════════════════════ -->
    <el-card shadow="never" class="ranking-card">
      <template #header>
        <div class="card-header-with-action">
          <span class="card-title-text">
            <el-icon><Rank /></el-icon> 完整排行榜
          </span>
          <div class="header-actions">
            <el-button
              type="success"
              size="small"
              @click="exportRanking"
            >
              <el-icon><Download /></el-icon> 导出
            </el-button>
            <el-button
              type="primary"
              size="small"
              @click="loadRanking"
            >
              <el-icon><Refresh /></el-icon> 刷新
            </el-button>
          </div>
        </div>
      </template>

      <el-table
        :data="rankingList"
        v-loading="rankingLoading"
        style="width: 100%"
        size="default"
        stripe
        empty-text="暂无排行数据"
      >
        <el-table-column prop="rank" label="排名" width="80" align="center">
          <template #default="{ row, $index }">
            <div class="rank-cell">
              <span v-if="$index < 3" class="rank-medal">
                {{ ['🥇', '🥈', '🥉'][$index] }}
              </span>
              <span v-else class="rank-number">{{ $index + 1 }}</span>
            </div>
          </template>
        </el-table-column>

        <el-table-column prop="student_name" label="学生姓名" width="120" />

        <el-table-column prop="class_name" label="班级" width="120" align="center" />

        <el-table-column label="各维度加分" width="300">
          <template #default="{ row }">
            <div class="dimension-bars">
              <div class="mini-bar">
                <span class="mini-label">品德</span>
                <el-progress
                  :percentage="row.moral_positive || 0"
                  :color="'#ef4444'"
                  :stroke-width="8"
                  :show-text="false"
                />
              </div>
              <div class="mini-bar">
                <span class="mini-label">学业</span>
                <el-progress
                  :percentage="row.academic_positive || 0"
                  :color="'#3b82f6'"
                  :stroke-width="8"
                  :show-text="false"
                />
              </div>
              <div class="mini-bar">
                <span class="mini-label">身心</span>
                <el-progress
                  :percentage="row.health_positive || 0"
                  :color="'#10b981'"
                  :stroke-width="8"
                  :show-text="false"
                />
              </div>
            </div>
          </template>
        </el-table-column>

        <el-table-column prop="positive_score" label="总加分" width="120" align="center">
          <template #default="{ row }">
            <span class="positive-score">{{ row.positive_score }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="record_count" label="加分次数" width="100" align="center">
          <template #default="{ row }">
            {{ row.record_count || 0 }} 次
          </template>
        </el-table-column>

        <el-table-column label="操作" width="120" align="center" fixed="right">
          <template #default="{ row }">
            <el-button
              type="primary"
              size="small"
              link
              @click="viewStudentDetail(row as RankingItem)"
            >
              查看详情
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <div class="pagination-wrapper">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :page-sizes="[10, 20, 50]"
          :total="totalRecords"
          layout="total, sizes, prev, pager, next"
          @size-change="loadRanking"
          @current-change="loadRanking"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * PositiveRanking.vue — 正能量排行榜
 *
 * 功能:
 *  1. 按正向加分总分排名
 *  2. 显示正能量之星（Top 10）
 *  3. 按维度展示（品德之星、志愿服务、劳动实践等）
 *
 * 对应后端 API:
 *  - GET /api/v1/evaluation/ranking/positive — 正向加分排行榜（需新增）
 *  - GET /api/v1/evaluation/classes/{class_id}/ranking — 班级排名（过滤正向加分）
 */

import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import {
  Histogram, Search, Rank, Download, Refresh,
} from '@element-plus/icons-vue'
import request from '@/api/request'
import {
  getPositiveScoreRanking,
  type PositiveRankingOut,
} from '@/api/evaluation'

// ════════════════════════════════════════
// 类型定义
// ════════════════════════════════════════

interface RankingItem {
  student_id: number
  student_name: string
  class_name: string
  positive_score: number
  record_count: number
  moral_positive: number
  academic_positive: number
  health_positive: number
  art_positive: number
  social_positive: number
}

// ════════════════════════════════════════
// 响应式状态
// ════════════════════════════════════════

const rankingScope = ref<'class' | 'grade' | 'school'>('class')
const selectedDimension = ref<string>('all')
const searchKeyword = ref('')
const rankingLoading = ref(false)

const currentPage = ref(1)
const pageSize = ref(20)
const totalRecords = ref(0)

const rankingList = ref<RankingItem[]>([])

// ════════════════════════════════════════
// 计算属性
// ════════════════════════════════════════

const topThree = computed(() => {
  return rankingList.value.slice(0, 3)
})

// ════════════════════════════════════════
// 生命周期
// ════════════════════════════════════════

onMounted(() => {
  loadRanking()
})

// ════════════════════════════════════════
// 数据加载
// ════════════════════════════════════════

async function loadRanking() {
  try {
    rankingLoading.value = true

    // 调用后端 API 获取正向加分排行榜
    const params: any = {
      limit: pageSize.value,
      offset: (currentPage.value - 1) * pageSize.value,
    }

    // 根据排名范围设置参数
    if (rankingScope.value === 'class') {
      // TODO: 获取当前用户管理的班级ID
      params.class_id = 1 // 临时硬编码
    } else if (rankingScope.value === 'grade') {
      // TODO: 获取当前用户管理的年级ID
      params.grade_id = 1 // 临时硬编码
    }

    // 维度筛选
    if (selectedDimension.value !== 'all') {
      params.dimension = selectedDimension.value
    }

    const data: PositiveRankingOut = await getPositiveScoreRanking(params)

    rankingList.value = data.ranking.map(item => ({
      ...item,
      moral_positive: 0,
      academic_positive: 0,
      health_positive: 0,
      art_positive: 0,
      social_positive: 0,
    }))
    totalRecords.value = data.total || data.ranking.length
  } catch (err: any) {
    ElMessage.error(`加载排行榜失败: ${err.message || err}`)
    // 降级到模拟数据
    rankingList.value = generateMockRanking()
    totalRecords.value = rankingList.value.length
  } finally {
    rankingLoading.value = false
  }
}

function handleSearch() {
  // TODO: 实现搜索逻辑
  if (searchKeyword.value.trim()) {
    loadRanking()
  }
}

async function exportRanking() {
  try {
    ElMessage.success('正在导出排行榜...')
    // TODO: 调用导出 API
  } catch (err: any) {
    ElMessage.error(`导出失败: ${err.message || err}`)
  }
}

function viewStudentDetail(row: RankingItem) {
  // TODO: 跳转到学生详情页
  ElMessage.info(`查看学生 ${row.student_name} 的详情`)
}

// ════════════════════════════════════════
// 模拟数据生成（临时）
// ════════════════════════════════════════

function generateMockRanking(): RankingItem[] {
  const names = ['张三', '李四', '王五', '赵六', '钱七', '孙八', '周九', '吴十']
  const classes = ['2501班', '2502班', '2503班']

  return names.map((name, idx) => ({
    student_id: idx + 1,
    student_name: name,
    class_name: classes[idx % classes.length],
    positive_score: Math.floor(Math.random() * 100) + 10,
    record_count: Math.floor(Math.random() * 20) + 1,
    moral_positive: Math.floor(Math.random() * 30),
    academic_positive: Math.floor(Math.random() * 30),
    health_positive: Math.floor(Math.random() * 30),
    art_positive: Math.floor(Math.random() * 30),
    social_positive: Math.floor(Math.random() * 30),
  })).sort((a, b) => b.positive_score - a.positive_score)
}
</script>

<style scoped>
.positive-ranking {
  padding: 16px;
  background: #f5f7fa;
  min-height: calc(100vh - 64px);
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding: 12px 16px;
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.page-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: #303133;
}

.page-subtitle {
  margin-left: 12px;
  font-size: 13px;
  color: #909399;
}

.filter-card {
  margin-bottom: 16px;
  border-radius: 8px;
}

.filter-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.filter-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.filter-label {
  font-size: 14px;
  color: #606266;
  font-weight: 500;
}

/* ════════════════════════════════════════ */
/* 领奖台样式                               */
/* ════════════════════════════════════════ */

.podium-section {
  margin-bottom: 24px;
}

.podium {
  display: flex;
  justify-content: center;
  align-items: flex-end;
  gap: 24px;
  padding: 32px;
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
}

.podium-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.podium-item.first {
  order: 2;
}

.podium-item.second {
  order: 1;
}

.podium-item.third {
  order: 3;
}

.podium-crown {
  font-size: 32px;
  margin-bottom: -8px;
}

.podium-avatar {
  position: relative;
}

.rank-avatar {
  background: #909399;
  font-size: 24px;
  font-weight: 600;
}

.gold-avatar {
  background: linear-gradient(135deg, #fbbf24, #f59e0b);
}

.rank-badge {
  position: absolute;
  bottom: -4px;
  right: -4px;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  color: #fff;
}

.rank-badge.gold {
  background: #fbbf24;
}

.rank-badge.silver {
  background: #9ca3af;
}

.rank-badge.bronze {
  background: #d97706;
}

.podium-name {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}

.podium-class {
  font-size: 12px;
  color: #909399;
}

.podium-score {
  font-size: 20px;
  font-weight: 700;
  color: #67c23a;
}

.podium-bar {
  width: 120px;
  border-radius: 8px 8px 0 0;
}

.gold-bar {
  height: 160px;
  background: linear-gradient(180deg, #fbbf24, #f59e0b);
}

.silver-bar {
  height: 120px;
  background: linear-gradient(180deg, #d1d5db, #9ca3af);
}

.bronze-bar {
  height: 100px;
  background: linear-gradient(180deg, #fcd34d, #d97706);
}

/* ════════════════════════════════════════ */
/* 排行榜表格                               */
/* ════════════════════════════════════════ */

.ranking-card {
  border-radius: 8px;
}

.card-title-text {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
  font-size: 15px;
}

.card-header-with-action {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.rank-cell {
  font-size: 18px;
}

.rank-medal {
  font-size: 20px;
}

.rank-number {
  font-weight: 600;
  color: #909399;
}

.dimension-bars {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.mini-bar {
  display: flex;
  align-items: center;
  gap: 4px;
}

.mini-label {
  font-size: 10px;
  color: #909399;
  width: 28px;
}

.positive-score {
  font-size: 16px;
  font-weight: 600;
  color: #67c23a;
}

.pagination-wrapper {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>
