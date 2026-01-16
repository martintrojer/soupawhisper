#!/usr/bin/env python3
"""
SoupaWhisper - Voice dictation tool using faster-whisper.
Hold the hotkey to record, release to transcribe and copy to clipboard.
"""

import argparse
import base64
import configparser
import logging
import selectors
import subprocess
import tempfile
import threading
import signal
import sys
import os
from pathlib import Path

import evdev
from evdev import ecodes
from faster_whisper import WhisperModel

__version__ = "0.1.0"

# Setup logging
logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s: %(message)s"
)
logger = logging.getLogger(__name__)

# Load configuration
CONFIG_PATH = Path.home() / ".config" / "soupawhisper" / "config.ini"


def load_config():
    config = configparser.ConfigParser()

    # Defaults
    defaults = {
        "model": "base.en",
        "device": "cpu",
        "compute_type": "int8",
        "key": "f12",
        "auto_type": "true",
        "notifications": "true",
    }

    if CONFIG_PATH.exists():
        config.read(CONFIG_PATH)

    return {
        "model": config.get("whisper", "model", fallback=defaults["model"]),
        "device": config.get("whisper", "device", fallback=defaults["device"]),
        "compute_type": config.get("whisper", "compute_type", fallback=defaults["compute_type"]),
        "key": config.get("hotkey", "key", fallback=defaults["key"]),
        "auto_type": config.getboolean("behavior", "auto_type", fallback=True),
        "notifications": config.getboolean("behavior", "notifications", fallback=True),
    }


CONFIG = load_config()


# Map key names to evdev key codes
KEY_MAP = {
    "f1": ecodes.KEY_F1, "f2": ecodes.KEY_F2, "f3": ecodes.KEY_F3, "f4": ecodes.KEY_F4,
    "f5": ecodes.KEY_F5, "f6": ecodes.KEY_F6, "f7": ecodes.KEY_F7, "f8": ecodes.KEY_F8,
    "f9": ecodes.KEY_F9, "f10": ecodes.KEY_F10, "f11": ecodes.KEY_F11, "f12": ecodes.KEY_F12,
    "scroll_lock": ecodes.KEY_SCROLLLOCK, "pause": ecodes.KEY_PAUSE,
    "insert": ecodes.KEY_INSERT, "home": ecodes.KEY_HOME, "end": ecodes.KEY_END,
    "pageup": ecodes.KEY_PAGEUP, "pagedown": ecodes.KEY_PAGEDOWN,
    "capslock": ecodes.KEY_CAPSLOCK, "numlock": ecodes.KEY_NUMLOCK,
}


def get_hotkey(key_name):
    """Map key name to evdev key code."""
    key_name = key_name.lower()
    if key_name in KEY_MAP:
        return KEY_MAP[key_name]
    elif len(key_name) == 1:
        # Single character keys (a-z, 0-9)
        key_attr = f"KEY_{key_name.upper()}"
        if hasattr(ecodes, key_attr):
            return getattr(ecodes, key_attr)
    print(f"Unknown key: {key_name}, defaulting to f12")
    return ecodes.KEY_F12


def get_key_name(keycode):
    """Get human-readable name for a key code."""
    for name, code in KEY_MAP.items():
        if code == keycode:
            return name.upper()
    # Try to get from ecodes
    name = ecodes.KEY.get(keycode, f"KEY_{keycode}")
    if isinstance(name, list):
        name = name[0]
    return name.replace("KEY_", "")


HOTKEY = get_hotkey(CONFIG["key"])
MODEL_SIZE = CONFIG["model"]
DEVICE = CONFIG["device"]
COMPUTE_TYPE = CONFIG["compute_type"]
AUTO_TYPE = CONFIG["auto_type"]
NOTIFICATIONS = CONFIG["notifications"]


def copy_to_clipboard(text):
    """Copy text to clipboard using OSC52, then fallback to wl-copy or xclip."""
    # Try OSC52 first (works in terminals that support it)
    encoded = base64.b64encode(text.encode()).decode()
    sys.stdout.write(f"\033]52;c;{encoded}\007")
    sys.stdout.flush()
    logger.debug("Copied to clipboard via OSC52")

    # Also copy via native clipboard tools for non-terminal contexts
    if os.environ.get("WAYLAND_DISPLAY"):
        # Wayland: use wl-copy
        if subprocess.run(["which", "wl-copy"], capture_output=True).returncode == 0:
            logger.debug("Running: wl-copy")
            process = subprocess.Popen(["wl-copy"], stdin=subprocess.PIPE)
            process.communicate(input=text.encode())
    elif os.environ.get("DISPLAY"):
        # X11: use xclip
        if subprocess.run(["which", "xclip"], capture_output=True).returncode == 0:
            logger.debug("Running: xclip -selection clipboard")
            process = subprocess.Popen(
                ["xclip", "-selection", "clipboard"],
                stdin=subprocess.PIPE
            )
            process.communicate(input=text.encode())


