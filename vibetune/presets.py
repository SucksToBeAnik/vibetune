"""Preset storage — save and load named vibe descriptions."""

from __future__ import annotations
import json
from datetime import datetime

from . import config


def load_all() -> dict[str, dict]:
    if not config.PRESETS_FILE.exists():
        return {}
    try:
        return json.loads(config.PRESETS_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def save_all(presets: dict[str, dict]) -> None:
    config.PRESETS_FILE.write_text(json.dumps(presets, indent=2))


def save(name: str, vibe: str, extras: dict | None = None) -> None:
    presets = load_all()
    presets[name] = {
        "vibe": vibe,
        "created": datetime.now().isoformat(timespec="seconds"),
        **(extras or {}),
    }
    save_all(presets)


def get(name: str) -> dict | None:
    return load_all().get(name)


def delete(name: str) -> bool:
    presets = load_all()
    if name in presets:
        del presets[name]
        save_all(presets)
        return True
    return False


def names() -> list[str]:
    return sorted(load_all().keys())
