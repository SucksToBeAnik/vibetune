"""Configuration: paths, defaults, and soundfont discovery."""

from __future__ import annotations
import os
import shutil
from pathlib import Path

# ---------- Paths ----------
HOME = Path.home()
DATA_DIR = Path(os.environ.get("AUTOTUNE_HOME", HOME / ".autotune"))
CACHE_DIR = DATA_DIR / "cache"          # working/auditioning files
LIBRARY_DIR = DATA_DIR / "library"      # saved music
PRESETS_FILE = DATA_DIR / "presets.json"

for d in (DATA_DIR, CACHE_DIR, LIBRARY_DIR):
    d.mkdir(parents=True, exist_ok=True)

# ---------- Ollama ----------
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("AUTOTUNE_MODEL", "qwen3.5:4b")

# ---------- Generation defaults ----------
DEFAULT_MIDI_DURATION = 30   # seconds
SAMPLE_RATE = 44100

# ---------- Soundfont discovery ----------
# Common locations across distros and Homebrew installs.
SOUNDFONT_CANDIDATES = [
    "/usr/share/sounds/sf2/FluidR3_GM.sf2",
    "/usr/share/sounds/sf2/default-GM.sf2",
    "/usr/share/soundfonts/FluidR3_GM.sf2",
    "/usr/share/soundfonts/default.sf2",
    "/opt/homebrew/share/fluid-soundfont/FluidR3_GM.sf2",
    "/usr/local/share/fluid-soundfont/FluidR3_GM.sf2",
    str(DATA_DIR / "soundfont.sf2"),  # user-provided fallback
]


def find_soundfont() -> str | None:
    """Return path to a usable .sf2 file, or None."""
    env = os.environ.get("AUTOTUNE_SOUNDFONT")
    if env and Path(env).is_file():
        return env
    for p in SOUNDFONT_CANDIDATES:
        if Path(p).is_file():
            return p
    return None


def has_fluidsynth() -> bool:
    return shutil.which("fluidsynth") is not None
