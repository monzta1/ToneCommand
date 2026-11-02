"""One cooperating TC process owns physical III MIDI, across checkouts.

An OS lock, not a PID file. Never unlink it and permit a second lock inode.
External editors must still close normally; this does not force their ports.
"""
import os
from pathlib import Path
import stat
import tempfile

from fm9.device import FM9NotFound


def _lock_path():
    return Path(tempfile.gettempdir()) / 'tonecommand-axefx3-midi-owner.lock'


class Lease:
    def __init__(self, fd):
        self._fd = fd

    def close(self):
        if self._fd is not None:
            fd, self._fd = self._fd, None
            os.close(fd)


def acquire():
    """Refuse before port open; handoff requires the previous owner's close."""
    fd = os.open(_lock_path(), os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    owned = False
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise FM9NotFound('III MIDI ownership requires a regular lock file')
        if os.fstat(fd).st_size == 0:
            os.write(fd, b'0')
        os.lseek(fd, 0, os.SEEK_SET)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise FM9NotFound('III MIDI is owned by another TC connection. Close '
                'that owner normally before handing MIDI to this reader; no '
                'takeover or second port open was attempted.') from error
        owned = True
        return Lease(fd)
    finally:
        if not owned:
            os.close(fd)
