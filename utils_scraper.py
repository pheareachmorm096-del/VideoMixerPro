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

def extract_xhs_playwright(url):

    print(f" -> 🟢 Starting Browser (Playwright) for: {url}")

    from playwright.sync_api import sync_playwright

    video_url = None

    with sync_playwright() as p:

        browser = p.chromium.launch(headless=True)

        context = browser.new_context(
            viewport={'width':1920,'height':1080},
            user_agent="Mozilla/5.0"
        )

        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        page = context.new_page()

        # Optional stealth
        try:
            from playwright_stealth import stealth_sync
            stealth_sync(page)
        except:
            pass

        page.goto(url, wait_until="networkidle", timeout=30000)

        for _ in range(3):
            try:
                page.wait_for_function(
                    "() => typeof window.__INITIAL_STATE__ !== 'undefined'",
                    timeout=30000
                )

                data = page.evaluate("() => window.__INITIAL_STATE__")

                def find_url(d):
                    if isinstance(d, dict):
                        if 'masterUrl' in d:
                            return d['masterUrl']
                        if 'originVideo' in d and 'url' in d['originVideo']:
                            return d['originVideo']['url']
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
