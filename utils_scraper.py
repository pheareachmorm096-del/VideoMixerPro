import os
import time
import re
import json
from playwright.sync_api import sync_playwright

# =====================================
# 1. ROBUST SHORT LINK RESOLVER
# =====================================
def resolve_xhs_link(url):
    """
    XHS links often come as 'xhslink.com/...' 
    We let Playwright handle the redirect, but this regex 
    cleans up the input if users paste text + link.
    """
    match = re.search(r'(https?://[a-zA-Z0-9./?=&_%-]+)', url)
    if match:
        return match.group(1)
    return url

# =====================================
# 2. THE EXTRACTOR
# =====================================
def extract_xhs_video(url):
    print(f" -> 🟢 Processing XHS Link: {url}")
    
    # Clean the URL
    target_url = resolve_xhs_link(url)
    
    # GET COOKIE FROM ENVIRONMENT (Render Dashboard)
    # This allows you to update it without redeploying code
    cookie_string = os.environ.get("XHS_COOKIE", "")
    
    if not cookie_string:
        print(" -> ⚠️ WARNING: No 'XHS_COOKIE' found in Environment Variables.")
        # You can fallback to a hardcoded one for testing, but unsafe for prod

    video_url = None

    with sync_playwright() as p:
        # Launch options for Render (Headless is mandatory)
        browser = p.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-blink-features=AutomationControlled',
            ]
        )
        
        # Create context with a realistic User Agent
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )

        # --- KEY FIX: PARSE COOKIE STRING CORRECTLY ---
        if cookie_string:
            try:
                cookie_list = []
                # Split by semicolon (standard cookie format)
                for item in cookie_string.split(';'):
                    if '=' in item:
                        name, value = item.strip().split('=', 1)
                        cookie_list.append({
                            'name': name,
                            'value': value,
                            'domain': ".xiaohongshu.com",
                            'path': "/"
                        })
                context.add_cookies(cookie_list)
                print(f" -> 🍪 Injected {len(cookie_list)} cookies.")
            except Exception as e:
                print(f" -> ❌ Cookie Error: {e}")
        # ----------------------------------------------

        page = context.new_page()

        # Stealth Mode (Essential for XHS)
        try:
            from playwright_stealth import stealth_sync
            stealth_sync(page)
        except ImportError:
            print(" -> ⚠️ playwright-stealth not installed")

        try:
            # Go to URL
            page.goto(target_url, wait_until="domcontentloaded", timeout=15000)
            
            # Check if we hit a CAPTCHA title
            title = page.title()
            print(f" -> Page Title: {title}")
            if "验证" in title or "Verify" in title:
                print(" -> 🔴 HIT CAPTCHA! The cookie might be expired or IP blocked.")
                browser.close()
                return None

            # Attempt to extract JSON data
            # XHS stores data in window.__INITIAL_STATE__
            extracted_data = None
            for _ in range(5): # Retry loop
                try:
                    extracted_data = page.evaluate("() => window.__INITIAL_STATE__")
                    if extracted_data:
                        break
                    time.sleep(1)
                except:
                    time.sleep(1)
            
            if extracted_data:
                video_url = find_url_recursive(extracted_data)
            else:
                print(" -> ⚠️ Could not find __INITIAL_STATE__")

        except Exception as e:
            print(f" -> ❌ Playwright Error: {e}")

        browser.close()

    return video_url

# =====================================
# 3. RECURSIVE SEARCH HELPER
# =====================================
def find_url_recursive(data):
    """
    Recursively searches the JSON state for the best video URL.
    Prioritizes 'originVideo' key.
    """
    if isinstance(data, dict):
        # Direct hit for master URL (highest quality usually)
        if 'masterUrl' in data and data['masterUrl']:
            return data['masterUrl']
        
        # Standard video object
        if 'originVideo' in data and 'url' in data['originVideo']:
            return data['originVideo']['url']
            
        # Recursive Search
        for value in data.values():
            res = find_url_recursive(value)
            if res: return res
            
    elif isinstance(data, list):
        for item in data:
            res = find_url_recursive(item)
            if res: return res
            
    return None