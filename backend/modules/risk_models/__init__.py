"""
modules/risk_models/ — 风险预警雷达模块

Phase 2 核心功能:
  - RiskDeviationIndexCalculator: RDI 风险偏离指数计算器
  - SPC 统计过程控制 (EWMA + Z-Score 离群检测)
  - 三级预警系统 (🟢正常 / 🟡关注 / 🔴干预)
  - 预警抑制阈值 (防止预警疲劳)

作者: 副总指挥
日期: 2026-06-28
"""
