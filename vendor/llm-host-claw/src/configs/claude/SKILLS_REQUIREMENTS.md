# Skill 环境安装指南

> 支持 Windows / macOS / Linux


---

## 二、Python 环境安装

### Windows

```powershell
# 1. 安装 Python (如未安装)
# 下载: https://www.python.org/downloads/
# 建议 3.10+

# 2. 安装核心依赖
pip install playwright playwright-stealth httpx pychrome

# 3. 安装文档处理库
pip install python-docx lxml python-pptx openpyxl pandas pypdf pdfplumber reportlab

# 4. 安装 Chromium 浏览器
playwright install chromium
```

### macOS

```bash
# 1. 如果没有 Python，先安装 (使用 Homebrew)
brew install python3

# 2. 安装依赖
pip3 install playwright playwright-stealth httpx pychrome
pip3 install python-docx lxml python-pptx openpyxl pandas pypdf pdfplumber reportlab

# 3. 安装浏览器
playwright install chromium
```

### Linux (Ubuntu/Debian)

```bash
# 1. 安装 Python 和依赖
sudo apt update
sudo apt install python3 python3-pip

# 2. 安装系统依赖
sudo apt install libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2

# 3. 安装 Python 包
pip3 install playwright playwright-stealth httpx pychrome
pip3 install python-docx lxml python-pptx openpyxl pandas pypdf pdfplumber reportlab

# 4. 安装浏览器
playwright install chromium
playwright install-deps  # 安装系统级依赖
```

---

## 三、Node.js 环境安装

### 所有平台通用

```bash
# 1. 确保已安装 Node.js
node --version  # 推荐 18+

# 2. MCP Servers (按需运行，无需全局安装)

# 媒体生成
npx -y fal-ai-mcp-server

# 深度研究/网页抓取
npx -y firecrawl-mcp-server
```

---

## 四、可选系统工具

### Linux

```bash
# PDF 处理 (Ubuntu/Debian)
sudo apt install poppler-utils qpdf pdftk libreoffice

# OCR 支持 (可选)
sudo apt install tesseract-ocr
```

### macOS

```bash
# 使用 Homebrew
brew install poppler qpdf pdftk
brew install --cask libreoffice
brew install tesseract
```

### Windows

- **PDF**: 建议使用 Python 包，无需额外安装
- **LibreOffice**: https://www.libreoffice.org/download/download/
- **Tesseract**: https://github.com/UB-Mannheim/tesseract/wiki
---

## 六、验证安装

```bash
# Python 版本
python --version

# Playwright
python -c "from playwright.async_api import async_playwright; print('OK')"

# 文档库
python -c "import docx; import pptx; import openpyxl; print('OK')"
python -c "import pypdf; import pdfplumber; print('OK')"

# MCP Servers
npx -y fal-ai-mcp-server --version
npx -y exa-mcp-server --version
```

---

## 七、按 Skill 速查

### 🕷️ 网页抓取 (zhihu-scraper, web-reader)

```bash
pip install playwright playwright-stealth httpx
playwright install chromium
```

### 📄 文档处理 (docx, pdf, pptx, xlsx)

```bash
pip install python-docx lxml python-pptx openpyxl pandas pypdf pdfplumber reportlab
```

### 🔍 搜索与研究 (exa-search, deep-research, web-search)

```bash
npx -y exa-mcp-server
npx -y firecrawl-mcp-server  # 可选
```

### 🎨 媒体生成 (fal-ai-media)

```bash
npx -y fal-ai-mcp-server
```

### 🧪 测试 (cdp-browser, webapp-testing, e2e-testing)

```bash
pip install pychrome playwright
playwright install chromium
```

