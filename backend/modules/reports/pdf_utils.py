"""
modules/reports/pdf_utils.py — ReportLab + matplotlib 双引擎 PDF 报告生成器

适配 Wings 3.0 预聚合数据格式，与 Celery Worker 深度耦合。
数据由 tasks.py 的 _aggregate_class_data / _compute_rankings 预计算完成后传入。
"""

import io
import os
import platform
from datetime import datetime

import matplotlib

matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import numpy as np
from reportlab.lib.colors import HexColor, grey
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ═══════════════════════════════════════════════════════════════
# 中文字体注册（跨平台自动探测）
# ═══════════════════════════════════════════════════════════════

_FONT_CANDIDATES = {
    "SimHei": [
        "C:/Windows/Fonts/simhei.ttf",
        "/usr/share/fonts/chinese/simhei.ttf",
        "/usr/share/fonts/truetype/simhei.ttf",
    ],
    "SimSun": [
        "C:/Windows/Fonts/simsun.ttc",
        "/usr/share/fonts/chinese/simsun.ttc",
        "/usr/share/fonts/truetype/simsun.ttf",
    ],
    "SimKai": [
        "C:/Windows/Fonts/simkai.ttf",
        "/usr/share/fonts/chinese/simkai.ttf",
    ],
}

# Linux 备选：Noto Sans/Serif CJK
if platform.system() == "Linux":
    _FONT_CANDIDATES["NotoSans"] = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc",
    ]
    _FONT_CANDIDATES["NotoSerif"] = [
        "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc",
        "/usr/share/fonts/google-noto-cjk/NotoSerifCJK-Bold.ttc",
    ]
    _FONT_CANDIDATES["WenQuanYi"] = [
        "/usr/share/fonts/wqy-microhei/wqy-microhei.ttc",
        "/usr/share/fonts/truetype/wqy-microhei.ttc",
    ]

_FONT_PATHS = {}
for name, candidates in _FONT_CANDIDATES.items():
    for path in candidates:
        if os.path.exists(path):
            _FONT_PATHS[name] = path
            break

_font_registered = False


def _ensure_chinese_font():
    """确保中文支持已注册（TTF 优先，CID 字体兜底）"""
    global _font_registered
    if _font_registered:
        return

    for name, path in _FONT_PATHS.items():
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont(name, path))
            except Exception:
                pass

    try:
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
        _FONT_PATHS["STSong"] = "__cid__"
    except Exception:
        pass

    _font_registered = True


_matplotlib_setup_done = False


def _setup_matplotlib_chinese():
    """确保 matplotlib 支持中文"""
    global _matplotlib_setup_done
    if _matplotlib_setup_done:
        return
    for name, path in _FONT_PATHS.items():
        if path != "__cid__" and os.path.exists(path):
            try:
                fm.fontManager.addfont(path)
            except Exception:
                pass
    if platform.system() == "Linux":
        plt.rcParams["font.sans-serif"] = [
            "WenQuanYi Micro Hei",
            "Noto Sans CJK SC",
            "SimHei",
            "SimSun",
            "DejaVu Sans",
        ]
    else:
        plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "SimSun"]
    plt.rcParams["axes.unicode_minus"] = False
    _matplotlib_setup_done = True


# ═══════════════════════════════════════════════════════════════
# 颜色方案（梨江中学品牌色）
# ═══════════════════════════════════════════════════════════════

BRAND_RED = HexColor("#C41E3A")
BRAND_DARK = HexColor("#2C3E50")
BRAND_LIGHT = HexColor("#ECF0F1")
BRAND_ACCENT = HexColor("#2980B9")

MPL_RED = "#C41E3A"
MPL_DARK = "#2C3E50"
MPL_BLUE = "#2980B9"
MPL_GREEN = "#27AE60"
MPL_ORANGE = "#F39C12"
MPL_PURPLE = "#8E44AD"
CHART_COLORS = [MPL_RED, MPL_BLUE, MPL_GREEN, MPL_ORANGE, MPL_PURPLE]

DIMENSION_NAMES_CN = {
    "moral": "思想品德",
    "academic": "学业水平",
    "health": "身心健康",
    "art": "艺术素养",
    "social": "社会实践",
}
DIMENSION_ORDER = ["moral", "academic", "health", "art", "social"]


# ═══════════════════════════════════════════════════════════════
# 样式表
# ═══════════════════════════════════════════════════════════════

_styles_initialized = False
_STYLES = {}


