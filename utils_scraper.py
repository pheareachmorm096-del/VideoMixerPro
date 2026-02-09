import os
import time
import re
import urllib.parse
import yt_dlp
from playwright.sync_api import sync_playwright

# =====================================
# CLEAN URL
# =====================================

def resolve_short_link(url):
    match = re.search(r'(https?://[a-zA-Z0-9./?=&_%-]+)', url)
    if match:
        return match.group(1)
    return url


# =====================================
# PLAYWRIGHT XHS SCRAPER (WITH COOKIES)
# =====================================

def extract_xhs_playwright(url):
    print(f" -> 🟢 Starting Browser (Playwright) for: {url}")

    video_url = None
    
    # Replace this with your actual cookie value (Keep your long string here)
    YOUR_WEB_SESSION = os.environ.get("XHS_COOKIE", "")

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

        # --- FIX: SPLIT THE LONG STRING INTO INDIVIDUAL COOKIES ---
        if YOUR_WEB_SESSION:
            try:
                cookies = []
                # Split by semicolon to get key=value pairs
                for cookie_string in YOUR_WEB_SESSION.split(';'):
                    if '=' in cookie_string:
                        # Split only on first '=' in case value has '=' inside
                        name, value = cookie_string.strip().split('=', 1)
                        cookies.append({
                            'name': name,
                            'value': value,
                            'domain': ".xiaohongshu.com",
                            'path': "/",
                            'secure': True
                        })
                
                # Add all cookies at once
                context.add_cookies(cookies)
                print(f" -> 🍪 Injected {len(cookies)} cookies successfully")
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
