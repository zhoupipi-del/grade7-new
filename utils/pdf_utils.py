"""PDF 报告单生成引擎 — ReportLab + matplotlib
每份报告单包含：
  1. 期末 AI 评语（优点 + 建议 + 综合评语）
  2. 学业成绩走势折线图（总分趋势 + 班级/年级排名）
  3. 德育五维雷达图（思想品德/学业水平/身心健康/艺术素养/社会实践）

使用方式：
  from utils.pdf_utils import generate_student_report_pdf
  pdf_bytes, filename = generate_student_report_pdf(student_id, semester)
  # pdf_bytes 可直接 return send_file(BytesIO(pdf_bytes), ...)
"""
import io
import os
from datetime import datetime

import matplotlib
matplotlib.use("Agg")  # 非交互后端
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib.ticker import MaxNLocator

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm, cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.lib.colors import HexColor, black, white, grey
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle,
    PageBreak, KeepTogether
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.cidfonts import UnicodeCIDFont

# ── 中文字体注册 ──
# 跨平台字体路径探测（Windows → Linux 常见位置 → 项目内置字体目录）
import platform

_FONT_CANDIDATES = {
    "SimHei": [
        "C:/Windows/Fonts/simhei.ttf",              # Windows
        "/usr/share/fonts/chinese/simhei.ttf",       # Linux 手动安装
        "/usr/share/fonts/truetype/simhei.ttf",
        os.path.join(os.path.dirname(__file__), "fonts", "simhei.ttf"),  # 项目内置
    ],
    "SimSun": [
        "C:/Windows/Fonts/simsun.ttc",               # Windows
        "/usr/share/fonts/chinese/simsun.ttc",        # Linux 手动安装
        "/usr/share/fonts/truetype/simsun.ttf",
        os.path.join(os.path.dirname(__file__), "fonts", "simsun.ttf"),
    ],
    "SimKai": [
        "C:/Windows/Fonts/simkai.ttf",               # Windows
        "/usr/share/fonts/chinese/simkai.ttf",        # Linux 手动安装
        "/usr/share/fonts/truetype/simkai.ttf",
        os.path.join(os.path.dirname(__file__), "fonts", "simkai.ttf"),
    ],
}

