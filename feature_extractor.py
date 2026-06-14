"""
数学学情风险预测 — 特征提取管道 (Feature Extractor Pipeline)

架构理念:
    单趟扫描 + 内存聚合 — 一次 IN 查询拉出全量数据，在内存中完成
    多维度特征组装，零 N+1 穿透。复用 Phase 1-4 验证黄金模式。

数据契约 (Schema):
    | student_id | math_slope | math_avg | quality_score |
    | risk_density | risk_level_latest | attendance_rate | discipline_factor |

每条记录 = 一个学生的完整特征向量，可直接喂给 sklearn / xgboost 等模型。

用法:
    from feature_extractor import FeatureExtractor

    fe = FeatureExtractor(grade_id=1)
    matrix = fe.extract()               # → list[dict]
    csv_path = fe.export_csv("/tmp/features.csv")  # → str path
"""

import csv
from collections import defaultdict
from datetime import datetime, timedelta, date
from models import (
    db, Student, Exam, Score, Subject,
    RiskRecord, DisciplineRecord, Attendance,
    WingsScore, QualityScore,
)

# ── 数学科目 ID ──
MATH_SUBJECT_ID = 2
MATH_FULL_SCORE = 100.0

# ── 违纪类型权重 (用于 discipline_factor) ──
DISCIPLINE_WEIGHTS = {
    "warning": 1.0,   # 警告
    "minor": 3.0,     # 轻微
    "major": 10.0,    # 重大
    "serious": 20.0,  # 严重
}

# ── 风险等级数值映射 ──
RISK_LEVEL_MAP = {"green": 0, "yellow": 1, "red": 2}


