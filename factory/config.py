import os
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

DATA = Path(os.environ.get('FACTORY_DATA', 'factory-data')).resolve()
SCRATCH = Path(os.environ.get('FACTORY_SCRATCH',str(DATA/'scratch'))).resolve()
DB = DATA / 'jobs.sqlite3'
GIB = 1024 ** 3
SCRATCH_BYTES = int(float(os.environ.get('SCRATCH_GB', '8')) * GIB)
RESERVE_BYTES = int(float(os.environ.get('FREE_RESERVE_GB', '4')) * GIB)
TOKEN = os.environ.get('FACTORY_TOKEN', '')
OLLAMA = os.environ.get('OLLAMA_URL', 'http://host.docker.internal:11434').rstrip('/')
MODEL = os.environ.get('OLLAMA_MODEL', 'qwen2.5:3b')
ASR_MODEL = os.environ.get('WHISPER_MODEL','small')
try:
    preferences=json.loads((DATA/'settings.json').read_text(encoding='utf-8'))
    MODEL=preferences.get('ollama_model',MODEL)
    ASR_MODEL=preferences.get('whisper_model',ASR_MODEL)
except (OSError,ValueError):
    pass


def initialize():
    SCRATCH.mkdir(parents=True, exist_ok=True)
