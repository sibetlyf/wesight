---
name: web-reader
description: |
  Extract structured data from any URL while evading bot detection. Use this skill when the user needs to scrape web pages, extract specific data fields, bypass CAPTCHAs, or build web scraping applications that avoid anti-bot detection. Features stealth browser automation, CSS/XPath extraction, proxy rotation, and human-like behavior simulation. Special support for tough sites like xiaohongshu (小红书), douyin, and other Chinese platforms that require mobile app emulation. Trigger phrases: "scrape this page", "extract data from URL", "bypass captcha", "read this webpage", "crawl website", "get structured data from", "xiaohongshu", "小红书".
license: MIT
---

# Web Reader Skill

Advanced web scraping skill with anti-bot detection evasion. Extracts structured data from any URL using stealth browser automation.

## Tech Stack

- **Playwright** — Headless browser automation
- **playwright-stealth** — Hides automation signals
- **CSS/XPath selectors** — Structured data extraction
- **Proxy rotation** — IP diversity for evading blocks

## Quick Start

### Installation

```bash
pip install playwright playwright-stealth httpx
playwright install chromium
```

### Basic Usage

```bash
# Read a simple page
python scripts/web-reader.py --url "https://example.com"

# Extract with CSS selector
python scripts/web-reader.py --url "https://news.ycombinator.com" --selector ".titleline > a -> titles"

# XPath extraction
python scripts/web-reader.py --url "https://example.com" --xpath "//div[@class='content']"

# Full page with stealth
python scripts/web-reader.py --url "https://example.com" --stealth --timeout 30
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

## Core Features

### 1. Stealth Browser Automation

Avoids bot detection through multiple layers:

```python
from web_reader import WebReader

# Enable all stealth features
reader = WebReader(
    stealth=True,           # Apply stealth plugin
    user_agent_rotation=True,  # Rotate User-Agent
    random_delay=True,      # Human-like delays
    proxy_rotation=True     # Rotate proxies
)

# Read without triggering bots
result = reader.read("https://protected-site.com")
```

### 2. Structured Data Extraction

Extract specific data using CSS or XPath selectors:

```python
# CSS selector for structured data
result = reader.read(
    url="https://shop.example.com/products",
    selector=".product-card h2, .product-card .price, .product-card img"
)

# XPath for complex patterns
result = reader.read(
    url="https://jobs.example.com",
    xpath="//div[@class='job-listing']//span[@class='salary']"
)
```

### 3. Site-Specific Extractors

Pre-built extractors for common sites:

```python
from web_reader.extractors import NewsExtractor, ProductExtractor, JobExtractor

# News articles
news = NewsExtractor(reader)
articles = news.extract("https://news.example.com/tech")

# E-commerce products
products = ProductExtractor(reader)
items = products.extract("https://shop.example.com/laptops")

# Job listings
jobs = JobExtractor(reader)
listings = jobs.extract("https://jobs.example.com/software")
```

### 4. Proxy Rotation

Avoid IP-based blocking:

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

### 5. CAPTCHA Handling

Graceful handling when CAPTCHA encountered:

```python
result = reader.read(
    url="https://site.example.com",
    handle_captcha=True,  # Will retry with new proxy/IP
    max_retries=3
)

if result.captcha_detected:
    print("CAPTCHA encountered, trying alternative...")
```

## Command Line Interface

### Basic Options

| Option | Description | Default |
|--------|-------------|---------|
| `--url` | Target URL (required) | - |
| `--selector` | CSS selector for extraction | body |
| `--xpath` | XPath selector | - |
| `--stealth` | Enable stealth mode | False |
| `--timeout` | Page load timeout (seconds) | 30 |
| `--wait` | Wait after load (seconds) | 2 |

### Advanced Options

| Option | Description | Default |
|--------|-------------|---------|
| `--proxy` | Single proxy URL | - |
| `--proxy-file` | File with proxy list | - |
| `--user-agent` | Custom User-Agent | Random |
| `--delay` | Random delay range | 1-3s |
| `--retry` | Max retry attempts | 3 |
| `--output` | Output file (JSON) | stdout |
| `--screenshot` | Save screenshot | - |

### Examples

```bash
# Simple page read
python scripts/web-reader.py --url "https://example.com"

