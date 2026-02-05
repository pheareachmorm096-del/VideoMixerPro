import os
import shutil
import subprocess
import yt_dlp
from config import TEMP_DIR, SOUNDS_DIR, SUGGESTIONS_DIR, HEADERS, tasks
from utils_ffmpeg import run_ffmpeg, get_video_duration, VIDEO_ENCODER, ffmpeg_path

def download_douyin(video_url, output_path, task_id):
    """
    Fast Douyin/TikTok download using yt-dlp with multi-threading.
    """
    try:
        print(f"[{task_id}] Starting fast download via yt-dlp...")
        ydl_opts = {
            'format': 'bestvideo+bestaudio/best',
            'outtmpl': output_path,
            'quiet': True,
            'no_warnings': True,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1'
            },
            'noprogress': True,
            'external_downloader': 'aria2c',          # multi-threaded download
            'external_downloader_args': ['-x', '16', '-k', '1M'],  # 16 threads
            'merge_output_format': 'mp4',
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])

        if not os.path.exists(output_path) or os.path.getsize(output_path) < 50_000:
            raise Exception("Downloaded file too small, likely blocked.")

        print(f"[{task_id}] Download completed successfully!")
        return output_path

    except Exception as e:
        print(f"[{task_id}] Douyin download error: {e}")
        raise


