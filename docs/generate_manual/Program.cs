using DocumentFormat.OpenXml;
using DocumentFormat.OpenXml.Packaging;
using DocumentFormat.OpenXml.Wordprocessing;

var outputPath = args.Length > 0 ? args[0] : "../班主任系统使用手册.docx";

using var doc = WordprocessingDocument.Create(outputPath, WordprocessingDocumentType.Document);
var mainPart = doc.AddMainDocumentPart();

// ── Styles Part ──
var stylesPart = mainPart.AddNewPart<StyleDefinitionsPart>();
stylesPart.Styles = BuildStyles();
stylesPart.Styles.Save();

// ── Document Body ──
mainPart.Document = new Document();
var body = new Body();
mainPart.Document.Append(body);

// ═══════════════════════════════════════════
//  COVER PAGE
// ═══════════════════════════════════════════
AddCover(body);
AddSectionBreak(body);

// ═══════════════════════════════════════════
//  TOC
// ═══════════════════════════════════════════
AddTOC(body);
AddSectionBreak(body);

// ═══════════════════════════════════════════
//  CHAPTERS
// ═══════════════════════════════════════════
Chapter1_Overview(body);
Chapter2_Login(body);
Chapter3_Navigation(body);
Chapter4_Dashboard(body);
Chapter5_StudentManagement(body);
Chapter6_ClassManagement(body);
Chapter7_AcademicManagement(body);
Chapter8_WingsQuality(body);
Chapter9_HomeSchool(body);
Chapter10_AI_Analysis(body);
Chapter11_ML_Models(body);
Chapter12_OtherFeatures(body);
Chapter13_FAQ(body);

// ── Final Section Properties (A4, moderate margins) ──
body.Append(new SectionProperties(
    new PageSize { Width = 11906U, Height = 16838U },
    new PageMargin { Top = 1440, Right = 1440U, Bottom = 1440, Left = 1440U, Header = 720U, Footer = 720U, Gutter = 0U },
    new HeaderReference { Type = HeaderFooterValues.Default, Id = "rId1" }
));

Console.WriteLine($"Manual generated: {outputPath}");

// ══════════════════════════════════════════════════════════════════
//  HELPER METHODS
// ══════════════════════════════════════════════════════════════════

static Styles BuildStyles()
{
    var styles = new Styles();

    // DocDefaults
    styles.Append(new DocDefaults(
        new RunPropertiesDefault(new RunProperties(
            new RunFonts { Ascii = "Calibri", HighAnsi = "Calibri", EastAsia = "SimSun", ComplexScript = "Arial" },
            new FontSize { Val = "24" },
            new FontSizeComplexScript { Val = "24" },
            new Languages { Val = "en-US", EastAsia = "zh-CN" }
        )),
        new ParagraphPropertiesDefault(new ParagraphProperties(
            new SpacingBetweenLines { After = "0", Line = "360", LineRule = LineSpacingRuleValues.Auto }
        ))
    ));

    // Normal
    styles.Append(new Style(
        new StyleName { Val = "Normal" },
        new StyleParagraphProperties(new SpacingBetweenLines { After = "120", Line = "360", LineRule = LineSpacingRuleValues.Auto }),
        new StyleRunProperties(new RunFonts { EastAsia = "SimSun", Ascii = "Calibri", HighAnsi = "Calibri" }, new FontSize { Val = "24" })
    ) { Type = StyleValues.Paragraph, StyleId = "Normal", Default = true });

    // Heading1 - 黑体 小二 18pt
    styles.Append(new Style(
        new StyleName { Val = "heading 1" },
        new BasedOn { Val = "Normal" },
        new NextParagraphStyle { Val = "Normal" },
        new StyleParagraphProperties(
            new KeepNext(),
            new KeepLines(),
            new SpacingBetweenLines { Before = "360", After = "200", Line = "360", LineRule = LineSpacingRuleValues.Auto },
            new OutlineLevel { Val = 0 }
        ),
        new StyleRunProperties(
            new RunFonts { EastAsia = "SimHei", Ascii = "Calibri", HighAnsi = "Calibri" },
            new Bold(),
            new FontSize { Val = "36" },
            new FontSizeComplexScript { Val = "36" },
            new Color { Val = "1F3864" }
        )
    ) { Type = StyleValues.Paragraph, StyleId = "Heading1" });

    // Heading2 - 黑体 三号 16pt
    styles.Append(new Style(
        new StyleName { Val = "heading 2" },
        new BasedOn { Val = "Normal" },
        new NextParagraphStyle { Val = "Normal" },
        new StyleParagraphProperties(
            new KeepNext(),
            new KeepLines(),
            new SpacingBetweenLines { Before = "280", After = "120", Line = "360", LineRule = LineSpacingRuleValues.Auto },
            new OutlineLevel { Val = 1 }
        ),
        new StyleRunProperties(
            new RunFonts { EastAsia = "SimHei", Ascii = "Calibri", HighAnsi = "Calibri" },
            new Bold(),
            new FontSize { Val = "32" },
            new FontSizeComplexScript { Val = "32" },
            new Color { Val = "2E75B6" }
        )
    ) { Type = StyleValues.Paragraph, StyleId = "Heading2" });

    // Heading3 - 楷体 四号 14pt
    styles.Append(new Style(
        new StyleName { Val = "heading 3" },
        new BasedOn { Val = "Normal" },
        new NextParagraphStyle { Val = "Normal" },
        new StyleParagraphProperties(
            new KeepNext(),
            new KeepLines(),
            new SpacingBetweenLines { Before = "200", After = "80", Line = "360", LineRule = LineSpacingRuleValues.Auto },
            new OutlineLevel { Val = 2 }
        ),
        new StyleRunProperties(
            new RunFonts { EastAsia = "KaiTi", Ascii = "Calibri", HighAnsi = "Calibri" },
            new Bold(),
            new FontSize { Val = "28" },
            new FontSizeComplexScript { Val = "28" },
            new Color { Val = "404040" }
        )
    ) { Type = StyleValues.Paragraph, StyleId = "Heading3" });

    return styles;
}