# Linux 备选：WenQuanYi Micro Hei / Noto Sans CJK 作为 SimHei 的替代
if platform.system() == "Linux":
    _FONT_CANDIDATES.setdefault("WenQuanYi", [
        "/usr/share/fonts/wqy-microhei/wqy-microhei.ttc",
        "/usr/share/fonts/truetype/wqy-microhei.ttc",
        "/usr/share/fonts/wqy-microhei.ttc",
    ])
    _FONT_CANDIDATES.setdefault("NotoSansCJK", [
        "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    ])

_FONT_PATHS = {}
for name, candidates in _FONT_CANDIDATES.items():
    for path in candidates:
        if os.path.exists(path):
            _FONT_PATHS[name] = path
            break

# ReportLab 字体注册
for name, path in _FONT_PATHS.items():
    if os.path.exists(path):
        try:
            pdfmetrics.registerFont(TTFont(name, path))
        except Exception:
            pass  # 已注册则跳过

# matplotlib 中文字体
_matplotlib_setup_done = False

def _setup_matplotlib_chinese():
    """确保 matplotlib 支持中文"""
    global _matplotlib_setup_done
    if _matplotlib_setup_done:
        return
    for name, path in _FONT_PATHS.items():
        if os.path.exists(path):
            try:
                fm.fontManager.addfont(path)
            except Exception:
                pass
    if platform.system() == "Linux":
        # Linux 上优先使用文泉驿/Noto 中文字体；SimHei/SimSun 作为后备
        plt.rcParams["font.sans-serif"] = [
            "WenQuanYi Micro Hei", "Noto Sans CJK SC", "SimHei",
            "SimSun", "Microsoft YaHei", "DejaVu Sans"
        ]
    else:
        plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "SimSun"]
    plt.rcParams["axes.unicode_minus"] = False
    _matplotlib_setup_done = True


# ── 颜色方案（梨江中学品牌色）─
# ReportLab 用 HexColor 对象
BRAND_RED = HexColor("#C41E3A")      # 中国红 — 标题/分隔线
BRAND_DARK = HexColor("#2C3E50")     # 深蓝灰 — 正文
BRAND_LIGHT = HexColor("#ECF0F1")    # 浅灰 — 背景
BRAND_ACCENT = HexColor("#2980B9")   # 蓝色 — 次级标题

# matplotlib 用 hex 字符串（HexColor 对象不被 matplotlib 接受）
MPL_RED = "#C41E3A"
MPL_DARK = "#2C3E50"
MPL_BLUE = "#2980B9"
MPL_GREEN = "#27AE60"
MPL_ORANGE = "#F39C12"
MPL_PURPLE = "#8E44AD"
CHART_COLORS = [MPL_RED, MPL_BLUE, MPL_GREEN, MPL_ORANGE, MPL_PURPLE]

# ── 维度中英文映射 ──
DIMENSION_NAMES_CN = {
    "moral": "思想品德",
    "academic": "学业水平",
    "health": "身心健康",
    "art": "艺术素养",
    "social": "社会实践",
}

DIMENSION_ORDER = ["moral", "academic", "health", "art", "social"]


# ══════════════════════════════════════════════════════════════
#  Section 1: 图表生成（matplotlib → PNG BytesIO）
# ══════════════════════════════════════════════════════════════

def generate_score_trend_chart(score_data: dict, dpi: int = 150) -> io.BytesIO:
    """成绩走势折线图 → PNG

    score_data 格式:
    {
        "exams": ["月考一", "月考二", "期中", "月考三", "期末"],
        "total_scores": [425.5, 442.0, 455.0, 448.0, 463.0],
        "class_ranks": [12, 9, 5, 7, 3],
        "grade_ranks": [85, 67, 42, 55, 28],
    }
    """
    _setup_matplotlib_chinese()

    exams = score_data.get("exams", [])
    total_scores = score_data.get("total_scores", [])
    class_ranks = score_data.get("class_ranks", [])
    grade_ranks = score_data.get("grade_ranks", [])

    n_exams = len(exams)
    if n_exams == 0:
        # 无数据时返回空白图
        fig, ax = plt.subplots(figsize=(8, 3.5), dpi=dpi)
        ax.text(0.5, 0.5, "暂无考试数据", ha="center", va="center",
                fontsize=14, color="grey", transform=ax.transAxes)
        ax.set_xticks([])
        ax.set_yticks([])
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight",
                     facecolor="white", edgecolor="none")
        plt.close(fig)
        buf.seek(0)
        return buf

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 5.5), dpi=dpi,
                                    gridspec_kw={"height_ratios": [2, 1]},
                                    facecolor="white")
    fig.subplots_adjust(hspace=0.35)

    x = list(range(n_exams))
    x_labels = exams

    # ── 上图：总分趋势 ──
    color_total = CHART_COLORS[1]  # 蓝色
    ax1.plot(x, total_scores, marker="o", linewidth=2.5, markersize=8,
             color=color_total, markerfacecolor="white",
             markeredgewidth=2, markeredgecolor=color_total, zorder=3)
    ax1.fill_between(x, total_scores, min(total_scores) * 0.95,
                     alpha=0.12, color=color_total)

    # 数据标签
    for i, (xi, val) in enumerate(zip(x, total_scores)):
        ax1.annotate(f"{val:.0f}", (xi, val), textcoords="offset points",
                     xytext=(0, 12), ha="center", fontsize=9,
                     fontweight="bold", color=color_total)

    ax1.set_ylabel("总分", fontsize=11, color=MPL_DARK)
    ax1.set_xticks(x)
    ax1.set_xticklabels(x_labels, fontsize=9)
    ax1.yaxis.set_major_locator(MaxNLocator(integer=True))
    ax1.spines["top"].set_visible(False)
    ax1.spines["right"].set_visible(False)
    ax1.grid(axis="y", alpha=0.3, linestyle="--")
    ax1.set_title("学业成绩总分走势", fontsize=13, fontweight="bold",
                  color=MPL_DARK, pad=10)

    # ── 下图：排名趋势（逆序 — 数字越小越好，所以反转Y轴）──
    if class_ranks and grade_ranks:
        color_cls = CHART_COLORS[0]  # 红色
        color_grd = CHART_COLORS[3]  # 橙色
        ax2.plot(x, class_ranks, marker="s", linewidth=2, markersize=6,
                 color=color_cls, markerfacecolor="white",
                 markeredgewidth=2, label="班级排名")
        ax2.plot(x, grade_ranks, marker="^", linewidth=2, markersize=6,
                 color=color_grd, markerfacecolor="white",
                 markeredgewidth=2, label="年级排名")
        ax2.invert_yaxis()  # 排名越小越好 → 视觉上"上升"表示进步
        ax2.legend(loc="upper right", fontsize=8, framealpha=0.9,
                   edgecolor="lightgrey")
        ax2.set_ylabel("排名", fontsize=11, color=MPL_DARK)
        ax2.set_xticks(x)
        ax2.set_xticklabels(x_labels, fontsize=9)
        ax2.grid(axis="y", alpha=0.3, linestyle="--")
        ax2.set_title("班级/年级排名变化", fontsize=11, color=MPL_DARK, pad=8)
    ax2.spines["top"].set_visible(False)
    ax2.spines["right"].set_visible(False)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    plt.close(fig)
    buf.seek(0)
    return buf


