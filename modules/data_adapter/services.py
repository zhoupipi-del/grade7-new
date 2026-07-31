"""
Data Adapter 服务层 — Phase-Aware 清洗分发器

职责:
  1. 模板注册表管理 (junior/senior/primary)
  2. Excel 读取 (.xlsx / .xls)
  3. 按 phase 分发清洗策略
  4. 高中选科过滤 (senior only)
"""

import io
from typing import Optional

from .cleaner import (
    CleanResult,
    CleanError,
    clean_grades_row,
    deduplicate_columns,
    ALL_TEMPLATES,
    TEMPLATE_LIJIANG_FINAL,
    TEMPLATE_LIJIANG_MIDTERM,
    TEMPLATE_LIJIANG_ROSTER,
)


# ============================================================
# 模板注册表
# ============================================================

TEMPLATE_REGISTRY = {
    "lijiang_final": TEMPLATE_LIJIANG_FINAL,
    "lijiang_midterm": TEMPLATE_LIJIANG_MIDTERM,
    "lijiang_roster": TEMPLATE_LIJIANG_ROSTER,
}

# 高中通用模板 (选科模式 — 9 学科全覆盖, 按选科映射过滤)
TEMPLATE_SENIOR_GENERIC = {
    "name": "高中通用成绩模板 (选科模式)",
    "source_type": "generic",
    "phase": "senior",
    "field_mapping": {
        "class_name": "班级",
        "student_name": "姓名",
        "subjects": {
            "语文": "语文",
            "数学": "数学",
            "英语": "英语",
            "物理": "物理",
            "化学": "化学",
            "生物": "生物",
            "政治": "道德与法治",
            "历史": "历史",
            "地理": "地理",
        },
        "total_score": "总分",
        "school_rank": "校次",
    },
    "cleaning_rules": {
        "normalize_class_name": True,
        "normalize_subject_name": True,
        "strip_name_spaces": True,
        "absent_as_null": True,
        "skip_all_absent": False,   # 高中选科 — 未选科目缺考是正常的
    },
    "error_handling": {
        "on_error": "skip",
        "max_errors": 100,
    },
}
TEMPLATE_REGISTRY["senior_generic"] = TEMPLATE_SENIOR_GENERIC


def get_all_templates() -> list[dict]:
    """返回所有模板, 附加 code 字段"""
    result = []
    for code, template in TEMPLATE_REGISTRY.items():
        result.append({**template, "code": code})
    return result


def select_template(
    phase: str,
    template_code: Optional[str] = None,
) -> tuple[str, dict]:
    """
    根据学段和模板代号选择清洗模板

    Returns: (template_code, template_dict)
    Raises:  ValueError 如果 template_code 无效
    """
    # 显式指定模板
    if template_code:
        if template_code in TEMPLATE_REGISTRY:
            return template_code, TEMPLATE_REGISTRY[template_code]
        raise ValueError(f"模板代号不存在: {template_code}")

    # 按学段自动匹配成绩模板 (排除学籍模板)
    for code, template in TEMPLATE_REGISTRY.items():
        if template.get("phase") == phase and "成绩" in template.get("name", ""):
            return code, template

    # 兜底: 该学段任意模板
    for code, template in TEMPLATE_REGISTRY.items():
        if template.get("phase") == phase:
            return code, template

    # 最终兜底
    return "lijiang_final", TEMPLATE_LIJIANG_FINAL


# ============================================================
# Excel 读取
# ============================================================

def read_excel_to_dicts(
    file_content: bytes,
    filename: str,
) -> tuple[list[str], list[dict]]:
    """
    读取 Excel 文件, 返回 (headers, rows_as_dicts)

    支持:
      .xlsx → openpyxl
      .xls  → xlrd (如果安装了)
    """
    filename_lower = filename.lower()

    if filename_lower.endswith(".xlsx"):
        try:
            import openpyxl
        except ImportError:
            raise ValueError("服务器未安装 openpyxl, 无法读取 .xlsx 文件")
        wb = openpyxl.load_workbook(
            io.BytesIO(file_content), read_only=True, data_only=True
        )
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        wb.close()

    elif filename_lower.endswith(".xls"):
        try:
            import xlrd
        except ImportError:
            raise ValueError(
                "服务器未安装 xlrd, 无法读取 .xls 文件. "
                "请将文件另存为 .xlsx 格式后重新上传"
            )
        wb = xlrd.open_workbook(file_contents=file_content)
        ws = wb.sheet_by_index(0)
        rows = [ws.row_values(i) for i in range(ws.nrows)]

    else:
        raise ValueError(f"不支持的文件格式: {filename} (仅支持 .xlsx / .xls)")

    if not rows:
        return [], []

    # 第一行作为表头
    raw_headers = [
        str(h).strip() if h is not None else f"col_{i}"
        for i, h in enumerate(rows[0])
    ]
    dedup_result = deduplicate_columns(raw_headers)

    # deduplicate_columns 返回 dict 列表, 提取 header 字符串
    # keep=False 的列设为 None, 后续跳过
    headers = []
    for item in dedup_result:
        if isinstance(item, dict):
            if item.get("keep", True):
                headers.append(item.get("header", ""))
            else:
                headers.append(None)  # 重复列, 标记跳过
        else:
            headers.append(str(item))

    # 转为 dict 列表
    data_rows = []
    for row in rows[1:]:
        row_dict = {}
        for i, val in enumerate(row):
            if i < len(headers) and headers[i] is not None:
                key = headers[i]
                if val is None:
                    row_dict[key] = ""
                elif isinstance(val, float):
                    # 浮点 → 字符串, 去掉 .0 后缀 (电话号码等)
                    if val == int(val):
                        row_dict[key] = str(int(val))
                    else:
                        row_dict[key] = str(val)
                else:
                    row_dict[key] = str(val).strip()
        data_rows.append(row_dict)

    return [h for h in headers if h is not None], data_rows


