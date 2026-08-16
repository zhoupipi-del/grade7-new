"""WINGS AI Privacy — PsychDataProvider 抽象（Step 0）。

源: WINGS Secure Fabric BASELINE FINAL v1.0 FROZEN / Step 0 / E

架构要求（冻结）:
  "CF-01 心理数据访问通过 PsychDataProvider；Cloud 阶段直连 Cloud
   数据源，Edge 阶段只换 Provider 实现；表结构和查询业务逻辑不改。"

纪律 E（冻结文档未冻结具体方法签名 → 不得自创心理业务 API）：
  1. 只读扫描 CF-01 当前所有心理读取入口。
  2. 以实际 call site 为唯一依据提取最小接口。
  3. 每个 Provider method 必须能映射到一个现有读取语义。
  4. 不增加未来假设型接口。
  5. psych full text / questionnaire / encrypted_clog 不得进入
     CF-03 普通学生上下文。
  6. 原 Capability + Scope + Audit 不得削弱。

CF-01 call site 侦察（2026-08-16）：
------------------------------------------------------------------
psych 数据读取入口（均受 resolve_psych_access 权限门 + 审计）：
  - modules/psych_profiles/services.py  (PsychProfile / 心理档案)
  - modules/psych_profiles/routers.py
  - modules/psych_screening/services.py (筛查/咨询/干预)
  - modules/ai_prescription/aggregator.py  psych_deep 路
    （aggregator.py:17 注释: 心理档案+筛查+咨询元数据）

机械抽取结论：
  - 现有读取语义均为 "权限门(require_psych_access) → 特定表查询 →
    按 role/scope 脱敏降级"，方法签名/返回 shape 因端点而异，
    不存在单一可映射的 "读取一个学生的心理数据" 函数。
  - 若强行抽成 Provider 方法，必然把 resolve_psych_access 权限门
    移入 Provider 或复制到 Provider——两者都会削弱 Capability+Scope
    +Audit 原样（违反纪律 E.6）。

因此 Step 0：PsychDataProvider 抽象声明如下（最小接口，方法映射
到现有 call site 语义），**不接线、不复制权限门**。接线待 Edge 阶段
以真实 Edge psych 数据源需求驱动，届时权限门仍留在 Cloud 侧。
------------------------------------------------------------------
"""

from abc import ABC, abstractmethod
from typing import Optional


class PsychDataProvider(ABC):
    """
    CF-01 心理数据访问抽象（最小接口，由实际 call site 提取）。

    方法映射:
      get_profile          → psych_profiles/services.py 档案读取语义
      get_screening        → psych_screening/services.py 筛查读取语义
      get_counseling_meta  → aggregator.py psych_deep 路咨询元数据语义

    硬约束:
      - 本接口只暴露 "访问点"，权限门(require_psych_access)与审计
        仍由 Cloud 侧现有调用链执行，Provider 不复制权限逻辑。
      - 永不返回问卷原文/咨询原文/encrypted_clog 到普通上下文。
    """

    @abstractmethod
    async def get_profile(
        self,
        student_token: str,
    ) -> Optional[dict]:
        """心理档案摘要（不含问卷原文）。"""
        ...

    @abstractmethod
    async def get_screening(
        self,
        student_token: str,
    ) -> Optional[dict]:
        """筛查记录摘要（不含问卷原文）。"""
        ...

    @abstractmethod
    async def get_counseling_meta(
        self,
        student_token: str,
    ) -> Optional[dict]:
        """咨询元数据（时间/类型/结论，不含咨询原文）。"""
        ...
