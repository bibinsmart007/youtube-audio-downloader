# YouTube Audio Downloader

A full-stack app to download audio from YouTube videos. Features a dark-mode HTML frontend and a FastAPI Python backend using `yt-dlp` and `ffmpeg`.

## Features

- Paste any YouTube URL and download audio in MP3, M4A, WAV, or OGG
- Choose bitrate: 128, 192, 256, or 320 kbps
- Custom output filename
- Clean dark-mode UI
- FastAPI backend with CORS support

## Project Structure

```
youtube-audio-downloader/
├── index.html        # Frontend app (open in browser)
├── server.py         # FastAPI backend
├── requirements.txt  # Python dependencies
└── README.md
```

## Prerequisites

- Python 3.9+
- `ffmpeg` installed on your system
  - Windows: `choco install ffmpeg` or download from https://ffmpeg.org
  - Mac: `brew install ffmpeg`
  - Linux: `sudo apt install ffmpeg`

## Setup & Run

### 1. Clone the repo

```bash
git clone https://github.com/bibinsmart007/youtube-audio-downloader.git
cd youtube-audio-downloader
```

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 3. Start the backend server

```bash
python server.py
```

The API will be available at `http://localhost:8000`

### 4. Open the frontend

Open `index.html` in your browser. Paste a YouTube URL, choose your format and bitrate, and click **Download Audio**.

## API Endpoint

`POST /api/extract-audio`

```json
{
  "url": "https://www.youtube.com/watch?v=...",
  "filename": "my-audio",
  "format": "mp3",
  "bitrate": 192
}
```

Returns the audio file as a binary download.

## Tech Stack

- **Frontend**: Vanilla HTML/CSS/JS
- **Backend**: Python, FastAPI, yt-dlp, ffmpeg
- **Audio processing**: FFmpegExtractAudio via yt-dlp post-processor

## License

MIT