void AddCover(Body body)
{
    // Empty space
    for (int i = 0; i < 6; i++) AddPara(body, "", "Normal");

    // Title
    var titlePara = new Paragraph(
        new ParagraphProperties(
            new Justification { Val = JustificationValues.Center }
        ),
        new Run(
            new RunProperties(
                new RunFonts { EastAsia = "SimHei", Ascii = "Calibri" },
                new Bold(),
                new FontSize { Val = "52" },
                new FontSizeComplexScript { Val = "52" },
                new Color { Val = "1F3864" }
            ),
            new Text("梨江中学德育管理系统")
        )
    );
    body.Append(titlePara);

    AddPara(body, "", "Normal");

    // Subtitle
    var subPara = new Paragraph(
        new ParagraphProperties(new Justification { Val = JustificationValues.Center }),
        new Run(new RunProperties(
            new RunFonts { EastAsia = "KaiTi", Ascii = "Calibri" },
            new FontSize { Val = "36" }, new FontSizeComplexScript { Val = "36" },
            new Color { Val = "2E75B6" }
        ), new Text("班主任操作手册"))
    );
    body.Append(subPara);

    AddPara(body, "", "Normal");
    AddPara(body, "", "Normal");

    // Decorative line
    var linePara = new Paragraph(new ParagraphProperties(new Justification { Val = JustificationValues.Center },
        new ParagraphBorders(new TopBorder { Val = BorderValues.Single, Size = 12, Color = "1F3864", Space = 1 })));
    body.Append(linePara);

    AddPara(body, "", "Normal");

    // Info
    AddCenterPara(body, "版本：V2.0", "SimSun", "24", "666666");
    AddCenterPara(body, "日期：2026年6月", "SimSun", "24", "666666");
    AddCenterPara(body, "适用于：班主任角色", "SimSun", "24", "666666");

    AddPara(body, "", "Normal");
    AddPara(body, "", "Normal");

    AddCenterPara(body, "梨江中学德育处 编制", "KaiTi", "24", "999999");
}

void AddTOC(Body body)
{
    AddH1(body, "目  录");
    AddPara(body, "", "Normal");

    var tocPara = new Paragraph(
        new SimpleField(
            new FieldCode(" TOC \\o \"1-3\" \\h \\z \\u "),
            new FieldChar { FieldCharType = FieldCharValues.Separate },
            new Run(new Text("（请在Word中右键点击此处 → 更新域 以生成目录）")),
            new FieldChar { FieldCharType = FieldCharValues.End }
        )
    );
    body.Append(tocPara);
}

void AddSectionBreak(Body body)
{
    body.Append(new Paragraph(
        new ParagraphProperties(new SectionProperties(
            new PageSize { Width = 11906U, Height = 16838U },
            new PageMargin { Top = 1440, Right = 1440U, Bottom = 1440, Left = 1440U, Header = 720U, Footer = 720U, Gutter = 0U }
        ))
    ));
}

// ── Paragraph helpers ──
void AddH1(Body b, string text) => b.Append(H1(text));
void AddH2(Body b, string text) => b.Append(H2(text));
void AddPara(Body b, string text, string styleId = "Normal") => b.Append(Para(text, styleId));
void AddBold(Body b, string label, string value) => b.Append(BoldLabel(label, value));
void AddBullet(Body b, string text, int level = 0) => b.Append(Bullet(text, level));
void AddTable(Body b, string[] headers, string[][] rows) => b.Append(MakeTable(headers, rows));

Paragraph H1(string text) => new Paragraph(
    new ParagraphProperties(new ParagraphStyleId { Val = "Heading1" }),
    new Run(new Text(text))
);

Paragraph H2(string text) => new Paragraph(
    new ParagraphProperties(new ParagraphStyleId { Val = "Heading2" }),
    new Run(new Text(text))
);

Paragraph Para(string text, string styleId) => new Paragraph(
    new ParagraphProperties(new ParagraphStyleId { Val = styleId }),
    new Run(new Text(text))
);

Paragraph BoldLabel(string label, string value) => new Paragraph(
    new ParagraphProperties(new ParagraphStyleId { Val = "Normal" }),
    new Run(new RunProperties(new Bold()), new Text(label)),
    new Run(new Text(value))
);

Paragraph Bullet(string text, int level)
{
    var indent = (level + 1) * 360;
    return new Paragraph(
        new ParagraphProperties(
            new ParagraphStyleId { Val = "Normal" },
            new Indentation { Left = indent.ToString(), Hanging = "360" }
        ),
        new Run(new Text("•  " + text))
    );
}

void AddCenterPara(Body b, string text, string font, string sz, string color)
{
    b.Append(new Paragraph(
        new ParagraphProperties(new Justification { Val = JustificationValues.Center }),
        new Run(new RunProperties(
            new RunFonts { EastAsia = font },
            new FontSize { Val = sz }, new FontSizeComplexScript { Val = sz },
            new Color { Val = color }
        ), new Text(text))
    ));
}

Table MakeTable(string[] headers, string[][] rows)
{
    var table = new Table();

    // Table properties
    table.Append(new TableProperties(
        new TableStyle { Val = "TableGrid" },
        new TableWidth { Width = "5000", Type = TableWidthUnitValues.Pct },
        new TableBorders(
            new TopBorder { Val = BorderValues.Single, Size = 4, Color = "1F3864" },
            new BottomBorder { Val = BorderValues.Single, Size = 4, Color = "1F3864" },
            new InsideHorizontalBorder { Val = BorderValues.Single, Size = 4, Color = "CCCCCC" },
            new InsideVerticalBorder { Val = BorderValues.Single, Size = 4, Color = "CCCCCC" }
        ),
        new TableCellMarginDefault(
            new TopMargin { Width = "40", Type = TableWidthUnitValues.Dxa },
            new StartMargin { Width = "80", Type = TableWidthUnitValues.Dxa },
            new BottomMargin { Width = "40", Type = TableWidthUnitValues.Dxa },
            new EndMargin { Width = "80", Type = TableWidthUnitValues.Dxa }
        )
    ));

    // Header row
    var headerRow = new TableRow();
    foreach (var h in headers)
    {
        headerRow.Append(new TableCell(
            new TableCellProperties(
                new Shading { Val = ShadingPatternValues.Clear, Color = "auto", Fill = "1F3864" }
            ),
            new Paragraph(
                new ParagraphProperties(new Justification { Val = JustificationValues.Center }),
                new Run(new RunProperties(
                    new Bold(), new Color { Val = "FFFFFF" }, new FontSize { Val = "21" }
                ), new Text(h))
            )
        ));
    }
    table.Append(headerRow);

    // Data rows
    for (int i = 0; i < rows.Length; i++)
    {
        var row = new TableRow();
        foreach (var cell in rows[i])
        {
            row.Append(new TableCell(
                i % 2 == 1 ? new TableCellProperties(new Shading { Val = ShadingPatternValues.Clear, Fill = "F2F7FB" }) : new TableCellProperties(),
                new Paragraph(new Run(new RunProperties(new FontSize { Val = "21" }), new Text(cell ?? "")))
            ));
        }
        table.Append(row);
    }

    return table;
}

