---
name: web-reader
description: |
  从任何 URL 提取结构化数据，同时规避机器人检测。当用户需要抓取网页、提取特定数据字段、绕过验证码或构建避免反机器人检测的网页抓取应用时使用。具有隐身浏览器自动化、CSS/XPath 提取、代理轮换和类人行为模拟功能。触发短语："抓取此页面"、"从 URL 提取数据"、"绕过验证码"、"读取此网页"、"爬取网站"、"从中获取结构化数据"。
license: MIT
---

# 网页读取技能

具有反机器人检测规避功能的高级网页抓取技能。使用隐身浏览器自动化从任何 URL 提取结构化数据。

## 技术栈

- **Playwright** — 无头浏览器自动化
- **playwright-stealth** — 隐藏自动化信号
- **CSS/XPath 选择器** — 结构化数据提取
- **代理轮换** — IP 多样性以规避封锁

## 快速开始

### 安装

需要的依赖：`playwright playwright-stealth httpx`

安装 Playwright 浏览器：`playwright install chromium`

### 基本用法

**读取简单页面：**
```bash
python3 ${SKILL_DIR}/scripts/web-reader.py --url "https://example.com"
```

**使用 CSS 选择器提取：**
```bash
python3 ${SKILL_DIR}/scripts/web-reader.py --url "https://news.ycombinator.com" --selector ".titleline > a -> titles"
```

**XPath 提取：**
```bash
python3 ${SKILL_DIR}/scripts/web-reader.py --url "https://example.com" --xpath "//div[@class='content']"
```

**带隐身的完整页面：**
```bash
python3 ${SKILL_DIR}/scripts/web-reader.py --url "https://example.com" --stealth --timeout 30
```

### Python API

```python
import asyncio
from web_reader import WebReader

async def main():
    async with WebReader(stealth=True) as reader:
        result = await reader.read(
            url="https://example.com",
            selector="h1 -> title"
        )
        print(result.title, result.fields)

asyncio.run(main())
```

## 核心功能

### 1. 隐身浏览器自动化

通过多层避免机器人检测：

```python
from web_reader import WebReader

# 启用所有隐身功能
reader = WebReader(
    stealth=True,           # 应用隐身插件
    user_agent_rotation=True,  # 轮换 User-Agent
    random_delay=True,      # 类人延迟
    proxy_rotation=True     # 轮换代理
)

# 读取而不触发机器人
result = reader.read("https://protected-site.com")
```

### 2. 结构化数据提取

使用 CSS 或 XPath 选择器提取特定数据：

```python
# 结构化数据的 CSS 选择器
result = reader.read(
    url="https://shop.example.com/products",
    selector=".product-card h2, .product-card .price, .product-card img"
)

# 复杂模式的 XPath
result = reader.read(
    url="https://jobs.example.com",
    xpath="//div[@class='job-listing']//span[@class='salary']"
)
```

### 3. 站点特定提取器

为常见站点预建的提取器：

```python
from web_reader.extractors import NewsExtractor, ProductExtractor, JobExtractor

# 新闻文章
news = NewsExtractor(reader)
articles = news.extract("https://news.example.com/tech")

# 电商产品
products = ProductExtractor(reader)
items = products.extract("https://shop.example.com/laptops")

# 职位列表
jobs = JobExtractor(reader)
listings = jobs.extract("https://jobs.example.com/software")
```

### 4. 代理轮换

避免基于 IP 的封锁：

```python
reader = WebReader(
    proxies=[
        "http://proxy1:8080",
        "http://proxy2:8080",
        "http://proxy3:8080"
    ],
    proxy_rotation=True
)
```

### 5. 验证码处理

遇到验证码时优雅处理：

```python
result = reader.read(
    url="https://site.example.com",
    handle_captcha=True,  # 将使用新代理/IP 重试
    max_retries=3
)

if result.captcha_detected:
    print("遇到验证码，尝试替代方案...")
```

## 命令行接口

### 基本选项

| 选项 | 说明 | 默认值 |
|------|------|--------|
| `--url` | 目标 URL（必需） | - |
| `--selector` | 提取的 CSS 选择器 | body |
| `--xpath` | XPath 选择器 | - |
| `--stealth` | 启用隐身模式 | False |
| `--timeout` | 页面加载超时（秒） | 30 |
| `--wait` | 加载后等待（秒） | 2 |

### 高级选项

| 选项 | 说明 | 默认值 |
|------|------|--------|
| `--proxy` | 单个代理 URL | - |
| `--proxy-file` | 代理列表文件 | - |
| `--user-agent` | 自定义 User-Agent | 随机 |
| `--delay` | 随机延迟范围 | 1-3秒 |
| `--retry` | 最大重试次数 | 3 |
| `--output` | 输出文件（JSON） | stdout |
| `--screenshot` | 保存截图 | - |

### 示例

```bash
# 简单页面读取
python scripts/web-reader.py --url "https://example.com"

# 提取标题
python scripts/web-reader.py \
  --url "https://news.example.com" \
  --selector "h1.headline, .article-body p"

# 带代理的完整隐身
python scripts/web-reader.py \
  --url "https://protected.site.com" \
  --stealth \
  --proxy-file proxies.txt \
  --output result.json

# 调试截图
python scripts/web-reader.py \
  --url "https://example.com" \
  --screenshot page.png

# 多选择器提取
python scripts/web-reader.py \
  --url "https://shop.example.com" \
  --selector "h1 -> title" \
  --selector ".price -> price" \
  --selector "img -> images" \
  --output products.json
```

## 提取语法

### CSS 选择器格式

```
selector -> field_name
```

多个选择器用换行或逗号分隔。

### XPath 格式

标准 XPath 1.0 表达式。

### 输出格式

**JSON 输出结构：**

