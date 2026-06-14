"""
MLOps 自进化引擎 — 模型自动重训练 + 热更新
============================================

架构:
    触发点 (scores/discipline settlement) → 异步线程 → 
    FeatureExtractor.extract() → pipeline.fit() → 
    joblib.dump() → invalidate_model_cache() → 下次请求自动加载新模型

触发机制:
    1. 自动触发: 成绩发布 / 违纪添加 → 后台异步重训
    2. 手动触发: POST /ai-api/retrain  (仅管理员可调用)
    3. 防抖控制: 至少间隔 1 小时 (避免高频写入时反复重训)

用法:
    from utils.model_retrain import retrain_model_async, trigger_auto_retrain
    trigger_auto_retrain(current_app._get_current_object(), grade_id=1)
"""
import os
import logging
import threading
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# ── 防抖控制 — 全局最后重训时间 ──
_LAST_RETRAIN = None
_RETRAIN_LOCK = threading.Lock()
_MIN_INTERVAL = timedelta(hours=1)  # 至少间隔 1 小时


def _can_retrain() -> bool:
    """检查是否满足重训间隔要求"""
    global _LAST_RETRAIN
    with _RETRAIN_LOCK:
        if _LAST_RETRAIN is None:
            return True
        if datetime.now() - _LAST_RETRAIN >= _MIN_INTERVAL:
            return True
        return False


def _mark_retrained():
    """标记最近一次重训时间"""
    global _LAST_RETRAIN
    with _RETRAIN_LOCK:
        _LAST_RETRAIN = datetime.now()


def trigger_auto_retrain(app, grade_id=1, force=False):
    """
    自动触发重训入口 — 被 scores/discipline 蓝图调用。

    Args:
        app: Flask app 对象 (必须用 _get_current_object() 捕获避免代理问题)
        grade_id: 年级 ID
        force: 是否跳过防抖控制

    Returns:
        bool: True 表示已发起重训, False 表示被防抖拦截
    """
    if not force and not _can_retrain():
        logger.info(f"[MLOps] 重训被防抖拦截 (上次: {_LAST_RETRAIN})")
        return False

    _mark_retrained()
    thread = threading.Thread(
        target=_retrain_job,
        args=(app, grade_id),
        daemon=True,
        name="mlops-retrain",
    )
    thread.start()
    logger.info(f"[MLOps] 后台重训线程已启动 (grade_id={grade_id})")
    return True


def _retrain_job(app, grade_id):
    """
    后台重训任务 — 在独立线程中运行，不阻塞 HTTP 响应。

    流程:
        1. 创建 Flask app context
        2. FeatureExtractor 重新扫描全量数据
        3. pipeline.fit() 重新训练
        4. joblib.dump() 覆盖 .pkl 文件
        5. 失效 ai_inference 内存缓存
    """
    try:
        with app.app_context():
            import numpy as np
            from collections import Counter
            from feature_extractor import FeatureExtractor
            from sklearn.pipeline import Pipeline
            from sklearn.preprocessing import StandardScaler
            from sklearn.feature_selection import VarianceThreshold
            from xgboost import XGBClassifier
            import joblib as jl

            logger.info(f"[MLOps] 开始重训 — grade_id={grade_id}")

            # ① 提取特征矩阵
            fe = FeatureExtractor(grade_id=grade_id)
            matrix = fe.extract()
            if not matrix:
                logger.warning("[MLOps] 特征矩阵为空，跳过重训")
                return

            # ② 构建 X, y
            y_true = []
            X_raw = []
            for row in matrix:
                y_true.append(1 if row.get("risk_level_latest", 0) >= 1 else 0)
                X_raw.append([
                    row["math_slope"],
                    row["math_avg"],
                    row["quality_score"],
                    row["risk_density"],
                    row["attendance_rate"],
                    row["discipline_factor"],
                ])

            X = np.array(X_raw, dtype=np.float64)
            y = np.array(y_true, dtype=np.int32)

            raw_features = [
                "math_slope", "math_avg", "quality_score",
                "risk_density", "attendance_rate", "discipline_factor",
            ]

            label_dist = Counter(y.tolist())
            logger.info(f"[MLOps] 特征矩阵: {X.shape}, 标签: 0={label_dist.get(0,0)} 1={label_dist.get(1,0)}")

            # ③ 重新训练
            pipeline = Pipeline([
                ('selector', VarianceThreshold(threshold=0.01)),
                ('scaler', StandardScaler()),
                ('classifier', XGBClassifier(
                    max_depth=3,
                    learning_rate=0.1,
                    n_estimators=50,
                    verbosity=0,
                    random_state=42,
                    eval_metric='logloss',
                ))
            ])
            pipeline.fit(X, y)

            # ④ 序列化
            model_dir = os.path.join(app.root_path, "models")
            os.makedirs(model_dir, exist_ok=True)

            pipeline_path = os.path.join(model_dir, "wings_xgb_pipeline.pkl")
            metadata_path = os.path.join(model_dir, "pipeline_metadata.pkl")

            jl.dump(pipeline, pipeline_path, compress=3)

            selector = pipeline.named_steps['selector']
            support_mask = selector.get_support()
            metadata = {
                "feature_names": raw_features,
                "support_mask": support_mask.tolist(),
                "passed_features": [raw_features[i] for i, passed in enumerate(support_mask) if passed],
                "dropped_features": [raw_features[i] for i, passed in enumerate(support_mask) if not passed],
            }
            jl.dump(metadata, metadata_path, compress=3)

            logger.info(
                f"[MLOps] 模型已固化: {os.path.getsize(pipeline_path)} bytes, "
                f"通过特征: {metadata['passed_features']}, "
                f"熔断特征: {metadata['dropped_features']}"
            )

            # ⑤ 失效内存缓存 — 下次 API 请求自动加载新模型
            from blueprints.ai_inference import invalidate_model_cache
            invalidate_model_cache()
            logger.info("[MLOps] 内存缓存已失效，下次推理将加载新模型")

            logger.info("[MLOps] ✅ 重训完成！模型已自动热更新")

    except Exception:
        logger.exception("[MLOps] ❌ 重训失败")


# ── 状态查询 ──
def get_retrain_status() -> dict:
    """返回当前重训状态"""
    global _LAST_RETRAIN
    with _RETRAIN_LOCK:
        return {
            "last_retrain": _LAST_RETRAIN.isoformat() if _LAST_RETRAIN else None,
            "can_retrain": _can_retrain(),
        }