# ============================================================
# Phase-Aware 清洗分发器
# ============================================================

def process_scores(
    file_content: bytes,
    filename: str,
    phase: str,
    template_code: Optional[str] = None,
    selected_subjects: Optional[dict] = None,
    preview_only: bool = False,
    preview_rows: int = 5,
) -> tuple[str, dict, CleanResult]:
    """
    成绩清洗主管函数 (Phase-Aware)

    Args:
        file_content:       Excel 文件二进制内容
        filename:           文件名
        phase:              学段 (primary/junior/senior/integrated)
        template_code:      模板代号 (可选, 自动选择)
        selected_subjects:  选科映射 {student_name: [subject1, ...]} (高中用)
        preview_only:       仅预览前 N 行
        preview_rows:       预览行数

    Returns: (template_code, template_dict, CleanResult)
    """
    # 1. 选择模板
    code, template = select_template(phase, template_code)

    # 2. 读取 Excel
    headers, data_rows = read_excel_to_dicts(file_content, filename)

    if not data_rows:
        result = CleanResult()
        result.errors.append(CleanError(
            row=0, column="", raw_value="",
            error_type="parse_failed",
            message="Excel 文件为空或无数据行",
        ))
        return code, template, result

    # 3. 预览模式
    if preview_only:
        data_rows = data_rows[:preview_rows]

    # 4. 初始化清洗结果
    result = CleanResult()
    result.total_rows = len(data_rows)

    field_mapping = template.get("field_mapping", {})
    error_handling = template.get("error_handling", {})
    max_errors = error_handling.get("max_errors", 100)

    # 5. 逐行清洗
    for idx, raw_row in enumerate(data_rows, start=1):
        # 错误上限熔断
        if len(result.errors) >= max_errors:
            result.errors.append(CleanError(
                row=idx, column="", raw_value="",
                error_type="parse_failed",
                message=f"达到最大错误数 {max_errors}, 中止清洗",
            ))
            break

        cleaned = clean_grades_row(idx, raw_row, field_mapping, result)
        if cleaned:
            result.cleaned_data.append(cleaned)

    # 6. 高中学段: 选科过滤
    if phase == "senior" and selected_subjects:
        result = _filter_senior_subjects(result, selected_subjects)

    return code, template, result


def _filter_senior_subjects(
    result: CleanResult,
    selected_subjects: dict,
) -> CleanResult:
    """
    高中学段选科过滤

    策略:
      - 语数英为必考科目, 始终保留
      - 物理/化学/生物/政治/历史/地理 按选科映射过滤
      - 学生不在映射中 → 保留全部成绩 (兜底)
    """
    mandatory = {"语文", "数学", "英语"}

    filtered_data = []
    for row in result.cleaned_data:
        student_name = row.get("student_name", "")
        selected = selected_subjects.get(student_name)

        if selected:
            keep = set(selected) | mandatory
            row["scores"] = {
                k: v for k, v in row.get("scores", {}).items() if k in keep
            }

        filtered_data.append(row)

    result.cleaned_data = filtered_data
    return result


# ============================================================
# 工具函数
# ============================================================

def serialize_errors(errors: list, limit: int = 20) -> list[dict]:
    """将 CleanError 列表序列化为可 JSON 化的 dict"""
    result = []
    for err in errors[:limit]:
        if isinstance(err, CleanError):
            result.append({
                "row": err.row,
                "column": err.column,
                "raw_value": str(err.raw_value)[:100],
                "error_type": err.error_type.value
                if hasattr(err.error_type, "value")
                else str(err.error_type),
                "message": err.message,
            })
        elif isinstance(err, dict):
            result.append(err)
    return result


# ============================================================
# 新高考 "3+1+2" 等级赋分核心自动机 (Scaling Engine)
# ============================================================

