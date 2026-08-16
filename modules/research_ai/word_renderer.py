"""
modules/research_ai/word_renderer.py
====================================
python-docx 通用排版工具函数。

统一样式：
  - 正文：宋体 11pt，1.5 倍行距，首行缩进 0.7cm
  - 标题：黑体加粗，分级字号
  - 页面：A4（21×29.7cm），上下边距 2cm，左右 2.5cm
  - 表格：全边框（single 4sz 黑色），表头浅蓝底
"""
from __future__ import annotations

import re
from typing import Any

from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Cm, Pt, RGBColor

SONG = "宋体"
HEI = "黑体"

# A4 尺寸
A4_WIDTH = Cm(21)
A4_HEIGHT = Cm(29.7)
MARGIN_TB = Cm(2.0)
MARGIN_LR = Cm(2.5)


# ── 基础 run / 段落工具 ────────────────────────────────

def set_font(
    run,
    name: str = SONG,
    size_pt: float = 11,
    bold: bool = False,
    color: tuple[int, int, int] | None = None,
) -> None:
    """设置 run 的中英文字体、字号、粗体、颜色。"""
    run.font.name = name
    run.font.size = Pt(size_pt)
    run.font.bold = bold
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = parse_xml(f'<w:rFonts {nsdecls("w")}/>')
        rPr.insert(0, rFonts)
    rFonts.set(qn("w:eastAsia"), name)
    if color:
        run.font.color.rgb = RGBColor(*color)


def shade_cell(cell, color_hex: str) -> None:
    """给表格单元格设置底纹色。"""
    cell._tc.get_or_add_tcPr().append(
        parse_xml(f'<w:shd {nsdecls("w")} w:fill="{color_hex}"/>')
    )


def set_table_borders(table) -> None:
    """给表格设置全边框（上下左右 + 内部横竖线）。"""
    tblPr = table._tbl.tblPr
    tblPr.append(
        parse_xml(
            f'<w:tblBorders {nsdecls("w")}>'
            '<w:top w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
            '<w:left w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
            '<w:bottom w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
            '<w:right w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
            '<w:insideH w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
            '<w:insideV w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
            "</w:tblBorders>"
        )
    )


def fill_cell(
    cell,
    text: Any,
    font: str = SONG,
    size: float = 10.5,
    bold: bool = False,
    align=WD_ALIGN_PARAGRAPH.LEFT,
    shade: str | None = None,
) -> None:
    """填充单元格文本并设置样式。"""
    cell.text = ""
    p = cell.paragraphs[0]
    p.alignment = align
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(2)
    run = p.add_run("" if text is None else str(text))
    set_font(run, font, size, bold)
    cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    if shade:
        shade_cell(cell, shade)


def add_paragraph(
    doc,
    text: Any,
    font: str = SONG,
    size: float = 11,
    bold: bool = False,
    align=None,
    before: float = 0,
    after: float = 2,
    indent: float | None = None,
    line_spacing: float = 18,
    color: tuple[int, int, int] | None = None,
):
    """添加一个段落并设置样式。"""
    p = doc.add_paragraph()
    if align:
        p.alignment = align
    pf = p.paragraph_format
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)
    pf.line_spacing = Pt(line_spacing)
    if indent:
        pf.first_line_indent = Cm(indent)
    run = p.add_run("" if text is None else str(text))
    set_font(run, font, size, bold, color)
    return p


def add_heading(doc, text: str, *, level: int = 1):
    """添加章节标题（黑体）。level 1=14pt, level 2=12pt。"""
    size = 14 if level == 1 else 12
    return add_paragraph(
        doc, text, font=HEI, size=size, bold=True, before=12, after=6
    )


def add_body(doc, text: str, *, indent: float = 0.7):
    """添加正文段落（宋体，首行缩进）。"""
    return add_paragraph(
        doc, text, font=SONG, size=11, bold=False, indent=indent, line_spacing=18
    )


def add_label_body(doc, label: str, body: str, *, indent: float = 0.7):
    """添加「标签：内容」段落，标签黑体加粗。"""
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.space_before = Pt(2)
    pf.space_after = Pt(2)
    pf.line_spacing = Pt(18)
    if indent:
        pf.first_line_indent = Cm(indent)
    r1 = p.add_run(label)
    set_font(r1, HEI, 11, True)
    r2 = p.add_run(body or "")
    set_font(r2, SONG, 11, False)
    return p


# ── 文档工厂 ──────────────────────────────────────────

def new_document() -> Document:
    """创建一个标准 A4 文档并设置页边距。"""
    doc = Document()
    sec = doc.sections[0]
    sec.page_width = A4_WIDTH
    sec.page_height = A4_HEIGHT
    sec.top_margin = MARGIN_TB
    sec.bottom_margin = MARGIN_TB
    sec.left_margin = MARGIN_LR
    sec.right_margin = MARGIN_LR
    return doc


def make_table(doc, rows: int, cols: int, *, alignment=WD_TABLE_ALIGNMENT.CENTER):
    """创建带全边框的表格。"""
    table = doc.add_table(rows=rows, cols=cols)
    set_table_borders(table)
    table.alignment = alignment
    return table


# ── 文件名安全 ────────────────────────────────────────

def safe_filename_part(text: Any, fallback: str = "文件") -> str:
    """把任意动态字段清洗为安全文件名片段（V2.2.1 P0）。

    移除 Windows/文件系统非法字符 `\\ / : * ? " < > |` 与控制字符，
    并剔除首尾空白/点（Windows 文件名禁尾点）。空结果用 fallback 兜底。
    典型场景：`2025/2026学年`、`一次函数/反比例函数`、`数学:期中` 等
    教师正常输入，若不清洗会导致 Word 保存 FileNotFoundError。
    """
    s = str(text or "").strip()
    s = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "", s)
    s = s.strip().strip(".")
    if not s:
        return fallback
    # 单片段不宜过长（避免超文件名上限）；保留开头 60 字符
    return s[:60]
