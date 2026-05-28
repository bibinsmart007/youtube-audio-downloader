import json
import os
import re
import tempfile
import urllib.request
import urllib.parse
from http.server import BaseHTTPRequestHandler
import yt_dlp

# Updated official Invidious public instances (May 2026)
INVIDIOUS_INSTANCES = [
    'https://inv.nadeko.net',
    'https://invidious.nerdvpn.de',
    'https://inv.thepixora.com',
    'https://yt.chocolatemoo53.com',
    'https://invidious.tiekoetter.com',
    'https://invidious.f5.si',
]

# Piped API instances
PIPED_INSTANCES = [
    'https://pipedapi.kavin.rocks',
    'https://piped-api.garudalinux.org',
    'https://api.piped.yt',
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


def _fetch_json(url, timeout=8, data=None, headers=None):
    h = {'User-Agent': 'Mozilla/5.0 (compatible; AudioBot/1.0)'}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=data, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        if resp.status != 200:
            return None
        return json.loads(resp.read())


def _extract_via_invidious(video_id):
    """Try Invidious API - no bot detection."""
    for instance in INVIDIOUS_INSTANCES:
        try:
            data = _fetch_json(
                f'{instance}/api/v1/videos/{video_id}?fields=adaptiveFormats,title'
            )
            if not data:
                continue
            title = data.get('title', 'audio')
            best = None
            for fmt in data.get('adaptiveFormats', []):
                if fmt.get('type', '').startswith('audio/'):
                    if best is None or fmt.get('bitrate', 0) > best.get('bitrate', 0):
                        best = fmt
            if best:
                raw_url = best.get('url', '')
                stream_url = f'{instance}{raw_url}' if raw_url.startswith('/') else raw_url
                ext = 'webm' if 'webm' in best.get('type', '') else 'm4a'
                return stream_url, ext, title
        except Exception:
            continue
    return None, None, None


def _extract_via_piped(video_id):
    """Try Piped API."""
    for instance in PIPED_INSTANCES:
        try:
            data = _fetch_json(f'{instance}/streams/{video_id}')
            if not data:
                continue
            title = data.get('title', 'audio')
            best = None
            best_bitrate = 0
            for stream in data.get('audioStreams', []):
                bitrate = stream.get('bitrate', 0)
                if bitrate > best_bitrate:
                    best = stream
                    best_bitrate = bitrate
            if best:
                stream_url = best.get('url', '')
                mime = best.get('mimeType', '')
                ext = 'webm' if 'webm' in mime else 'm4a'
                if stream_url:
                    return stream_url, ext, title
        except Exception:
            continue
    return None, None, None


def _extract_via_cobalt(video_id):
    """Try cobalt.tools API - a privacy-respecting no-auth downloader."""
    url = f'https://www.youtube.com/watch?v={video_id}'
    try:
        payload = json.dumps({
            'url': url,
            'audioFormat': 'best',
            'downloadMode': 'audio',
            'quality': '320',
        }).encode()
        data = _fetch_json(
            'https://api.cobalt.tools/',
            data=payload,
            headers={
                'Content-Type': 'application/json',
                'Accept': 'application/json',
            },
            timeout=15,
        )
        if data and data.get('url'):
            return data['url'], 'm4a', data.get('filename', 'audio').rstrip('.m4a')
    except Exception:
        pass
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
    """Try multiple yt-dlp client strategies."""
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
        pass

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

            # Step 1: Try Invidious (fast, no auth)
            if video_id:
                stream_url, ext, title = _extract_via_invidious(video_id)

            # Step 2: Try Piped API
            if not stream_url and video_id:
                stream_url, ext, title = _extract_via_piped(video_id)

            # Step 3: Try Cobalt API
            if not stream_url and video_id:
                stream_url, ext, title = _extract_via_cobalt(video_id)

            # Step 4: Fallback to yt-dlp
            if not stream_url:
                cookie_file = _write_cookie_file()
                try:
                    stream_url, ext, err = _extract_via_ytdlp(url, cookie_file)
                    if not stream_url:
                        self._json_error(
                            500,
                            err or 'Could not extract audio stream. Please add YouTube cookies via the instructions below.'
                        )
                        return
                finally:
                    if cookie_file and os.path.exists(cookie_file):
                        os.unlink(cookie_file)

            response_body = json.dumps({
                'stream_url': stream_url,
                'ext': ext,
                'title': title or 'audio',
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