import pandas as pd
import numpy as np


def compute_new_gaokao_scaled_scores(df_subject_scores: pd.DataFrame) -> pd.DataFrame:
    """
    【新高考等级赋分核心自动机】

    输入: 包含某个单科考试大盘的 DataFrame，必须包含 ['student_id', 'raw_score', 'is_absent']
    输出: 扩充了 ['cohort_rank', 'cohort_total', 'percentile', 'grade_level', 'scaled_score'] 的 DataFrame

    五级标准:
      A: 前15%     → 86~100分
      B: 16%~50%  → 71~85分
      C: 51%~85%  → 56~70分
      D: 86%~98%  → 41~55分
      E: 倒数2%   → 30~40分

    核心公式 (线性插值):
      Y = Y1 + (Y2 - Y1) * (X - Xmin) / (Xmax - Xmin)
    """
    # 1. 深度拷贝，防止污染原始数据
    df = df_subject_scores.copy()

    # 2. 剥离缺考样本，缺考不参与大盘排名与赋分比例计算
    df_active = df[df['is_absent'] == False].copy()
    df_absent = df[df['is_absent'] == True].copy()

    total_active = len(df_active)
    if total_active == 0:
        # 如果全员缺考，直接返回原样
        df['cohort_rank'] = None
        df['cohort_total'] = 0
        df['percentile'] = None
        df['grade_level'] = None
        df['scaled_score'] = None
        return df

    # 3. 计算绝对排名 (使用 min 模式，同分并列同名次，如 1, 2, 2, 4)
    # 并强制按原始分降序排列
    df_active['cohort_rank'] = df_active['raw_score'].rank(method='min', ascending=False).astype(int)
    df_active['cohort_total'] = total_active

    # 4. 计算百分比排位 (当前名次 / 总有效人数)
    df_active['percentile'] = df_active['cohort_rank'] / total_active

    # 5. 定义新高考五级标准区间箱
    # 阈值：A<=15%, B<=50%, C<=85%, D<=98%, E<=100%
    GRADE_BOXES = [
        {"level": "A", "upper_pct": 0.15, "y_min": 86, "y_max": 100},
        {"level": "B", "upper_pct": 0.50, "y_min": 71, "y_max": 85},
        {"level": "C", "upper_pct": 0.85, "y_min": 56, "y_max": 70},
        {"level": "D", "upper_pct": 0.98, "y_min": 41, "y_max": 55},
        {"level": "E", "upper_pct": 1.00, "y_min": 30, "y_max": 40},
    ]

    # 6. 打上等级标签 (Grade Level)
    def assign_grade_level(pct):
        for box in GRADE_BOXES:
            if pct <= box["upper_pct"]:
                return box["level"]
        return "E"

    df_active['grade_level'] = df_active['percentile'].apply(assign_grade_level)

    # 7. 级联核心：分等级区间执行【线性插值算法】
    df_active['scaled_score'] = np.nan  # 初始化赋分列

    for box in GRADE_BOXES:
        level = box["level"]
        y_min, y_max = box["y_min"], box["y_max"]

        # 捞出当前等级区间内的所有学生
        mask = df_active['grade_level'] == level
        df_level = df_active[mask]

        if df_level.empty:
            continue

        # 抓取当前等级内，全大盘学生中暴露出的最大原始分和最小原始分
        x_max = df_level['raw_score'].max()
        x_min = df_level['raw_score'].min()

        # 边界防御：如果这个等级内所有人的原始分一模一样 (x_max == x_min)，防止除以 0 导致溢出
        if x_max == x_min:
            df_active.loc[mask, 'scaled_score'] = y_max
        else:
            # 🚀 拍入标准新高考插值公式
            raw_scores = df_level['raw_score']
            scaled_vals = y_min + ((y_max - y_min) * (raw_scores - x_min)) / (x_max - x_min)
            # 四舍五入取整并落盘
            df_active.loc[mask, 'scaled_score'] = np.round(scaled_vals).astype(int)

    # 8. 合并缺考数据，保持数据集完整性
    if not df_absent.empty:
        df_absent['cohort_rank'] = None
        df_absent['cohort_total'] = total_active
        df_absent['percentile'] = None
        df_absent['grade_level'] = None
        df_absent['scaled_score'] = None
        df_result = pd.concat([df_active, df_absent])
    else:
        df_result = df_active

    return df_result


# ============================================================
# 必考/首选科目: 只算排名, 不赋分
# ============================================================

