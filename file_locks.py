"""Exclusive descriptor locks, released by the OS on close or process exit.

Unix keeps flock semantics. Windows reserves byte zero (including beyond EOF),
without altering file contents or the caller's position. Only the exclusive,
nonblocking and unlock operations used by the application are supported.
"""
import os

if os.name != 'nt':
    from fcntl import LOCK_EX, LOCK_NB, LOCK_UN, flock
else:
    import errno
    import msvcrt
    import time

    LOCK_EX, LOCK_NB, LOCK_UN = 2, 4, 8

    def flock(file, operation):
        fd = file if isinstance(file, int) else file.fileno()
        position = os.lseek(fd, 0, os.SEEK_CUR)
        try:
            os.lseek(fd, 0, os.SEEK_SET)
            if operation == LOCK_UN:
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                return
            if operation not in (LOCK_EX, LOCK_EX | LOCK_NB):
                raise ValueError('Unsupported lock operation')
            while True:
                try:
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                    return
                except OSError as error:
                    if operation & LOCK_NB or error.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                        raise
                    time.sleep(0.05)
        finally:
            os.lseek(fd, position, os.SEEK_SET)
