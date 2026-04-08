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
        try:
            os.remove(filepath)
        except Exception:
            pass

def convert_to_mp3(input_path: str):
    """Converts a video file to MP3 using ffmpeg"""
    output_path = input_path.rsplit('.', 1)[0] + ".mp3"
    try:
        subprocess.run([
            'ffmpeg', '-i', input_path, 
            '-vn', '-acodec', 'libmp3lame', '-q:a', '2', 
            output_path
        ], check=True, capture_output=True)
        if os.path.exists(input_path):
            os.remove(input_path)
        return output_path
    except Exception as e:
        print(f"FFmpeg Error: {e}")
        return input_path

@app.post("/api/extract")
async def extract_video_link(request: VideoRequest, background_tasks: BackgroundTasks):
    short_id = generate_short_id()
    domain = request.url.lower()
    is_mp3 = request.format.lower() == "mp3"
    
    # ==========================================
    # ROUTE 1: INSTAGRAM
    # ==========================================
    if "instagram.com" in domain:
        try:
            headers = {
                "content-type": "application/json",
                "x-rapidapi-host": "social-download-all-in-one.p.rapidapi.com",
                "x-rapidapi-key": "6cc2ad1a0fmsh6bbce3f718432fap169013jsn88c1fddd2f7d"
            }
            api_response = requests.post(
                "https://social-download-all-in-one.p.rapidapi.com/v1/social/autolink", 
                json={"url": request.url}, 
                headers=headers
            )
            
            if api_response.status_code == 429:
                raise HTTPException(status_code=429, detail="Instagram limit reached. Try again later.")
                
            data = api_response.json()
            medias = data.get("medias", [])
            target_url = next((m.get("url") for m in medias if m.get("extension") == "mp4"), None)

            if not target_url:
                raise Exception("Could not find a valid video stream.")

            filename = f"withouthustle.net-{short_id}.mp4"
            filepath = os.path.join(DOWNLOAD_DIR, filename)
            
            with requests.get(target_url, stream=True) as r:
                with open(filepath, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)

            if is_mp3:
                filepath = convert_to_mp3(filepath)
                filename = os.path.basename(filepath)

            background_tasks.add_task(cleanup_file, filepath)

            return {
                "success": True,
                "title": data.get("title", "Instagram Media"),
                "download_url": f"/api/download/{filename}",
                "thumbnail": data.get("thumbnail")
            }
        except Exception as e:
            if isinstance(e, HTTPException): raise e
            raise HTTPException(status_code=400, detail=str(e))

    # ==========================================
    # ROUTE 2: YOUTUBE
    # ==========================================
    elif "youtube.com" in domain or "youtu.be" in domain:
        try:
            headers = {
                "x-rapidapi-host": "youtube-info-download-api.p.rapidapi.com",
                "x-rapidapi-key": "6cc2ad1a0fmsh6bbce3f718432fap169013jsn88c1fddd2f7d"
            }
            init_resp = requests.get(
                "https://youtube-info-download-api.p.rapidapi.com/ajax/download.php", 
                headers=headers, 
                params={"format": "720", "url": request.url}
            )
            
            init_data = init_resp.json()
            progress_url = init_data.get("progress_url")
            target_url = None
            
            for _ in range(30):
                await asyncio.sleep(2)
                prog_data = requests.get(progress_url).json()
                if prog_data.get("text") == "Finished":
                    target_url = prog_data.get("download_url")
                    break
            
            if not target_url: raise Exception("YouTube Proxy Timeout")

            filename = f"withouthustle.net-{short_id}.mp4"
            filepath = os.path.join(DOWNLOAD_DIR, filename)
            
            with requests.get(target_url, stream=True) as r:
                with open(filepath, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)

            if is_mp3:
                filepath = convert_to_mp3(filepath)
                filename = os.path.basename(filepath)

            background_tasks.add_task(cleanup_file, filepath)

            return {
                "success": True,
                "title": init_data.get("info", {}).get("title", "YouTube Media"),
                "download_url": f"/api/download/{filename}",
                "thumbnail": init_data.get("info", {}).get("image")
            }
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    # ==========================================
    # ROUTE 3: LOCAL ENGINE (X, TikTok, FB)
    # ==========================================
    else:
        out_template = os.path.join(DOWNLOAD_DIR, f'withouthustle.net-{short_id}.%(ext)s')
        ydl_opts = {
            'format': 'bestaudio/best' if is_mp3 else 'best',
            'outtmpl': out_template,
            'quiet': True,
            'noplaylist': True, 
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            }
        }

        if is_mp3:
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(request.url, download=True)
                ext = "mp3" if is_mp3 else "*"
                search_pattern = os.path.join(DOWNLOAD_DIR, f'withouthustle.net-{short_id}.{ext}')
                files = glob.glob(search_pattern)
                if not files: raise Exception("Download failed.")
                
                actual_filepath = files[0]
                filename_only = os.path.basename(actual_filepath)
                background_tasks.add_task(cleanup_file, actual_filepath)
                
                return {
                    "success": True,
                    "title": info.get('title', 'Media'),
                    "download_url": f"/api/download/{filename_only}",
                    "thumbnail": info.get('thumbnail')
                }
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/download/{filename}")
async def download_file(filename: str):
    filepath = os.path.join(DOWNLOAD_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File expired.")
    return FileResponse(path=filepath, filename=filename, media_type='application/octet-stream')
