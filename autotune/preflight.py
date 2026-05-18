"""Startup dependency checks — fail fast with clear install instructions."""

from __future__ import annotations
import platform
import shutil
import sys


def _missing_deps() -> list[str]:
    missing = []
    if not shutil.which("fluidsynth"):
        missing.append("fluidsynth")
    return missing


def _install_instructions(deps: list[str]) -> str:
    joined = " ".join(deps)
    system = platform.system()
    if system == "Darwin":
        return f"  brew install {joined}"
    if system == "Linux":
        pkg_map = {"fluidsynth": "fluidsynth fluid-soundfont-gm"}
        pkgs = " ".join(pkg_map.get(d, d) for d in deps)
        return f"  sudo apt install {pkgs}"
    return f"  Install {joined} using your system package manager."


def check() -> None:
    missing = _missing_deps()
    if not missing:
        return

    joined = ", ".join(missing)
    print(f"✗ Missing system dependencies: {joined}\n")
    print("Install them first:")
    print(_install_instructions(missing))
    if platform.system() == "Darwin":
        print("\n  (Get Homebrew at https://brew.sh if you don't have it)")
    print("\nThen re-run autotune.")
    sys.exit(1)
