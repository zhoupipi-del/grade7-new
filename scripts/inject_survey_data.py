"""
注入腾讯在线问卷数据到 grade7-new 系统
- MSSMHS-55 心理健康筛查 (survey_id=26930973): 363份 → psych_surveys
- PCE-55 家长综合测评 (survey_id=26931054): 342份 → psych_surveys (survey_type=PCE-55)
"""
import json
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── 配置 ──
JSON_DIR = r"C:\Users\Administrator\AppData\Local\Temp"

# MSSMHS-55 维度映射 (题号 → 维度)  题号从1开始（问卷中第4题=心理题第1题）
MSSMHS_DIMENSIONS = {
    "强迫症状": [1, 12, 23, 34, 45],
    "偏执":     [2, 13, 24, 35, 46],
    "敌对":     [3, 14, 25, 36, 47],
    "人际敏感": [4, 15, 26, 37, 48],
    "抑郁":     [5, 16, 27, 39, 49],
    "焦虑":     [6, 17, 29, 40, 50],
    "学习压力": [7, 19, 30, 41, 51],
    "适应不良": [9, 20, 31, 42, 53],
    "情绪不平衡": [10, 21, 32, 43, 54],
    "心理不平衡": [11, 22, 33, 44, 55],
}
LIE_ITEMS = [8, 18, 28, 38, 52]  # 测谎题

# PCE-55 维度映射
PCE_DIMENSIONS = {
    "亲子参与": list(range(4, 22)),   # Q4-Q21 (问卷中第4-21题)
    "家校配合": list(range(22, 39)),  # Q22-Q38
    "家长示范": list(range(39, 56)),  # Q39-Q55
}
PCE_LIE = [4, 11, 21, 36, 53]  # PCE测谎题

OPTION_SCORE_MAP = {
    "从无": 1, "轻度": 2, "中度": 3, "偏重": 4, "严重": 5,
    "完全不符合": 1, "不太符合": 2, "一般": 3, "比较符合": 4, "完全符合": 5,
}


def parse_survey_answers(json_path, survey_type):
    """解析问卷回答JSON"""
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    answers = data.get("list", [])
    results = []

    for ans in answers:
        pages = ans.get("answer", [])
        record = {"answer_id": ans.get("answer_id"), "started_at": ans.get("started_at"),
                  "ended_at": ans.get("ended_at"), "respondent": ans.get("respondent_nickname", "")}

        # 解析所有页面
        all_qs = []
        for page in pages:
            for q in page.get("questions", []):
                all_qs.append(q)

        if len(all_qs) < 3:
            continue

        # 前3题是: 学生姓名, 班级, 学号
        name = all_qs[0].get("text", "").strip()
        class_name = all_qs[1].get("text", "").strip()
        student_no = all_qs[2].get("text", "").strip() if len(all_qs) > 2 else ""

        record["name"] = name
        record["class_name"] = class_name
        record["student_no"] = student_no

        # 评分题目（第4题开始，共55题）
        scores = []
        for i, q in enumerate(all_qs[3:58]):  # 最多55题
            score = _get_option_score(q, survey_type)
            scores.append(score)

        record["scores"] = scores
        record["total_score"] = sum(s for s in scores if s is not None)
        results.append(record)

    return results


def _get_option_score(q, survey_type):
    """从回答中提取分数"""
    opts = q.get("options", [])
    if not opts:
        return None

    for opt in opts:
        if opt.get("selected"):
            text = opt.get("text", "")
            return OPTION_SCORE_MAP.get(text, 0)
    return None


def calculate_mssmhs_dimensions(scores):
    """计算MSSMHS-55各维度得分"""
    dims = {}
    for dim_name, q_nums in MSSMHS_DIMENSIONS.items():
        dim_score = sum(scores[i-1] or 0 for i in q_nums if i-1 < len(scores) and scores[i-1] is not None)
        dims[dim_name] = dim_score

    # 测谎分
    lie_score = sum(scores[i-1] or 0 for i in LIE_ITEMS if i-1 < len(scores) and scores[i-1] is not None)

    # 总分为50题（排除测谎）
    all_dim_nums = set()
    for q_nums in MSSMHS_DIMENSIONS.values():
        all_dim_nums.update(q_nums)
    total = sum(scores[i-1] or 0 for i in all_dim_nums if i-1 < len(scores) and scores[i-1] is not None)

    # 风险等级
    is_valid = lie_score < 12  # 测谎分≥12视为无效
    if total >= 160:
        risk = "high"
    elif total >= 120:
        risk = "medium"
    else:
        risk = "low"

    return {
        "dimensions": dims,
        "lie_score": lie_score,
        "is_valid": is_valid,
        "total": total,
        "risk_level": risk,
    }


