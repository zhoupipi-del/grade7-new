<template>
  <div class="gaokao-placeholder">
    <el-result icon="warning" title="高考学情大盘" sub-title="高中专属模块 - 千人千面动态渲染入口">
      <template #extra>
        <el-alert
          title="该模块仅对高中学段（senior/integrated）开放，初中/小学侧边栏不可见"
          type="warning"
          :closable="false"
          show-icon
        />
        <el-descriptions :column="1" border class="meta-desc">
          <el-descriptions-item label="模块名称">高考学情大盘</el-descriptions-item>
          <el-descriptions-item label="目标学段">高中 / 完中（senior / integrated）</el-descriptions-item>
          <el-descriptions-item label="开发状态">待开发（占位页面）</el-descriptions-item>
          <el-descriptions-item label="规划功能">
            高考选科组合分析 / 一本率预测 / 学科均衡度热力图 / 强基计划推荐
          </el-descriptions-item>
        </el-descriptions>
      </template>
    </el-result>
  </div>
</template>

<script setup lang="ts">
// 高考学情大盘占位页面 — 高中学段专属入口
</script>

<style scoped>
.gaokao-placeholder {
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
