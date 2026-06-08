#!/usr/bin/env python3
import asyncio
import argparse
import json
import sys
import time
from enum import Enum
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any, Union

try:
    from playwright.async_api import async_playwright, Page, Browser, BrowserContext
    import playwright_stealth
except ImportError:
    print("Error: playwright and playwright-stealth are required.")
    print("Install with: pip install playwright playwright-stealth")
    sys.exit(1)


class ContentType(Enum):
    QUESTION = "question"
    ANSWER = "answer"
    USER = "user"
    ARTICLE = "article"
    COLUMN = "column"
    SEARCH = "search"
    UNKNOWN = "unknown"


@dataclass
class Author:
    name: str = ""
    url: str = ""
    headline: str = ""
    avatar: str = ""
    gender: str = ""
    location: str = ""
    business: str = ""
    education: str = ""


@dataclass
class QuestionData:
    url: str = ""
    title: str = ""
    content: str = ""
    author: Author = field(default_factory=Author)
    created_time: str = ""
    updated_time: str = ""
    answer_count: int = 0
    followers: int = 0
    views: int = 0
    tags: List[str] = field(default_factory=list)


@dataclass
class AnswerData:
    url: str = ""
    question_title: str = ""
    content: str = ""
    author: Author = field(default_factory=Author)
    vote_count: int = 0
    comment_count: int = 0
    created_time: str = ""
    updated_time: str = ""


@dataclass
class UserData:
    url: str = ""
    name: str = ""
    headline: str = ""
    avatar: str = ""
    gender: str = ""
    location: str = ""
    business: str = ""
    education: str = ""
    description: str = ""
    following_count: int = 0
    follower_count: int = 0
    following_topic_count: int = 0
    following_column_count: int = 0
    accepted_answer_count: int = 0
    zhihu_salt_score: int = 0


@dataclass
class ArticleData:
    url: str = ""
    title: str = ""
    content: str = ""
    author: Author = field(default_factory=Author)
    publish_time: str = ""
    like_count: int = 0
    comment_count: int = 0
    view_count: int = 0
    topics: List[str] = field(default_factory=list)
    images: List[str] = field(default_factory=list)


@dataclass
class ScrapedResult:
    type: str = ""
    url: str = ""
    question: Optional[QuestionData] = None
    answer: Optional[AnswerData] = None
    user: Optional[UserData] = None
    article: Optional[ArticleData] = None
    raw_html: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


POPUP_SELECTORS = [
    ".Modal-wrapper",
    ".SignFlow",
    ".Login-modal",
    ".Login-content",
    ".LoginForm",
    "[class*='Login']",
    "[class*='Sign']",
    ".AgreementModal",
    ".PrivacyDialog",
    ".UserAgreement",
    "[class*='Agreement']",
    "[class*='Privacy']",
    ".QRCodeLogin",
    ".LoginQRCode",
    ".qrcode-login",
    "[class*='QRCode']",
    ".NotificationModal",
    ".PushPermission",
    ".app-download-modal",
    "[class*='Notification']",
    "[class*='DownloadModal']",
    ".CookieConsent",
    ".CookieBanner",
    ".cookie-agreement",
    "[class*='Cookie']",
    ".Modal-closeButton",
    ".SignFlowClose",
    ".Modal-close",
    ".close",
    "[class*='Close']",
]

CONTENT_PATTERNS = {
    ContentType.QUESTION: ["/question/", "/topic/"],
    ContentType.ANSWER: ["/question/", "/answer/"],
    ContentType.USER: ["/people/", "/org/"],
    ContentType.ARTICLE: ["/p/", "/article/", "/专栏/"],
    ContentType.COLUMN: ["/column/", "/special/"],
    ContentType.SEARCH: ["/search"],
}


