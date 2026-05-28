import json
import os
import tempfile
import urllib.request
from http.server import BaseHTTPRequestHandler
import yt_dlp

INVIDIOUS_INSTANCES = [
    'https://inv.nadeko.net',
    'https://invidious.nerdvpn.de',
    'https://invidious.privacydev.net',
]


def _write_cookie_file():
    """Write YOUTUBE_COOKIES env var (Netscape format) to a temp file."""
    cookie_data = os.environ.get('YOUTUBE_COOKIES', '').strip()
    if not cookie_data:
        return None
    tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.txt',
                                      delete=False, prefix='yt_cookies_')
    if not cookie_data.startswith('# Netscape'):
        tmp.write('# Netscape HTTP Cookie File\n')
    tmp.write(cookie_data)
    tmp.flush()
    tmp.close()
    return tmp.name


def _extract_via_invidious(video_id):
    """Try to get audio stream URL from Invidious API."""
    for instance in INVIDIOUS_INSTANCES:
        try:
            api_url = f'{instance}/api/v1/videos/{video_id}?fields=adaptiveFormats,title'
            req = urllib.request.Request(
                api_url,
                headers={'User-Agent': 'Mozilla/5.0'},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            title = data.get('title', 'audio')
            # Find best audio-only adaptive format
            best = None
            for fmt in data.get('adaptiveFormats', []):
                if fmt.get('type', '').startswith('audio/'):
                    if best is None or fmt.get('bitrate', 0) > best.get('bitrate', 0):
                        best = fmt
            if best:
                raw_url = best.get('url', '')
                # Invidious proxies the URL - construct direct YouTube URL
                stream_url = f'{instance}{raw_url}' if raw_url.startswith('/') else raw_url
                ext = 'webm' if 'webm' in best.get('type', '') else 'm4a'
                return stream_url, ext, title
        except Exception:
            continue
    return None, None, None


def _get_video_id(url):
    """Extract video ID from YouTube URL."""
    import re
    patterns = [
        r'(?:v=|/)([0-9A-Za-z_-]{11}).*',
        r'youtu\.be/([0-9A-Za-z_-]{11})',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


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

            # Try yt-dlp with multiple player clients
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
                        'socket_timeout': 12,
                    }
                    if cookie_file:
                        ydl_opts['cookiefile'] = cookie_file

                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(url, download=False)
                    break
                except Exception as e:
                    last_error = str(e)
                    info = None
                    continue

            if cookie_file and os.path.exists(cookie_file):
                os.unlink(cookie_file)

            stream_url = None
            ext = 'm4a'
            title = 'audio'

            if info is not None:
                formats = info.get('formats', [])
                for f in reversed(formats):
                    if f.get('vcodec') == 'none' and f.get('url'):
                        stream_url = f['url']
                        ext = f.get('ext', 'm4a')
                        break
                if not stream_url:
                    stream_url = info.get('url')
                    ext = info.get('ext', 'm4a')
                title = info.get('title', 'audio')

            # Fallback: try Invidious API
            if not stream_url:
                video_id = _get_video_id(url)
                if video_id:
                    stream_url, ext, title = _extract_via_invidious(video_id)

            if not stream_url:
                self._json_error(500, last_error or 'Could not extract stream URL')
                return

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
