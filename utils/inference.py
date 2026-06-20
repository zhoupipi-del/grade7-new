"""
XGBoost 推理共享模块 — 从 ml_models.py + ai_inference.py 中抽离

包含:
  1. load_xgb_pipeline()         — 统一模型加载（模块级全局缓存）
  2. classify_risk_level()       — 集中化阈值分类
  3. calculate_feature_contributions()  — StandardScaler 严谨归因
  4. invalidate_model_cache()    — MLOps 热更新

特征向量 6 维 (与 feature_extractor.INFERENCE_FEATURES 对齐):
  [math_slope, math_avg, quality_score, risk_density, attendance_rate, discipline_factor]
"""

import os
import joblib
import numpy as np

# ── 模块级全局缓存 (减少 Repeated I/O) ──
_PIPELINE = None
_METADATA = None


def load_xgb_pipeline(model_dir=None):
    """懒加载 XGBoost pipeline 到内存（线程安全由 Gunicorn 保证）

    Args:
        model_dir: 模型目录路径（可选，默认从当前文件定位到项目 models/）

    Returns:
        tuple: (pipeline, metadata_dict)

    Raises:
        FileNotFoundError: 模型文件不存在时抛出
    """
    global _PIPELINE, _METADATA
    if _PIPELINE is not None:
        return _PIPELINE, _METADATA

    if model_dir is None:
        # 自动定位: utils/ → ../models/
        model_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "models"
        )

    pipeline_path = os.path.join(model_dir, "wings_xgb_pipeline.pkl")
    metadata_path = os.path.join(model_dir, "pipeline_metadata.pkl")

    if not os.path.exists(pipeline_path):
        raise FileNotFoundError(
            f"模型文件不存在: {pipeline_path}\n"
            f"请先运行: cd project_root && python model_trainer.py"
        )

    _PIPELINE = joblib.load(pipeline_path)

    if os.path.exists(metadata_path):
        _METADATA = joblib.load(metadata_path)
    else:
        # 兜底默认元数据
        _METADATA = {
            "feature_names": [
                "math_slope", "math_avg", "quality_score",
                "risk_density", "attendance_rate", "discipline_factor",
            ],
            "support_mask": [True] * 6,
            "passed_features": [
                "math_slope", "math_avg", "quality_score",
                "risk_density", "attendance_rate", "discipline_factor",
            ],
        }

    return _PIPELINE, _METADATA


def classify_risk_level(risk_prob):
    """集中化风险等级阈值分类

    规则（唯一真理源）:
      >= 0.7  → "high"
      >= 0.4  → "medium"
      else    → "low"

    Args:
        risk_prob: float, 风险概率 [0, 1]

    Returns:
        str: "high" | "medium" | "low"
    """
    if risk_prob >= 0.7:
        return "high"
    elif risk_prob >= 0.4:
        return "medium"
    else:
        return "low"


def calculate_feature_contributions(features, pipeline, passed_features):
    """Per-student 局部贡献分析（类 SHAP）

    使用 |scaled_value * importance| 归一化算法，比原始的
    feature_value * importance 更严谨（不受特征量纲影响）。

    Args:
        features: list[float], 6维特征向量
        pipeline: 加载好的 sklearn Pipeline
        passed_features: list[str], 与 features 对齐的特征名

    Returns:
        list[dict]: [{feature, importance}]  按 importance 降序, sum=1
    """
    classifier = pipeline.named_steps.get("classifier")
    if classifier is None:
        # Pipeline 中没有 classifier step → 降级返回值
        return []

    scaler = pipeline.named_steps.get("scaler")
    if scaler:
        X_scaled = scaler.transform([features])[0]
    else:
        X_scaled = np.array(features, dtype=float)

    importances = classifier.feature_importances_

    # Per-feature contribution = |scaled_value| * importance
    contributions = []
    n_factors = min(len(importances), len(passed_features))
    for i in range(n_factors):
        contrib = abs(float(X_scaled[i]) * float(importances[i]))
        contributions.append({
            "feature": passed_features[i],
            "importance": contrib,
        })

    # Normalize to sum=1
    total = sum(c["importance"] for c in contributions)
    if total > 0:
        for c in contributions:
            c["importance"] = round(c["importance"] / total, 4)

    contributions.sort(key=lambda x: -x["importance"])
    return contributions


def run_inference(features, pipeline, metadata):
    """执行完整推理 — predict_proba + 风险等级

    Args:
        features: list[float], 特征向量
        pipeline: 加载好的 sklearn Pipeline
        metadata: dict, 模型元数据

    Returns:
        dict: {risk_prob, risk_level, top_factors}
    """
    classifier = pipeline.named_steps.get("classifier")
    if classifier is None:
        return {"risk_prob": 0.0, "risk_level": "low", "top_factors": []}

    # 维度适配
    n_expected = classifier.n_features_in_
    if len(features) != n_expected:
        if len(features) > n_expected:
            features = features[:n_expected]
        else:
            features = features + [0.0] * (n_expected - len(features))

    proba = pipeline.predict_proba([features])[0]
    risk_prob = float(proba[1])

    risk_level = classify_risk_level(risk_prob)

    passed_features = metadata.get(
        "passed_features",
        metadata.get("feature_names", []),
    )
    top_factors = calculate_feature_contributions(features, pipeline, passed_features)

    # 只返回 Top 2
    return {
        "risk_prob": round(risk_prob, 4),
        "risk_level": risk_level,
        "top_factors": top_factors[:2],
    }


def invalidate_model_cache():
    """MLOps 热更新 — 失效所有内存缓存

    下次调用 load_xgb_pipeline() 时自动重新加载模型。
    被 model_retrain.py 重训完成后调用。
    """
    global _PIPELINE, _METADATA
    _PIPELINE = None
    _METADATA = None
