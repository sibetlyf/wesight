#!/usr/bin/env python3
"""
Web Reader - Advanced web scraping with anti-bot detection evasion
Supports stealth browser automation, structured data extraction, and proxy rotation.
Includes XHS (Xiaohongshu) support via direct API calls.
"""

# type: ignore

import argparse
import asyncio
import json
import random
import re
import time
import sys
from dataclasses import dataclass, field
from datetime import datetime
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
                          "playwright", "httpx[http2]"])
    try:
        from playwright_stealth.stealth import Stealth  # type: ignore
        STEALTH_AVAILABLE = True
    except ImportError:
        STEALTH_AVAILABLE = False
        Stealth = None  # type: ignore
    from playwright.async_api import async_playwright, Page, BrowserContext  # type: ignore
    import httpx  # type: ignore


@dataclass
class XHSNote:
    """XHS Note data structure"""
    note_id: str = ""
    title: str = ""
    description: str = ""
    type: str = ""
    user_id: str = ""
    user_nickname: str = ""
    user_url: str = ""
    note_url: str = ""
    collect_count: int = 0
    comment_count: int = 0
    share_count: int = 0
    like_count: int = 0
    tags: str = ""
    publish_time: str = ""
    timestamp: Optional[int] = None
    image_urls: List[str] = field(default_factory=list)
    video_url: str = ""
    
    def to_dict(self) -> Dict:
        return {
            "note_id": self.note_id,
            "title": self.title,
            "description": self.description,
            "type": self.type,
            "user_id": self.user_id,
            "user_nickname": self.user_nickname,
            "user_url": self.user_url,
            "note_url": self.note_url,
            "collect_count": self.collect_count,
            "comment_count": self.comment_count,
            "share_count": self.share_count,
            "like_count": self.like_count,
            "tags": self.tags,
            "publish_time": self.publish_time,
            "timestamp": self.timestamp,
            "image_urls": self.image_urls,
            "video_url": self.video_url,
        }


