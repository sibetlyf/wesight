---
name: zhihu-scraper
description: |
  Extract content from zhihu.com (知乎) using stealth browser automation with automatic popup and login modal handling. Use this skill when the user needs to scrape zhihu articles, answers, questions, or profiles while preventing login popups from blocking content extraction. Features incognito mode, intelligent popup detection, automatic dismissal of login/modals/agreements, and structured data extraction. Trigger phrases: "抓取知乎", "scrape zhihu", "知乎内容", "zhihu article", "知乎回答", "zhihu answer", "知乎问题", "zhihu question", "知乎用户", "zhihu user", "知乎专栏", "zhihu column".
license: MIT
---

# Zhihu Scraper Skill

Advanced zhihu.com content extraction skill with stealth browser automation and intelligent popup handling.

## Tech Stack

- **Playwright** — Headless browser automation with incognito mode
- **playwright-stealth** — Hides automation signals to avoid detection
- **Intelligent Popup Detection** — Auto-detects and dismisses login modals, agreements, and notifications
- **CSS/XPath selectors** — Structured data extraction

## Quick Start

### Installation

```bash
pip install playwright playwright-stealth httpx
playwright install chromium
```

### Basic Usage

```bash
# Extract article content
python scripts/zhihu_scraper.py --url "https://www.zhihu.com/question/12345678"

# Extract answer content
python scripts/zhihu_scraper.py --url "https://www.zhihu.com/question/12345678/answer/987654321"

# Extract user profile
python scripts/zhihu_scraper.py --url "https://www.zhihu.com/people/username"
```

### Python API

```python
import asyncio
from zhihu_scraper import ZhihuScraper

async def main():
    async with ZhihuScraper(incognito=True) as scraper:
        result = await scraper.scrape(
            url="https://www.zhihu.com/question/12345678",
            content_type="question"
        )
        print(result.title, result.content)

asyncio.run(main())
```

## Core Features

### 1. Incognito Mode

Always use incognito mode to avoid login state interference:

```python
from zhihu_scraper import ZhihuScraper

# Enable incognito mode
scraper = ZhihuScraper(
    incognito=True,  # Always use incognito
    stealth=True     # Enable stealth
)

# Read without being logged in
result = scraper.scrape("https://www.zhihu.com/question/12345678")
```

### 2. Intelligent Popup Handling

Automatically detects and dismisses various popups:

```python
scraper = ZhihuScraper(
    auto_close_popups=True,  # Auto-close modals
    popup_timeout=5          # Timeout for popup detection
)

# The scraper will automatically handle:
# - Login modals (登录弹窗)
# - Agreement dialogs (用户协议)
# - Notification prompts (通知提示)
# - QR code login windows (二维码登录)
# - Cookie consent banners (Cookie同意)
```

### 3. Popup Detection Patterns

The scraper recognizes these common zhihu popups:

| Popup Type | Selectors | Action |
|------------|-----------|--------|
| Login Modal | `.Modal-wrapper`, `.SignFlow`, `.Login-modal` | Click outside or press Escape |
| Agreement | `.AgreementModal`, `.PrivacyDialog` | Click "同意" or "I agree" |
| Notification | `.NotificationModal`, `.PushPermission` | Click "不允许" or deny |
| QR Code | `.QRCodeLogin`, `.LoginQRCode` | Click close button |
| Cookie Banner | `.CookieConsent`, `.CookieBanner` | Click "知道了" or accept |

### 4. Content Extraction

Extract various content types from zhihu:

```python
from zhihu_scraper import ZhihuScraper, ContentType

scraper = ZhihuScraper()

# Question content
question = await scraper.scrape(
    url="https://www.zhihu.com/question/12345678",
    content_type=ContentType.QUESTION
)

# Answer content
answer = await scraper.scrape(
    url="https://www.zhihu.com/question/12345678/answer/987654321",
    content_type=ContentType.ANSWER
)

# User profile
profile = await scraper.scrape(
    url="https://www.zhihu.com/people/username",
    content_type=ContentType.USER
)

# Article/Column
article = await scraper.scrape(
    url="https://www.zhihu.com/p/12345678",
    content_type=ContentType.ARTICLE
)
```