def type_text(text):
    """Type text into the active input field using wtype (Wayland) or xdotool (X11)."""
    if os.environ.get("WAYLAND_DISPLAY"):
        # Wayland: use wtype
        logger.debug("Running: wtype <text>")
        subprocess.run(["wtype", text])
    else:
        # X11: use xdotool
        logger.debug("Running: xdotool type --clearmodifiers <text>")
        subprocess.run(["xdotool", "type", "--clearmodifiers", text])


def get_audio_recorder():
    """Determine which audio recorder to use: pw-record (PipeWire) or arecord (ALSA)."""
    if subprocess.run(["which", "pw-record"], capture_output=True).returncode == 0:
        return "pipewire"
    elif subprocess.run(["which", "arecord"], capture_output=True).returncode == 0:
        return "alsa"
    return None


def get_record_command(output_file):
    """Get the command to record audio to the specified file."""
    recorder = get_audio_recorder()
    if recorder == "pipewire":
        return [
            "pw-record",
            "--format", "s16",      # 16-bit signed
            "--rate", "16000",      # Sample rate: 16kHz (what Whisper expects)
            "--channels", "1",      # Mono
            output_file
        ]
    else:
        # ALSA fallback
        return [
            "arecord",
            "-f", "S16_LE",         # Format: 16-bit little-endian
            "-r", "16000",          # Sample rate: 16kHz (what Whisper expects)
            "-c", "1",              # Mono
            "-t", "wav",
            output_file
        ]


def find_keyboards():
    """Find all keyboard input devices."""
    keyboards = []
    for path in evdev.list_devices():
        try:
            device = evdev.InputDevice(path)
            caps = device.capabilities()
            # Check if device has EV_KEY capability with typical keyboard keys
            if ecodes.EV_KEY in caps:
                keys = caps[ecodes.EV_KEY]
                # Check for common keyboard keys (KEY_A = 30, KEY_SPACE = 57)
                if ecodes.KEY_A in keys or ecodes.KEY_SPACE in keys:
                    keyboards.append(device)
                    logger.debug(f"Found keyboard: {device.path} - {device.name}")
        except (PermissionError, OSError) as e:
            logger.debug(f"Cannot access {path}: {e}")
    return keyboards


