from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import threading
import subprocess
from urllib.request import urlopen

import pytest
from factory import hls_range, media, config


def playlist(count=5):
    return '\n'.join(['#EXTM3U', '#EXT-X-MEDIA-SEQUENCE:7',
        '#EXT-X-MAP:URI="init.mp4"',
        *[f'#EXTINF:10.000,\n{i}.mp4' for i in range(count)], '#EXT-X-ENDLIST'])


def test_select_only_intersecting_fragments_and_boundary_offset(monkeypatch):
    seen = []
    monkeypatch.setattr(hls_range, 'assert_public_url', seen.append)
    text, offset = hls_range.select_playlist(playlist(), 'https://cdn.example/audio/index.m3u8', 23, 40)
    assert offset == 3
    assert 'https://cdn.example/audio/2.mp4' in text
    assert 'https://cdn.example/audio/3.mp4' in text
    assert '/1.mp4' not in text and '/4.mp4' not in text
    assert '#EXT-X-MEDIA-SEQUENCE:9' in text
    assert len(seen) == 3  # init plus two selected fragments


@pytest.mark.parametrize('text', [
    playlist().replace('#EXT-X-ENDLIST', ''),
    playlist().replace('#EXT-X-MAP:', '#EXT-X-KEY:METHOD=AES-128,'),
    playlist().replace('#EXTINF:10.000,', '#EXTINF:nan,'),
    playlist().replace('#EXTINF:10.000,', '#EXT-X-BYTERANGE:100@0\n#EXTINF:10.000,'),
])
def test_reject_live_encrypted_or_unsupported_manifests(text, monkeypatch):
    monkeypatch.setattr(hls_range, 'assert_public_url', lambda _: None)
    with pytest.raises(ValueError):
        hls_range.select_playlist(text, 'https://cdn.example/index.m3u8', 0, 10)


def test_reject_private_fragment_urls():
    text = '#EXTM3U\n#EXTINF:10,\nhttp://127.0.0.1/secret.ts\n#EXT-X-ENDLIST'
    with pytest.raises(ValueError):
        hls_range.select_playlist(text, 'https://cdn.example/index.m3u8', 0, 10)


def test_reject_empty_artifact_before_asr(tmp_path):
    path = tmp_path / 'empty.mka'
    path.write_bytes(b'')
    with pytest.raises(ValueError, match='not decodable'):
        hls_range.validate_download(path, 10, audio=True)


@pytest.mark.parametrize('audio', [True, False])
def test_real_fmp4_with_large_timestamps_fetches_only_selected_range(tmp_path, monkeypatch, audio):
    import av
    monkeypatch.setattr(config, 'SCRATCH', tmp_path)
    monkeypatch.setattr(config, 'DATA', tmp_path)
    monkeypatch.setattr(config, 'RESERVE_BYTES', 0)
    monkeypatch.setattr(hls_range, 'assert_public_url', lambda _: None)
    generated = subprocess.run([media.ffmpeg(), '-hide_banner', '-loglevel', 'error', '-y',
        '-f', 'lavfi', '-i', 'testsrc2=size=160x90:rate=2',
        '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=16000',
        '-t', '12', '-c:v', 'libx264', '-threads', '2', '-g', '4', '-bf', '0', '-sc_threshold', '0',
        '-c:a', 'aac', '-output_ts_offset', '10800', '-f', 'hls',
        '-hls_time', '2', '-hls_segment_type', 'fmp4', '-hls_list_size', '0',
        'index.m3u8'], cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert generated.returncode == 0, generated.stderr[-2000:]
    requests = []
    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_GET(self):
            requests.append(self.path)
            super().do_GET()
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Handler, directory=str(tmp_path)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    class YDL:
        def urlopen(self, request):
            return urlopen(request.url, timeout=10)
    base = f'http://127.0.0.1:{server.server_port}/index.m3u8'
    target = tmp_path / ('selected.mka' if audio else 'selected.mp4')
    try:
        hls_range.download(YDL(), {'url': base}, target, 6.25, 9.5, media.ffmpeg())
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2)
    with av.open(str(target)) as result:
        assert abs(result.duration / av.time_base - 3.25) < .3
        assert result.streams.audio
        assert bool(result.streams.video) != audio
    assert '/index0.m4s' not in requests and '/index1.m4s' not in requests
    assert '/index2.m4s' not in requests and '/index5.m4s' not in requests
    assert '/index3.m4s' in requests and '/index4.m4s' in requests
