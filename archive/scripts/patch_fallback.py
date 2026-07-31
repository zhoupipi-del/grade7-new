#!/usr/bin/env python3
"""
Patch recalculate_snapshot() 添加 EvaluationScore Fallback 逻辑

当学生没有任何 EvaluationScore 记录时，使用 rule.base_score (100)
作为各维度基准分，而非强制设为 0。

用法: python3 patch_fallback.py /root/backend/modules/evaluation/services.py
"""

import sys


OLD = """        # 构建: {indicator_id: score}
        score_map = {s.indicator_id: s.score for s in scores}

        # 步骤 1: 维度内归一化加权
        raw_dim_scores = {}
        for d_key in DIMENSION_KEYS:
            subs = indicators_by_dim.get(d_key, [])
            if not subs:
                raw_dim_scores[d_key] = 0.0
                continue

            total_weight = sum(s.weight for s in subs)
            if total_weight <= 0:
                raw_dim_scores[d_key] = 0.0
                continue

            dim_total = 0.0
            for sub in subs:
                s = score_map.get(sub.id)
                if s is not None:
                    normalized_weight = sub.weight / total_weight
                    dim_total += s * normalized_weight
            raw_dim_scores[d_key] = round(dim_total, 1)

        # 步骤 2: 平衡补偿
        balanced_scores = dict(raw_dim_scores)
        non_zero = [v for v in raw_dim_scores.values() if v > 0]
        if len(non_zero) >= 2:
            avg_score = sum(non_zero) / len(non_zero)
            for d_key, d_score in balanced_scores.items():
                if d_score > avg_score * rule.balance_threshold:
                    balanced_scores[d_key] = round(d_score * rule.balance_penalty, 1)

        # 步骤 3: 一级维度加权求和
        total = 0.0
        for d_key in DIMENSION_KEYS:
            w = weights.get(d_key, 0.20)
            total += balanced_scores[d_key] * w"""

NEW = """        # 构建: {indicator_id: score}
        score_map = {s.indicator_id: s.score for s in scores}

        # Fallback: 无教师评分时使用 rule.base_score 作为各维度基准（惰性初始化）
        if not scores:
            base = float(rule.base_score)
            raw_dim_scores = {d: base for d in DIMENSION_KEYS}
            balanced_scores = dict(raw_dim_scores)
            total = 0.0
            for d_key in DIMENSION_KEYS:
                w = weights.get(d_key, 0.20)
                total += balanced_scores[d_key] * w
            total = round(total, 1)
            logger.info(
                f"[evaluation] 学生 {student_id} 无 EvaluationScore, "
                f"使用 base_score={base} 作为维度基准分, total={total}"
            )
        else:
            # 步骤 1: 维度内归一化加权
            raw_dim_scores = {}
            for d_key in DIMENSION_KEYS:
                subs = indicators_by_dim.get(d_key, [])
                if not subs:
                    raw_dim_scores[d_key] = 0.0
                    continue

                total_weight = sum(s.weight for s in subs)
                if total_weight <= 0:
                    raw_dim_scores[d_key] = 0.0
                    continue

                dim_total = 0.0
                for sub in subs:
                    s = score_map.get(sub.id)
                    if s is not None:
                        normalized_weight = sub.weight / total_weight
                        dim_total += s * normalized_weight
                raw_dim_scores[d_key] = round(dim_total, 1)

            # 步骤 2: 平衡补偿
            balanced_scores = dict(raw_dim_scores)
            non_zero = [v for v in raw_dim_scores.values() if v > 0]
            if len(non_zero) >= 2:
                avg_score = sum(non_zero) / len(non_zero)
                for d_key, d_score in balanced_scores.items():
                    if d_score > avg_score * rule.balance_threshold:
                        balanced_scores[d_key] = round(d_score * rule.balance_penalty, 1)

            # 步骤 3: 一级维度加权求和
            total = 0.0
            for d_key in DIMENSION_KEYS:
                w = weights.get(d_key, 0.20)
                total += balanced_scores[d_key] * w"""


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "/root/backend/modules/evaluation/services.py"

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    if OLD not in content:
        print("❌ 未找到目标代码段！可能已经被修改过。")
        sys.exit(1)

    content = content.replace(OLD, NEW, 1)

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

    print("✅ Fallback 补丁已写入。")


if __name__ == "__main__":
    main()
