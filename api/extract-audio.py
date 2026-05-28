import json
import os
import tempfile
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
            fmt = data.get('format', 'mp3').strip()
            bitrate = str(data.get('bitrate', 192))

            if not url:
                self._json_error(400, 'URL is required')
                return

            tmp_dir = tempfile.mkdtemp()
            output_template = os.path.join(tmp_dir, f'{filename}.%(ext)s')

            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': output_template,
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': fmt,
                    'preferredquality': bitrate,
                }],
                'quiet': True,
                'noplaylist': True,
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            output_file = os.path.join(tmp_dir, f'{filename}.{fmt}')
            if not os.path.exists(output_file):
                self._json_error(500, 'Output file not found after processing')
                return

            with open(output_file, 'rb') as f:
                audio_data = f.read()

            self.send_response(200)
            self.send_header('Content-Type', 'audio/mpeg')
            self.send_header('Content-Disposition', f'attachment; filename="{filename}.{fmt}"')
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
