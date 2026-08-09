/**
 * ECharts On-Demand Registration
 *
 * Only imports the chart types and components needed by Wings 3.0:
 * - RadarChart (RDI Z-Score radar)
 * - LineChart (EWMA trend)
 * - BarChart (violation statistics)
 * - PieChart (discipline distribution)
 * - ScatterChart (four-quadrant analysis)
 *
 * Components: Title, Tooltip, Legend, Grid, Radar, DataZoom, MarkLine
 */

import { use, registerTheme } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { RadarChart, LineChart, BarChart, PieChart, ScatterChart, FunnelChart } from 'echarts/charts'
import {
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  GridComponent,
  RadarComponent,
  DataZoomComponent,
  MarkLineComponent,
  MarkPointComponent,
  ToolboxComponent,
} from 'echarts/components'
import wingsTheme from './echartsTheme'

// 注册 WINGS 品牌图表主题（与 WINGS_DESIGN_TOKENS.md §7 同源）
registerTheme('wings', wingsTheme)

use([
  CanvasRenderer,
  RadarChart,
  LineChart,
  BarChart,
  PieChart,
  ScatterChart,
  FunnelChart,
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  GridComponent,
  RadarComponent,
  DataZoomComponent,
  MarkLineComponent,
  MarkPointComponent,
  ToolboxComponent,
])