class FeatureExtractor:
    """单趟扫描特征提取器 — 一个 grade 对应一个 pipeline 实例"""

    def __init__(self, grade_id: int):
        """
        Args:
            grade_id: 年级 ID（如 1 = 初一）
        """
        self.grade_id = grade_id
        self._math_subject_id = MATH_SUBJECT_ID

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  主入口: extract() — 对外唯一暴露的方法
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def extract(self) -> list[dict]:
        """
        单趟扫描主流程:
            1. 定位最近 3 次大考 → 获取 exam_ids
            2. 一条 IN 语句拉出全年级数学分 → 内存计算 slope + avg
            3. 批量拉取质量分 / 预警 / 考勤 / 违纪 → 内存聚合
            4. 组装特征矩阵并返回

        Returns:
            list[dict]: 每行一个学生 {student_id, math_slope, math_avg, ...}
        """
        # ① 获取该年级活跃学生
        students = self._fetch_students()
        if not students:
            return []

        student_ids = [s.id for s in students]
        student_map = {s.id: s for s in students}

        # ② 获取最近 3 次大考的 exam_ids（时间轴基准）
        exam_ids = self._get_recent_exam_ids(limit=3)
        if not exam_ids:
            # 暂无考试数据 — 返回带默认值的空矩阵
            return [self._make_default_row(s) for s in students]

        # ③ 单趟 IN 查询拉数学分 → 内存计算斜率 + 平均分
        math_scores = self._fetch_math_scores(student_ids, exam_ids)

        # ④ 批量拉取其他维度的原始数据
        quality_map = self._fetch_quality_scores(student_ids)
        risk_map = self._fetch_risk_data(student_ids)
        attendance_map = self._fetch_attendance(student_ids)
        discipline_map = self._fetch_discipline(student_ids)

        # ⑤ 内存组装特征矩阵
        matrix = []
        for sid in student_ids:
            row = {
                "student_id": sid,
                "student_name": student_map[sid].name,
                "class_id": student_map[sid].class_id,
                "grade_id": self.grade_id,
                # ── 学业特征 ──
                "math_slope": self._calc_slope(math_scores.get(sid, {}), exam_ids),
                "math_avg": self._calc_avg(math_scores.get(sid, {})),
                # ── 综合素质（优先 WingsScore，降级 QualityScore，兜底 80.0）──
                "quality_score": quality_map.get(sid, 80.0),
                # ── AI 预警 ──
                "risk_density": risk_map.get(sid, {}).get("density", 0),
                "risk_level_latest": risk_map.get(sid, {}).get("level", 0),
                # ── 考勤 ──
                "attendance_rate": attendance_map.get(sid, 1.0),
                # ── 违纪 ──
                "discipline_factor": discipline_map.get(sid, 0.0),
            }
            matrix.append(row)

        return matrix

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  数据抓取层 — 全是批量 IN 查询
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _fetch_students(self) -> list:
        """获取该年级所有活跃学生"""
        return Student.query.filter(
            Student.grade_id == self.grade_id,
        ).all()

    def _get_recent_exam_ids(self, limit: int = 3) -> list[int]:
        """
        获取该年级最近 N 次大考的 exam_id 序列（按日期升序 → 旧→新）

        排序: exam_date ASC 确保 exam_ids[0] = 最早, exam_ids[-1] = 最新
        """
        exams = (
            Exam.query
            .filter(Exam.grade_id == self.grade_id)
            .order_by(Exam.exam_date.desc())
            .limit(limit)
            .all()
        )
        # 反转为升序 (最早→最新)，用于 (y3 - y1) / 2 计算
        return [e.id for e in reversed(exams)]

    def _fetch_math_scores(
        self, student_ids: list[int], exam_ids: list[int]
    ) -> dict[int, dict[int, float]]:
        """
        一条 IN 语句拉出所有学生在最近 N 次考试中的数学分。

        返回: {student_id: {exam_id: score}}
        """
        rows = (
            Score.query
            .filter(
                Score.student_id.in_(student_ids),
                Score.exam_id.in_(exam_ids),
                Score.subject_id == self._math_subject_id,
                Score.verify_status == "VERIFIED",  # 只取已确认成绩
            )
            .all()
        )
        result: dict[int, dict[int, float]] = defaultdict(dict)
        for r in rows:
            result[r.student_id][r.exam_id] = float(r.score)
        return result

    def _fetch_quality_scores(self, student_ids: list[int]) -> dict[int, float]:
        """
        两级降级策略获取综合素质平衡分:
            L1: WingsScore 五维分加权平均（德智体美劳）
            L2: QualityScore 所有指标分平均（降级方案）
            L3: 80.0（硬编码默认值）

        返回: {student_id: 82.5}
        """
        # ── L1: WingsScore ──
        wings_rows = (
            WingsScore.query
            .filter(
                WingsScore.student_id.in_(student_ids),
                WingsScore.grade_id == self.grade_id,
            )
            .all()
        )
        if wings_rows:
            dim_scores: dict[int, list[float]] = defaultdict(list)
            for r in wings_rows:
                dim_scores[r.student_id].append(float(r.score))
            return {
                sid: round(sum(scores) / len(scores), 2)
                for sid, scores in dim_scores.items()
            }

        # ── L2: QualityScore ──
        quality_rows = (
            QualityScore.query
            .filter(
                QualityScore.student_id.in_(student_ids),
                QualityScore.grade_id == self.grade_id,
            )
            .all()
        )
        if quality_rows:
            q_scores: dict[int, list[float]] = defaultdict(list)
            for r in quality_rows:
                q_scores[r.student_id].append(float(r.score))
            return {
                sid: round(sum(scores) / len(scores), 2)
                for sid, scores in q_scores.items()
            }

        # ── L3: 兜底默认值 ──
        return {}

    def _fetch_risk_data(self, student_ids: list[int]) -> dict[int, dict]:
        """
        批量拉取 RiskRecord：最近 30 天预警密度 + 最新风险等级。

        返回: {student_id: {"density": 5, "level": 1}}
        """
        cutoff = datetime.utcnow() - timedelta(days=30)
        rows = (
            RiskRecord.query
            .filter(
                RiskRecord.student_id.in_(student_ids),
                RiskRecord.scan_date >= cutoff.date(),
            )
            .order_by(RiskRecord.scan_date.desc())
            .all()
        )

        # 内存聚合: 每个学生 → 计数(密度) + 最新等级
        counts: dict[int, int] = defaultdict(int)
        latest: dict[int, str] = {}
        for r in rows:
            counts[r.student_id] += 1
            if r.student_id not in latest:
                latest[r.student_id] = r.risk_level

        result = {}
        for sid in student_ids:
            result[sid] = {
                "density": counts.get(sid, 0),
                "level": RISK_LEVEL_MAP.get(latest.get(sid, "green"), 0),
            }
        return result

    def _fetch_attendance(
        self, student_ids: list[int], days: int = 30
    ) -> dict[int, float]:
        """
        批量拉取 Attendance：最近 N 天的出勤率。

        返回: {student_id: 0.95}
        """
        cutoff = date.today() - timedelta(days=days)
        rows = (
            Attendance.query
            .filter(
                Attendance.student_id.in_(student_ids),
                Attendance.record_date >= cutoff,
            )
            .all()
        )

        # 内存聚合: 每个学生 → {total, present}
        stats: dict[int, dict[str, int]] = defaultdict(lambda: {"total": 0, "present": 0})
        for r in rows:
            stats[r.student_id]["total"] += 1
            if r.status in ("present", "late", "early"):
                # 迟到/早退也算出勤（区别于旷课/请假）
                stats[r.student_id]["present"] += 1

        result = {}
        for sid in student_ids:
            s = stats.get(sid, {"total": 1, "present": 1})
            result[sid] = round(s["present"] / max(s["total"], 1), 4)
        return result

    def _fetch_discipline(self, student_ids: list[int]) -> dict[int, float]:
        """
        批量拉取 DisciplineRecord：加权违纪因子。

        返回: {student_id: 9.0}  (warning×1 + minor×3 + major×10 + serious×20)
        """
        rows = (
            DisciplineRecord.query
            .filter(
                DisciplineRecord.student_id.in_(student_ids),
                DisciplineRecord.verify_status == "VERIFIED",
            )
            .all()
        )

        # 内存聚合: 按 type 加权求和
        result: dict[int, float] = defaultdict(float)
        for r in rows:
            weight = DISCIPLINE_WEIGHTS.get(r.type, 0.0)
            result[r.student_id] += weight
        return dict(result)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  特征计算层 — 纯内存运算
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @staticmethod
    def _calc_slope(scores: dict[int, float], exam_ids: list[int]) -> float:
        """
        计算数学成绩 3 次滑动斜率。

        公式简化:
            x = [1, 2, 3]  (固定顺序)
            m = (y3 - y1) / 2

        边界处理:
            - 设考 0 次 → 0.0
            - 设考 1 次 → 0.0
            - 设考 2 次 → (y2 - y1) / 1
        """
        if len(exam_ids) == 0 or not scores:
            return 0.0

        ordered = [scores.get(eid, None) for eid in exam_ids]
        # 过滤 None
        values = [v for v in ordered if v is not None]

        if len(values) < 2:
            return 0.0  # 数据不足，斜率不可计算

        n = len(values)
        return round((values[-1] - values[0]) / (n - 1), 4)

    @staticmethod
    def _calc_avg(scores: dict[int, float]) -> float:
        """计算最近几次数学考试的平均分。"""
        if not scores:
            return 0.0
        values = list(scores.values())
        return round(sum(values) / len(values), 2)

    @staticmethod
    def _make_default_row(student) -> dict:
        """缺少考试数据时的默认特征行"""
        return {
            "student_id": student.id,
            "student_name": student.name,
            "class_id": student.class_id,
            "grade_id": student.grade_id,
            "math_slope": 0.0,
            "math_avg": 0.0,
            "quality_score": 80.0,
            "risk_density": 0,
            "risk_level_latest": 0,
            "attendance_rate": 1.0,
            "discipline_factor": 0.0,
        }

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  导出层
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    COLUMNS = [
        "student_id", "student_name", "class_id", "grade_id",
        "math_slope", "math_avg", "quality_score",
        "risk_density", "risk_level_latest",
        "attendance_rate", "discipline_factor",
    ]

    # ━━━━━━ 线上推理专用特征顺序 (与 model_trainer.py raw_features 对齐) ━━━━━━
    INFERENCE_FEATURES = [
        "math_slope", "math_avg", "quality_score",
        "risk_density", "attendance_rate", "discipline_factor",
    ]

    def get_student_vector(self, student_id: int) -> dict:
        """
        单生特征秒级聚合 — 线上推理 O(1) 专用。

        复用私有批量 IN 查询逻辑，仅拉取该学生的数据，在内存中
        组装成与 extract() 完全同构的特征字典。

        Args:
            student_id: 学生 ID

        Returns:
            dict: {
                "student_id": 123,
                "student_name": "陈佳乐",
                "class_id": 2501,
                "features": [slope, avg, quality, density, rate, discipline],
                "feature_dict": {"math_slope": -5.2, ...}  # 全量特征字典
            }

        Raises:
            ValueError: 学生不存在或不在当前 grade 中
        """
        # ① 验证学生属于当前 grade
        student = Student.query.filter(
            Student.id == student_id,
            Student.grade_id == self.grade_id,
        ).first()
        if not student:
            raise ValueError(f"Student {student_id} not found in grade {self.grade_id}")

        # ② 获取最近 3 次大考 (复用 _get_recent_exam_ids)
        exam_ids = self._get_recent_exam_ids(limit=3)

        # ③ 单生 IN 查询 (复用已有私有方法，内部已做 IN 批量)
        math_scores = self._fetch_math_scores([student_id], exam_ids)
        quality_map = self._fetch_quality_scores([student_id])
        risk_map = self._fetch_risk_data([student_id])
        attendance_map = self._fetch_attendance([student_id])
        discipline_map = self._fetch_discipline([student_id])

        # ④ 内存组装 (与 extract() L98-116 完全同构)
        feature_dict = {
            "math_slope": self._calc_slope(math_scores.get(student_id, {}), exam_ids),
            "math_avg": self._calc_avg(math_scores.get(student_id, {})),
            "quality_score": quality_map.get(student_id, 80.0),
            "risk_density": risk_map.get(student_id, {}).get("density", 0),
            "risk_level_latest": risk_map.get(student_id, {}).get("level", 0),
            "attendance_rate": attendance_map.get(student_id, 1.0),
            "discipline_factor": discipline_map.get(student_id, 0.0),
        }

        # ⑤ 按 INFERENCE_FEATURES 顺序提取向量 (6 维，不含 risk_level_latest)
        features = [feature_dict[k] for k in self.INFERENCE_FEATURES]

        return {
            "student_id": student_id,
            "student_name": student.name,
            "class_id": student.class_id,
            "features": features,
            "feature_dict": feature_dict,
        }

    def get_grade_baselines(self) -> dict:
        """
        计算年级级特征基线 (均值)，用于 evidence 偏离度计算。

        Returns:
            dict: {"math_avg": 75.2, "discipline_factor": 1.8, ...}
        """
        matrix = self.extract()
        if not matrix:
            return {}

        # 只使用 INFERENCE_FEATURES 计算基线
        baselines = {}
        n = len(matrix)
        for key in self.INFERENCE_FEATURES:
            values = [row.get(key, 0) for row in matrix if key in row]
            baselines[key] = round(sum(values) / max(len(values), 1), 4)
        return baselines

    def export_csv(self, path: str) -> str:
        """将特征矩阵导出为 CSV 文件"""
        matrix = self.extract()
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=self.COLUMNS, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(matrix)
        return path

    def export_matrix(self) -> tuple[list, list]:
        """
        导出为模型可消费的 (X, y_ids) 格式。

        Returns:
            X: 特征矩阵 list[list[float]] (不含 student_id/name/class_id/grade_id)
            y_ids: 学生 ID 列表 (与 X 行对齐)
        """
        matrix = self.extract()
        feature_keys = [
            "math_slope", "math_avg", "quality_score",
            "risk_density", "risk_level_latest",
            "attendance_rate", "discipline_factor",
        ]
        X = []
        y_ids = []
        for row in matrix:
            X.append([row[k] for k in feature_keys])
            y_ids.append(row["student_id"])
        return X, y_ids
