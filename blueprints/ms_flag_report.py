# -*- coding: utf-8 -*-
"""
【流动红旗历史报告归档仓 (FlagArchiveReport)】
提供流动红旗评比结果的不变性物理冷冻快照，杜绝历史回溯引发的排名篡改。
归档源：已发布(published)的 FlagEvaluation 记录 → 不可变 FlagArchiveReport 快照
"""

from flask import Blueprint, request, jsonify, session
from datetime import datetime
import json

from models import db, FlagEvaluation, FlagArchiveReport, Class
from decorators import require_role, login_required
from utils import get_local_now
from utils.db_utils import safe_commit

ms_flag_report_bp = Blueprint('ms_flag_report', __name__)


# ==========================================
# 归档核心引擎 API
# ==========================================

@ms_flag_report_bp.route('/archive', methods=['POST'])
@require_role("ms_admin")
def archive_leaderboard():
    """
    【收官核心】将已发布(published)的 FlagEvaluation 数据冷冻归档为只读快照。
    归档后数据不可篡改，支持跨周期趋势分析。
    """
    req_data = request.json or request.form.to_dict() or {}
    period_type = req_data.get("period_type", "")
    period_label = req_data.get("period_label", "")
    grade_id_raw = req_data.get("grade_id")
    try:
        grade_id = int(grade_id_raw) if grade_id_raw else None
    except (ValueError, TypeError):
        grade_id = None

    if not all([period_type, period_label, grade_id]):
        return jsonify({
            "status": "error",
            "message": "缺失关键参数：period_type, period_label, grade_id"
        }), 400

    # 1. 捞取已发布的评价数据
    published_evals = FlagEvaluation.query.filter_by(
        period_type=period_type,
        period_label=period_label,
        grade_id=grade_id,
        status='published'
    ).order_by(FlagEvaluation.rank.asc()).all()

    if not published_evals:
        return jsonify({
            "status": "error",
            "message": f"未找到周期 [{period_label}] 已发布的评价数据，请先在排行榜页面点击「发布」"
        }), 404

    # 2. 检查是否已归档过（幂等防护）
    already_archived = FlagArchiveReport.query.filter_by(
        period_type=period_type,
        period_label=period_label,
        grade_id=grade_id
    ).count()
    if already_archived > 0:
        return jsonify({
            "status": "error",
            "message": f"周期 [{period_label}] 已有 {already_archived} 条归档记录，不可重复归档（历史快照不可变）"
        }), 409

    try:
        # 3. 依次生成物理快照
        archived_count = 0
        for eval_item in published_evals:
            rank_idx = eval_item.rank or (archived_count + 1)
            has_flag = rank_idx <= 2  # 年级前2名获流动红旗

            class_name = ""
            if eval_item.class_:
                class_name = eval_item.class_.name

            # 构建高保真快照
            snapshot = {
                "class_name": class_name,
                "period_label": period_label,
                "scores": {
                    "self_score": eval_item.self_score,
                    "grade_score": eval_item.grade_score,
                    "ms_score": eval_item.ms_score,
                    "self_weight": eval_item.self_weight,
                    "grade_weight": eval_item.grade_weight,
                    "ms_weight": eval_item.ms_weight,
                },
                "base_score": eval_item.base_score,
                "deductions_detail": {
                    "discipline": {
                        "minus": eval_item.discipline_deduction or 0.0,
                        "raw_points": eval_item.discipline_points or 0.0,
                    },
                    "attendance": {
                        "minus": eval_item.attendance_deduction or 0.0,
                        "exceptions_count": eval_item.attendance_exceptions or 0,
                    }
                }
            }

            report = FlagArchiveReport(
                period_type=period_type,
                period_label=period_label,
                grade_id=grade_id,
                class_id=eval_item.class_id,
                final_score=eval_item.final_score,
                rank=rank_idx,
                has_flag=has_flag,
                base_score=eval_item.base_score,
                discipline_deduction=eval_item.discipline_deduction or 0.0,
                attendance_deduction=eval_item.attendance_deduction or 0.0,
                snapshot_data_json=json.dumps(snapshot, ensure_ascii=False),
                archived_by=session.get("user_id", 1),
            )
            db.session.add(report)
            archived_count += 1

        safe_commit()

        # 统计获旗班级
        flag_classes = [e.class_.name if e.class_ else str(e.class_id)
                        for e in published_evals if (e.rank or 99) <= 2]

        return jsonify({
            "status": "success",
            "message": f"年级 [{grade_id}] 周期 [{period_label}] 评比数据已成功完成物理锁定与归档！",
            "archived_count": archived_count,
            "flag_classes": flag_classes,
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({
            "status": "error",
            "message": f"物理冷冻归档失败，事务已安全回滚: {str(e)}"
        }), 500


# ==========================================
# 趋势分析与多维对比数据管道 (API)
# ==========================================

@ms_flag_report_bp.route('/api/trends', methods=['GET'])
@login_required
def get_class_trends():
    """
    【图表赋能】获取某班级本学期历史流动红旗最终得分与排名走势。
    供前端 ECharts 折线图/柱状图消费。
    """
    class_id = request.args.get("class_id", type=int)
    if not class_id:
        return jsonify({"status": "error", "message": "参数 class_id 缺失"}), 400

    # 捞取该班级所有已完成历史归档的报告，按时间正序排列
    reports = FlagArchiveReport.query.filter_by(class_id=class_id) \
        .order_by(FlagArchiveReport.period_label.asc()).all()

    if not reports:
        return jsonify({
            "status": "success",
            "class_id": class_id,
            "trends": {
                "periods": [],
                "scores": [],
                "ranks": [],
                "total_flags_won": 0,
            }
        }), 200

    labels = [r.period_label for r in reports]
    scores = [r.final_score for r in reports]
    ranks = [r.rank for r in reports]
    flags_won = sum(1 for r in reports if r.has_flag)

    # 班级名
    class_name = reports[0].class_.name if reports[0].class_ else f"{class_id}班"

    return jsonify({
        "status": "success",
        "class_id": class_id,
        "class_name": class_name,
        "trends": {
            "periods": labels,
            "scores": scores,
            "ranks": ranks,
            "total_flags_won": flags_won,
        }
    }), 200


# ==========================================
# 归档历史查看 API
# ==========================================

@ms_flag_report_bp.route('/api/history', methods=['GET'])
@require_role("ms_admin", "grade_leader", "class_teacher")
def get_archive_history():
    """
    【历史回溯】获取指定周期的归档快照列表。
    支持按 period_type + grade_id 筛选所有已归档周期。
    """
    period_type = request.args.get("period_type", "")
    grade_id = request.args.get("grade_id", type=int)

    q = FlagArchiveReport.query
    if period_type:
        q = q.filter_by(period_type=period_type)
    if grade_id:
        q = q.filter_by(grade_id=grade_id)

    reports = q.order_by(
        FlagArchiveReport.period_label.desc(),
        FlagArchiveReport.rank.asc()
    ).all()

    if not reports:
        return jsonify({
            "status": "success",
            "reports": [],
            "message": "暂无归档历史数据"
        }), 200

    # 按周期分组
    grouped = {}
    for r in reports:
        key = f"{r.period_type}|{r.period_label}"
        if key not in grouped:
            grouped[key] = {
                "period_type": r.period_type,
                "period_label": r.period_label,
                "grade_id": r.grade_id,
                "archived_at": r.archived_at.strftime("%Y-%m-%d %H:%M") if r.archived_at else "",
                "classes": []
            }
        class_name = r.class_.name if r.class_ else f"{r.class_id}班"
        grouped[key]["classes"].append({
            "class_id": r.class_id,
            "class_name": class_name,
            "final_score": round(r.final_score, 2),
            "rank": r.rank,
            "has_flag": r.has_flag,
            "base_score": round(r.base_score, 2) if r.base_score else 0,
            "discipline_deduction": round(r.discipline_deduction or 0, 2),
            "attendance_deduction": round(r.attendance_deduction or 0, 2),
        })

    return jsonify({
        "status": "success",
        "periods": list(grouped.values()),
        "total_periods": len(grouped),
    }), 200
