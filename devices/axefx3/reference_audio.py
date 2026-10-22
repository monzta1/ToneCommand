"""Bounded public audio fetch for local browser measurements, never AI hearing."""
import ipaddress
import http.client
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener
from urllib.error import HTTPError

MAX_BYTES = 40 * 1024 * 1024
HOSTED = {'youtube.com', 'www.youtube.com', 'm.youtube.com', 'youtu.be',
          'soundcloud.com', 'www.soundcloud.com'}
EXTENSIONS = {'.mp3', '.wav', '.flac', '.m4a', '.ogg', '.opus', '.aac', '.webm'}


def public_url(url):
    parsed = urlparse(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError('Use a public HTTPS audio/video link without credentials or a custom port.')
    addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError('Local/private network audio links are not allowed.')
    return parsed


def links(prompt):
    found = re.findall(r'https?://[^\s<>"\]]+', prompt)
    # Markdown closing brackets and sentence punctuation are not URL data.
    return list(dict.fromkeys(u.rstrip(').,;') for u in found))


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def pinned_opener(url):
    """Connect to a checked public address, preserving TLS SNI/certificate checks.

    A second DNS lookup inside urllib would permit DNS rebinding after validation.
    Do not use an implicit environment proxy that defeats this address check.
    """
    parsed = public_url(url)
    addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError('Audio host changed to a private address.')
    address = addresses[0][4][0]

    class Connection(http.client.HTTPSConnection):
        def connect(self):
            raw = socket.create_connection((address, 443), self.timeout)
            try:
                self.sock = self._context.wrap_socket(raw, server_hostname=parsed.hostname)
            except BaseException:
                raw.close()
                raise

    class Handler(HTTPSHandler):
        def https_open(self, req):
            return self.do_open(Connection, req, context=self._context)

    return build_opener(ProxyHandler({}), NoRedirect(), Handler())


def fetch_audio(url):
    parsed = public_url(url)
    if parsed.hostname in HOSTED:
        with tempfile.TemporaryDirectory(prefix='tc-reference-') as directory:
            command = [sys.executable, '-m', 'yt_dlp', '--ignore-config', '--no-playlist',
                       '--no-cache-dir', '--max-filesize', str(MAX_BYTES), '--socket-timeout', '15',
                       '-f', 'bestaudio/best', '-o', str(Path(directory) / 'reference.%(ext)s'), url]
            result = subprocess.run(command, capture_output=True, timeout=120, check=False)
            if result.returncode:
                raise ValueError('Audio download failed. Install the optional yt-dlp dependency, or upload a local audio file. No DRM bypass.')
            files = [p for p in Path(directory).iterdir() if p.suffix.lower() in EXTENSIONS]
            if len(files) != 1 or files[0].stat().st_size > MAX_BYTES:
                raise ValueError('No single audio file under 40 MiB was returned.')
            return files[0].read_bytes()
    if Path(parsed.path).suffix.lower() not in EXTENSIONS:
        raise ValueError('Use YouTube, SoundCloud or a direct HTTPS audio-file link.')
    # Check every redirect before fetching; never follow one into a private host.
    for _ in range(4):
        public_url(url)
        try:
            opener = pinned_opener(url)
            with opener.open(Request(url, headers={'User-Agent': 'ToneCommand reference audio'}), timeout=30) as response:
                data = response.read(MAX_BYTES + 1)
                if len(data) > MAX_BYTES:
                    raise ValueError('Audio exceeds 40 MiB. Upload a shorter clip.')
                return data
        except HTTPError as exc:
            if exc.code not in (301, 302, 303, 307, 308) or not exc.headers.get('Location'):
                raise ValueError('Audio download refused (HTTP %s).' % exc.code) from None
            from urllib.parse import urljoin
            url = urljoin(url, exc.headers['Location'])
    raise ValueError('Too many audio redirects.')
