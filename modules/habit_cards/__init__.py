"""
Habit Cards Module - 小学虚拟萌卡激励系统

为小学学段提供游戏化卡牌激励闭环:
  - 教师端头像墙批量闪击发卡
  - AI (DeepSeek) 自动充能《高光少年家校表彰信》
  - 家长端盲盒翻牌 + 裂变分享

核心组件:
  - models.py:   HabitCard / StudentCardWallet / CardTransaction / ParentBlindboxLog
  - services.py: 发卡引擎 + AI 表彰信自动机
  - routers.py:  REST API (templates / issue / wallet / blindbox)
  - schemas.py:  Pydantic 请求/响应模型
"""
