import os
import shutil
import subprocess
import time
import requests
import yt_dlp
from flask import Flask, request, jsonify, send_file
from playwright.sync_api import sync_playwright

# ==========================================
# CONFIGURATION
# ==========================================

# Use /tmp on Render (it's the only writable directory usually, but current works too)
BASE_DIR = os.getcwd()
TEMP_DIR = os.path.join(BASE_DIR, "temp_data")
SOUNDS_DIR = os.path.join(BASE_DIR, "sounds")
SUGGESTIONS_DIR = os.path.join(BASE_DIR, "suggestions")

# Ensure directories exist
os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(SOUNDS_DIR, exist_ok=True)
os.makedirs(SUGGESTIONS_DIR, exist_ok=True)

# Global task storage (In-memory for simplicity)
tasks = {}

# FFmpeg Setup (Auto-detect or Fallback)
def get_ffmpeg_path():
    # 1. Check system path (standard install)
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg
    
    # 2. Check local folder (if manually downloaded via Build Command)
    local_ffmpeg = os.path.join(BASE_DIR, "ffmpeg")
    if os.path.exists(local_ffmpeg):
        return local_ffmpeg

    print("⚠️ WARNING: FFmpeg not found in path or local folder.")
    return "ffmpeg" # Default and hope for the best

FFMPEG_PATH = get_ffmpeg_path()


# ==========================================
# HELPER: DOWNLOADERS
# ==========================================

def resolve_xhs_link(url):
    import re
    match = re.search(r'(https?://[a-zA-Z0-9./?=&_%-]+)', url)
    return match.group(1) if match else url

def extract_xhs_playwright(url):
    """
    Robust XHS extractor with Cookie support from Environment Variables
    """
    print(f" -> 🟢 Starting Playwright for: {url}")
    
    # Get cookie from Render Environment Variable
    cookie_string = os.environ.get("XHS_COOKIE", "")
    
    video_url = None

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-blink-features=AutomationControlled']
        )
        
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )

        # Inject Cookies
        if cookie_string:
            try:
                cookies = []
                for item in cookie_string.split(';'):
                    if '=' in item:
                        k, v = item.strip().split('=', 1)
                        cookies.append({'name': k.strip(), 'value': v.strip(), 'domain': ".xiaohongshu.com", 'path': "/"})
                context.add_cookies(cookies)
                print(f" -> 🍪 Injected {len(cookies)} cookies.")
            except Exception as e:
                print(f" -> ⚠️ Cookie Error: {e}")

        page = context.new_page()
        
        try:
            from playwright_stealth import stealth_sync
            stealth_sync(page)
        except: pass

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            
            # Recursive search for video URL in window state
            for _ in range(5):
                try:
                    data = page.evaluate("() => window.__INITIAL_STATE__")
                    
                    def find_url(d):
                        if isinstance(d, dict):
                            if 'masterUrl' in d: return d['masterUrl']
                            if 'originVideo' in d and 'url' in d['originVideo']: return d['originVideo']['url']
                            for v in d.values():
                                res = find_url(v)
                                if res: return res
                        elif isinstance(d, list):
                            for i in d:
                                res = find_url(i)
                                if res: return res
                        return None

                    if data:
                        video_url = find_url(data)
                        if video_url: break
                except:
                    time.sleep(1)
                time.sleep(1)
        except Exception as e:
            print(f"Playwright Error: {e}")

        browser.close()
    return video_url

