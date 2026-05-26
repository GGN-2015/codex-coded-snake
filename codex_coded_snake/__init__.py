"""Codex Coded Snake package.

This package exposes a simple snake game with procedural audio and a Tkinter UI.
"""

from .main import AudioEngine, MusicComposer, SnakeGame, chirp_event, midi, percussion_event, scale_note, tone_event

__all__ = [
    "AudioEngine",
    "MusicComposer",
    "SnakeGame",
    "chirp_event",
    "midi",
    "percussion_event",
    "scale_note",
    "tone_event",
]