def generate_quality_radar_chart(dim_scores: dict, dpi: int = 150) -> io.BytesIO:
    """德育五维雷达图 → PNG

    dim_scores 格式:
    {
        "moral": 85.5,
        "academic": 92.0,
        "health": 78.0,
        "art": 70.5,
        "social": 82.0,
    }
    """
    _setup_matplotlib_chinese()

    import numpy as np

    labels = [DIMENSION_NAMES_CN.get(k, k) for k in DIMENSION_ORDER]
    values = [dim_scores.get(k, 0) for k in DIMENSION_ORDER]

    n = len(labels)
    angles = np.linspace(0, 2 * np.pi, n, endpoint=False).tolist()
    angles += angles[:1]  # 闭合
    values_plot = values + values[:1]

    fig, ax = plt.subplots(figsize=(5.5, 5.5), dpi=dpi,
                           subplot_kw={"projection": "polar"},
                           facecolor="white")
    fig.subplots_adjust(left=0.05, right=0.95, top=0.88, bottom=0.05)

    # 填充区域
    ax.fill(angles, values_plot, color=CHART_COLORS[0], alpha=0.15)
    ax.plot(angles, values_plot, color=CHART_COLORS[0], linewidth=2.5,
            marker="o", markersize=8, markerfacecolor="white",
            markeredgewidth=2, markeredgecolor=CHART_COLORS[0])

    # 网格参考线
    ax.set_ylim(0, 100)
    ax.set_yticks([20, 40, 60, 80, 100])
    ax.set_yticklabels(["20", "40", "60", "80", "100"], fontsize=7, color="grey")
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels, fontsize=10, fontweight="bold",
                       color=MPL_DARK)

    # 美化
    ax.spines["polar"].set_visible(False)
    ax.grid(True, alpha=0.3, linestyle="--")
    ax.set_title("德育综合素质五维雷达", fontsize=13, fontweight="bold",
                 color=MPL_DARK, pad=25)

    # 数据标签
    for angle, label, val in zip(angles[:-1], labels, values):
        ax.annotate(f"{val:.0f}", xy=(angle, val),
                    xytext=(8, 8), textcoords="offset points",
                    fontsize=8, fontweight="bold",
                    color=CHART_COLORS[0],
                    bbox=dict(boxstyle="round,pad=0.2", facecolor="white",
                              edgecolor=CHART_COLORS[0], alpha=0.8))

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    plt.close(fig)
    buf.seek(0)
    return buf


# ══════════════════════════════════════════════════════════════
#  Section 2: 数据聚合
# ══════════════════════════════════════════════════════════════