class PopupHandler:
    def __init__(self, page: Page, timeout: int = 5):
        self.page = page
        self.timeout = timeout
        self.custom_selectors: List[str] = []
        
    def add_custom_selector(self, selector: str):
        self.custom_selectors.append(selector)
        
    async def detect_popups(self) -> List[str]:
        detected = []
        all_selectors = POPUP_SELECTORS + self.custom_selectors
        
        for selector in all_selectors:
            try:
                element = await self.page.query_selector(selector)
                if element:
                    is_visible = await element.is_visible()
                    if is_visible:
                        detected.append(selector)
            except Exception:
                continue
                
        return detected
    
    async def close_popup(self, selector: str) -> bool:
        try:
            await self.page.keyboard.press("Escape")
            await self.page.wait_for_timeout(500)
            
            await self.page.mouse.click(10, 10)
            await self.page.wait_for_timeout(300)
            
            close_selectors = [
                ".Modal-closeButton",
                ".SignFlowClose", 
                ".Modal-close",
                ".close",
                "[aria-label='关闭']",
                "[class*='close']",
                "button:has-text('关闭')",
                "button:has-text('取消')",
                "button:has-text('我知道')",
                "button:has-text('知道了')",
                "button:has-text('同意')",
                "button:has-text('不允许')",
            ]
            
            for close_sel in close_selectors:
                close_btn = await self.page.query_selector(close_sel)
                if close_btn and await close_btn.is_visible():
                    await close_btn.click()
                    await self.page.wait_for_timeout(500)
                    return True
                    
            return False
            
        except Exception as e:
            print(f"Error closing popup {selector}: {e}")
            return False
    
    async def handle_all_popups(self, max_rounds: int = 3) -> List[str]:
        handled = []
        
        for round_num in range(max_rounds):
            popups = await self.detect_popups()
            
            if not popups:
                break
                
            for popup in popups:
                if popup not in handled:
                    await self.close_popup(popup)
                    handled.append(popup)
                    
            await self.page.wait_for_timeout(1000)
            
        return handled


