"""Chargement / sauvegarde des paramètres utilisateur."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "correcteur-auto"
CONFIG_FILE = CONFIG_DIR / "config.json"
AUTOSTART_DIR = Path.home() / ".config" / "autostart"
AUTOSTART_FILE = AUTOSTART_DIR / "correcteur-auto.desktop"

DEFAULTS: dict = {
    "enabled": True,
    "language": "auto",  # auto | fr | en
    "fix_spelling": True,
    "fix_commas": False,
    "fix_periods": False,
    "fix_capitals": False,
    # False = garder les mêmes mots, corriger seulement les fautes
    "allow_reformulation": False,
    "ollama_model": "qwen2.5:1.5b",
    "ollama_url": "http://127.0.0.1:11434",
    "min_chars": 2,
    # Confort
    "hotkey_enabled": True,
    "show_toast": True,
    "autostart": False,
}


def ensure_config_dir() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def load() -> dict:
    ensure_config_dir()
    cfg = deepcopy(DEFAULTS)
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for key in DEFAULTS:
                    if key in data:
                        cfg[key] = data[key]
        except (OSError, json.JSONDecodeError):
            pass
    return cfg


def save(cfg: dict) -> None:
    ensure_config_dir()
    out = {key: cfg.get(key, DEFAULTS[key]) for key in DEFAULTS}
    CONFIG_FILE.write_text(
        json.dumps(out, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    sync_autostart(bool(out.get("autostart", False)))


def sync_autostart(enabled: bool, exec_path: str | None = None) -> None:
    """Active / désactive le lancement au démarrage de session."""
    if exec_path is None:
        # Chemin par défaut du projet
        exec_path = str(Path.home() / "Projects" / "correcteur-auto" / "run.sh")
    try:
        if enabled:
            AUTOSTART_DIR.mkdir(parents=True, exist_ok=True)
            AUTOSTART_FILE.write_text(
                "\n".join(
                    [
                        "[Desktop Entry]",
                        "Type=Application",
                        "Name=Correcteur Auto",
                        "Comment=Correction orthographe via icône systray",
                        f"Exec={exec_path}",
                        "Icon=accessories-character-map",
                        "Terminal=false",
                        "X-GNOME-Autostart-enabled=true",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
        elif AUTOSTART_FILE.exists():
            AUTOSTART_FILE.unlink()
    except OSError:
        pass
