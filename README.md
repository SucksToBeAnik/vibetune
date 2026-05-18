# vibetune

A lightweight terminal music generator that uses local LLMs (via Ollama) as the creative brain to produce MIDI background music for videos.

## Features

- **LLM-driven composition**: Ollama translates a vibe description into a full music spec (key, tempo, chords, instruments)
- **Built-in player**: Play, pause, and stop without leaving the terminal
- **Trim & crop**: Cut clips to any length
- **Loop-friendly export**: Crossfade-loop a clip seamlessly for video backgrounds
- **Presets**: Save favorite vibes and reuse them
- **Variations**: Generate riffs on a track you liked
- **Save/discard**: Audition before committing

## Installation

### 1. Install prerequisites

**Ollama** — runs the local LLM ([ollama.com](https://ollama.com)):

```bash
ollama pull qwen3.5:4b
```

**FluidSynth** — MIDI synthesis (vibetune will remind you if it's missing):

```bash
# macOS
brew install fluidsynth

# Ubuntu/Debian
sudo apt install fluidsynth fluid-soundfont-gm
```

### 2. Install vibetune

```bash
pip install vibetune
```

### 3. Run

```bash
vibetune
```

## Usage

### Generating a track

Describe any vibe and vibetune composes a MIDI track via the local LLM:

```
vibetune> gen lofi study beat, rainy afternoon, jazzy chords
vibetune> gen upbeat 8-bit adventure theme, fast tempo
vibetune> gen dark ambient drone, cinematic, building tension
```

### Auditioning and editing

```
vibetune> play               # play the current track
vibetune> pause              # pause
vibetune> resume             # resume
vibetune> stop               # stop playback

vibetune> trim 0 30          # cut to the first 30 seconds
vibetune> trim 0:10 0:45     # also accepts mm:ss format
vibetune> loop               # crossfade the end into the start for seamless looping
vibetune> loop 2.5           # longer crossfade (seconds)
vibetune> undo               # revert the last edit

vibetune> info               # show key, tempo, instruments, chord progression
```

### Saving

```
vibetune> save               # save with an auto-generated name
vibetune> save my_track      # save with a custom name
vibetune> library            # list all saved tracks
vibetune> discard            # throw away the current track without saving
```

### Variations

Generate a new track with the same vibe but different chords, tempo, and instruments:

```
vibetune> vary
```

### Presets

Save a vibe you like and reuse it later:

```
vibetune> preset save              # interactive: pick current vibe or enter a new one
vibetune> preset list              # show all saved presets
vibetune> preset use lofi-study    # generate a track from a preset
vibetune> preset edit lofi-study   # edit the preset's name or vibe inline
vibetune> preset delete lofi-study # remove a preset
```

### Other

```
vibetune> duration 60        # set default track length to 60 seconds
vibetune> model qwen3.5:9b   # switch to a different Ollama model
vibetune> help               # full command reference
vibetune> quit
```

## Configuration

| Env var              | Default                  | Description                       |
|----------------------|--------------------------|-----------------------------------|
| `VIBETUNE_HOME`      | `~/.vibetune`            | Data directory (cache, library)   |
| `VIBETUNE_MODEL`     | `qwen3.5:4b`             | Ollama model to use               |
| `VIBETUNE_SOUNDFONT` | auto-detected            | Path to a custom `.sf2` soundfont |
| `OLLAMA_HOST`        | `http://localhost:11434` | Ollama server URL                 |
