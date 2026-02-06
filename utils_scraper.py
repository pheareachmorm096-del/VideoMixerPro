import time
import re
import yt_dlp
from playwright.sync_api import sync_playwright

# =====================================
# CLEAN URL
# =====================================

def resolve_short_link(url):
    match = re.search(r'(https?://[a-zA-Z0-9./?=&_%-]+)', url)
    return match.group(1) if match else url


# =====================================
# PLAYWRIGHT XHS SCRAPER (CLOUD SAFE)
# =====================================

def extract_xhs_playwright(url):

    print(f"🟢 Playwright XHS -> {url}")

    video_url = None

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled"
            ]
        )

        context = browser.new_context(
            viewport={'width':1920,'height':1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122 Safari/537.36"
        )

        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        """)

        page = context.new_page()

        page.goto(url, wait_until="domcontentloaded", timeout=60000)

        for _ in range(5):
            try:
                page.wait_for_function(
                    "() => window.__INITIAL_STATE__ !== undefined",
                    timeout=15000
                )

                data = page.evaluate("() => window.__INITIAL_STATE__")

                def find_url(d):
                    if isinstance(d, dict):
                        if 'masterUrl' in d:
                            return d['masterUrl']
                        if 'originVideo' in d and isinstance(d['originVideo'], dict):
                            return d['originVideo'].get('url')
                        for v in d.values():
                            r = find_url(v)
                            if r:
                                return r
                    elif isinstance(d, list):
                        for i in d:
                            r = find_url(i)
                            if r:
                                return r
                    return None

                video_url = find_url(data)

                if video_url:
                    break

            except:
                time.sleep(2)

        browser.close()

    return video_url


# =====================================
# YT-DLP FALLBACK (WITH HEADERS)
# =====================================

def extract_with_ytdlp(url):

    ydl_opts = {
        "quiet": True,
        "nocheckcertificate": True,
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122 Safari/537.36",
        "headers": {
            "Referer": url
        }
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        return info.get("url")


# =====================================
# UNIVERSAL EXTRACTOR
# =====================================

def extract_video_universal(url):

    url = resolve_short_link(url)

    if "xiaohongshu" in url or "xhslink" in url:
        return extract_xhs_playwright(url)

    try:
        return extract_with_ytdlp(url)
    except:
        return None
