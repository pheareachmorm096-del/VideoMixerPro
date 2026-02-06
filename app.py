import os
import uuid
import threading
import requests
import shutil
import re
import traceback
from flask import Flask, render_template, request, jsonify, Response, send_file, send_from_directory

# Import config and modules
from config import *
# --- UPDATE: Import the new universal function instead of the old XHS ones ---
from utils_scraper import extract_video_universal 
from task_processor import process_video_task

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024 

# --- SAFETY WRAPPER FOR ERRORS ---
@app.errorhandler(500)
def internal_error(error):
    return jsonify({"error": "Server Error (500): Check terminal for details"}), 500

@app.route('/start-merge', methods=['POST'])
def start_merge():
    try:
        task_id = str(uuid.uuid4())
        files_paths = {'visuals': [], 'audios': [], 'effect': None}
        
        # 1. Visuals
        visual_files = request.files.getlist('visual_files')
        if visual_files:
            for i, f in enumerate(visual_files):
                if f.filename:
                    path = os.path.join(TEMP_DIR, f"visual_{task_id}_{i}_{f.filename}")
                    f.save(path)
                    files_paths['visuals'].append(path)
        
        # Suggestions (Using getlist directly is safer)
        for fname in request.form.getlist('visual_suggestions'):
            src = os.path.join(SUGGESTIONS_DIR, 'video', fname)
            if not os.path.exists(src): src = os.path.join(SUGGESTIONS_DIR, 'image', fname)
            if os.path.exists(src):
                dest = os.path.join(TEMP_DIR, f"sugg_vis_{task_id}_{fname}")
                shutil.copy(src, dest)
                files_paths['visuals'].append(dest)

        # 2. Audios
        audio_files = request.files.getlist('audio_files')
        if audio_files:
            for i, f in enumerate(audio_files):
                if f.filename:
                    path = os.path.join(TEMP_DIR, f"audio_{task_id}_{i}_{f.filename}")
                    f.save(path)
                    files_paths['audios'].append(path)
                    
        for fname in request.form.getlist('audio_suggestions'):
            src = os.path.join(SUGGESTIONS_DIR, 'audio', fname)
            if os.path.exists(src):
                dest = os.path.join(TEMP_DIR, f"sugg_aud_{task_id}_{fname}")
                shutil.copy(src, dest)
                files_paths['audios'].append(dest)

        # 3. Effect
        effect_file = request.files.get('effect_file')
        if effect_file:
            path = os.path.join(TEMP_DIR, f"effect_{task_id}.mp4")
            effect_file.save(path)
            files_paths['effect'] = path

        tasks[task_id] = {'status': 'starting', 'progress': 0, 'file': None}
        
        # 4. Data Preparation (FIXED PART)
        # We extract specific lists and single values properly before threading
        clean_data = {
            "video_url": request.form.get("video_url", ""),
            "duration": request.form.get("duration", "0"),
            "aspect_ratio": request.form.get("aspect_ratio", "original"),
            "remove_outro": request.form.get("remove_outro", "false"),
            "remove_watermark": request.form.get("remove_watermark", "false"),
            "audio_strategy": request.form.get("audio_strategy", "sequential"),
            # This is the important fix: extracting the list correctly
            "library_sounds": request.form.getlist("library_sounds") 
        }

        # Start background thread with the plain dictionary
        thread = threading.Thread(target=process_video_task, args=(task_id, clean_data, files_paths))
        thread.start()
        
        return jsonify({"task_id": task_id})
        
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
@app.route('/get-video', methods=['POST'])
def get_video():
    try:
        # Get raw text
        json_data = request.get_json(force=True, silent=True)
        if not json_data:
            return jsonify({"error": "Invalid JSON data received"}), 400
            
        raw_text = json_data.get('url', '')
        
        # Regex to extract the URL from the messy text
        match = re.search(r'(https?://[a-zA-Z0-9./?=&_%-]+)', raw_text)
        
        if not match: 
            return jsonify({"error": "No valid link found. Please paste a full http://... link"}), 400
        
        clean_url = match.group(1)
        
        # --- UPDATE: Use universal extractor ---
        # This now handles YouTube, TikTok, XHS, etc. automatically
        video_url = extract_video_universal(clean_url)
        
        if video_url:
            encoded_vid = requests.utils.quote(video_url)
            return jsonify({
                "success": True, 
                "video_url": f"/proxy-video?url={encoded_vid}", 
                "original_url": video_url
            })
            
        return jsonify({"error": "Failed to extract video. The link might be Private or Not Supported."}), 404

    except Exception as e:
        print("!!! SERVER CRASH IN /get-video !!!")
        traceback.print_exc() 
        return jsonify({"error": f"Server Error: {str(e)}"}), 500