def _init_styles():
    global _styles_initialized
    if _styles_initialized:
        return

    _ensure_chinese_font()
    registered = set(pdfmetrics._fonts.keys()) if hasattr(pdfmetrics, "_fonts") else set()

    # 标题字体
    if "SimHei" in registered:
        font_title = "SimHei"
    elif "NotoSerif" in registered:
        font_title = "NotoSerif"
    elif "STSong-Light" in registered:
        font_title = "STSong-Light"
    elif "WenQuanYi" in registered:
        font_title = "WenQuanYi"
    else:
        font_title = "Helvetica-Bold"

    # 正文字体
    if "SimSun" in registered:
        font_body = "SimSun"
    elif "NotoSans" in registered:
        font_body = "NotoSans"
    elif "STSong-Light" in registered:
        font_body = "STSong-Light"
    elif "WenQuanYi" in registered:
        font_body = "WenQuanYi"
    else:
        font_body = "Helvetica"

    # 楷体（评语用）
    if "SimKai" in registered:
        font_kai = "SimKai"
    else:
        font_kai = font_body

    _STYLES["title"] = ParagraphStyle(
        "RPT_Title",
        fontName=font_title,
        fontSize=22,
        leading=30,
        alignment=TA_CENTER,
        textColor=BRAND_RED,
        spaceAfter=4,
    )
    _STYLES["subtitle"] = ParagraphStyle(
        "RPT_Subtitle",
        fontName=font_body,
        fontSize=12,
        leading=18,
        alignment=TA_CENTER,
        textColor=BRAND_DARK,
        spaceAfter=2,
    )
    _STYLES["info"] = ParagraphStyle(
        "RPT_Info",
        fontName=font_body,
        fontSize=10,
        leading=16,
        alignment=TA_CENTER,
        textColor=BRAND_DARK,
        spaceAfter=12,
    )
    _STYLES["section_title"] = ParagraphStyle(
        "RPT_SectionTitle",
        fontName=font_title,
        fontSize=14,
        leading=20,
        textColor=BRAND_RED,
        spaceBefore=16,
        spaceAfter=8,
    )
    _STYLES["body"] = ParagraphStyle(
        "RPT_Body",
        fontName=font_body,
        fontSize=10,
        leading=16,
        textColor=BRAND_DARK,
        alignment=TA_JUSTIFY,
    )
    _STYLES["footer"] = ParagraphStyle(
        "RPT_Footer",
        fontName=font_body,
        fontSize=8,
        leading=12,
        alignment=TA_CENTER,
        textColor=grey,
    )
    _STYLES["table_header"] = ParagraphStyle(
        "RPT_TH",
        fontName=font_title,
        fontSize=9,
        leading=14,
        textColor=BRAND_RED,
        alignment=TA_CENTER,
    )
    _STYLES["table_cell"] = ParagraphStyle(
        "RPT_TD",
        fontName=font_body,
        fontSize=9,
        leading=14,
        textColor=BRAND_DARK,
        alignment=TA_CENTER,
    )
    _styles_initialized = True


def _section_title(text: str) -> Paragraph:
    _init_styles()
    return Paragraph(f"<b>{text}</b>", _STYLES["section_title"])


def _separator(width: float, color=BRAND_RED, thickness: float = 1.2) -> Table:
    t = Table([[""]], colWidths=[width], rowHeights=[thickness])
    t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), thickness, color)]))
    return t


# ═══════════════════════════════════════════════════════════════
# 图表生成（matplotlib → PNG BytesIO）
# ═══════════════════════════════════════════════════════════════


