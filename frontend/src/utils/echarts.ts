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

import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { RadarChart, LineChart, BarChart, PieChart, ScatterChart } from 'echarts/charts'
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

use([
  CanvasRenderer,
  RadarChart,
  LineChart,
  BarChart,
  PieChart,
  ScatterChart,
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
