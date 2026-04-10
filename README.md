# NDI Signal Generator

Professional 4-channel NDI test signal generator with web-based management.
Runs as a headless service on **Linux**, **macOS**, and **Windows**.

---

## Features

| Channel Source | Description |
|---|---|
| 🟧 **EBU Colorbars** | R 75 standard (75/0/75/0) with 1 kHz −18 dBFS tone, PLUGE |
| 🕐 **Broadcast Clock** | Smooth-sweep analog + digital, configurable label |
| 🎞 **LTC Timecode** | SMPTE 12M biphase-mark encoded on audio ch1, 1 kHz pilot on ch2, visual TC display |
| 🖼 **Image** | Upload any JPG/PNG; scaled to output resolution |

**4 independent NDI outputs** — each with its own resolution, frame rate, label, and source.  
**Web UI** — full management from any browser, real-time FPS & drop stats via WebSocket.  
**CPU or NVIDIA GPU** — selectable per channel.  
**Endless service** — systemd / LaunchDaemon / Windows Service support.

---

## Requirements

- Python 3.10+
- [NDI SDK](https://ndi.video/for-developers/ndi-sdk/download/) (free, requires registration)

### Optional (GPU)
- NVIDIA GPU with CUDA 11+
- `cupy-cuda12x` Python package

---

## Quick Start

### Linux / macOS

```bash
# 1. Install NDI SDK from ndi.video

# 2. Clone / extract the project
cd ndi-generator

# 3. Install
sudo bash install.sh

# 4. Start
sudo systemctl start ndi-generator    # Linux
# or
sudo launchctl start com.ndi-generator  # macOS

# 5. Open browser
open http://localhost:8080
```

### Windows

```powershell
# Run as Administrator
Set-ExecutionPolicy Bypass -Scope Process
.\install.ps1
```

### Development (no NDI SDK)

```bash
pip install -r requirements.txt
NDI_MOCK=1 python main.py --port 8080
```

---

## Command Line Options

```
python main.py [options]

  --host     Bind address   (default: 0.0.0.0)
  --port     Web port        (default: 8080)
  --mock-ndi No NDI SDK, console-only output
  --gpu      Enable GPU for all channels by default
  --log-level DEBUG|INFO|WARNING|ERROR
```

Environment variables:
```
NDI_MOCK=1          Force mock mode
NDI_CONFIG=path     Config file path (default: channels.json)
NDI_PORT=8080       Web server port
NDI_HOST=0.0.0.0   Bind address
```

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/channels` | All channel configs + live stats |
| `GET` | `/api/channels/{id}` | Single channel |
| `PATCH` | `/api/channels/{id}` | Update config (partial) |
| `POST` | `/api/channels/{id}/restart` | Restart channel |
| `POST` | `/api/channels/{id}/upload` | Upload image (multipart) |
| `GET` | `/api/options` | Available sources, resolutions, fps |
| `GET` | `/api/system` | System info (GPU detection) |
| `WS` | `/ws` | Live stats push (JSON array, 1 Hz) |

### PATCH body example
```json
{
  "source": "colorbars",
  "resolution": "1080p",
  "fps": "25",
  "enabled": true,
  "label": "STUDIO A",
  "use_gpu": false
}
```

---

## GPU Acceleration

When `use_gpu: true` is set on a channel:
- Install `cupy` matching your CUDA version:  
  `pip install cupy-cuda12x`
- Frame generation arrays are computed on GPU
- Significant benefit at UHD/4K resolutions

---

## Supported Resolutions

| Key | Size |
|---|---|
| `480p` | 720×480 |
| `576p` | 720×576 |
| `720p` | 1280×720 |
| `1080p` | 1920×1080 |
| `1080i` | 1920×1080 (interlaced) |
| `UHD` | 3840×2160 |
| `4K` | 4096×2160 |

## Supported Frame Rates

23.98, 24, 25, 29.97, 30, 50, 59.94, 60

---

## LTC Technical Details

- SMPTE 12M biphase-mark code
- 80 bits per frame, LSB first
- Drop-frame support for 29.97/59.94 fps
- Audio: float32 planar (FLTP), 48 kHz, stereo
  - CH1: LTC signal (~0.9 FS)
  - CH2: 1 kHz pilot tone (−18 dBFS)

---

## File Structure

```
ndi-generator/
├── main.py              Entry point
├── ndi_wrapper.py       NDI SDK abstraction (+ mock fallback)
├── channel_manager.py   4-channel thread management + config persistence
├── web_server.py        FastAPI REST + WebSocket server
├── generators/
│   ├── colorbars.py     EBU R 75 colour bars + 1 kHz tone
│   ├── clock.py         Broadcast clock (analog + digital)
│   ├── ltc.py           SMPTE 12M LTC encoder
│   └── image_src.py     JPG/PNG image source
├── static/
│   └── index.html       Web management UI
├── channels.json        Auto-saved channel configuration
├── uploads/             Uploaded images
├── requirements.txt
├── install.sh           Linux/macOS installer
├── install.ps1          Windows installer
└── ndi-generator.service  systemd unit
```

---

## License

MIT — use freely in production.  
NDI® is a registered trademark of Vizrt NDI AB.
