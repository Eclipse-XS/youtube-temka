"""Isolated ranged yt-dlp operation (no whole-source fallback)."""
import sys
import shutil
from pathlib import Path
import yt_dlp
from yt_dlp.utils import download_range_func
import ssrf_guard
from .media import validate_url


def main():
    source, destination, start, end, fmt, binary = sys.argv[1:]
    binary=shutil.which(binary) or binary
    validate_url(source)
    opts={'quiet':True,'noplaylist':True,'socket_timeout':20,'retries':2,
          'format':fmt,'ffmpeg_location':binary,'outtmpl':destination,
          'download_ranges':download_range_func(None,[(float(start),float(end))]),
          'force_keyframes_at_cuts':True,'overwrites':True}
    with ssrf_guard.guarded(), yt_dlp.YoutubeDL(opts) as ydl:
        info=ydl.extract_info(source,download=False)
        ssrf_guard.assert_public_urls(info)
        ydl.process_ie_result(info,download=True)
    if not Path(destination).is_file():
        raise RuntimeError('Ranged downloader did not produce the expected artifact')


if __name__=='__main__':
    main()
