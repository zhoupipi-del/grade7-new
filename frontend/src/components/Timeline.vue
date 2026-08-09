<template>
  <div class="custom-timeline">
    <slot />
  </div>
</template>

<script setup lang="ts">
/**
 * Timeline — Custom semantic vertical timeline container.
 *
 * Does NOT use Element Plus el-timeline. Built specifically for the
 * probation lifecycle chain rendering with flash-border animation support.
 *
 * Usage:
 *   <Timeline>
 *     <TimelineEvent title="..." time="..." status="completed">...</TimelineEvent>
 *   </Timeline>
 */
</script>

<style scoped>
.custom-timeline {
  position: relative;
  padding-left: 28px;
}

.custom-timeline::before {
  content: '';
  position: absolute;
  left: 7px;
  top: 10px;
  bottom: 10px;
  width: 2px;
  background: linear-gradient(to bottom, #dcdfe6 0%, #e4e7ed 50%, #dcdfe6 100%);
  border-radius: 1px;
}
</style>
