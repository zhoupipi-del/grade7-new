"""
Data Adapter Module - 统一数据并网适配层

将不同学段 (primary/junior/senior) 的 Excel 成绩数据
通过 phase-aware 清洗管道统一并网到 Wings 3.0 数据库。

核心组件:
  - cleaner.py:    纯函数清洗引擎 (已存在)
  - services.py:   phase-aware 清洗分发器 + Excel 读取
  - routers.py:    REST API (upload-scores / templates / preview)
  - models.py:     ImportTask 导入任务记录表
  - schemas.py:    Pydantic 请求/响应模型
"""
