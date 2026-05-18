"""Audio playback wrapper around pygame.mixer."""

from __future__ import annotations
import time
from pathlib import Path
from typing import Optional

import pygame

from . import config


class Player:
    def __init__(self) -> None:
        # Init lazily because pygame can be slow & noisy on import.
        self._initialized = False
        self._current: Optional[Path] = None
        self._duration: float = 0.0
        self._start_time: float = 0.0
        self._paused_at: Optional[float] = None
        self._loops: int = 0

    def _ensure_init(self) -> None:
        if not self._initialized:
            pygame.mixer.init(frequency=config.SAMPLE_RATE)
            self._initialized = True

    def load(self, path: Path, duration: float) -> None:
        self._ensure_init()
        pygame.mixer.music.load(str(path))
        self._current = path
        self._duration = duration
        self._paused_at = None

    def play(self, loops: int = 0) -> None:
        if self._current is None:
            raise RuntimeError("No track loaded.")
        self._ensure_init()
        pygame.mixer.music.play(loops=loops)
        self._loops = loops
        self._start_time = time.time()
        self._paused_at = None

    def pause(self) -> None:
        if self.is_playing():
            pygame.mixer.music.pause()
            self._paused_at = time.time() - self._start_time

    def unpause(self) -> None:
        if self._paused_at is not None:
            pygame.mixer.music.unpause()
            self._start_time = time.time() - self._paused_at
            self._paused_at = None

    def stop(self) -> None:
        if self._initialized:
            pygame.mixer.music.stop()
        self._paused_at = None

    def is_playing(self) -> bool:
        if not self._initialized:
            return False
        return pygame.mixer.music.get_busy() and self._paused_at is None

    def is_paused(self) -> bool:
        return self._paused_at is not None

    def position(self) -> float:
        """Seconds elapsed in current track (best-effort)."""
        if self._paused_at is not None:
            return self._paused_at
        if self.is_playing():
            return min(time.time() - self._start_time, self._duration)
        return 0.0

    def shutdown(self) -> None:
        if self._initialized:
            try:
                pygame.mixer.music.stop()
                pygame.mixer.quit()
            except Exception:
                pass
            self._initialized = False
