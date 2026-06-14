# -*- coding: utf-8 -*-
"""grade7-new 工具函数集"""
from datetime import datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))


def get_local_now():
    """获取当前国内标准时间 (Asia/Shanghai UTC+8) — naive datetime，兼容 MySQL"""
    return datetime.now(CST).replace(tzinfo=None)
