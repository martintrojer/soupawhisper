# SoupaWhisper

A simple push-to-talk voice dictation tool for Linux using faster-whisper. Hold a key to record, release to transcribe, and it automatically copies to clipboard and types into the active input.

## Requirements

- Python 3.10-3.13
- uv
- Linux with X11 or Wayland (ALSA audio)

## Supported Distros

- Ubuntu / Pop!_OS / Debian (apt)
- Fedora (dnf)
- Arch Linux (pacman)
- openSUSE (zypper)

## Installation

```bash
git clone https://github.com/ksred/soupawhisper.git
cd soupawhisper
chmod +x install.sh
./install.sh
```

The installer will:
1. Detect your package manager
2. Install system dependencies
3. Install Python dependencies via uv
4. Set up the config file
5. Optionally install as a systemd service

### Manual Installation

```bash
# Ubuntu/Debian
sudo apt install alsa-utils libnotify-bin xdotool xclip wtype wl-clipboard

# Fedora
sudo dnf install alsa-utils libnotify xdotool xclip wtype wl-clipboard

# Arch
sudo pacman -S alsa-utils libnotify xdotool xclip wtype wl-clipboard

# Then install Python deps
uv sync
```

Note: xdotool and xclip are for X11, wtype and wl-clipboard are for Wayland. Install all for maximum compatibility, or just the ones for your display server.

### GPU Support (Optional)

By default, SoupaWhisper runs on CPU which works well on modern Intel/AMD processors. GPU acceleration is optional and requires additional setup.

#### NVIDIA GPU (CUDA)

Install cuDNN 9:

```bash
wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-keyring_1.1-1_all.deb
sudo dpkg -i cuda-keyring_1.1-1_all.deb
sudo apt update
sudo apt install libcudnn9-cuda-12
```

Then edit `~/.config/soupawhisper/config.ini`:
```ini
device = cuda
compute_type = float16
```

#### AMD GPU (ROCm)

Install ROCm and the ROCm-compatible CTranslate2:

```bash
# Install ROCm (see https://rocm.docs.amd.com for your distro)
# Then install ctranslate2 with ROCm support
pip install ctranslate2 --extra-index-url https://download.pytorch.org/whl/rocm6.0
```

Then edit `~/.config/soupawhisper/config.ini`:
```ini
device = cuda
compute_type = float16
```

Note: ROCm uses the same `device = cuda` setting as it provides CUDA compatibility.

## Usage

```bash
uv run python dictate.py
```

- Hold **F12** to record
- Release to transcribe → copies to clipboard and types into active input
- Press **Ctrl+C** to quit (when running manually)

## Run as a systemd Service

The installer can set this up automatically. If you skipped it, run:

```bash
./install.sh  # Select 'y' when prompted for systemd
```

### Service Commands

```bash
systemctl --user start soupawhisper     # Start
systemctl --user stop soupawhisper      # Stop
systemctl --user restart soupawhisper   # Restart
systemctl --user status soupawhisper    # Status
journalctl --user -u soupawhisper -f    # View logs
```

## Configuration

Edit `~/.config/soupawhisper/config.ini`:

```ini
[whisper]
# Model size: tiny.en, base.en, small.en, medium.en, large-v3
model = base.en

# Device: cpu or cuda
# cpu - Works on all systems, optimized for Intel/AMD processors
# cuda - NVIDIA GPU (requires cuDNN) or AMD GPU (requires ROCm)
device = cpu

# Compute type: int8 for CPU, float16 for GPU
compute_type = int8

[hotkey]
# Key to hold for recording: f12, scroll_lock, pause, etc.
key = f12

[behavior]
# Type text into active input field
auto_type = true

# Show desktop notification
notifications = true
```

Create the config directory and file if it doesn't exist:
```bash
mkdir -p ~/.config/soupawhisper
cp /path/to/soupawhisper/config.example.ini ~/.config/soupawhisper/config.ini
```

## Troubleshooting

**No audio recording:**
```bash
# Check your input device
arecord -l

# Test recording
arecord -d 3 test.wav && aplay test.wav
```

**Permission issues with keyboard (required for Wayland):**
```bash
sudo usermod -aG input $USER
# Then log out and back in
```
On Wayland, pynput requires access to /dev/input devices. Adding your user to the `input` group is required.

**GPU errors (cuDNN/ROCm):**
```
Unable to load any of {libcudnn_ops.so.9...}
```
For NVIDIA: Install cuDNN 9 (see GPU Support section above).
For AMD: Ensure ROCm is properly installed.
Or switch to CPU mode (`device = cpu` in config).

## Model Sizes

| Model | Size | Speed | Accuracy |
|-------|------|-------|----------|
| tiny.en | ~75MB | Fastest | Basic |
| base.en | ~150MB | Fast | Good |
| small.en | ~500MB | Medium | Better |
| medium.en | ~1.5GB | Slower | Great |
| large-v3 | ~3GB | Slowest | Best |

For dictation, `base.en` or `small.en` is usually the sweet spot.
