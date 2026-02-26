from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import yt_dlp
import os
import uuid
import glob

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

# Create an absolute path to a dedicated downloads folder
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

def cleanup_file(filepath: str):
    if os.path.exists(filepath):
        os.remove(filepath)

@app.post("/api/extract")
async def extract_video_link(request: VideoRequest, req: Request):
    file_id = str(uuid.uuid4())
    
    # Force yt-dlp to use the exact, absolute path
    out_template = os.path.join(DOWNLOAD_DIR, f'{file_id}.%(ext)s')
    
    ydl_opts = {
        'format': 'best',
        'outtmpl': out_template,
        'quiet': True,
        'noplaylist': True, # Ensures it only grabs a single video
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(request.url, download=True)
            
            # Find the file using the absolute path
            search_pattern = os.path.join(DOWNLOAD_DIR, f'{file_id}.*')
            downloaded_files = glob.glob(search_pattern)
            
            if not downloaded_files:
                raise Exception("Download failed on the server. File not found.")
                
            actual_filepath = downloaded_files[0]
            
            # Strip out the path so we only send the clean filename to the browser
            filename_only = os.path.basename(actual_filepath)
            host_url = req.headers.get("host")
            
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
    # Reconstruct the absolute path to locate the file securely
    filepath = os.path.join(DOWNLOAD_DIR, filename)
    
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found or expired.")
        
    background_tasks.add_task(cleanup_file, filepath)
    
    return FileResponse(
        path=filepath, 
        filename=filename,
        media_type='application/octet-stream'
    )