def get_student_report_data(student_id: int, semester: str = None):
    """聚合学生报告单所需全部数据

    返回:
    {
        "student": {"name": "张三", "student_no": "2025001",
                     "class_name": "七年级(1)班", "gender": "男"},
        "comment": {"overall_comment": "...", "strengths": "...",
                     "improvements": "...", "teacher_suggestion": "..."},
        "score_trend": {"exams": [...], "total_scores": [...],
                         "class_ranks": [...], "grade_ranks": [...]},
        "quality_radar": {"moral": 85.5, "academic": 92.0, ...},
        "meta": {"generated_at": datetime(...), "semester": "..."},
    }
    """
    from models import db, Student, EndTermComment, Score, Exam, Subject
    from sqlalchemy import func
    from utils import get_local_now

    # ── 1. 学生基本信息 ──
    student = Student.query.options(
        db.joinedload(Student.class_)
    ).get(student_id)
    if not student:
        raise ValueError(f"学生 ID={student_id} 不存在")

    class_name = f"七年级({student.class_.name.replace('七年级（', '').replace('）班', '').replace('(', '').replace(')', '')})班" if student.class_ else ""
    if not class_name.startswith("七"):
        class_name = student.class_.name if student.class_ else "未知"

    student_info = {
        "name": student.name,
        "student_no": student.student_no or "",
        "class_name": class_name,
        "gender": student.gender or "",
    }

    # ── 2. 期末评语 ──
    if not semester:
        from utils import get_local_now
        now = get_local_now()
        year = now.year
        term = "2" if now.month >= 2 and now.month <= 7 else "1"
        if term == "1":
            semester = f"{year}-{year + 1}-1"
        else:
            semester = f"{year - 1}-{year}-2"

    comment_obj = EndTermComment.query.filter_by(
        student_id=student_id, semester=semester
    ).first()

    comment_data = {}
    if comment_obj:
        comment_data = {
            "overall_comment": comment_obj.overall_comment or "",
            "strengths": comment_obj.strengths or "",
            "improvements": comment_obj.improvements or "",
            "teacher_suggestion": comment_obj.teacher_suggestion or "",
            "status": comment_obj.status or "draft",
        }
    else:
        comment_data = {
            "overall_comment": "该生本学期表现良好。",
            "strengths": "",
            "improvements": "",
            "teacher_suggestion": "",
            "status": "none",
        }

    # ── 3. 成绩走势 ──
    # 获取该学生所有考试，按日期排序
    scores_query = (
        db.session.query(
            Exam.id.label("exam_id"),
            Exam.name.label("exam_name"),
            Exam.exam_date,
            Score.score,
            Score.rank_class,
            Score.rank_grade,
            Subject.name.label("subject_name"),
        )
        .select_from(Score)
        .join(Exam, Score.exam_id == Exam.id)
        .join(Subject, Score.subject_id == Subject.id)
        .filter(Score.student_id == student_id)
        .filter(Score.verify_status == "VERIFIED")
        .order_by(Exam.exam_date, Exam.id)
        .all()
    )

    # 按考试聚合
    exam_map = {}  # exam_id → {name, date, subjects: {name: score}, rank_class, rank_grade}
    for row in scores_query:
        eid = row.exam_id
        if eid not in exam_map:
            exam_map[eid] = {
                "name": row.exam_name,
                "date": row.exam_date,
                "subjects": {},
                "class_rank": row.rank_class,
                "grade_rank": row.rank_grade,
            }
        exam_map[eid]["subjects"][row.subject_name] = float(row.score) if row.score else 0
        # 保留最后的排名（同一考试的排名可能在不同 subject 行中重复）
        if row.rank_class is not None:
            exam_map[eid]["class_rank"] = int(row.rank_class)
        if row.rank_grade is not None:
            exam_map[eid]["grade_rank"] = int(row.rank_grade)

    # 按日期排序
    sorted_exams = sorted(exam_map.items(),
                          key=lambda x: (x[1]["date"] or datetime.min, x[0]))

    score_trend = {
        "exams": [],
        "total_scores": [],
        "class_ranks": [],
        "grade_ranks": [],
    }

    for eid, edata in sorted_exams:
        total = sum(edata["subjects"].values())
        score_trend["exams"].append(edata["name"])
        score_trend["total_scores"].append(round(total, 1))
        score_trend["class_ranks"].append(edata.get("class_rank"))
        score_trend["grade_ranks"].append(edata.get("grade_rank"))

    # ── 4. 德育五维雷达数据 ──
    from blueprints.quality import _calculate_balanced_score

    try:
        quality_result = _calculate_balanced_score(student_id, semester,
                                                    scorer_type="teacher")
        quality_radar = {
            k: round(v, 1) for k, v in quality_result.get("balanced_scores", {}).items()
        }
    except Exception:
        # 无素质评分数据时返回零值
        quality_radar = {k: 0.0 for k in DIMENSION_ORDER}

    # ── 5. 元数据 ──
    meta = {
        "generated_at": get_local_now(),
        "semester": semester,
    }

    return {
        "student": student_info,
        "comment": comment_data,
        "score_trend": score_trend,
        "quality_radar": quality_radar,
        "meta": meta,
    }


