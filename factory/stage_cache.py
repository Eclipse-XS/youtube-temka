"""Bounded, atomic checkpoints shared by jobs on the same worker volume."""
import json
import os
import shutil
from pathlib import Path
from tempfile import NamedTemporaryFile

from jsonfile import write_json_atomic
from . import config, media
from .render_timeline import fingerprint


def file_identity(path):
    stat = path.stat()
    return [stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns]


def source_identity(source):
    path = media.local_source(source)
    if path is not None:
        return [source, *file_identity(path)]
    return None


def cache_path(stage, dependencies, suffix='.json'):
    return config.SCRATCH/'stage-cache'/f'{stage}-{fingerprint(dependencies)}{suffix}'


def read_json(path):
    if path is not None:
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            pass
    return None


def room(path, size):
    limit = min(1024**3,config.SCRATCH_BYTES//8)
    if size > limit//2 or shutil.disk_usage(config.SCRATCH).free - size < config.RESERVE_BYTES:
        return False
    path.parent.mkdir(parents=True,exist_ok=True)
    records = []
    for entry in path.parent.iterdir():
        if not entry.is_file() or entry.is_symlink() or entry.suffix == '.part':
            continue
        try:
            stat = entry.stat()
            records.append((stat.st_mtime,stat.st_size,entry))
        except FileNotFoundError:
            continue
    total = sum(record[1] for record in records)
    if total + size <= limit:
        return True
    for _,length,entry in sorted(records):
        try:
            entry.unlink(missing_ok=True)
            total -= length
        except OSError:
            continue
        if total + size <= limit:
            return True
    return False


def save_json(path, data):
    if path is not None:
        try:
            from .resources import preflight
            size = len(json.dumps(data,ensure_ascii=True))
            preflight(size)
            if room(path,size):
                write_json_atomic(path,data,ensure_ascii=True)
        except (OSError,RuntimeError):
            pass


def restore_file(path, target):
    if path is None or not path.is_file():
        return False
    temporary = None
    try:
        with path.open('rb') as source, NamedTemporaryFile(dir=target.parent,suffix='.part',delete=False) as output:
            temporary = Path(output.name)
            shutil.copyfileobj(source,output,1024**2)
        temporary.replace(target)
        return True
    except OSError:
        return False
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def save_file(path, source):
    if path is not None and not path.is_file():
        try:
            from .resources import preflight
            size = source.stat().st_size
            preflight(size)
            if room(path,size):
                restore_file(source,path)
        except (OSError,RuntimeError):
            pass
