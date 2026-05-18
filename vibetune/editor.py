"""Audio editing: trim, fade, seamless loop export.

Uses soundfile + numpy for raw operations (fast, no ffmpeg dependency for these).
"""

from __future__ import annotations
from pathlib import Path

import numpy as np
import soundfile as sf


def get_duration(path: Path) -> float:
    info = sf.info(str(path))
    return info.frames / info.samplerate


def trim(input_path: Path, output_path: Path,
         start: float, end: float,
         fade_in: float = 0.0, fade_out: float = 0.0) -> Path:
    """Trim WAV to [start, end] with optional fade in/out (seconds)."""
    data, sr = sf.read(str(input_path))
    total = data.shape[0] / sr
    start = max(0.0, min(start, total))
    end = max(start + 0.1, min(end, total))

    start_frame = int(start * sr)
    end_frame = int(end * sr)
    clip = data[start_frame:end_frame]

    if fade_in > 0:
        n = min(int(fade_in * sr), len(clip))
        if n > 0:
            env = np.linspace(0.0, 1.0, n)
            if clip.ndim == 1:
                clip[:n] = clip[:n] * env
            else:
                clip[:n] = clip[:n] * env[:, None]
    if fade_out > 0:
        n = min(int(fade_out * sr), len(clip))
        if n > 0:
            env = np.linspace(1.0, 0.0, n)
            if clip.ndim == 1:
                clip[-n:] = clip[-n:] * env
            else:
                clip[-n:] = clip[-n:] * env[:, None]

    sf.write(str(output_path), clip, sr)
    return output_path


def seamless_loop(input_path: Path, output_path: Path,
                  crossfade: float = 1.5) -> Path:
    """Produce a seamlessly loopable clip by crossfading the tail into the head.

    The resulting file, when played end-to-end repeatedly, has no audible seam:
    the last `crossfade` seconds are blended into the first `crossfade` seconds,
    and the tail is trimmed off.
    """
    data, sr = sf.read(str(input_path))
    n_total = data.shape[0]
    n_fade = int(crossfade * sr)

    if n_fade <= 0 or n_total < 2 * n_fade:
        # Track too short for the requested crossfade; just write as-is.
        sf.write(str(output_path), data, sr)
        return output_path

    # Split: head | middle | tail (head and tail are n_fade frames each)
    head = data[:n_fade].copy()
    tail = data[-n_fade:].copy()
    middle = data[n_fade:-n_fade]

    # Crossfade tail into head with equal-power curves
    t = np.linspace(0.0, 1.0, n_fade)
    fade_out = np.cos(t * np.pi / 2) ** 2  # 1 -> 0
    fade_in = np.sin(t * np.pi / 2) ** 2   # 0 -> 1

    if data.ndim == 1:
        blended_head = head * fade_in + tail * fade_out
    else:
        blended_head = head * fade_in[:, None] + tail * fade_out[:, None]

    # The loop body = blended_head + middle. When played repeatedly, the next
    # iteration's blended_head naturally matches because the crossfade absorbed
    # both ends into a continuous transition.
    looped = np.concatenate([blended_head, middle])
    sf.write(str(output_path), looped, sr)
    return output_path
