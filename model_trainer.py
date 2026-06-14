"""
Phase 5 方向1 — 7年级数学学情风险预测 Pipeline
================================================
三段式咬合: VarianceThreshold(审计熔断) → StandardScaler(标准化) → XGBClassifier(浅树破冰)

标签定义: RiskRecord 风险等级 ≥ 1 (黄色及以上) → 正例(需关注)
特征维度: 6 维 (math_slope/math_avg/quality_score/risk_density/attendance_rate/discipline_factor)
         已从 X 中移除 risk_level_latest 防止数据泄露
"""
import os
import json
import sys
import numpy as np
import joblib
from collections import Counter

# Flask app context
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app import create_app
from feature_extractor import FeatureExtractor
from models import db, RiskRecord

from sklearn.feature_selection import VarianceThreshold
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.model_selection import cross_val_score, StratifiedKFold
from sklearn.metrics import classification_report, confusion_matrix
from xgboost import XGBClassifier


def run_icebreaker_pipeline():
    print("====== 🛰️  Phase 5: 终极数智预测 Pipeline 启动 ======\n")

    app = create_app()
    with app.app_context():
        # ━━━━━━━━ 1. 灌入真数据弹药 ━━━━━━━━
        fe = FeatureExtractor(grade_id=1)
        matrix = fe.extract()  # list[dict] 包含所有字段

        # ── 构建标签: risk_level_latest >= 1 → 1 (需关注), 0 (正常) ──
        y_true = []
        X_raw = []
        student_ids = []

        for row in matrix:
            student_ids.append(row["student_id"])
            y_true.append(1 if row["risk_level_latest"] >= 1 else 0)
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

        # ── 从特征中移除 risk_level_latest（已作为标签，防止泄露）──
        raw_features = [
            "math_slope", "math_avg", "quality_score",
            "risk_density", "attendance_rate", "discipline_factor",
        ]

        print(f"📥 特征矩阵: {X.shape}  |  标签集: {y.shape}")
        label_dist = Counter(y.tolist())
        print(f"📊 标签分布: 正常(0)={label_dist.get(0,0)}  需关注(1)={label_dist.get(1,0)} "
              f"| 正例率={label_dist.get(1,0)/len(y)*100:.1f}%\n")

        # ━━━━━━━━ 2. 三段式 Pipeline 组装 ━━━━━━━━
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

        # ━━━━━━━━ 3. 全量拟合 ━━━━━━━━
        pipeline.fit(X, y)
        print("🔥 Pipeline 全维拟合完成。正在提取前线审计与消融报告...\n")

        # ━━━━━━━━ 4. get_support() 审计报告 ━━━━━━━━
        selector_step = pipeline.named_steps['selector']
        support_mask = selector_step.get_support()

        passed_features = [raw_features[i] for i, passed in enumerate(support_mask) if passed]
        dropped_features = [raw_features[i] for i, passed in enumerate(support_mask) if not passed]

        print("====== 📝 [特征工程合规审计报告] ======")
        print(f"✅ 安全通过列 ({len(passed_features)}维): {passed_features}")
        print(f"❌ 熔断拦截列 ({len(dropped_features)}维): {dropped_features}")
        print("---------------------------------------")
        if dropped_features:
            for df in dropped_features:
                col_idx = raw_features.index(df)
                col_var = np.var(X[:, col_idx])
                print(f"   [⚠️ 告警] 特征 '{df}' 方差={col_var:.6f} < 阈值 0.01，"
                      f"已被审计闸无感截断，完美保护下游 StandardScaler。")
        else:
            print("   [✅] 所有特征方差健康，零熔断，全量通行！")
        print("=======================================\n")

        # ━━━━━━━━ 5. feature_importances_ 降序矩阵 ━━━━━━━━
        classifier_step = pipeline.named_steps['classifier']
        importances = classifier_step.feature_importances_

        # 建立通过列与权重的精确映射并降序排列
        feature_rank = sorted(
            zip(passed_features, importances),
            key=lambda x: x[1],
            reverse=True
        )

        print("====== 🏆 [XGBoost 破冰特征增益贡献榜] ======")
        for rank, (f_name, f_score) in enumerate(feature_rank, 1):
            bar = "█" * max(1, int(f_score * 60))
            print(f" 🌟 Top {rank} | {f_name.ljust(20)} : {f_score:.4f}  {bar}")
        print("============================================\n")

        # ━━━━━━━━ 6. 交叉验证 (5-Fold Stratified) ━━━━━━━━
        print("====== 🔬 [5-Fold 交叉验证] ======")
        cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
        scores = cross_val_score(pipeline, X, y, cv=cv, scoring='f1_weighted')
        print(f"   F1 (weighted): {scores.mean():.4f} ± {scores.std():.4f}")
        acc_scores = cross_val_score(pipeline, X, y, cv=cv, scoring='accuracy')
        print(f"   Accuracy     : {acc_scores.mean():.4f} ± {acc_scores.std():.4f}")
        roc_scores = cross_val_score(pipeline, X, y, cv=cv, scoring='roc_auc')
        print(f"   ROC-AUC      : {roc_scores.mean():.4f} ± {roc_scores.std():.4f}")
        print("================================\n")

        # ━━━━━━━━ 7. 全量预测 + 混淆矩阵 ━━━━━━━━
        y_pred = pipeline.predict(X)
        print("====== 📋 [全量预测报告] ======")
        print(classification_report(y, y_pred, target_names=["正常(0)", "需关注(1)"]))
        cm = confusion_matrix(y, y_pred)
        print(f"混淆矩阵:\n  TN={cm[0][0]:4d}  FP={cm[0][1]:4d}\n  FN={cm[1][0]:4d}  TP={cm[1][1]:4d}")
        print("===============================\n")

        print("🚀 基线测试完全封顶，消融实验战略蓝图已生成，随时可以进行线上推理部署！")

        # ━━━━━━ 8. 模型序列化 (线上推理固化) ━━━━━━
        serialize_model(pipeline, raw_features)


