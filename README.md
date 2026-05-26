# codex-coded-snake

`codex-coded-snake` is a lightweight Python package that delivers a retro-style Snake game with procedural music and sound effects. The game is built using Tkinter for the UI and native audio on Windows.

## Features

- Classic snake gameplay with keyboard controls
- Dynamic procedural soundtrack generated in real time
- Minimal dependency footprint: standard library only
- Runs as a package via `python -m codex_coded_snake`

## Installation

```bash
pip install codex-coded-snake
```

> Note: the packaged audio engine currently uses the Windows `winmm` API. The game UI uses Tkinter, so a desktop Python environment is required.

## Usage

Run the game from the command line:

```bash
python -m codex_coded_snake
```

Or import the package in your own Python code:

```python
from codex_coded_snake import SnakeGame

SnakeGame().run()
```

## Controls

- `Up`, `Down`, `Left`, `Right` or `W`, `A`, `S`, `D`: move the snake
- `P`: pause / resume
- `R`: restart after game over

## Package Structure

- `codex_coded_snake/main.py`: game logic, audio engine, and entry point
- `codex_coded_snake/__init__.py`: package exports
- `codex_coded_snake/__main__.py`: module entry point for `python -m`

## License

This project is released under the terms of the MIT License.