// ══════════════════════════════════════════════════════════════════
//  CHAPTER 1: SYSTEM OVERVIEW
// ══════════════════════════════════════════════════════════════════
void Chapter1_Overview(Body body)
{
    AddH1(body, "第一章 系统概述");

    AddH2(body, "1.1 系统简介");
    AddPara(body, "梨江中学德育管理系统是一个面向中学德育工作的综合性信息化平台。系统遵循「德育处下发 → 年级组分配 → 班主任执行 → 家长查看」的数据流设计，为班主任提供了从学生管理、成绩分析、综合评价到家校沟通的全流程数字化支持。");

    AddH2(body, "1.2 班主任角色定位");
    AddPara(body, "班主任是系统中承上启下的关键角色，主要职责包括：");
    AddBullet(body, "管理班级学生信息（名册、档案、标签）");
    AddBullet(body, "记录和处理学生日常表现（考勤、违纪）");
    AddBullet(body, "审批学生请假申请");
    AddBullet(body, "录入和分析学生考试成绩");
    AddBullet(body, "对学生进行综合素质评价");
    AddBullet(body, "撰写期末评语和成长报告");
    AddBullet(body, "与家长进行通知、沟通和家访");
    AddBullet(body, "组织和管理班级活动");
    AddBullet(body, "使用AI辅助分析工具关注学生发展");

    AddH2(body, "1.3 系统访问地址");
    AddBold(body, "系统网址：", "http://8.137.180.152");
    AddBold(body, "测试账号（班主任）：", "ct_2501 / admin123");
    AddPara(body, "如需其他测试账号，请联系系统管理员。");

    AddH2(body, "1.4 功能模块总览");
    AddPara(body, "班主任可使用的功能模块共22个，涵盖以下主要领域：");
    AddTable(body,
        new[] { "序号", "模块领域", "包含功能" },
        new[] {
            new[] { "1", "工作台", "仪表盘、快捷入口、数据概览" },
            new[] { "2", "学生管理", "名册、详情、导入导出、学生标签" },
            new[] { "3", "班级管理", "违纪记录、考勤打卡、请假审批、任务反馈" },
            new[] { "4", "学业管理", "成绩录入、考试分析、成绩趋势、学期对比" },
            new[] { "5", "评价体系", "五翼评价、综合素质评价、期末评语" },
            new[] { "6", "家校沟通", "通知家长、家长会、家访记录、沟通追踪" },
            new[] { "7", "活动管理", "创建活动、报名管理、签到统计" },
            new[] { "8", "智能分析", "统一仪表盘、心理健康评估、AI预测模型" },
            new[] { "9", "消息中心", "收件箱、写消息、系统公告" },
        }
    );

    AddPara(body, "");
    AddPara(body, "提示：本书册涵盖所有模块的详细操作说明，请根据目录查阅对应章节。");
}

// ══════════════════════════════════════════════════════════════════
//  CHAPTER 2: LOGIN AND BASICS
// ══════════════════════════════════════════════════════════════════
void Chapter2_Login(Body body)
{
    AddH1(body, "第二章 登录与基础操作");

    AddH2(body, "2.1 登录系统");
    AddPara(body, "1. 打开浏览器，访问系统地址 http://8.137.180.152");
    AddPara(body, "2. 在登录页面输入您的用户名和密码");
    AddPara(body, "3. 点击「登录」按钮进入系统");
    AddPara(body, "登录成功后，系统会自动识别您的班主任角色，展示班主任专属的工作台页面。");

    AddH2(body, "2.2 修改密码");
    AddPara(body, "首次登录后建议立即修改默认密码：");
    AddPara(body, "1. 点击右上角用户头像/姓名旁的齿轮图标");
    AddPara(body, "2. 选择「修改密码」");
    AddPara(body, "3. 输入旧密码和新密码，确认后保存");

    AddH2(body, "2.3 退出登录");
    AddPara(body, "点击右上角的「退出登录」按钮安全退出系统。建议使用完毕后及时退出，尤其在公共电脑上操作时。");

    AddH2(body, "2.4 导航结构说明");
    AddPara(body, "系统采用左侧导航栏 + 顶部消息通知的布局：");
    AddBullet(body, "左侧导航栏：显示班主任的所有功能入口，按模块分组排列");
    AddBullet(body, "顶部状态栏：显示系统名称、消息图标（红点提示新消息）、用户信息");
    AddBullet(body, "内容区域：显示当前选中功能的操作页面");

    AddH2(body, "2.5 全局搜索");
    AddPara(body, "系统提供全局搜索功能，可在任意页面快速查找学生、考试等信息：");
    AddBullet(body, "点击导航栏中的搜索图标或按快捷键进入搜索页面");
    AddBullet(body, "输入学生姓名、学号等关键词进行搜索");
    AddBullet(body, "选择搜索结果可直接跳转到对应的学生详情页");
}

