"""Garantit une seule instance de l'application."""

from __future__ import annotations

import atexit
import fcntl
import os
import sys
from pathlib import Path

from correcteur.config import CONFIG_DIR, ensure_config_dir

_LOCK_FILE = CONFIG_DIR / "instance.lock"
_lock_handle = None


def acquire_or_exit() -> None:
    """Quitte immédiatement si Correcteur Auto tourne déjà."""
    global _lock_handle
    ensure_config_dir()
    _lock_handle = open(_LOCK_FILE, "w", encoding="utf-8")
    try:
        fcntl.flock(_lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print(
            "Correcteur Auto est déjà lancé "
            "(une seule instance autorisée pour éviter la surcharge CPU).",
            file=sys.stderr,
        )
        sys.exit(0)

    _lock_handle.write(str(os.getpid()))
    _lock_handle.flush()
    atexit.register(_release)


def _release() -> None:
    global _lock_handle
    if _lock_handle is None:
        return
    try:
        fcntl.flock(_lock_handle.fileno(), fcntl.LOCK_UN)
        _lock_handle.close()
    except OSError:
        pass
    _lock_handle = None
    try:
        Path(_LOCK_FILE).unlink(missing_ok=True)
    except OSError:
        pass
