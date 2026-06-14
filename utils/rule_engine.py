"""
统一规则引擎 — 集中管理所有学业预警规则
消除 ai_analysis.py 中三处重复的规则硬编码

使用方式:
    from utils.rule_engine import evaluate_rules

    warnings = evaluate_rules(student_id, today,
                               attendance_records=att_list,
                               discipline_records=disc_list,
                               score_data=score_rows,
                               leave_records=leave_list,
                               psych_survey=psych_obj,
                               mental_assessments=assessments,
                               wings_scores=wings_list,
                               problem_student=prob_stu)

每条规则返回 dict:
    {"type": str, "level": "red"|"yellow", "text": str, "suggestion": str}

新增规则只需:
    1. 写一个函数，签名 (student_id, today, **preloaded) -> list[dict]
    2. 在 RULE_REGISTRY 中注册
"""
from collections import defaultdict


# ── 规则注册表 ──
# 每条规则: {"name": str, "func": callable, "requires": set}
# requires 声明该规则需要哪些预加载数据源
RULE_REGISTRY = []


def register_rule(name, func, requires=None):
    """注册一条预警规则"""
    RULE_REGISTRY.append({
        "name": name,
        "func": func,
        "requires": requires or set(),
    })


def evaluate_rules(student_id, today, **preloaded):
    """
    统一执行所有注册的预警规则

    Args:
        student_id: 学生 ID
        today: date.today()
        **preloaded: 预加载数据源（按需传入）
            - attendance_records: list[Attendance]
            - discipline_records: list[DisciplineRecord]
            - score_data: list[dict] [{"exam_id": int, "total": float}, ...]
            - leave_records: list[LeaveRequest]
            - psych_survey: PsychSurvey 或 None
            - mental_assessments: list[MentalHealthAssessment]
            - wings_scores: list[WingsScore]
            - problem_student: ProblemStudent 或 None

    Returns:
        list[dict] — 触发的预警列表
    """
    all_warnings = []
    for rule in RULE_REGISTRY:
        try:
            # 检查所需数据源是否已预加载
            missing = rule["requires"] - set(preloaded.keys())
            if missing:
                continue  # 数据源缺失则跳过此规则
            result = rule["func"](student_id, today, **preloaded)
            if result:
                if isinstance(result, list):
                    all_warnings.extend(result)
                else:
                    all_warnings.append(result)
        except Exception:
            continue  # 单条规则失败不中断
    return all_warnings


# ══════════════════════════════════════════════════════════════
#  原有 8 条规则（从 ai_analysis.py 提取的标准化版本）
# ══════════════════════════════════════════════════════════════

def _rule_consecutive_absent(student_id, today, **kw):
    """连续缺勤 >= 3 天"""
    from datetime import timedelta
    att_list = kw.get("attendance_records", [])
    if not att_list:
        return []
    att_list = sorted(att_list, key=lambda r: r.record_date)
    max_consecutive = 0
    consecutive = 0
    last_date = None
    for r in att_list:
        if r.status == "absent":
            if last_date and (r.record_date - last_date).days <= 1:
                consecutive += 1
            else:
                consecutive = 1
            max_consecutive = max(max_consecutive, consecutive)
            last_date = r.record_date
        else:
            consecutive = 0
            last_date = None
    if max_consecutive >= 3:
        return [{"type": "consecutive_absent", "level": "red",
                  "text": "连续缺勤>=3天",
                  "suggestion": "建议立即联系家长，了解缺勤原因"}]
    return []


def _rule_monthly_absent(student_id, today, **kw):
    """本月缺勤 >= 5 次"""
    month_start = today.replace(day=1)
    att_list = kw.get("attendance_records", [])
    month_absent = sum(1 for r in att_list if r.record_date >= month_start and r.status == "absent")
    if month_absent >= 5:
        return [{"type": "monthly_absent", "level": "yellow",
                  "text": f"本月已缺勤{month_absent}次",
                  "suggestion": "建议关注学生出勤情况，必要时约谈家长"}]
    return []


