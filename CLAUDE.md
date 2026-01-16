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

This is a single-file Python application (`dictate.py`) with approximately 270 lines of code.

**Core Components:**

- `Dictation` class: Main controller that manages recording state, keyboard listener, and transcription workflow
- `load_config()`: Loads settings from `~/.config/soupawhisper/config.ini` with fallback defaults
- Model loading happens in a background thread to avoid blocking startup

**Key Dependencies:**

- `faster-whisper`: Whisper model for speech-to-text transcription
- `pynput`: Global keyboard listener for hotkey detection
- System tools: `arecord` (ALSA recording), `xclip` (clipboard), `xdotool` (auto-typing), `notify-send` (notifications)

**Flow:**

1. On startup, load config and spawn background thread to load Whisper model
2. Keyboard listener waits for hotkey press/release events
3. On press: start `arecord` subprocess to capture audio to temp WAV file
4. On release: terminate recording, run transcription via faster-whisper, copy result to clipboard and optionally type it

## Configuration

User config lives at `~/.config/soupawhisper/config.ini`. See `config.example.ini` for the template. Key settings: model size, device (cpu/cuda), compute type, hotkey, auto_type, notifications.
