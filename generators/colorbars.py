"""
EBU R 75 Colour Bars — 75/0/75/0 com tom 1 kHz a −18 dBFS em stereo.
Frame pré-computado; audio gerado uma vez por resolução/fps.
"""

import numpy as np

_BARS_TOP = [
    (191, 191, 191),   # White 75%
    (191, 191,   0),   # Yellow
    (  0, 191, 191),   # Cyan
    (  0, 191,   0),   # Green
    (191,   0, 191),   # Magenta
    (191,   0,   0),   # Red
    (  0,   0, 191),   # Blue
]
_BARS_BOT = [
    (  0,   0, 191),
    ( 19,  19,  19),
    (191,   0, 191),
    ( 19,  19,  19),
    (  0, 191, 191),
    ( 19,  19,  19),
    (191, 191, 191),
]
_PLUGE = [
    ( 19,   0,  63),
    (235, 235, 235),
    ( 83,   0,  83),
    (  0,   0,   0),
    (  7,   7,   7),
    (  0,   0,   0),
    ( 22,  22,  22),
]


def _build_frame(width, height):
    frame = np.zeros((height, width, 4), dtype=np.uint8)
    frame[:, :, 3] = 255
    n = 7
    top_h = int(height * 0.67)
    mid_h = int(height * 0.90)

    for i, (r, g, b) in enumerate(_BARS_TOP):
        x0, x1 = width * i // n, width * (i + 1) // n
        frame[:top_h, x0:x1, 0] = b
        frame[:top_h, x0:x1, 1] = g
        frame[:top_h, x0:x1, 2] = r

    for i, (r, g, b) in enumerate(_BARS_BOT):
        x0, x1 = width * i // n, width * (i + 1) // n
        frame[top_h:mid_h, x0:x1, 0] = b
        frame[top_h:mid_h, x0:x1, 1] = g
        frame[top_h:mid_h, x0:x1, 2] = r

    for i, (r, g, b) in enumerate(_PLUGE):
        x0, x1 = width * i // n, width * (i + 1) // n
        frame[mid_h:, x0:x1, 0] = b
        frame[mid_h:, x0:x1, 1] = g
        frame[mid_h:, x0:x1, 2] = r

    return frame


def _build_tone(sample_rate, samples, freq=1000.0, db=-18.0):
    amplitude = 10 ** (db / 20.0)
    t = np.arange(samples, dtype=np.float32) / sample_rate
    return (amplitude * np.sin(2 * np.pi * freq * t)).astype(np.float32)


class ColorbarsGenerator:
    def __init__(self, width=1920, height=1080, fps_n=25, fps_d=1,
                 sample_rate=48000, use_gpu=False):
        self.width = width
        self.height = height
        self.fps_n = fps_n
        self.fps_d = fps_d
        self.sample_rate = sample_rate
        self.use_gpu = use_gpu
        self.spf = int(round(sample_rate * fps_d / fps_n))

        frame = _build_frame(width, height)
        self._frame_bytes = frame.tobytes()

        tone = _build_tone(sample_rate, self.spf)
        # Stereo planar: CH0 (L) | CH1 (R)
        self._audio = np.concatenate([tone, tone]).tobytes()

    def get_video_frame(self): return self._frame_bytes
    def get_audio_frame(self): return self._audio

    @property
    def audio_samples(self): return self.spf
