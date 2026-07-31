"""
Wings Data Adapter - Excel 数据清洗过滤阀
基于梨江中学 3 份真实阅卷系统导出 Excel 的脏数据分析

脏数据模式清单:
  P0-1: 班级名称格式爆炸 (3种格式: "2501班" / "2501.0" / "七年级2501班")
  P0-2: 同学科不同名 ("道法" vs "政治")
  P1-1: 缺考标记不统一 ("缺考，不计排名" / "缺考")
  P1-2: 电话号码浮点化 ("13875920883.0")
  P2-1: 出生日期 Tab 污染 ("\t20130405")
  P2-2: 学籍表重复列 (姓名+学生姓名 / 身份证号+身份证件号)
  P2-3: 序号浮点化 ("16.0")
"""

import re
from dataclasses import dataclass, field
from typing import Any, Optional
from enum import Enum


class ErrorType(str, Enum):
    """坏账错误类型"""
    TYPE_MISMATCH = "type_mismatch"           # 类型不匹配
    PARSE_FAILED = "parse_failed"             # 解析失败
    MISSING_REQUIRED = "missing_required"     # 必填字段缺失
    INVALID_FORMAT = "invalid_format"         # 格式无效
    ABSENT_MARKER = "absent_marker"           # 缺考标记 (非错误, 跳过)


@dataclass
class CleanError:
    """单条坏账记录"""
    row: int
    column: str
    raw_value: str
    error_type: ErrorType
    message: str


@dataclass
class CleanResult:
    """清洗结果"""
    total_rows: int = 0
    success_rows: int = 0
    failed_rows: int = 0
    skipped_rows: int = 0       # 缺考跳过 (非错误)
    errors: list = field(default_factory=list)
    cleaned_data: list = field(default_factory=list)


# ============================================================
# 学科别名映射表 (P0-2)
# ============================================================
SUBJECT_ALIASES = {
    # 道德与法治: 期末叫"道法", 期中叫"政治"
    "道法": "道德与法治",
    "政治": "道德与法治",
    "思想政治": "道德与法治",
    "思品": "道德与法治",
    "品德": "道德与法治",

    # 生物
    "生物": "生物",

    # 历史
    "历史": "历史",

    # 地理
    "地理": "地理",

    # 语文/数学/英语 (基本不混, 但兜底)
    "语文": "语文",
    "中文": "语文",
    "数学": "数学",
    "英语": "英语",
    "外语": "英语",
    "英文": "英语",

    # 高中段可能出现的学科
    "物理": "物理",
    "化学": "化学",
    "政治 ": "道德与法治",  # 带尾空格的脏数据
}

# 反向映射: 标准名 → 可能的别名列表 (用于字段映射提示)
SUBJECT_REVERSE_MAP = {}
for alias, standard in SUBJECT_ALIASES.items():
    SUBJECT_REVERSE_MAP.setdefault(standard, []).append(alias)


# ============================================================
# 缺考标记识别 (P1-1)
# ============================================================
ABSENT_PATTERNS = [
    re.compile(r"缺考", re.IGNORECASE),
    re.compile(r"免考", re.IGNORECASE),
    re.compile(r"^\s*W\s*$", re.IGNORECASE),      # "W" / "w"
    re.compile(r"^\s*F\s*$", re.IGNORECASE),      # "F" (false)
    re.compile(r"^\s*-+\s*$"),                      # "---"
    re.compile(r"^\s*NULL\s*$", re.IGNORECASE),
    re.compile(r"^\s*空\s*$"),
]


def is_absent_marker(value: Any) -> bool:
    """判断值是否是缺考标记"""
    if not isinstance(value, str):
        return False
    v = value.strip()
    for pattern in ABSENT_PATTERNS:
        if pattern.search(v):
            return True
    return False


# ============================================================
# 清洗函数
# ============================================================

