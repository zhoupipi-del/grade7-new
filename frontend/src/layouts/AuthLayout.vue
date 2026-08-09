<template>
  <div class="auth-layout">
    <div class="auth-bg">
      <div class="auth-bg-circle circle-1"></div>
      <div class="auth-bg-circle circle-2"></div>
      <div class="auth-bg-circle circle-3"></div>
    </div>
    <router-view />
  </div>
</template>

<script setup lang="ts">
</script>

<style scoped>
.auth-layout {
  height: 100vh;
  width: 100vw;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #1f2c3f 0%, #2d3e50 50%, #1f2c3f 100%);
  position: relative;
  overflow: hidden;
}

.auth-bg {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  z-index: 0;
}

.auth-bg-circle {
  position: absolute;
  border-radius: 50%;
  opacity: 0.1;
}

.circle-1 {
  width: 400px;
  height: 400px;
  background: #1e6091;
  top: -100px;
  right: -100px;
  animation: float 8s ease-in-out infinite;
}

.circle-2 {
  width: 300px;
  height: 300px;
  background: #2a9d8f;
  bottom: -80px;
  left: -80px;
  animation: float 10s ease-in-out infinite reverse;
}

.circle-3 {
  width: 200px;
  height: 200px;
  background: #e6a23c;
  top: 40%;
  left: 50%;
  animation: float 12s ease-in-out infinite;
}

@keyframes float {
  0%, 100% { transform: translateY(0) translateX(0); }
  50% { transform: translateY(-30px) translateX(20px); }
}
</style>
