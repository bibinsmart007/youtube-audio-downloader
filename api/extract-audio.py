import json
import os
import tempfile
from http.server import BaseHTTPRequestHandler
import yt_dlp


def _write_cookie_file():
    """Write YOUTUBE_COOKIES env var (Netscape format) to a temp file."""
    cookie_data = os.environ.get('YOUTUBE_COOKIES', '').strip()
    if not cookie_data:
        return None
    tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.txt',
                                      delete=False, prefix='yt_cookies_')
    # Ensure the Netscape header is present
    if not cookie_data.startswith('# Netscape'):
        tmp.write('# Netscape HTTP Cookie File\n')
    tmp.write(cookie_data)
    tmp.flush()
    tmp.close()
    return tmp.name


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

            cookie_file = _write_cookie_file()

            # Try multiple player clients in order to bypass bot detection
            clients_to_try = [
                ['tv_embedded'],
                ['android_vr'],
                ['android'],
                ['ios'],
                ['web'],
            ]

            info = None
            last_error = None

            for clients in clients_to_try:
                try:
                    ydl_opts = {
                        'format': 'bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio',
                        'quiet': True,
                        'noplaylist': True,
                        'no_warnings': True,
                        'extractor_args': {
                            'youtube': {
                                'player_client': clients,
                            }
                        },
                        'socket_timeout': 15,
                    }
                    if cookie_file:
                        ydl_opts['cookiefile'] = cookie_file

                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(url, download=False)
                    break  # success
                except Exception as e:
                    last_error = str(e)
                    info = None
                    continue

            # Clean up temp cookie file
            if cookie_file and os.path.exists(cookie_file):
                os.unlink(cookie_file)

            if info is None:
                self._json_error(500, last_error or 'Failed to extract info')
                return

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
