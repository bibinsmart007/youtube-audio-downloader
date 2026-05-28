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

            if not url:
                self._json_error(400, 'URL is required')
                return

            tmp_dir = tempfile.mkdtemp()
            output_template = os.path.join(tmp_dir, f'{filename}.%(ext)s')

            # Download best audio WITHOUT ffmpeg post-processing
            # This downloads the native audio stream (webm or m4a)
            ydl_opts = {
                'format': 'bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio',
                'outtmpl': output_template,
                'quiet': True,
                'noplaylist': True,
                'no_warnings': True,
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                ext = info.get('ext', 'm4a')

            output_file = os.path.join(tmp_dir, f'{filename}.{ext}')

            if not os.path.exists(output_file):
                # Try to find whatever file was downloaded
                files = os.listdir(tmp_dir)
                if not files:
                    self._json_error(500, 'No output file found after download')
                    return
                output_file = os.path.join(tmp_dir, files[0])
                ext = files[0].split('.')[-1]

            with open(output_file, 'rb') as f:
                audio_data = f.read()

            # Set correct content type
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