```json
{
  "url": "https://example.com",
  "title": "Page Title",
  "fields": {
    "title": "Extracted title text",
    "price": "$19.99",
    "images": ["url1.jpg", "url2.jpg"]
  },
  "text": "Full page text...",
  "html": "Raw HTML...",
  "metadata": {
    "stealth_used": true,
    "proxy_used": "http://proxy1:8080",
    "captcha_detected": false,
    "extraction_time_ms": 2340
  }
}
```

## 最佳实践

### 1. 始终使用隐身模式

```python
# ✅ 好 — 启用隐身
reader = WebReader(stealth=True)

# ❌ 不好 — 容易被检测
reader = WebReader(stealth=False)
```

### 2. 添加随机延迟

```python
# ✅ 好 — 类人时间
reader = WebReader(
    random_delay=True,
    min_delay=1,
    max_delay=5
)

# ❌ 不好 — 太快
reader = WebReader(random_delay=False)
```

### 3. 对敏感站点轮换代理

```python
# ✅ 好 — IP 多样性
reader = WebReader(
    proxies=["http://p1:8080", "http://p2:8080"],
    proxy_rotation=True
)

# ❌ 不好 — 单一 IP，容易被封
reader = WebReader(proxies=["http://single:8080"])
```

### 4. 优雅处理错误

```python
try:
    result = reader.read(url, timeout=30, retry=3)
except ExtractionError as e:
    print(f"Failed: {e}")
    # 回退到替代方法
```

### 5. 尊重速率限制

```python
# 间隔请求
for url in urls:
    result = reader.read(url)
    time.sleep(random.uniform(3, 8))  # 请求之间 3-8 秒
```

## 高级用法

### 自定义隐身配置

```python
from playwright_stealth import stealth_questions

reader = WebReader(stealth=True)

# 覆盖特定隐身设置
reader.browser_context.set_extra_http_headers({
    "Accept-Language": "en-US,en;q=0.9"
})
```

### JavaScript 执行

```python
result = reader.read(url)

# 为动态内容执行自定义 JS
reader.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
reader.page.wait_for_timeout(1000)

# 滚动后重新提取
new_result = reader.extract_text("article")
```

### 会话管理

```python
# 跨请求保持 cookie
reader = WebReader(stealth=True)

# 登录
reader.page.goto("https://site.example.com/login")
reader.page.fill("#username", "user")
reader.page.fill("#password", "pass")
reader.page.click("button[type='submit']")

# 使用会话进行后续请求
result = reader.read("https://site.example.com/protected")
```

### 等待策略

```python
# 等待特定元素
result = reader.read(
    url="https://spa.example.com",
    wait_for="div.content-loaded",
    wait_timeout=10
)

# 等待网络空闲
result = reader.read(
    url="https://lazy.example.com",
    wait_until="networkidle"
)
```

## 错误处理

### 常见错误

| 错误 | 原因 | 解决方案 |
|------|------|----------|
| `StealthDetectionError` | 机器人被检测 | 增强隐身，使用代理 |
| `CAPTCHADetectedError` | 验证码挑战 | 使用新代理/IP 重试 |
| `TimeoutError` | 页面加载慢 | 增加超时 |
| `ProxyError` | 代理失败 | 使用不同代理 |
| `SelectorError` | 选择器无效 | 检查选择器语法 |

### 重试逻辑

```python
reader = WebReader(
    max_retries=3,
    retry_delay=5,
    retry_backoff=2  # 指数退避
)

for url in urls:
    result = reader.read_with_retry(url)
```

## 道德准则

1. **尊重 robots.txt** — 检查并遵守站点指令
2. **速率限制** — 不要压垮服务器
3. **服务条款** — 抓取前检查
4. **个人数据** — 未经同意不要收集
5. **合法使用** — 仅用于合法目的

```python
# 检查 robots.txt
from web_reader.robots import RobotsChecker

checker = RobotsChecker()
if checker.can_fetch("https://example.com/allowed"):
    result = reader.read("https://example.com/allowed")
else:
    print("被 robots.txt 阻止")
```

## 性能提示

1. **批处理** — 对多个 URL 使用 `read_batch()`
2. **连接池** — 重用浏览器实例
3. **选择性提取** — 仅获取需要的字段
4. **缓存** — 缓存频繁访问的页面

```python
# 带进度的批处理
results = reader.read_batch(
    urls=["https://a.com", "https://b.com", "https://c.com"],
    concurrency=3,  # 并行请求
    callback=lambda r: print(f"Done: {r.url}")
)
```

## 集成

### Express.js API

```javascript
const express = require('express');
const { WebReader } = require('./web-reader-py');

const app = express();
app.use(express.json());

let reader;
const initReader = async () => {
  reader = new WebReader({ stealth: true });
};

app.post('/api/scrape', async (req, res) => {
  try {
    const { url, selector } = req.body;
    const result = await reader.read(url, { selector });
    res.json({ success: true, data: result });
  } catch (error) {
    res.status(500).json({ success: false, error: error.message });
  }
});
```

## 故障排除

### 仍被检测为机器人？

1. 启用完整隐身模式
2. 添加更多代理
3. 增加请求间隔
4. 使用住宅代理
5. 尝试不同的 User-Agent

### 总是显示验证码？

1. 使用高级代理（住宅）
2. 减慢请求节奏
3. 轮换更多 IP
4. 考虑验证码解决服务

### 性能慢？

1. 减少超时
2. 使用更简单的选择器
3. 禁用截图
4. 减少并发

## 记住

- **对敏感站点始终使用隐身模式**
- **轮换代理**以避免 IP 封禁
- **添加延迟**以模拟人类行为
- **用重试逻辑处理错误**
- **尊重速率限制和 robots.txt**
- **使用特定选择器**以更快提取