def process_video_task(task_id, data, files_paths):
    temp_visual_raw = os.path.join(TEMP_DIR, f"raw_visual_{task_id}.mp4")
    temp_visual_clean = os.path.join(TEMP_DIR, f"clean_visual_{task_id}.mp4") 
    temp_base_unit = os.path.join(TEMP_DIR, f"base_unit_{task_id}.mp4")
    final_audio_path = os.path.join(TEMP_DIR, f"full_audio_{task_id}.mp3")
    output_vid = os.path.join(TEMP_DIR, f"final_{task_id}.mp4")

    uploaded_visuals = files_paths.get('visuals', [])
    uploaded_audios = files_paths.get('audios', [])
    temp_effect = files_paths.get('effect')

    try:
        print(f"[{task_id}] Processing Started | Encoder: {VIDEO_ENCODER}")
        
        # --- 1. Parameters ---
        video_url = data.get('video_url')
        duration_min = float(data.get('duration', -1))
        target_duration_sec = duration_min * 60 if duration_min > 0 else 0
        
        effect_type = data.get('effect_type', "none")
        remove_outro = data.get('remove_outro') == 'true'
        remove_watermark = data.get('remove_watermark') == 'true'
        audio_strategy = data.get('audio_strategy', 'sequential') 
        audio_switch_time = float(data.get('audio_switch_time', 10))
        library_sounds_list = data.get('library_sounds', []) 
        aspect_ratio_mode = data.get('aspect_ratio', 'original') 

        tasks[task_id]['status'] = 'processing'
        tasks[task_id]['progress'] = 5

        # --- 2. Handle Visual Inputs ---
        visual_inputs = []
        if uploaded_visuals:
            visual_inputs = uploaded_visuals
        else:
            if not video_url: raise Exception("No Video Source")
            temp_visual_raw = download_douyin(video_url, temp_visual_raw, task_id)

            # Only sanitize if file seems broken
            file_size = os.path.getsize(temp_visual_raw)
            if file_size < 100_000:  # <100KB is likely an error page
                print(f"[{task_id}] Video small, sanitizing...")
                sanitize_cmd = [
                    ffmpeg_path, "-y", "-ignore_unknown", 
                    "-i", temp_visual_raw, 
                    "-c:v", "copy", "-c:a", "copy", 
                    "-map_metadata", "-1",
                    temp_visual_clean
                ]
                subprocess.run(sanitize_cmd, check=True)
                visual_inputs = [temp_visual_clean]
            else:
                visual_inputs = [temp_visual_raw]

        tasks[task_id]['progress'] = 20

        # --- 3. Video Filter Chain (Optimized) ---
        try:
            base_dur = get_video_duration(visual_inputs[0])
        except:
            base_dur = 10

        if remove_outro and base_dur > 3: base_dur -= 2.5

        # FAST PATH: Skip filters if possible
        fast_path = (not remove_watermark) and (aspect_ratio_mode == "original") and (not temp_effect) and len(visual_inputs) == 1
        if fast_path:
            print(f"[{task_id}] Step 3 fast path: copying video directly")
            shutil.copyfile(visual_inputs[0], temp_base_unit)
        else:
            # SLOW PATH: original filter_complex logic
            cmd_base = [ffmpeg_path, "-y", "-ignore_unknown"]
            filter_chain = []
            
            for i, v_path in enumerate(visual_inputs):
                if v_path.lower().endswith(('.png', '.jpg')):
                    cmd_base.extend(["-loop", "1", "-t", "5", "-i", v_path])
                else:
                    cmd_base.extend(["-i", v_path])
            
            effect_index = len(visual_inputs)
            if temp_effect: cmd_base.extend(["-stream_loop", "-1", "-i", temp_effect])
            
            tw, th = (1920, 1080)
            if aspect_ratio_mode == "shortvideo":
                tw, th = (1080, 1920)

            for i in range(len(visual_inputs)):
                vf_steps = ["fps=30", "format=yuv420p"]
                if remove_watermark:
                    z_w, z_h = (int(tw * 1.12), int(th * 1.12))
                    vf_steps.append(f"scale={z_w}:{z_h}:force_original_aspect_ratio=increase")
                    vf_steps.append(f"crop={tw}:{th}")
                elif aspect_ratio_mode != "original":
                    vf_steps.append(f"scale={tw}:{th}:force_original_aspect_ratio=increase,crop={tw}:{th}")
                else:
                    vf_steps.append("scale=trunc(iw/2)*2:trunc(ih/2)*2")
                vf_steps.append("setsar=1")
                filter_chain.append(f"[{i}:v]{','.join(vf_steps)}[v{i}_clean]")

            if len(visual_inputs) > 1:
                concat_str = "".join([f"[v{i}_clean]" for i in range(len(visual_inputs))])
                filter_chain.append(f"{concat_str}concat=n={len(visual_inputs)}:v=1:a=0[v_joined]")
                curr_v = "[v_joined]"
            else:
                curr_v = "[v0_clean]"

            filter_chain.append(f"{curr_v}trim=duration={base_dur},setpts=PTS-STARTPTS[v_trimmed]")
            final_v_map = "[v_trimmed]"

            if temp_effect:
                filter_chain.append(f"[{effect_index}:v]{final_v_map}scale2ref[eff_resized][base_ref]")
                if effect_type == "chromakey":
                    filter_chain.append(f"[eff_resized]colorkey=0x00FF00:0.3:0.2[eff_alpha]")
                    filter_chain.append(f"[base_ref][eff_alpha]overlay=shortest=1[v_final]")
                else:
                    filter_chain.append(f"[eff_resized][base_ref]blend=all_mode=screen[v_final]")
                final_v_map = "[v_final]"

            cmd_base.extend([
                "-filter_complex", ";".join(filter_chain),
                "-map", final_v_map,
                "-c:v", VIDEO_ENCODER,
                "-an",
                "-pix_fmt", "yuv420p",
                temp_base_unit
            ])
            if VIDEO_ENCODER == 'libx264':
                cmd_base.extend(["-preset", "ultrafast", "-crf", "23", "-threads", "0"])

            run_ffmpeg(cmd_base)

        tasks[task_id]['progress'] = 40

        # --- 4. Audio Processing ---
        audio_sources = uploaded_audios[:]
        if library_sounds_list:
            for s in library_sounds_list:
                p = os.path.join(SOUNDS_DIR, s)
                if not os.path.exists(p): p = os.path.join(SUGGESTIONS_DIR, 'audio', s)
                if os.path.exists(p): audio_sources.append(p)

        if not audio_sources:
            src_for_audio = visual_inputs[0]
            subprocess.run([ffmpeg_path, "-y", "-ignore_unknown", "-i", src_for_audio, "-vn", "-c:a", "libmp3lame", final_audio_path], stderr=subprocess.PIPE)
            if not os.path.exists(final_audio_path) or os.path.getsize(final_audio_path) < 1000:
                dur = target_duration_sec if target_duration_sec > 0 else 10
                subprocess.run([ffmpeg_path, "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", str(dur), final_audio_path], check=True)
        else:
            cmd_aud = [ffmpeg_path, "-y"]
            a_filter_chain = []
            gen_duration = target_duration_sec if target_duration_sec > 0 else base_dur
            seg_time = audio_switch_time if audio_strategy == 'switch' else (gen_duration / len(audio_sources))
            for i, a_path in enumerate(audio_sources):
                cmd_aud.extend(["-stream_loop", "-1", "-i", a_path])
                if audio_strategy == 'sequential' or len(audio_sources) == 1:
                    a_filter_chain.append(f"[{i}:a]atrim=0:{seg_time},asetpts=PTS-STARTPTS[a{i}]")
                else:
                    a_filter_chain.append(f"[{i}:a]atrim=0:{seg_time},asetpts=PTS-STARTPTS,afade=t=in:st=0:d=1,afade=t=out:st={seg_time-1}:d=1[a{i}]")
            concat_str = "".join([f"[a{i}]" for i in range(len(audio_sources))])
            a_filter_chain.append(f"{concat_str}concat=n={len(audio_sources)}:v=0:a=1[outa]")
            cmd_aud.extend(["-filter_complex", ";".join(a_filter_chain), "-map", "[outa]", "-t", str(gen_duration), "-c:a", "libmp3lame", final_audio_path])
            run_ffmpeg(cmd_aud)

        tasks[task_id]['progress'] = 70

        # --- 5. Final Assembly ---
        cmd_final = [ffmpeg_path, "-y"]
        if target_duration_sec > 0: cmd_final.extend(["-stream_loop", "-1"])
        cmd_final.extend(["-i", temp_base_unit, "-i", final_audio_path])
        cmd_final.extend(["-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "copy", "-shortest", output_vid])
        run_ffmpeg(cmd_final)

        tasks[task_id]['progress'] = 100
        tasks[task_id]['status'] = 'done'
        tasks[task_id]['file'] = output_vid

    except Exception as e:
        print(f"[{task_id}] ERROR: {e}")
        tasks[task_id]['status'] = 'error'
        tasks[task_id]['error'] = str(e)

    finally:
        clean = [temp_visual_raw, temp_visual_clean, temp_base_unit, final_audio_path, temp_effect]
        if uploaded_visuals: clean.extend(uploaded_visuals)
        if uploaded_audios: clean.extend(uploaded_audios)
        for f in clean:
            if f and os.path.exists(f):
                try: os.remove(f)
                except: pass
