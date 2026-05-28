import json
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
            if not url:
                self._json_error(400, 'URL is required')
                return

            ydl_opts = {
                'format': 'bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio',
                'quiet': True,
                'noplaylist': True,
                'no_warnings': True,
                # Use the Android VR client to bypass bot-detection without cookies
                'extractor_args': {
                    'youtube': {
                        'player_client': ['android_vr'],
                    }
                },
                'http_headers': {
                    'User-Agent': 'com.google.android.apps.youtube.vr.oculus/1.56.379 (Linux; Android 12; Build/SQ3A.220705.003.A1)',
                    'Accept-Language': 'en-US,en;q=0.9',
                },
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)

                formats = info.get('formats', [])
                stream_url = None
                ext = 'm4a'

                # Find best audio-only format
                for f in reversed(formats):
                    if f.get('vcodec') == 'none' and f.get('url'):
                        stream_url = f['url']
                        ext = f.get('ext', 'm4a')
                        break

                if not stream_url:
                    stream_url = info.get('url')
                    ext = info.get('ext', 'm4a')

                if not stream_url:
                    self._json_error(500, 'Could not extract stream URL')
                    return

                title = info.get('title', 'audio')
                response_body = json.dumps({
                    'stream_url': stream_url,
                    'ext': ext,
                    'title': title,
                }).encode()

                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(response_body)))
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(response_body)

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
