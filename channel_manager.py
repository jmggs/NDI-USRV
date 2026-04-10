"""
Channel Manager.

Each Channel runs in its own daemon thread:
  - Creates / recreates its generator based on config
  - Sends video + audio via NDI at the target frame rate
  - Reports live stats (actual FPS, frame drops, etc.)
"""

import threading
import time
import logging
import os
import json
from dataclasses import dataclass, field, asdict
from typing import Optional

from ndi_wrapper import NDISender
from generators import (
    ColorbarsGenerator, ClockGenerator,
    LTCGenerator, ImageSourceGenerator,
)

log = logging.getLogger("channel_manager")

VALID_SOURCES    = ("colorbars", "clock", "ltc", "image")
VALID_RESOLUTIONS = {
    "720p":   (1280,  720),
    "1080p":  (1920, 1080),
    "1080i":  (1920, 1080),   # interlaced flag set separately
    "UHD":    (3840, 2160),
    "4K":     (4096, 2160),
    "576p":   ( 720,  576),
    "480p":   ( 720,  480),
}
VALID_FPS = {
    "23.98": (24000, 1001),
    "24":    (24, 1),
    "25":    (25, 1),
    "29.97": (30000, 1001),
    "30":    (30, 1),
    "50":    (50, 1),
    "59.94": (60000, 1001),
    "60":    (60, 1),
}

CONFIG_PATH = os.environ.get("NDI_CONFIG", "channels.json")


# ─── Channel config ───────────────────────────────────────────────────────────

@dataclass
class ChannelConfig:
    id:         int
    name:       str       = ""
    enabled:    bool      = True
    source:     str       = "colorbars"
    resolution: str       = "1080p"
    fps:        str       = "25"
    image_path: str       = ""
    label:      str       = ""
    # GPU
    use_gpu:    bool      = False

    def __post_init__(self):
        if not self.name:
            self.name = f"NDI Channel {self.id + 1}"
        if not self.label:
            self.label = self.name


@dataclass
class ChannelStats:
    running:    bool  = False
    actual_fps: float = 0.0
    frame_count: int  = 0
    drop_count:  int  = 0
    error:      str   = ""


# ─── Single channel ───────────────────────────────────────────────────────────

class Channel:
    def __init__(self, cfg: ChannelConfig):
        self.cfg   = cfg
        self.stats = ChannelStats()
        self._thread: Optional[threading.Thread] = None
        self._stop  = threading.Event()
        self._lock  = threading.Lock()
        self._dirty = threading.Event()   # config changed → recreate generator

    # ── Lifecycle ─────────────────────────────────────────────────────────

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, daemon=True,
            name=f"ch-{self.cfg.id}"
        )
        self._thread.start()
        log.info(f"Channel {self.cfg.id} started")

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        self.stats.running = False
        log.info(f"Channel {self.cfg.id} stopped")

    def update_config(self, new_cfg: dict):
        with self._lock:
            for k, v in new_cfg.items():
                if hasattr(self.cfg, k) and k != "id":
                    setattr(self.cfg, k, v)
        self._dirty.set()

    # ── Worker thread ─────────────────────────────────────────────────────

    def _run(self):
        self.stats.running = True
        self.stats.error   = ""

        while not self._stop.is_set():
            if not self.cfg.enabled:
                time.sleep(0.2)
                continue

            sender = gen = None
            try:
                sender, gen = self._create_resources()
                self._send_loop(sender, gen)
            except Exception as e:
                self.stats.error = str(e)
                log.error(f"Channel {self.cfg.id} error: {e}", exc_info=True)
                time.sleep(2)   # back-off before retry
            finally:
                if sender:
                    sender.destroy()

        self.stats.running = False

    def _create_resources(self):
        with self._lock:
            cfg = self.cfg

        w, h   = VALID_RESOLUTIONS.get(cfg.resolution, (1920, 1080))
        fps_n, fps_d = VALID_FPS.get(cfg.fps, (25, 1))
        gpu    = cfg.use_gpu

        sender = NDISender(cfg.name)

        if cfg.source == "colorbars":
            gen = ColorbarsGenerator(w, h, fps_n, fps_d, use_gpu=gpu)
        elif cfg.source == "clock":
            gen = ClockGenerator(w, h, fps_n, fps_d, label=cfg.label, use_gpu=gpu)
        elif cfg.source == "ltc":
            gen = LTCGenerator(w, h, fps_n, fps_d, label=cfg.label, use_gpu=gpu)
        elif cfg.source == "image":
            gen = ImageSourceGenerator(w, h, fps_n, fps_d,
                                       image_path=cfg.image_path or None,
                                       use_gpu=gpu)
        else:
            raise ValueError(f"Unknown source: {cfg.source}")

        self._dirty.clear()
        log.info(f"Channel {cfg.id}: {cfg.source} @ {w}×{h} {fps_n}/{fps_d}fps")
        return sender, gen

    def _send_loop(self, sender: NDISender, gen):
        with self._lock:
            cfg = self.cfg

        w, h   = VALID_RESOLUTIONS.get(cfg.resolution, (1920, 1080))
        fps_n, fps_d = VALID_FPS.get(cfg.fps, (25, 1))
        frame_dur = fps_d / fps_n

        fps_window = []
        last_fps_calc = time.monotonic()
        t_next = time.monotonic()

        while not self._stop.is_set() and not self._dirty.is_set():
            if not self.cfg.enabled:
                time.sleep(0.1)
                continue

            t0 = time.monotonic()

            try:
                video = gen.get_video_frame()
                audio = gen.get_audio_frame()

                sender.send_video(video, w, h, fps_n, fps_d)
                sender.send_audio(audio, 2, gen.audio_samples)

                self.stats.frame_count = sender.frame_count
            except Exception as e:
                self.stats.drop_count += 1
                log.warning(f"Ch{cfg.id} frame drop: {e}")

            # ── FPS accounting ────────────────────────────────────────────
            now = time.monotonic()
            fps_window.append(now)
            # keep last 2 seconds
            cutoff = now - 2.0
            fps_window = [t for t in fps_window if t > cutoff]
            if now - last_fps_calc > 0.5:
                self.stats.actual_fps = len(fps_window) / 2.0
                last_fps_calc = now

            # ── Pacing ───────────────────────────────────────────────────
            t_next += frame_dur
            sleep = t_next - time.monotonic()
            if sleep > 0:
                time.sleep(sleep)
            else:
                # We're late; skip ahead to avoid spiral
                t_next = time.monotonic()


