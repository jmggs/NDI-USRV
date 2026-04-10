"""
Image Source Generator.
Loads a JPG or PNG file, scales it to the output resolution, and
loops it at the target frame rate (static image; no animation).
"""

import numpy as np
import logging
from PIL import Image

log = logging.getLogger("image_src")

_PLACEHOLDER_COLORS = [
    (30, 30, 40),   # very dark blue-grey
]


def _placeholder(width, height, message="NO IMAGE LOADED"):
    """Simple dark slate with centred message."""
    img = Image.new("RGBA", (width, height), (20, 22, 28, 255))
    from PIL import ImageDraw, ImageFont
    draw = ImageDraw.Draw(img)

    # find a font
    font = None
    for path in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "C:/Windows/Fonts/arial.ttf",
    ]:
        try:
            from PIL import ImageFont
            font = ImageFont.truetype(path, max(24, height // 24))
            break
        except Exception:
            pass

    if font is None:
        font = ImageFont.load_default()

    bb = draw.textbbox((0, 0), message, font=font)
    tw = bb[2] - bb[0]
    th = bb[3] - bb[1]
    draw.text(((width - tw) // 2, (height - th) // 2),
              message, font=font, fill=(100, 100, 120, 255))

    arr = np.array(img, dtype=np.uint8)
    arr[:, :, :3] = arr[:, :, [2, 1, 0]]   # RGB→BGR
    return arr.tobytes()


class ImageSourceGenerator:

    def __init__(self, width=1920, height=1080, fps_n=25, fps_d=1,
                 sample_rate=48000, image_path: str = None, use_gpu=False):
        self.width = width
        self.height = height
        self.fps_n  = fps_n
        self.fps_d  = fps_d
        self.sample_rate = sample_rate
        self.use_gpu = use_gpu
        self.image_path = image_path

        self.spf = int(round(sample_rate * fps_d / fps_n))
        self._silence = np.zeros(self.spf * 2, dtype=np.float32).tobytes()

        self._frame_bytes: bytes = b""
        self._load(image_path)

    # ── Loading ───────────────────────────────────────────────────────────

    def _load(self, path: str | None):
        if not path:
            self._frame_bytes = _placeholder(self.width, self.height)
            return
        try:
            img = Image.open(path).convert("RGBA")
            img = img.resize((self.width, self.height), Image.LANCZOS)
            arr = np.array(img, dtype=np.uint8)
            arr[:, :, :3] = arr[:, :, [2, 1, 0]]   # RGB→BGR
            self._frame_bytes = arr.tobytes()
            log.info(f"Image loaded: {path} → {self.width}×{self.height}")
        except Exception as e:
            log.error(f"Failed to load image '{path}': {e}")
            self._frame_bytes = _placeholder(self.width, self.height,
                                              f"ERROR: {e}")

    def load_image(self, path: str):
        """Hot-swap image without recreating the generator."""
        self.image_path = path
        self._load(path)

    # ── Public interface ──────────────────────────────────────────────────

    def get_video_frame(self) -> bytes:
        return self._frame_bytes

    def get_audio_frame(self) -> bytes:
        return self._silence

    @property
    def audio_samples(self):
        return self.spf
