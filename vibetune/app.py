"""vibetune main TUI application.

A simple, snappy REPL: describe a vibe, generate, audition, edit, save or discard.
"""

from __future__ import annotations
import re
import shlex
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from prompt_toolkit import PromptSession, prompt as pt_prompt
from prompt_toolkit.history import FileHistory
from prompt_toolkit.completion import WordCompleter
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import brain, config, editor, midi_gen, presets
from .brain import MusicSpec
from .player import Player


console = Console()


# ---------- App state ----------

@dataclass
class Track:
    path: Path
    title: str
    vibe: str
    duration: float
    spec: Optional[MusicSpec] = None
    history: list[Path] = field(default_factory=list)

    def push_history(self) -> None:
        self.history.append(self.path)


@dataclass
class AppState:
    current: Optional[Track] = None
    default_duration: float = config.DEFAULT_MIDI_DURATION


# ---------- UI helpers ----------

BANNER = r"""
 _   _ _ _          _____            
| | | (_) |__   ___|_   _|   _ _ __  ___ 
| | | | | '_ \ / _ \ | || | | | '_ \/ _ \
| |_| | | |_) |  __/ | || |_| | | | |  __/
 \___/|_|_.__/ \___| |_| \__,_|_| |_|\___|
"""


COMMANDS = [
    "gen", "generate", "vary", "variation",
    "play", "pause", "resume", "stop", "loop",
    "trim", "undo", "save", "discard", "info", "status",
    "library", "preset", "presets", "use",
    "duration", "model", "help", "quit", "exit", "q",
]


def print_banner() -> None:
    console.print(Text(BANNER, style="bold cyan"))
    console.print("[dim]Local-LLM MIDI music generator for videos. Type [bold]help[/bold] for commands.[/dim]\n")


def print_help() -> None:
    table = Table(title="Commands", show_lines=False, header_style="bold cyan")
    table.add_column("Command", style="bold")
    table.add_column("Description")

    rows = [
        ("gen <vibe>",            "Generate a track"),
        ("vary",                  "Generate a variation of the current track"),
        ("play",                  "Play the current track"),
        ("pause / resume",        "Pause/resume playback"),
        ("stop",                  "Stop playback"),
        ("loop [seconds]",        "Make a seamlessly looping version (default crossfade 1.5s)"),
        ("trim <start> <end>",    "Trim to [start, end] in seconds (also accepts mm:ss)"),
        ("undo",                  "Revert last edit"),
        ("save [name]",           "Save current track to library"),
        ("library",               "List saved tracks"),
        ("discard",               "Discard current track"),
        ("info / status",         "Show details about the current track"),
        ("preset save",           "Save a vibe as a preset (interactive)"),
        ("preset edit <name>",    "Edit a preset's name or vibe"),
        ("preset use <name>",     "Generate from a saved preset"),
        ("preset list",           "List saved presets"),
        ("preset delete <name>",  "Delete a preset"),
        ("duration <seconds>",    "Set default generation duration"),
        ("model <name>",          "Switch Ollama model"),
        ("help",                  "Show this help"),
        ("quit",                  "Exit"),
    ]
    for c, d in rows:
        table.add_row(c, d)
    console.print(table)


