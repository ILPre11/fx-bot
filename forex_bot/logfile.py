"""Output su file rotante accanto alla console (tee di stdout/stderr).

Il bot usa print(): qui si duplica tutto l'output su un file di log, con
timestamp per riga e rotazione a dimensione, per il post-mortem di crash
e riavvii. La scrittura su file non deve MAI rompere il bot: ogni errore
di logging viene ignorato.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime


class _LogFile:
    """File di log condiviso tra stdout e stderr: timestamp a inizio riga,
    rotazione quando supera max_bytes (bot.log -> bot.log.1 -> .2 ...)."""

    def __init__(self, path: str, max_bytes: int, backups: int) -> None:
        self.path = path
        self.max_bytes = max_bytes
        self.backups = backups
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self._file = open(path, "a", encoding="utf-8")
        self._line_start = True

    def write(self, s: str) -> None:
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for chunk in s.splitlines(keepends=True):
            if self._line_start:
                self._file.write(f"{stamp} | ")
            self._file.write(chunk)
            self._line_start = chunk.endswith(("\n", "\r"))
        self._file.flush()
        if self._file.tell() > self.max_bytes:
            self._rotate()

    def flush(self) -> None:
        self._file.flush()

    def _rotate(self) -> None:
        self._file.close()
        for i in range(self.backups - 1, 0, -1):
            src, dst = f"{self.path}.{i}", f"{self.path}.{i + 1}"
            if os.path.exists(src):
                os.replace(src, dst)
        os.replace(self.path, f"{self.path}.1")
        self._file = open(self.path, "a", encoding="utf-8")


class _Tee:
    """Sostituto di sys.stdout/sys.stderr: scrive sia sulla console
    originale sia sul file di log condiviso."""

    def __init__(self, console, logfile: _LogFile) -> None:
        self.console = console
        self.logfile = logfile

    def write(self, s: str) -> int:
        try:
            self.console.write(s)
        except UnicodeEncodeError:
            enc = getattr(self.console, "encoding", None) or "ascii"
            self.console.write(s.encode(enc, "replace").decode(enc))
        try:
            self.logfile.write(s)
        except Exception:
            pass  # il log su file non deve mai fermare il bot
        return len(s)

    def flush(self) -> None:
        try:
            self.console.flush()
            self.logfile.flush()
        except Exception:
            pass

    def __getattr__(self, name):
        # inoltra tutto il resto (encoding, isatty, ...) alla console vera
        return getattr(self.console, name)


def enable_file_log(path: str, max_bytes: int = 5_000_000, backups: int = 3) -> None:
    """Attiva il tee: da qui in poi stdout e stderr finiscono anche nel file."""
    logfile = _LogFile(path, max_bytes, backups)
    sys.stdout = _Tee(sys.stdout, logfile)
    sys.stderr = _Tee(sys.stderr, logfile)
    print(f"[log] output duplicato su {path} (rotazione a {max_bytes // 1_000_000} MB)")
