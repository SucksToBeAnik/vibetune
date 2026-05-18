"""MIDI composition + synthesis.

Translates a MusicSpec into a multi-track MIDI file, then renders to WAV via
FluidSynth (subprocess) using a General MIDI soundfont.
"""

from __future__ import annotations
import random
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import pretty_midi

from . import config
from .brain import MusicSpec


# ---------- Music theory helpers ----------

NOTE_TO_SEMITONE = {
    "C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3,
    "E": 4, "F": 5, "F#": 6, "Gb": 6, "G": 7, "G#": 8,
    "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11,
}

# Scale degree -> semitone offset from root
MAJOR_SCALE = [0, 2, 4, 5, 7, 9, 11]
MINOR_SCALE = [0, 2, 3, 5, 7, 8, 10]

# Roman numeral -> (scale_degree_index, chord_type)
# chord_type: "maj", "min", "dim", "maj7", "min7", "dom7"
ROMAN_MAJOR = {
    "I": (0, "maj"), "ii": (1, "min"), "iii": (2, "min"),
    "IV": (3, "maj"), "V": (4, "maj"), "vi": (5, "min"),
    "vii°": (6, "dim"), "viio": (6, "dim"),
    "Imaj7": (0, "maj7"), "ii7": (1, "min7"), "iii7": (2, "min7"),
    "IVmaj7": (3, "maj7"), "V7": (4, "dom7"), "vi7": (5, "min7"),
    "bVII": (6, "maj"),  # borrowed from parallel minor (lowered 7)
    "bIII": (2, "maj"),
    "bVI": (5, "maj"),
}
ROMAN_MINOR = {
    "i": (0, "min"), "ii°": (1, "dim"), "iio": (1, "dim"),
    "III": (2, "maj"), "iv": (3, "min"), "v": (4, "min"),
    "V": (4, "maj"),  # harmonic minor V
    "V7": (4, "dom7"),
    "VI": (5, "maj"), "VII": (6, "maj"),
    "i7": (0, "min7"), "iv7": (3, "min7"),
}

CHORD_INTERVALS = {
    "maj": [0, 4, 7], "min": [0, 3, 7], "dim": [0, 3, 6],
    "maj7": [0, 4, 7, 11], "min7": [0, 3, 7, 10], "dom7": [0, 4, 7, 10],
}


def _parse_key(key: str, mode: str) -> int:
    """Return the root pitch class (0-11) of the key."""
    key = key.strip()
    # Try 2-char first (handles "C#", "Bb"), then 1-char.
    for length in (2, 1):
        if len(key) >= length and key[:length] in NOTE_TO_SEMITONE:
            return NOTE_TO_SEMITONE[key[:length]]
    return 0  # default C


def _scale_pitches(root: int, mode: str, octave: int = 4) -> list[int]:
    """Return MIDI note numbers for one octave of the scale starting at C4-area."""
    scale = MINOR_SCALE if mode == "minor" else MAJOR_SCALE
    base = 12 * (octave + 1) + root  # MIDI: C4 = 60
    return [base + s for s in scale]


def _chord_notes(roman: str, root_pc: int, mode: str, octave: int = 3) -> list[int]:
    """Translate a roman numeral into a list of MIDI pitches at the given octave."""
    table = ROMAN_MINOR if mode == "minor" else ROMAN_MAJOR
    info = table.get(roman)
    if info is None:
        # Try case-insensitive lookup as fallback
        for k, v in table.items():
            if k.lower() == roman.lower():
                info = v
                break
    if info is None:
        info = (0, "maj" if mode == "major" else "min")  # default to tonic

    degree_idx, chord_type = info
    scale = MINOR_SCALE if mode == "minor" else MAJOR_SCALE
    chord_root_pc = (root_pc + scale[degree_idx]) % 12
    chord_root_midi = 12 * (octave + 1) + chord_root_pc
    intervals = CHORD_INTERVALS.get(chord_type, [0, 4, 7])
    return [chord_root_midi + i for i in intervals]


def _gm_program(name: str) -> int:
    """Map an instrument name to a General MIDI program number, with fallback."""
    try:
        return pretty_midi.instrument_name_to_program(name)
    except Exception:
        # Fuzzy fallback — search the GM list
        name_lower = name.lower()
        for i in range(128):
            if name_lower in pretty_midi.program_to_instrument_name(i).lower():
                return i
        return 0  # Acoustic Grand Piano


# ---------- Composition ----------

def _add_pad(pm: pretty_midi.PrettyMIDI, spec: MusicSpec,
             root_pc: int, beats_per_chord: float, total_beats: float) -> None:
    """Long sustained chord pad underneath everything."""
    pad = pretty_midi.Instrument(program=_gm_program(spec.pad_instrument))
    seconds_per_beat = 60.0 / spec.tempo
    progression = spec.chord_progression

    t = 0.0
    i = 0
    while t < total_beats * seconds_per_beat - 0.01:
        chord = progression[i % len(progression)]
        notes = _chord_notes(chord, root_pc, spec.mode, octave=4)
        duration = beats_per_chord * seconds_per_beat
        for pitch in notes:
            pad.notes.append(pretty_midi.Note(
                velocity=50, pitch=pitch, start=t, end=t + duration
            ))
        t += duration
        i += 1
    pm.instruments.append(pad)


