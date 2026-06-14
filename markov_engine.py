"""
Markov Chain Event Horizon Predictor
数学学力"事件视界" - Markov链状态转移/教学熔断预警
VERSION: 3.0
  - 新增 STATE_SHORT / STATE_CSS / INTERVENTIONS 常量
  - 新增 build_global_matrix() 全局转移矩阵
  - compute_event_horizon() 新增 fall_to_s1_prob 计算与 last_score
  - scan_all_students() 支持 class_id / subject_name / top_n 参数
  - 返回字段对齐暗色模板：name, warning_state, fall_to_s1_prob, current_score, class_name, interventions
"""
import json
from datetime import datetime, timedelta
from collections import defaultdict
from models import Score, Exam, Subject, Student, Class, db

# ── 状态定义 (基于数学成绩离散化) ──
STATE_BOUNDS = [(0, 35), (36, 59), (60, 74), (75, 94), (95, 120)]

STATE_LABELS = {
    0: "危险区 (0-35分)",
    1: "薄弱区 (36-59分)",
    2: "及格区 (60-74分)",
    3: "良好区 (75-94分)",
    4: "优秀区 (95-120分)"
}

STATE_SHORT = {
    0: "S1", 1: "S2", 2: "S3", 3: "S4", 4: "S5"
}

STATE_CSS = {
    0: "danger",   # 红色 - 危险
    1: "warning",  # 橙色 - 薄弱
    2: "info",     # 蓝色 - 及格
    3: "success",  # 绿色 - 良好
    4: "primary"   # 主色 - 优秀
}

INTERVENTIONS = {
    0: {"icon": "bi-heartbeat", "title": "一对一紧急辅导", "detail": "降低作业难度，寻找知识断点，立即联系家长", "action": "物理熔断"},
    1: {"icon": "bi-book-fill", "title": "专项补漏训练", "detail": "针对薄弱知识点布置专项训练，安排小组互助", "action": "专项补漏"},
    2: {"icon": "bi-graph-up-arrow", "title": "巩固防滑落", "detail": "提高练习强度，定期跟踪，防止进一步下滑", "action": "巩固训练"},
}


def score_to_state(score):
    """将分数映射到状态 0-4"""
    if score is None:
        return None
    for i, (low, high) in enumerate(STATE_BOUNDS):
        if low <= score <= high:
            return i
    return None


def build_transition_matrix(student_id, subject_name="数学"):
    """构建学生的Markov状态转移矩阵，返回概率矩阵 + 历史状态序列 + 最近分数"""
    student = Student.query.get(student_id)
    if not student:
        return None

    subject = Subject.query.filter_by(name=subject_name).first()
    if not subject:
        return None

    scores = Score.query.filter(
        Score.student_id == student_id,
        Score.subject_id == subject.id
    ).join(Exam).order_by(Exam.exam_date.asc()).all()

    if len(scores) < 3:
        return None

    states = [score_to_state(s.score) for s in scores if score_to_state(s.score) is not None]
    raw_scores = [s.score for s in scores if score_to_state(s.score) is not None]

    if len(states) < 3:
        return None

    # 构建转移计数矩阵 (5x5)
    matrix = [[0] * 5 for _ in range(5)]
    counts = [0] * 5

    for i in range(len(states) - 1):
        from_state = states[i]
        to_state = states[i + 1]
        matrix[from_state][to_state] += 1
        counts[from_state] += 1

    # 转换为概率
    prob_matrix = []
    for i in range(5):
        if counts[i] > 0:
            row = [matrix[i][j] / counts[i] for j in range(5)]
        else:
            row = [0] * 5
        prob_matrix.append(row)

    return {
        "matrix": prob_matrix,
        "counts": counts,
        "states": states,
        "last_score": raw_scores[-1] if raw_scores else None,
        "exam_dates": [s.exam.exam_date.isoformat() for s in scores if score_to_state(s.score) is not None]
    }


def compute_event_horizon(student_id, subject_name="数学", horizon=5):
    """计算事件视界 (预测未来horizon次考试)"""
    result = build_transition_matrix(student_id, subject_name)
    if not result:
        return None

    matrix = result["matrix"]
    current_state = result["states"][-1]
    last_score = result["last_score"]

    # 预测未来horizon次考试
    predictions = []
    state = current_state

    for step in range(horizon):
        probs = matrix[state]
        predictions.append({
            "step": step + 1,
            "current_state": state,
            "probs": probs,
            "most_likely": probs.index(max(probs))
        })
        # 转移到最可能的状态
        state = probs.index(max(probs))

    # 计算短期提升概率（未来3次考试的平均提升概率）
    short_term_improve_probs = []
    for i in range(min(3, len(predictions))):
        current = predictions[i]["current_state"]
        improve_prob = sum(predictions[i]["probs"][s] for s in range(5) if s > current)
        short_term_improve_probs.append(improve_prob)

    short_term_pass_prob = sum(short_term_improve_probs) / len(short_term_improve_probs) if short_term_improve_probs else 0

    # 计算坠落至S1的概率（未来3次考试最终落入S1的累积概率）
    fall_to_s1_prob = _compute_fall_to_s1(matrix, current_state, 3)

    # 事件视界阈值 (短期通过概率 < 30%)
    event_horizon_reached = short_term_pass_prob < 0.3

    return {
        "student_id": student_id,
        "current_state": current_state,
        "current_state_label": STATE_LABELS[current_state],
        "warning_state": STATE_SHORT.get(current_state, f"S{current_state+1}"),
        "last_score": last_score,
        "predictions": predictions,
        "short_term_pass_prob": round(short_term_pass_prob, 4),
        "fall_to_s1_prob": round(fall_to_s1_prob, 4),
        "event_horizon_reached": event_horizon_reached,
        "transition_matrix": matrix
    }