# Extract headlines
python scripts/web-reader.py \
  --url "https://news.example.com" \
  --selector "h1.headline, .article-body p"

# Full stealth with proxy
python scripts/web-reader.py \
  --url "https://protected.site.com" \
  --stealth \
  --proxy-file proxies.txt \
  --output result.json

# Screenshot for debugging
python scripts/web-reader.py \
  --url "https://example.com" \
  --screenshot page.png

# Multi-selector extraction
python scripts/web-reader.py \
  --url "https://shop.example.com" \
  --selector "h1 -> title" \
  --selector ".price -> price" \
  --selector "img -> images" \
  --output products.json
```

## Extraction Syntax

### CSS Selector Format

```
selector -> field_name
```

Multiple selectors separated by newlines or commas.

### XPath Format

Standard XPath 1.0 expressions.

### Output Formats

**JSON output structure:**

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

## Best Practices

### 1. Always Use Stealth Mode

```python
# ✅ Good - stealth enabled
reader = WebReader(stealth=True)

# ❌ Bad -容易被检测
reader = WebReader(stealth=False)
```

### 2. Add Random Delays

```python
# ✅ Good - human-like timing
reader = WebReader(
    random_delay=True,
    min_delay=1,
    max_delay=5
)

# ❌ Bad - too fast
reader = WebReader(random_delay=False)
```

### 3. Rotate Proxies for Sensitive Sites

```python
# ✅ Good - IP diversity
reader = WebReader(
    proxies=["http://p1:8080", "http://p2:8080"],
    proxy_rotation=True
)

# ❌ Bad - single IP, easily blocked
reader = WebReader(proxies=["http://single:8080"])
```

### 4. Handle Errors Gracefully

```python
try:
    result = reader.read(url, timeout=30, retry=3)
except ExtractionError as e:
    print(f"Failed: {e}")
    # Fallback to alternative method
```

### 5. Respect Rate Limits

```python
# Space out requests
for url in urls:
    result = reader.read(url)
    time.sleep(random.uniform(3, 8))  # 3-8 seconds between requests
```

## Advanced Usage

### Custom Stealth Configuration

```python
from playwright_stealth import stealth_questions

reader = WebReader(stealth=True)

# Override specific stealth settings
reader.browser_context.set_extra_http_headers({
    "Accept-Language": "en-US,en;q=0.9"
})
```

### JavaScript Execution

```python
result = reader.read(url)

# Execute custom JS for dynamic content
reader.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
reader.page.wait_for_timeout(1000)

# Re-extract after scroll
new_result = reader.extract_text("article")
```

### Session Management

```python
# Maintain cookies across requests
reader = WebReader(stealth=True)

# Login
reader.page.goto("https://site.example.com/login")
reader.page.fill("#username", "user")
reader.page.fill("#password", "pass")
reader.page.click("button[type='submit']")

# Use session for subsequent requests
result = reader.read("https://site.example.com/protected")
```

### Waiting Strategies

```python
# Wait for specific elements
result = reader.read(
    url="https://spa.example.com",
    wait_for="div.content-loaded",
    wait_timeout=10
)

# Wait for network idle
result = reader.read(
    url="https://lazy.example.com",
    wait_until="networkidle"
)
```

## Error Handling

### Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `StealthDetectionError` | Bot detected | Increase stealth, use proxy |
| `CAPTCHADetectedError` | CAPTCHA challenge | Retry with new proxy/IP |
| `TimeoutError` | Page load slow | Increase timeout |
| `ProxyError` | Proxy failed | Use different proxy |
| `SelectorError` | Invalid selector | Check selector syntax |

### Retry Logic

```python
reader = WebReader(
    max_retries=3,
    retry_delay=5,
    retry_backoff=2  # Exponential backoff
)