class Dictation:
    def __init__(self):
        self.recording = False
        self.record_process = None
        self.temp_file = None
        self.model = None
        self.model_loaded = threading.Event()
        self.model_error = None
        self.running = True
        self.keyboards = []
        self.selector = None

        # Load model in background
        print(f"Loading Whisper model ({MODEL_SIZE})...")
        threading.Thread(target=self._load_model, daemon=True).start()

    def _load_model(self):
        try:
            self.model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)
            self.model_loaded.set()
            hotkey_name = get_key_name(HOTKEY)
            print(f"Model loaded. Ready for dictation!")
            print(f"Hold [{hotkey_name}] to record, release to transcribe.")
            print("Press Ctrl+C to quit.")
        except Exception as e:
            self.model_error = str(e)
            self.model_loaded.set()
            print(f"Failed to load model: {e}")
            if "cudnn" in str(e).lower() or "cuda" in str(e).lower():
                print("Hint: Try setting device = cpu in your config, or install cuDNN (NVIDIA) / ROCm (AMD).")

    def notify(self, title, message, icon="dialog-information", timeout=2000):
        """Send a desktop notification."""
        if not NOTIFICATIONS:
            return
        subprocess.run(
            [
                "notify-send",
                "-a", "SoupaWhisper",
                "-i", icon,
                "-t", str(timeout),
                "-h", "string:x-canonical-private-synchronous:soupawhisper",
                title,
                message
            ],
            capture_output=True
        )

    def start_recording(self):
        if self.recording or self.model_error:
            return

        self.recording = True
        self.temp_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        self.temp_file.close()

        # Record using pw-record (PipeWire) or arecord (ALSA)
        record_cmd = get_record_command(self.temp_file.name)
        logger.debug(f"Running: {' '.join(record_cmd)}")
        self.record_process = subprocess.Popen(
            record_cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        print("Recording...")
        hotkey_name = get_key_name(HOTKEY)
        self.notify("Recording...", f"Release {hotkey_name} when done", "audio-input-microphone", 30000)

    def stop_recording(self):
        if not self.recording:
            return

        self.recording = False

        if self.record_process:
            self.record_process.terminate()
            self.record_process.wait()
            self.record_process = None

        print("Transcribing...")
        self.notify("Transcribing...", "Processing your speech", "emblem-synchronizing", 30000)

        # Wait for model if not loaded yet
        self.model_loaded.wait()

        if self.model_error:
            print(f"Cannot transcribe: model failed to load")
            self.notify("Error", "Model failed to load", "dialog-error", 3000)
            return

        # Transcribe
        try:
            segments, info = self.model.transcribe(
                self.temp_file.name,
                beam_size=5,
                vad_filter=True,
            )

            text = " ".join(segment.text.strip() for segment in segments)

            if text:
                # Copy to clipboard using OSC52
                copy_to_clipboard(text)

                # Type it into the active input field
                if AUTO_TYPE:
                    type_text(text)

                print(f"Copied: {text}")
                self.notify("Copied!", text[:100] + ("..." if len(text) > 100 else ""), "emblem-ok-symbolic", 3000)
            else:
                print("No speech detected")
                self.notify("No speech detected", "Try speaking louder", "dialog-warning", 2000)

        except Exception as e:
            print(f"Error: {e}")
            self.notify("Error", str(e)[:50], "dialog-error", 3000)
        finally:
            # Cleanup temp file
            if self.temp_file and os.path.exists(self.temp_file.name):
                os.unlink(self.temp_file.name)

    def on_key_event(self, event):
        """Handle a key event from evdev."""
        if event.code == HOTKEY:
            if event.value == 1:  # Key press
                self.start_recording()
            elif event.value == 0:  # Key release
                self.stop_recording()
            # value == 2 is key repeat, ignore it

    def stop(self):
        print("\nExiting...")
        self.running = False
        # Force immediate termination (evdev's select loop blocks signals)
        os.kill(os.getpid(), signal.SIGKILL)

    def run(self):
        self.keyboards = find_keyboards()
        if not self.keyboards:
            print("Error: No keyboards found!")
            print("Make sure you're in the 'input' group: sudo usermod -aG input $USER")
            print("Then log out and back in.")
            sys.exit(1)

        print(f"Monitoring {len(self.keyboards)} keyboard(s)...")
        for kb in self.keyboards:
            logger.debug(f"  {kb.name}")

        self.selector = selectors.DefaultSelector()
        for kb in self.keyboards:
            self.selector.register(kb, selectors.EVENT_READ)

        while self.running:
            for key, mask in self.selector.select(timeout=1):
                device = key.fileobj
                try:
                    for event in device.read():
                        if event.type == ecodes.EV_KEY:
                            self.on_key_event(event)
                except OSError:
                    # Device disconnected
                    logger.debug(f"Device disconnected: {device.name}")
                    self.selector.unregister(device)


def check_dependencies():
    """Check that required system commands are available."""
    missing = []

    # Check for audio recorder (pw-record or arecord)
    if get_audio_recorder() is None:
        missing.append(("pw-record or arecord", "pipewire or alsa-utils"))

    if AUTO_TYPE:
        if os.environ.get("WAYLAND_DISPLAY"):
            # Wayland: need wtype
            if subprocess.run(["which", "wtype"], capture_output=True).returncode != 0:
                missing.append(("wtype", "wtype"))
        else:
            # X11: need xdotool
            if subprocess.run(["which", "xdotool"], capture_output=True).returncode != 0:
                missing.append(("xdotool", "xdotool"))

    if missing:
        print("Missing dependencies:")
        for cmd, pkg in missing:
            print(f"  {cmd} - install with: sudo apt install {pkg}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="SoupaWhisper - Push-to-talk voice dictation"
    )
    parser.add_argument(
        "-v", "--version",
        action="version",
        version=f"SoupaWhisper {__version__}"
    )
    parser.add_argument(
        "-d", "--debug",
        action="store_true",
        help="Enable debug logging"
    )
    args = parser.parse_args()

    if args.debug:
        logger.setLevel(logging.DEBUG)

    print(f"SoupaWhisper v{__version__}")
    if CONFIG_PATH.exists():
        print(f"Config: {CONFIG_PATH}")
    else:
        print(f"Config: using defaults (create {CONFIG_PATH} to customize)")

    # Log environment detection
    display_server = "Wayland" if os.environ.get("WAYLAND_DISPLAY") else "X11" if os.environ.get("DISPLAY") else "Unknown"
    audio_backend = get_audio_recorder() or "None"
    logger.debug(f"Display server: {display_server}")
    logger.debug(f"Audio backend: {audio_backend}")
    logger.debug(f"Model: {MODEL_SIZE}, Device: {DEVICE}, Compute: {COMPUTE_TYPE}")
    logger.debug(f"Hotkey: {CONFIG['key']}, Auto-type: {AUTO_TYPE}, Notifications: {NOTIFICATIONS}")

    check_dependencies()

    dictation = Dictation()

    # Handle Ctrl+C gracefully
    def handle_sigint(sig, frame):
        dictation.stop()

    signal.signal(signal.SIGINT, handle_sigint)

    dictation.run()


if __name__ == "__main__":
    main()
