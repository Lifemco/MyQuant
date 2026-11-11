"""跨线程/进程的写事务与原子文件替换（Linux/macOS）。"""
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import tempfile
from threading import RLock

_writeLock = RLock()


@contextmanager
def fileLock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with _writeLock, path.with_suffix(path.suffix + ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


@contextmanager
def atomicFile(path: Path):
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    os.close(fd)
    temporary = Path(name)
    try:
        yield temporary
        with temporary.open("rb") as stream:
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
