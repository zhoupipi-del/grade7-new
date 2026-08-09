<template>
  <div class="card-system-placeholder">
    <el-result icon="success" title="萌卡系统" sub-title="小学专属模块 - 千人千面动态渲染入口">
      <template #extra>
        <el-alert
          title="该模块仅对小学学段（primary）开放，初中/高中侧边栏不可见"
          type="success"
          :closable="false"
          show-icon
        />
        <el-descriptions :column="1" border class="meta-desc">
          <el-descriptions-item label="模块名称">萌卡系统</el-descriptions-item>
          <el-descriptions-item label="目标学段">小学（primary）</el-descriptions-item>
          <el-descriptions-item label="插件开关">enable_card</el-descriptions-item>
          <el-descriptions-item label="开发状态">待开发（占位页面）</el-descriptions-item>
        </el-descriptions>
      </template>
    </el-result>
  </div>
</template>

<script setup lang="ts">
// 萌卡系统占位页面 — 小学学段专属入口
</script>

<style scoped>
.card-system-placeholder {
  display: flex;
  justify-content: center;
  align-items: flex-start;
  padding: 40px;
}

.meta-desc {
  margin-top: 20px;
  width: 100%;
  max-width: 600px;
}
</style>
