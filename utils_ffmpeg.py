import subprocess
import os
import re
from imageio_ffmpeg import get_ffmpeg_exe
from config import PREFERRED_ENCODER

ffmpeg_path = get_ffmpeg_exe()

FFMPEG_FLAGS = 0
if os.name == 'nt':
    FFMPEG_FLAGS = 0x00004000 | 0x08000000

def get_best_encoder():
    if PREFERRED_ENCODER != 'auto': return PREFERRED_ENCODER
    try:
        if os.name == 'nt': return 'libx264' # Change to 'h264_nvenc' for NVIDIA
        elif os.uname().sysname == 'Darwin': return 'h264_videotoolbox'
    except: pass
    return 'libx264'

VIDEO_ENCODER = get_best_encoder()

def run_ffmpeg(cmd):
    subprocess.run(
        cmd, 
        check=True, 
        timeout=3600,
        creationflags=FFMPEG_FLAGS
    )

def get_video_duration(file_path):
    try:
        cmd = [ffmpeg_path, "-i", file_path]
        result = subprocess.run(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True, creationflags=FFMPEG_FLAGS)
        match = re.search(r"Duration: (\d{2}):(\d{2}):(\d{2}\.\d{2})", result.stderr)
        if match:
            h, m, s = map(float, match.groups())
            return h * 3600 + m * 60 + s
    except: pass
    return 10.0
