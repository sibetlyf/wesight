#!/usr/bin/env python3
"""
XHS (Xiaohongshu) Scraper Module
Based on XHS-Downloader: https://github.com/JoeanAmier/XHS-Downloader
"""

import asyncio
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse

try:
    from httpx import AsyncClient, AsyncHTTPTransport, TimeoutException
except ImportError:
    print("Installing httpx...")
    import subprocess
    subprocess.check_call([__import__("sys").executable, "-m", "pip", "install", "httpx"])
    from httpx import AsyncClient, AsyncHTTPTransport, TimeoutException


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
    download_urls: Dict[str, Any] = field(default_factory=dict)


@dataclass
class XHSExtractResult:
    """Result of XHS extraction"""
    url: str
    note: Optional[XHSNote] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return {
            "url": self.url,
            "note": self.note.__dict__ if self.note else None,
            "error": self.error,
            "metadata": self.metadata
        }


class XHSScraper:
    """
    Xiaohongshu scraper using direct API calls
    Based on XHS-Downloader approach
    """
    
    USERAGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36 Edg/143.0.0.0"
    )
    
    BASE_URL = "https://www.xiaohongshu.com"
    API_URL = "https://edith.xiaohongshu.com/api/sns/web/v1/feed"
    NOTE_URL = "https://edith.xiaohongshu.com/api/sns/web/v1/note"
    FEED_URL = "https://edith.xiaohongshu.com/api/sns/web/v1/feed"
    
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
        self.client: Optional[AsyncClient] = None
        
    async def __aenter__(self):
        await self.launch()
        return self
    
    async def __aexit__(self, *args):
        await self.close()
    
    async def launch(self):
        """Initialize HTTP client"""
        transport = AsyncHTTPTransport(proxy=self.proxy) if self.proxy else None
        
        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "referer": f"{self.BASE_URL}/explore",
            "user-agent": self.USERAGENT,
        }
        
        self.client = AsyncClient(
            headers=headers,
            cookies=self._parse_cookie(self.cookie),
            timeout=self.timeout,
            verify=False,
            http2=False,  # Use HTTP/1.1 instead of HTTP/2
            follow_redirects=True,
            mounts={
                "http://": AsyncHTTPTransport(proxy=self.proxy) if self.proxy else None,
                "https://": AsyncHTTPTransport(proxy=self.proxy) if self.proxy else None,
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
    
    async def fetch_note(self, note_id: str) -> Dict:
        """Fetch note data using the FEED API"""
        url = self.FEED_URL
        
        headers = {
            "accept": "application/json, text/plain, */*",
            "content-type": "application/json",
            "origin": self.BASE_URL,
            "referer": f"{self.BASE_URL}/explore/{note_id}",
        }
        
        # Try different payload formats
        payloads = [
            {
                "source_note_id": note_id,
                "image_infos": [],
                "extra": {"need_body_topic": "1"},
                "xsec_source": "pc_feed",
                "xsec_token": "",
            },
            {
                "note_id": note_id,
                "image_infos": [],
                "extra": {"need_body_topic": "1"},
            },
        ]
        
        for attempt in range(self.max_retries):
            for i, data in enumerate(payloads):
                try:
                    response = await self.client.post(url, json=data, headers=headers)
                    if response.status_code == 200:
                        result = response.json()
                        if result.get("success") or result.get("data"):
                            return result
                except Exception as e:
                    if attempt < self.max_retries - 1:
                        await asyncio.sleep(1)
                        continue
                    raise
            await asyncio.sleep(1)
        
        return {"success": False, "msg": "All API attempts failed"}
    
    def parse_note_data(self, data: dict, note_id: str) -> XHSNote:
        """Parse API response to XHSNote"""
        note = XHSNote()
        note.note_id = note_id
        note.note_url = f"{self.BASE_URL}/explore/{note_id}"
        
        try:
            # Get main data
            item = data.get("data", {}).get("items", [{}])[0].get("note_card", {})
            note_data = item.get("note", {})
            
            # Basic info
            note.title = note_data.get("title", "")
            note.description = note_data.get("desc", "")
            note.type = note_data.get("type", "")
            
            # User info
            user = note_data.get("user", {})
            note.user_id = user.get("userId", "")
            note.user_nickname = user.get("nickname", "") or user.get("nickName", "")
            note.user_url = f"{self.BASE_URL}/user/profile/{note.user_id}"
            
            # Interact info
            interact = note_data.get("interactInfo", {})
            note.collect_count = self._parse_count(interact.get("collectedCount"))
            note.comment_count = self._parse_count(interact.get("commentCount"))
            note.share_count = self._parse_count(interact.get("shareCount"))
            note.like_count = self._parse_count(interact.get("likedCount"))
            
            # Time
            time_ts = note_data.get("time")
            if time_ts:
                note.timestamp = time_ts // 1000
                note.publish_time = datetime.fromtimestamp(note.timestamp).strftime("%Y-%m-%d_%H:%M:%S")
            
            # Tags
            tags = [t.get("name", "") for t in note_data.get("tagList", [])]
            note.tags = " ".join(tags)
            
            # Images
            image_list = note_data.get("imageList", [])
            note.image_urls = [img.get("url", "") for img in image_list if img.get("url")]
            
            # Video
            video_info = note_data.get("video", {})
            if video_info:
                note.video_url = video_info.get("url", "")
                
        except Exception as e:
            print(f"Parse error: {e}")
            
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
    
    async def extract(
        self,
        url: str,
        download: bool = False,
    ) -> XHSExtractResult:
        """Extract note from URL"""
        start_time = datetime.now()
        
        # Extract note ID
        note_id = self.extract_note_id(url)
        if not note_id:
            return XHSExtractResult(
                url=url,
                error="Could not extract note ID from URL",
                metadata={"retries": 0}
            )
        
        try:
            # Fetch data
            data = await self.fetch_note(note_id)
            
            if not data or not data.get("success", False):
                return XHSExtractResult(
                    url=url,
                    error=f"API request failed: {data.get('msg', 'Unknown error')}",
                    metadata={"note_id": note_id}
                )
            
            # Parse note
            note = self.parse_note_data(data, note_id)
            
            return XHSExtractResult(
                url=url,
                note=note,
                metadata={
                    "extraction_time_ms": int((datetime.now() - start_time).total_seconds() * 1000),
                    "note_id": note_id,
                }
            )
            
        except Exception as e:
            return XHSExtractResult(
                url=url,
                error=str(e),
                metadata={"note_id": note_id}
            )


async def main():
    """Test the scraper"""
    import sys
    
    url = sys.argv[1] if len(sys.argv) > 1 else "https://www.xiaohongshu.com/discovery/item/69bfa6c0000000001a02b5fa"
    cookie = sys.argv[2] if len(sys.argv) > 2 else ""
    
    async with XHSScraper(cookie=cookie) as scraper:
        result = await scraper.extract(url)
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
