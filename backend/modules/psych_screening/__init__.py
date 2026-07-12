"""
Psych Screening Module — 心理筛查与干预全生命周期管理

整合旧 Flask 的 survey.py + mental_health.py，涵盖:
  - MSSMHS-55 中学生心理健康量表全流程 (答题→评分→风险定级→自动通知→AI分析)
  - 心理健康评估档案管理 (问卷/访谈/观察/家长反馈/教师反馈)
  - 绿洲干预追踪闭环 (发起干预→随访→效果评定→风险改善)
  - 十维度雷达图 + 班级对比 + AI 宏观白皮书
  - 干预时间轴可视化

核心组件:
  - models.py:   PsychSurvey / MentalHealthAssessment / MentalHealthQuestion / MentalHealthAnswer / InterventionRecord
  - services.py: 自动评分引擎 + 风险定级 + 评估同步 + 干预管理 + 维度聚合 + AI 分析 + MSSMHS-55 种子数据
  - routers.py:  18 个 REST API 端点 + 验证中间件
  - schemas.py:  Pydantic 请求/响应模型
"""