def fmt_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    m = int(seconds // 60)
    s = seconds - m * 60
    return f"{m}:{s:05.2f}"


def parse_time(s: str) -> float:
    s = s.strip()
    if ":" in s:
        m, sec = s.split(":", 1)
        return int(m) * 60 + float(sec)
    return float(s)


def show_spec(spec: MusicSpec) -> None:
    panel = Panel(
        f"[bold]{spec.title}[/bold]\n"
        f"[cyan]Key:[/cyan] {spec.key} {spec.mode}    "
        f"[cyan]Tempo:[/cyan] {spec.tempo} BPM    "
        f"[cyan]Drums:[/cyan] {spec.drum_style if spec.drums else 'none'}\n"
        f"[cyan]Progression:[/cyan] {' → '.join(spec.chord_progression)}\n"
        f"[cyan]Melody:[/cyan] {spec.melody_instrument}\n"
        f"[cyan]Pad:[/cyan] {spec.pad_instrument}    [cyan]Bass:[/cyan] {spec.bass_instrument}\n"
        f"[dim]{spec.mood_notes}[/dim]",
        title="Composition",
        border_style="cyan",
    )
    console.print(panel)


def _edit_field(label: str, default: str = "") -> Optional[str]:
    """Inline editable prompt. Returns None if the user cancels with Ctrl+C."""
    try:
        result = pt_prompt(f"  {label}: ", default=default)
        return result.strip() or None
    except (KeyboardInterrupt, EOFError):
        return None


# ---------- Generation ----------

def _new_cache_path(prefix: str = "track") -> Path:
    return config.CACHE_DIR / f"{prefix}_{uuid.uuid4().hex[:8]}.wav"


def _safe_filename(s: str) -> str:
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", s).strip("_")
    return s[:60] or "track"


def generate(vibe: str, state: AppState,
             variation_of: Optional[MusicSpec] = None) -> Optional[Track]:
    try:
        with console.status("[cyan]Asking the LLM for a composition...[/cyan]"):
            spec = brain.generate_spec(vibe, variation_of=variation_of)
    except brain.BrainError as e:
        console.print(f"[red]Brain error:[/red] {e}")
        return None

    show_spec(spec)

    path = _new_cache_path("track")
    try:
        with console.status("[cyan]Composing & synthesizing...[/cyan]"):
            midi_gen.generate(spec, state.default_duration, path)
    except midi_gen.SynthesisError as e:
        console.print(f"[red]Synthesis error:[/red] {e}")
        return None
    except Exception as e:
        console.print(f"[red]Generation failed:[/red] {e}")
        return None

    duration = editor.get_duration(path)
    track = Track(path=path, title=spec.title, vibe=vibe, duration=duration, spec=spec)
    console.print(f"[green]✓ Generated:[/green] [bold]{spec.title}[/bold] "
                  f"([dim]{fmt_time(duration)}[/dim])")
    return track


# ---------- Command handlers ----------

def cmd_play(state: AppState, player: Player) -> None:
    if state.current is None:
        console.print("[yellow]No track loaded. Generate one first.[/yellow]")
        return
    player.load(state.current.path, state.current.duration)
    player.play()
    console.print(f"[green]▶ Playing[/green] ({fmt_time(state.current.duration)}). "
                  "Use [bold]pause[/bold] or [bold]stop[/bold].")


def cmd_loop(state: AppState, args: list[str]) -> None:
    if state.current is None:
        console.print("[yellow]No track loaded.[/yellow]")
        return
    try:
        crossfade = float(args[0]) if args else 1.5
    except ValueError:
        console.print("[red]Crossfade must be a number (seconds).[/red]")
        return

    new_path = _new_cache_path("loop")
    try:
        editor.seamless_loop(state.current.path, new_path, crossfade=crossfade)
    except Exception as e:
        console.print(f"[red]Loop failed:[/red] {e}")
        return

    state.current.push_history()
    state.current.path = new_path
    state.current.duration = editor.get_duration(new_path)
    console.print(f"[green]✓ Loop-ready[/green] "
                  f"(crossfade {crossfade}s, new length {fmt_time(state.current.duration)})")


def cmd_trim(state: AppState, args: list[str]) -> None:
    if state.current is None:
        console.print("[yellow]No track loaded.[/yellow]")
        return
    if len(args) < 2:
        console.print("[red]Usage:[/red] trim <start> <end>  (seconds or mm:ss)")
        return
    try:
        start = parse_time(args[0])
        end = parse_time(args[1])
    except ValueError:
        console.print("[red]Invalid time format.[/red]")
        return

    new_path = _new_cache_path("trim")
    try:
        editor.trim(state.current.path, new_path, start, end, fade_in=0.02, fade_out=0.05)
    except Exception as e:
        console.print(f"[red]Trim failed:[/red] {e}")
        return

    state.current.push_history()
    state.current.path = new_path
    state.current.duration = editor.get_duration(new_path)
    console.print(f"[green]✓ Trimmed[/green] to {fmt_time(state.current.duration)}")


def cmd_undo(state: AppState) -> None:
    if state.current is None or not state.current.history:
        console.print("[yellow]Nothing to undo.[/yellow]")
        return
    prev = state.current.history.pop()
    state.current.path = prev
    state.current.duration = editor.get_duration(prev)
    console.print(f"[green]↶ Reverted[/green] ({fmt_time(state.current.duration)})")


def cmd_save(state: AppState, args: list[str]) -> None:
    if state.current is None:
        console.print("[yellow]No track to save.[/yellow]")
        return
    if args:
        name = "_".join(args)
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        name = f"{_safe_filename(state.current.title)}_{ts}"

    out = config.LIBRARY_DIR / f"{_safe_filename(name)}.wav"
    import shutil
    shutil.copy(state.current.path, out)
    console.print(f"[green]Saved:[/green] {out}")


def cmd_discard(state: AppState, player: Player) -> None:
    if state.current is None:
        console.print("[yellow]Nothing to discard.[/yellow]")
        return
    player.stop()
    state.current = None
    console.print("[dim]Discarded.[/dim]")


def cmd_info(state: AppState) -> None:
    if state.current is None:
        console.print("[yellow]No track loaded.[/yellow]")
        return
    t = state.current
    console.print(Panel(
        f"[bold]{t.title}[/bold]\n"
        f"[cyan]Duration:[/cyan] {fmt_time(t.duration)}\n"
        f"[cyan]Vibe:[/cyan] {t.vibe}\n"
        f"[cyan]File:[/cyan] {t.path}\n"
        f"[dim]Edits stacked: {len(t.history)}[/dim]",
        title="Track info",
        border_style="cyan",
    ))
    if t.spec:
        show_spec(t.spec)


def cmd_library() -> None:
    wav_files = sorted(
        config.LIBRARY_DIR.glob("*.wav"),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    if not wav_files:
        console.print("[dim]Library is empty. Use [bold]save[/bold] to add tracks.[/dim]")
        return

    table = Table(title="Library", header_style="bold cyan")
    table.add_column("#", style="dim", justify="right")
    table.add_column("Name", style="bold")
    table.add_column("Duration", justify="right")
    table.add_column("Size", justify="right")
    table.add_column("Saved")

    for i, f in enumerate(wav_files, 1):
        try:
            dur_str = fmt_time(editor.get_duration(f))
        except Exception:
            dur_str = "?"
        size = f.stat().st_size
        size_str = f"{size / 1024:.0f} KB" if size < 1_048_576 else f"{size / 1_048_576:.1f} MB"
        saved = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        table.add_row(str(i), f.stem, dur_str, size_str, saved)

    console.print(table)


def cmd_preset(state: AppState, args: list[str]) -> None:
    if not args:
        console.print("[red]Usage:[/red] preset save|edit|use|list|delete [name]")
        return
    sub = args[0].lower()

    if sub == "list":
        all_names = presets.names()
        if not all_names:
            console.print("[dim]No presets yet.[/dim]")
            return
        table = Table(title="Presets", header_style="bold cyan")
        table.add_column("Name", style="bold")
        table.add_column("Vibe")
        table.add_column("Saved")
        for n in all_names:
            p = presets.get(n)
            table.add_row(n, p.get("vibe", "")[:60], p.get("created", ""))
        console.print(table)

    elif sub == "save":
        # Determine the vibe
        if state.current is not None:
            console.print(f"  [bold]1.[/bold] Use current vibe  [dim]{state.current.vibe[:60]}[/dim]")
            console.print("  [bold]2.[/bold] Enter new vibe")
            choice = _edit_field("Choice [1/2]", default="1")
            if choice is None:
                console.print("[dim]Cancelled.[/dim]")
                return
            if choice == "1":
                vibe = state.current.vibe
            else:
                vibe = _edit_field("Vibe")
                if not vibe:
                    console.print("[dim]Cancelled.[/dim]")
                    return
        else:
            vibe = _edit_field("Vibe")
            if not vibe:
                console.print("[dim]Cancelled.[/dim]")
                return

        name = _edit_field("Name")
        if not name:
            console.print("[dim]Cancelled.[/dim]")
            return

        extras = {}
        if state.current and state.current.spec and vibe == state.current.vibe:
            extras["spec"] = state.current.spec.to_json()
        presets.save(name, vibe, extras)
        console.print(f"[green]✓ Preset saved:[/green] {name}")

    elif sub == "edit":
        if len(args) < 2:
            console.print("[red]Usage:[/red] preset edit <name>")
            return
        old_name = args[1]
        p = presets.get(old_name)
        if not p:
            console.print(f"[yellow]Not found:[/yellow] {old_name}")
            return

        console.print("[dim]Edit fields — press Enter to keep, Ctrl+C to cancel.[/dim]")
        new_name = _edit_field("Name", default=old_name)
        if new_name is None:
            console.print("[dim]Cancelled.[/dim]")
            return
        new_vibe = _edit_field("Vibe", default=p.get("vibe", ""))
        if new_vibe is None:
            console.print("[dim]Cancelled.[/dim]")
            return

        extras = {k: v for k, v in p.items() if k not in ("vibe", "created")}
        # Drop the cached spec if the vibe changed — it's now stale
        if new_vibe != p.get("vibe"):
            extras.pop("spec", None)

        if new_name != old_name:
            presets.delete(old_name)
        presets.save(new_name, new_vibe, extras)
        console.print(f"[green]✓ Preset updated:[/green] {new_name}")

    elif sub == "delete":
        if len(args) < 2:
            console.print("[red]Usage:[/red] preset delete <name>")
            return
        if presets.delete(args[1]):
            console.print(f"[green]✓ Deleted:[/green] {args[1]}")
        else:
            console.print(f"[yellow]Not found:[/yellow] {args[1]}")

    elif sub == "use":
        if len(args) < 2:
            console.print("[red]Usage:[/red] preset use <name>")
            return
        p = presets.get(args[1])
        if not p:
            console.print(f"[yellow]Not found:[/yellow] {args[1]}")
            return
        vibe = p["vibe"]
        console.print(f"[dim]Using preset '{args[1]}': {vibe}[/dim]")
        track = generate(vibe, state)
        if track:
            state.current = track

    else:
        console.print(f"[red]Unknown preset subcommand:[/red] {sub}")


def cmd_duration(state: AppState, args: list[str]) -> None:
    if not args:
        console.print(f"Default duration: [bold]{state.default_duration}s[/bold]")
        return
    try:
        state.default_duration = float(args[0])
        console.print(f"[green]✓[/green] Duration: {state.default_duration}s")
    except ValueError:
        console.print("[red]Duration must be a number (seconds).[/red]")


def cmd_model(args: list[str]) -> None:
    if not args:
        console.print(f"Current model: [bold]{config.OLLAMA_MODEL}[/bold]")
        return
    config.OLLAMA_MODEL = args[0]
    ok, msg = brain.check_ollama()
    if ok:
        console.print(f"[green]✓[/green] {msg}")
    else:
        console.print(f"[yellow]⚠[/yellow] {msg}")


# ---------- Main loop ----------

def run() -> None:
    print_banner()

    ok, msg = brain.check_ollama()
    style = "green" if ok else "yellow"
    console.print(f"[{style}]●[/{style}] {msg}")
    if not config.find_soundfont():
        console.print(
            "[yellow]●[/yellow] No soundfont found — MIDI will use basic sine-wave synthesis. "
            "Install [bold]fluid-soundfont-gm[/bold] (apt) or [bold]fluidsynth[/bold] (brew) "
            "for richer sound."
        )
    else:
        console.print(f"[green]●[/green] Soundfont: {config.find_soundfont()}")
    console.print()

    state = AppState()
    player = Player()

    session = PromptSession(
        history=FileHistory(str(config.DATA_DIR / "history")),
        completer=WordCompleter(COMMANDS, ignore_case=True),
    )

    try:
        while True:
            try:
                line = session.prompt("vibetune> ").strip()
            except (KeyboardInterrupt, EOFError):
                console.print()
                break

            if not line:
                continue

            try:
                tokens = shlex.split(line)
            except ValueError:
                tokens = line.split()
            cmd = tokens[0].lower()
            args = tokens[1:]
            rest = line[len(tokens[0]):].strip()

            try:
                if cmd in ("quit", "exit", "q"):
                    break
                elif cmd == "help":
                    print_help()
                elif cmd in ("gen", "generate"):
                    if not rest:
                        console.print("[red]Usage:[/red] gen <vibe description>")
                        continue
                    t = generate(rest, state)
                    if t:
                        state.current = t
                elif cmd in ("vary", "variation"):
                    if state.current is None:
                        console.print("[yellow]No track loaded. Generate one first.[/yellow]")
                        continue
                    t = generate(state.current.vibe, state,
                                 variation_of=state.current.spec)
                    if t:
                        state.current = t
                elif cmd == "play":
                    cmd_play(state, player)
                elif cmd == "pause":
                    player.pause()
                    console.print("[yellow]⏸ Paused[/yellow]")
                elif cmd == "resume":
                    player.unpause()
                    console.print("[green]▶ Resumed[/green]")
                elif cmd == "stop":
                    player.stop()
                    console.print("[dim]⏹ Stopped[/dim]")
                elif cmd == "loop":
                    cmd_loop(state, args)
                elif cmd == "trim":
                    cmd_trim(state, args)
                elif cmd == "undo":
                    cmd_undo(state)
                elif cmd == "save":
                    cmd_save(state, args)
                elif cmd == "library":
                    cmd_library()
                elif cmd == "discard":
                    cmd_discard(state, player)
                elif cmd in ("info", "status"):
                    cmd_info(state)
                elif cmd == "preset":
                    cmd_preset(state, args)
                elif cmd == "presets":
                    cmd_preset(state, ["list"])
                elif cmd == "use":
                    cmd_preset(state, ["use", *args])
                elif cmd == "duration":
                    cmd_duration(state, args)
                elif cmd == "model":
                    cmd_model(args)
                else:
                    console.print(f"[red]Unknown command:[/red] {cmd}. "
                                  "Type [bold]help[/bold].")
            except Exception as e:
                console.print(f"[red]Error:[/red] {e}")

    finally:
        player.shutdown()
        console.print("[dim]Bye![/dim]")