## Command Line Interface

### Basic Options

| Option | Description | Default |
|--------|-------------|---------|
| `--url` | Target zhihu URL (required) | - |
| `--type` | Content type: question/answer/user/article | auto-detect |
| `--output`, `-o` | Output JSON file | zhihu_output.json |
| `--output-dir`, `-d` | Output directory | current directory |
| `--download-images` | Download all images to output directory | false |
| `--screenshot` | Save screenshot | - |

### Advanced Options

| Option | Description | Default |
|--------|-------------|---------|
| `--incognito` | Use incognito mode | True |
| `--stealth` | Enable stealth mode | True |
| `--no-popup-close` | Disable auto popup closing | False |
| `--timeout` | Page load timeout (seconds) | 30 |
| `--wait` | Additional wait after load (seconds) | 10 |
| `--headless` | Run in headless mode | **False** (重要: 知乎会检测headless模式) |

### Examples

```bash
# Extract article (默认保存到当前目录)
python scripts/zhihu_scraper.py \
  --url "https://zhuanlan.zhihu.com/p/416200448"

# Extract article with output directory (保存到指定目录)
python scripts/zhihu_scraper.py \
  --url "https://zhuanlan.zhihu.com/p/416200448" \
  --output-dir "./output"

# Extract article and download images
python scripts/zhihu_scraper.py \
  --url "https://zhuanlan.zhihu.com/p/416200448" \
  --output-dir "./output" \
  --download-images

# Extract article with more wait time (更稳定)
python scripts/zhihu_scraper.py \
  --url "https://zhuanlan.zhihu.com/p/416200448" \
  --output-dir "./output" \
  --wait 15

# Extract question with answers
python scripts/zhihu_scraper.py \
  --url "https://www.zhihu.com/question/12345678" \
  --output-dir "./output"

# Extract specific answer
python scripts/zhihu_scraper.py \
  --url "https://www.zhihu.com/question/12345678/answer/987654321" \
  --output-dir "./output"

# Extract user profile
python scripts/zhihu_scraper.py \
  --url "https://www.zhihu.com/people/username" \
  --output-dir "./output"

# With screenshot for debugging
python scripts/zhihu_scraper.py \
  --url "https://www.zhihu.com/question/12345678" \
  --output-dir "./output" \
  --screenshot debug.png
```

> ⚠️ **重要**: 知乎会检测headless模式，建议使用默认参数（显示浏览器窗口）。如果必须使用headless模式，成功率会显著降低。

## Output Formats

### Question Output

```json
{
  "type": "question",
  "url": "https://www.zhihu.com/question/12345678",
  "title": "问题标题",
  "content": "问题详细内容...",
  "author": {
    "name": "用户名",
    "url": "https://www.zhihu.com/people/username",
    "headline": "用户简介"
  },
  "created_time": "2024-01-01T00:00:00Z",
  "updated_time": "2024-01-02T00:00:00Z",
  "answer_count": 42,
  "followers": 1234,
  "views": 56789,
  "tags": ["标签1", "标签2"],
  "answers": [
    {
      "id": "answer_123",
      "author": {...},
      "content": "回答内容...",
      "vote_count": 100,
      "created_time": "..."
    }
  ]
}
```

### Answer Output

```json
{
  "type": "answer",
  "url": "https://www.zhihu.com/question/12345678/answer/987654321",
  "question_title": "问题标题",
  "content": "回答详细内容...",
  "author": {
    "name": "用户名",
    "url": "https://www.zhihu.com/people/username",
    "headline": "用户简介",
    "avatar": "https://头像URL"
  },
  "vote_count": 250,
  "comment_count": 15,
  "created_time": "2024-01-01T00:00:00Z",
  "updated_time": "2024-01-02T00:00:00Z"
}
```

### User Profile Output

```json
{
  "type": "user",
  "url": "https://www.zhihu.com/people/username",
  "name": "用户名",
  "headline": "个人简介",
  "avatar": "https://头像URL",
  "gender": "male",
  "location": "北京",
  "business": "互联网",
  "education": "清华大学",
  "following_count": 250,
  "follower_count": 1200,
  "following_topic_count": 50,
  "following_column_count": 10,
  "accepted_answer_count": 15,
  "知乎盐值": 650,
  "description": "详细个人描述..."
}
```