class XHSScraper:
    """
    Xiaohongshu scraper using direct API calls
    Based on XHS-Downloader: https://github.com/JoeanAmier/XHS-Downloader
    """
    
    USERAGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36 Edg/143.0.0.0"
    )
    
    BASE_URL = "https://www.xiaohongshu.com"
    API_URL = "https://edith.xiaohongshu.com/api/sns/web/v1/feed"
    NOTE_URL = "https://edith.xiaohongshu.com/api/sns/web/v1/note"
    
    def __init__(
        self,
        cookie: str = "",
        proxy: str = None,
        timeout: int = 10,
        max_retries: int = 3,
    ):
        self.cookie = cookie
        self.proxy = proxy
        self.timeout = timeout
        self.max_retries = max_retries
        self.client = None
        
    async def __aenter__(self):
        await self.launch()
        return self
    
    async def __aexit__(self, *args):
        await self.close()
    
    async def launch(self):
        """Initialize HTTP client"""
        transport = httpx.AsyncHTTPTransport(proxy=self.proxy) if self.proxy else None
        
        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "referer": f"{self.BASE_URL}/explore",
            "user-agent": self.USERAGENT,
        }
        
        self.client = httpx.AsyncClient(
            headers=headers,
            cookies=self._parse_cookie(self.cookie),
            timeout=self.timeout,
            verify=False,
            http2=True,
            follow_redirects=True,
            mounts={
                "http://": transport,
                "https://": transport,
            } if self.proxy else None,
        )
    
    async def close(self):
        """Close HTTP client"""
        if self.client:
            await self.client.aclose()
    
    @staticmethod
    def _parse_cookie(cookie_str: str) -> dict:
        """Parse cookie string to dict"""
        if not cookie_str:
            return {}
        cookies = {}
        for item in cookie_str.split(";"):
            item = item.strip()
            if "=" in item:
                key, value = item.split("=", 1)
                cookies[key.strip()] = value.strip()
        return cookies
    
    @staticmethod
    def extract_note_id(url: str) -> Optional[str]:
        """Extract note ID from URL"""
        patterns = [
            r"xiaohongshu\.com/explore/([a-zA-Z0-9]+)",
            r"xiaohongshu\.com/discovery/item/([a-zA-Z0-9]+)",
            r"xiaohongshu\.com/user/profile/[^/]+/([a-zA-Z0-9]+)",
            r"xhslink\.com/([a-zA-Z0-9]+)",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None
    
    @staticmethod
    def is_xhs_url(url: str) -> bool:
        """Check if URL is a Xiaohongshu URL"""
        return "xiaohongshu.com" in url or "xhslink.com" in url
    
    async def fetch_html(self, url: str) -> str:
        try:
            response = await self.client.get(url)
            if response.status_code == 200:
                return response.text
        except Exception:
            pass
        return ""
    
    def parse_initial_state(self, html: str, note_id: str) -> Optional[Dict]:
        import re
        from yaml import safe_load
        
        pattern = r"window\.__INITIAL_STATE__\s*=\s*(.+?)(?:;|$)"
        match = re.search(pattern, html)
        if not match:
            return None
        
        try:
            raw = match.group(1).strip()
            if raw.endswith('</scripts></body></html>'):
                raw = raw[:-len('</scripts></body></html>')]
            
            data = safe_load(raw)
            
            note_container = data.get("note", {})
            note_detail = note_container.get("noteDetailMap", {})
            
            note_data = note_detail.get("undefined", {}).get("note", {})
            
            if note_data:
                return note_data
        except Exception:
            pass
        return None
    
    async def fetch_note(self, note_id: str) -> Dict:
        """Fetch note data using the FEED API"""
        url = self.API_URL
        
        headers = {
            "accept": "application/json, text/plain, */*",
            "content-type": "application/json",
            "origin": self.BASE_URL,
            "referer": f"{self.BASE_URL}/explore/{note_id}",
        }
        
        payloads = [
            {
                "source_note_id": note_id,
                "image_infos": [],
                "extra": {"need_body_topic": "1"},
                "xsec_source": "pc_feed",
                "xsec_token": "",
            },
        ]
        
        for attempt in range(self.max_retries):
            for data in payloads:
                try:
                    response = await self.client.post(url, json=data, headers=headers)
                    if response.status_code == 200:
                        result = response.json()
                        if result.get("success") or result.get("data"):
                            return result
                except Exception:
                    if attempt < self.max_retries - 1:
                        await asyncio.sleep(1)
                        continue
            await asyncio.sleep(1)
        
        return {"success": False, "msg": "API request failed"}
    
    def parse_note_data(self, data: dict, note_id: str) -> XHSNote:
        """Parse API response to XHSNote"""
        note = XHSNote()
        note.note_id = note_id
        note.note_url = f"{self.BASE_URL}/explore/{note_id}"
        
        try:
            items = data.get("data", {}).get("items", [])
            if items:
                note_card = items[0].get("note_card", {})
                note_data = note_card.get("note", {})
                
                note.title = note_data.get("title", "")
                note.description = note_data.get("desc", "")
                note.type = note_data.get("type", "")
                
                user = note_data.get("user", {})
                note.user_id = user.get("userId", "")
                note.user_nickname = user.get("nickname", "") or user.get("nickName", "")
                note.user_url = f"{self.BASE_URL}/user/profile/{note.user_id}"
                
                interact = note_data.get("interactInfo", {})
                note.collect_count = self._parse_count(interact.get("collectedCount"))
                note.comment_count = self._parse_count(interact.get("commentCount"))
                note.share_count = self._parse_count(interact.get("shareCount"))
                note.like_count = self._parse_count(interact.get("likedCount"))
                
                time_ts = note_data.get("time")
                if time_ts:
                    note.timestamp = time_ts // 1000
                    note.publish_time = datetime.fromtimestamp(note.timestamp).strftime("%Y-%m-%d_%H:%M:%S")
                
                tags = [t.get("name", "") for t in note_data.get("tagList", [])]
                note.tags = " ".join(tags)
                
                image_list = note_data.get("imageList", [])
                note.image_urls = [img.get("url", "") for img in image_list if img.get("url")]
                
                video_info = note_data.get("video", {})
                if video_info:
                    note.video_url = video_info.get("url", "")
                    
        except Exception:
            pass
            
        return note
    
    @staticmethod
    def _parse_count(value) -> int:
        """Parse count value"""
        if not value:
            return 0
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            value = value.strip()
            if value == "-1":
                return 0
            try:
                return int(value)
            except:
                return 0
        return 0
    
    async def extract(self, url: str) -> Dict:
        start_time = datetime.now()
        
        note_id = self.extract_note_id(url)
        if not note_id:
            return {
                "url": url,
                "success": False,
                "error": "Could not extract note ID from URL",
            }
        
        try:
            data = await self.fetch_note(note_id)
            
            if data and data.get("success"):
                note = self.parse_note_data(data, note_id)
                return {
                    "url": url,
                    "success": True,
                    "note": note.to_dict(),
                    "metadata": {
                        "extraction_time_ms": int((datetime.now() - start_time).total_seconds() * 1000),
                        "note_id": note_id,
                        "source": "xhs_api",
                    }
                }
            
            html = await self.fetch_html(url)
            if html:
                note_data = self.parse_initial_state(html, note_id)
                if note_data:
                    note = self.parse_html_note(note_data, note_id)
                    return {
                        "url": url,
                        "success": True,
                        "note": note.to_dict(),
                        "metadata": {
                            "extraction_time_ms": int((datetime.now() - start_time).total_seconds() * 1000),
                            "note_id": note_id,
                            "source": "xhs_html",
                        }
                    }
            
            return {
                "url": url,
                "success": False,
                "error": "Failed to fetch note data",
                "note_id": note_id,
            }
            
        except Exception as e:
            return {
                "url": url,
                "success": False,
                "error": str(e),
                "note_id": note_id,
            }
    
    def parse_html_note(self, data: dict, note_id: str) -> XHSNote:
        note = XHSNote()
        note.note_id = note_id
        note.note_url = f"{self.BASE_URL}/explore/{note_id}"
        
        try:
            note.title = data.get("title", "")
            note.description = data.get("desc", "")
            note.type = data.get("type", "")
            
            user = data.get("user", {})
            note.user_id = user.get("userId", "")
            note.user_nickname = user.get("nickname", "") or user.get("nickName", "")
            note.user_url = f"{self.BASE_URL}/user/profile/{note.user_id}"
            
            interact = data.get("interactInfo", {})
            note.collect_count = self._parse_count(interact.get("collectedCount"))
            note.comment_count = self._parse_count(interact.get("commentCount"))
            note.share_count = self._parse_count(interact.get("shareCount"))
            note.like_count = self._parse_count(interact.get("likedCount"))
            
            time_ts = data.get("time")
            if time_ts:
                note.timestamp = time_ts // 1000
                note.publish_time = datetime.fromtimestamp(note.timestamp).strftime("%Y-%m-%d_%H:%M:%S")
            
            tags = [t.get("name", "") for t in data.get("tagList", [])]
            note.tags = " ".join(tags)
            
            image_list = data.get("imageList", [])
            note.image_urls = [img.get("url", "") for img in image_list if img.get("url")]
            
            video_info = data.get("video", {})
            if video_info:
                note.video_url = video_info.get("url", "")
                
        except Exception:
            pass
            
        return note


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


class XHSSignedScraper:
    BASE_URL = "https://www.xiaohongshu.com"
    API_URL = "https://edith.xiaohongshu.com"
    
    def __init__(
        self,
        cookie: str = "",
        proxy: str = None,
        timeout: int = 10,
        auto_cookie: bool = True,
    ):
        self.cookie = cookie
        self.proxy = proxy
        self.timeout = timeout
        self.client = None
        self.xhshow = None
        self.auto_cookie = auto_cookie
        
    async def __aenter__(self):
        await self.launch()
        return self
    
    async def __aexit__(self, *args):
        await self.close()
    
    async def launch(self):
        from xhshow import Xhshow
        self.xhshow = Xhshow()
        
        if self.auto_cookie and not self.cookie:
            self.cookie = self._extract_browser_cookie()
        
        transport = httpx.AsyncHTTPTransport(proxy=self.proxy) if self.proxy else None
        
        headers = {
            "accept": "application/json, text/plain, */*",
            "content-type": "application/json",
            "origin": self.BASE_URL,
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }
        
        self.client = httpx.AsyncClient(
            headers=headers,
            cookies=self._parse_cookie(self.cookie),
            timeout=self.timeout,
            verify=False,
            http2=True,
            follow_redirects=True,
            mounts={
                "http://": transport,
                "https://": transport,
            } if self.proxy else None,
        )
    
    def _extract_browser_cookie(self) -> str:
        """Auto-extract XHS cookies from browser"""
        try:
            import browser_cookie3 as bc3
            import sys
            
            browsers = ['edge', 'chrome', 'chromium', 'brave', 'opera', 'vivaldi', 'firefox']
            
            for browser_name in browsers:
                try:
                    loader = getattr(bc3, browser_name, None)
                    if not loader:
                        continue
                    
                    cj = loader(domain_name=".xiaohongshu.com")
                    
                    cookies = {}
                    for cookie in cj:
                        if "xiaohongshu.com" in (cookie.domain or ""):
                            cookies[cookie.name] = cookie.value
                    
                    if cookies.get("a1"):
                        cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
                        return cookie_str
                        
                except Exception:
                    continue
                    
        except ImportError:
            pass
        
        return ""
    
    async def close(self):
        if self.client:
            await self.client.aclose()
    
    @staticmethod
    def _parse_cookie(cookie_str: str) -> dict:
        if not cookie_str:
            return {}
        cookies = {}
        for item in cookie_str.split(";"):
            item = item.strip()
            if "=" in item:
                key, value = item.split("=", 1)
                cookies[key.strip()] = value.strip()
        return cookies
    
    @staticmethod
    def extract_note_id(url: str) -> Optional[str]:
        patterns = [
            r"xiaohongshu\.com/explore/([a-zA-Z0-9]+)",
            r"xiaohongshu\.com/discovery/item/([a-zA-Z0-9]+)",
            r"xhslink\.com/([a-zA-Z0-9]+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None
    
    @staticmethod
    def extract_xsec_token(url: str) -> Optional[str]:
        match = re.search(r"xsec_token=([^&]+)", url)
        if match:
            return match.group(1)
        return None
    
    async def fetch_note_detail(self, note_id: str, xsec_token: str = "") -> Dict:
        url = f"{self.API_URL}/api/sns/web/v1/feed"
        
        cookies = self._parse_cookie(self.cookie)
        
        payload = {
            "source_note_id": note_id,
            "image_infos": [],
            "extra": {"need_body_topic": "1"},
            "xsec_source": "app_share",
            "xsec_token": xsec_token,
        }
        
        signing_headers = self.xhshow.sign_headers_post(
            url, cookies, payload=payload
        )
        
        headers = {
            "accept": "application/json, text/plain, */*",
            "content-type": "application/json",
            "origin": self.BASE_URL,
            "referer": f"{self.BASE_URL}/explore/{note_id}",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            **signing_headers,
        }
        
        for attempt in range(3):
            try:
                response = await self.client.post(url, json=payload, headers=headers)
                if response.status_code == 200:
                    result = response.json()
                    if result.get("success"):
                        return result
                    if result.get("code") in [-1, 406]:
                        return {"success": False, "msg": result.get("msg", "API returned error")}
                elif response.status_code == 461:
                    return {"success": False, "msg": "CAPTCHA required"}
            except Exception as e:
                if attempt < 2:
                    await asyncio.sleep(1)
                    continue
                return {"success": False, "error": str(e)}
        
        return {"success": False, "error": "Max retries exceeded"}
    
    def parse_note_data(self, data: dict, note_id: str) -> XHSNote:
        note = XHSNote()
        note.note_id = note_id
        note.note_url = f"{self.BASE_URL}/explore/{note_id}"
        
        try:
            item = data.get("data", {}).get("items", [{}])[0].get("note_card", {})
            
            note.title = item.get("title", "")
            note.description = item.get("desc", "")
            note.type = item.get("type", "")
            
            user = item.get("user", {})
            note.user_id = user.get("user_id", "")
            note.user_nickname = user.get("nickname", "")
            note.user_url = f"{self.BASE_URL}/user/profile/{note.user_id}"
            
            interact = item.get("interact_info", {})
            note.collect_count = int(interact.get("collected_count", 0) or 0)
            note.comment_count = int(interact.get("comment_count", 0) or 0)
            note.share_count = int(interact.get("share_count", 0) or 0)
            note.like_count = int(interact.get("liked_count", 0) or 0)
            
            time_ts = item.get("time")
            if time_ts:
                note.timestamp = time_ts // 1000
                note.publish_time = datetime.fromtimestamp(note.timestamp).strftime("%Y-%m-%d_%H:%M:%S")
            
            image_list = item.get("image_list", [])
            note.image_urls = [img.get("url", "") for img in image_list if img.get("url")]
            
            video_info = item.get("video", {})
            if video_info:
                note.video_url = video_info.get("url", "")
                
        except Exception:
            pass
            
        return note
    
    async def extract(self, url: str) -> Dict:
        start_time = datetime.now()
        
        note_id = self.extract_note_id(url)
        if not note_id:
            return {
                "url": url,
                "success": False,
                "error": "Could not extract note ID from URL",
            }
        
        xsec_token = self.extract_xsec_token(url) or ""
        
        try:
            data = await self.fetch_note_detail(note_id, xsec_token)
            
            if data and data.get("success"):
                note = self.parse_note_data(data, note_id)
                return {
                    "url": url,
                    "success": True,
                    "note": note.to_dict(),
                    "metadata": {
                        "extraction_time_ms": int((datetime.now() - start_time).total_seconds() * 1000),
                        "note_id": note_id,
                        "source": "xhs_signed_api",
                    }
                }
            
            return {
                "url": url,
                "success": False,
                "error": data.get("msg", data.get("error", "API request failed")),
                "note_id": note_id,
            }
            
        except Exception as e:
            return {
                "url": url,
                "success": False,
                "error": str(e),
                "note_id": note_id,
            }


class XHSBrowserScraper:
    """Xiaohongshu scraper using Playwright browser - extracts __INITIAL_STATE__"""
    
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    
    BASE_URL = "https://www.xiaohongshu.com"
    
    def __init__(
        self,
        headless: bool = True,
        proxy: str = None,
        timeout: int = 30000,
    ):
        self.headless = headless
        self.proxy = proxy
        self.timeout = timeout
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        
    async def __aenter__(self):
        await self.launch()
        return self
    
    async def __aexit__(self, *args):
        await self.close()
    
    async def launch(self):
        self.playwright = await async_playwright().start()
        
        launch_options = {"headless": self.headless}
        
        if self.proxy:
            launch_options["proxy"] = {"server": self.proxy}
        
        self.browser = await self.playwright.chromium.launch(**launch_options)
        
        self.context = await self.browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=self.USER_AGENT,
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
        )
        
        self.page = await self.context.new_page()
    
    async def close(self):
        if self.page:
            await self.page.close()
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
    
    @staticmethod
    def extract_note_id(url: str) -> Optional[str]:
        patterns = [
            r"xiaohongshu\.com/explore/([a-zA-Z0-9]+)",
            r"xiaohongshu\.com/discovery/item/([a-zA-Z0-9]+)",
            r"xiaohongshu\.com/user/profile/[^/]+/([a-zA-Z0-9]+)",
            r"xhslink\.com/([a-zA-Z0-9]+)",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None
    
    async def extract(self, url: str) -> Dict:
        start_time = datetime.now()
        
        note_id = self.extract_note_id(url)
        if not note_id:
            return {
                "url": url,
                "success": False,
                "error": "Could not extract note ID from URL",
            }
        
        try:
            await self.page.goto(url, wait_until="domcontentloaded", timeout=self.timeout)
            
            await asyncio.sleep(3)
            
            initial_state = await self.page.evaluate("""() => {
                return window.__INITIAL_STATE__;
            }""")
            
            if not initial_state:
                return {
                    "url": url,
                    "success": False,
                    "error": "Could not extract __INITIAL_STATE__",
                    "note_id": note_id,
                }
            
            note_data = self._extract_note_from_state(initial_state, note_id)
            
            if note_data:
                note = self._parse_note_data(note_data, note_id)
                return {
                    "url": url,
                    "success": True,
                    "note": note.to_dict(),
                    "metadata": {
                        "extraction_time_ms": int((datetime.now() - start_time).total_seconds() * 1000),
                        "note_id": note_id,
                        "source": "xhs_browser",
                    }
                }
            
            return {
                "url": url,
                "success": False,
                "error": "Note data not found in page state",
                "note_id": note_id,
            }
            
        except Exception as e:
            return {
                "url": url,
                "success": False,
                "error": str(e),
                "note_id": note_id,
            }
    
    def _extract_note_from_state(self, state: dict, note_id: str) -> Optional[Dict]:
        try:
            note_container = state.get("note", {})
            note_detail = note_container.get("noteDetailMap", {})
            
            if "undefined" in note_detail:
                return note_detail["undefined"].get("note", {})
            
            if note_id in note_detail:
                return note_detail[note_id].get("note", {})
            
            for key, value in note_detail.items():
                if isinstance(value, dict) and value.get("note"):
                    return value.get("note", {})
                    
        except Exception:
            pass
        return None
    
    def _parse_note_data(self, data: dict, note_id: str) -> XHSNote:
        note = XHSNote()
        note.note_id = note_id
        note.note_url = f"{self.BASE_URL}/explore/{note_id}"
        
        try:
            note.title = data.get("title", "")
            note.description = data.get("desc", "")
            note.type = data.get("type", "")
            
            user = data.get("user", {})
            note.user_id = user.get("userId", "")
            note.user_nickname = user.get("nickname", "") or user.get("nickName", "")
            note.user_url = f"{self.BASE_URL}/user/profile/{note.user_id}"
            
            interact = data.get("interactInfo", {})
            note.collect_count = int(interact.get("collectedCount", 0) or 0)
            note.comment_count = int(interact.get("commentCount", 0) or 0)
            note.share_count = int(interact.get("shareCount", 0) or 0)
            note.like_count = int(interact.get("likedCount", 0) or 0)
            
            time_ts = data.get("time")
            if time_ts:
                note.timestamp = time_ts // 1000
                note.publish_time = datetime.fromtimestamp(note.timestamp).strftime("%Y-%m-%d_%H:%M:%S")
            
            tags = [t.get("name", "") for t in data.get("tagList", [])]
            note.tags = " ".join(tags)
            
            image_list = data.get("imageList", [])
            note.image_urls = [img.get("url", "") for img in image_list if img.get("url")]
            
            video_info = data.get("video", {})
            if video_info:
                note.video_url = video_info.get("url", "")
                
        except Exception:
            pass
            
        return note


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
    
    # Common User-Agents for rotation - including mobile User-Agents for apps like xiaohongshu
    USER_AGENTS = [
        # Desktop
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0",
        # Mobile Android - critical for xiaohongshu
        "Mozilla/5.0 (Linux; Android 14; Build/UP1A.231005.007) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.210 Mobile Safari/537.36",
        "Mozilla/5.0 (Linux; Android 13; Build/TQ3A.230805.001) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.43 Mobile Safari/537.36",
        "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.210 Mobile Safari/537.36",
        "Mozilla/5.0 (Linux; Android 13; SM-G998B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.43 Mobile Safari/537.36",
        # Mobile iOS
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1",
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
            "device_scale_factor": random.choice([1, 1.25, 1.5, 2, 2.5, 3]),
            "has_touch": random.choice([True, False]),
        }
        
        # Apply proxy if configured
        proxy = self.proxy_manager.get_next() if self.proxy_rotation else None
        if proxy:
            context_options["proxy"] = {"server": proxy}  # type: ignore
        
        # Apply User-Agent and locale
        if self.user_agent_rotation:
            context_options["user_agent"] = random.choice(self.USER_AGENTS)
            context_options["locale"] = random.choice(["zh-CN", "zh-TW", "en-US", "en-GB"])
            context_options["timezone_id"] = random.choice(["Asia/Shanghai", "Asia/Hong_Kong", "America/New_York"])
        
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
        """Check if CAPTCHA or block page is present on page."""
        captcha_indicators = [
            "captcha",
            "recaptcha",
            "hcaptcha",
            "challenge",
            "verify you are human",
            "i am not a robot",
            "请在客户端查看",
            "当前内容仅支持在小红书 APP 查看",
            "not-found-container",
            "打开小红书",
            "APP内查看"
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
    use_xhs_browser = getattr(args, 'xhs_browser', False) or XHSScraper.is_xhs_url(args.url) and not args.xhs
    
    if use_xhs_browser:
        scraper = XHSBrowserScraper(
            headless=args.headless,
            proxy=args.proxy,
            timeout=args.timeout * 1000,
        )
        
        try:
            await scraper.launch()
            result = await scraper.extract(args.url)
            output = result
            
            if args.output:
                with open(args.output, "w", encoding="utf-8") as f:
                    json.dump(output, f, ensure_ascii=False, indent=2)
                print(f"Saved to {args.output}")
            else:
                import sys
                try:
                    sys.stdout.reconfigure(encoding='utf-8')
                except AttributeError:
                    pass
                print(json.dumps(output, ensure_ascii=False, indent=2))
        finally:
            await scraper.close()
        return
    
    use_xhs_signed = args.xhs_signed or (args.xhs and XHSSignedScraper.extract_xsec_token(args.url))
    
    if use_xhs_signed:
        scraper = XHSSignedScraper(
            cookie=args.xhs_cookie or "",
            proxy=args.xhs_proxy,
            timeout=args.xhs_timeout,
            auto_cookie=args.auto_cookie,
        )
        
        try:
            await scraper.launch()
            result = await scraper.extract(args.url)
            output = result
            
            if args.output:
                with open(args.output, "w", encoding="utf-8") as f:
                    json.dump(output, f, ensure_ascii=False, indent=2)
                print(f"Saved to {args.output}")
            else:
                import sys
                try:
                    sys.stdout.reconfigure(encoding='utf-8')
                except AttributeError:
                    pass
                print(json.dumps(output, ensure_ascii=False, indent=2))
        finally:
            await scraper.close()
        return
    
    use_xhs_mode = args.xhs
    
    if use_xhs_mode:
        scraper = XHSScraper(
            cookie=args.xhs_cookie or "",
            proxy=args.xhs_proxy,
            timeout=args.xhs_timeout,
        )
        
        try:
            await scraper.launch()
            result = await scraper.extract(args.url)
            output = result
            
            if args.output:
                with open(args.output, "w", encoding="utf-8") as f:
                    json.dump(output, f, ensure_ascii=False, indent=2)
                print(f"Saved to {args.output}")
            else:
                import sys
                try:
                    sys.stdout.reconfigure(encoding='utf-8')
                except AttributeError:
                    pass
                print(json.dumps(output, ensure_ascii=False, indent=2))
        finally:
            await scraper.close()
        return
    
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
            import sys
            try:
                sys.stdout.reconfigure(encoding='utf-8')
            except AttributeError:
                pass
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
    
    # XHS specific options
    xhs_group = parser.add_argument_group("XHS Options", "Options for Xiaohongshu scraping")
    xhs_group.add_argument("--xhs", action="store_true", help="Use XHS API mode for Xiaohongshu URLs (faster, no browser)")
    xhs_group.add_argument("--xhs-browser", action="store_true", help="Use XHS browser mode (enters browser to extract full data)")
    xhs_group.add_argument("--xhs-signed", action="store_true", help="Use XHS signed API mode (with x-s signature, requires xsec_token)")
    xhs_group.add_argument("--xhs-cookie", help="Cookie for XHS API")
    xhs_group.add_argument("--xhs-proxy", help="Proxy for XHS API requests")
    xhs_group.add_argument("--xhs-timeout", type=int, default=10, help="XHS API timeout (seconds)")
    xhs_group.add_argument("--auto-cookie", action="store_true", default=True, help="Auto-extract cookies from browser (default: True)")
    xhs_group.add_argument("--no-auto-cookie", dest="auto_cookie", action="store_false", help="Disable auto cookie extraction")

    args = parser.parse_args()
    
    # Run async
    try:
        asyncio.run(main_async(args))
    except KeyboardInterrupt:
        print("\nInterrupted")
        sys.exit(1)


if __name__ == "__main__":
    main()
