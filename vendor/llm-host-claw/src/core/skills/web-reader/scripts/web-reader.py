#!/usr/bin/env python3
"""
Web Reader - Advanced web scraping with anti-bot detection evasion
Supports stealth browser automation, structured data extraction, and proxy rotation.
"""

# type: ignore

import argparse
import asyncio
import json
import random
import time
import sys
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Callable
from pathlib import Path

try:
    from playwright.async_api import async_playwright, Page, BrowserContext  # type: ignore
    import httpx  # type: ignore
    # Try to import stealth plugin
    try:
        from playwright_stealth.stealth import Stealth  # type: ignore
        STEALTH_AVAILABLE = True
    except ImportError:
        print("Note: playwright_stealth not installed. Stealth mode limited.")
        STEALTH_AVAILABLE = False
        Stealth = None  # type: ignore
except ImportError:
    print("Installing dependencies...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", 
                          "playwright", "httpx"])
    try:
        from playwright_stealth.stealth import Stealth  # type: ignore
        STEALTH_AVAILABLE = True
    except ImportError:
        STEALTH_AVAILABLE = False
        Stealth = None  # type: ignore
    from playwright.async_api import async_playwright, Page, BrowserContext  # type: ignore
    import httpx  # type: ignore


@dataclass
class ExtractionResult:
    """Result of web extraction."""
    url: str
    title: str = ""
    text: str = ""
    html: str = ""
    fields: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    captcha_detected: bool = False
    error: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return {
            "url": self.url,
            "title": self.title,
            "text": self.text,
            "html": self.html,
            "fields": self.fields,
            "metadata": self.metadata,
            "captcha_detected": self.captcha_detected,
            "error": self.error
        }


class ProxyManager:
    """Manages proxy rotation."""
    
    def __init__(self, proxies: Optional[List[str]] = None, proxy_file: Optional[str] = None):
        self.proxies = proxies or []
        self.current_index = 0
        
        if proxy_file:
            self._load_from_file(proxy_file)
    
    def _load_from_file(self, filepath: str):
        """Load proxies from file."""
        path = Path(filepath)
        if path.exists():
            with open(path) as f:
                self.proxies = [line.strip() for line in f if line.strip()]
    
    def get_next(self) -> Optional[str]:
        """Get next proxy in rotation."""
        if not self.proxies:
            return None
        proxy = self.proxies[self.current_index]
        self.current_index = (self.current_index + 1) % len(self.proxies)
        return proxy
    
    def random(self) -> Optional[str]:
        """Get random proxy."""
        if not self.proxies:
            return None
        return random.choice(self.proxies)