def generate_radar_chart(dim_scores: dict, dpi: int = 120) -> io.BytesIO:
    """五维素质雷达图 → PNG"""
    _setup_matplotlib_chinese()

    labels = [DIMENSION_NAMES_CN.get(k, k) for k in DIMENSION_ORDER]
    values = [dim_scores.get(k, 0) for k in DIMENSION_ORDER]

    n = len(labels)
    angles = np.linspace(0, 2 * np.pi, n, endpoint=False).tolist()
    angles += angles[:1]
    values_plot = values + values[:1]

    fig, ax = plt.subplots(
        figsize=(4.5, 4.5), dpi=dpi, subplot_kw={"projection": "polar"}, facecolor="white"
    )

    ax.fill(angles, values_plot, color=CHART_COLORS[0], alpha=0.12)
    ax.plot(
        angles,
        values_plot,
        color=CHART_COLORS[0],
        linewidth=2,
        marker="o",
        markersize=6,
        markerfacecolor="white",
        markeredgewidth=1.5,
        markeredgecolor=CHART_COLORS[0],
    )

    ax.set_ylim(0, 100)
    ax.set_yticks([20, 40, 60, 80, 100])
    ax.set_yticklabels(["20", "40", "60", "80", "100"], fontsize=6, color="grey")
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels, fontsize=9, fontweight="bold", color=MPL_DARK)
    ax.spines["polar"].set_visible(False)
    ax.grid(True, alpha=0.3, linestyle="--")

    for angle, val in zip(angles[:-1], values):
        ax.annotate(
            f"{val:.0f}",
            xy=(angle, val),
            xytext=(6, 6),
            textcoords="offset points",
            fontsize=7,
            fontweight="bold",
            color=CHART_COLORS[0],
            bbox=dict(
                boxstyle="round,pad=0.15", facecolor="white", edgecolor=CHART_COLORS[0], alpha=0.8
            ),
        )

    buf = io.BytesIO()
    fig.savefig(
        buf, format="png", dpi=dpi, bbox_inches="tight", facecolor="white", edgecolor="none"
    )
    plt.close(fig)
    buf.seek(0)
    return buf


def generate_class_scores_bar(students: list, dpi: int = 120) -> io.BytesIO:
    """全班五维总分柱状图 → PNG（Top 20 学生）"""
    _setup_matplotlib_chinese()

    ranked = sorted(students, key=lambda s: s["scores"].get("total", 0), reverse=True)[:20]
    names = [s["name"] for s in ranked]
    scores = [s["scores"].get("total", 0) for s in ranked]

    fig, ax = plt.subplots(figsize=(10, 4.5), dpi=dpi, facecolor="white")

    colors_bar = []
    for i in range(len(ranked)):
        if i == 0:
            colors_bar.append(MPL_RED)
        elif i <= 2:
            colors_bar.append(MPL_ORANGE)
        else:
            colors_bar.append(MPL_BLUE)

    bars = ax.bar(range(len(names)), scores, color=colors_bar, edgecolor="white", linewidth=0.5)

    for bar, val in zip(bars, scores):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 1,
            f"{val:.0f}",
            ha="center",
            va="bottom",
            fontsize=7,
            fontweight="bold",
            color=MPL_DARK,
        )

    ax.set_xticks(range(len(names)))
    ax.set_xticklabels(names, fontsize=7, rotation=45, ha="right")
    ax.set_ylabel("综合素质总分", fontsize=10, color=MPL_DARK)
    ax.set_ylim(0, max(scores) * 1.15 if scores else 100)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", alpha=0.3, linestyle="--")
    ax.set_title(
        "全班综合素质总分排名 Top 20", fontsize=12, fontweight="bold", color=MPL_DARK, pad=10
    )

    buf = io.BytesIO()
    fig.savefig(
        buf, format="png", dpi=dpi, bbox_inches="tight", facecolor="white", edgecolor="none"
    )
    plt.close(fig)
    buf.seek(0)
    return buf


def generate_flag_history_chart(flag_history: list, dpi: int = 120) -> io.BytesIO:
    """流动红旗历史得分走势 → PNG"""
    _setup_matplotlib_chinese()

    if not flag_history:
        fig, ax = plt.subplots(figsize=(8, 2.5), dpi=dpi, facecolor="white")
        ax.text(
            0.5,
            0.5,
            "暂无流动红旗数据",
            ha="center",
            va="center",
            fontsize=12,
            color="grey",
            transform=ax.transAxes,
        )
        ax.set_xticks([])
        ax.set_yticks([])
        buf = io.BytesIO()
        fig.savefig(
            buf, format="png", dpi=dpi, bbox_inches="tight", facecolor="white", edgecolor="none"
        )
        plt.close(fig)
        buf.seek(0)
        return buf

    history = list(reversed(flag_history))
    labels = [h["period_label"] for h in history]
    scores_val = [h["final_score"] for h in history]
    has_flags = [h["has_flag"] for h in history]

    fig, ax = plt.subplots(figsize=(8, 3), dpi=dpi, facecolor="white")

    x = range(len(labels))
    colors = [MPL_RED if f else MPL_BLUE for f in has_flags]
    # matplotlib 仅支持 ASCII marker，用不同形状区分：D(菱形,红旗) / o(圆,无旗)
    markers = ["D" if f else "o" for f in has_flags]
    sizes = [14 if f else 8 for f in has_flags]

    for i, (xi, yi) in enumerate(zip(x, scores_val)):
        ax.plot(
            xi,
            yi,
            marker=markers[i],
            markersize=sizes[i],
            color=colors[i],
            markeredgewidth=0.5,
            markeredgecolor="white",
            markerfacecolor=colors[i],
            zorder=3,
        )

    ax.plot(x, scores_val, color=MPL_DARK, linewidth=1.5, alpha=0.5, zorder=1)

    for i, (xi, yi) in enumerate(zip(x, scores_val)):
        ax.annotate(
            f"{yi:.1f}",
            (xi, yi),
            textcoords="offset points",
            xytext=(0, 12),
            ha="center",
            fontsize=8,
            fontweight="bold" if has_flags[i] else "normal",
            color=colors[i],
        )

    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, fontsize=7, rotation=30, ha="right")
    ax.set_ylabel("最终得分", fontsize=10, color=MPL_DARK)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", alpha=0.3, linestyle="--")
    ax.set_title(
        "流动红旗得分历史（★ = 获得红旗）", fontsize=12, fontweight="bold", color=MPL_DARK, pad=10
    )

    buf = io.BytesIO()
    fig.savefig(
        buf, format="png", dpi=dpi, bbox_inches="tight", facecolor="white", edgecolor="none"
    )
    plt.close(fig)
    buf.seek(0)
    return buf