# ══════════════════════════════════════════════════════════════
#  Section 3: PDF 文档生成（ReportLab）
# ══════════════════════════════════════════════════════════════

# 样式表
_styles_initialized = False
_STYLES = {}

def _init_styles():
    global _styles_initialized
    if _styles_initialized:
        return

    # ReportLab 字体选择（按优先级：SimHei/SimSun > WenQuanYi > NotoSansCJK > Helvetica）
    _registered = set(pdfmetrics._fonts.keys()) if hasattr(pdfmetrics, '_fonts') else set()
    if "SimHei" in _registered:
        font_title = "SimHei"
    elif "WenQuanYi" in _registered:
        font_title = "WenQuanYi"
    elif "NotoSansCJK" in _registered:
        font_title = "NotoSansCJK"
    else:
        font_title = "Helvetica-Bold"

    if "SimSun" in _registered:
        font_body = "SimSun"
    elif "WenQuanYi" in _registered:
        font_body = "WenQuanYi"
    elif "NotoSansCJK" in _registered:
        font_body = "NotoSansCJK"
    else:
        font_body = "Helvetica"

    if "SimKai" in _registered:
        font_kai = "SimKai"
    else:
        font_kai = font_body  # 无楷体时回退到正文字体

    _STYLES["title"] = ParagraphStyle(
        "RPT_Title", fontName=font_title, fontSize=22, leading=30,
        alignment=TA_CENTER, textColor=BRAND_RED, spaceAfter=4,
    )
    _STYLES["subtitle"] = ParagraphStyle(
        "RPT_Subtitle", fontName=font_body, fontSize=12, leading=18,
        alignment=TA_CENTER, textColor=BRAND_DARK, spaceAfter=2,
    )
    _STYLES["info"] = ParagraphStyle(
        "RPT_Info", fontName=font_body, fontSize=10, leading=16,
        alignment=TA_CENTER, textColor=BRAND_DARK, spaceAfter=12,
    )
    _STYLES["section_title"] = ParagraphStyle(
        "RPT_SectionTitle", fontName=font_title, fontSize=14, leading=20,
        textColor=BRAND_RED, spaceBefore=16, spaceAfter=8,
        borderPadding=(0, 0, 2, 0),
    )
    _STYLES["comment_body"] = ParagraphStyle(
        "RPT_CommentBody", fontName=font_kai, fontSize=11, leading=20,
        textColor=BRAND_DARK, alignment=TA_JUSTIFY,
        firstLineIndent=22, spaceAfter=6,
    )
    _STYLES["comment_label"] = ParagraphStyle(
        "RPT_CommentLabel", fontName=font_title, fontSize=10, leading=16,
        textColor=BRAND_ACCENT, spaceBefore=4, spaceAfter=2,
    )
    _STYLES["footer"] = ParagraphStyle(
        "RPT_Footer", fontName=font_body, fontSize=8, leading=12,
        alignment=TA_CENTER, textColor=grey,
    )
    _styles_initialized = True


def _section_title(text: str) -> Paragraph:
    """渲染带装饰线的章节标题"""
    _init_styles()
    return Paragraph(f"<b>{text}</b>", _STYLES["section_title"])


def _draw_separator(width: float, color=BRAND_RED, thickness: float = 1.2) -> Table:
    """绘制装饰分隔线"""
    t = Table([[""]], colWidths=[width], rowHeights=[thickness])
    t.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, -1), thickness, color),
    ]))
    return t