def _compute_ranking_only(df_engine_input: pd.DataFrame) -> pd.DataFrame:
    """语数英/物理/历史: 只算 cohort_rank + percentile, scaled_score = None"""
    df = df_engine_input.copy()
    df_active = df[df['is_absent'] == False].copy()
    df_absent = df[df['is_absent'] == True].copy()

    total_active = len(df_active)
    if total_active == 0:
        df['cohort_rank'] = None
        df['cohort_total'] = 0
        df['percentile'] = None
        df['grade_level'] = None
        df['scaled_score'] = None
        return df

    df_active['cohort_rank'] = df_active['raw_score'].rank(method='min', ascending=False).astype(int)
    df_active['cohort_total'] = total_active
    df_active['percentile'] = df_active['cohort_rank'] / total_active
    df_active['grade_level'] = None
    df_active['scaled_score'] = None

    if not df_absent.empty:
        df_absent['cohort_rank'] = None
        df_absent['cohort_total'] = total_active
        df_absent['percentile'] = None
        df_absent['grade_level'] = None
        df_absent['scaled_score'] = None
        df_result = pd.concat([df_active, df_absent])
    else:
        df_result = df_active

    return df_result


# ============================================================
# 科目中英文映射
# ============================================================

SUBJECT_CN_TO_CODE = {
    "语文": "chinese",
    "数学": "math",
    "英语": "english",
    "物理": "physics",
    "历史": "history",
    "化学": "chemistry",
    "生物": "biology",
    "道德与法治": "politics",
    "地理": "geography",
}

# 再选科目 — 需要赋分
SCALED_SUBJECTS = {"chemistry", "biology", "politics", "geography"}


# ============================================================
# 辅助: 解析或自动创建班级
# ============================================================

async def _resolve_or_create_classes(
    db,
    school_id: int,
    cleaned_data: list[dict],
) -> dict[str, int]:
    """返回 {class_name: class_id}, 不存在的班级自动创建"""
    from sqlalchemy import select
    from core.models import Class, Grade

    class_names = set()
    for item in cleaned_data:
        name = item.get("class_name", "")
        if name:
            class_names.add(name)

    if not class_names:
        return {}

    result = await db.execute(
        select(Class.id, Class.name).where(
            Class.school_id == school_id,
            Class.name.in_(class_names),
        )
    )
    name_to_id = {row.name: row.id for row in result}

    missing = class_names - set(name_to_id.keys())
    if missing:
        grade_result = await db.execute(
            select(Grade.id).where(Grade.school_id == school_id).limit(1)
        )
        grade_row = grade_result.first()
        if grade_row:
            grade_id = grade_row.id
        else:
            new_grade = Grade(
                name="高中", school_id=school_id, sort_order=1, is_active=True
            )
            db.add(new_grade)
            await db.flush()
            grade_id = new_grade.id

        for name in missing:
            new_class = Class(name=name, school_id=school_id, grade_id=grade_id)
            db.add(new_class)
            await db.flush()
            name_to_id[name] = new_class.id

    return name_to_id


# ============================================================
# 辅助: 解析或自动创建学生
# ============================================================

async def _resolve_or_create_students(
    db,
    school_id: int,
    class_name_to_id: dict[str, int],
    cleaned_data: list[dict],
) -> dict[str, int]:
    """返回 {student_name: student_id}, 不存在的学生自动创建"""
    import time
    from sqlalchemy import select
    from core.models import Student, Class

    student_names = set()
    for item in cleaned_data:
        name = item.get("student_name", "")
        if name:
            student_names.add(name)

    if not student_names:
        return {}

    result = await db.execute(
        select(Student.id, Student.name).where(
            Student.school_id == school_id,
            Student.name.in_(student_names),
        )
    )
    name_to_id = {row.name: row.id for row in result}

    timestamp = int(time.time() * 1000) % 1000000
    counter = 0
    for item in cleaned_data:
        name = item.get("student_name", "")
        if not name or name in name_to_id:
            continue

        class_name = item.get("class_name", "")
        class_id = class_name_to_id.get(class_name)
        if not class_id:
            continue

        class_result = await db.execute(
            select(Class.grade_id).where(Class.id == class_id)
        )
        class_row = class_result.first()
        grade_id = class_row.grade_id if class_row else None

        counter += 1
        student_no = f"A{school_id}{timestamp}{counter:03d}"

        new_student = Student(
            name=name,
            student_no=student_no,
            school_id=school_id,
            class_id=class_id,
            grade_id=grade_id,
        )
        db.add(new_student)
        await db.flush()
        name_to_id[name] = new_student.id

    return name_to_id


# ============================================================
# 新高考统一全流道落盘管道 (async)
# ============================================================

