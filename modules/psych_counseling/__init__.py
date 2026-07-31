"""
Psych Counseling Module — 心理咨询预约与工作台

Wings Phase 2 心理关怀板块核心主干:
  - 心理咨询可预约时间槽管理
  - 学生自荐/班主任转介双通道预约
  - 心理老师专属工作台(加密写实+风险评估)
  - Fernet 对称加密隐私切面(仅 counselor+MS_ADMIN 可解密)

核心组件:
  - models.py:   PsyConsultableSlot / PsyAppointment / PsyConsultRecord
  - services.py: 加密引擎 + 业务逻辑
  - routers.py:  14 REST API 端点
  - schemas.py:  Pydantic 请求/响应模型

安全声明:
  加密密钥从环境变量 PSY_ENCRYPTION_KEY 加载，
  生产部署前必须执行 `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
  并将生成的密钥注入系统环境。
"""