## How Popup Detection Works

### Step 1: Pre-load Popup Patterns

The scraper loads known popup selectors at initialization:

```python
POPUP_SELECTORS = [
    # Login modals
    ".Modal-wrapper",
    ".SignFlow",
    ".Login-modal",
    ".Login-content",
    
    # Agreement dialogs
    ".AgreementModal",
    ".PrivacyDialog",
    ".UserAgreement",
    
    # QR code login
    ".QRCodeLogin",
    ".LoginQRCode",
    ".qrcode-login",
    
    # Notification prompts
    ".NotificationModal",
    ".PushPermission",
    ".app-download-modal",
    
    # Cookie banners
    ".CookieConsent",
    ".CookieBanner",
    ".cookie-agreement"
]
```

### Step 2: Detect Popups After Page Load

After navigating to the page, check for popups:

```python
async def detect_and_close_popups(page):
    for selector in POPUP_SELECTORS:
        popup = await page.query_selector(selector)
        if popup and await popup.is_visible():
            # Click outside to close or press Escape
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(500)
            
            # Try clicking close button if exists
            close_btn = await page.query_selector(
                ".Modal-closeButton, .SignFlowClose, .close"
            )
            if close_btn:
                await close_btn.click()
```

### Step 3: Wait and Re-check

After closing initial popups, wait and re-check:

```python
async def handle_popups(page):
    # First round
    await detect_and_close_popups(page)
    
    # Wait for potential delayed popups
    await page.wait_for_timeout(2000)
    
    # Second round
    await detect_and_close_popups(page)
```

## Best Practices

### 1. Use Visible Browser Window (重要!)

```python
# ✅ Good - 知乎不检测正常浏览器
scraper = ZhihuScraper(headless=False)  # 默认

# ❌ Bad - 知乎会检测headless并拦截
scraper = ZhihuScraper(headless=True)
```

### 2. Always Use Incognito Mode

```python
# ✅ Good - clean state
scraper = ZhihuScraper(incognito=True)

# ❌ Bad - may have logged-in state interference
scraper = ZhihuScraper(incognito=False)
```

### 3. Enable Stealth Mode

```python
# ✅ Good - avoid detection
scraper = ZhihuScraper(stealth=True)

# ❌ Bad -容易被检测为机器人
scraper = ZhihuScraper(stealth=False)
```

### 4. Let Popup Handler Run

```python
# ✅ Good - auto handle popups
scraper = ZhihuScraper(auto_close_popups=True)

# ❌ Bad - popups will block content
scraper = ZhihuScraper(auto_close_popups=False)
```

### 5. Add Appropriate Delays

```python
# ✅ Good - wait for content to load
result = await scraper.scrape(
    url="https://www.zhihu.com/question/12345678",
    wait_for_selector=".List-item",  # Wait for answers to load
    wait_timeout=15
)

# ❌ Bad - may get empty content
result = await scraper.scrape(url, wait_for_selector=None)
```

### 6. Handle Rate Limits

```python
# Space out requests to avoid rate limiting
for url in urls:
    result = await scraper.scrape(url)
    await asyncio.sleep(random.uniform(3, 8))  # 3-8 seconds between requests
```

## Error Handling

### Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `PopupBlockError` | Login modal blocks content | Increase popup_timeout, check selectors |
| `ContentLoadError` | Page content not loaded | Increase wait time, check selector |
| `StealthDetectionError` | Bot detected | Enable stealth mode, use proxy |
| `TimeoutError` | Page load slow | Increase timeout |
| `SelectorError` | Invalid selector | Check selector syntax |

### Retry Logic

```python
scraper = ZhihuScraper(
    max_retries=3,
    retry_delay=5,
    retry_backoff=2
)

for url in urls:
    result = await scraper.scrape_with_retry(url)
```

## Advanced Usage

### Custom Popup Patterns

Add custom popup selectors:

```python
scraper = ZhihuScraper(
    custom_popup_selectors=[
        ".my-custom-popup",
        "#special-modal",
        "[data-testid='popup']"
    ]
)
```