def _rule_weekly_late(student_id, today, **kw):
    """本周迟到 >= 3 次"""
    from datetime import timedelta
    week_start = today - timedelta(days=today.weekday())
    att_list = kw.get("attendance_records", [])
    week_late = sum(1 for r in att_list if r.record_date >= week_start and r.status == "late")
    if week_late >= 3:
        return [{"type": "weekly_late", "level": "yellow",
                  "text": f"本周已迟到{week_late}次",
                  "suggestion": "建议加强时间观念教育"}]
    return []


def _rule_major_discipline(student_id, today, **kw):
    """重大违纪 >= 1 次"""
    disc_list = kw.get("discipline_records", [])
    major_count = sum(1 for r in disc_list if r.type == "major")
    if major_count >= 1:
        return [{"type": "major_discipline", "level": "red",
                  "text": f"有重大违纪{major_count}次",
                  "suggestion": "建议德育处介入，制定个别教育方案"}]
    return []


def _rule_serious_discipline(student_id, today, **kw):
    """严重违纪 >= 2 次"""
    disc_list = kw.get("discipline_records", [])
    serious_count = sum(1 for r in disc_list if r.type == "serious")
    if serious_count >= 2:
        return [{"type": "serious_discipline", "level": "red",
                  "text": f"严重违纪{serious_count}次",
                  "suggestion": "建议启动危机干预机制"}]
    return []


def _rule_score_drop(student_id, today, **kw):
    """两次考试总分下滑 >= 10 分"""
    scores = kw.get("score_data", [])
    if len(scores) >= 2:
        score_drop = max(0, scores[1]["total"] - scores[0]["total"])
        if score_drop >= 10:
            return [{"type": "score_drop", "level": "yellow",
                      "text": f"成绩下滑{score_drop:.1f}分",
                      "suggestion": "建议与任课教师沟通，查找学习困难原因"}]
    return []


def _rule_frequent_leave(student_id, today, **kw):
    """本月请假 >= 3 次"""
    leave_list = kw.get("leave_records", [])
    leave_count = len(leave_list)
    if leave_count >= 3:
        return [{"type": "frequent_leave", "level": "yellow",
                  "text": f"本月请假{leave_count}次",
                  "suggestion": "建议关注学生身心健康，了解请假原因"}]
    return []


def _rule_psych_survey(student_id, today, **kw):
    """MSSMHS-55 心理问卷风险"""
    psych = kw.get("psych_survey")
    warnings = []
    if psych and psych.total_score:
        if psych.total_score >= 160:
            warnings.append({
                "type": "psych_survey_high", "level": "red",
                "text": f"MSSMHS-55心理问卷高风险（{int(psych.total_score)}分）",
                "suggestion": "心理健康筛查提示高风险，建议安排心理老师个别访谈",
            })
        elif psych.total_score >= 120:
            warnings.append({
                "type": "psych_survey_medium", "level": "yellow",
                "text": f"MSSMHS-55心理问卷中风险（{int(psych.total_score)}分）",
                "suggestion": "建议班主任关注学生情绪状态，适时沟通",
            })
    return warnings


# ══════════════════════════════════════════════════════════════
#  新增增强规则 — 接入更多数据源
# ══════════════════════════════════════════════════════════════

def _rule_mental_assessment_high(student_id, today, **kw):
    """心理健康教师评估高风险（新增）"""
    assessments = kw.get("mental_assessments", [])
    high_count = sum(1 for a in assessments if a.risk_level == "high")
    if high_count >= 1:
        latest = max(assessments, key=lambda a: a.created_at or a.id) if assessments else None
        scale_name = latest.scale_name if latest else "未知量表"
        return [{"type": "mental_assess_high", "level": "red",
                  "text": f"教师心理评估高风险（{scale_name}）",
                  "suggestion": "教师评估提示需要心理干预，建议联系心理老师进行专业评估"}]
    return []