def clean_class_name(value: Any) -> str:
    """
    P0-1: 班级名称格式统一
    输入: "2501班" / "2501.0" / "七年级2501班" / 2501.0 (float)
    输出: "2501班"
    """
    if value is None:
        return ""
    s = str(value).strip()
    # 去除浮点 .0 后缀
    if s.endswith(".0"):
        s = s[:-2]
    # 去除年级前缀: "七年级2501班" → "2501班", "初二2505班" → "2505班"
    s = re.sub(r"^(七年级|八年级|九年级|初一|初二|初三|高一|高二|高三|小学)", "", s)
    # 去除括号: "高一(01)班" → "高一01班" → "01班"
    s = s.replace("(", "").replace(")", "")
    # 如果纯数字, 补 "班" 后缀
    if s.isdigit():
        s = s + "班"
    # 如果已经是 "xxxx班" 格式, 保持
    return s


def clean_subject_name(value: Any) -> str:
    """
    P0-2: 学科名称标准化
    输入: "道法" / "政治" / "思想政治" / "思品"
    输出: "道德与法治"
    """
    if value is None:
        return ""
    s = str(value).strip()
    return SUBJECT_ALIASES.get(s, s)


def clean_score(value: Any, row: int, col: str, result: CleanResult) -> Optional[float]:
    """
    P1-1: 成绩值清洗
    - 缺考标记 → None + skipped_rows++
    - 字符串数字 → float
    - float → float
    - 异常 → error log
    """
    if value is None or (isinstance(value, str) and value.strip() == ""):
        result.errors.append(CleanError(
            row=row, column=col, raw_value=str(value),
            error_type=ErrorType.MISSING_REQUIRED,
            message="成绩为空"
        ))
        result.failed_rows += 1
        return None

    # 检查缺考标记
    if is_absent_marker(value):
        result.skipped_rows += 1
        return None  # 返回 None, 调用方决定是否跳过

    # 尝试转为 float
    try:
        if isinstance(value, (int, float)):
            return float(value)
        s = str(value).strip().replace(" ", "")
        return float(s)
    except (ValueError, TypeError):
        result.errors.append(CleanError(
            row=row, column=col, raw_value=str(value),
            error_type=ErrorType.PARSE_FAILED,
            message=f"无法解析为数值: {value}"
        ))
        result.failed_rows += 1
        return None


def clean_phone(value: Any) -> str:
    """
    P1-2: 电话号码清洗
    输入: "13875920883.0" / 13875920883.0 (float)
    输出: "13875920883"
    """
    if value is None:
        return ""
    s = str(value).strip()
    # 去除浮点 .0 后缀
    if s.endswith(".0"):
        s = s[:-2]
    # 去除所有非数字字符 (保留 + 号用于国际号码)
    s = re.sub(r"[^\d+]", "", s)
    return s


def clean_date(value: Any) -> str:
    """
    P2-1: 日期清洗
    输入: "\t20130405" / "2013-04-05" / "2013/04/05"
    输出: "2013-04-05"
    """
    if value is None:
        return ""
    s = str(value).strip().replace("\t", "")
    # 纯数字 8 位: 20130405 → 2013-04-05
    if re.match(r"^\d{8}$", s):
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    # 替换 / 为 -
    s = s.replace("/", "-")
    return s


def clean_id_card(value: Any) -> str:
    """
    身份证号清洗
    输入: "\t43012120130405017X" / "43012120130405017X"
    输出: "43012120130405017X"
    """
    if value is None:
        return ""
    s = str(value).strip().replace("\t", "").replace(" ", "")
    # 防止科学计数法
    if "E+" in s or "e+" in s:
        # 尝试还原
        try:
            num = float(s)
            s = str(int(num))
        except ValueError:
            pass
    return s.upper()


def clean_serial_number(value: Any) -> int:
    """
    P2-3: 序号清洗
    输入: "16.0" / 16.0 (float) / "16"
    输出: 16 (int)
    """
    if value is None:
        return 0
    try:
        return int(float(str(value).strip()))
    except (ValueError, TypeError):
        return 0


def clean_name(value: Any) -> str:
    """
    姓名清洗
    输入: "张 三" / "张三 " / "\t张三\t"
    输出: "张三"
    """
    if value is None:
        return ""
    s = str(value).strip()
    # 去除所有空白字符 (包括全角空格 \u3000)
    s = s.replace(" ", "").replace("\u3000", "").replace("\t", "")
    return s


