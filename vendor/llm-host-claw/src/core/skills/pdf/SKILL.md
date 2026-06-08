---
name: pdf
description: 当用户想要对 PDF 文件执行任何操作时使用此技能。包括从 PDF 读取或提取文本/表格、合并或合并多个 PDF、拆分 PDF、旋转页面、添加水印、创建新 PDF、填写 PDF 表单、加密/解密 PDF、提取图像以及对扫描的 PDF 进行 OCR 以使其可搜索。如果用户提到 .pdf 文件或要求生成一个，使用此技能。
license: Proprietary. LICENSE.txt has complete terms
---

# PDF 处理指南

## 概述

本指南涵盖使用 Python 库和命令行工具的基本 PDF 处理操作。有关高级功能、JavaScript 库和详细示例，请参阅 REFERENCE.md。如果需要填写 PDF 表单，请阅读 FORMS.md 并按照其说明操作。

## 快速开始

```python
from pypdf import PdfReader, PdfWriter

# 读取 PDF
reader = PdfReader("document.pdf")
print(f"Pages: {len(reader.pages)}")

# 提取文本
text = ""
for page in reader.pages:
    text += page.extract_text()
```

## Python 库

### pypdf - 基本操作

#### 合并 PDF
```python
from pypdf import PdfWriter, PdfReader

writer = PdfWriter()
for pdf_file in ["doc1.pdf", "doc2.pdf", "doc3.pdf"]:
    reader = PdfReader(pdf_file)
    for page in reader.pages:
        writer.add_page(page)

with open("merged.pdf", "wb") as output:
    writer.write(output)
```

#### 拆分 PDF
```python
reader = PdfReader("input.pdf")
for i, page in enumerate(reader.pages):
    writer = PdfWriter()
    writer.add_page(page)
    with open(f"page_{i+1}.pdf", "wb") as output:
        writer.write(output)
```

#### 提取元数据
```python
reader = PdfReader("document.pdf")
meta = reader.metadata
print(f"Title: {meta.title}")
print(f"Author: {meta.author}")
print(f"Subject: {meta.subject}")
print(f"Creator: {meta.creator}")
```

#### 旋转页面
```python
reader = PdfReader("input.pdf")
writer = PdfWriter()

page = reader.pages[0]
page.rotate(90)  # 顺时针旋转 90 度
writer.add_page(page)

with open("rotated.pdf", "wb") as output:
    writer.write(output)
```

### pdfplumber - 文本和表格提取

#### 带布局提取文本
```python
import pdfplumber

with pdfplumber.open("document.pdf") as pdf:
    for page in pdf.pages:
        text = page.extract_text()
        print(text)
```

#### 提取表格
```python
with pdfplumber.open("document.pdf") as pdf:
    for i, page in enumerate(pdf.pages):
        tables = page.extract_tables()
        for j, table in enumerate(tables):
            print(f"Table {j+1} on page {i+1}:")
            for row in table:
                print(row)
```

#### 高级表格提取
```python
import pandas as pd

with pdfplumber.open("document.pdf") as pdf:
    all_tables = []
    for page in pdf.pages:
        tables = page.extract_tables()
        for table in tables:
            if table:  # 检查表格是否非空
                df = pd.DataFrame(table[1:], columns=table[0])
                all_tables.append(df)

# 合并所有表格
if all_tables:
    combined_df = pd.concat(all_tables, ignore_index=True)
    combined_df.to_excel("extracted_tables.xlsx", index=False)
```

### reportlab - 创建 PDF

#### 基本 PDF 创建
```python
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

c = canvas.Canvas("hello.pdf", pagesize=letter)
width, height = letter

# 添加文本
c.drawString(100, height - 100, "Hello World!")
c.drawString(100, height - 120, "This is a PDF created with reportlab")

# 添加线条
c.line(100, height - 140, 400, height - 140)

# 保存
c.save()
```

#### 创建多页 PDF
```python
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet

doc = SimpleDocTemplate("report.pdf", pagesize=letter)
styles = getSampleStyleSheet()
story = []

# 添加内容
title = Paragraph("Report Title", styles['Title'])
story.append(title)
story.append(Spacer(1, 12))

body = Paragraph("This is the body of the report. " * 20, styles['Normal'])
story.append(body)
story.append(PageBreak())

# 第 2 页
story.append(Paragraph("Page 2", styles['Heading1']))
story.append(Paragraph("Content for page 2", styles['Normal']))

# 构建 PDF
doc.build(story)
```

#### 下标和上标

**重要**：切勿在 ReportLab PDF 中使用 Unicode 下标/上标字符（₀₁₂₃₄₅₆₇₈₉、⁰¹²³⁴⁵⁶⁷⁸⁹）。内置字体不包含这些字形，导致它们渲染为实心黑框。

