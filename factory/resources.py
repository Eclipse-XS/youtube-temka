import shutil
import os
import platform
import subprocess
from . import config


def usage():
    config.initialize()
    used = sum(p.stat().st_size for folder in (config.SCRATCH,config.DATA/'asset-cache') for p in folder.rglob('*') if p.is_file())
    persistent=sum(p.stat().st_size for folder in (config.DATA/'backgrounds',config.DATA/'music',config.DATA/'logos') for p in folder.rglob('*') if p.is_file())
    free = shutil.disk_usage(config.SCRATCH).free
    return {'scratch_bytes':used,'persistent_asset_bytes':persistent, 'free_bytes':free, 'budget_bytes':config.SCRATCH_BYTES, 'reserve_bytes':config.RESERVE_BYTES}


def preflight(extra=0):
    state = usage()
    if state['scratch_bytes'] + extra > config.SCRATCH_BYTES:
        raise RuntimeError('Scratch budget exceeded. Upload/clean completed jobs or select a shorter interval.')
    if state['free_bytes'] - extra < config.RESERVE_BYTES:
        raise RuntimeError('Free-space reserve would be exceeded. Free disk space before retrying.')
    return state


def hardware():
    memory=memory_status()
    return {**usage(),'memory':memory,'memory_admission':'READY' if memory_ready(memory) else 'WAITING_MEMORY',
            'cpu_count':os.cpu_count(),'os':platform.system(),'gpu':gpu_status(),'heavy_task_limit':1}


def gpu_status():
    try:
        response=subprocess.run(['nvidia-smi','--query-gpu=name,memory.total,memory.free','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=3,check=True)
        name,total,free=response.stdout.splitlines()[0].rsplit(',',2)
        return {'name':name.strip(),'total_mib':int(total),'free_mib':int(free)}
    except (OSError,ValueError,subprocess.SubprocessError,IndexError):
        pass
    return None


class ResourcePeaks:
    def __init__(self):
        self.samples = 0
        self.peak = {}
        self.gpu = None

    def sample(self):
        memory = memory_status()
        gpu = gpu_status()
        values = {}
        if 'host_available_bytes' in memory:
            values['host_ram_used_bytes'] = memory['host_total_bytes'] - memory['host_available_bytes']
        if 'container_used_bytes' in memory:
            values['container_memory_used_bytes'] = memory['container_used_bytes']
        if gpu:
            if self.gpu is None:
                self.gpu = gpu
            values['device_vram_used_mib'] = gpu['total_mib'] - gpu['free_mib']
        for metric,value in values.items():
            self.peak[metric] = max(self.peak.get(metric,0),value)
        self.samples += 1

    def report(self):
        return {'samples':self.samples,'peak':dict(self.peak),'initial_gpu':self.gpu}


def memory_status():
    """Host availability and cgroup headroom are separate measurement scopes."""
    result={}
    if os.name=='nt':
        import ctypes
        class Status(ctypes.Structure):
            _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong),
                      *[(name,ctypes.c_ulonglong) for name in ('total','available','page_total','page_available','virtual_total','virtual_available','extended')]]
        status=Status();status.length=ctypes.sizeof(status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            result.update(host_total_bytes=status.total,host_available_bytes=status.available)
    else:
        from pathlib import Path
        try:
            entries={line.split(':')[0]:int(line.split()[1])*1024 for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith(('MemTotal:','MemAvailable:'))}
            result.update(host_total_bytes=entries['MemTotal'],host_available_bytes=entries['MemAvailable'])
        except (OSError,ValueError,KeyError):pass
        try:
            current=int(Path('/sys/fs/cgroup/memory.current').read_text())
            limit=int(Path('/sys/fs/cgroup/memory.max').read_text())
            result.update(container_used_bytes=current,container_limit_bytes=limit,container_available_bytes=max(0,limit-current))
        except (OSError,ValueError):pass
    return result


def memory_ready(values=None):
    values=memory_status() if values is None else values
    threshold=int(os.environ.get('FACTORY_MEMORY_RESERVE_MB','512'))*1024**2
    return all(values[key]>=threshold for key in ('host_available_bytes','container_available_bytes') if key in values)
