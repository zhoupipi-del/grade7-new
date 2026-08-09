import { createApp } from 'vue'
import { createPinia } from 'pinia'
import piniaPluginPersistedstate from 'pinia-plugin-persistedstate'
// Element Plus: 按需加载 — AutoImport + Components resolver 处理模板组件
// ElMessage/ElMessageBox 等程序式 API 由各视图自行 import
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import 'element-plus/dist/index.css'
import VChart from 'vue-echarts'
import './utils/echarts'
import App from './App.vue'
import router from './router'
import './assets/styles/main.scss'

const app = createApp(App)

const pinia = createPinia()
pinia.use(piniaPluginPersistedstate)

for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

app.component('VChart', VChart)

app.use(pinia)
app.use(router)
// 不再 app.use(ElementPlus) — 模板组件由 unplugin-auto-import + unplugin-vue-components 按需加载

app.mount('#app')