def generate_student_report_pdf(student_id: int, semester: str = None) -> tuple:
    """生成单个学生的 PDF 综合素质报告单

    返回: (pdf_bytes: bytes, filename: str)
    """
    _init_styles()

    # 聚合数据
    data = get_student_report_data(student_id, semester)

    s = data["student"]
    c = data["comment"]
    sc = data["score_trend"]
    qr = data["quality_radar"]
    m = data["meta"]

    semester_display = m["semester"]
    generated_str = m["generated_at"].strftime("%Y年%m月%d日 %H:%M")

    # ── 构建 PDF ──
    buf = io.BytesIO()
    page_w, page_h = A4  # 210 × 297 mm

    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
        title=f"{s['name']} 德育综合素质报告单",
        author="梨江中学德育处",
    )

    story = []

    # ═══ 页眉 ═══
    story.append(Paragraph("梨 江 中 学", _STYLES["title"]))
    story.append(Paragraph("德育综合素质报告单", _STYLES["subtitle"]))
    semester_label = (
        f"{semester_display.split('-')[0]}学年度 "
        f"第{'一' if semester_display.endswith('1') else '二'}学期"
        if "-" in semester_display else semester_display
    )
    story.append(Paragraph(semester_label, _STYLES["subtitle"]))
    story.append(Spacer(1, 6 * mm))

    # ── 学生信息行 ──
    info_items = [
        f"姓名：{s['name']}",
        f"班级：{s['class_name']}",
        f"学号：{s['student_no']}",
        f"性别：{s['gender']}",
    ]
    info_text = "　　".join(info_items)
    story.append(Paragraph(info_text, _STYLES["info"]))
    story.append(_draw_separator(doc.width))
    story.append(Spacer(1, 4 * mm))

    # ═══ 一、期末评语 ═══
    story.append(_section_title("一、期末评语"))

    if c.get("strengths"):
        story.append(Paragraph("【闪光点】", _STYLES["comment_label"]))
        story.append(Paragraph(c["strengths"], _STYLES["comment_body"]))

    if c.get("improvements"):
        story.append(Paragraph("【成长建议】", _STYLES["comment_label"]))
        story.append(Paragraph(c["improvements"], _STYLES["comment_body"]))

    story.append(Paragraph("【综合评语】", _STYLES["comment_label"]))
    story.append(Paragraph(c["overall_comment"], _STYLES["comment_body"]))

    if c.get("teacher_suggestion"):
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph("【班主任寄语】", _STYLES["comment_label"]))
        story.append(Paragraph(c["teacher_suggestion"], _STYLES["comment_body"]))

    story.append(Spacer(1, 4 * mm))
    story.append(_draw_separator(doc.width, BRAND_ACCENT, 0.5))

    # ═══ 二、学业成绩走势 ═══
    story.append(_section_title("二、学业成绩走势"))
    chart_buf = generate_score_trend_chart(sc)
    chart_img = Image(chart_buf, width=doc.width * 0.95, height=doc.width * 0.62)
    story.append(chart_img)
    story.append(Spacer(1, 4 * mm))
    story.append(_draw_separator(doc.width, BRAND_ACCENT, 0.5))

    # ═══ 三、德育五维评价 ═══
    story.append(_section_title("三、德育综合素质五维评价"))
    radar_buf = generate_quality_radar_chart(qr)
    radar_img = Image(radar_buf, width=doc.width * 0.65, height=doc.width * 0.65)
    # 雷达图居中
    radar_table = Table([[radar_img]], colWidths=[doc.width])
    radar_table.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ]))
    story.append(radar_table)

    # 维度说明
    dim_lines = []
    for dk in DIMENSION_ORDER:
        cn_name = DIMENSION_NAMES_CN.get(dk, dk)
        val = qr.get(dk, 0)
        dim_lines.append(f"{cn_name}：{val:.0f} 分")
    dim_text = "　　".join(dim_lines)
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(dim_text, _STYLES["info"]))

    # ═══ 页脚 ═══
    story.append(Spacer(1, 10 * mm))
    story.append(_draw_separator(doc.width, BRAND_RED, 1.5))
    footer_text = (
        f"报告生成时间：{generated_str}　　　"
        f"梨江中学德育处　　　"
        f"本报告仅供家校沟通使用"
    )
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(footer_text, _STYLES["footer"]))

    # ── 生成 PDF ──
    doc.build(story)

    # 文件名
    safe_name = s["name"]
    filename = f"{safe_name}_德育报告单_{semester_display}.pdf"

    buf.seek(0)
    return buf.getvalue(), filename


