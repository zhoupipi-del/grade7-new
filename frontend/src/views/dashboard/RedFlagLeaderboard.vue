<template>
  <div class="flag-leaderboard">
    <!-- ═══ 顶部：金旗荣誉榜 — 各年级第一名 ═══ -->
    <div class="flag-champions" v-if="champions.length > 0">
      <div
        v-for="(champ, idx) in champions"
        :key="champ.class_id"
        class="champion-card"
        :style="{ animationDelay: `${idx * 0.12}s` }"
      >
        <div class="champion-flag">
          <el-icon :size="28" color="#fbbf24"><Flag /></el-icon>
        </div>
        <div class="champion-body">
          <div class="champion-rank-label">第 {{ champ.rank }} 名 · 蝉联</div>
          <div class="champion-class">{{ champ.class_name }}</div>
          <div class="champion-score">
            <span class="score-num">{{ champ.final_score.toFixed(1) }}</span>
            <span class="score-unit">分</span>
          </div>
        </div>
        <div class="champion-period">{{ champ.period_label }}</div>
      </div>
    </div>

    <!-- ═══ 底部：龙虎榜表格 ═══ -->
    <div class="flag-table-container">
      <div class="table-header">
        <span class="table-title">
          <el-icon><Trophy /></el-icon>
          班级流动红旗龙虎榜
        </span>
        <div class="table-meta">
          <el-tag v-if="!isOffline" type="success" effect="plain" size="small">
            <el-icon class="pulse-dot"><CircleCheck /></el-icon>
            在线 · 实时
          </el-tag>
          <el-tag v-else type="warning" effect="dark" size="small" class="animate-pulse">
            ⚠️ 离线 · 缓存
          </el-tag>
        </div>
      </div>

      <el-table
        :data="leaderboard"
        size="small"
        :row-class-name="rowClassName"
        style="width: 100%"
        :max-height="280"
      >
        <el-table-column label="排名" width="70" align="center">
          <template #default="{ row }">
            <div class="rank-cell" :class="`rank-${row.rank}`">
              <span v-if="row.rank <= 3" class="rank-medal" :class="`medal-${row.rank}`">
                {{ row.rank }}
              </span>
              <span v-else class="rank-num">{{ row.rank }}</span>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="班级" min-width="100">
          <template #default="{ row }">
            <span class="class-name">{{ row.class_name }}</span>
          </template>
        </el-table-column>

        <el-table-column label="基础分" width="80" align="center">
          <template #default="{ row }">
            <span class="score-base">{{ row.base_score.toFixed(1) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="违纪扣分" width="90" align="center">
          <template #default="{ row }">
            <span class="deduction discipline" v-if="row.discipline_deduction > 0">
              -{{ row.discipline_deduction.toFixed(1) }}
            </span>
            <span v-else class="deduction-zero">—</span>
          </template>
        </el-table-column>

        <el-table-column label="考勤扣分" width="90" align="center">
          <template #default="{ row }">
            <span class="deduction attendance" v-if="row.attendance_deduction > 0">
              -{{ row.attendance_deduction.toFixed(1) }}
            </span>
            <span v-else class="deduction-zero">—</span>
          </template>
        </el-table-column>

        <el-table-column label="最终得分" width="100" align="center">
          <template #default="{ row }">
            <span class="score-final" :class="`final-${scoreTier(row.final_score)}`">
              {{ row.final_score.toFixed(1) }}
            </span>
          </template>
        </el-table-column>

        <el-table-column label="评分明细" min-width="140">
          <template #default="{ row }">
            <div class="score-breakdown">
              <span class="breakdown-item" v-if="row.self_score !== null">
                自评 <strong>{{ row.self_score }}</strong>
              </span>
              <span class="breakdown-item" v-if="row.grade_score !== null">
                年级 <strong>{{ row.grade_score }}</strong>
              </span>
              <span class="breakdown-item" v-if="row.ms_score !== null">
                德育处 <strong>{{ row.ms_score }}</strong>
              </span>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { Flag, Trophy, CircleCheck } from '@element-plus/icons-vue'
import {
  getRedFlagLeaderboard,
  getDemoRedFlagLeaderboard,
  type FlagEvaluationItem,
} from '@/api/dashboard'

// ─── 响应式数据 ──────────────────────────────────────────────────
const leaderboard = ref<FlagEvaluationItem[]>(getDemoRedFlagLeaderboard())
const isOffline = ref(!navigator.onLine)
let poller: ReturnType<typeof setInterval> | null = null

// ─── 计算属性 ────────────────────────────────────────────────────
/** 各年级第一名 — 金旗荣誉 */
const champions = computed(() => {
  const byGrade = new Map<number, FlagEvaluationItem>()
  for (const item of leaderboard.value) {
    const existing = byGrade.get(item.grade_id)
    if (!existing || item.rank < existing.rank) {
      byGrade.set(item.grade_id, item)
    }
  }
  return Array.from(byGrade.values()).sort((a, b) => b.final_score - a.final_score)
})

// ─── 工具函数 ────────────────────────────────────────────────────
const rowClassName = ({ row }: { row: FlagEvaluationItem }): string => {
  if (row.rank === 1) return 'row-gold'
  if (row.rank === 2) return 'row-silver'
  if (row.rank === 3) return 'row-bronze'
  return ''
}

const scoreTier = (score: number): string => {
  if (score >= 90) return 'excellent'
  if (score >= 80) return 'good'
  if (score >= 70) return 'fair'
  return 'poor'
}

// ─── 数据拉取 (含 demo 降级) ────────────────────────────────────
const fetchData = async () => {
  if (!navigator.onLine) {
    isOffline.value = true
    return
  }
  isOffline.value = false

  try {
    // 后端返回裸数组 (非对象包裹)
    const data = await getRedFlagLeaderboard({ period_type: 'week' })
    // 按 rank 排序
    leaderboard.value = (Array.isArray(data) ? data : []).sort(
      (a, b) => a.rank - b.rank,
    )
  } catch {
    // 后端不可用 → demo 数据降级
    leaderboard.value = getDemoRedFlagLeaderboard()
  }
}

// ─── 生命周期 ────────────────────────────────────────────────────
onMounted(async () => {
  await fetchData()
  // 120s 轮询刷新 (红旗排名变化较慢，降低频率)
  poller = setInterval(fetchData, 120_000)
})

onBeforeUnmount(() => {
  if (poller) clearInterval(poller)
})
</script>

<style scoped>
.flag-leaderboard {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-height: 320px;
}

/* ═══ 金旗荣誉榜 ═══ */
.flag-champions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.champion-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  background: linear-gradient(135deg, #fefce8 0%, #fef3c7 100%);
  border: 1px solid #fde68a;
  border-radius: 10px;
  flex: 1;
  min-width: 200px;
  animation: champSlide 0.6s ease both;
}

@keyframes champSlide {
  from {
    opacity: 0;
    transform: translateY(-10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.champion-flag {
  width: 44px;
  height: 44px;
  border-radius: 10px;
  background: rgba(251, 191, 36, 0.15);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.champion-body {
  flex: 1;
  min-width: 0;
}

.champion-rank-label {
  font-size: 11px;
  color: #92400e;
  font-weight: 500;
}

.champion-class {
  font-size: 16px;
  font-weight: 700;
  color: #303133;
  line-height: 1.3;
}

.champion-score {
  display: flex;
  align-items: baseline;
  gap: 2px;
}

.score-num {
  font-size: 22px;
  font-weight: 700;
  color: #d97706;
  font-family: 'DIN Alternate', sans-serif;
}

.score-unit {
  font-size: 12px;
  color: #92400e;
}

.champion-period {
  font-size: 10px;
  color: #a16207;
  background: rgba(251, 191, 36, 0.1);
  padding: 2px 6px;
  border-radius: 4px;
  align-self: flex-start;
}

/* ═══ 表格 ═══ */
.flag-table-container {
  flex: 1;
}

.table-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.table-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.table-title .el-icon {
  color: #d97706;
}

.pulse-dot {
  animation: dotPulse 1.5s ease-in-out infinite;
}

@keyframes dotPulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

/* ═══ 排名徽章 ═══ */
.rank-cell {
  display: flex;
  align-items: center;
  justify-content: center;
}

.rank-medal {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border-radius: 50%;
  font-size: 13px;
  font-weight: 700;
  color: #fff;
}

.medal-1 { background: linear-gradient(135deg, #fbbf24, #f59e0b); }
.medal-2 { background: linear-gradient(135deg, #e5e7eb, #9ca3af); }
.medal-3 { background: linear-gradient(135deg, #fb923c, #c2410c); }

.rank-num {
  font-size: 14px;
  font-weight: 600;
  color: #909399;
}

.class-name {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
}

.score-base {
  font-size: 13px;
  color: #606266;
  font-family: 'DIN Alternate', sans-serif;
}

.deduction {
  font-size: 13px;
  font-weight: 600;
  font-family: 'DIN Alternate', sans-serif;
}

.deduction.discipline { color: #ef4444; }
.deduction.attendance { color: #f59e0b; }

.deduction-zero {
  color: #c0c4cc;
  font-size: 13px;
}

.score-final {
  font-size: 16px;
  font-weight: 700;
  font-family: 'DIN Alternate', sans-serif;
}

.final-excellent { color: #10b981; }
.final-good { color: #3b82f6; }
.final-fair { color: #f59e0b; }
.final-poor { color: #ef4444; }

.score-breakdown {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.breakdown-item {
  font-size: 11px;
  color: #909399;
}

.breakdown-item strong {
  color: #606266;
  font-weight: 600;
}

/* ═══ 表格行高亮 ═══ */
:deep(.row-gold) {
  background: rgba(251, 191, 36, 0.06) !important;
}

:deep(.row-gold:hover > td) {
  background: rgba(251, 191, 36, 0.12) !important;
}

:deep(.row-silver) {
  background: rgba(156, 163, 175, 0.04) !important;
}

:deep(.row-bronze) {
  background: rgba(251, 146, 60, 0.04) !important;
}
</style>
