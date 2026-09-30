# -*- coding: utf-8 -*-
import os
import re
import time
import shutil
from urllib.parse import quote
from flask import Flask, render_template, request, jsonify, send_file
import yt_dlp

try:
    import librosa
    import numpy as np
    LIBROSA_AVAILABLE = True
except ImportError:
    LIBROSA_AVAILABLE = False

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Đã trỏ template_folder về thư mục 'templates' chuẩn
app = Flask(__name__, static_folder='static', template_folder='templates')

DOWNLOAD_FOLDER = os.path.join(BASE_DIR, "downloads")
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

download_history = []

@app.route("/")
def index():
    return render_template("index_5.html")

@app.route("/api/stats", methods=["GET"])
def get_stats():
    try:
        total, used, free = shutil.disk_usage(DOWNLOAD_FOLDER)
        free_gb = round(free / (1024**3), 2)
    except Exception:
        free_gb = 0.0
        
    return jsonify({
        "disk_free_gb": f"{free_gb} GB",
        "download_count": len(download_history),
        "history": download_history[::-1]
    })

@app.route('/api/youtube-search', methods=['GET'])
def youtube_search():
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({'success': False, 'error': 'Vui lòng nhập từ khóa tìm kiếm!'}), 400

    try:
        ydl_opts = {
            'extract_flat': True,
            'max_results': 10,
            'quiet': True,
        }
        search_query = f"ytsearch10:{query}"

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(search_query, download=False)
            entries = info.get('entries', [])

        videos = []
        for entry in entries:
            video_id = entry.get('id')
            
            raw_duration = entry.get('duration', 0)
            try:
                dur_int = int(raw_duration) if raw_duration else 0
                m = dur_int // 60
                s = dur_int % 60
                duration_str = f"{m:02d}:{s:02d}"
            except Exception:
                duration_str = "00:00"

            videos.append({
                'title': entry.get('title', 'Unknown Title'),
                'channelTitle': entry.get('uploader') or entry.get('channel') or 'Unknown Channel',
                'thumbnail': f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg" if video_id else '',
                'duration': duration_str,
                'views': entry.get('view_count', 'N/A'),
                'publishedAt': entry.get('upload_date', ''),
                'url': f"https://www.youtube.com/watch?v={video_id}" if video_id else ''
            })

        response_data = {
            'success': True,
            'channel': {
                'name': query,
                'subscribers': 'N/A',
                'videosCount': f'{len(videos)} video tìm thấy',
                'avatar': videos[0]['thumbnail'] if videos else '',
                'url': f'https://www.youtube.com/results?search_query={quote(query)}',
                'description': f'Kết quả tra cứu trực tiếp từ hệ thống cho từ khóa: {query}'
            },
            'videos': videos
        }
        return jsonify(response_data)

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route("/api/download", methods=["POST"])
def download_audio():
    data = request.get_json() or {}
    url = data.get('url')
    format_option = data.get('format', 'WAV')
    
    if not url:
        return jsonify({'error': 'Vui lòng cung cấp đường dẫn YouTube!'}), 400

    if format_option.upper() == 'FLAC':
        ext = 'flac'
        postprocessors = [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'flac'}]
    elif format_option.upper() == 'MP3':
        ext = 'mp3'
        postprocessors = [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '320'}]
    else:
        ext = 'wav'
        postprocessors = [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'wav'}]

    timestamp = int(time.time())
    output_template = os.path.join(DOWNLOAD_FOLDER, f"%(title)s_{timestamp}.%(ext)s")

    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': postprocessors,
        'outtmpl': output_template,
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        'cookiefile': 'cookies.txt',  # Thêm dòng này để nhận diện tài khoản
        'extractor_args': {
            'youtube': {
                'player_client': ['ios', 'mweb', 'web']
            }
        }
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get('title', 'Unknown Title')
            duration_sec = info.get('duration', 180)
            
            minutes = duration_sec // 60
            seconds = duration_sec % 60
            duration_str = f"{minutes:02d}:{seconds:02d}"

            safe_title = re.sub(r'[\\/*?:"<>|]', "", title)
            
            file_path_base = ydl.prepare_filename(info)
            final_file_path = os.path.splitext(file_path_base)[0] + f".{ext}"

        if os.path.exists(final_file_path):
            current_time = time.strftime("%H:%M %d/%m/%Y")
            
            download_history.append({
                "title": safe_title,
                "duration": duration_str,
                "format": format_option.upper(),
                "time": current_time
            })

            filename_to_download = f"{safe_title}.{ext}"
            encoded_title = quote(filename_to_download)
            
            response = send_file(
                final_file_path,
                as_attachment=True,
                download_name=filename_to_download,
                mimetype=f"audio/{ext}"
            )
            response.headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{encoded_title}"
            response.headers["Access-Control-Expose-Headers"] = "Content-Disposition"
            return response
        else:
            return jsonify({'error': 'Không tìm thấy file sau khi chuyển đổi.'}), 500
    
    except Exception as e:
        clean_error = re.sub(r'\x1b\[[0-9;]*m', '', str(e))
        return jsonify({'error': clean_error}), 500

@app.route("/api/download-history", methods=["GET"])
def get_download_history():
    return jsonify(download_history[::-1])

@app.route("/api/download-history/<int:index>", methods=["DELETE"])
def delete_history_item(index):
    try:
        real_index = len(download_history) - 1 - index
        if 0 <= real_index < len(download_history):
            download_history.pop(real_index)
            return jsonify({"success": True})
        return jsonify({"error": "Không tìm thấy mục"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/latest-audio", methods=["GET"])
def get_latest_audio():
    try:
        files = [os.path.join(DOWNLOAD_FOLDER, f) for f in os.listdir(DOWNLOAD_FOLDER) if f.endswith(('.wav', '.mp3', '.flac', '.m4a', '.ogg'))]
        if not files:
            return "", 404
        latest_file = max(files, key=os.path.getmtime)
        return send_file(latest_file)
    except Exception:
        return "", 404

@app.route("/api/upload-analyze", methods=["POST"])
def upload_analyze():
    if 'audio' not in request.files:
        return jsonify({'error': 'Không tìm thấy file tải lên'}), 400
    
    file = request.files['audio']
    if file.filename == '':
        return jsonify({'error': 'Chưa chọn file'}), 400

    filename = file.filename
    save_path = os.path.join(DOWNLOAD_FOLDER, f"uploaded_{int(time.time())}_{filename}")
    file.save(save_path)

    bpm_val = 120
    key_val = "C Major"

    if LIBROSA_AVAILABLE:
        try:
            y, sr = librosa.load(save_path, duration=60)
            tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
            if isinstance(tempo, np.ndarray):
                bpm_val = round(float(tempo[0]), 1)
            else:
                bpm_val = round(float(tempo), 1)

            chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
            chroma_mean = np.mean(chroma, axis=1)
            
            major_profile = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
            minor_profile = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
            
            keys = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
            max_corr = -1
            best_key = "C Major"
            
            for i in range(12):
                corr_major = np.corrcoef(chroma_mean, np.roll(major_profile, i))[0, 1]
                if corr_major > max_corr:
                    max_corr = corr_major
                    best_key = f"{keys[i]} Major"
                
                corr_minor = np.corrcoef(chroma_mean, np.roll(minor_profile, i))[0, 1]
                if corr_minor > max_corr:
                    max_corr = corr_minor
                    best_key = f"{keys[i]} Minor"
                    
            key_val = best_key
        except Exception as e:
            print(f"Lỗi phân tích librosa: {e}")

    return jsonify({
        "success": True,
        "bpm": str(bpm_val),
        "key": key_val,
        "filename": filename
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)