### Scroll for Dynamic Content

Zhihu loads more content as you scroll:

```python
async def scroll_and_extract(page):
    # Scroll to load more answers
    for _ in range(5):
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(1000)
    
    # Now extract all loaded content
    content = await page.evaluate("""
        Array.from(document.querySelectorAll('.List-item')).map(item => 
            item.innerText
        ).join('\\n')
    """)
    return content
```

### Extract Multiple Questions from Feed

```python
async def scrape_feed(scraper, feed_url):
    await scraper.goto(feed_url)
    
    # Extract question links
    links = await scraper.page.evaluate("""
        Array.from(document.querySelectorAll('.List-item a[href*="/question/"]'))
            .map(a => a.href)
    """)
    
    results = []
    for link in links:
        result = await scraper.scrape(link)
        results.append(result)
        await asyncio.sleep(random.uniform(2, 5))
    
    return results
```

## Integration Examples

### With FastAPI

```python
from fastapi import FastAPI
from zhihu_scraper import ZhihuScraper

app = FastAPI()

@app.get("/api/zhihu/scrape")
async def scrape_zhihu(url: str):
    async with ZhihuScraper(incognito=True, stealth=True) as scraper:
        result = await scraper.scrape(url)
        return result.dict()
```

### Batch Processing

```python
import asyncio
from zhihu_scraper import ZhihuScraper

async def batch_scrape(urls):
    async with ZhihuScraper(incognito=True) as scraper:
        tasks = []
        for url in urls:
            task = scraper.scrape(url)
            tasks.append(task)
            await asyncio.sleep(2)  # Rate limiting
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return results

urls = [
    "https://www.zhihu.com/question/123",
    "https://www.zhihu.com/question/456",
    "https://www.zhihu.com/question/789"
]

results = asyncio.run(batch_scrape(urls))
```

## Troubleshooting

### 重定向到安全验证页面?

**这是最主要的问题！知乎会检测headless模式。**

解决方案：
1. ✅ 使用默认参数 `headless=False` (显示浏览器窗口)
2. ✅ 增加等待时间 `--wait 15`
3. ✅ 如果必须headless，成功率会显著降低

### Login Modal Still Appears?

1. Check if selectors are still valid (zhihu may update their UI)
2. Increase popup detection timeout
3. Try pressing Escape multiple times
4. Check if page is redirected to login

### Content Not Loading?

1. Enable screenshot to see what's happening
2. Check if wait time is sufficient (建议15秒)
3. Try scrolling to trigger lazy loading
4. Check network requests for errors

### Bot Detection?

1. ✅ 使用 `headless=False` (最重要!)
2. ✅ 增加等待时间 `--wait 15`
3. Try using a proxy
4. Increase delays between requests

### Getting Old/Cached Content?

1. Clear browser context
2. Add cache-busting parameter: `?t={timestamp}`
3. Use incognito mode to avoid cached login state

## Ethical Guidelines

1. **Respect rate limits** — Don't overwhelm zhihu servers
2. **Personal use only** — Don't redistribute scraped content
3. **No authentication bypass** — Don't try to access paid content
4. **Terms of Service** — Check zhihu's terms before scraping
5. **Attribution** — Credit zhihu and original authors when sharing

## Remember

- **Always use incognito mode** for clean browser state
- **Enable stealth mode** to avoid bot detection
- **Let popup handler run** to auto-close login modals
- **Add delays** to mimic human behavior
- **Handle errors** with retry logic
- **Scroll for more content** on lazy-loaded pages

## Special Notes for Zhihu

### Common URL Patterns

| Type | URL Pattern |
|------|-------------|
| Question | `/question/{id}` |
| Answer | `/question/{id}/answer/{answer_id}` |
| User | `/people/{username}` |
| Article | `/p/{id}` |
| Column | `/column/{id}` |
| Collection | `/collection/{id}` |
| Search | `/search?q={keyword}` |

### Content That Requires Login

Some content may require authentication:
- Private answers
- Paid content
- Some followee-only content

For these, you may need to provide cookies from a logged-in session.
