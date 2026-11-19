"""One reentrant heavy-work slot across threads and cooperating host processes."""
import os
import threading
from pathlib import Path
from . import config
from file_locks import flock, LOCK_EX, LOCK_NB, LOCK_UN


class HostSlot:
    def __init__(self):
        self.local = threading.RLock()
        self.depth = 0
        self.file = None

    def acquire(self, blocking=True):
        if not self.local.acquire(blocking):return False
        if self.depth:
            self.depth += 1
            return True
        try:
            folder=Path(os.environ.get('FACTORY_HOST_LOCK_DIR',str(config.DATA/'locks')))
            folder.mkdir(parents=True,exist_ok=True)
            handle=(folder/'heavy.lock').open('a+b')
            try:flock(handle,LOCK_EX | (0 if blocking else LOCK_NB))
            except OSError:
                handle.close()
                self.local.release()
                return False
            self.file=handle
            self.depth=1
            return True
        except BaseException:
            self.local.release()
            raise

    def release(self):
        if not self.local._is_owned():raise RuntimeError('Heavy slot is not owned by this thread')
        self.depth -= 1
        try:
            if not self.depth:
                try:flock(self.file,LOCK_UN)
                finally:self.file.close();self.file=None
        finally:self.local.release()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self,*_):self.release()


HEAVY_LOCK=HostSlot()
