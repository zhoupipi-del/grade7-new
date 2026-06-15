#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ML 模型真实数据训练脚本 — 替代 heal_pipeline.py 的随机数据方案
=============================================================
核心思路:
    1. 用 FeatureExtractor 提取全校学生的 6 维真实特征
    2. 根据多维度信号自动生成风险标签（复合评分法）
    3. 用真实数据训练 sklearn/XGBoost 管道
    4. 保存到 models/ 目录供 ai_inference.py 懒加载

用法:
    本地: python train_pipeline.py
    服务器: /opt/grade7-new/venv/bin/python /opt/grade7-new/train_pipeline.py
"""
import os
import sys
import pickle
import numpy as np

# 把项目根目录加入 sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

MODELS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
PIPELINE_PATH = os.path.join(MODELS_DIR, "wings_xgb_pipeline.pkl")
METADATA_PATH = os.path.join(MODELS_DIR, "pipeline_metadata.pkl")

os.makedirs(MODELS_DIR, exist_ok=True)

# ── 特征列顺序（必须与 FeatureExtractor.INFERENCE_FEATURES 完全一致）──
FEATURE_NAMES = [
    "math_slope", "math_avg", "quality_score",
    "risk_density", "attendance_rate", "discipline_factor",
]


def generate_labels(matrix: list[dict]) -> np.ndarray:
    """
    复合评分法自动生成风险标签。

    根据学生的多维度特征，计算一个 0-100 的综合风险分，
    然后用阈值切分为 0（安全）和 1（高危）。

    评分维度（加权求和）:
        - 违纪因子 (0-100, 权重 30%) — discipline_factor 越高风险越高
        - 风险密度 (0-100, 权重 25%) — risk_density 越高风险越高
        - 成绩下降 (0-100, 权重 20%) — math_slope 越负风险越高
        - 低分 (0-100, 权重 15%) — math_avg 越低风险越高
        - 缺勤 (0-100, 权重 10%) — attendance_rate 越低风险越高

    标签阈值: 45 分 → 0=安全, 1=高危
    """
    scores = []
    for row in matrix:
        disc = row.get("discipline_factor", 0)
        density = row.get("risk_density", 0)
        slope = row.get("math_slope", 0)
        avg = row.get("math_avg", 75)
        att = row.get("attendance_rate", 1.0)

        # 各维度映射到 0-100（越高越危险）
        s_disc = min(disc * 5, 100)                          # 违纪 20分以上 → 满分
        s_dens = min(density * 8, 100)                        # 12次以上预警 → 满分
        s_slope = min(max(-slope * 4, 0), 100)              # 下降25分以上 → 满分
        s_avg = max((75 - avg) * 4, 0) if avg < 75 else 0  # 低于75分才计分
        s_att = max((1.0 - att) * 200, 0)                    # 出勤<50% → 满分

        total = s_disc * 0.30 + s_dens * 0.25 + s_slope * 0.20 + s_avg * 0.15 + s_att * 0.10
        scores.append(total)

    scores = np.array(scores)

    # 自适应阈值：确保高危比例在 15%-35%
    # 先尝试固定阈值 45
    threshold = 45.0
    high_ratio = np.mean(scores >= threshold)

    if high_ratio < 0.12:
        # 高危太少 → 降低阈值到 30 分位
        threshold = float(np.percentile(scores, 30))
    elif high_ratio > 0.40:
        # 高危太多 → 提高阈值到 65 分位
        threshold = float(np.percentile(scores, 65))

    labels = (scores >= threshold).astype(int)
    high_ratio = np.mean(labels)
    print(f"  风险分范围: [{scores.min():.1f}, {scores.max():.1f}], 均值 {scores.mean():.1f}")
    print(f"  标签阈值: {threshold:.1f}, 高危比例: {high_ratio:.1%} ({labels.sum()}/{len(labels)})")

    return labels, scores


def train_on_real_data():
    """
    用真实学生数据训练 ML 管道。
    """
    print("====== ML 管道真实数据训练 ======\n")

    # ① 初始化 Flask app（需要数据库连接）
    os.environ.setdefault("SECRET_KEY", "train-pipeline-temp")
    # 从 systemd 服务文件读取 DATABASE_URL
    _load_env_from_systemd()

    from app import create_app
    from feature_extractor import FeatureExtractor

    app = create_app()

    with app.app_context():
        # ② 获取所有年级
        from models import db, Grade
        grades = Grade.query.filter_by(is_active=True).all()
        if not grades:
            print("[ERROR] 没有找到活跃年级")
            return

        # ③ 提取所有年级的特征矩阵
        all_matrix = []
        for grade in grades:
            print(f"  提取年级 {grade.name} (ID={grade.id}) 特征...")
            fe = FeatureExtractor(grade_id=grade.id)
            matrix = fe.extract()
            print(f"    → {len(matrix)} 条学生特征")
            all_matrix.extend(matrix)

        if len(all_matrix) < 10:
            print(f"[ERROR] 学生数量太少 ({len(all_matrix)})，无法训练")
            return

        print(f"\n  合计: {len(all_matrix)} 名学生")

        # ④ 自动生成标签
        print("\n  生成风险标签（复合评分法）...")
        labels, risk_scores = generate_labels(all_matrix)

        # ⑤ 构建特征矩阵
        X = np.array([[row.get(f, 0.0) for f in FEATURE_NAMES] for row in all_matrix])
        y = labels

        # 处理 NaN / Inf
        X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

        print(f"  特征矩阵形状: {X.shape}")
        print(f"  标签分布: 安全={np.sum(y==0)}, 高危={np.sum(y==1)}")

        # ⑥ 训练模型
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler

        try:
            from xgboost import XGBClassifier
            clf = XGBClassifier(
                n_estimators=50,
                max_depth=3,
                learning_rate=0.1,
                subsample=0.8,
                colsample_bytree=0.8,
                use_label_encoder=False,
                eval_metric='logloss',
                random_state=42,
                n_jobs=1,
            )
            clf_name = "XGBoost"
        except ImportError:
            from sklearn.ensemble import GradientBoostingClassifier
            clf = GradientBoostingClassifier(
                n_estimators=50,
                max_depth=3,
                learning_rate=0.1,
                subsample=0.8,
                random_state=42,
            )
            clf_name = "GradientBoosting"

        pipeline = Pipeline([
            ('scaler', StandardScaler()),
            ('classifier', clf),
        ])

        pipeline.fit(X, y)
        print(f"\n  [OK] {clf_name} 管道训练完毕")

        # ⑦ 输出 feature_importances
        classifier = pipeline.named_steps['classifier']
        importances = classifier.feature_importances_
        print("\n  特征重要性排序:")
        for name, imp in sorted(zip(FEATURE_NAMES, importances), key=lambda x: -x[1]):
            print(f"    {name:20s}: {imp:.4f}")

        # ⑧ 校验：用训练数据预测，确认输出有区分度
        probas = pipeline.predict_proba(X)[:, 1]
        print(f"\n  预测概率统计:")
        print(f"    min={probas.min():.4f}, max={probas.max():.4f}, mean={probas.mean():.4f}, std={probas.std():.4f}")

        # ⑨ 按风险分排序，打印 Top 10 高危学生
        high_mask = y == 1
        if high_mask.any():
            high_indices = np.where(high_mask)[0]
            sorted_high = sorted(high_indices, key=lambda i: risk_scores[i], reverse=True)
            print(f"\n  Top 10 高危学生:")
            for idx in sorted_high[:10]:
                row = all_matrix[idx]
                print(f"    {row['student_name']:8s} (ID={row['student_id']}) 班级={row['class_id']} "
                      f"风险分={risk_scores[idx]:.1f} "
                      f"违纪={row['discipline_factor']:.0f} 预警={row['risk_density']} "
                      f"数学={row['math_avg']:.1f} 斜率={row['math_slope']:.1f}")

        # ⑩ 保存
        with open(PIPELINE_PATH, "wb") as f:
            pickle.dump(pipeline, f)
        print(f"\n  [OK] 模型保存: {PIPELINE_PATH}")

        metadata = {
            "model_type": f"{clf_name}-Pipeline-RealData",
            "version": "2026.06.15.RealTrain",
            "feature_names": FEATURE_NAMES,
            "passed_features": FEATURE_NAMES,
            "target_labels": ["正常/安全", "高危/预警"],
            "n_samples": len(all_matrix),
            "n_high_risk": int(y.sum()),
            "n_safe": int(len(y) - y.sum()),
            "label_threshold": 45.0,
            "mean_train_proba": round(float(probas.mean()), 4),
            "std_train_proba": round(float(probas.std()), 4),
        }
        with open(METADATA_PATH, "wb") as f:
            pickle.dump(metadata, f)
        print(f"  [OK] 元数据保存: {METADATA_PATH}")

    print(f"\n====== 训练完成！{clf_name} 已基于 {len(all_matrix)} 名学生真实数据训练 ======")


def _load_env_from_systemd():
    """从 systemd 服务文件中读取环境变量"""
    import re

    service_file = "/etc/systemd/system/grade7-new.service"
    override_file = "/etc/systemd/system/grade7-new.service.d/override.conf"

    for fpath in [override_file, service_file]:
        if os.path.exists(fpath):
            try:
                with open(fpath, "r") as f:
                    for line in f:
                        m = re.match(r'Environment\s*=\s*(.+)', line.strip())
                        if m:
                            for item in m.group(1).split():
                                if "=" in item:
                                    k, v = item.split("=", 1)
                                    if k not in os.environ:
                                        os.environ[k] = v
                print(f"  [OK] 从 {fpath} 加载环境变量")
                return
            except Exception as e:
                print(f"  [WARN] 读取 {fpath} 失败: {e}")

    # 尝试直接用已知默认值
    if "DATABASE_URL" not in os.environ:
        os.environ["DATABASE_URL"] = "mysql+pymysql://grade7:waOPKoyFf4ByQD1h@127.0.0.1:3307/grade7_new"
        print("  [OK] 使用默认 DATABASE_URL")


if __name__ == "__main__":
    train_on_real_data()