class ZhihuScraper:
    def __init__(
        self,
        incognito: bool = True,
        stealth: bool = True,
        auto_close_popups: bool = True,
        popup_timeout: int = 5,
        timeout: int = 30,
        headless: bool = True,
        custom_popup_selectors: Optional[List[str]] = None,
        user_agent: Optional[str] = None,
    ):
        self.incognito = incognito
        self.stealth = stealth
        self.auto_close_popups = auto_close_popups
        self.popup_timeout = popup_timeout
        self.timeout = timeout
        self.headless = headless
        self.custom_popup_selectors = custom_popup_selectors or []
        self.user_agent = user_agent
        
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.popup_handler: Optional[PopupHandler] = None
        
    async def __aenter__(self):
        await self.init()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
        
    async def init(self):
        self.playwright = await async_playwright().start()
        
        launch_options = {
            "headless": self.headless,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-web-security",
            ]
        }
        
        self.browser = await self.playwright.chromium.launch(**launch_options)
        
        if self.incognito:
            self.context = await self.browser.new_context()
        else:
            self.context = await self.browser.new_context(
                user_agent=self.user_agent
            )
            
        self.page = await self.context.new_page()
        
        if self.stealth:
            try:
                import playwright_stealth
                stealth_func = getattr(playwright_stealth, 'stealth_async', None) or getattr(playwright_stealth, 'stealth', None)
                if stealth_func and self.page:
                    await stealth_func(self.page)
            except Exception:
                pass
            
        await self.context.set_extra_http_headers({
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        })
        
        self.popup_handler = PopupHandler(self.page, self.popup_timeout)
        for selector in self.custom_popup_selectors:
            self.popup_handler.add_custom_selector(selector)
            
    async def close(self):
        if self.page:
            await self.page.close()
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
            
    async def goto(self, url: str, wait_until: str = "networkidle"):
        if self.page:
            wait_option = wait_until if wait_until in ("commit", "domcontentloaded", "load", "networkidle") else "networkidle"
            await self.page.goto(url, wait_until=wait_option, timeout=self.timeout * 1000)
        
    async def handle_popups(self):
        if self.popup_handler and self.auto_close_popups and self.page:
            return await self.popup_handler.handle_all_popups()
        return []
    
    def detect_content_type(self, url: str) -> ContentType:
        for content_type, patterns in CONTENT_PATTERNS.items():
            for pattern in patterns:
                if pattern in url:
                    return content_type
        return ContentType.UNKNOWN
    
    async def extract_question(self, url: str) -> QuestionData:
        data = QuestionData(url=url)
        
        if not self.page:
            return data
        
        try:
            title_elem = await self.page.query_selector("h1[data-zop-href]") or \
                        await self.page.query_selector(".QuestionHeader-title")
            if title_elem:
                data.title = await title_elem.inner_text()
                
            content_elem = await self.page.query_selector(".QuestionHeader-detail") or \
                          await self.page.query_selector(".RichText")
            if content_elem:
                data.content = await content_elem.inner_text()
                
            author_elem = await self.page.query_selector(".AuthorInfo") or \
                         await self.page.query_selector(".QuestionHeader-author")
            if author_elem:
                name_elem = await author_elem.query_selector(".AuthorInfo-name")
                if name_elem:
                    data.author.name = await name_elem.inner_text()
                    
                link_elem = await author_elem.query_selector("a[href*='/people/']")
                if link_elem:
                    href = await link_elem.get_attribute("href")
                    if href:
                        data.author.url = href
                        
            stats_elements = await self.page.query_selector_all(".Button--plain")
            for elem in stats_elements:
                text = await elem.inner_text()
                if "关注" in text:
                    data.followers = int(''.join(filter(str.isdigit, text)) or 0)
                elif "回答" in text:
                    data.answer_count = int(''.join(filter(str.isdigit, text)) or 0)
                    
            view_elem = await self.page.query_selector(".NumberBoard-itemValue")
            if view_elem:
                text = await view_elem.inner_text()
                data.views = int(''.join(filter(str.isdigit, text)) or 0)
                
        except Exception as e:
            print(f"Error extracting question: {e}")
            
        return data
    
    async def extract_answer(self, url: str) -> AnswerData:
        data = AnswerData(url=url)
        
        if not self.page:
            return data
        
        try:
            question_elem = await self.page.query_selector(".QuestionHeader-title")
            if question_elem:
                data.question_title = await question_elem.inner_text()
                
            content_elem = await self.page.query_selector(".RichContent-inner") or \
                          await self.page.query_selector(".AnswerItem")
            if content_elem:
                data.content = await content_elem.inner_text()
                
            author_elem = await self.page.query_selector(".AuthorInfo") or \
                         await self.page.query_selector(".AnswerItem-author")
            if author_elem:
                name_elem = await author_elem.query_selector(".AuthorInfo-name") or \
                           await author_elem.query_selector(".name")
                if name_elem:
                    data.author.name = await name_elem.inner_text()
                    
                link_elem = await author_elem.query_selector("a[href*='/people/']")
                if link_elem:
                    href = await link_elem.get_attribute("href")
                    if href:
                        data.author.url = href
                    
                avatar_elem = await author_elem.query_selector("img.Avatar")
                if avatar_elem:
                    src = await avatar_elem.get_attribute("src")
                    if src:
                        data.author.avatar = src
                    
            vote_elem = await self.page.query_selector(".VoteButton") or \
                       await self.page.query_selector(".Count")
            if vote_elem:
                text = await vote_elem.inner_text()
                data.vote_count = int(''.join(filter(str.isdigit, text)) or 0)
                
            comment_elem = await self.page.query_selector(".CommentButton")
            if comment_elem:
                text = await comment_elem.inner_text()
                data.comment_count = int(''.join(filter(str.isdigit, text)) or 0)
                
        except Exception as e:
            print(f"Error extracting answer: {e}")
            
        return data
    
    async def extract_user(self, url: str) -> UserData:
        data = UserData(url=url)
        
        if not self.page:
            return data
        
        try:
            name_elem = await self.page.query_selector(".ProfileHeader-name") or \
                       await self.page.query_selector("h1")
            if name_elem:
                data.name = await name_elem.inner_text()
                
            headline_elem = await self.page.query_selector(".ProfileHeader-headline") or \
                           await self.page.query_selector(".headline")
            if headline_elem:
                data.headline = await headline_elem.inner_text()
                
            avatar_elem = await self.page.query_selector(".Avatar") or \
                         await self.page.query_selector(".Profile-avatarImg")
            if avatar_elem:
                src = await avatar_elem.get_attribute("src")
                if src:
                    data.avatar = src
                
            stat_elements = await self.page.query_selector_all(".NumberBoard-item")
            for elem in stat_elements:
                label_elem = await elem.query_selector(".NumberBoard-itemName")
                value_elem = await elem.query_selector(".NumberBoard-itemValue")
                if label_elem and value_elem:
                    label = await label_elem.inner_text()
                    value = await value_elem.inner_text()
                    value_int = int(''.join(filter(str.isdigit, value)) or 0)
                    
                    if "关注" in label:
                        data.following_count = value_int
                    elif "粉丝" in label:
                        data.follower_count = value_int
                        
            desc_elem = await self.page.query_selector(".ProfileHeader-description")
            if desc_elem:
                data.description = await desc_elem.inner_text()
                
        except Exception as e:
            print(f"Error extracting user: {e}")
            
        return data
    
    async def extract_article(self, url: str) -> ArticleData:
        data = ArticleData(url=url)
        
        if not self.page:
            return data
        
        try:
            title_elem = await self.page.query_selector("h1.Post-Title") or \
                        await self.page.query_selector(".Post-header h1") or \
                        await self.page.query_selector("h1")
            if title_elem:
                data.title = await title_elem.inner_text()
                
            content_elem = await self.page.query_selector(".Post-RichText") or \
                          await self.page.query_selector(".RichText") or \
                          await self.page.query_selector(".article-content")
            if content_elem:
                data.content = await content_elem.inner_text()
                
            author_elem = await self.page.query_selector(".AuthorInfo") or \
                         await self.page.query_selector(".Post-header .AuthorInfo")
            if author_elem:
                name_elem = await author_elem.query_selector(".AuthorInfo-name") or \
                           await author_elem.query_selector(".name")
                if name_elem:
                    data.author.name = await name_elem.inner_text()
                    
                link_elem = await author_elem.query_selector("a[href*='/people/']")
                if link_elem:
                    href = await link_elem.get_attribute("href")
                    if href:
                        data.author.url = href
                    
                avatar_elem = await author_elem.query_selector("img.Avatar")
                if avatar_elem:
                    src = await avatar_elem.get_attribute("src")
                    if src:
                        data.author.avatar = src
            
            stats_elem = await self.page.query_selector(".Post-stats")
            if stats_elem:
                text = await stats_elem.inner_text()
                import re
                views = re.search(r'阅读.*?(\d+)', text)
                if views:
                    data.view_count = int(views.group(1) or 0)
                likes = re.search(r'(\d+)', text)
                if likes:
                    data.like_count = int(likes.group(1) or 0)
                    
            topic_elems = await self.page.query_selector_all(".Post-Topic")
            for elem in topic_elems:
                topic = await elem.inner_text()
                if topic:
                    data.topics.append(topic)
            
            img_elems = await self.page.query_selector_all(".Post-RichText img, .article-content img, .RichText img, img[width]")
            for elem in img_elems:
                src = await elem.get_attribute("src")
                if src and src.startswith("http"):
                    if src not in data.images:
                        data.images.append(src)
                    
        except Exception as e:
            print(f"Error extracting article: {e}")
            
        return data
    
    async def scrape(
        self,
        url: str,
        content_type: Optional[ContentType] = None,
        wait_for_selector: Optional[str] = None,
        wait_timeout: int = 10,
        scroll: bool = True,
    ) -> ScrapedResult:
        
        if content_type is None:
            content_type = self.detect_content_type(url)
            
        result = ScrapedResult(
            type=content_type.value,
            url=url,
        )
        
        await self.goto(url)
        
        await self.handle_popups()
        
        if wait_for_selector and self.page:
            try:
                await self.page.wait_for_selector(wait_for_selector, timeout=wait_timeout * 1000)
            except Exception:
                pass
        
        if scroll and self.page:
            for _ in range(3):
                await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await self.page.wait_for_timeout(1000)
                
        await self.handle_popups()
        
        if content_type == ContentType.QUESTION:
            result.question = await self.extract_question(url)
        elif content_type == ContentType.ANSWER:
            result.answer = await self.extract_answer(url)
        elif content_type == ContentType.USER:
            result.user = await self.extract_user(url)
        elif content_type == ContentType.ARTICLE:
            result.article = await self.extract_article(url)
            
        result.metadata = {
            "scraped_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "content_type": content_type.value,
            "title": await self.page.title() if self.page else "",
        }
        
        return result
    
    async def scrape_with_retry(
        self,
        url: str,
        max_retries: int = 3,
        retry_delay: int = 5,
        **kwargs
    ) -> ScrapedResult:
        last_error = None
        
        for attempt in range(max_retries):
            try:
                return await self.scrape(url, **kwargs)
            except Exception as e:
                last_error = e
                print(f"Attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay * (attempt + 1))
                    
        raise Exception(f"Failed after {max_retries} attempts: {last_error}")


async def main():
    parser = argparse.ArgumentParser(description="Zhihu Scraper - Extract content from zhihu.com")
    
    parser.add_argument("--url", "-u", required=True, help="Target zhihu URL")
    parser.add_argument("--type", "-t", choices=["question", "answer", "user", "article"], 
                       help="Content type (auto-detected if not specified)")
    parser.add_argument("--output", "-o", default="zhihu_output.json", help="Output JSON file")
    parser.add_argument("--output-dir", "-d", default=".", help="Output directory (default: current directory)")
    parser.add_argument("--screenshot", "-s", help="Save screenshot")
    parser.add_argument("--download-images", action="store_true", help="Download all images to output directory")
    parser.add_argument("--incognito", action="store_true", default=True,
                       help="Use incognito mode (default: True)")
    parser.add_argument("--no-incognito", dest="incognito", action="store_false",
                       help="Disable incognito mode")
    parser.add_argument("--stealth", action="store_true", default=True,
                       help="Enable stealth mode (default: True)")
    parser.add_argument("--no-stealth", dest="stealth", action="store_false",
                       help="Disable stealth mode")
    parser.add_argument("--no-popup-close", dest="auto_close_popups", action="store_false", default=True,
                       help="Disable auto popup closing")
    parser.add_argument("--timeout", type=int, default=30,
                       help="Page load timeout in seconds (default: 30)")
    parser.add_argument("--wait", type=int, default=10,
                       help="Wait after load in seconds (default: 10, 建议15)")
    parser.add_argument("--headless", action="store_true", default=False,
                       help="Run in headless mode (default: False, 知乎会检测headless)")
    parser.add_argument("--no-headless", dest="headless", action="store_false",
                       help="Show browser window (默认)")
    
    args = parser.parse_args()
    
    content_type = None
    if args.type:
        content_type = ContentType(args.type)
    
    scraper = ZhihuScraper(
        incognito=args.incognito,
        stealth=args.stealth,
        auto_close_popups=args.auto_close_popups,
        timeout=args.timeout,
        headless=args.headless,
    )
    
    try:
        async with scraper:
            result = await scraper.scrape(
                url=args.url,
                content_type=content_type,
                wait_timeout=args.wait,
            )
            
            import os
            output_dir = args.output_dir
            if output_dir and output_dir != ".":
                os.makedirs(output_dir, exist_ok=True)
            
            if args.screenshot and scraper.page:
                screenshot_path = args.screenshot
                if output_dir and output_dir != "." and not os.path.isabs(screenshot_path):
                    screenshot_path = os.path.join(output_dir, screenshot_path)
                await scraper.page.screenshot(path=screenshot_path)
                print(f"Screenshot saved to: {screenshot_path}")
            
            output = {
                "type": result.type,
                "url": result.url,
                "metadata": result.metadata,
            }
            
            if result.question:
                output["question"] = asdict(result.question)
            if result.answer:
                output["answer"] = asdict(result.answer)
            if result.user:
                output["user"] = asdict(result.user)
            if result.article:
                output["article"] = asdict(result.article)
                
            json_output = json.dumps(output, ensure_ascii=False, indent=2)
            
            output_file = args.output
            if output_dir and output_dir != "." and not os.path.isabs(output_file):
                output_file = os.path.join(output_dir, output_file)
            
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(json_output)
            print(f"Output saved to: {output_file}")
            
            if args.download_images and result.article and result.article.images:
                import urllib.request
                import urllib.error
                images_dir = os.path.join(output_dir, "images") if output_dir and output_dir != "." else "images"
                os.makedirs(images_dir, exist_ok=True)
                print(f"Downloading {len(result.article.images)} images...")
                for idx, img_url in enumerate(result.article.images, 1):
                    try:
                        img_path = os.path.join(images_dir, f"{idx:02d}.jpg")
                        urllib.request.urlretrieve(img_url, img_path)
                        print(f"  Downloaded: {img_path}")
                    except Exception as img_err:
                        print(f"  Failed to download {img_url}: {img_err}")
                print(f"Images saved to: {images_dir}")
                
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