相反，在 Paragraph 对象中使用 ReportLab 的 XML 标记标签：
```python
from reportlab.platypus import Paragraph
from reportlab.lib.styles import getSampleStyleSheet

styles = getSampleStyleSheet()

# 下标：使用 <sub> 标签
chemical = Paragraph("H<sub>2</sub>O", styles['Normal'])

# 上标：使用 <super> 标签
squared = Paragraph("x<super>2</super> + y<super>2</super>", styles['Normal'])
```

对于画布绘制的文本（非 Paragraph 对象），手动调整字体大小和位置，而不是使用 Unicode 下标/上标。

### 中文字体处理

**重要**：ReportLab默认字体（Helvetica/Times/Courier）不支持中文，必须注册中文字体。

#### 跨平台中文字体解决方案

```python
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.styles import ParagraphStyle
import platform

def register_chinese_fonts():
    """
    注册跨平台中文字体
    按优先级尝试不同字体源
    """
    system = platform.system()
    font_registered = False
    
    # 字体路径配置（按优先级）
    if system == 'Windows':
        font_paths = [
            # Windows系统字体
            ('SimSun', 'C:/Windows/Fonts/simsun.ttc'),      # 宋体
            ('SimHei', 'C:/Windows/Fonts/simhei.ttf'),      # 黑体
            ('Microsoft YaHei', 'C:/Windows/Fonts/msyh.ttc'), # 微软雅黑
            ('Microsoft YaHei Bold', 'C:/Windows/Fonts/msyhbd.ttc'),
        ]
    elif system == 'Darwin':  # macOS
        font_paths = [
            ('PingFang', '/System/Library/Fonts/PingFang.ttc'),
            ('Heiti TC', '/System/Library/Fonts/STHeiti Light.ttc'),
            ('Songti SC', '/System/Library/Fonts/STSong.ttf'),
        ]
    else:  # Linux
        font_paths = [
            ('WenQuanYi Micro Hei', '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc'),
            ('WenQuanYi Zen Hei', '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc'),
            ('Noto Sans CJK SC', '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'),
            ('Droid Sans Fallback', '/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf'),
        ]
    
    # 尝试注册字体
    registered_fonts = {}
    for font_name, font_path in font_paths:
        try:
            pdfmetrics.registerFont(TTFont(font_name, font_path))
            registered_fonts[font_name] = font_path
            font_registered = True
        except:
            continue
    
    if not font_registered:
        raise RuntimeError(
            "无法注册中文字体。请确保系统已安装中文字体。\n"
            "Windows: 检查 C:/Windows/Fonts/ 目录\n"
            "Linux: 安装 fonts-wqy-zenhei 或 fonts-noto-cjk\n"
            "macOS: 系统通常自带中文字体"
        )
    
    return registered_fonts

# 使用示例
registered = register_chinese_fonts()
chinese_font = list(registered.keys())[0]  # 使用第一个成功注册的字体
chinese_font_bold = list(registered.keys())[1] if len(registered) > 1 else chinese_font

# 创建中文样式
title_style = ParagraphStyle(
    'ChineseTitle',
    fontName=chinese_font_bold,
    fontSize=18,
    spaceAfter=12
)

body_style = ParagraphStyle(
    'ChineseBody',
    fontName=chinese_font,
    fontSize=12,
    leading=20,  # 行高，中文需要更大行距
    spaceAfter=10
)
```

#### 中文PDF生成完整示例

```python
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import platform

def create_chinese_pdf(output_path, title, content):
    """创建支持中文的PDF文档"""
    
    # 1. 注册中文字体
    system = platform.system()
    if system == 'Windows':
        font_candidates = [
            ('ChineseFont', 'C:/Windows/Fonts/simsun.ttc'),
            ('ChineseFont', 'C:/Windows/Fonts/msyh.ttc'),
        ]
    elif system == 'Darwin':
        font_candidates = [
            ('ChineseFont', '/System/Library/Fonts/PingFang.ttc'),
        ]
    else:  # Linux
        font_candidates = [
            ('ChineseFont', '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc'),
            ('ChineseFont', '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc'),
        ]
    
    font_name = None
    for name, path in font_candidates:
        try:
            pdfmetrics.registerFont(TTFont(name, path))
            font_name = name
            break
        except:
            continue
    
    if not font_name:
        raise Exception("无法找到可用的中文字体")
    
    # 2. 创建文档
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        rightMargin=2*cm,
        leftMargin=2*cm,
        topMargin=2*cm,
        bottomMargin=2*cm
    )
    
    # 3. 定义中文样式
    title_style = ParagraphStyle(
        'Title',
        fontName=font_name,
        fontSize=20,
        spaceAfter=20,
        alignment=1  # 居中
    )
    
    body_style = ParagraphStyle(
        'Body',
        fontName=font_name,
        fontSize=12,
        leading=20,  # 中文需要更大的行距
        spaceAfter=10
    )
    
    # 4. 构建内容
    story = []
    story.append(Paragraph(title, title_style))
    story.append(Spacer(1, 0.5*cm))
    
    for paragraph in content.split('\n\n'):
        story.append(Paragraph(paragraph, body_style))
        story.append(Spacer(1, 0.3*cm))
    
    # 5. 生成PDF
    doc.build(story)
    print(f"PDF已生成: {output_path}")

# 使用
content = """这是第一段中文内容。\n\n这是第二段中文内容，包含更多文字。"""
create_chinese_pdf("output.pdf", "中文PDF标题", content)
```