for url in urls:
    result = reader.read_with_retry(url)
```

## Ethical Guidelines

1. **Respect robots.txt** — Check and honor site directives
2. **Rate limiting** — Don't overwhelm servers
3. **Terms of Service** — Check before scraping
4. **Personal data** — Don't collect without consent
5. **Legal use** — Only for legitimate purposes

```python
# Check robots.txt
from web_reader.robots import RobotsChecker

checker = RobotsChecker()
if checker.can_fetch("https://example.com/allowed"):
    result = reader.read("https://example.com/allowed")
else:
    print("Blocked by robots.txt")
```

## Performance Tips

1. **Batch processing** — Use `read_batch()` for multiple URLs
2. **Connection pooling** — Reuse browser instances
3. **Selective extraction** — Only get needed fields
4. **Caching** — Cache frequently accessed pages

```python
# Batch processing with progress
results = reader.read_batch(
    urls=["https://a.com", "https://b.com", "https://c.com"],
    concurrency=3,  # Parallel requests
    callback=lambda r: print(f"Done: {r.url}")
)
```

## Integrations

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

## Troubleshooting

### Bot Still Detected?

1. Enable full stealth mode
2. Add more proxies
3. Increase delay between requests
4. Use residential proxies
5. Try different User-Agent

### CAPTCHA Always Shows?

1. Use premium proxies (residential)
2. Slower request cadence
3. Rotate more IPs
4. Consider CAPTCHA solving service

### Slow Performance?

1. Reduce timeout
2. Use simpler selectors
3. Disable screenshot
4. Reduce concurrency

## Remember

- **Always use stealth mode** for sensitive sites
- **Rotate proxies** to avoid IP bans
- **Add delays** to mimic human behavior
- **Handle errors** with retry logic
- **Respect rate limits** and robots.txt
- **Use specific selectors** for faster extraction

## Special: Difficult Sites (Xiaohongshu, Douyin, etc.)

Some sites like xiaohongshu (小红书) have strong anti-bot protections. They may show "请在客户端查看" or redirect to app download pages.

### For Xiaohongshu specifically:

#### Method 1: Browser Automation (Basic Scraping)

```bash
python scripts/web-reader.py --url "https://www.xiaohongshu.com/discovery/item/XXXXX" --stealth --timeout 60
```

#### Method 2: Signed API with Auto-Cookie (Recommended)

Automatically extracts cookies from your logged-in browser and uses xhshow for API signature generation:

```bash
# Auto-extract cookies from browser (Chrome/Edge/Firefox)
python scripts/web-reader.py \
  --url "https://www.xiaohongshu.com/explore/XXXXX?xsec_token=YYY" \
  --xhs \
  --auto-cookie

# Or disable auto-cookie and provide manually
python scripts/web-reader.py \
  --url "https://www.xiaohongshu.com/explore/XXXXX?xsec_token=YYY" \
  --xhs \
  --xhs-cookie "a1=xxx;webId=xxx;web_session=xxx"
```

**Requirements:**
- Browser must be logged into xiaohongshu.com
- Cookie extraction requires `browser-cookie3` library
- URL must include `xsec_token` parameter

**Supported Browsers:** Chrome, Chromium, Edge, Brave, Opera, Vivaldi, Firefox

#### How to Get Cookies Manually:

1. Open browser and log into https://www.xiaohongshu.com
2. Press F12 → Application → Cookies
3. Copy required cookies: `a1`, `webId`, `web_session`
4. Format: `--xhs-cookie "a1=xxx;webId=xxx;web_session=xxx"`

#### Method 3: XHS-Downloader

For full functionality (video downloads, user profiles), use the dedicated [XHS-Downloader](https://github.com/JoeanAmier/XHS-Downloader) project which provides:
- Tampermonkey userscript for in-browser extraction
- Python downloader for batch processing
- Cookie-based authentication
