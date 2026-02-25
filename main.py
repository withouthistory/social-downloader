from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import yt_dlp

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

@app.post("/api/extract")
async def extract_video_link(request: VideoRequest):
    ydl_opts = {
        'format': 'best',
        'quiet': True,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(request.url, download=False)
            
            return {
                "success": True,
                "title": info.get('title', 'Video'),
                "download_url": info.get('url'),
                "thumbnail": info.get('thumbnail')
            }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
