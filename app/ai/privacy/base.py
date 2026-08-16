"""WINGS AI Privacy — StudentDataProvider 抽象（Step 0）。

源: WINGS Secure Fabric BASELINE FINAL v1.0 FROZEN / Step 0 / C
"""

from abc import ABC, abstractmethod


class StudentDataProvider(ABC):
    """
    Privacy Gateway 使用的学生数据访问接口。

    Cloud 阶段：
        CloudStudentDataProvider

    Edge Secure 阶段：
        EdgeStudentDataProvider

    业务逻辑只依赖本接口，不知道数据来自 Cloud 还是 Edge。

    AD-09：
    Edge Secure 可以在 HTTPS 阶段启用，
    不依赖 Fabric Network。
    """

    @abstractmethod
    async def get_behavior_events(
        self,
        student_token: str,
        days: int = 30,
    ) -> list[dict]:
        ...

    @abstractmethod
    async def get_attendance(
        self,
        student_token: str,
        days: int = 30,
    ) -> dict:
        ...

    @abstractmethod
    async def get_grades(
        self,
        student_token: str,
        days: int = 90,
    ) -> list[dict]:
        ...

    @abstractmethod
    async def get_psych_risk(
        self,
        student_token: str,
    ) -> dict:
        """
        只返回：
        risk_level + trend + confirmed

        永远不返回：
        问卷原文
        咨询原文
        psych profile 原文
        """
        ...
