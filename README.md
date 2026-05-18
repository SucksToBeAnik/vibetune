# autotune

A lightweight terminal music generator that uses local LLMs (via Ollama) as the creative brain to produce MIDI background music for videos.

## Features

- **LLM-driven composition**: Ollama translates a vibe description into a full music spec (key, tempo, chords, instruments)
- **Built-in player**: Play, pause, and stop without leaving the terminal
- **Trim & crop**: Cut clips to any length
- **Loop-friendly export**: Crossfade-loop a clip seamlessly for video backgrounds
- **Presets**: Save favorite vibes and reuse them
- **Variations**: Generate riffs on a track you liked
- **Save/discard**: Audition before committing

## Setup

### 1. Install Ollama and a model

```bash
# https://ollama.com
ollama pull qwen3.5:4b
```

### 2. Install system dependencies

autotune will tell you if these are missing when you run it.

```bash
# macOS
brew install fluidsynth

# Ubuntu/Debian
sudo apt install fluidsynth fluid-soundfont-gm
```

### 3. Install autotune

```bash
uv tool install .
```

### 4. Run

```bash
autotune
```

## Usage

Once running, describe a vibe and hit enter:

```
autotune> lofi study beat, rainy afternoon, jazzy chords
autotune> upbeat 8-bit adventure theme, fast tempo
autotune> dark ambient drone, cinematic, building tension
```

Then audition with `play`, trim with `trim 0 30`, loop with `loop`, save with `save`, or generate a variation with `vary`.

Type `help` in the app for the full command list.

## Configuration

| Env var              | Default                  | Description                       |
|----------------------|--------------------------|-----------------------------------|
| `AUTOTUNE_HOME`      | `~/.autotune`            | Data directory (cache, library)   |
| `AUTOTUNE_MODEL`     | `qwen3.5:4b`             | Ollama model to use               |
| `AUTOTUNE_SOUNDFONT` | auto-detected            | Path to a custom `.sf2` soundfont |
| `OLLAMA_HOST`        | `http://localhost:11434` | Ollama server URL                 |