def _add_bass(pm: pretty_midi.PrettyMIDI, spec: MusicSpec,
              root_pc: int, beats_per_chord: float, total_beats: float) -> None:
    """Root-note bass on each chord, with occasional 5th."""
    bass = pretty_midi.Instrument(program=_gm_program(spec.bass_instrument))
    seconds_per_beat = 60.0 / spec.tempo
    progression = spec.chord_progression
    rng = random.Random(hash(spec.title) & 0xFFFFFFFF)

    t = 0.0
    i = 0
    while t < total_beats * seconds_per_beat - 0.01:
        chord = progression[i % len(progression)]
        notes = _chord_notes(chord, root_pc, spec.mode, octave=2)
        root_note = notes[0]
        fifth_note = notes[2] if len(notes) > 2 else root_note + 7

        # On each beat of the chord, play root, occasionally fifth on offbeat
        for b in range(int(beats_per_chord)):
            start = t + b * seconds_per_beat
            pitch = root_note if b % 2 == 0 or rng.random() > 0.4 else fifth_note
            bass.notes.append(pretty_midi.Note(
                velocity=75, pitch=pitch,
                start=start, end=start + seconds_per_beat * 0.9
            ))
        t += beats_per_chord * seconds_per_beat
        i += 1
    pm.instruments.append(bass)


def _add_melody(pm: pretty_midi.PrettyMIDI, spec: MusicSpec,
                root_pc: int, beats_per_chord: float, total_beats: float) -> None:
    """Generate a melody by walking the scale around each chord's tones."""
    mel = pretty_midi.Instrument(program=_gm_program(spec.melody_instrument))
    seconds_per_beat = 60.0 / spec.tempo
    progression = spec.chord_progression
    scale = _scale_pitches(root_pc, spec.mode, octave=5)
    rng = random.Random(hash(spec.title + "mel") & 0xFFFFFFFF)

    # Subdivision: density 0 = quarter notes, 1 = sixteenth notes
    if spec.melody_density < 0.3:
        subdiv = 1.0   # quarter notes
    elif spec.melody_density < 0.7:
        subdiv = 0.5   # eighth notes
    else:
        subdiv = 0.25  # sixteenth notes

    swing_offset = spec.swing * subdiv * seconds_per_beat * 0.5

    t = 0.0
    chord_idx = 0
    last_pitch_idx = 3  # start mid-scale
    while t < total_beats * seconds_per_beat - 0.01:
        chord = progression[chord_idx % len(progression)]
        chord_tones = _chord_notes(chord, root_pc, spec.mode, octave=5)
        chord_duration_sec = beats_per_chord * seconds_per_beat
        chord_end = t + chord_duration_sec

        local_t = t
        step = 0
        while local_t < chord_end - 0.01:
            note_dur = subdiv * seconds_per_beat
            # Rest probability — sparser melodies have more rests
            if rng.random() < (1.0 - spec.melody_density) * 0.6:
                local_t += note_dur
                step += 1
                continue

            # On strong beats, prefer chord tones; elsewhere, walk the scale
            if step % 2 == 0 and rng.random() < 0.6:
                pitch = rng.choice(chord_tones)
            else:
                # Random walk: move ±1-2 scale steps
                move = rng.choice([-2, -1, -1, 1, 1, 2])
                last_pitch_idx = max(0, min(len(scale) - 1, last_pitch_idx + move))
                pitch = scale[last_pitch_idx]

            # Apply swing to off-beats
            start = local_t
            if step % 2 == 1 and swing_offset > 0:
                start += swing_offset

            velocity = 70 + rng.randint(-15, 20)
            velocity = max(40, min(110, velocity))
            mel.notes.append(pretty_midi.Note(
                velocity=velocity, pitch=pitch,
                start=start, end=start + note_dur * 0.85
            ))
            local_t += note_dur
            step += 1

        t += chord_duration_sec
        chord_idx += 1
    pm.instruments.append(mel)


