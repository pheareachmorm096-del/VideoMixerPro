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
        # REQUIRED FOR RENDER: Add args to bypass sandbox and memory limits
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu"
            ]
        )

        # USE A FULL USER AGENT: Helps avoid immediate bot detection
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        page = context.new_page()

        try:
            from playwright_stealth import stealth_sync
            stealth_sync(page)
        except:
            pass

        try:
            # Increase timeout and wait for network to be completely quiet
            page.goto(url, wait_until="networkidle", timeout=60000)
            
            # SMALL DELAY: Give the JavaScript extra time to populate __INITIAL_STATE__
            time.sleep(3)

            for attempt in range(3):
                try:
                    # Check if we were blocked by a Captcha/Shield
                    if "verify" in page.url or page.query_selector('.captcha'):
                        print(" -> ⚠️ Blocked by Captcha on Render IP.")
                        break

                    page.wait_for_function(
                        "() => typeof window.__INITIAL_STATE__ !== 'undefined'",
                        timeout=10000
                    )

                    data = page.evaluate("() => window.__INITIAL_STATE__")
                    
                    if not data:
                        print(f" -> 🔄 Attempt {attempt+1}: Data empty, retrying...")
                        time.sleep(2)
                        continue

                    def find_url(d):
                        if isinstance(d, dict):
                            if 'masterUrl' in d:
                                return d['masterUrl']
                            if 'originVideo' in d and 'url' in d['originVideo']:
                                return d['originVideo']['url']
                            for v in d.values():
                                r = find_url(v)
                                if r: return r
                        elif isinstance(d, list):
                            for i in d:
                                r = find_url(i)
                                if r: return r
                        return None

                    video_url = find_url(data)
                    if video_url:
                        print(" -> ✅ Video URL Extracted Successfully.")
                        break

                except Exception as e:
                    print(f" -> ⚠️ Wait attempt {attempt+1} failed.")
                    time.sleep(2)

        except Exception as e:
            print(f" -> ❌ Page load error: {e}")
        
        finally:
            browser.close()

    return video_url


# =====================================
# UNIVERSAL EXTRACTOR
# =====================================

def extract_video_universal(url, cookie=None):
    url = resolve_short_link(url)

    if "xiaohongshu" in url or "xhslink" in url:
        res = extract_xhs_playwright(url)
        if res:
            return res
        else:
            print(" -> ❌ Failed to extract XHS video.")
            return None

    try:
        # Use a real user agent for yt-dlp too
        ydl_opts = {
            'quiet': True,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return info.get("url")
    except Exception as e:
        print(f" -> ❌ yt-dlp error: {e}")
        return None