# ═══════════════════════════════════════════════════════════════
# 数据表格构建
# ═══════════════════════════════════════════════════════════════


def _build_student_score_table(students: list, col_widths: list) -> Table:
    """构建全班成绩汇总大表"""
    _init_styles()

    header = [
        Paragraph("姓名", _STYLES["table_header"]),
        Paragraph("学号", _STYLES["table_header"]),
        Paragraph("品德", _STYLES["table_header"]),
        Paragraph("学业", _STYLES["table_header"]),
        Paragraph("健康", _STYLES["table_header"]),
        Paragraph("艺术", _STYLES["table_header"]),
        Paragraph("实践", _STYLES["table_header"]),
        Paragraph("总分", _STYLES["table_header"]),
        Paragraph("排名", _STYLES["table_header"]),
    ]

    rows = [header]
    for s in sorted(students, key=lambda x: x.get("rank_total", 999)):
        scores = s.get("scores", {})
        rows.append(
            [
                Paragraph(s["name"], _STYLES["table_cell"]),
                Paragraph(s.get("student_no", ""), _STYLES["table_cell"]),
                Paragraph(f"{scores.get('moral', 0):.0f}", _STYLES["table_cell"]),
                Paragraph(f"{scores.get('academic', 0):.0f}", _STYLES["table_cell"]),
                Paragraph(f"{scores.get('health', 0):.0f}", _STYLES["table_cell"]),
                Paragraph(f"{scores.get('art', 0):.0f}", _STYLES["table_cell"]),
                Paragraph(f"{scores.get('social', 0):.0f}", _STYLES["table_cell"]),
                Paragraph(f"{scores.get('total', 0):.0f}", _STYLES["table_cell"]),
                Paragraph(str(s.get("rank_total", "-")), _STYLES["table_cell"]),
            ]
        )

    t = Table(rows, colWidths=col_widths, repeatRows=1)
    style_commands = [
        ("BACKGROUND", (0, 0), (-1, 0), BRAND_LIGHT),
        ("GRID", (0, 0), (-1, -1), 0.5, grey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    for i in range(1, len(rows)):
        if i % 2 == 0:
            style_commands.append(("BACKGROUND", (0, i), (-1, i), HexColor("#F8F9FA")))
        if i <= 3:
            style_commands.append(("TEXTCOLOR", (0, i), (-1, i), BRAND_RED))
    t.setStyle(TableStyle(style_commands))
    return t


def _build_discipline_summary(students: list, col_widths: list) -> Table:
    """构建违纪汇总表"""
    _init_styles()

    header = [
        Paragraph("姓名", _STYLES["table_header"]),
        Paragraph("违纪次数", _STYLES["table_header"]),
        Paragraph("总扣分", _STYLES["table_header"]),
        Paragraph("出勤(天)", _STYLES["table_header"]),
        Paragraph("迟到", _STYLES["table_header"]),
        Paragraph("缺勤", _STYLES["table_header"]),
    ]

    rows = [header]
    for s in students:
        disc = s.get("discipline", {})
        att = s.get("attendance", {})
        rows.append(
            [
                Paragraph(s["name"], _STYLES["table_cell"]),
                Paragraph(str(disc.get("count", 0)), _STYLES["table_cell"]),
                Paragraph(str(disc.get("total_points", 0)), _STYLES["table_cell"]),
                Paragraph(str(att.get("present", 0)), _STYLES["table_cell"]),
                Paragraph(str(att.get("late", 0)), _STYLES["table_cell"]),
                Paragraph(str(att.get("absent", 0)), _STYLES["table_cell"]),
            ]
        )

    t = Table(rows, colWidths=col_widths, repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), BRAND_LIGHT),
                ("GRID", (0, 0), (-1, -1), 0.5, grey),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return t


# ═══════════════════════════════════════════════════════════════
# 主入口: 班级德育综合报告 PDF
# ═══════════════════════════════════════════════════════════════


def generate_class_moral_report_pdf(report_data: dict) -> tuple:
    """
    生成班级期末德育综合报告 PDF。

    入参: report_data — tasks.py 预聚合的完整数据字典
    出参: (pdf_bytes, filename)
    """
    _init_styles()

    students = report_data.get("students", [])
    class_name = report_data.get("class_name", "未知班级")
    semester = report_data.get("semester", "")
    flag_history = report_data.get("flag_history", [])
    generated_at = report_data.get("generated_at", datetime.now().strftime("%Y-%m-%d %H:%M"))

    # 学期格式化
    semester_parts = semester.split("-") if semester else []
    if len(semester_parts) >= 3:
        semester_display = (
            f"{semester_parts[0]}学年度 第{'一' if semester_parts[2] == '1' else '二'}学期"
        )
    else:
        semester_display = semester

    # ── 构建 PDF ──
    buf = io.BytesIO()
    page_w, page_h = A4

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        title=f"{class_name} 德育综合素质报告",
        author="梨江中学德育处",
    )

    story = []
    available_width = page_w - 30 * mm

    # ═══ 封面 ═══
    story.append(Spacer(1, 15 * mm))
    story.append(Paragraph("梨 江 中 学", _STYLES["title"]))
    story.append(Paragraph("班级德育综合素质报告", _STYLES["subtitle"]))
    story.append(Paragraph(semester_display, _STYLES["subtitle"]))
    story.append(Spacer(1, 8 * mm))

    # 班级信息
    info_text = (
        f"班级：{class_name}　　　学生人数：{len(students)} 人　　　报告生成时间：{generated_at}"
    )
    story.append(Paragraph(info_text, _STYLES["info"]))
    story.append(_separator(available_width))
    story.append(Spacer(1, 4 * mm))

    # ═══ 一、全班综合素质总分排名 ═══
    story.append(_section_title("一、全班综合素质总分排名"))
    if students:
        chart_buf = generate_class_scores_bar(students)
        chart_img = Image(chart_buf, width=available_width * 0.95, height=available_width * 0.42)
        story.append(chart_img)
    else:
        story.append(Paragraph("暂无评价数据", _STYLES["body"]))
    story.append(Spacer(1, 4 * mm))
    story.append(_separator(available_width, BRAND_ACCENT, 0.5))

    # ═══ 二、五维素质分详表 ═══
    story.append(_section_title("二、五维素质分详表"))
    if students:
        col_w = [
            available_width * 0.12,
            available_width * 0.10,
            available_width * 0.10,
            available_width * 0.10,
            available_width * 0.10,
            available_width * 0.10,
            available_width * 0.10,
            available_width * 0.10,
            available_width * 0.08,
        ]
        score_table = _build_student_score_table(students, col_w)
        story.append(score_table)
    else:
        story.append(Paragraph("暂无学生数据", _STYLES["body"]))
    story.append(Spacer(1, 4 * mm))
    story.append(_separator(available_width, BRAND_ACCENT, 0.5))

    # ═══ 三、流动红旗历史 ═══
    story.append(_section_title("三、流动红旗得分历史"))
    if flag_history:
        flag_chart_buf = generate_flag_history_chart(flag_history)
        flag_img = Image(flag_chart_buf, width=available_width * 0.9, height=available_width * 0.32)
        story.append(flag_img)
    else:
        story.append(Paragraph("暂无流动红旗评估数据", _STYLES["body"]))
    story.append(Spacer(1, 4 * mm))
    story.append(_separator(available_width, BRAND_ACCENT, 0.5))

    # ═══ 四、违纪与考勤汇总 ═══
    story.append(_section_title("四、违纪与考勤汇总"))
    if students:
        disc_col_w = [
            available_width * 0.12,
            available_width * 0.15,
            available_width * 0.15,
            available_width * 0.15,
            available_width * 0.13,
            available_width * 0.13,
        ]
        disc_table = _build_discipline_summary(students, disc_col_w)
        story.append(disc_table)
    else:
        story.append(Paragraph("暂无违纪/考勤数据", _STYLES["body"]))

    # ═══ 页脚 ═══
    story.append(Spacer(1, 10 * mm))
    story.append(_separator(available_width, BRAND_RED, 1.5))
    story.append(Spacer(1, 3 * mm))
    footer_text = f"报告生成时间：{generated_at}　　　梨江中学德育处　　　本报告仅供家校沟通使用"
    story.append(Paragraph(footer_text, _STYLES["footer"]))

    # ── 编译 PDF ──
    doc.build(story)

    # 文件名
    safe_name = class_name.replace("/", "_").replace("\\", "_")
    filename = f"{safe_name}_德育报告_{semester.replace('-', '_')}.pdf"

    buf.seek(0)
    return buf.getvalue(), filename