def _rule_wings_decline(student_id, today, **kw):
    """五翼评价连续下滑（新增）"""
    wings_list = kw.get("wings_scores", [])
    if not wings_list:
        return []
    # 按学期分组，取最近两个学期
    semester_map = defaultdict(list)
    for w in wings_list:
        semester_map[w.semester].append(w)
    semesters = sorted(semester_map.keys(), reverse=True)
    if len(semesters) < 2:
        return []
    curr_total = sum(w.score for w in semester_map[semesters[0]])
    prev_total = sum(w.score for w in semester_map[semesters[1]])
    if prev_total > 0:
        decline_rate = (prev_total - curr_total) / prev_total
        if decline_rate >= 0.2:  # 下滑超过20%
            return [{"type": "wings_decline", "level": "yellow",
                      "text": f"五翼评价下滑{decline_rate:.0%}（{int(prev_total)}->{int(curr_total)}）",
                      "suggestion": "综合素质评价持续走低，建议关注学生综合表现变化原因"}]
    return []


def _rule_problem_student_active(student_id, today, **kw):
    """问题学生档案红色等级（新增）"""
    prob = kw.get("problem_student")
    if prob and prob.level == "red":
        return [{"type": "problem_student_red", "level": "red",
                  "text": f"问题学生档案红色预警（{prob.category}）",
                  "suggestion": "已标记为红色问题学生，建议加强关注和干预力度"}]
    return []


def _rule_discipline_points_accumulate(student_id, today, **kw):
    """违纪扣分累积阈值（新增）"""
    disc_list = kw.get("discipline_records", [])
    total_points = sum(r.points or 0 for r in disc_list)
    if total_points >= 20:
        return [{"type": "discipline_points_high", "level": "red",
                  "text": f"违纪累计扣分{total_points}分（>=20分红线）",
                  "suggestion": "违纪积分已超红线，建议启动纪律处分程序"}]
    elif total_points >= 10:
        return [{"type": "discipline_points_warning", "level": "yellow",
                  "text": f"违纪累计扣分{total_points}分",
                  "suggestion": "违纪积分较高，建议加强行为规范教育"}]
    return []


def _rule_discipline_multi_type(student_id, today, **kw):
    """多类型违纪分散（新增）— 多种违纪类型混合为高风险"""
    disc_list = kw.get("discipline_records", [])
    categories = set(r.category for r in disc_list if r.category)
    if len(categories) >= 3:
        cat_str = "、".join(sorted(categories))
        return [{"type": "discipline_multi_type", "level": "yellow",
                  "text": f"违纪类型分散（{len(categories)}类：{cat_str}）",
                  "suggestion": "违纪类型多样，可能存在行为模式问题，建议综合评估"}]
    return []


# ══════════════════════════════════════════════════════════════
#  注册所有规则
# ══════════════════════════════════════════════════════════════

# 原有 8 条
register_rule("连续缺勤>=3天", _rule_consecutive_absent, {"attendance_records"})
register_rule("本月缺勤>=5次", _rule_monthly_absent, {"attendance_records"})
register_rule("本周迟到>=3次", _rule_weekly_late, {"attendance_records"})
register_rule("重大违纪>=1次", _rule_major_discipline, {"discipline_records"})
register_rule("严重违纪>=2次", _rule_serious_discipline, {"discipline_records"})
register_rule("成绩下滑>=10分", _rule_score_drop, {"score_data"})
register_rule("频繁请假>=3次/月", _rule_frequent_leave, {"leave_records"})
register_rule("MSSMHS-55心理问卷风险", _rule_psych_survey, {"psych_survey"})

# 新增 5 条
register_rule("教师心理评估高风险", _rule_mental_assessment_high, {"mental_assessments"})
register_rule("五翼评价连续下滑", _rule_wings_decline, {"wings_scores"})
register_rule("问题学生红色档案", _rule_problem_student_active, {"problem_student"})
register_rule("违纪扣分累积阈值", _rule_discipline_points_accumulate, {"discipline_records"})
register_rule("多类型违纪分散", _rule_discipline_multi_type, {"discipline_records"})
