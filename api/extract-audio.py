import json
import os
import re
import tempfile
import urllib.request
from http.server import BaseHTTPRequestHandler
import yt_dlp

# Invidious public instances as first-try fallback (no bot detection)
INVIDIOUS_INSTANCES = [
    'https://inv.nadeko.net',
    'https://invidious.nerdvpn.de',
    'https://invidious.privacydev.net',
    'https://vid.puffyan.us',
    'https://yt.cdaut.de',
]

# yt-dlp client strategies in priority order
CLIENT_STRATEGIES = [
    ['tv_embedded'],
    ['android_vr'],
    ['ios'],
    ['android'],
    ['web'],
]


def _get_video_id(url):
    patterns = [
        r'(?:v=|/)([0-9A-Za-z_-]{11})(?:[&?#]|$)',
        r'youtu\.be/([0-9A-Za-z_-]{11})',
        r'shorts/([0-9A-Za-z_-]{11})',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def _extract_via_invidious(video_id):
    """Try Invidious API - fastest, no bot detection."""
    for instance in INVIDIOUS_INSTANCES:
        try:
            api_url = f'{instance}/api/v1/videos/{video_id}?fields=adaptiveFormats,title'
            req = urllib.request.Request(
                api_url,
                headers={'User-Agent': 'Mozilla/5.0 (compatible; AudioBot/1.0)'}
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                if resp.status != 200:
                    continue
                data = json.loads(resp.read())
            title = data.get('title', 'audio')
            best = None
            for fmt in data.get('adaptiveFormats', []):
                mime = fmt.get('type', '')
                if mime.startswith('audio/'):
                    if best is None or fmt.get('bitrate', 0) > best.get('bitrate', 0):
                        best = fmt
            if best:
                raw_url = best.get('url', '')
                # Invidious proxies audio via its own domain
                stream_url = f'{instance}{raw_url}' if raw_url.startswith('/') else raw_url
                ext = 'webm' if 'webm' in best.get('type', '') else 'm4a'
                return stream_url, ext, title
        except Exception:
            continue
    return None, None, None


def _write_cookie_file():
    """Write YOUTUBE_COOKIES env var to a temp Netscape cookie file."""
    cookie_data = os.environ.get('YOUTUBE_COOKIES', '').strip()
    if not cookie_data:
        return None
    tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, prefix='yt_')
    if not cookie_data.startswith('# Netscape'):
        tmp.write('# Netscape HTTP Cookie File\n')
    tmp.write(cookie_data + '\n')
    tmp.flush()
    tmp.close()
    return tmp.name


def _extract_via_ytdlp(url, cookie_file=None):
    """Try multiple yt-dlp client strategies to get a direct audio stream URL."""
    last_error = None
    for clients in CLIENT_STRATEGIES:
        try:
            ydl_opts = {
                'format': 'bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best',
                'quiet': True,
                'no_warnings': True,
                'noplaylist': True,
                'skip_download': True,
                'extractor_args': {
                    'youtube': {
                        'player_client': clients,
                        'skip': ['webpage', 'config'],
                    }
                },
                'socket_timeout': 12,
                'http_headers': {
                    'User-Agent': (
                        'Mozilla/5.0 (Linux; Android 11; SM-G991B) '
                        'AppleWebKit/537.36 (KHTML, like Gecko) '
                        'Chrome/120.0.0.0 Mobile Safari/537.36'
                    )
                },
            }
            if cookie_file:
                ydl_opts['cookiefile'] = cookie_file

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)

            # Find best audio-only format
            stream_url = None
            ext = 'm4a'
            for f in reversed(info.get('formats', [])):
                if f.get('vcodec') in ('none', None) and f.get('url'):
                    stream_url = f['url']
                    ext = f.get('ext', 'm4a')
                    break
            if not stream_url:
                stream_url = info.get('url')
                ext = info.get('ext', 'm4a')

            title = info.get('title', 'audio')
            if stream_url:
                return stream_url, ext, title
        except Exception as e:
            last_error = str(e)
            continue
    return None, None, last_error


class handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Suppress access logs

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

            video_id = _get_video_id(url)
            stream_url = None
            ext = 'm4a'
            title = 'audio'

            # Step 1: Try Invidious (fast, no auth needed)
            if video_id:
                stream_url, ext, title = _extract_via_invidious(video_id)

            # Step 2: Fallback to yt-dlp with multiple client strategies
            if not stream_url:
                cookie_file = _write_cookie_file()
                try:
                    stream_url, ext, err = _extract_via_ytdlp(url, cookie_file)
                    title = title or 'audio'
                    if not stream_url:
                        self._json_error(500, err or 'Could not extract audio stream. Please add YouTube cookies.')
                        return
                finally:
                    if cookie_file and os.path.exists(cookie_file):
                        os.unlink(cookie_file)

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

        except json.JSONDecodeError:
            self._json_error(400, 'Invalid JSON body')
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