// ══════════════════════════════════════════════════════════════════
//  CHAPTER 3: NAVIGATION
// ══════════════════════════════════════════════════════════════════
void Chapter3_Navigation(Body body)
{
    AddH1(body, "第三章 导航菜单详解");

    AddPara(body, "班主任左侧导航栏包含以下14个主菜单项（含5个下拉子菜单），下面是每个菜单项的快速索引：");

    AddTable(body,
        new[] { "菜单名称", "图标", "URL路径", "说明" },
        new[] {
            new[] { "工作台", "bi-speedometer2", "/class/", "班主任首页，数据概览和快捷入口" },
            new[] { "学生名册", "bi-people", "/class/students", "班级学生名单管理" },
            new[] { "班级管理 ▼", "bi-journal-check", "下拉菜单", "违纪记录、考勤打卡" },
            new[] { "请假审批", "bi-calendar-check", "/class/leaves", "学生请假审批处理" },
            new[] { "任务反馈", "bi-list-check", "/class/tasks", "德育处下发任务反馈" },
            new[] { "通知家长", "bi-bell", "/class/notify", "向家长发送通知信息" },
            new[] { "五翼评价", "bi-star", "/wings/", "五翼成长评价体系" },
            new[] { "学业管理 ▼", "bi-graph-up", "下拉菜单", "成绩、考试、趋势、评语" },
            new[] { "家校沟通 ▼", "bi-megaphone", "下拉菜单", "通知公告、家长会、家访" },
            new[] { "学生标签", "bi-tags", "/tags/", "学生分类标签管理" },
            new[] { "智能分析 ▼", "bi-cpu", "下拉菜单", "仪表盘、心理健康、ML模型" },
            new[] { "消息", "bi-envelope", "/common/messages", "收件箱和消息中心" },
        }
    );

    AddPara(body, "");
    AddPara(body, "提示：各菜单项的详细操作方法请参见后续章节。");
}

// ══════════════════════════════════════════════════════════════════
//  CHAPTER 4: DASHBOARD
// ══════════════════════════════════════════════════════════════════
void Chapter4_Dashboard(Body body)
{
    AddH1(body, "第四章 工作台");

    AddH2(body, "4.1 工作台首页");
    AddPara(body, "登录后默认进入工作台首页，提供班级数据的全景概览：");
    AddBullet(body, "班级人数统计：总人数、男女比例");
    AddBullet(body, "近期考试概览：最新考试的成绩分布");
    AddBullet(body, "考勤统计：今日出勤/缺勤/请假人数");
    AddBullet(body, "违纪记录：近期违纪统计");
    AddBullet(body, "待处理事项：待审批请假、待反馈任务等");
    AddBullet(body, "快捷入口：常用功能的快速跳转按钮");

    AddH2(body, "4.2 数据驾驶舱");
    AddPara(body, "点击「数据驾驶舱」可进入班级数据总览视图：");
    AddPara(body, "地址：/cockpit/");
    AddBullet(body, "查看班级各维度可视化数据");
    AddBullet(body, "支持按学期切换数据范围");
}

// ══════════════════════════════════════════════════════════════════
//  CHAPTER 5: STUDENT MANAGEMENT
// ══════════════════════════════════════════════════════════════════
void Chapter5_StudentManagement(Body body)
{
    AddH1(body, "第五章 学生管理");

    AddH2(body, "5.1 学生名册");
    AddPara(body, "路径：导航栏 → 学生名册 或 /class/students");
    AddPara(body, "学生名册显示本班所有在校学生列表，支持以下操作：");
    AddBullet(body, "查看：点击学生姓名或「详情」按钮进入学生详情页");
    AddBullet(body, "搜索：使用搜索框按姓名/学号快速查找学生");
    AddBullet(body, "添加学生：点击「添加学生」按钮，填写信息后保存");
    AddBullet(body, "编辑学生：点击「编辑」修改学生基本信息");
    AddBullet(body, "删除学生：点击「删除」移除学生（慎用，建议先确认）");
    AddBullet(body, "导入学生：下载模板 → 填写数据 → 上传Excel批量导入");
    AddBullet(body, "导出学生：点击「导出」下载本班学生Excel名单");

    AddH2(body, "5.2 学生详情页");
    AddPara(body, "路径：点击学生名册中的学生姓名 → /class/students/<sid>");
    AddPara(body, "学生详情页整合了该生的多维数据：");
    AddBullet(body, "基本信息：姓名、学号、性别、班级");
    AddBullet(body, "成绩记录：各科历次考试成绩汇总");
    AddBullet(body, "考勤记录：出勤/缺勤/请假统计");
    AddBullet(body, "违纪记录：违纪类型、时间、处理结果");
    AddBullet(body, "综合评价：五翼评价、综合素质评分");
    AddBullet(body, "AI分析：综合风险评估、成绩趋势预测");
    AddBullet(body, "成长档案：学期成长记录");

    AddH2(body, "5.3 学生画像");
    AddPara(body, "路径：/student-profile/<sid>");
    AddPara(body, "学生画像是更全面的学生档案视图，包括：");
    AddBullet(body, "多维度数据可视化（雷达图、趋势线）");
    AddBullet(body, "教师手记：班主任可在此添加对学生的个性化记录");
    AddBullet(body, "风险预警：系统自动标记需关注的学生");
    AddBullet(body, "处理风险：对预警进行处理并记录处理结果");

    AddH2(body, "5.4 学生标签");
    AddPara(body, "路径：导航栏 → 学生标签 或 /tags/");
    AddPara(body, "班主任可以为本班学生打标签，用于分类管理和快速筛选：");
    AddBullet(body, "系统预设标签：如「重点关注」「进步明显」等");
    AddBullet(body, "支持自定义标签内容");
    AddBullet(body, "支持批量为多名学生添加相同标签");
    AddBullet(body, "标签可用于后续的筛选、分析和通知场景");
}

