# -*- coding: utf-8 -*-
"""
MockDeYuPipeline — 高保真德育数学模型管道
供 heal_pipeline.py 和 ai_inference.py 共同引用
"""
import pickle


class MockDeYuPipeline:
    """
    模拟真实 XGBoost 的 predict_proba 行为
    对沙盘推演舱的特征微调做出确定性数学响应
    """
    def __init__(self):
        self.weights = {
            "classroom_risk_index": 0.35,
            "mental_alert_flag": 0.30,
            "wings_drop_rate": 0.20,
            "leave_frequency": 0.15
        }

    def predict_proba(self, X):
        """
        兼容 sklearn predict_proba 接口
        X: 特征字典或列表
        返回: [[安全概率, 风险概率]]
        """
        if isinstance(X, dict):
            features = [X]
        else:
            features = X

        results = []
        for item in features:
            if isinstance(item, dict):
                risk = 0.15
                for key, w in self.weights.items():
                    risk += item.get(key, 0) * w
                risk = max(0.02, min(0.98, risk))
                results.append([1.0 - risk, risk])
            else:
                results.append([0.8, 0.2])
        return results

    def predict(self, X):
        """返回类别: 0=安全, 1=预警"""
        probas = self.predict_proba(X)
        return [1 if p[1] > 0.5 else 0 for p in probas]