def calculate_pce_dimensions(scores):
    """计算PCE-55各维度得分"""
    dims = {}
    for dim_name, q_nums in PCE_DIMENSIONS.items():
        valid_scores = []
        for i in q_nums:
            idx = i - 1
            if idx < len(scores) and scores[idx] is not None:
                valid_scores.append(scores[idx])
        if valid_scores:
            dims[dim_name] = {"sum": sum(valid_scores), "avg": round(sum(valid_scores)/len(valid_scores), 2),
                              "count": len(valid_scores)}

    lie_score = sum(scores[i-1] or 0 for i in PCE_LIE if i-1 < len(scores) and scores[i-1] is not None)
    is_valid = lie_score < 12

    # PCE总分 (排除测谎)
    all_dim_nums = set()
    for q_nums in PCE_DIMENSIONS.values():
        all_dim_nums.update(q_nums)
    total = sum(scores[i-1] or 0 for i in all_dim_nums if i-1 < len(scores) and scores[i-1] is not None)

    return {
        "dimensions": dims,
        "lie_score": lie_score,
        "is_valid": is_valid,
        "total": total,
    }


def import_to_db():
    """连接数据库并导入"""
    from app import create_app
    from models import db, Student, PsychSurvey, Class

    app = create_app()
    with app.app_context():
        # 加载所有学生和班级
        students = {s.name.strip(): s for s in Student.query.all()}
        classes = {c.name.strip(): c for c in Class.query.all()}

        print(f"数据库: {len(students)} 学生, {len(classes)} 班级")

        stats = {"mssmhs": {"total": 0, "matched": 0, "inserted": 0, "high": 0, "medium": 0, "low": 0, "invalid": 0},
                 "pce": {"total": 0, "matched": 0, "inserted": 0}}

        # ── 处理 MSSMHS-55 ──
        print("\n" + "="*60)
        print("处理 MSSMHS-55 心理健康筛查问卷")
        print("="*60)

        mssmhs_path = os.path.join(JSON_DIR, "survey_26930973_answers_p1.json")
        records = parse_survey_answers(mssmhs_path, "mssmhs")
        stats["mssmhs"]["total"] = len(records)

        unmatched = []
        for rec in records:
            name = rec["name"]
            cls_name = rec["class_name"]
            scores = rec["scores"]

            if len(scores) < 55:
                continue

            # 匹配学生
            student = _match_student(name, cls_name, rec.get("student_no", ""), students, classes)
            if not student:
                unmatched.append(f"  {name} | {cls_name}")
                continue

            stats["mssmhs"]["matched"] += 1
            analysis = calculate_mssmhs_dimensions(scores)

            # 删除旧记录
            PsychSurvey.query.filter_by(student_id=student.id, survey_type="MSSMHS-55").delete()

            survey = PsychSurvey(
                student_id=student.id,
                class_id=student.class_id,
                grade_id=student.grade_id,
                survey_type="MSSMHS-55",
                answers_json=json.dumps({"scores": scores, "questions_55": True}, ensure_ascii=False),
                total_score=analysis["total"],
                dimensions_json=json.dumps({
                    "dimensions": analysis["dimensions"],
                    "lie_score": analysis["lie_score"],
                    "risk_level": analysis["risk_level"],
                }, ensure_ascii=False),
                is_valid=analysis["is_valid"],
                completed_at=rec.get("ended_at") or datetime.utcnow(),
            )
            db.session.add(survey)
            stats["mssmhs"]["inserted"] += 1

            if not analysis["is_valid"]:
                stats["mssmhs"]["invalid"] += 1
            else:
                stats["mssmhs"][analysis["risk_level"]] += 1

        db.session.commit()
        print(f"MSSMHS-55: 总数={stats['mssmhs']['total']}, 匹配={stats['mssmhs']['matched']}, "
              f"已插入={stats['mssmhs']['inserted']}")
        print(f"  高风险={stats['mssmhs']['high']}, 中风险={stats['mssmhs']['medium']}, "
              f"低风险={stats['mssmhs']['low']}, 无效={stats['mssmhs']['invalid']}")
        if unmatched:
            print(f"  未匹配 {len(unmatched)} 人:")
            for u in unmatched[:15]:
                print(u)
            if len(unmatched) > 15:
                print(f"  ...还有 {len(unmatched)-15} 人")

        # ── 处理 PCE-55 ──
        print("\n" + "="*60)
        print("处理 PCE-55 家长综合测评问卷")
        print("="*60)

        pce_path = os.path.join(JSON_DIR, "survey_26931054_answers_p1.json")
        records = parse_survey_answers(pce_path, "pce")
        stats["pce"]["total"] = len(records)

        unmatched = []
        for rec in records:
            name = rec["name"]
            cls_name = rec["class_name"]
            scores = rec["scores"]

            if len(scores) < 55:
                continue

            student = _match_student(name, cls_name, rec.get("student_no", ""), students, classes)
            if not student:
                unmatched.append(f"  {name} | {cls_name}")
                continue

            stats["pce"]["matched"] += 1
            analysis = calculate_pce_dimensions(scores)

            # 删除旧记录
            PsychSurvey.query.filter_by(student_id=student.id, survey_type="PCE-55").delete()

            survey = PsychSurvey(
                student_id=student.id,
                class_id=student.class_id,
                grade_id=student.grade_id,
                survey_type="PCE-55",
                answers_json=json.dumps({"scores": scores, "questions_55": True}, ensure_ascii=False),
                total_score=analysis["total"],
                dimensions_json=json.dumps({
                    "dimensions": analysis["dimensions"],
                    "lie_score": analysis["lie_score"],
                }, ensure_ascii=False),
                is_valid=analysis["is_valid"],
                completed_at=rec.get("ended_at") or datetime.utcnow(),
            )
            db.session.add(survey)
            stats["pce"]["inserted"] += 1

        db.session.commit()
        print(f"PCE-55: 总数={stats['pce']['total']}, 匹配={stats['pce']['matched']}, "
              f"已插入={stats['pce']['inserted']}")
        if unmatched:
            print(f"  未匹配 {len(unmatched)} 人:")
            for u in unmatched[:15]:
                print(u)
            if len(unmatched) > 15:
                print(f"  ...还有 {len(unmatched)-15} 人")

        # ── 汇总 ──
        print("\n" + "="*60)
        print("导入完成汇总")
        print("="*60)
        total_psych = PsychSurvey.query.count()
        mssmhs_count = PsychSurvey.query.filter_by(survey_type="MSSMHS-55").count()
        pce_count = PsychSurvey.query.filter_by(survey_type="PCE-55").count()
        print(f"psych_surveys 表总数: {total_psych}")
        print(f"  MSSMHS-55: {mssmhs_count} 条")
        print(f"  PCE-55: {pce_count} 条")

    return stats