// ══════════════════════════════════════════════════════════════════
//  CHAPTER 6: CLASS MANAGEMENT
// ══════════════════════════════════════════════════════════════════
void Chapter6_ClassManagement(Body body)
{
    AddH1(body, "第六章 班级管理");

    AddH2(body, "6.1 违纪记录管理");
    AddPara(body, "路径：导航栏 → 班级管理 → 违纪记录 或 /class/discipline");
    AddPara(body, "班主任可以记录和管理学生的违纪行为：");
    AddBullet(body, "查看列表：显示本班所有违纪记录，按时间倒序排列");
    AddBullet(body, "新增违纪：点击「新增违纪」→ 选择学生 → 选择违纪类型 → 填写描述 → 保存");
    AddBullet(body, "违纪类型：警告、轻微违纪、重大违纪、严重违纪（对应素质分扣除1/3/10/20分）");
    AddBullet(body, "编辑违纪：点击「编辑」修改违纪记录详情");
    AddBullet(body, "删除违纪：点击「删除」移除记录");
    AddBullet(body, "解决违纪：点击「解决」标记违纪为已处理状态");
    AddBullet(body, "批量操作：支持一次性为多名学生添加违纪记录");
    AddBullet(body, "考勤转违纪：将连续缺勤自动转为违纪记录");

    AddPara(body, "");
    AddPara(body, "⚠ 注意：违纪记录一旦添加，会按违纪等级自动扣除学生综合素质评价分数，请谨慎操作。");

    AddH2(body, "6.2 考勤打卡");
    AddPara(body, "路径：导航栏 → 班级管理 → 考勤打卡 或 /class/attendance");
    AddPara(body, "班主任可在此管理班级每日考勤：");
    AddBullet(body, "当日考勤：按学生列表逐一标记出勤/迟到/缺勤/请假状态");
    AddBullet(body, "快速全勤：一键将所有学生标记为出勤");
    AddBullet(body, "考勤历史：查看历史考勤记录，支持按日期筛选");
    AddBullet(body, "考勤统计：通过 /attendance-stats/ 查看班级出勤率趋势");
    AddBullet(body, "异常预警：系统自动标记出勤异常（连续缺勤等）的学生");

    AddH2(body, "6.3 请假审批");
    AddPara(body, "路径：导航栏 → 请假审批 或 /class/leaves");
    AddPara(body, "处理家长提交的学生请假申请：");
    AddBullet(body, "查看请假列表：显示待审批/已审批的请假申请");
    AddBullet(body, "审批请假：查看请假详情（学生、时间、原因）→ 点击「通过」或「拒绝」");
    AddBullet(body, "请假类型：事假、病假、其他");
    AddBullet(body, "联动考勤：审批通过后，系统自动在对应日期标记请假状态");
    AddBullet(body, "通知家长：审批结果会自动通知家长");

    AddH2(body, "6.4 任务反馈");
    AddPara(body, "路径：导航栏 → 任务反馈 或 /class/tasks");
    AddPara(body, "德育处下发的任务，班主任需要在此提交反馈：");
    AddBullet(body, "查看任务：显示德育处下发的待完成/已完成任务");
    AddBullet(body, "提交反馈：点击某个任务 → 填写反馈内容 → 上传附件（如有）→ 提交");
    AddBullet(body, "任务状态：显示各任务的完成状态和截止时间");

    AddH2(body, "6.5 通知家长");
    AddPara(body, "路径：导航栏 → 通知家长 或 /class/notify");
    AddPara(body, "班主任可以向本班学生家长发送通知：");
    AddBullet(body, "选择接收人：可发送给全班家长、个别学生家长或特定分组");
    AddBullet(body, "撰写通知：输入通知标题和内容");
    AddBullet(body, "使用模板：可以选用系统预设的消息模板快速生成通知");
    AddBullet(body, "发送通知：点击「发送」后，家长端会实时收到通知");
    AddBullet(body, "消息关联：发送时可以关联特定学生，方便追踪");
}

// ══════════════════════════════════════════════════════════════════
//  CHAPTER 7: ACADEMIC MANAGEMENT
// ══════════════════════════════════════════════════════════════════
void Chapter7_AcademicManagement(Body body)
{
    AddH1(body, "第七章 学业管理");

    AddH2(body, "7.1 成绩管理首页");
    AddPara(body, "路径：导航栏 → 学业管理 → 成绩管理 或 /scores/");
    AddPara(body, "成绩管理首页展示：");
    AddBullet(body, "班级所有考试列表");
    AddBullet(body, "最近一次考试的成绩汇总");
    AddBullet(body, "班级平均分和各科成绩分布");

    AddH2(body, "7.2 考试管理");
    AddPara(body, "路径：/scores/exams");
    AddPara(body, "班主任可进行以下考试相关操作：");
    AddBullet(body, "创建考试：点击「新建考试」→ 填写考试名称、日期、学期 → 选择参与科目 → 保存");
    AddBullet(body, "删除考试：点击「删除」移除考试及其所有成绩数据（不可恢复！）");
    AddBullet(body, "查看考试：点击考试名称进入详情页（/scores/exams/<eid>）");

    AddH2(body, "7.3 成绩录入");
    AddPara(body, "路径：进入考试详情页 → 点击「录入成绩」 或 /scores/exams/<eid>/input");
    AddPara(body, "成绩录入页面提供两种录入方式：");
    AddBullet(body, "逐人录入：按学生列表逐一填写各科成绩");
    AddBullet(body, "快速录入：表格形式，Tab键快速切换单元格");
    AddBullet(body, "保存成绩：录入完成后点击「保存」，系统自动计算班级平均分");
    AddBullet(body, "修改成绩：已保存的成绩可重新编辑（修改后会自动检测并触发AI分析）");
    AddBullet(body, "删除成绩：可删除单个学生或全部学生的某次考试成绩");
    AddPara(body, "");
    AddPara(body, "⚠ 提示：修改已录入的成绩会触发系统的AI分析，自动检测成绩异常波动并通知班主任。");

    AddH2(body, "7.4 考试分析");
    AddPara(body, "路径：/scores/exams/<eid>/analysis");
    AddPara(body, "系统自动生成考试分析报告，包含：");
    AddBullet(body, "成绩分布：各科最高分/最低分/平均分/中位数");
    AddBullet(body, "分数段统计：优秀/良好/及格/不及格人数和比例");
    AddBullet(body, "年级排名：本班各科在年级中的排名位置");
    AddBullet(body, "进退步分析：与上次考试对比，标注进步/退步学生");
    AddBullet(body, "学生排名：/scores/exams/<eid>/ranking");

    AddH2(body, "7.5 成绩趋势线");
    AddPara(body, "路径：导航栏 → 学业管理 → 成绩趋势线 或 /scores/trend");
    AddPara(body, "选择学生后，系统自动生成四个图表：");
    AddBullet(body, "总分趋势：历次考试总分变化折线图");
    AddBullet(body, "各科对比：各科目的单独成绩趋势");
    AddBullet(body, "排名变化：年级排名随时间的变化曲线");
    AddBullet(body, "成绩预测：基于历史数据使用线性回归预测下次考试成绩");
    AddBullet(body, "多学生对比：支持选择多名学生进行成绩趋势对比");

    AddH2(body, "7.6 多学期对比");
    AddPara(body, "路径：导航栏 → 学业管理 → 多学期对比 或 /scores/comparison");
    AddPara(body, "提供班级维度的成绩对比分析：");
    AddBullet(body, "本班与年级对比：各科成绩与年级平均的差距");
    AddBullet(body, "跨学期对比：不同学期的班级成绩变化趋势");
    AddBullet(body, "可视化图表：柱状图、折线图展示对比数据");

    AddH2(body, "7.7 期末评语");
    AddPara(body, "路径：导航栏 → 学业管理 → 期末评语 或 /endterm-comment/");
    AddPara(body, "班主任为本班学生撰写学期评语：");
    AddBullet(body, "选择学生：从下拉列表中选择需要写评语的学生");
    AddBullet(body, "撰写评语：编辑器支持富文本格式");
    AddBullet(body, "智能辅助：系统自动展示该生的成绩、考勤、违纪等多维度数据作为参考");
    AddBullet(body, "批量录入：支持为全班学生批量录入评语（/endterm-comment/batch）");
    AddBullet(body, "编辑/删除：已撰写的评语可修改或删除");
    AddBullet(body, "导出评语：支持一键导出全班评语为文件");
}

