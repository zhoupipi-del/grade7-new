"""WINGS Edge Core — Connector 基类与数据契约（Step 0）。

源: WINGS Secure Fabric BASELINE FINAL v1.0 FROZEN / Step 0
本文件为冻结契约，字段/默认值/方法签名不擅自扩展。
"""

from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel


class ConnectorStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"


class HealthStatus(BaseModel):
    connector_name: str
    status: ConnectorStatus
    latency_ms: int
    last_check: datetime
    message: Optional[str] = None


class FieldDef(BaseModel):
    name: str
    data_type: str
    # string / int / float / date / datetime / boolean / json

    nullable: bool = True

    classification: str = "internal"
    # public / internal / student_pii / psych_sensitive

    storage_policy: str = "CLOUD_ALLOWED"
    # CLOUD_ALLOWED / TOKENIZED_CLOUD / EDGE_ONLY

    description: Optional[str] = None


class DataSchema(BaseModel):
    entity_type: str
    fields: list[FieldDef]
    primary_key: str
    updated_at_field: str
    supports_delta: bool = False


class DeltaBatch(BaseModel):
    entity_type: str
    records: list[dict]
    next_cursor: Optional[str] = None
    has_more: bool = False


class BaseConnector(ABC):
    """
    所有校内系统 Connector 的基类。

    Edge Core 阶段在 Edge 侧运行，通过 HTTPS 出站与 Cloud 通信。
    Edge 本身在校园 LAN 内，可直接访问校内 MySQL/HTTP/SMB。
    Edge Secure 阶段可叠加 Vault/Privacy Gateway，不改变 Connector 接口。
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Connector 唯一名称，如 sis / attendance / psych。"""
        ...

    @abstractmethod
    async def health_check(self) -> HealthStatus:
        ...

    @abstractmethod
    async def read_schema(self) -> DataSchema:
        ...

    @abstractmethod
    async def fetch_delta(
        self,
        since: datetime,
        cursor: Optional[str] = None,
    ) -> DeltaBatch:
        ...

    @abstractmethod
    async def fetch_by_id(
        self,
        entity_type: str,
        entity_id: str,
    ) -> dict:
        ...
