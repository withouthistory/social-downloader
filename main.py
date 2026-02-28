from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import yt_dlp
import os
import uuid
import glob
import requests
import time 

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

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

def cleanup_file(filepath: str):
    if os.path.exists(filepath):
        os.remove(filepath)

@app.post("/api/extract")
async def extract_video_link(request: VideoRequest, req: Request):
    file_id = str(uuid.uuid4())
    domain = request.url.lower()

    # ==========================================
    # ROUTE 1: INSTAGRAM (Proxy Tunnel 1)
    # ==========================================
    if "instagram.com" in domain:
        try:
            headers = {
                "content-type": "application/json",
                "x-rapidapi-host": "social-download-all-in-one.p.rapidapi.com",
                "x-rapidapi-key": "6cc2ad1a0fmsh6bbce3f718432fap169013jsn88c1fddd2f7d"
            }
            payload = {"url": request.url}
            api_response = requests.post("https://social-download-all-in-one.p.rapidapi.com/v1/social/autolink", json=payload, headers=headers)
            
            # Catch API Limits for Instagram
            if api_response.status_code == 429:
                raise HTTPException(status_code=429, detail="The Instagram request limit has been reached today. Please try again tomorrow.")
                
            data = api_response.json()

            if data.get("error"):
                raise Exception(data.get("message", "API returned an error"))

            medias = data.get("medias", [])
            target_url = None

            for m in medias:
                if m.get("type") == "video" and m.get("is_audio") is True and m.get("extension") == "mp4":
                    target_url = m.get("url")
                    break

            if not target_url:
                for m in medias:
                    if m.get("type") == "video" and m.get("extension") == "mp4":
                        target_url = m.get("url")
                        break

            if not target_url:
                raise Exception("Proxy could not find a valid MP4 stream.")

            filename = f"{file_id}.mp4"
            filepath = os.path.join(DOWNLOAD_DIR, filename)
            
            vid_resp = requests.get(target_url, stream=True)
            vid_resp.raise_for_status()
            
            with open(filepath, 'wb') as f:
                for chunk in vid_resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            return {
                "success": True,
                "title": data.get("title", "Instagram Video"),
                "download_url": f"/api/download/{filename}",
                "thumbnail": data.get("thumbnail")
            }
        except HTTPException as http_exc:
            raise http_exc
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Instagram Tunnel Error: {str(e)}")

    # ==========================================
    # ROUTE 2: YOUTUBE (Asynchronous Proxy Tunnel 2)
    # ==========================================
    elif "youtube.com" in domain or "youtu.be" in domain:
        try:
            headers = {
                "x-rapidapi-host": "youtube-info-download-api.p.rapidapi.com",
                "x-rapidapi-key": "6cc2ad1a0fmsh6bbce3f718432fap169013jsn88c1fddd2f7d"
            }
            params = {
                "format": "720", 
                "add_info": "1",
                "url": request.url
            }
            
            init_resp = requests.get("https://youtube-info-download-api.p.rapidapi.com/ajax/download.php", headers=headers, params=params)
            
            # Catch API Limits for YouTube
            if init_resp.status_code == 429:
                raise HTTPException(status_code=429, detail="The YouTube request limit has been reached today. Please try again tomorrow.")
                
            init_data = init_resp.json()
            
            if not init_data.get("success"):
                error_msg = init_data.get("message", "YouTube Proxy failed to initialize.")
                # Fallback check in case the API passes the limit in the payload instead of the header
                if "quota" in error_msg.lower() or "limit" in error_msg.lower():
                    raise HTTPException(status_code=429, detail="The YouTube request limit has been reached today. Please try again tomorrow.")
                raise Exception(error_msg)
                
            progress_url = init_data.get("progress_url")
            vid_title = init_data.get("info", {}).get("title", "YouTube Video")
            vid_thumb = init_data.get("info", {}).get("image", "")
            
            target_url = None
            for _ in range(45): 
                time.sleep(2) 
                prog_resp = requests.get(progress_url)
                prog_data = prog_resp.json()
                
                if prog_data.get("text") == "Finished" and prog_data.get("download_url"):
                    target_url = prog_data.get("download_url")
                    break
                elif prog_data.get("text") == "Error":
                    raise Exception("Proxy encountered an error while processing the video.")
            
            if not target_url:
                raise Exception("YouTube proxy timed out.")

            filename = f"{file_id}.mp4"
            filepath = os.path.join(DOWNLOAD_DIR, filename)
            
            final_headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            vid_resp = requests.get(target_url, headers=final_headers, stream=True)
            vid_resp.raise_for_status()
            
            with open(filepath, 'wb') as f:
                for chunk in vid_resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            return {
                "success": True,
                "title": vid_title,
                "download_url": f"/api/download/{filename}",
                "thumbnail": vid_thumb
            }
            
        except HTTPException as http_exc:
            raise http_exc # Respects our custom 429 message without wrapping it
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"YouTube Tunnel Error: {str(e)}")

    # ==========================================
    # ROUTE 3: LOCAL ENGINE (X, TikTok, Facebook)
    # ==========================================
    else:
        out_template = os.path.join(DOWNLOAD_DIR, f'{file_id}.%(ext)s')
        
        ydl_opts = {
            'format': 'best',
            'outtmpl': out_template,
            'quiet': True,
            'noplaylist': True, 
            'max_filesize': 150 * 1024 * 1024, 
            'no_color': True,
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(request.url, download=True)
                
                search_pattern = os.path.join(DOWNLOAD_DIR, f'{file_id}.*')
                downloaded_files = glob.glob(search_pattern)
                
                if not downloaded_files:
                    raise Exception("Download failed on the server. File not found.")
                    
                actual_filepath = downloaded_files[0]
                filename_only = os.path.basename(actual_filepath)
                
                return {
                    "success": True,
                    "title": info.get('title', 'Video'),
                    "download_url": f"/api/download/{filename_only}",
                    "thumbnail": info.get('thumbnail')
                }
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/download/{filename}")
async def download_file(filename: str, background_tasks: BackgroundTasks):
    filepath = os.path.join(DOWNLOAD_DIR, filename)
    
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found or expired.")
        
    background_tasks.add_task(cleanup_file, filepath)
    
    return FileResponse(
        path=filepath, 
        filename=filename,
        media_type='application/octet-stream'
    )
