<template>
  <div class="timeline-event" :class="status">
    <!-- Node dot on the timeline line -->
    <div class="timeline-dot">
      <el-icon v-if="status === 'completed'" class="dot-icon"><Check /></el-icon>
      <el-icon v-else-if="status === 'active'" class="dot-icon"><Loading /></el-icon>
      <el-icon v-else class="dot-icon"><Clock /></el-icon>
    </div>

    <!-- Content card -->
    <div class="timeline-content">
      <div class="timeline-header">
        <span class="timeline-title">{{ title }}</span>
        <span class="timeline-time">{{ time }}</span>
      </div>
      <div class="timeline-body">
        <slot />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * TimelineEvent — Custom semantic timeline node.
 *
 * Props:
 *   - title: milestone title
 *   - time: date/time string
 *   - status: 'completed' | 'active' | 'pending'
 *
 * Visual states:
 *   - completed: green dot with checkmark, solid card
 *   - active: orange dot with pulse, flash-border animation on card
 *   - pending: gray dot with clock, dimmed card
 */
defineProps<{
  title: string
  time: string
  status: 'completed' | 'active' | 'pending'
}>()
</script>

<style scoped>
.timeline-event {
  position: relative;
  padding-bottom: 28px;
}

.timeline-event:last-child {
  padding-bottom: 0;
}

/* ── Dot ── */
.timeline-dot {
  position: absolute;
  left: -28px;
  top: 2px;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  border: 3px solid #fff;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 0 0 1px #dcdfe6;
}

.dot-icon {
  font-size: 8px;
  color: #fff;
}

/* ── Completed ── */
.timeline-event.completed .timeline-dot {
  background: #67c23a;
  box-shadow: 0 0 0 1px #b3e19d;
}

/* ── Active (pulsing) ── */
.timeline-event.active .timeline-dot {
  background: #e6a23c;
  box-shadow: 0 0 0 1px #f3d19e;
  animation: pulse-dot 2s ease-in-out infinite;
}

/* ── Pending ── */
.timeline-event.pending .timeline-dot {
  background: #c0c4cc;
  box-shadow: 0 0 0 1px #dcdfe6;
}

/* ── Content Card ── */
.timeline-content {
  padding: 12px 16px;
  border-radius: 8px;
  background: #f5f7fa;
  border: 1px solid #e4e7ed;
  transition: border-color 0.3s, box-shadow 0.3s;
}

.timeline-event.completed .timeline-content {
  border-left: 3px solid #67c23a;
}

.timeline-event.active .timeline-content {
  border-left: 3px solid #e6a23c;
  background: #fdf6ec;
  animation: flash-border 2s ease-in-out infinite;
}

.timeline-event.pending .timeline-content {
  border-left: 3px solid #c0c4cc;
  opacity: 0.6;
  background: #fafafa;
}

/* ── Header ── */
.timeline-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}

.timeline-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

.timeline-event.active .timeline-title {
  color: #e6a23c;
}

.timeline-event.pending .timeline-title {
  color: #909399;
}

.timeline-time {
  font-size: 12px;
  color: #909399;
  white-space: nowrap;
  margin-left: 12px;
}

/* ── Body ── */
.timeline-body {
  font-size: 13px;
  line-height: 1.6;
  color: #606266;
}

/* ── Animations ── */
@keyframes pulse-dot {
  0%, 100% {
    box-shadow: 0 0 0 1px #f3d19e, 0 0 0 0 rgba(230, 162, 60, 0.4);
  }
  50% {
    box-shadow: 0 0 0 1px #f3d19e, 0 0 0 6px rgba(230, 162, 60, 0);
  }
}

@keyframes flash-border {
  0%, 100% {
    border-color: #e4e7ed #e4e7ed #e4e7ed #e6a23c;
    box-shadow: 0 0 0 0 rgba(230, 162, 60, 0.05);
  }
  50% {
    border-color: #e4e7ed #e4e7ed #e4e7ed #e6a23c;
    box-shadow: 0 0 8px 2px rgba(230, 162, 60, 0.15);
  }
}
</style>
