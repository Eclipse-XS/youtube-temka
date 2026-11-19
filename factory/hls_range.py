"""Bounded Twitch HLS ranges, without seeking across the full remote playlist."""
import math
from pathlib import Path
import re
import tempfile
from urllib.parse import urljoin

from security_utils import assert_public_url
from . import media


def select_playlist(text, base, start, end):
    if not math.isfinite(start + end) or not 0 <= start < end:
        raise ValueError('Invalid HLS interval')
    lines = text.splitlines()
    if not lines or lines[0].strip() != '#EXTM3U' or '#EXT-X-ENDLIST' not in lines:
        raise ValueError('Twitch range requires a completed HLS media playlist')
    selected = []
    position = 0.0
    duration = None
    init = None
    previous_init = None
    discontinuity = False
    sequence = 0
    index = 0
    first_sequence = None
    first_position = None
    max_duration = 0
    for raw in lines[1:]:
        line = raw.strip()
        if line.startswith('#EXT-X-MEDIA-SEQUENCE:'):
            sequence = int(line.split(':', 1)[1])
        elif line.startswith('#EXTINF:'):
            duration = float(line.split(':', 1)[1].split(',')[0])
            if not math.isfinite(duration) or not 0 < duration <= 60:
                raise ValueError('Unsupported HLS segment duration')
        elif line.startswith('#EXT-X-MAP:'):
            match = re.fullmatch(r'#EXT-X-MAP:URI="([^"]+)"', line)
            if not match:
                raise ValueError('Unsupported HLS initialization segment')
            init = urljoin(base, match[1])
        elif line.startswith('#EXT-X-KEY:') and line != '#EXT-X-KEY:METHOD=NONE':
            raise ValueError('Encrypted Twitch ranges are not supported')
        elif line.startswith(('#EXT-X-BYTERANGE:', '#EXT-X-STREAM-INF:')):
            raise ValueError('Unsupported HLS range playlist')
        elif line == '#EXT-X-DISCONTINUITY':
            discontinuity = True
        elif line and not line.startswith('#'):
            if duration is None:
                raise ValueError('Missing HLS segment duration')
            finish = position + duration
            if position < end and finish > start:
                if first_position is None:
                    first_position, first_sequence = position, sequence + index
                if discontinuity and selected:
                    selected.append('#EXT-X-DISCONTINUITY')
                if init and init != previous_init:
                    assert_public_url(init)
                    selected.append(f'#EXT-X-MAP:URI="{init}"')
                    previous_init = init
                url = urljoin(base, line)
                assert_public_url(url)
                selected.extend([f'#EXTINF:{duration:.6f},', url])
                max_duration = max(max_duration, duration)
            position = finish
            index += 1
            duration = None
            discontinuity = False
    if first_position is None or position < end - .25:
        raise ValueError('Requested interval is outside the available Twitch playlist')
    header = ['#EXTM3U', '#EXT-X-VERSION:6',
              f'#EXT-X-TARGETDURATION:{math.ceil(max_duration)}',
              '#EXT-X-PLAYLIST-TYPE:VOD', f'#EXT-X-MEDIA-SEQUENCE:{first_sequence}']
    return '\n'.join([*header, *selected, '#EXT-X-ENDLIST', '']), start - first_position


def download(ydl, info, destination, start, end, binary):
    """Give FFmpeg only intersecting segments plus at most one boundary segment."""
    from yt_dlp.networking import Request
    url = info['url']
    assert_public_url(url)
    headers = info.get('http_headers') or {}
    with ydl.urlopen(Request(url, headers=headers)) as response:
        payload = response.read(4 * 1024 * 1024 + 1)
        if len(payload) > 4 * 1024 * 1024:
            raise ValueError('Twitch HLS playlist exceeds the bounded manifest budget')
        playlist, offset = select_playlist(payload.decode('utf-8-sig'), response.url, start, end)
    target = Path(destination)
    # This directory contains only our manifest/output, never an existing export.
    with tempfile.TemporaryDirectory(prefix='hls-range-', dir=target.parent) as folder:
        manifest = Path(folder) / 'range.m3u8'
        manifest.write_text(playlist, encoding='utf-8')
        temporary = Path(folder) / target.name
        args = [binary, '-hide_banner', '-loglevel', 'error', '-y',
                '-threads', '2', '-rw_timeout', '20000000',
                '-protocol_whitelist', 'file,http,https,tcp,tls',
                '-i', str(manifest), '-ss', str(offset), '-t', str(end - start),
                '-threads', '2', '-filter_threads', '1']
        audio = target.suffix.lower() == '.mka'
        if audio:
            args += ['-vn', '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', '-f', 'matroska']
        else:
            args += ['-c:v', 'libx264', '-preset', 'fast', '-c:a', 'aac', '-movflags', '+faststart', '-f', 'mp4']
        media.run([*args, str(temporary)], duration=end - start)
        validate_download(temporary, end - start, audio=audio)
        temporary.replace(target)


def validate_download(path, expected, audio=False):
    import av
    try:
        with av.open(str(path)) as container:
            streams = container.streams.audio if audio else container.streams.video
            if not streams or not container.duration or container.duration / av.time_base < expected - 1:
                raise ValueError('Downloaded range is empty or shorter than requested; retry the source interval')
            if next(container.decode(streams[0]), None) is None:
                raise ValueError('Downloaded range contains no decodable media')
    except av.error.FFmpegError:
        raise ValueError('Downloaded range is not decodable; retry the source interval') from None
