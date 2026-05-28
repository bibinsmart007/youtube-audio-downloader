import json
import urllib.request
from http.server import BaseHTTPRequestHandler
import yt_dlp


class handler(BaseHTTPRequestHandler):

    def do_OPTIONS(self):
        self.send_response(200)
        self._send_cors_headers()
        self.end_headers()

    def do_POST(self):
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            data = json.loads(body)

            url = data.get('url', '').strip()
            filename = data.get('filename', 'audio').strip() or 'audio'

            if not url:
                self._json_error(400, 'URL is required')
                return

            # Extract info only - get the direct stream URL without downloading
            ydl_opts = {
                'format': 'bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio',
                'quiet': True,
                'noplaylist': True,
                'no_warnings': True,
                'skip_download': True,  # Don't download, just get URL
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)

            # Get the direct stream URL
            stream_url = info.get('url')
            ext = info.get('ext', 'm4a')

            if not stream_url:
                self._json_error(500, 'Could not extract stream URL')
                return

            # Stream the audio directly from YouTube CDN to the client
            req = urllib.request.Request(
                stream_url,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
            )
            with urllib.request.urlopen(req, timeout=30) as audio_response:
                audio_data = audio_response.read()

            content_types = {
                'm4a': 'audio/mp4',
                'webm': 'audio/webm',
                'mp3': 'audio/mpeg',
                'ogg': 'audio/ogg',
            }
            content_type = content_types.get(ext, 'audio/octet-stream')

            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Disposition', f'attachment; filename="{filename}.{ext}"')
            self.send_header('Content-Length', str(len(audio_data)))
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(audio_data)

        except Exception as e:
            self._json_error(500, str(e))

    def _json_error(self, code, message):
        body = json.dumps({'detail': message}).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _send_cors_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