def download_video_safe(url, output_path, task_id):
    """
    Smart downloader that switches between XHS and yt-dlp
    """
    if "xiaohongshu" in url or "xhslink" in url:
        print(f"[{task_id}] Mode: Xiaohongshu")
        direct_url = extract_xhs_playwright(resolve_xhs_link(url))
        if not direct_url:
            raise Exception("Could not extract XHS URL. Check Cookie or CAPTCHA.")
        
        # Download stream
        with requests.get(direct_url, stream=True, headers={'User-Agent': 'Mozilla/5.0'}) as r:
            r.raise_for_status()
            with open(output_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
    else:
        print(f"[{task_id}] Mode: yt-dlp")
        ydl_opts = {
            'format': 'best',
            'outtmpl': output_path,
            'quiet': True,
            'no_warnings': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

    if not os.path.exists(output_path) or os.path.getsize(output_path) < 1000:
        raise Exception("Download failed: File empty")
    
    return output_path


# ==========================================
# CORE: VIDEO PROCESSOR (FFMPEG)
# ==========================================

def get_video_duration(path):
    cmd = [FFMPEG_PATH, "-i", path, "-hide_banner"]
    result = subprocess.run(cmd, stderr=subprocess.PIPE, text=True)
    import re
    match = re.search(r"Duration: (\d{2}):(\d{2}):(\d{2}\.\d{2})", result.stderr)
    if match:
        h, m, s = map(float, match.groups())
        return h*3600 + m*60 + s
    return 0

def process_video_task(task_id, data, files_paths):
    """
    The main worker function. Optimized for Render (Low RAM).
    """
    temp_visual_raw = os.path.join(TEMP_DIR, f"raw_{task_id}.mp4")
    temp_processed = os.path.join(TEMP_DIR, f"processed_{task_id}.mp4")
    final_audio = os.path.join(TEMP_DIR, f"audio_{task_id}.mp3")
    output_vid = os.path.join(TEMP_DIR, f"final_{task_id}.mp4")

    uploaded_visuals = files_paths.get('visuals', [])
    uploaded_audios = files_paths.get('audios', [])

    try:
        tasks[task_id]['status'] = 'processing'
        tasks[task_id]['progress'] = 10
        print(f"[{task_id}] Task Started")

        # --- 1. GET VISUAL SOURCE ---
        visual_inputs = []
        if uploaded_visuals:
            visual_inputs = uploaded_visuals
        else:
            url = data.get('video_url')
            if not url: raise Exception("No video URL provided")
            download_video_safe(url, temp_visual_raw, task_id)
            visual_inputs = [temp_visual_raw]

        tasks[task_id]['progress'] = 30

        # --- 2. PREPARE VIDEO (Resizing / Watermark Removal) ---
        # We use a simplified filter chain to save memory
        
        remove_watermark = data.get('remove_watermark') == 'true'
        aspect_ratio = data.get('aspect_ratio', 'original')
        
        cmd_vid = [FFMPEG_PATH, "-y", "-i", visual_inputs[0]]
        
        vf = []
        
        # Scaling Logic
        if aspect_ratio == 'shortvideo':
            # Force 9:16 (1080x1920)
            vf.append("scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920")
        elif aspect_ratio == 'fullscreen':
            # Force 16:9 (1920x1080)
            vf.append("scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080")
        
        # Watermark Crop (Simple Zoom)
        if remove_watermark:
            vf.append("crop=iw*0.9:ih*0.9") # Crop 10% from edges

        if vf:
            cmd_vid.extend(["-vf", ",".join(vf)])
        
        # RENDER OPTIMIZATION: Use ultrafast preset
        cmd_vid.extend([
            "-c:v", "libx264", 
            "-preset", "ultrafast", 
            "-crf", "28", 
            "-an", 
            temp_processed
        ])
        
        print(f"[{task_id}] Encoding Video...")
        # Capture stderr to debug if it fails
        res = subprocess.run(cmd_vid, capture_output=True, text=True)
        if res.returncode != 0:
            print(res.stderr)
            raise Exception("FFmpeg Encoding Failed")
        
        tasks[task_id]['progress'] = 60

        # --- 3. PREPARE AUDIO ---
        audio_sources = uploaded_audios[:]
        # (Add logic here to fetch library sounds if needed)
        
        # If no audio provided, extract from original video
        if not audio_sources:
            subprocess.run([FFMPEG_PATH, "-y", "-i", visual_inputs[0], "-vn", final_audio], check=False)
        else:
            # Concatenate provided audio files
            # Simple method: Create a text file list for ffmpeg
            list_file = os.path.join(TEMP_DIR, f"list_{task_id}.txt")
            with open(list_file, 'w') as f:
                for a in audio_sources:
                    f.write(f"file '{a}'\n")
            
            subprocess.run([FFMPEG_PATH, "-y", "-f", "concat", "-safe", "0", "-i", list_file, "-c", "copy", final_audio], check=True)

        tasks[task_id]['progress'] = 80

        # --- 4. MERGE ---
        # Combine Video + Audio (Stream Copy for speed)
        cmd_merge = [
            FFMPEG_PATH, "-y",
            "-i", temp_processed,
            "-i", final_audio,
            "-c:v", "copy", # Fast copy
            "-c:a", "aac",  # Ensure audio compatibility
            "-shortest",    # Stop when shortest stream ends
            output_vid
        ]
        
        # Loop video if requested
        if data.get('duration') and int(data.get('duration')) > 0:
             # Insert -stream_loop before input
             cmd_merge.insert(2, "-stream_loop")
             cmd_merge.insert(3, "-1")

        print(f"[{task_id}] Merging...")
        subprocess.run(cmd_merge, check=True)

        tasks[task_id]['progress'] = 100
        tasks[task_id]['status'] = 'done'
        tasks[task_id]['file'] = output_vid

    except Exception as e:
        print(f"[{task_id}] ERROR: {e}")
        tasks[task_id]['status'] = 'error'
        tasks[task_id]['error'] = str(e)
    finally:
        # Cleanup temps
        for f in [temp_visual_raw, temp_processed, final_audio]:
             if os.path.exists(f): 
                 try: os.remove(f)
                 except: pass

# ==========================================
# FLASK APP
# ==========================================

app = Flask(__name__)

@app.route('/')
def home():
    if os.path.exists('index.html'):
        return send_file('index.html')
    return "Backend Running. Please upload index.html."

@app.route('/get-video', methods=['POST'])
def get_video_info():
    data = request.json
    url = data.get('url')
    try:
        resolved_url = resolve_xhs_link(url)
        # Just resolve the link, don't download yet for preview if possible
        # Or download to a temp file and serve it
        task_id = "preview_" + str(int(time.time()))
        path = os.path.join(TEMP_DIR, f"{task_id}.mp4")
        download_video_safe(url, path, task_id)
        return jsonify({'video_url': f"/preview/{task_id}.mp4", 'original_url': url})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/preview/<filename>')
def serve_preview(filename):
    return send_file(os.path.join(TEMP_DIR, filename))

@app.route('/start-merge', methods=['POST'])
def start_merge():
    import uuid
    import threading
    task_id = str(uuid.uuid4())
    tasks[task_id] = {'status': 'queued', 'progress': 0}
    
    # Save Uploads
    files_paths = {'visuals': [], 'audios': []}
    
    if 'visual_files' in request.files:
        for f in request.files.getlist('visual_files'):
            path = os.path.join(TEMP_DIR, f"{task_id}_{f.filename}")
            f.save(path)
            files_paths['visuals'].append(path)

    if 'audio_files' in request.files:
        for f in request.files.getlist('audio_files'):
            path = os.path.join(TEMP_DIR, f"{task_id}_{f.filename}")
            f.save(path)
            files_paths['audios'].append(path)

    # Start Background Thread
    data = request.form.to_dict()
    thread = threading.Thread(target=process_video_task, args=(task_id, data, files_paths))
    thread.start()
    
    return jsonify({'task_id': task_id})

@app.route('/progress/<task_id>')
def progress(task_id):
    return jsonify(tasks.get(task_id, {'status': 'not_found'}))

@app.route('/download-result/<task_id>')
def download_result(task_id):
    task = tasks.get(task_id)
    if task and task['status'] == 'done':
        return send_file(task['file'], as_attachment=True)
    return "File not ready", 404

if __name__ == '__main__':
    # Use PORT env var for Render
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)