async def process_and_save_senior_scores_pipeline(
    db,
    exam_id: int,
    school_id: int,
    cleaned_data: list[dict],
) -> dict:
    """
    【新高考统一全流道落盘管道】

    输入: cleaner 清洗后的 cleaned_data (list[dict])
    动作:
      1. 解析/自动创建班级和学生
      2. 按学科拆表 -> 跑赋分/排名自动机
      3. 批量落盘到 exam_grades_detail
    返回: {subject_code: {total, active}} 汇总
    """
    from sqlalchemy import delete as sa_delete
    from .models import ExamGradesDetail

    # 1. 解析/创建班级和学生
    class_name_to_id = await _resolve_or_create_classes(db, school_id, cleaned_data)
    student_name_to_id = await _resolve_or_create_students(
        db, school_id, class_name_to_id, cleaned_data
    )

    # 2. 构建长格式 DataFrame (每行 = 一个学生 x 一个学科)
    rows = []
    for item in cleaned_data:
        student_name = item.get("student_name", "")
        class_name = item.get("class_name", "")
        student_id = student_name_to_id.get(student_name)
        class_id = class_name_to_id.get(class_name)

        if not student_id or not class_id:
            continue

        for subject_cn, score in item.get("scores", {}).items():
            subject_code = SUBJECT_CN_TO_CODE.get(subject_cn)
            if not subject_code:
                continue

            is_absent = score is None
            rows.append({
                "student_id": student_id,
                "admin_class_id": class_id,
                "subject_code": subject_code,
                "raw_score": float(score) if score is not None else 0.0,
                "is_absent": is_absent,
            })

    if not rows:
        return {"error": "no data to persist"}

    df_cleaned = pd.DataFrame(rows)

    # 3. 按学科拆表, 逐个跑自动机
    all_records = []
    summary = {}

    for subject_code in df_cleaned["subject_code"].unique():
        df_sub = df_cleaned[df_cleaned["subject_code"] == subject_code].copy()

        df_engine_input = pd.DataFrame({
            "student_id": df_sub["student_id"].values,
            "raw_score": df_sub["raw_score"].values,
            "is_absent": df_sub["is_absent"].values,
        })

        if subject_code in SCALED_SUBJECTS:
            df_engine_output = compute_new_gaokao_scaled_scores(df_engine_input)
        else:
            df_engine_output = _compute_ranking_only(df_engine_input)

        df_final = df_sub[["student_id", "admin_class_id"]].merge(
            df_engine_output, on="student_id", how="left"
        )

        for _, row in df_final.iterrows():
            record = ExamGradesDetail(
                exam_id=exam_id,
                student_id=int(row["student_id"]),
                school_id=school_id,
                admin_class_id=int(row["admin_class_id"]),
                teaching_class_id=None,
                subject_code=subject_code,
                raw_score=float(row["raw_score"]) if not row["is_absent"] else 0.0,
                scaled_score=float(row["scaled_score"]) if pd.notna(row.get("scaled_score")) else None,
                is_absent=bool(row["is_absent"]),
                cohort_rank=int(row["cohort_rank"]) if pd.notna(row.get("cohort_rank")) else None,
                cohort_total=int(row["cohort_total"]) if pd.notna(row.get("cohort_total")) else None,
                percentile=float(row["percentile"]) if pd.notna(row.get("percentile")) else None,
                grade_level=row.get("grade_level") if pd.notna(row.get("grade_level")) else None,
            )
            all_records.append(record)

        active_count = int(len(df_sub[~df_sub["is_absent"]]))
        summary[subject_code] = {"total": len(df_sub), "active": active_count}

    # 4. 批量落盘 (先删旧数据保证幂等, 再批量插入)
    if all_records:
        await db.execute(
            sa_delete(ExamGradesDetail).where(
                ExamGradesDetail.exam_id == exam_id,
                ExamGradesDetail.school_id == school_id,
            )
        )
        db.add_all(all_records)
        await db.commit()

    return summary


# ============================================================
# 全校大盘 Z-Score 热力图矩阵引擎 (宏观战役 #1392)
# ============================================================