class WebReader:
    """
    Advanced web reader with anti-bot detection evasion.
    
    Features:
    - Stealth browser automation
    - User-Agent rotation
    - Proxy rotation
    - Random delays (human-like behavior)
    - Structured data extraction (CSS/XPath)
    - CAPTCHA handling
    """
    
    # Common User-Agents for rotation
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0",
    ]
    
    def __init__(
        self,
        stealth: bool = True,
        user_agent_rotation: bool = True,
        random_delay: bool = True,
        min_delay: float = 1.0,
        max_delay: float = 3.0,
        proxy_rotation: bool = False,
        proxies: Optional[List[str]] = None,
        proxy_file: Optional[str] = None,
        headless: bool = True,
        timeout: int = 30000,
        screenshot_dir: Optional[str] = None,
    ):
        self.stealth = stealth
        self.user_agent_rotation = user_agent_rotation
        self.random_delay = random_delay
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.proxy_rotation = proxy_rotation
        self.headless = headless
        self.timeout = timeout
        self.screenshot_dir = screenshot_dir
        
        # Initialize proxy manager
        self.proxy_manager = ProxyManager(proxies, proxy_file)
        
        # Browser instance (Optional for type checking)
        self.playwright: Optional[Any] = None
        self.browser: Optional[Any] = None
        self.context: Optional[Any] = None
        self.page: Optional[Page] = None
    
    async def __aenter__(self):
        await self.launch()
        return self
    
    async def __aexit__(self, *args):
        await self.close()
    
    async def launch(self):
        """Launch browser with optional stealth."""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=self.headless)
        
        # Build context options
        context_options = {
            "viewport": {
                "width": random.randint(1200, 1920),
                "height": random.randint(800, 1080)
            },
            "ignore_https_errors": True,
        }
        
        # Apply proxy if configured
        proxy = self.proxy_manager.get_next() if self.proxy_rotation else None
        if proxy:
            context_options["proxy"] = {"server": proxy}  # type: ignore
        
        # Apply User-Agent
        if self.user_agent_rotation:
            context_options["user_agent"] = random.choice(self.USER_AGENTS)
        
        self.context = await self.browser.new_context(**context_options)  # type: ignore
        self.page = await self.context.new_page()  # type: ignore
        
        # Apply stealth if enabled
        if self.stealth and Stealth and self.page:
            await Stealth().apply_stealth_async(self.page)
    
    async def close(self):
        """Close browser."""
        if self.page:
            await self.page.close()
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
    
    async def _wait_random(self):
        """Wait a random duration to mimic human behavior."""
        if self.random_delay:
            delay = random.uniform(self.min_delay, self.max_delay)
            await asyncio.sleep(delay)
    
    async def _detect_captcha(self, page: Page) -> bool:
        """Check if CAPTCHA is present on page."""
        captcha_indicators = [
            "captcha",
            "recaptcha",
            "hcaptcha",
            "challenge",
            "verify you are human",
            "i am not a robot"
        ]
        content = await page.content()
        return any(indicator in content.lower() for indicator in captcha_indicators)
    
    async def _extract_fields(self, page: Page, selector: Optional[str] = None, xpath: Optional[str] = None) -> Dict[str, Any]:
        """Extract fields using CSS selector or XPath."""
        fields: Dict[str, Any] = {}
        
        if selector:
            # Parse selector -> field_name format
            lines = selector.replace(", ", "\n").split("\n")
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                    
                sel = ""
                field_name = ""
                
                if "->" in line:
                    sel, field_name = line.split("->", 1)
                    sel = sel.strip()
                    field_name = field_name.strip()
                else:
                    sel = line
                    field_name = line
                
                if sel:
                    try:
                        elements = await page.query_selector_all(sel)
                        if len(elements) == 1:
                            fields[field_name] = await elements[0].inner_text()
                        elif len(elements) > 1:
                            fields[field_name] = await asyncio.gather(
                                *[el.inner_text() for el in elements]
                            )
                    except Exception as e:
                        fields[f"{field_name}_error"] = str(e)
        
        if xpath:
            try:
                elements = await page.query_selector_all(f"xpath={xpath}")
                fields["xpath_results"] = await asyncio.gather(
                    *[el.inner_text() for el in elements]
                )
            except Exception as e:
                fields["xpath_error"] = str(e)
        
        return fields
    
    async def read(
        self,
        url: str,
        selector: Optional[str] = None,
        xpath: Optional[str] = None,
        wait_for: Optional[str] = None,
        wait_until: str = "load",
        screenshot: Optional[str] = None,
        handle_captcha: bool = False,
        max_retries: int = 3,
    ) -> ExtractionResult:
        """
        Read and extract content from URL.
        
        Args:
            url: Target URL
            selector: CSS selector for extraction (format: "selector -> field_name")
            xpath: XPath selector
            wait_for: CSS selector to wait for
            wait_until: When to consider load complete ("load", "domcontentloaded", "networkidle")
            screenshot: Path to save screenshot
            handle_captcha: Retry on CAPTCHA detection
            max_retries: Max retry attempts
        
        Returns:
            ExtractionResult with extracted data
        """
        start_time = time.time()
        retries = 0
        
        # Type assertions for safe access (page/context are set in launch())
        assert self.page is not None, "Browser page not initialized"
        
        while retries < max_retries:
            try:
                # Random delay before request
                await self._wait_random()
                
                # Navigate to page
                nav_options = {
                    "timeout": self.timeout,
                    "wait_until": wait_until
                }
                
                if wait_for:
                    nav_options["wait_for"] = wait_for
                
                response = await self.page.goto(url, **nav_options)
                
                if not response or response.status >= 400:
                    return ExtractionResult(
                        url=url,
                        error=f"HTTP {response.status if response else 'No response'}",
                        metadata={"retries": retries}
                    )
                
                # Check for CAPTCHA
                if await self._detect_captcha(self.page):  # type: ignore
                    if handle_captcha and retries < max_retries - 1:
                        retries += 1
                        # Try with new proxy/IP
                        if self.proxy_rotation:
                            new_proxy = self.proxy_manager.get_next()
                            if new_proxy and self.context and self.browser:
                                await self.context.close()
                                self.context = await self.browser.new_context(
                                    proxy={"server": new_proxy},
                                    user_agent=random.choice(self.USER_AGENTS) if self.user_agent_rotation else None
                                )
                                self.page = await self.context.new_page()  # type: ignore
                                if self.stealth and Stealth and self.page:
                                    await Stealth().apply_stealth_async(self.page)
                        continue
                    else:
                        return ExtractionResult(
                            url=url,
                            captcha_detected=True,
                            error="CAPTCHA detected",
                            metadata={"retries": retries}
                        )
                
                # Get page content
                title = await self.page.title()  # type: ignore
                html = await self.page.content()  # type: ignore
                
                # Extract visible text
                text_elements = await self.page.query_selector_all("body")  # type: ignore
                text = await text_elements[0].inner_text() if text_elements else ""
                
                # Extract structured fields
                fields = await self._extract_fields(self.page, selector, xpath)  # type: ignore
                
                # Take screenshot if requested
                if screenshot and self.page:
                    await self.page.screenshot(path=screenshot, full_page=True)  # type: ignore
                
                return ExtractionResult(
                    url=url,
                    title=title,
                    text=text[:50000],  # Limit text length
                    html=html[:100000],  # Limit HTML length
                    fields=fields,
                    metadata={
                        "status": response.status,
                        "extraction_time_ms": int((time.time() - start_time) * 1000),
                        "stealth_used": self.stealth,
                        "proxy_used": self.proxy_manager.proxies[self.proxy_manager.current_index - 1] if self.proxy_rotation else None,
                    }
                )
                
            except asyncio.TimeoutError:
                if retries < max_retries - 1:
                    retries += 1
                    continue
                return ExtractionResult(
                    url=url,
                    error="Timeout",
                    metadata={"retries": retries}
                )
            except Exception as e:
                if retries < max_retries - 1:
                    retries += 1
                    continue
                return ExtractionResult(
                    url=url,
                    error=str(e),
                    metadata={"retries": retries}
                )
        
        return ExtractionResult(
            url=url,
            error="Max retries exceeded",
            metadata={"retries": max_retries}
        )
    
    async def read_batch(
        self,
        urls: List[str],
        selector: Optional[str] = None,
        concurrency: int = 1,
        callback: Optional[Callable[[ExtractionResult], None]] = None,
    ) -> List[ExtractionResult]:
        """Read multiple URLs with optional concurrency."""
        results = []
        
        for i, url in enumerate(urls):
            result = await self.read(url, selector=selector)
            results.append(result)
            
            if callback:
                callback(result)
            
            # Rate limiting between batches
            if concurrency > 1 and (i + 1) % concurrency == 0:
                await asyncio.sleep(random.uniform(1, 3))
        
        return results