def _match_student(name, cls_name, student_no, students, classes):
    """匹配学生：优先学号，其次姓名+班级"""
    # 清理班级名称
    cls_name_clean = cls_name.strip()
    # 尝试多种班级格式
    cls_variants = [cls_name_clean]
    if "班" in cls_name_clean:
        cls_variants.append(cls_name_clean.replace("班", ""))
    if not cls_name_clean.endswith("班"):
        cls_variants.append(cls_name_clean + "班")

    name = name.strip()

    # 1. 按学号匹配
    if student_no and student_no.strip():
        for s in students.values():
            if s.student_no and s.student_no.strip() == student_no.strip():
                return s

    # 2. 按姓名精确匹配（全校）
    exact_matches = [s for s in students.values() if s.name.strip() == name]
    if len(exact_matches) == 1:
        return exact_matches[0]
    elif len(exact_matches) > 1:
        # 多个同名，用班级区分
        for s in exact_matches:
            s_cls = s.class_rel.name if s.class_rel else ""
            if s_cls.strip() in cls_variants or cls_name_clean in s_cls:
                return s
        return exact_matches[0]  # 勉强返回第一个

    # 3. 模糊匹配
    for s in students.values():
        if name in s.name or s.name in name:
            s_cls = s.class_rel.name if s.class_rel else ""
            if s_cls.strip() in cls_variants or cls_name_clean in s_cls:
                return s

    return None


if __name__ == "__main__":
    import_to_db()