// ══════════════════════════════════════════════════════════════════
//  CHAPTER 8: WINGS & QUALITY
// ══════════════════════════════════════════════════════════════════
void Chapter8_WingsQuality(Body body)
{
    AddH1(body, "第八章 评价体系");

    AddH2(body, "8.1 五翼评价系统");
    AddPara(body, "路径：导航栏 → 五翼评价 或 /wings/");
    AddPara(body, "五翼评价是从五个维度对学生进行综合评价的体系：");
    AddBullet(body, "仪表盘（/wings/）：班级五翼评价总览");
    AddBullet(body, "教师评分（/wings/score/teacher）：班主任为学生进行五翼维度评分");
    AddBullet(body, "班级排名（/wings/class-ranking）：五翼评价班级排名");
    AddBullet(body, "勋章系统（/wings/medals）：根据评分自动授予勋章");
    AddBullet(body, "成长档案（/wings/portfolio）：学生五翼评价档案");
    AddBullet(body, "五翼分析（/wings/analysis）：五翼维度深入分析");

    AddH2(body, "8.2 综合素质评价");
    AddPara(body, "路径：导航栏 → 学业管理 → 综合素质评价 或 /quality/");
    AddPara(body, "综合素质评价包含五个维度共23个评价指标：");
    AddBullet(body, "思想品德：遵纪守法、诚实守信、文明礼貌等");
    AddBullet(body, "学业水平：学习态度、学习方法、学业成绩等");
    AddBullet(body, "身心健康：体育锻炼、心理素质、卫生习惯等");
    AddBullet(body, "艺术素养：艺术兴趣、审美能力、艺术表现等");
    AddBullet(body, "社会实践：劳动实践、志愿服务、社会调查等");

    AddPara(body, "");
    AddPara(body, "评分操作（/quality/score）：");
    AddBullet(body, "逐人评分：选择学生 → 按指标逐项打分 → 保存");
    AddBullet(body, "批量评分（/quality/batch-score）：一次性为全班学生在同一指标上打分");
    AddBullet(body, "查看本班评价（/quality/my-class）：查看全班各维度评价结果");
    AddBullet(body, "综合评价报告（/quality/report/<sid>）：单个学生的综合雷达图报告");

    AddPara(body, "");
    AddPara(body, "⚠ 注意：违纪记录会自动扣除综合素质评价的思想品德维度分数（警告-1/轻微-3/重大-10/严重-20），请班主任在记录违纪时注意该联动效应。");
}

// ══════════════════════════════════════════════════════════════════
//  CHAPTER 9: HOME-SCHOOL COMMUNICATION
// ══════════════════════════════════════════════════════════════════
void Chapter9_HomeSchool(Body body)
{
    AddH1(body, "第九章 家校沟通");

    AddH2(body, "9.1 通知公告");
    AddPara(body, "路径：导航栏 → 家校沟通 → 通知公告 或 /notices/");
    AddBullet(body, "查看公告：查看德育处和年级组发布的通知公告");
    AddBullet(body, "创建通知（/notices/create）：班主任可在本班范围内发布通知");
    AddBullet(body, "删除通知：删除自己创建的通知");
    AddBullet(body, "查看回执（/notices/<nid>/receipts）：查看家长是否已读/已签收");
    AddBullet(body, "标记已读（/notices/<nid>/mark_read）：手动标记通知为已读状态");

    AddH2(body, "9.2 家长会管理");
    AddPara(body, "路径：导航栏 → 家校沟通 → 家长会 或 /parent-meeting/");
    AddBullet(body, "查看家长会列表：显示已安排的家长会");
    AddBullet(body, "家长会详情（/parent-meeting/<mid>）：查看会议时间、地点、主题");
    AddBullet(body, "签到管理（/parent-meeting/<mid>/signin）：为到场家长逐一签到");
    AddBullet(body, "批量签到（/parent-meeting/<mid>/batch_signin）：一键批量签到");
    AddPara(body, "");
    AddPara(body, "注：创建和删除家长会需要年级组长或德育处权限，班主任可联系年级组长协助创建。");

    AddH2(body, "9.3 家访记录");
    AddPara(body, "路径：导航栏 → 家校沟通 → 家访记录 或 /home-visits/");
    AddBullet(body, "创建家访（/home-visits/create）：记录家访时间、学生、方式（上门/电话/来校）、内容和后续跟进");
    AddBullet(body, "查看家访列表：按时间顺序查看历史家访记录");
    AddBullet(body, "删除家访：删除自己的家访记录");
    AddPara(body, "");
    AddPara(body, "提示：建议对有异常表现（成绩大幅下降、频繁违纪、心理预警等）的学生优先安排家访。");

    AddH2(body, "9.4 家校沟通追踪");
    AddPara(body, "路径：导航栏 → 智能分析 → 家校沟通追踪 或 /communication/");
    AddBullet(body, "沟通统计：消息发送量、家长阅读率、回复率等");
    AddBullet(body, "发送提醒（/communication/api/remind/<msg_id>）：对未读消息的家长发送提醒");
    AddBullet(body, "数据概览：提供沟通效果的可视化图表");
}

