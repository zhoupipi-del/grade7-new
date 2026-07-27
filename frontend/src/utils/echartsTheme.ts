/**
 * WINGS 品牌图表主题（Direction A：教育蓝）
 *
 * 与 `WINGS_DESIGN_TOKENS.md` §1 / §7 同源：
 *  - 分类色板采用品牌蓝绿系（§7.1），禁止每处图表手写颜色
 *  - 坐标 / 文本 / 分隔线沿用 Element token（§7.2）
 *  - 语义色与 §1.2 一致（§7.3）
 *
 * 使用方式：
 *   main.ts 中 `import './utils/echartsTheme'` 触发注册一次即可；
 *   vue-echarts 用 `<v-chart theme="wings">`，原生 echarts.init(el, 'wings')。
 */

// 与 §1.1 品牌主色梯度一致
const PRIMARY = '#1e6091'
const PRIMARY_DARK2 = '#184d74'
const PRIMARY_LIGHT3 = '#6290b2'

// §7.1 多系列分类色板（与品牌蓝绿系协调）
export const WINGS_CHART_COLORS = [
  '#1e6091', // ① 主色 深蓝
  '#2a9d8f', // ② 辅助 青绿
  '#4f86c6', // ③ 中蓝
  '#6abab1', // ④ 青绿浅
  '#e6a23c', // ⑤ 琥珀（警告语义）
  '#f56c6c', // ⑥ 红（危险语义）
  '#7a8ca3', // ⑦ 石板灰
  '#9ec7e0', // ⑧ 天蓝浅
]

// §7.2 坐标 / 文本 / 分隔
const AXIS_LINE = '#e4e9f0' // 轴线，同 --el-border-color
const SPLIT_LINE = '#f0f2f5' // 网格线，同 --el-bg-color-page
const TEXT_SECONDARY = '#52606d' // 同 --el-text-color-secondary
const TEXT_PRIMARY = '#1f2933' // 同 --el-text-color-primary

// §7.3 语义映射
const SEMANTIC = {
  success: '#67c23a',
  warning: '#e6a23c',
  danger: '#f56c6c',
  info: '#909399',
}

const wingsTheme = {
  color: WINGS_CHART_COLORS,

  backgroundColor: 'transparent',

  textStyle: {
    color: TEXT_SECONDARY,
    fontFamily:
      '-apple-system, "Segoe UI", "PingFang SC", "Microsoft YaHei", Arial, sans-serif',
  },

  title: {
    textStyle: { color: TEXT_PRIMARY, fontWeight: 600 },
    subtextStyle: { color: TEXT_SECONDARY },
  },

  // 坐标轴（直角坐标：line / bar / scatter）
  categoryAxis: {
    axisLine: { lineStyle: { color: AXIS_LINE } },
    axisTick: { lineStyle: { color: AXIS_LINE } },
    axisLabel: { color: TEXT_SECONDARY },
    splitLine: { lineStyle: { color: SPLIT_LINE } },
  },
  valueAxis: {
    axisLine: { show: true, lineStyle: { color: AXIS_LINE } },
    axisTick: { lineStyle: { color: AXIS_LINE } },
    axisLabel: { color: TEXT_SECONDARY },
    splitLine: { lineStyle: { color: SPLIT_LINE } },
  },

  // 雷达轴
  radar: {
    axisLine: { lineStyle: { color: AXIS_LINE } },
    splitLine: { lineStyle: { color: SPLIT_LINE } },
    splitArea: {
      areaStyle: { color: ['rgba(255,255,255,0)', 'rgba(244,247,250,0.6)'] },
    },
    axisName: { color: TEXT_SECONDARY },
  },

  // 图例
  legend: {
    textStyle: { color: TEXT_SECONDARY },
    inactiveColor: '#c0c4cc',
  },

  tooltip: {
    backgroundColor: 'rgba(31,41,51,0.92)',
    borderColor: 'rgba(31,41,51,0.92)',
    textStyle: { color: '#ffffff' },
    axisPointer: {
      lineStyle: { color: PRIMARY_LIGHT3 },
      crossStyle: { color: PRIMARY_LIGHT3 },
      shadowStyle: { color: 'rgba(30,96,145,0.08)' },
    },
  },

  // 标记线 / 点
  markLine: {
    lineStyle: { color: PRIMARY_DARK2 },
    label: { color: TEXT_PRIMARY },
  },
  markPoint: {
    label: { color: '#ffffff' },
    emphasis: { label: { color: '#ffffff' } },
  },

  // 系列级默认（line/bar 等强调色统一为品牌主色）
  line: {
    itemStyle: { color: PRIMARY },
    lineStyle: { color: PRIMARY },
    symbolSize: 6,
    smooth: true,
  },
  bar: {
    itemStyle: { color: PRIMARY, borderRadius: [4, 4, 0, 0] },
  },
  scatter: {
    itemStyle: { color: PRIMARY },
  },
  pie: {
    itemStyle: {
      borderColor: '#ffffff',
      borderWidth: 2,
    },
  },

  // 语义色快捷引用（供业务代码按需取用）
  semantic: SEMANTIC,
}

export default wingsTheme