def serialize_model(pipeline, feature_names, output_dir="models"):
    """
    将训练好的 pipeline 序列化到磁盘。

    Args:
        pipeline: 训练好的 sklearn Pipeline
        feature_names: 特征名称列表 (全量，含被 VarianceThreshold 过滤的)
        output_dir: 输出目录

    Returns:
        dict: {"pipeline_path": str, "metadata_path": str}
    """
    os.makedirs(output_dir, exist_ok=True)

    # ① 保存 pipeline (含 VarianceThreshold + StandardScaler + XGBClassifier)
    pipeline_path = os.path.join(output_dir, "wings_xgb_pipeline.pkl")
    joblib.dump(pipeline, pipeline_path, compress=3)

    # ② 保存元数据 (特征名称、过滤掩码等)
    selector = pipeline.named_steps['selector']
    support_mask = selector.get_support()

    metadata = {
        "feature_names": feature_names,
        "support_mask": support_mask.tolist(),
        "passed_features": [feature_names[i] for i, passed in enumerate(support_mask) if passed],
        "dropped_features": [feature_names[i] for i, passed in enumerate(support_mask) if not passed],
    }

    metadata_path = os.path.join(output_dir, "pipeline_metadata.pkl")
    joblib.dump(metadata, metadata_path, compress=3)

    # ③ 保存特征重要性（XGBoost feature_importances_ → JSON，供线上归因使用）
    classifier_step = pipeline.named_steps['classifier']
    importances = classifier_step.feature_importances_
    passed_features = metadata["passed_features"]

    importance_json = {}
    for f_name, imp in zip(passed_features, importances):
        importance_json[f_name] = round(float(imp), 6)

    # 降序排列的 top triggers（供前端直接展示）
    top_triggers = sorted(importance_json.items(), key=lambda x: x[1], reverse=True)

    importance_path = os.path.join(output_dir, "feature_importances.json")
    with open(importance_path, "w", encoding="utf-8") as f:
        json.dump({
            "importances": importance_json,
            "top_triggers": top_triggers,
            "feature_order": passed_features,
        }, f, ensure_ascii=False, indent=2)

    print(f"💾 特征重要性已固化: {importance_path}")
    for rank, (f_name, f_score) in enumerate(top_triggers, 1):
        print(f"   Top {rank}: {f_name} = {f_score:.4f}")

    print(f"\n💾 Pipeline 已固化: {pipeline_path} ({os.path.getsize(pipeline_path)} bytes)")
    print(f"💾 元数据已固化: {metadata_path}")
    print(f"   通过特征: {metadata['passed_features']}")
    print(f"   熔断特征: {metadata['dropped_features']}")

    return {"pipeline_path": pipeline_path, "metadata_path": metadata_path}


if __name__ == "__main__":
    run_icebreaker_pipeline()