async def main_async(args):
    """Async main function."""
    # Build WebReader options
    options = {
        "stealth": args.stealth,
        "user_agent_rotation": args.user_agent_rotation,
        "random_delay": args.delay,
        "min_delay": args.min_delay,
        "max_delay": args.max_delay,
        "proxy_rotation": bool(args.proxy or args.proxy_file),
        "proxies": [args.proxy] if args.proxy else None,
        "proxy_file": args.proxy_file,
        "headless": args.headless,
        "timeout": args.timeout * 1000,
        "screenshot_dir": args.screenshot,
    }
    
    async with WebReader(**{k: v for k, v in options.items() if v is not None}) as reader:
        result = await reader.read(
            url=args.url,
            selector=args.selector,
            xpath=args.xpath,
            wait_for=args.wait_for,
            wait_until=args.wait_until or "load",
            screenshot=args.screenshot,
            handle_captcha=args.handle_captcha,
            max_retries=args.retry,
        )
        
        # Output
        output = result.to_dict()
        
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(output, f, ensure_ascii=False, indent=2)
            print(f"Saved to {args.output}")
        else:
            print(json.dumps(output, ensure_ascii=False, indent=2))


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Web Reader - Advanced web scraping with anti-bot evasion",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic page read
  web-reader --url "https://example.com"
  
  # Extract structured data
  web-reader --url "https://shop.example.com" --selector "h1 -> title, .price -> price"
  
  # Full stealth mode with proxy
  web-reader --url "https://protected.site.com" --stealth --proxy-file proxies.txt
  
  # With XPath
  web-reader --url "https://jobs.example.com" --xpath "//div[@class='job']/span[@class='salary']"
        """
    )
    
    # Required
    parser.add_argument("--url", "-u", required=True, help="Target URL")
    
    # Extraction
    parser.add_argument("--selector", "-s", help="CSS selector (format: 'selector -> field_name')")
    parser.add_argument("--xpath", "-x", help="XPath selector")
    
    # Stealth options
    parser.add_argument("--stealth", action="store_true", default=True, help="Enable stealth mode (default: True)")
    parser.add_argument("--no-stealth", dest="stealth", action="store_false", help="Disable stealth mode")
    parser.add_argument("--user-agent-rotation", action="store_true", default=True, help="Rotate User-Agent")
    parser.add_argument("--no-user-agent-rotation", dest="user_agent_rotation", action="store_false")
    
    # Timing
    parser.add_argument("--delay", action="store_true", default=True, help="Random delay between requests")
    parser.add_argument("--no-delay", dest="delay", action="store_false", help="No random delay")
    parser.add_argument("--min-delay", type=float, default=1.0, help="Min delay seconds")
    parser.add_argument("--max-delay", type=float, default=3.0, help="Max delay seconds")
    
    # Proxy
    parser.add_argument("--proxy", "-p", help="Single proxy URL")
    parser.add_argument("--proxy-file", help="File with proxy list (one per line)")
    
    # Browser
    parser.add_argument("--headless", action="store_true", default=True, help="Run headless")
    parser.add_argument("--no-headless", dest="headless", action="store_false", help="Show browser")
    parser.add_argument("--timeout", type=int, default=30, help="Page timeout (seconds)")
    parser.add_argument("--wait-for", help="Wait for selector before returning")
    parser.add_argument("--wait-until", choices=["load", "domcontentloaded", "networkidle"], help="Wait condition")
    
    # CAPTCHA
    parser.add_argument("--handle-captcha", action="store_true", help="Retry on CAPTCHA detection")
    parser.add_argument("--retry", type=int, default=3, help="Max retry attempts")
    
    # Output
    parser.add_argument("--output", "-o", help="Output JSON file")
    parser.add_argument("--screenshot", help="Save screenshot to file")
    
    args = parser.parse_args()
    
    # Run async
    try:
        asyncio.run(main_async(args))
    except KeyboardInterrupt:
        print("\nInterrupted")
        sys.exit(1)


if __name__ == "__main__":
    main()