async def calculate_exam_zscore_matrix(db, exam_id: int, school_id: int) -> dict:
    """
    【全校大盘 Z-Score 强弱热力图矩阵引擎】

    流程:
      1. 从 exam_grades_detail 捞出全量有效成绩 (剔除缺考)
      2. 按学科算全校大盘均值(Mean)与标准差(Std)
      3. 逐条算个人单科 Z-Score = (X - μ) / σ
      4. 按班级×学科联合分组, 求班级平均 Z-Score
      5. 组装 ECharts Heatmap 三元组 [class_idx, subject_idx, z_score]

    返回:
      classes:         班级名称列表
      class_ids:       班级ID列表
      subjects:        学科代码列表
      matrix_data:     [[c_idx, s_idx, z_score], ...]
      global_subject_stats: {subject: {mean, std}}
    """
    from sqlalchemy import select
    from .models import ExamGradesDetail
    from core.models import Class

    # 1. 查全量有效成绩 (非缺考)
    stmt = select(
        ExamGradesDetail.admin_class_id,
        ExamGradesDetail.subject_code,
        ExamGradesDetail.raw_score,
    ).where(
        ExamGradesDetail.exam_id == exam_id,
        ExamGradesDetail.school_id == school_id,
        ExamGradesDetail.is_absent == False,  # noqa: E712
    )
    result = await db.execute(stmt)
    rows = result.fetchall()

    if not rows:
        return {
            "classes": [],
            "class_ids": [],
            "subjects": [],
            "matrix_data": [],
            "global_subject_stats": {},
        }

    # 转 DataFrame
    df_records = pd.DataFrame(
        rows, columns=["admin_class_id", "subject_code", "raw_score"]
    )
    df_records["raw_score"] = df_records["raw_score"].astype(float)

    # 2. 全校大盘级别: 学科均值与标准差
    group_stats = (
        df_records.groupby("subject_code")["raw_score"]
        .agg(["mean", "std"])
        .to_dict("index")
    )

    # 3. 级联计算每个学生的个人单科 Z-Score
    def compute_row_z(row):
        sub = row["subject_code"]
        score = row["raw_score"]
        if sub in group_stats:
            sub_mean = group_stats[sub]["mean"]
            sub_std = group_stats[sub]["std"]
            if sub_std == 0 or pd.isna(sub_std):
                return 0.0
            return (score - sub_mean) / sub_std
        return 0.0

    df_records["z_score"] = df_records.apply(compute_row_z, axis=1)

    # 4. 核心聚合: 按班级 × 学科 联合分组, 求班级平均 Z-Score
    df_matrix = (
        df_records.groupby(["admin_class_id", "subject_code"])["z_score"]
        .mean()
        .reset_index()
    )

    # 5. 提取去重的班级轴与学科轴
    unique_class_ids = sorted([int(cid) for cid in df_matrix["admin_class_id"].unique()])
    unique_subjects = sorted([str(sub) for sub in df_matrix["subject_code"].unique()])

    # 6. 查班级名称
    class_stmt = select(Class.id, Class.name).where(
        Class.id.in_(unique_class_ids)
    )
    class_result = await db.execute(class_stmt)
    class_id_to_name = {row.id: row.name for row in class_result}

    # 兜底: 没查到的用 ID
    for cid in unique_class_ids:
        if cid not in class_id_to_name:
            class_id_to_name[cid] = f"班级ID:{cid}"

    # 7. 组装 ECharts Heatmap 三元组
    matrix_data = []
    for _, row in df_matrix.iterrows():
        c_idx = unique_class_ids.index(int(row["admin_class_id"]))
        s_idx = unique_subjects.index(str(row["subject_code"]))
        z_val = round(float(row["z_score"]), 3)
        if z_val == 0:
            z_val = 0.0  # 消除 -0.0
        matrix_data.append([
            c_idx,
            s_idx,
            z_val,
        ])

    return {
        "classes": [class_id_to_name[cid] for cid in unique_class_ids],
        "class_ids": unique_class_ids,
        "subjects": unique_subjects,
        "matrix_data": matrix_data,
        "global_subject_stats": {
            sub: {"mean": round(stats["mean"], 2), "std": round(stats["std"], 2)}
            for sub, stats in group_stats.items()
            if not pd.isna(stats["std"])
        },
    }


# ============================================================
# RDI 跨周期血缘追溯与风险触发自动机 (Task #1395)
# ============================================================