# ─── Manager ─────────────────────────────────────────────────────────────────

class ChannelManager:
    NUM_CHANNELS = 4

    def __init__(self):
        self._channels = [
            Channel(ChannelConfig(id=i)) for i in range(self.NUM_CHANNELS)
        ]
        self._load_config()

    # ── Config persistence ────────────────────────────────────────────────

    def _load_config(self):
        if not os.path.exists(CONFIG_PATH):
            return
        try:
            with open(CONFIG_PATH) as f:
                saved = json.load(f)
            for ch_data in saved.get("channels", []):
                idx = ch_data.get("id")
                if idx is not None and 0 <= idx < self.NUM_CHANNELS:
                    cfg = self._channels[idx].cfg
                    for k, v in ch_data.items():
                        if hasattr(cfg, k):
                            setattr(cfg, k, v)
            log.info(f"Config loaded from {CONFIG_PATH}")
        except Exception as e:
            log.warning(f"Config load failed: {e}")

    def save_config(self):
        data = {"channels": [asdict(ch.cfg) for ch in self._channels]}
        try:
            with open(CONFIG_PATH, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            log.error(f"Config save failed: {e}")

    # ── Public API ────────────────────────────────────────────────────────

    def start_all(self):
        for ch in self._channels:
            ch.start()

    def stop_all(self):
        for ch in self._channels:
            ch.stop()

    def get_channel(self, idx: int) -> Channel:
        if not 0 <= idx < self.NUM_CHANNELS:
            raise IndexError(f"Channel index {idx} out of range")
        return self._channels[idx]

    def get_all_status(self) -> list:
        out = []
        for ch in self._channels:
            out.append({
                "id":         ch.cfg.id,
                "name":       ch.cfg.name,
                "enabled":    ch.cfg.enabled,
                "source":     ch.cfg.source,
                "resolution": ch.cfg.resolution,
                "fps":        ch.cfg.fps,
                "label":      ch.cfg.label,
                "image_path": ch.cfg.image_path,
                "use_gpu":    ch.cfg.use_gpu,
                # live stats
                "running":    ch.stats.running,
                "actual_fps": round(ch.stats.actual_fps, 2),
                "frame_count": ch.stats.frame_count,
                "drop_count": ch.stats.drop_count,
                "error":      ch.stats.error,
            })
        return out

    def update_channel(self, idx: int, data: dict):
        ch = self.get_channel(idx)
        ch.update_config(data)
        self.save_config()

    def restart_channel(self, idx: int):
        ch = self.get_channel(idx)
        ch.stop()
        time.sleep(0.3)
        ch.start()

    @staticmethod
    def get_options():
        return {
            "sources":     list(VALID_SOURCES),
            "resolutions": list(VALID_RESOLUTIONS.keys()),
            "fps":         list(VALID_FPS.keys()),
        }
