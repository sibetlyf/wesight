import asyncio
from playwright.async_api import async_playwright

async def test():
    url = "https://www.xiaohongshu.com/discovery/item/69bfa6c0000000001a02b5fa"
    
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
        )
        page = await context.new_page()
        
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            print("Page loaded")
            
            await asyncio.sleep(5)
            
            # Check page title
            title = await page.title()
            print(f"Page title: {title}")
            
            # Try to get __INITIAL_STATE__
            initial_state = await page.evaluate("""() => {
                if (window.__INITIAL_STATE__) {
                    return Object.keys(window.__INITIAL_STATE__);
                }
                return null;
            }""")
            print(f"__INITIAL_STATE__ keys: {initial_state}")
            
            if initial_state:
                # Try to get note data
                note_data = await page.evaluate("""() => {
                    const state = window.__INITIAL_STATE__;
                    if (state && state.note) {
                        return Object.keys(state.note);
                    }
                    return null;
                }""")
                print(f"note keys: {note_data}")
                
        except Exception as e:
            print(f"Error: {e}")
        finally:
            input("Press Enter to close...")
            await browser.close()

asyncio.run(test())