def _compute_fall_to_s1(matrix, current_state, steps):
    """计算未来steps步内累积落入S1的概率 (蒙特卡洛简化版：直接概率传播)"""
    if current_state == 0:
        # 已经在S1，且根据历史数据自留概率
        return matrix[0][0]

    # 概率传播：states_after[k] = k步后各状态的概率分布
    prob_dist = [0.0] * 5
    prob_dist[current_state] = 1.0

    for _ in range(steps):
        new_dist = [0.0] * 5
        for s in range(5):
            if prob_dist[s] > 0:
                for next_s in range(5):
                    new_dist[next_s] += prob_dist[s] * matrix[s][next_s]
        prob_dist = new_dist

    return prob_dist[0]


def build_global_matrix(subject_name="数学"):
    """构建全校全局状态转移矩阵 (所有学生数据汇总)"""
    subject = Subject.query.filter_by(name=subject_name).first()
    if not subject:
        return None

    # 一次查询获取所有该科目的成绩（按考试排序）
    all_scores = Score.query.filter(
        Score.subject_id == subject.id
    ).join(Exam).order_by(Exam.exam_date.asc()).all()

    if not all_scores:
        return None

    # 按 (student_id, exam_id) 分组，提取每科每次考试的状态
    # 建立 student_id -> [(exam_id, state)] 的有序列表
    from collections import defaultdict
    student_exams = defaultdict(list)
    exam_map = {}  # exam_id -> 排序序号

    # 收集所有考试并排序
    exam_ids = sorted(set(s.exam_id for s in all_scores))
    exam_id_to_order = {eid: idx for idx, eid in enumerate(exam_ids)}

    # 按 student 分组
    for s in all_scores:
        state = score_to_state(s.score)
        if state is not None:
            student_exams[s.student_id].append((exam_id_to_order[s.exam_id], state))

    # 每个学生按考试顺序排列
    for sid in student_exams:
        student_exams[sid].sort(key=lambda x: x[0])

    # 构建全局转移矩阵
    matrix = [[0] * 5 for _ in range(5)]
    counts = [0] * 5
    total_transitions = 0

    for sid, exam_states in student_exams.items():
        states_only = [st for _, st in exam_states]
        for i in range(len(states_only) - 1):
            from_s = states_only[i]
            to_s = states_only[i + 1]
            matrix[from_s][to_s] += 1
            counts[from_s] += 1
            total_transitions += 1

    # 转概率
    prob_matrix = []
    for i in range(5):
        if counts[i] > 0:
            row = [round(matrix[i][j] / counts[i], 4) for j in range(5)]
        else:
            row = [0] * 5
        prob_matrix.append(row)

    return {
        "matrix": prob_matrix,
        "counts": counts,
        "total_transitions": total_transitions,
        "student_count": len(student_exams)
    }


def scan_all_students(class_id=None, subject_name="数学", top_n=0):
    """
    扫描所有学生，找出达到事件视界的学生。
    参数:
      - class_id: 班级ID筛选 (None=全年级)
      - subject_name: 科目 (默认"数学")
      - top_n: 返回前N名 (0=全部)
    返回:
      - list[dict]: 每个元素包含 name, warning_state, fall_to_s1_prob, current_score,
                    student_id, class_id, class_name, short_term_pass_prob, interventions
    """
    query = Student.query
    if class_id:
        query = query.filter(Student.class_id == class_id)

    students = query.all()
    warnings = []

    # 批量预加载班级名称
    class_ids = set(s.class_id for s in students if s.class_id)
    classes = Class.query.filter(Class.id.in_(class_ids)).all()
    class_map = {c.id: c.name for c in classes}

    for student in students:
        result = compute_event_horizon(student.id, subject_name)
        if result and result["event_horizon_reached"]:
            current_state = result["current_state"]
            interventions = INTERVENTIONS.get(current_state, INTERVENTIONS.get(2, {}))

            warnings.append({
                "student_id": student.id,
                "name": student.name,
                "class_id": student.class_id,
                "class_name": class_map.get(student.class_id, "未知班级"),
                "warning_state": result["warning_state"],
                "current_state": current_state,
                "current_score": result["last_score"],
                "short_term_pass_prob": result["short_term_pass_prob"],
                "fall_to_s1_prob": result["fall_to_s1_prob"],
                "interventions": interventions,
                "predictions": result["predictions"][:3]
            })

    # 按 fall_to_s1_prob 降序排序（最危险的学生排前面）
    warnings.sort(key=lambda x: x["fall_to_s1_prob"], reverse=True)

    if top_n > 0:
        warnings = warnings[:top_n]

    return warnings
