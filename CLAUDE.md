# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SoupaWhisper is a push-to-talk voice dictation tool for Linux using faster-whisper. Users hold a hotkey to record audio, release to transcribe, and the text is automatically copied to clipboard and typed into the active input.

## Commands

```bash
# Install dependencies
uv sync

# Run the application
uv run python dictate.py

# Run with version info
uv run python dictate.py -v
```

## Architecture

This is a single-file Python application (`dictate.py`) with approximately 350 lines of code.

**Core Components:**

- `Dictation` class: Main controller that manages recording state, keyboard listener, and transcription workflow
- `load_config()`: Loads settings from `~/.config/soupawhisper/config.ini` with fallback defaults
- `find_keyboards()`: Discovers keyboard input devices via evdev
- Model loading happens in a background thread to avoid blocking startup

**Key Dependencies:**

- `faster-whisper`: Whisper model for speech-to-text transcription
- `evdev`: Direct Linux input device access for hotkey detection (requires user to be in `input` group)
- System tools: `pw-record` (PipeWire) or `arecord` (ALSA fallback), `notify-send` (notifications)
- Auto-typing: `wtype` (Wayland) or `xdotool` (X11)
- Clipboard: OSC52 escape sequences (primary), with fallback to `wl-copy` (Wayland) or `xclip` (X11)

**Flow:**

1. On startup, load config and spawn background thread to load Whisper model
2. Discover all keyboard input devices via evdev and monitor them with selectors
3. On hotkey press: start `pw-record` or `arecord` subprocess to capture audio to temp WAV file
4. On hotkey release: terminate recording, run transcription via faster-whisper, copy result to clipboard and optionally type it

## Configuration

User config lives at `~/.config/soupawhisper/config.ini`. See `config.example.ini` for the template. Key settings: model size, device (cpu/cuda), compute type, hotkey, auto_type, notifications.