@app.route('/proxy-video')
def proxy_video():
    url = request.args.get('url')
    if not url: return "No URL", 400
    
    # Generic headers usually work for most proxied content
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }

    try:
        req = requests.get(url, headers=headers, stream=True, timeout=20)
        return Response(req.iter_content(chunk_size=1024*1024), content_type="video/mp4")
    except Exception as e: return str(e), 500

# --- Standard Routes ---
@app.route('/')
def index(): return render_template('index.html')

@app.route('/progress/<task_id>')
def get_progress(task_id):
    task = tasks.get(task_id)
    if not task: return jsonify({"error": "Task not found"}), 404
    return jsonify(task)

@app.route('/download-result/<task_id>')
def download_result(task_id):
    task = tasks.get(task_id)
    if not task or not task.get('file'): return "File not ready", 404
    return send_file(task['file'], as_attachment=True, download_name="final_video.mp4")

@app.route('/list-suggestions')
def list_suggestions():
    data = {'audio': [], 'video': [], 'image': []}
    for cat in data.keys():
        p = os.path.join(SUGGESTIONS_DIR, cat)
        if os.path.exists(p): data[cat] = [f for f in os.listdir(p) if not f.startswith('.')]
    return jsonify(data)

@app.route('/suggestions/<type>/<filename>')
def serve_suggestion(type, filename):
    return send_from_directory(os.path.join(SUGGESTIONS_DIR, type), filename)

@app.route('/list-sounds')
def list_sounds():
    if os.path.exists(SOUNDS_DIR): return jsonify([f for f in os.listdir(SOUNDS_DIR) if f.endswith('.mp3')])
    return jsonify([])

@app.route('/sounds/<path:filename>')
def serve_sound(filename):
    response = send_from_directory(SOUNDS_DIR, filename, mimetype='audio/mpeg')
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response

@app.route('/delete-sound', methods=['POST'])
def delete_sound():
    filename = request.json.get('filename')
    path = os.path.join(SOUNDS_DIR, filename)
    if os.path.exists(path):
        os.remove(path)
        return jsonify({"success": True})
    return jsonify({"error": "File not found"}), 404

@app.route('/search-freesound')
def search_freesound():
    query = request.args.get('q', 'nature')
    url = f"https://freesound.org/apiv2/search/text/?query={query}&filter=license:\"Creative Commons 0\"&token={FREESOUND_API_KEY}&fields=name,id,previews,duration"
    try: 
        return jsonify(requests.get(url).json().get('results', []))
    except Exception as e: 
        return jsonify({"error": str(e)}), 500

@app.route('/import-freesound', methods=['POST'])
def import_freesound():
    data = request.json
    preview_url = data.get('url')
    clean_id = str(data.get('id')).strip()
    filename = f"freesound_{clean_id}.mp3"
    save_path = os.path.join(SOUNDS_DIR, filename)
    try:
        r = requests.get(preview_url, stream=True)
        if r.status_code == 200:
            with open(save_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192): f.write(chunk)
            return jsonify({"success": True, "filename": filename})
        return jsonify({"error": "Failed"}), 400
    except Exception as e: return jsonify({"error": str(e)}), 500

# if __name__ == '__main__':
#     app.run(debug=True, port=5000, threaded=True)
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)