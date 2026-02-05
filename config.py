import os
import platform
# --- AUTHENTICATION & KEYS ---
XHS_COOKIE = "REPLACE_WITH_YOUR_REAL_COOKIE_HERE" 
FREESOUND_API_KEY = "Yx97OenNHyQOZQuq0PpROcoVQIgNOEl8hYWQ6VrI"

# --- SYSTEM SETTINGS ---
# Set to 'h264_nvenc' (NVIDIA), 'h264_videotoolbox' (Mac), or 'auto'
PREFERRED_ENCODER = 'auto' 

# --- SHARED HEADERS ---
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Referer": "https://www.xiaohongshu.com/",
    "Origin": "https://www.xiaohongshu.com",
    "Cookie": XHS_COOKIE
}

# --- PATHS ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SOUNDS_DIR = os.path.join(BASE_DIR, "sounds")
TEMP_DIR = os.path.join(BASE_DIR, "temp")
SUGGESTIONS_DIR = os.path.join(BASE_DIR, "suggestions")
# If it's in your System Path, Python can find it just by name
if platform.system() == "Windows":
    ffmpeg_path = os.path.join(os.getcwd(), "ffmpeg.exe")
    ffprobe_path = os.path.join(os.getcwd(), "ffprobe.exe")
else:
    # This will work on Linux hosting automatically
    ffmpeg_path = "ffmpeg"
    ffprobe_path = "ffprobe"
# Ensure directories exist
for d in [SOUNDS_DIR, TEMP_DIR, SUGGESTIONS_DIR]:
    if not os.path.exists(d): os.makedirs(d)
for sub in ['audio', 'video', 'image']:
    p = os.path.join(SUGGESTIONS_DIR, sub)
    if not os.path.exists(p): os.makedirs(p)

tasks = {}