def deduplicate_columns(headers: list) -> list:
    """
    P2-2: 学籍表重复列去重
    输入: ["序号", "班级", "姓名", "性别", "身份证号", "全国学籍号",
           "毕业学校", "联系电话", "学生姓名", "全国学籍号", "身份证件号", "性别", ...]
    输出: 标记哪些列是重复的, 优先保留第一个出现的列
    """
    seen = {}
    result = []
    for i, h in enumerate(headers):
        h_clean = str(h).strip()
        # 已知重复列的映射关系
        duplicate_groups = {
            "学生姓名": "姓名",
            "身份证件号": "身份证号",
            "全国学籍号": "全国学籍号",  # 自重复
            "性别": "性别",  # 自重复
        }
        canonical = duplicate_groups.get(h_clean, h_clean)
        if canonical in seen:
            result.append({
                "index": i,
                "header": h_clean,
                "canonical": canonical,
                "is_duplicate": True,
                "keep": False  # 丢弃重复列
            })
        else:
            seen[canonical] = i
            result.append({
                "index": i,
                "header": h_clean,
                "canonical": canonical,
                "is_duplicate": False,
                "keep": True
            })
    return result


# ============================================================
# 主清洗流水线
# ============================================================

def clean_grades_row(
    row_idx: int,
    raw_row: dict,
    field_mapping: dict,
    result: CleanResult
) -> Optional[dict]:
    """
    成绩行清洗主函数

    Args:
        row_idx: 行号 (1-based, 0 是表头)
        raw_row: {列名: 值} 原始行数据
        field_mapping: 字段映射配置
        result: CleanResult 累积结果

    Returns:
        cleaned dict or None (跳过)
    """
    cleaned = {}

    # 1. 班级名称清洗
    class_col = field_mapping.get("class_name", "班级")
    raw_class = raw_row.get(class_col)
    cleaned["class_name"] = clean_class_name(raw_class)
    if not cleaned["class_name"]:
        result.errors.append(CleanError(
            row=row_idx, column=class_col, raw_value=str(raw_class),
            error_type=ErrorType.MISSING_REQUIRED,
            message="班级名称为空"
        ))
        result.failed_rows += 1
        return None

    # 2. 姓名清洗
    name_col = field_mapping.get("student_name", "姓名")
    raw_name = raw_row.get(name_col)
    cleaned["student_name"] = clean_name(raw_name)
    if not cleaned["student_name"]:
        result.errors.append(CleanError(
            row=row_idx, column=name_col, raw_value=str(raw_name),
            error_type=ErrorType.MISSING_REQUIRED,
            message="姓名为空"
        ))
        result.failed_rows += 1
        return None

    # 3. 学科成绩清洗
    cleaned["scores"] = {}
    all_absent = True
    subject_cols = field_mapping.get("subjects", {})

    for raw_subject_name, standard_subject in subject_cols.items():
        raw_score = raw_row.get(raw_subject_name)
        score = clean_score(raw_score, row_idx, raw_subject_name, result)
        if score is not None:
            cleaned["scores"][standard_subject] = score
            all_absent = False
        else:
            # 缺考或解析失败, 记录为 None
            cleaned["scores"][standard_subject] = None

    # 如果所有科目都缺考, 跳过该行
    if all_absent and cleaned["scores"]:
        result.skipped_rows += 1
        return None

    result.success_rows += 1
    return cleaned


