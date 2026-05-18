"""Ollama LLM interface — the creative brain.

Returns a structured MusicSpec (key, tempo, chords, melody, drums) for MIDI synthesis.
"""

from __future__ import annotations
import json
import re
from dataclasses import dataclass, field, asdict
from typing import Optional

import ollama

from . import config


# ---------- Data shapes ----------

@dataclass
class MusicSpec:
    title: str = "Untitled"
    key: str = "C"
    mode: str = "major"             # "major" | "minor"
    tempo: int = 90                 # BPM
    chord_progression: list[str] = field(default_factory=lambda: ["I", "V", "vi", "IV"])
    melody_instrument: str = "Acoustic Grand Piano"
    pad_instrument: str = "String Ensemble 1"
    bass_instrument: str = "Acoustic Bass"
    drums: bool = True
    drum_style: str = "lofi"        # "lofi" | "rock" | "electronic" | "ambient" | "none"
    melody_density: float = 0.5     # 0=sparse, 1=busy
    swing: float = 0.0              # 0=straight, 0.6=heavy swing
    mood_notes: str = ""

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)


# ---------- Prompt ----------

MIDI_SYSTEM_PROMPT = """You are a music composition assistant. Given a vibe description, output a JSON object describing how to compose a short instrumental piece. Output ONLY valid JSON, no prose, no markdown fences.

Required schema:
{
  "title": "short evocative title",
  "key": "C" | "D" | "E" | "F" | "G" | "A" | "B" | with optional "#" or "b",
  "mode": "major" | "minor",
  "tempo": integer BPM (60-180),
  "chord_progression": array of 4-8 roman numerals like "I", "IV", "V", "vi", "ii", "iii", "bVII",
  "melody_instrument": General MIDI instrument name (e.g. "Acoustic Grand Piano", "Electric Piano 1", "Music Box", "Pad 2 (warm)", "Acoustic Guitar (nylon)", "Synth Lead 1 (square)"),
  "pad_instrument": General MIDI instrument name for sustained background,
  "bass_instrument": GM bass instrument (e.g. "Acoustic Bass", "Electric Bass (finger)", "Synth Bass 1"),
  "drums": true | false,
  "drum_style": "lofi" | "rock" | "electronic" | "ambient" | "none",
  "melody_density": float 0.0 to 1.0 (sparse to busy),
  "swing": float 0.0 to 0.7,
  "mood_notes": "short note about the feeling"
}

Pick choices that match the requested vibe. For lofi/study: slow tempo (70-90), jazzy chords like "ii", "V7", "Imaj7", piano + soft drums, swing ~0.3. For ambient: very slow (50-70), pads, no drums or sparse, drum_style "ambient". For chiptune/8-bit: fast (120-160), use "Synth Lead" instruments, drum_style "electronic". For cinematic: dynamic tempo (70-110), strings/pads, sparse melody."""


# ---------- Ollama client ----------

class BrainError(RuntimeError):
    pass


def _client() -> ollama.Client:
    return ollama.Client(host=config.OLLAMA_HOST)


def _call_ollama(prompt: str, system: str, *, temperature: float = 0.8) -> str:
    try:
        response = _client().generate(
            model=config.OLLAMA_MODEL,
            prompt=prompt,
            system=system,
            format="json",
            stream=False,
            think=False,  # disable thinking mode so the response field isn't empty
            options={"temperature": temperature},
        )
        return response.response.strip()
    except ollama.ResponseError as e:
        if e.status_code == 404:
            raise BrainError(
                f"Model '{config.OLLAMA_MODEL}' not found. "
                f"Try: ollama pull {config.OLLAMA_MODEL}"
            ) from e
        raise BrainError(f"Ollama error: {e}") from e
    except Exception as e:
        raise BrainError(
            f"Could not reach Ollama at {config.OLLAMA_HOST}. Is it running?"
        ) from e


def _extract_json(text: str) -> dict:
    # Strip thinking blocks that some models emit even with think=False
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    # Strip code fences
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Fallback: extract first {...} block
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError as e:
            raise BrainError(f"LLM returned invalid JSON: {e}\n---\n{text[:500]}")
    raise BrainError(f"No JSON found in LLM response:\n{text[:500]}")


def _coerce_spec(data: dict) -> MusicSpec:
    spec = MusicSpec()
    spec.title = str(data.get("title", spec.title))[:60]
    spec.key = str(data.get("key", spec.key))[:3]
    mode = str(data.get("mode", spec.mode)).lower()
    spec.mode = "minor" if mode.startswith("min") else "major"
    try:
        spec.tempo = max(40, min(200, int(data.get("tempo", spec.tempo))))
    except (TypeError, ValueError):
        spec.tempo = 90
    cp = data.get("chord_progression") or spec.chord_progression
    if isinstance(cp, list) and cp:
        spec.chord_progression = [str(c)[:8] for c in cp[:12]]
    spec.melody_instrument = str(data.get("melody_instrument", spec.melody_instrument))
    spec.pad_instrument = str(data.get("pad_instrument", spec.pad_instrument))
    spec.bass_instrument = str(data.get("bass_instrument", spec.bass_instrument))
    spec.drums = bool(data.get("drums", spec.drums))
    spec.drum_style = str(data.get("drum_style", spec.drum_style)).lower()
    try:
        spec.melody_density = max(0.0, min(1.0, float(data.get("melody_density", 0.5))))
    except (TypeError, ValueError):
        spec.melody_density = 0.5
    try:
        spec.swing = max(0.0, min(0.7, float(data.get("swing", 0.0))))
    except (TypeError, ValueError):
        spec.swing = 0.0
    spec.mood_notes = str(data.get("mood_notes", ""))[:200]
    return spec


# ---------- Public API ----------

def generate_spec(vibe: str, *, variation_of: Optional[MusicSpec] = None) -> MusicSpec:
    if variation_of is not None:
        prompt = (
            f"Create a VARIATION of this previous track (same general vibe but different "
            f"melody/chords/feel — like a remix or alt version):\n\n"
            f"Previous spec:\n{variation_of.to_json()}\n\n"
            f"Keep the overall mood but change the chord progression, vary tempo slightly "
            f"(±15 BPM), and consider different instruments. Output the new JSON only."
        )
    else:
        prompt = f"Vibe to compose: {vibe}\n\nOutput the JSON spec now."

    raw = _call_ollama(prompt, MIDI_SYSTEM_PROMPT, temperature=0.9)
    return _coerce_spec(_extract_json(raw))


def check_ollama() -> tuple[bool, str]:
    try:
        result = _client().list()
        names = [m.model for m in result.models]
        if not names:
            return False, "Ollama running but no models installed."
        target = config.OLLAMA_MODEL
        if not any(n == target or n.startswith(target.split(":")[0] + ":") for n in names):
            return False, (
                f"Model '{target}' not found. Available: {', '.join(names)}. "
                f"Try: ollama pull {target}"
            )
        return True, f"Ollama OK ({target})"
    except Exception:
        return False, f"Cannot reach Ollama at {config.OLLAMA_HOST}. Run: ollama serve"
