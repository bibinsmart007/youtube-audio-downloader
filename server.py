import os
import tempfile
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
import yt_dlp

app = FastAPI(title="YouTube Audio Downloader API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class DownloadRequest(BaseModel):
    url: str
    filename: str = "audio"
    format: str = "mp3"
    bitrate: int = 192

@app.post("/api/extract-audio")
async def extract_audio(req: DownloadRequest):
    if not req.url:
        raise HTTPException(status_code=400, detail="URL is required")

    tmp_dir = tempfile.mkdtemp()
    output_template = os.path.join(tmp_dir, f"{req.filename}.%(ext)s")

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": output_template,
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": req.format,
            "preferredquality": str(req.bitrate),
        }],
        "quiet": True,
        "noplaylist": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([req.url])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Download failed: {str(e)}")

    output_file = os.path.join(tmp_dir, f"{req.filename}.{req.format}")
    if not os.path.exists(output_file):
        raise HTTPException(status_code=500, detail="Output file not found after processing")

    return FileResponse(
        path=output_file,
        media_type="audio/mpeg",
        filename=f"{req.filename}.{req.format}"
    )

@app.get("/")
def root():
    return {"status": "YouTube Audio Downloader API is running"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