async def execute_rdi_risk_analysis_pipeline(
    db,
    exam_id: int,
    school_id: int,
) -> dict:
    """
    【RDI 跨周期血缘追溯与风险触发自动机】

    流程:
      1. 异步拉取该场大考当前学校的所有有效成绩 (剔除缺考)
      2. Pandas 重构全校大盘各学科 μ(均值) 与 σ(标准差)
      3. 逐条计算个人单科 Z-Score = (X - μ) / σ
      4. 阈值拦截: Z ≤ -1.5 → 红灯, -1.5 < Z ≤ -1.0 → 黄灯
      5. 为每个危重样本组装 3 层血缘 DAG JSON
      6. 幂等 DELETE-BEFORE-INSERT 批量落盘到 student_risk_alerts

    返回:
      {status, alerts_triggered, red_count, yellow_count, msg}
    """
    from sqlalchemy import select, delete
    from .models import ExamGradesDetail, StudentRiskAlert

    # 1. 异步拉取全量有效成绩
    stmt = select(
        ExamGradesDetail.student_id,
        ExamGradesDetail.admin_class_id,
        ExamGradesDetail.subject_code,
        ExamGradesDetail.raw_score,
        ExamGradesDetail.scaled_score,
        ExamGradesDetail.cohort_rank,
        ExamGradesDetail.percentile,
        ExamGradesDetail.grade_level,
    ).where(
        ExamGradesDetail.exam_id == exam_id,
        ExamGradesDetail.school_id == school_id,
        ExamGradesDetail.is_absent == False,  # noqa: E712
    )
    result = await db.execute(stmt)
    records = result.mappings().all()

    if not records:
        return {
            "status": "skipped",
            "reason": "未检索到有效的并网学生成绩，血缘自动机挂起",
            "alerts_triggered": 0,
        }

    # 2. 组装 Pandas 矩阵 + 动态推算全校大盘统计标尺
    df = pd.DataFrame(records)
    df["raw_score"] = df["raw_score"].astype(float)

    stats_map = (
        df.groupby("subject_code")["raw_score"]
        .agg(["mean", "std"])
        .to_dict("index")
    )

    # 3. 级联计算个人 Z-Score
    def _get_individual_z(row):
        sub = row["subject_code"]
        if sub in stats_map:
            mu = stats_map[sub]["mean"]
            sigma = stats_map[sub]["std"]
            if sigma > 0 and not pd.isna(sigma):
                return (row["raw_score"] - mu) / sigma
        return 0.0

    df["z_score"] = df.apply(_get_individual_z, axis=1)

    # 4. 阈值拦截: Z ≤ -1.0 触发预警
    df_alerts = df[df["z_score"] <= -1.0].copy()

    if df_alerts.empty:
        return {
            "status": "success",
            "alerts_triggered": 0,
            "msg": "大盘安全，无红黄灯学业危机样本触发",
        }

    # 4.5 按学生聚合: 一个学生一场大考一条预警 (匹配唯一键 uk_student_exam_risk)
    # 每个学生可能有多个学科触发预警, 全部收入同一个 lineage_graph
    grouped = df_alerts.groupby("student_id")

    new_alert_objects = []
    red_count = 0
    yellow_count = 0

    for stu_id, stu_df in grouped:
        stu_id = int(stu_id)
        class_id_val = int(stu_df["admin_class_id"].iloc[0])

        # 取该生所有触发学科, 按 Z-Score 升序 (最差的排前面)
        stu_df = stu_df.sort_values("z_score")

        # 风险等级: 只要有任一学科 Z ≤ -1.5 → 红灯, 否则黄灯
        worst_z = float(stu_df["z_score"].min())
        risk_level = "red" if worst_z <= -1.5 else "yellow"
        if risk_level == "red":
            red_count += 1
            level_cn = "重度红灯"
        else:
            yellow_count += 1
            level_cn = "中度黄灯"

        # 组装触发原因摘要 (列出所有触发的学科)
        subject_reasons = []
        for _, row in stu_df.iterrows():
            sub_code = str(row["subject_code"])
            z_val = round(float(row["z_score"]), 3)
            if z_val == 0:
                z_val = 0.0
            subject_reasons.append(f"[{sub_code}] Z={z_val}")

        reason = (
            f"在本次大考中，学科 {' / '.join(subject_reasons)} "
            f"的标准分(Z-Score)处于全校极弱势象限"
        )

        # 组装 3 层血缘有向无环图 (DAG) — 多学科节点
        nodes = []
        edges = []

        # Layer 1: 单一风险洞察节点
        l1_id = f"L1_ALERT_{stu_id}"
        nodes.append({
            "id": l1_id,
            "layer": "risk_insight",
            "label": f"学业{level_cn}危机预警",
            "data": {
                "risk_type": "academic",
                "risk_level": risk_level,
                "trigger_reason": reason,
                "triggered_subjects": len(stu_df),
            },
        })

        # Layer 2 + Layer 3: 每个触发学科一个聚合节点 + 一个源节点
        for _, row in stu_df.iterrows():
            sub_code = str(row["subject_code"])
            z_val = round(float(row["z_score"]), 3)
            if z_val == 0:
                z_val = 0.0

            scaled_val = (
                float(row["scaled_score"])
                if pd.notna(row.get("scaled_score"))
                else None
            )
            rank_val = (
                int(row["cohort_rank"])
                if pd.notna(row.get("cohort_rank"))
                else None
            )
            pct_val = (
                float(row["percentile"])
                if pd.notna(row.get("percentile"))
                else None
            )
            grade_val = (
                str(row["grade_level"])
                if pd.notna(row.get("grade_level"))
                else None
            )

            l2_id = f"L2_AGG_{stu_id}_{sub_code}"
            l3_id = f"L3_SRC_{stu_id}_{class_id_val}_{sub_code}"

            nodes.append({
                "id": l2_id,
                "layer": "aggregation_metrics",
                "label": f"学科[{sub_code}]并网计算中间体",
                "data": {
                    "raw_score": float(row["raw_score"]),
                    "scaled_score": scaled_val,
                    "cohort_rank": rank_val,
                    "percentile": pct_val,
                    "grade_level": grade_val,
                    "computed_z_score": z_val,
                },
            })
            nodes.append({
                "id": l3_id,
                "layer": "source_ingestion",
                "label": "行政班级教务数据源锚点",
                "data": {
                    "admin_class_id": class_id_val,
                    "school_id": school_id,
                    "exam_id": exam_id,
                    "ingestion_engine": "Wings_New_Gaokao_Automaton_v3",
                },
            })
            edges.append({"source": l3_id, "target": l2_id})
            edges.append({"source": l2_id, "target": l1_id})

        lineage_graph = {"nodes": nodes, "edges": edges}

        alert_obj = StudentRiskAlert(
            school_id=school_id,
            student_id=stu_id,
            exam_id=exam_id,
            risk_type="academic",
            risk_level=risk_level,
            trigger_reason=reason,
            lineage_graph=lineage_graph,
            status="active",
        )
        new_alert_objects.append(alert_obj)

    # 6. 幂等 DELETE-BEFORE-INSERT
    try:
        await db.execute(
            delete(StudentRiskAlert).where(
                StudentRiskAlert.exam_id == exam_id,
                StudentRiskAlert.school_id == school_id,
                StudentRiskAlert.status == "active",
            )
        )
        await db.flush()  # 确保 DELETE 先于 INSERT 执行, 防止唯一键冲突
        db.add_all(new_alert_objects)
        await db.commit()
    except Exception as e:
        await db.rollback()
        raise RuntimeError(f"MySQL RDI 血缘图谱批量写入溃缩: {e}")

    return {
        "status": "success",
        "alerts_triggered": len(new_alert_objects),
        "red_count": red_count,
        "yellow_count": yellow_count,
        "msg": (
            f"RDI 血缘自动机计算完毕，成功拦截并落盘 "
            f"{len(new_alert_objects)} 条危重红黄灯数据链路"
        ),
    }