// ══════════════════════════════════════════════════════════════════
//  CHAPTER 10: AI ANALYSIS
// ══════════════════════════════════════════════════════════════════
void Chapter10_AI_Analysis(Body body)
{
    AddH1(body, "第十章 智能分析");

    AddH2(body, "10.1 统一仪表盘");
    AddPara(body, "路径：导航栏 → 智能分析 → 统一仪表盘 或 /ai-analysis/dashboard");
    AddPara(body, "统一仪表盘整合了三个维度的数据可视化：");
    AddBullet(body, "心理筛查：MSSMHS-55问卷得分分布和风险等级统计");
    AddBullet(body, "学业预警：成绩异常波动学生自动识别");
    AddBullet(body, "综合风险：融合心理+学业+违纪的三维风险评估");
    AddBullet(body, "单人档案（/ai-analysis/dashboard/<sid>）：每个学生的独立风险档案");

    AddH2(body, "10.2 AI分析首页");
    AddPara(body, "路径：/ai-analysis/");
    AddPara(body, "提供AI分析的入口，包括：");
    AddBullet(body, "学生综合风险评估：选择学生查看AI生成的综合风险评估报告");
    AddBullet(body, "风险等级：红色（高危）/ 黄色（中危）/ 绿色（安全）");
    AddBullet(body, "预警规则：MSSMHS-55≥160红色预警，120-159黄色预警");

    AddH2(body, "10.3 心理健康评估");
    AddPara(body, "路径：导航栏 → 智能分析 → 心理健康评估 或 /mental-health/");
    AddBullet(body, "评估列表：显示本班学生的心理健康评估记录");
    AddBullet(body, "创建评估（/mental-health/create）：为学生创建新的心理健康评估");
    AddBullet(body, "评估详情（/mental-health/<aid>）：查看评估详情，包含辅助数据（违纪/成绩/考勤/请假）");
    AddBullet(body, "编辑评估（/mental-health/<aid>/edit）：修改评估记录");
    AddBullet(body, "数据联动：问卷→评估→AI预警自动流转");
    AddPara(body, "");
    AddPara(body, "提示：心理健康评估与MSSMHS-55问卷自动联动。当学生问卷总分≥120分时，系统会自动创建心理健康评估记录。");
}

// ══════════════════════════════════════════════════════════════════
//  CHAPTER 11: ML MODELS
// ══════════════════════════════════════════════════════════════════
void Chapter11_ML_Models(Body body)
{
    AddH1(body, "第十一章 数学模型（即时推理）");

    AddPara(body, "系统内置6个数学模型，全部采用「即时推理」模式——输入学生姓名后，系统自动拉取历史数据并实时计算预测结果。无需手动训练步骤。");

    AddH2(body, "11.1 成绩预测");
    AddPara(body, "路径：/ml/grade-prediction");
    AddPara(body, "使用线性回归模型（sklearn LinearRegression）基于历史成绩预测下次考试分数：");
    AddBullet(body, "输入学生姓名 → 系统自动搜索并拉取历史成绩 → 点击「开始预测」");
    AddBullet(body, "输出：各科预测分数、置信度、趋势方向（上升/下降/平稳）");
    AddBullet(body, "适用场景：识别成绩下滑风险，提前介入辅导");

    AddH2(body, "11.2 心理风险预测");
    AddPara(body, "路径：/ml/mental-risk");
    AddPara(body, "基于MSSMHS-55心理问卷数据的规则引擎分析：");
    AddBullet(body, "输入学生姓名 → 拉取最新问卷数据 → 输出风险等级和概率");
    AddBullet(body, "风险分级：≥160红色高危 / 120-159黄色中危 / <120绿色安全");
    AddBullet(body, "输出：各维度得分、总体风险概率、建议关注方向");

    AddH2(body, "11.3 违纪预测");
    AddPara(body, "路径：/ml/discipline-prediction");
    AddPara(body, "基于历史违纪频率的泊松外推预测：");
    AddBullet(body, "计算学生日均违纪率 → 推测未来30天违纪次数");
    AddBullet(body, "风险分级：预测≥3次红色高危 / 1-2次黄色中危 / <1次绿色安全");

    AddH2(body, "11.4 综合素质预测");
    AddPara(body, "路径：/ml/quality-prediction");
    AddPara(body, "基于历史综合素质评分趋势的线性外推：");
    AddBullet(body, "分析各维度历史评分 → 预测下一阶段评分");
    AddBullet(body, "输出：各维度预测分值、发展趋势");

    AddH2(body, "11.5 成长预测");
    AddPara(body, "路径：/ml/growth-prediction");
    AddPara(body, "多维度综合成长趋势分析：");
    AddBullet(body, "先选择班级 → 再选择学生 → 点击「分析」");
    AddBullet(body, "输出：多维度趋势图表、成长建议");

    AddH2(body, "11.6 相似学生推荐");
    AddPara(body, "路径：/ml/similar-students");
    AddPara(body, "基于五维特征的余弦相似度算法：");
    AddBullet(body, "先选择班级 → 选择学生 → 点击「查找相似学生」");
    AddBullet(body, "输出：与该生特征最相似的前10名学生，可用于参考辅导策略");
}

