"""Run the Factory and retained-core suite in a bounded isolated Linux container.

Only source/test allowlists are staged. No .env, credentials, private runtime,
media exports, model cache or Git credential store enters the test container.
"""
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory

ROOT=Path(__file__).resolve().parents[1]


def main():
    scratch=ROOT/'scratch';scratch.mkdir(exist_ok=True)
    with TemporaryDirectory(prefix='v7-linux-',dir=scratch) as temporary:
        stage=Path(temporary)
        if not stage.resolve().is_relative_to(scratch.resolve()):raise ValueError('Invalid staging boundary')
        for name in ('factory','factory_tests','tests','bin','fonts','cloud'):
            folder=ROOT/name
            if not folder.is_dir():continue
            for source in folder.rglob('*'):
                if not source.is_file() or source.is_symlink() or '__pycache__' in source.parts:continue
                target=stage/source.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(source,target)
                if name=='bin' and source.name=='ffmpeg':
                    target.write_bytes(target.read_bytes().replace(b'\r\n',b'\n'))
                    target.chmod(0o755)
        for source in [*ROOT.glob('*.py'),ROOT/'LICENSE',ROOT/'NOTICE',ROOT/'Dockerfile',ROOT/'requirements-factory.lock']:
            shutil.copyfile(source,stage/source.name)
        (stage/'deploy').mkdir(exist_ok=True)
        for name in ('download-wheels.py','gpu-wheels.json'):
            shutil.copyfile(ROOT/'deploy'/name,stage/'deploy'/name)
        command=['docker','run','--rm','--label','com.ai-content-factory.verification=v7-linux',
                 '--env','OLLAMA_URL=http://127.0.0.1:9',
                 '--memory','3g','--memory-swap','3g','--cpus','2',
                 '--mount',f'type=bind,source={stage.resolve()},target=/verify,readonly',
                 '--workdir','/verify','--entrypoint','python','youtube-temka-controller',
                 '-m','pytest','factory_tests','tests/test_jsonfile.py','tests/test_ffmpeg_utils.py',
                 'tests/test_subtitles.py','tests/test_ssrf_guard.py','tests/test_ssrf_connect_guard.py',
                 'tests/test_transcribe_backends.py','tests/test_file_locks.py','-q','-p','no:cacheprovider',
                 '--basetemp','/tmp/v7-tests','--tb=short']
        raise SystemExit(subprocess.call(command,cwd=ROOT))


if __name__=='__main__':main()