# ============================================================
# 本地断言单测 (直接运行本文件时触发)
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("  新高考等级赋分核心自动机 — 本地自跑断言单测")
    print("=" * 60)

    # 模拟 10 个考生的原始化学成绩，包含同分并列和缺考
    mock_data = {
        "student_id": [101, 102, 103, 104, 105, 106, 107, 108, 109, 110],
        "raw_score":  [95,  90,  85,  85,  70,  65,  60,  55,  40,  0],
        "is_absent":  [False, False, False, False, False, False, False, False, False, True],
    }
    df_mock = pd.DataFrame(mock_data)

    # 运行自动机
    df_out = compute_new_gaokao_scaled_scores(df_mock)

    # 打印排产矩阵大盘
    print("\n" + "=" * 60)
    print("  赋分引擎处理后排产大盘：")
    print("=" * 60)
    print(
        df_out.sort_values(by="cohort_rank")[
            ["student_id", "raw_score", "cohort_rank", "grade_level", "scaled_score", "is_absent"]
        ].to_string(index=False)
    )

    # 执行硬核技术断言
    print("\n" + "-" * 60)
    print("  断言验证：")
    print("-" * 60)

    # 1. 验证有效样本数是否剔除了缺考（应为 9 人）
    assert df_out["cohort_total"].iloc[0] == 9, "样本总数统计错误"
    print("  [PASS] 有效样本数 = 9 (缺考已剔除)")

    # 2. 验证第一名 (95分) 是否成功拿到了等级 A 并赋分 100
    top_student = df_out[df_out["student_id"] == 101].iloc[0]
    assert top_student["grade_level"] == "A" and top_student["scaled_score"] == 100, "等级 A 赋分规则计算跑偏"
    print("  [PASS] student_id=101 → raw=95 → Grade A → scaled=100")

    # 3. 验证缺考考生的各项统计指标是否安全置空
    absent_student = df_out[df_out["student_id"] == 110].iloc[0]
    assert pd.isna(absent_student["scaled_score"]) and absent_student["is_absent"] == True, "缺考过滤阀失效"
    print("  [PASS] student_id=110 → 缺考 → scaled=None (安全置空)")

    # 4. 额外断言：赋分区间边界合规性
    for _, row in df_out[~df_out["scaled_score"].isna()].iterrows():
        s = int(row["scaled_score"])
        assert 30 <= s <= 100, f"赋分越界: student={row['student_id']}, scaled={s}"
    print("  [PASS] 所有赋分值均在 [30, 100] 区间内")

    # 5. 额外断言：同分同等级 (103 & 104 都是 85 分)
    s103 = df_out[df_out["student_id"] == 103].iloc[0]
    s104 = df_out[df_out["student_id"] == 104].iloc[0]
    assert s103["grade_level"] == s104["grade_level"], "同分学生等级不一致"
    assert s103["scaled_score"] == s104["scaled_score"], "同分学生赋分不一致"
    print(f"  [PASS] student_id=103 & 104 (raw=85) → 同等级={s103['grade_level']}, 同赋分={int(s103['scaled_score'])}")

    print("\n" + "=" * 60)
    print("  [ALL PASS] 新高考等级赋分引擎单测硬核通过！算法无溢出漏洞。")
    print("=" * 60)