# ═══════════════════════════════════════════════════════════════
# 学生个人报告（保持兼容，后续扩展）
# ═══════════════════════════════════════════════════════════════


def generate_student_report_pdf(report_data: dict) -> tuple:
    """
    生成单个学生的综合素质报告单 PDF。

    入参: report_data — 包含 student, scores, discipline, attendance, flag_history
    出参: (pdf_bytes, filename)
    """
    _init_styles()

    student = report_data.get("student", {})
    scores = report_data.get("scores", {})
    discipline = report_data.get("discipline", {})
    attendance = report_data.get("attendance", {})
    generated_at = report_data.get("generated_at", datetime.now().strftime("%Y-%m-%d %H:%M"))

    buf = io.BytesIO()
    page_w, page_h = A4

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"{student.get('name', '学生')} 综合素质报告单",
        author="梨江中学德育处",
    )

    story = []
    available_width = page_w - 36 * mm

    # 页眉
    story.append(Paragraph("梨 江 中 学", _STYLES["title"]))
    story.append(Paragraph("学生综合素质报告单", _STYLES["subtitle"]))
    story.append(Spacer(1, 6 * mm))

    info_items = [
        f"姓名：{student.get('name', '')}",
        f"学号：{student.get('student_no', '')}",
        f"性别：{student.get('gender', '')}",
    ]
    story.append(Paragraph("　　".join(info_items), _STYLES["info"]))
    story.append(_separator(available_width))
    story.append(Spacer(1, 4 * mm))

    # 五维雷达图
    story.append(_section_title("一、五维素质评价"))
    if scores:
        radar_buf = generate_radar_chart(scores)
        radar_img = Image(radar_buf, width=available_width * 0.55, height=available_width * 0.55)
        radar_table = Table([[radar_img]], colWidths=[available_width])
        radar_table.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER")]))
        story.append(radar_table)

        dim_lines = []
        for dk in DIMENSION_ORDER:
            cn_name = DIMENSION_NAMES_CN.get(dk, dk)
            val = scores.get(dk, 0)
            dim_lines.append(f"{cn_name}：{val:.0f} 分")
        story.append(Paragraph("　　".join(dim_lines), _STYLES["info"]))
    else:
        story.append(Paragraph("暂无评价数据", _STYLES["body"]))
    story.append(Spacer(1, 2 * mm))
    story.append(_separator(available_width, BRAND_ACCENT, 0.5))

    # 违纪与考勤
    story.append(_section_title("二、违纪与考勤"))
    summary = (
        f"违纪次数：{discipline.get('count', 0)}　　总扣分：{discipline.get('total_points', 0)}\n"
        f"出勤：{attendance.get('present', 0)} 天　　"
        f"迟到：{attendance.get('late', 0)}　　缺勤：{attendance.get('absent', 0)}　　请假：{attendance.get('leave', 0)}"
    )
    story.append(Paragraph(summary, _STYLES["body"]))

    # 页脚
    story.append(Spacer(1, 10 * mm))
    story.append(_separator(available_width, BRAND_RED, 1.5))
    story.append(Spacer(1, 3 * mm))
    story.append(
        Paragraph(
            f"报告生成时间：{generated_at}　　　梨江中学德育处　　　本报告仅供家校沟通使用",
            _STYLES["footer"],
        )
    )

    doc.build(story)

    safe_name = student.get("name", "学生").replace("/", "_")
    filename = f"{safe_name}_德育报告单.pdf"

    buf.seek(0)
    return buf.getvalue(), filename