// ══════════════════════════════════════════════════════════════════
//  CHAPTER 12: OTHER FEATURES
// ══════════════════════════════════════════════════════════════════
void Chapter12_OtherFeatures(Body body)
{
    AddH1(body, "第十二章 其他功能");

    AddH2(body, "12.1 活动管理");
    AddPara(body, "路径：导航栏 → 活动（如有显示）或 /activity/");
    AddPara(body, "班主任可以管理和组织班级活动：");
    AddBullet(body, "创建活动：填写活动名称、时间、地点、类型");
    AddBullet(body, "报名管理：查看学生报名情况，确认/取消报名");
    AddBullet(body, "签到管理：活动当天为学生签到，支持批量签到");
    AddBullet(body, "签到统计（/activity/<aid>/signin-stats）：查看签到率和缺勤名单");
    AddBullet(body, "标记缺席（/activity/<aid>/signin/<sid>/absent）：标记未到场学生");

    AddH2(body, "12.2 心理问卷");
    AddPara(body, "路径：/survey/psych");
    AddBullet(body, "问卷列表（/survey/psych）：查看本班学生完成的问卷");
    AddBullet(body, "问卷统计（/survey/psych/stats）：查看班级问卷数据统计");
    AddBullet(body, "问卷分析（/survey/analysis）：深入分析问卷结果");
    AddBullet(body, "同步评估（/survey/psych/sync-to-assessment）：手动触发问卷→心理评估的同步");

    AddH2(body, "12.3 消息中心");
    AddPara(body, "路径：导航栏 → 消息 或 /common/messages");
    AddBullet(body, "收件箱：查看接收到的所有消息，支持按类型筛选");
    AddBullet(body, "写消息（/common/messages/compose）：向其他教师/家长发送消息，支持关联学生");
    AddBullet(body, "消息模板（/message-templates/）：查看和使用预设模板快速发送");
    AddBullet(body, "系统公告（/common/announcements）：查看系统级别的公共公告");
    AddBullet(body, "未读提醒：顶部消息图标红点显示未读消息数量");
    AddBullet(body, "实时推送：系统通过SSE技术实时推送新消息（无需刷新页面）");

    AddH2(body, "12.4 考勤统计");
    AddPara(body, "路径：/attendance-stats/");
    AddBullet(body, "班级考勤总览：出勤率、缺勤率统计");
    AddBullet(body, "异常预警（/attendance-stats/anomalies）：自动标记出勤异常学生");
    AddBullet(body, "学生考勤详情（/attendance-stats/detail/<sid>）：单个学生考勤详情");

    AddH2(body, "12.5 成长报告");
    AddPara(body, "路径：/growth/");
    AddBullet(body, "成长报告首页：班级学生成长报告汇总");
    AddBullet(body, "学生成长详情（/growth/detail/<sid>）：综合性成长档案");
    AddBullet(body, "导出PDF（/growth/export/pdf/<sid>）：导出为PDF格式");
    AddBullet(body, "导出Excel（/growth/export/excel）：批量导出全班成长数据");

    AddH2(body, "12.6 学期归档");
    AddPara(body, "路径：/archive/");
    AddBullet(body, "查看归档（/archive/<semester_name>）：查看历史学期数据");
    AddBullet(body, "学期对比（/archive/compare）：对比两个学期的数据差异");
    AddBullet(body, "导出归档（/archive/<semester_name>/export）：导出学期数据");
}

// ══════════════════════════════════════════════════════════════════
//  CHAPTER 13: FAQ
// ══════════════════════════════════════════════════════════════════
void Chapter13_FAQ(Body body)
{
    AddH1(body, "第十三章 常见问题");

    AddH2(body, "13.1 登录相关问题");
    AddPara(body, "Q：忘记密码怎么办？");
    AddPara(body, "A：请联系年级组长或德育处管理员重置密码。目前系统不支持自主找回密码。");

    AddPara(body, "");
    AddPara(body, "Q：登录页面很慢怎么办？");
    AddPara(body, "A：首次登录可能需要加载资源，稍等几秒即可。如果持续缓慢，请检查网络连接或联系管理员。");

    AddH2(body, "13.2 数据相关问题");
    AddPara(body, "Q：为什么我只能看到自己班的数据？");
    AddPara(body, "A：系统按角色和班级进行数据隔离，班主任只能查看和管理自己班级的数据，这是出于数据安全和隐私保护的设计。");

    AddPara(body, "");
    AddPara(body, "Q：录入的成绩为什么不见了？");
    AddPara(body, "A：请检查是否正确点击了「保存」按钮。如果确认已保存但仍然找不到，请联系管理员查看操作日志。");

    AddPara(body, "");
    AddPara(body, "Q：违纪扣分能否撤销？");
    AddPara(body, "A：删除违纪记录后，扣分会自动恢复。如果不小心添加了错误记录，可以在违纪列表中点击「删除」移除。");

    AddH2(body, "13.3 模型预测相关问题");
    AddPara(body, "Q：数学模型需要训练吗？");
    AddPara(body, "A：不需要手动训练。系统采用「即时推理」模式，输入学生姓名后会自动拉取历史数据并实时计算预测结果。");

    AddPara(body, "");
    AddPara(body, "Q：预测结果显示「无数据」怎么办？");
    AddPara(body, "A：不同模型需要不同类型的数据支持。例如成绩预测需要至少2次考试成绩，心理风险需要完成MSSMHS-55问卷。请确保学生已有相关历史数据。");

    AddPara(body, "");
    AddPara(body, "Q：预测结果准确吗？");
    AddPara(body, "A：模型预测仅供参考，基于历史数据的统计推断存在天然不确定性。请结合您的教学经验综合判断，不要完全依赖模型结果。");

    AddH2(body, "13.4 操作相关问题");
    AddPara(body, "Q：如何批量导入学生？");
    AddPara(body, "A：在学生名册页面（/class/students），点击「导入学生」→「下载模板」→ 按模板格式填写数据 →「选择文件」→「上传」。注意学号不能重复。");

    AddPara(body, "");
    AddPara(body, "Q：如何给全班学生统一评分？");
    AddPara(body, "A：综合素质评价支持批量评分：/quality/batch-score → 选择指标 → 为全班学生统一设置分值。期末评语也支持批量录入：/endterm-comment/batch。");

    AddPara(body, "");
    AddPara(body, "Q：家长收到我的通知了吗？");
    AddPara(body, "A：可以在通知公告的回执页面（/notices/<nid>/receipts）查看家长的已读/已签状态。在沟通追踪页面（/communication/）可以查看整体沟通统计数据。");

    AddH2(body, "13.5 系统功能边界");
    AddPara(body, "以下功能班主任无法操作，需要年级组长或德育处权限：");
    AddBullet(body, "创建和删除科目（需年级组长）");
    AddBullet(body, "发布成绩和计算排名（需年级组长）");
    AddBullet(body, "删除心理健康评估（需年级组长）");
    AddBullet(body, "创建和删除家长会（需年级组长）");
    AddBullet(body, "导出汇总数据和Excel（需年级组长或德育处）");
    AddBullet(body, "查看数据大屏和工作量统计（需年级组长或德育处）");
    AddBullet(body, "管理用户和系统配置（需德育处）");
    AddBullet(body, "数据备份和审计日志（需德育处）");

    AddPara(body, "");
    AddPara(body, "如有需要，请联系相应角色的管理员协助操作。");

    AddH2(body, "13.6 技术支持");
    AddPara(body, "如遇到本手册未覆盖的问题，请联系：");
    AddBullet(body, "系统管理员（德育处）：负责账号管理、系统配置、数据维护");
    AddBullet(body, "年级组长：负责成绩发布、排名计算、家长会创建等年级级别操作");
    AddBullet(body, "技术支持：如遇系统故障，请联系IT部门或系统开发团队");
}

// ══════════════════════════════════════════════════════════════════
//  END
// ══════════════════════════════════════════════════════════════════