def _add_drums(pm: pretty_midi.PrettyMIDI, spec: MusicSpec, total_beats: float) -> None:
    """Drums on channel 10 (GM drumkit). Style-specific patterns."""
    if not spec.drums or spec.drum_style == "none":
        return

    drums = pretty_midi.Instrument(program=0, is_drum=True, name="Drums")
    seconds_per_beat = 60.0 / spec.tempo
    style = spec.drum_style

    # GM drum note numbers
    KICK, SNARE, HAT_CLOSED, HAT_OPEN, RIDE = 36, 38, 42, 46, 51

    rng = random.Random(hash(spec.title + "drums") & 0xFFFFFFFF)

    for beat in range(int(total_beats)):
        t = beat * seconds_per_beat

        if style == "lofi":
            # Kick on 1 & 3, snare on 2 & 4, soft hats on 8ths
            if beat % 4 in (0, 2):
                drums.notes.append(pretty_midi.Note(85, KICK, t, t + 0.1))
            if beat % 4 in (1, 3):
                drums.notes.append(pretty_midi.Note(70, SNARE, t, t + 0.1))
            for sub in (0, 0.5):
                offset = sub * seconds_per_beat + (spec.swing * 0.5 * seconds_per_beat if sub else 0)
                vel = 50 + rng.randint(-10, 10)
                drums.notes.append(pretty_midi.Note(vel, HAT_CLOSED, t + offset, t + offset + 0.05))

        elif style == "rock":
            if beat % 4 in (0, 2):
                drums.notes.append(pretty_midi.Note(100, KICK, t, t + 0.1))
            if beat % 4 in (1, 3):
                drums.notes.append(pretty_midi.Note(95, SNARE, t, t + 0.1))
            # Constant 8th hats
            for sub in (0, 0.5):
                offset = sub * seconds_per_beat
                drums.notes.append(pretty_midi.Note(75, HAT_CLOSED, t + offset, t + offset + 0.05))

        elif style == "electronic":
            # Four-on-the-floor
            drums.notes.append(pretty_midi.Note(100, KICK, t, t + 0.1))
            if beat % 2 == 1:
                drums.notes.append(pretty_midi.Note(85, SNARE, t, t + 0.1))
            # Offbeat open hat
            offset = 0.5 * seconds_per_beat
            drums.notes.append(pretty_midi.Note(70, HAT_OPEN, t + offset, t + offset + 0.1))

        elif style == "ambient":
            # Very sparse — occasional soft kick or ride
            if beat % 8 == 0:
                drums.notes.append(pretty_midi.Note(55, KICK, t, t + 0.1))
            if rng.random() < 0.15:
                drums.notes.append(pretty_midi.Note(40, RIDE, t, t + 0.1))

    pm.instruments.append(drums)


def compose_midi(spec: MusicSpec, duration_seconds: float) -> pretty_midi.PrettyMIDI:
    """Build a PrettyMIDI object from a MusicSpec, looping the progression."""
    pm = pretty_midi.PrettyMIDI(initial_tempo=spec.tempo)
    root_pc = _parse_key(spec.key, spec.mode)

    # 2 beats per chord by default for a 4-chord loop = 8 beats per cycle.
    # For longer progressions we shorten so loops fit nicely.
    progression_len = len(spec.chord_progression)
    beats_per_chord = 4.0 if progression_len <= 4 else 2.0

    seconds_per_beat = 60.0 / spec.tempo
    total_beats = duration_seconds / seconds_per_beat
    # Round up to a whole progression cycle
    cycle = progression_len * beats_per_chord
    total_beats = max(cycle, round(total_beats / cycle) * cycle)

    _add_pad(pm, spec, root_pc, beats_per_chord, total_beats)
    _add_bass(pm, spec, root_pc, beats_per_chord, total_beats)
    _add_melody(pm, spec, root_pc, beats_per_chord, total_beats)
    _add_drums(pm, spec, total_beats)

    return pm


# ---------- Synthesis ----------

class SynthesisError(RuntimeError):
    pass


def _normalize_peak(wav_path: Path, target_peak: float = 0.9) -> None:
    """Peak-normalize a WAV file in place to avoid clipping and keep volume consistent."""
    import soundfile as sf
    import numpy as np
    data, sr = sf.read(str(wav_path))
    peak = float(np.max(np.abs(data)))
    if peak > 1e-6:
        data = data * (target_peak / peak)
        sf.write(str(wav_path), data, sr)


def synthesize(pm: pretty_midi.PrettyMIDI, output_wav: Path,
               soundfont: Optional[str] = None) -> Path:
    """Render MIDI to WAV via fluidsynth subprocess.

    Tries the high-quality CLI fluidsynth first, falls back to pretty_midi's
    built-in sine-wave synthesis (still works, sounds basic).
    """
    soundfont = soundfont or config.find_soundfont()

    if soundfont and config.has_fluidsynth():
        with tempfile.NamedTemporaryFile(suffix=".mid", delete=False) as tmp:
            mid_path = Path(tmp.name)
        try:
            pm.write(str(mid_path))
            result = subprocess.run(
                [
                    "fluidsynth", "-ni", "-g", "0.5",
                    "-F", str(output_wav),
                    "-r", str(config.SAMPLE_RATE),
                    soundfont, str(mid_path),
                ],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode != 0:
                raise SynthesisError(
                    f"fluidsynth failed: {result.stderr[:300]}"
                )
        finally:
            mid_path.unlink(missing_ok=True)
        _normalize_peak(output_wav)
        return output_wav

    # Fallback: pretty_midi's built-in synth (sine waves, no soundfont needed)
    import soundfile as sf
    audio = pm.synthesize(fs=config.SAMPLE_RATE)
    sf.write(str(output_wav), audio, config.SAMPLE_RATE)
    _normalize_peak(output_wav)
    return output_wav


def generate(spec: MusicSpec, duration: float, output_path: Path) -> Path:
    """Top-level: compose + synthesize, returns path to WAV."""
    pm = compose_midi(spec, duration)
    return synthesize(pm, output_path)
