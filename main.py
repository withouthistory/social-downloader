# Ensure we are in the project directory
cd /root/social-downloader

# Update Backend to Hybrid Logic (Restored YouTube API + Pro All-In-One for others)
cat << 'EOF' > /root/social-downloader/main.py
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import yt_dlp
import os
import glob
import requests
import asyncio
import string
import random
import subprocess
import re

app = FastAPI(title="Social Media Downloader API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class VideoRequest(BaseModel):
    url: str
    format: str = "mp4" 

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

def generate_short_id():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=8))

async def cleanup_file(filepath: str):
    await asyncio.sleep(600) 
    if os.path.exists(filepath):
        try: os.remove(filepath)
        except Exception: pass

def convert_to_mp3(input_path: str):
    output_path = input_path.rsplit('.', 1)[0] + ".mp3"
    try:
        subprocess.run(['ffmpeg', '-i', input_path, '-vn', '-acodec', 'libmp3lame', '-q:a', '2', output_path], check=True, capture_output=True)
        if os.path.exists(input_path): os.remove(input_path)
        return output_path
    except Exception: return input_path

def get_file_size_mb(filepath: str):
    if os.path.exists(filepath): return round(os.path.getsize(filepath) / (1024 * 1024), 2)
    return 0

def extract_with_ytdlp(url: str, is_mp3: bool, short_id: str, background_tasks: BackgroundTasks):
    out_template = os.path.join(DOWNLOAD_DIR, f'withouthustle.net-{short_id}.%(ext)s')
    ydl_opts = {
        'format': 'bestaudio/best' if is_mp3 else 'best',
        'outtmpl': out_template, 'quiet': True, 'noplaylist': True,
        'http_headers': {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    }
    if is_mp3: ydl_opts['postprocessors'] = [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3','preferredquality': '192'}]
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        ext = "mp3" if is_mp3 else "*"
        files = glob.glob(os.path.join(DOWNLOAD_DIR, f'withouthustle.net-{short_id}.{ext}'))
        if not files: raise Exception("Local engine blocked.")
        actual_filepath = files[0]
        background_tasks.add_task(cleanup_file, actual_filepath)
        return {
            "success": True, "title": info.get('title', 'Media'),
            "download_url": f"/api/download/{os.path.basename(actual_filepath)}",
            "thumbnail": info.get('thumbnail'), "filesize_mb": get_file_size_mb(actual_filepath)
        }

@app.post("/api/extract")
async def extract_video_link(request: VideoRequest, background_tasks: BackgroundTasks):
    short_id = generate_short_id()
    url_input = request.url.strip()
    is_mp3 = request.format.lower() == "mp3"
    domain = url_input.lower()

    # 1. SPECIALIST ROUTE: YOUTUBE (Restored dedicated API)
    if "youtube.com" in domain or "youtu.be" in domain:
        try:
            headers = {
                "x-rapidapi-host": "youtube-info-download-api.p.rapidapi.com",
                "x-rapidapi-key": "6cc2ad1a0fmsh6bbce3f718432fap169013jsn88c1fddd2f7d"
            }
            init_resp = requests.get(
                "https://youtube-info-download-api.p.rapidapi.com/ajax/download.php", 
                headers=headers, params={"format": "720", "url": url_input}, timeout=20
            )
            init_data = init_resp.json()
            progress_url = init_data.get("progress_url")
            
            target_url = None
            for _ in range(30): # Wait up to 60 seconds
                await asyncio.sleep(2)
                prog_data = requests.get(progress_url).json()
                if prog_data.get("text") == "Finished":
                    target_url = prog_data.get("download_url")
                    break
            
            if target_url:
                filename = f"withouthustle.net-{short_id}.mp4"
                filepath = os.path.join(DOWNLOAD_DIR, filename)
                with requests.get(target_url, stream=True) as r:
                    with open(filepath, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=8192): f.write(chunk)
                if is_mp3:
                    filepath = convert_to_mp3(filepath)
                    filename = os.path.basename(filepath)
                background_tasks.add_task(cleanup_file, filepath)
                return {"success": True, "title": init_data.get("info", {}).get("title", "YouTube Media"), "download_url": f"/api/download/{filename}", "thumbnail": init_data.get("info", {}).get("image"), "filesize_mb": get_file_size_mb(filepath)}
        except Exception as e:
            print(f"YT API Failed: {e}. Falling back to local...")

    # 2. PRO ROUTE: Instagram, Twitter, TikTok (Paid All-In-One API)
    else:
        clean_url = url_input.split('?')[0]
        try:
            headers = {
                "content-type": "application/json",
                "x-rapidapi-host": "social-download-all-in-one.p.rapidapi.com",
                "x-rapidapi-key": "6cc2ad1a0fmsh6bbce3f718432fap169013jsn88c1fddd2f7d"
            }
            api_response = requests.post(
                "https://social-download-all-in-one.p.rapidapi.com/v1/social/autolink", 
                json={"url": clean_url}, headers=headers, timeout=30
            )
            if api_response.status_code == 200:
                data = api_response.json()
                medias = data.get("medias", [])
                target_url = next((m.get("url") for m in medias if m.get("extension") == "mp4"), None)
                if not target_url: target_url = next((m.get("url") for m in medias), None)
                
                if target_url:
                    filename = f"withouthustle.net-{short_id}.mp4"
                    filepath = os.path.join(DOWNLOAD_DIR, filename)
                    with requests.get(target_url, stream=True) as r:
                        with open(filepath, 'wb') as f:
                            for chunk in r.iter_content(chunk_size=8192): f.write(chunk)
                    if is_mp3:
                        filepath = convert_to_mp3(filepath)
                        filename = os.path.basename(filepath)
                    background_tasks.add_task(cleanup_file, filepath)
                    return {"success": True, "title": data.get("title", "Social Media Content"), "download_url": f"/api/download/{filename}", "thumbnail": data.get("thumbnail"), "filesize_mb": get_file_size_mb(filepath)}
        except Exception as e:
            print(f"Pro API Error: {e}. Falling back...")

    # 3. FINAL FALLBACK: Local yt-dlp
    try:
        return extract_with_ytdlp(url_input, is_mp3, short_id, background_tasks)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Extraction failed: {str(e)}")

@app.get("/api/download/{filename}")
async def download_file(filename: str):
    filepath = os.path.join(DOWNLOAD_DIR, filename)
    if not os.path.exists(filepath): raise HTTPException(status_code=404, detail="Expired")
    return FileResponse(path=filepath, filename=filename, media_type='application/octet-stream')
EOF

# Restart server
fuser -k 8000/tcp ; nohup /root/social-downloader/venv/bin/python3 /root/social-downloader/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000 > /root/social-downloader/uvicorn.log 2>&1 &