def clean_roster_row(
    row_idx: int,
    raw_row: dict,
    field_mapping: dict,
    result: CleanResult
) -> Optional[dict]:
    """
    学籍行清洗主函数
    """
    cleaned = {}

    # 序号
    serial_col = field_mapping.get("serial", "序号")
    cleaned["serial"] = clean_serial_number(raw_row.get(serial_col))

    # 班级
    cleaned["class_name"] = clean_class_name(raw_row.get(field_mapping.get("class_name", "班级")))

    # 姓名
    cleaned["student_name"] = clean_name(raw_row.get(field_mapping.get("student_name", "姓名")))

    # 性别
    cleaned["gender"] = str(raw_row.get(field_mapping.get("gender", "性别"), "")).strip()

    # 身份证号
    cleaned["id_card"] = clean_id_card(raw_row.get(field_mapping.get("id_card", "身份证号")))

    # 全国学籍号
    cleaned["national_student_id"] = clean_id_card(
        raw_row.get(field_mapping.get("national_student_id", "全国学籍号"))
    )

    # 联系电话
    cleaned["phone"] = clean_phone(raw_row.get(field_mapping.get("phone", "联系电话")))

    # 出生日期
    cleaned["birth_date"] = clean_date(raw_row.get(field_mapping.get("birth_date", "出生日期")))

    # 毕业学校
    cleaned["graduation_school"] = str(
        raw_row.get(field_mapping.get("graduation_school", "毕业学校"), "")
    ).strip()

    # 监护人信息
    cleaned["guardian1_name"] = str(
        raw_row.get(field_mapping.get("guardian1_name", "监护一"), "")
    ).strip()
    cleaned["guardian1_phone"] = clean_phone(
        raw_row.get(field_mapping.get("guardian1_phone", "监护一电话号码"))
    )
    cleaned["guardian2_name"] = str(
        raw_row.get(field_mapping.get("guardian2_name", "监护二"), "")
    ).strip()
    cleaned["guardian2_phone"] = clean_phone(
        raw_row.get(field_mapping.get("guardian2_phone", "监护二电话号码"))
    )

    # 必填校验
    if not cleaned["student_name"]:
        result.errors.append(CleanError(
            row=row_idx, column="student_name", raw_value="",
            error_type=ErrorType.MISSING_REQUIRED,
            message="姓名为空"
        ))
        result.failed_rows += 1
        return None

    result.success_rows += 1
    return cleaned


# ============================================================
# JSON Schema 字段映射契约 (下周一 7/13 死锁用)
# ============================================================

GRADES_IMPORT_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "Wings Grades Import Schema",
    "description": "成绩 Excel 导入字段映射契约 v1.0",
    "type": "object",
    "properties": {
        "exam_name": {
            "type": "string",
            "description": "考试名称, 如 '2025年初中七年一期期末质量监测'",
            "required": True
        },
        "exam_date": {
            "type": "string",
            "format": "date",
            "description": "考试日期 YYYY-MM-DD",
            "required": False
        },
        "field_mapping": {
            "type": "object",
            "properties": {
                "class_name": {
                    "type": "string",
                    "description": "班级列名, 默认 '班级'",
                    "default": "班级"
                },
                "student_name": {
                    "type": "string",
                    "description": "姓名列名, 默认 '姓名'",
                    "default": "姓名"
                },
                "student_no": {
                    "type": "string",
                    "description": "准考证号列名, 可选",
                    "required": False
                },
                "total_score": {
                    "type": "string",
                    "description": "总分列名, 默认 '总分'",
                    "default": "总分"
                },
                "school_rank": {
                    "type": "string",
                    "description": "校次列名, 默认 '校次'",
                    "default": "校次"
                },
                "class_rank": {
                    "type": "string",
                    "description": "班次列名, 可选",
                    "required": False
                },
                "subjects": {
                    "type": "object",
                    "description": "学科列名 → 标准学科名映射",
                    "additionalProperties": {
                        "type": "string",
                        "description": "标准学科名 (参考 SUBJECT_ALIASES)"
                    },
                    "examples": [
                        {
                            "语文": "语文",
                            "数学": "数学",
                            "英语": "英语",
                            "生物": "生物",
                            "道法": "道德与法治",
                            "历史": "历史",
                            "地理": "地理"
                        }
                    ]
                }
            },
            "required": ["class_name", "student_name", "subjects"]
        },
        "cleaning_rules": {
            "type": "object",
            "properties": {
                "normalize_class_name": {
                    "type": "boolean",
                    "default": True,
                    "description": "班级名称标准化 (去年级前缀/补班后缀)"
                },
                "normalize_subject_name": {
                    "type": "boolean",
                    "default": True,
                    "description": "学科名称标准化 (道法→道德与法治)"
                },
                "strip_name_spaces": {
                    "type": "boolean",
                    "default": True,
                    "description": "姓名去空格"
                },
                "absent_as_null": {
                    "type": "boolean",
                    "default": True,
                    "description": "缺考标记转为 NULL (不报错)"
                },
                "skip_all_absent": {
                    "type": "boolean",
                    "default": True,
                    "description": "全科目缺考则跳过该行"
                }
            }
        },
        "error_handling": {
            "type": "object",
            "properties": {
                "on_error": {
                    "type": "string",
                    "enum": ["skip", "abort"],
                    "default": "skip",
                    "description": "遇到坏账: skip=跳过继续, abort=中断"
                },
                "max_errors": {
                    "type": "integer",
                    "default": 100,
                    "description": "最大坏账数, 超过则中断"
                }
            }
        }
    },
    "required": ["exam_name", "field_mapping"]
}