def generate_class_reports_pdf(class_id: int, semester: str = None) -> tuple:
    """批量生成一个班级所有学生的报告单（多页 PDF）

    返回: (pdf_bytes: bytes, filename: str)
    """
    from models import Student

    students = Student.query.filter_by(
        class_id=class_id, is_active=True
    ).order_by(Student.student_no).all()

    if not semester:
        from utils import get_local_now
        now = get_local_now()
        year = now.year
        term = "2" if now.month >= 2 and now.month <= 7 else "1"
        if term == "1":
            semester = f"{year}-{year + 1}-1"
        else:
            semester = f"{year - 1}-{year}-2"

    # 合并多个学生报告到一个 PDF
    all_bufs = []
    for student in students:
        try:
            pdf_bytes, _ = generate_student_report_pdf(student.id, semester)
            all_bufs.append(pdf_bytes)
        except Exception:
            continue  # 跳过生成失败的学生

    if not all_bufs:
        raise ValueError("没有成功生成任何学生报告")

    # 使用 PyPDF 或直接返回多页合并
    # 简化方案：用 reportlab 的 PageBreak 在一个文档中生成
    _init_styles()

    combined_buf = io.BytesIO()
    doc = SimpleDocTemplate(
        combined_buf, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
        title=f"班级德育综合素质报告单",
        author="梨江中学德育处",
    )

    story = []
    for i, student in enumerate(students):
        if i > 0:
            story.append(PageBreak())

        try:
            data = get_student_report_data(student.id, semester)
        except Exception:
            continue

        s = data["student"]
        c = data["comment"]
        sc = data["score_trend"]
        qr = data["quality_radar"]
        m = data["meta"]

        generated_str = m["generated_at"].strftime("%Y年%m月%d日 %H:%M")
        semester_label = (
            f"{semester.split('-')[0]}学年度 "
            f"第{'一' if semester.endswith('1') else '二'}学期"
        )

        story.append(Paragraph("梨 江 中 学", _STYLES["title"]))
        story.append(Paragraph("德育综合素质报告单", _STYLES["subtitle"]))
        story.append(Paragraph(semester_label, _STYLES["subtitle"]))
        story.append(Spacer(1, 4 * mm))

        info_text = f"姓名：{s['name']}　　班级：{s['class_name']}　　学号：{s['student_no']}"
        story.append(Paragraph(info_text, _STYLES["info"]))
        story.append(_draw_separator(doc.width))
        story.append(Spacer(1, 2 * mm))

        story.append(_section_title("一、期末评语"))
        story.append(Paragraph("【综合评语】", _STYLES["comment_label"]))
        story.append(Paragraph(c["overall_comment"], _STYLES["comment_body"]))
        story.append(Spacer(1, 2 * mm))
        story.append(_draw_separator(doc.width, BRAND_ACCENT, 0.5))

        story.append(_section_title("二、学业成绩走势"))
        chart_buf = generate_score_trend_chart(sc)
        chart_img = Image(chart_buf, width=doc.width * 0.95, height=doc.width * 0.62)
        story.append(chart_img)
        story.append(Spacer(1, 2 * mm))
        story.append(_draw_separator(doc.width, BRAND_ACCENT, 0.5))

        story.append(_section_title("三、德育五维评价"))
        radar_buf = generate_quality_radar_chart(qr)
        radar_img = Image(radar_buf, width=doc.width * 0.6, height=doc.width * 0.6)
        radar_table = Table([[radar_img]], colWidths=[doc.width])
        radar_table.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER")]))
        story.append(radar_table)

        dim_lines = []
        for dk in DIMENSION_ORDER:
            cn_name = DIMENSION_NAMES_CN.get(dk, dk)
            val = qr.get(dk, 0)
            dim_lines.append(f"{cn_name}：{val:.0f} 分")
        dim_text = "　　".join(dim_lines)
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph(dim_text, _STYLES["info"]))

        story.append(Spacer(1, 6 * mm))
        story.append(_draw_separator(doc.width, BRAND_RED, 1.5))
        footer_text = (
            f"报告生成时间：{generated_str}　　　"
            f"梨江中学德育处　　　"
            f"本报告仅供家校沟通使用"
        )
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph(footer_text, _STYLES["footer"]))

    doc.build(story)

    class_name = students[0].class_.name if students and students[0].class_ else f"班级{class_id}"
    filename = f"{class_name}_德育报告单合集_{semester}.pdf"

    combined_buf.seek(0)
    return combined_buf.getvalue(), filename
