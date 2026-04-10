"""
NDI Wrapper — carrega libndi.so.6 via ctypes directamente.
Não requer ndi-python nem compilação.
Fallback automático para mock se a lib não estiver disponível.
"""

import ctypes
import logging
import os
import time

log = logging.getLogger("ndi_wrapper")

MOCK_MODE = os.environ.get("NDI_MOCK", "0") == "1"

# ── C structs ─────────────────────────────────────────────────────────────────

class NDIlib_send_create_t(ctypes.Structure):
    _fields_ = [
        ("p_ndi_name",  ctypes.c_char_p),
        ("p_groups",    ctypes.c_char_p),
        ("clock_video", ctypes.c_bool),
        ("clock_audio", ctypes.c_bool),
    ]

class NDIlib_video_frame_v2_t(ctypes.Structure):
    _fields_ = [
        ("xres",                ctypes.c_int),
        ("yres",                ctypes.c_int),
        ("FourCC",              ctypes.c_int),
        ("frame_rate_N",        ctypes.c_int),
        ("frame_rate_D",        ctypes.c_int),
        ("picture_aspect_ratio",ctypes.c_float),
        ("frame_format_type",   ctypes.c_int),
        ("timecode",            ctypes.c_int64),
        ("p_data",              ctypes.c_char_p),
        ("line_stride_or_size", ctypes.c_int),
        ("p_metadata",          ctypes.c_char_p),
        ("timestamp",           ctypes.c_int64),
    ]

class NDIlib_audio_frame_v3_t(ctypes.Structure):
    _fields_ = [
        ("sample_rate",     ctypes.c_int),
        ("no_channels",     ctypes.c_int),
        ("no_samples",      ctypes.c_int),
        ("timecode",        ctypes.c_int64),
        ("FourCC",          ctypes.c_int),
        ("p_data",          ctypes.c_char_p),
        ("channel_stride_or_data_size", ctypes.c_int),
        ("p_metadata",      ctypes.c_char_p),
        ("timestamp",       ctypes.c_int64),
    ]

FOURCC_VIDEO_BGRA = 0x41524742
FOURCC_AUDIO_FLTP = 0x50544c46

# ── Load library ──────────────────────────────────────────────────────────────

_lib = None

def _try_load():
    global _lib
    if MOCK_MODE:
        log.info("NDI_MOCK=1 — mock mode activo")
        return

    candidates = [
        "libndi.so.6",
        "libndi.so",
        "/usr/local/lib/libndi.so.6",
        "/usr/local/lib/libndi.so",
        "/Library/NDI SDK for Apple/lib/macOS/libndi.dylib",
        r"C:\Program Files\NDI\NDI 6 SDK\Bin\x64\Processing.NDI.Lib.x64.dll",
    ]

    for name in candidates:
        try:
            lib = ctypes.CDLL(name)

            lib.NDIlib_initialize.restype  = ctypes.c_bool
            lib.NDIlib_initialize.argtypes = []
            lib.NDIlib_destroy.restype  = None
            lib.NDIlib_destroy.argtypes = []
            lib.NDIlib_send_create.restype  = ctypes.c_void_p
            lib.NDIlib_send_create.argtypes = [ctypes.POINTER(NDIlib_send_create_t)]
            lib.NDIlib_send_destroy.restype  = None
            lib.NDIlib_send_destroy.argtypes = [ctypes.c_void_p]
            lib.NDIlib_send_send_video_v2.restype  = None
            lib.NDIlib_send_send_video_v2.argtypes = [
                ctypes.c_void_p, ctypes.POINTER(NDIlib_video_frame_v2_t)]
            lib.NDIlib_send_send_audio_v3.restype  = None
            lib.NDIlib_send_send_audio_v3.argtypes = [
                ctypes.c_void_p, ctypes.POINTER(NDIlib_audio_frame_v3_t)]

            if not lib.NDIlib_initialize():
                raise RuntimeError("NDIlib_initialize() retornou false")

            _lib = lib
            log.info(f"✅  NDI SDK carregado: {name}")
            return

        except Exception as e:
            log.debug(f"  tentativa '{name}': {e}")

    log.warning("⚠️  NDI SDK não encontrado — modo MOCK activo")


# ── Sender ────────────────────────────────────────────────────────────────────

class NDISender:

    def __init__(self, name: str, clock_video: bool = True):
        self.name = name
        self._handle = None
        self._mock = MOCK_MODE or (_lib is None)
        self._frame_count = 0
        self._last_log = 0.0
        self._buf = None
        self._abuf = None

        if not self._mock:
            try:
                sc = NDIlib_send_create_t()
                sc.p_ndi_name  = name.encode()
                sc.p_groups    = None
                sc.clock_video = clock_video
                sc.clock_audio = False
                self._handle = _lib.NDIlib_send_create(ctypes.byref(sc))
                if not self._handle:
                    raise RuntimeError("NDIlib_send_create retornou NULL")
                log.info(f"NDI sender criado: '{name}'")
            except Exception as e:
                log.error(f"Falha ao criar sender '{name}': {e}")
                self._mock = True

    def send_video(self, frame_bgra: bytes, width: int, height: int,
                   fps_n: int = 25, fps_d: int = 1):
        if self._mock:
            self._mock_log("video", width, height)
            self._frame_count += 1
            return

        self._buf = ctypes.create_string_buffer(frame_bgra, len(frame_bgra))
        vf = NDIlib_video_frame_v2_t()
        vf.xres = width
        vf.yres = height
        vf.FourCC = FOURCC_VIDEO_BGRA
        vf.frame_rate_N = fps_n
        vf.frame_rate_D = fps_d
        vf.picture_aspect_ratio = width / height
        vf.frame_format_type = 1
        vf.timecode = 0x8000000000000000
        vf.p_data = ctypes.cast(self._buf, ctypes.c_char_p)
        vf.line_stride_or_size = width * 4
        vf.p_metadata = None
        vf.timestamp = 0
        _lib.NDIlib_send_send_video_v2(self._handle, ctypes.byref(vf))
        self._frame_count += 1

    def send_audio(self, samples_f32_planar: bytes, num_channels: int,
                   num_samples: int, sample_rate: int = 48000):
        if self._mock:
            return

        self._abuf = ctypes.create_string_buffer(samples_f32_planar, len(samples_f32_planar))
        af = NDIlib_audio_frame_v3_t()
        af.sample_rate = sample_rate
        af.no_channels = num_channels
        af.no_samples = num_samples
        af.timecode = 0x8000000000000000
        af.FourCC = FOURCC_AUDIO_FLTP
        af.p_data = ctypes.cast(self._abuf, ctypes.c_char_p)
        af.channel_stride_or_data_size = num_samples * 4
        af.p_metadata = None
        af.timestamp = 0
        _lib.NDIlib_send_send_audio_v3(self._handle, ctypes.byref(af))

    def destroy(self):
        if self._handle and not self._mock:
            try:
                _lib.NDIlib_send_destroy(self._handle)
            except Exception:
                pass
        self._handle = None

    @property
    def frame_count(self):
        return self._frame_count

    def _mock_log(self, kind, *args):
        now = time.time()
        if now - self._last_log > 5:
            log.debug(f"[MOCK] '{self.name}' → {kind} {args}")
            self._last_log = now


def initialize():
    _try_load()

def shutdown():
    if _lib:
        try:
            _lib.NDIlib_destroy()
        except Exception:
            pass