ROSTER_IMPORT_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "Wings Roster Import Schema",
    "description": "学籍 Excel 导入字段映射契约 v1.0",
    "type": "object",
    "properties": {
        "field_mapping": {
            "type": "object",
            "properties": {
                "serial": {"type": "string", "default": "序号"},
                "class_name": {"type": "string", "default": "班级"},
                "student_name": {"type": "string", "default": "姓名"},
                "gender": {"type": "string", "default": "性别"},
                "id_card": {"type": "string", "default": "身份证号"},
                "national_student_id": {"type": "string", "default": "全国学籍号"},
                "phone": {"type": "string", "default": "联系电话"},
                "birth_date": {"type": "string", "default": "出生日期"},
                "graduation_school": {"type": "string", "default": "毕业学校"},
                "guardian1_name": {"type": "string", "default": "监护一"},
                "guardian1_phone": {"type": "string", "default": "监护一电话号码"},
                "guardian2_name": {"type": "string", "default": "监护二"},
                "guardian2_phone": {"type": "string", "default": "监护二电话号码"}
            }
        },
        "deduplicate_columns": {
            "type": "boolean",
            "default": True,
            "description": "自动去重重复列 (姓名+学生姓名 等)"
        }
    },
    "required": ["field_mapping"]
}


# ============================================================
# 预置模板 (开箱即用)
# ============================================================

TEMPLATE_LIJIANG_FINAL = {
    "name": "梨江中学-期末成绩模板",
    "source_type": "yuejuan_system",
    "phase": "junior",
    "field_mapping": {
        "class_name": "班级",
        "student_name": "姓名",
        "subjects": {
            "语文": "语文",
            "数学": "数学",
            "英语": "英语",
            "生物": "生物",
            "历史": "历史",
            "地理": "地理",
            "道法": "道德与法治"
        },
        "total_score": "总分",
        "school_rank": "校次"
    },
    "cleaning_rules": {
        "normalize_class_name": True,
        "normalize_subject_name": True,
        "strip_name_spaces": True,
        "absent_as_null": True,
        "skip_all_absent": True
    },
    "error_handling": {
        "on_error": "skip",
        "max_errors": 100
    }
}

TEMPLATE_LIJIANG_MIDTERM = {
    "name": "梨江中学-期中成绩模板",
    "source_type": "yuejuan_system",
    "phase": "junior",
    "field_mapping": {
        "class_name": "班级",
        "student_name": "姓名",
        "subjects": {
            "语文": "语文",
            "数学": "数学",
            "英语": "英语",
            "生物": "生物",
            "政治": "道德与法治",   # 注意: 期中叫"政治"
            "历史": "历史",
            "地理": "地理"
        },
        "total_score": "总分",
        "school_rank": "校次"
    },
    "cleaning_rules": {
        "normalize_class_name": True,
        "normalize_subject_name": True,
        "strip_name_spaces": True,
        "absent_as_null": True,
        "skip_all_absent": True
    }
}

TEMPLATE_LIJIANG_ROSTER = {
    "name": "梨江中学-学籍信息模板",
    "source_type": "manual_export",
    "phase": "junior",
    "field_mapping": {
        "serial": "序号",
        "class_name": "班级",
        "student_name": "姓名",
        "gender": "性别",
        "id_card": "身份证号",
        "national_student_id": "全国学籍号",
        "phone": "联系电话",
        "birth_date": "出生日期",
        "graduation_school": "毕业学校",
        "guardian1_name": "监护一",
        "guardian1_phone": "监护一电话号码",
        "guardian2_name": "监护二",
        "guardian2_phone": "监护二电话号码"
    },
    "deduplicate_columns": True
}

ALL_TEMPLATES = [
    TEMPLATE_LIJIANG_FINAL,
    TEMPLATE_LIJIANG_MIDTERM,
    TEMPLATE_LIJIANG_ROSTER,
]
