import shutil
import os
import platform
import subprocess
from . import config


def usage():
    config.initialize()
    used = sum(p.stat().st_size for folder in (config.SCRATCH,config.DATA/'backgrounds',config.DATA/'music',config.DATA/'asset-cache') for p in folder.rglob('*') if p.is_file())
    free = shutil.disk_usage(config.SCRATCH).free
    return {'scratch_bytes':used, 'free_bytes':free, 'budget_bytes':config.SCRATCH_BYTES, 'reserve_bytes':config.RESERVE_BYTES}


def preflight(extra=0):
    state = usage()
    if state['scratch_bytes'] + extra > config.SCRATCH_BYTES:
        raise RuntimeError('Scratch budget exceeded. Upload/clean completed jobs or select a shorter interval.')
    if state['free_bytes'] - extra < config.RESERVE_BYTES:
        raise RuntimeError('Free-space reserve would be exceeded. Free disk space before retrying.')
    return state


def hardware():
    result={**usage(),'cpu_count':os.cpu_count(),'os':platform.system(),'gpu':None,'heavy_task_limit':1}
    try:
        response=subprocess.run(['nvidia-smi','--query-gpu=name,memory.total,memory.free','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=3,check=True)
        name,total,free=response.stdout.splitlines()[0].rsplit(',',2)
        result['gpu']={'name':name.strip(),'total_mib':int(total),'free_mib':int(free)}
    except (OSError,ValueError,subprocess.SubprocessError,IndexError):
        pass
    return result
