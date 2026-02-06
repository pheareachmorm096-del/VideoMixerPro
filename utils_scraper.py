import time
import re
import urllib.parse
import yt_dlp

# =====================================
# CLEAN URL
# =====================================

def resolve_short_link(url):
    match = re.search(r'(https?://[a-zA-Z0-9./?=&_%-]+)', url)
    if match:
        return match.group(1)
    return url


# =====================================
# PLAYWRIGHT XHS SCRAPER
# =====================================

# =====================================
# PLAYWRIGHT XHS SCRAPER (WITH COOKIES)
# =====================================

def extract_xhs_playwright(url):
    print(f" -> 🟢 Starting Browser (Playwright) for: {url}")
    from playwright.sync_api import sync_playwright

    video_url = None
    
    # Replace this with your actual cookie value
    YOUR_WEB_SESSION = "abRequestId=e4fa1952-81d5-5082-83af-9452fbb6fa0a; a1=19abdfc35aelxg47maimu2110uc8x1ub9ceki197t50000268623; webId=5ac1d88071e17f662527992e286b46ae; gid=yj0DfiS20Jjjyj0DfiSq2Syj0d1Ck4W60367dW9Jyy87ST28YCy7D3888JKYKJq8fJYSJY2q; xsecappid=xhs-pc-web; webBuild=5.11.0; web_session=040069b855e40e8e6f937beab03b4b4ebd1bca; id_token=VjEAABwtnTMxNYTXGDhEKizlBaMOgYFvJZ+Xhp3B30mCFzW9WlalDM4ahAbhTl2p0nWjyma52ArG5xkzXtJjEWoD+pDz4fAEngvGopGQTqgna36KGGxHJAd7xjO9y1xTPOYY3yi0; loadts=1770366733380; unread={%22ub%22:%22698059eb000000000e03f362%22%2C%22ue%22:%2269853c7e000000000a028504%22%2C%22uc%22:16}; websectiga=634d3ad75ffb42a2ade2c5e1705a73c845837578aeb31ba0e442d75c648da36a; sec_poison_id=3364661e-4f24-40af-bc66-d0b1cdcf2688" 

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-blink-features=AutomationControlled',
            ]
        )

        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        # --- FIX: ROBUST COOKIE INJECTION ---
        if YOUR_WEB_SESSION:
            try:
                context.add_cookies([{
                    'name': 'web_session',
                    'value': YOUR_WEB_SESSION.strip(),
                    'domain': ".xiaohongshu.com",
                    'path': "/",
                    'secure': True
                }])
                print(" -> 🍪 Cookie injected successfully")
            except Exception as e:
                print(f" -> ⚠️ Cookie Injection Failed: {e}")
        # ------------------------------------

        page = context.new_page()

        try:
            from playwright_stealth import stealth_sync
            stealth_sync(page)
        except:
            pass

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except:
            pass

        # ... (Rest of your extraction logic remains the same) ...
        
        for _ in range(5):
            try:
                data = page.evaluate("() => window.__INITIAL_STATE__")
                
                # Internal helper to find URL in nested dict
                def find_url(d):
                    if isinstance(d, dict):
                        if 'masterUrl' in d: return d['masterUrl']
                        if 'originVideo' in d and 'url' in d['originVideo']: return d['originVideo']['url']
                        for v in d.values():
                            r = find_url(v)
                            if r: return r
                    elif isinstance(d, list):
                        for i in d:
                            r = find_url(i)
                            if r: return r
                    return None

                if data:
                    video_url = find_url(data)
                
                if video_url:
                    break
                time.sleep(1)
            except:
                time.sleep(1)

        browser.close()

    return video_url
# =====================================
# UNIVERSAL EXTRACTOR
# =====================================

def extract_video_universal(url, cookie=None):

    url = resolve_short_link(url)

    if "xiaohongshu" in url or "xhslink" in url:
        return extract_xhs_playwright(url)

    try:
        with yt_dlp.YoutubeDL({'quiet':True}) as ydl:
            info = ydl.extract_info(url, download=False)
            return info.get("url")
    except:
        return None
