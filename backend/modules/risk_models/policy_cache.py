"""
policy_cache.py — policy.yaml 模块级单例缓存

消除三处独立 yaml.safe_load() 磁盘 I/O：
  - explainer.py:39      _load_policy_config()
  - services.py:41       load_policy_config()
  - policy_engine/config.py:202  PolicyConfig.from_yaml()

设计要点:
  1. 模块级单例 — 进程生命周期内首次加载后缓存
  2. mtime 校验 — policy.yaml 文件变更时自动刷新（支持热更新）
  3. 线程安全 — 双检锁 (double-checked locking) 适配 Gunicorn 多线程 worker
  4. Fail-Soft — 加载失败返回空 dict，不阻断主业务（与原有行为一致）
"""

import logging
import os
import threading

import yaml

logger = logging.getLogger(__name__)

# ── 模块级缓存状态 ──────────────────────────────────────────
_CACHE_LOCK = threading.Lock()
_cached_config: dict = {}
_cached_mtime: float = 0.0

# policy.yaml 路径（相对于本文件: modules/risk_models/policy_cache.py）
_POLICY_PATH = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "policy.yaml"))


def _load_from_disk() -> dict:
    """从磁盘加载 policy.yaml 并返回 policy_engine 区块"""
    try:
        with open(_POLICY_PATH, encoding="utf-8") as f:
            config = yaml.safe_load(f)
            return config.get("policy_engine", {}) if config else {}
    except Exception as e:
        logger.warning(f"[policy_cache] Failed to load policy.yaml: {e}")
        return {}


def _get_mtime() -> float:
    """获取 policy.yaml 的 mtime，失败返回 0.0"""
    try:
        return os.path.getmtime(_POLICY_PATH)
    except OSError:
        return 0.0


def get_policy_config() -> dict:
    """
    获取 policy_engine 配置（带 mtime 校验的模块级单例）。

    线程安全：双检锁模式，仅在缓存失效时加锁。
    热更新：policy.yaml 文件 mtime 变化时自动刷新缓存。

    Returns:
        dict: policy_engine 配置区块，加载失败时返回空 dict
    """
    global _cached_config, _cached_mtime

    # ── 快速路径：无锁检查（99% 命中）──
    current_mtime = _get_mtime()
    if current_mtime == _cached_mtime and _cached_config:
        return _cached_config

    # ── 慢速路径：加锁双检（防竞态）──
    with _CACHE_LOCK:
        # 双检：防止多个线程同时通过快速路径后重复加载
        current_mtime = _get_mtime()
        if current_mtime == _cached_mtime and _cached_config:
            return _cached_config

        # 加载并更新缓存
        _cached_config = _load_from_disk()
        _cached_mtime = current_mtime
        logger.debug(f"[policy_cache] Cache refreshed (mtime={current_mtime})")
        return _cached_config


def invalidate_cache() -> None:
    """手动清除缓存（测试/运维用）"""
    global _cached_config, _cached_mtime
    with _CACHE_LOCK:
        _cached_config = {}
        _cached_mtime = 0.0
        logger.debug("[policy_cache] Cache invalidated manually")