#### 常见问题

**问题1：中文显示为空白或方框**
- 原因：未正确注册中文字体，或使用了不支持中文的字体
- 解决：确保调用 `pdfmetrics.registerFont()` 成功，且字体文件存在

**问题2：中文换行不正确**
- 原因：ReportLab默认按空格换行，中文没有空格
- 解决：使用 `Paragraph` 类并设置 `wordWrap='CJK'`，或手动插入 `<br/>`

```python
# 中文换行解决方案
from reportlab.platypus import Paragraph

# 方法1：使用HTML换行标签
text = "第一行内容<br/>第二行内容"
p = Paragraph(text, style)

# 方法2：设置CJK换行模式（实验性）
style.wordWrap = 'CJK'
```

**问题3：字体文件找不到**
- Windows：使用正斜杠或原始字符串 `r'C:\Windows\Fonts\simsun.ttc'`
- Linux/macOS：确保字体已安装，路径正确

## 命令行工具

### pdftotext (poppler-utils)
```bash
# 提取文本
pdftotext input.pdf output.txt

# 保留布局提取文本
pdftotext -layout input.pdf output.txt

# 提取特定页面
pdftotext -f 1 -l 5 input.pdf output.txt  # 第 1-5 页
```

### qpdf
```bash
# 合并 PDF
qpdf --empty --pages file1.pdf file2.pdf -- merged.pdf

# 拆分页面
qpdf input.pdf --pages . 1-5 -- pages1-5.pdf
qpdf input.pdf --pages . 6-10 -- pages6-10.pdf

# 旋转页面
qpdf input.pdf output.pdf --rotate=+90:1  # 将第 1 页旋转 90 度

# 移除密码
qpdf --password=mypassword --decrypt encrypted.pdf decrypted.pdf
```

### pdftk（如果可用）
```bash
# 合并
pdftk file1.pdf file2.pdf cat output merged.pdf

# 拆分
pdftk input.pdf burst

# 旋转
pdftk input.pdf rotate 1east output rotated.pdf
```

## 常见任务

### 从扫描的 PDF 提取文本
```python
# 需要：pip install pytesseract pdf2image
import pytesseract
from pdf2image import convert_from_path

# 将 PDF 转换为图像
images = convert_from_path('scanned.pdf')

# 对每页进行 OCR
text = ""
for i, image in enumerate(images):
    text += f"Page {i+1}:\n"
    text += pytesseract.image_to_string(image)
    text += "\n\n"

print(text)
```

### 添加水印
```python
from pypdf import PdfReader, PdfWriter

# 创建水印（或加载现有的）
watermark = PdfReader("watermark.pdf").pages[0]

# 应用到所有页面
reader = PdfReader("document.pdf")
writer = PdfWriter()

for page in reader.pages:
    page.merge_page(watermark)
    writer.add_page(page)

with open("watermarked.pdf", "wb") as output:
    writer.write(output)
```

### 提取图像
```bash
# 使用 pdfimages (poppler-utils)
pdfimages -j input.pdf output_prefix

# 这将提取所有图像为 output_prefix-000.jpg、output_prefix-001.jpg 等
```

### 密码保护
```python
from pypdf import PdfReader, PdfWriter

reader = PdfReader("input.pdf")
writer = PdfWriter()

for page in reader.pages:
    writer.add_page(page)

# 添加密码
writer.encrypt("userpassword", "ownerpassword")

with open("encrypted.pdf", "wb") as output:
    writer.write(output)
```

## 快速参考

| 任务 | 最佳工具 | 命令/代码 |
|------|----------|-----------|
| 合并 PDF | pypdf | `writer.add_page(page)` |
| 拆分 PDF | pypdf | 每页一个文件 |
| 提取文本 | pdfplumber | `page.extract_text()` |
| 提取表格 | pdfplumber | `page.extract_tables()` |
| 创建 PDF | reportlab | Canvas 或 Platypus |
| 命令行合并 | qpdf | `qpdf --empty --pages ...` |
| 扫描 PDF OCR | pytesseract | 先转换为图像 |
| 填写 PDF 表单 | pdf-lib 或 pypdf（参见 FORMS.md） | 参见 FORMS.md |

## 后续步骤

- 有关高级 pypdfium2 用法，请参阅 REFERENCE.md
- 有关 JavaScript 库（pdf-lib），请参阅 REFERENCE.md
- 如果需要填写 PDF 表单，请按照 FORMS.md 中的说明操作
- 有关故障排除指南，请参阅 REFERENCE.md
