import asyncio
import httpx
import re
import json

async def test_xhs():
    url = "https://www.xiaohongshu.com/discovery/item/69bfa6c0000000001a02b5fa"
    
    USERAGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36 Edg/143.0.0.0"
    )
    
    client = httpx.AsyncClient(
        headers={
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "referer": "https://www.xiaohongshu.com/explore",
            "user-agent": USERAGENT,
        },
        timeout=10,
        verify=False,
        http2=True,
        follow_redirects=True,
    )
    
    try:
        response = await client.get(url)
        html = response.text
        
        pattern = r"window\.__INITIAL_STATE__\s*=\s*(.+?)(?:;|$)"
        match = re.search(pattern, html)
        if match:
            raw = match.group(1).strip()
            
            # Find the JSON object boundaries
            brace_count = 0
            start = 0
            for i, c in enumerate(raw):
                if c == '{':
                    brace_count += 1
                elif c == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        json_str = raw[:i+1]
                        break
            
            data = json.loads(json_str)
            print("Parsed with JSON!")
            print(f"Keys: {list(data.keys())}")
            
            if "note" in data:
                print("Found 'note' key!")
                note = data["note"]
                print(f"Note type: {type(note)}")
                if isinstance(note, dict):
                    print(f"Note keys: {list(note.keys())}")
        else:
            print("No __INITIAL_STATE__ found")
    finally:
        await client.aclose()

asyncio.run(test_xhs())