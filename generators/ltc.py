"""
SMPTE 12M LTC Generator.
Audio CH0: LTC biphase-mark  CH1: 1 kHz pilot −18 dBFS
"""
import math, time, datetime
import numpy as np
from PIL import Image, ImageDraw, ImageFont

_LTC_SYNC = 0x3FFD

def _font(size):
    for p in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/System/Library/Fonts/Menlo.ttc",
        "C:/Windows/Fonts/consola.ttf",
    ]:
        try: return ImageFont.truetype(p, size)
        except: pass
    return ImageFont.load_default()


def _build_ltc_word(h, m, s, f, fps=25, df=False):
    bits = [0] * 80
    def pack(val, start, count):
        for i in range(count): bits[start+i] = (val >> i) & 1
    pack(f % 10,   0, 4)
    pack(f // 10,  8, 2)
    bits[10] = 1 if df else 0
    pack(s % 10,  16, 4)
    pack(s // 10, 24, 3)
    pack(m % 10,  32, 4)
    pack(m // 10, 40, 3)
    pack(h % 10,  48, 4)
    pack(h // 10, 56, 2)
    for i in range(16): bits[64+i] = (_LTC_SYNC >> i) & 1
    return bits


def _biphase_mark(bits, spb):
    total = int(round(spb * len(bits)))
    out   = np.zeros(total, dtype=np.float32)
    level = 1.0
    pos   = 0
    for i, bit in enumerate(bits):
        end = int(round(spb * (i + 1)))
        n   = end - pos
        level = -level
        if bit == 0:
            out[pos:end] = level
        else:
            h = n // 2
            out[pos:pos+h] = level
            level = -level
            out[pos+h:end] = level
        pos = end
    return out


C_BG    = ( 13,  14,  16, 255)
C_GREEN = ( 57, 255, 110, 255)
C_DIM   = ( 18,  55,  28, 255)
C_AMBER = (200, 160,  20, 255)
C_GREY  = ( 75,  82,  92, 255)
C_WHITE = (210, 215, 220, 255)
C_DARK  = ( 26,  28,  32, 255)


class LTCGenerator:
    def __init__(self, width=1920, height=1080, fps_n=25, fps_d=1,
                 sample_rate=48000, drop_frame=False, label="", use_gpu=False, **kw):
        self.width  = width
        self.height = height
        self.fps_n  = fps_n
        self.fps_d  = fps_d
        self.sample_rate = sample_rate
        self.drop_frame  = drop_frame and fps_n in (30, 60)
        self.label  = label or "LTC OUTPUT"
        self.spf    = int(round(sample_rate * fps_d / fps_n))
        self._spb   = self.spf / 80.0

        now = datetime.datetime.now()
        self._origin_wall = time.monotonic()
        self._origin_tc   = (now.hour * 3600 + now.minute * 60 + now.second) * fps_n

        t = np.arange(self.spf, dtype=np.float32) / sample_rate
        self._pilot = (10**(-18/20) * np.sin(2*math.pi*1000*t)).astype(np.float32)

        H = height
        # fontes mais pequenas e equilibradas
        self._f_tc   = _font(max(60, H // 9))    # era H//7 — mais pequeno
        self._f_meta = _font(max(22, H // 30))
        self._f_aud  = _font(max(16, H // 42))
        self._f_lbl  = _font(max(16, H // 42))
        self._f_tiny = _font(max(13, H // 56))

    def _frame_num(self):
        return self._origin_tc + int((time.monotonic() - self._origin_wall) * self.fps_n)

    def _hmsf(self, fn):
        fps = self.fps_n
        return fn//(fps*3600)%24, fn//(fps*60)%60, fn//fps%60, fn%fps

    def get_audio_frame(self):
        h,m,s,f = self._hmsf(self._frame_num())
        bits = _build_ltc_word(h, m, s, f, self.fps_n, self.drop_frame)
        ltc  = np.resize(_biphase_mark(bits, self._spb), self.spf) * 0.9
        return np.concatenate([ltc, self._pilot]).tobytes()

    def get_video_frame(self):
        fn    = self._frame_num()
        h,m,s,f = self._hmsf(fn)
        W, H  = self.width, self.height

        img  = Image.new("RGBA", (W,H), C_BG)
        draw = ImageDraw.Draw(img)

        sep = ";" if self.drop_frame else ":"
        tc  = f"{h:02d}:{m:02d}:{s:02d}{sep}{f:02d}"

        # ── calcular tamanho do TC para centrar caixa ─────────────────
        bb   = draw.textbbox((0,0), tc, font=self._f_tc)
        tw,th = bb[2]-bb[0], bb[3]-bb[1]

        # caixa centrada vertical e horizontalmente
        pad  = int(H * 0.03)
        bx0  = (W - tw) // 2 - pad
        bx1  = (W + tw) // 2 + pad
        # caixa centrada verticalmente no ecrã
        cy   = H // 2
        by0  = cy - th//2 - pad
        by1  = cy + th//2 + pad

        # fundo + borda
        draw.rectangle([bx0, by0, bx1, by1], fill=C_DARK)
        draw.rectangle([bx0, by0, bx1, by1], outline=C_GREEN, width=2)

        # linha acento verde acima da caixa
        lw = bx1 - bx0
        draw.rectangle([bx0, by0-8, bx1, by0-5], fill=C_GREEN)

        # TC — exactamente centrado dentro da caixa (vertical e horizontal)
        tx = (W - tw) // 2
        ty = by0 + (by1 - by0 - th) // 5
        draw.text((tx+2, ty+2), tc, font=self._f_tc, fill=C_DIM)
        draw.text((tx,   ty),   tc, font=self._f_tc, fill=C_GREEN)

        # ── linha separadora abaixo da caixa ──────────────────────────
        sep_y = by1 + int(H*0.025)

        # meta (fps / ndf)
        df_str  = "DROP FRAME" if self.drop_frame else "NON DROP FRAME"
        meta    = f"{self.fps_n}/{self.fps_d} fps  •  SMPTE 12M  •  {df_str}"
        bb2     = draw.textbbox((0,0), meta, font=self._f_meta)
        draw.text(((W-(bb2[2]-bb2[0]))//2, sep_y),
                  meta, font=self._f_meta, fill=C_AMBER)

        # áudio info
        aud  = "CH 1: LTC SIGNAL  •  CH 2: 1 kHz PILOT  −18 dBFS  •  48 kHz"
        bb3  = draw.textbbox((0,0), aud, font=self._f_aud)
        draw.text(((W-(bb3[2]-bb3[0]))//2, sep_y + int(H*0.058)),
                  aud, font=self._f_aud, fill=C_GREY)

        # ── bit visualiser ────────────────────────────────────────────
        bits = _build_ltc_word(h,m,s,f, self.fps_n, self.drop_frame)
        bvx0 = int(W * 0.08)
        bvx1 = int(W * 0.92)
        bvy  = H - int(H * 0.16)
        bvh  = int(H * 0.07)
        bvw  = (bvx1 - bvx0) // 80
        for i,b in enumerate(bits):
            xi = bvx0 + i*bvw
            draw.rectangle([xi+1, bvy, xi+bvw-1, bvy+bvh],
                           fill=(C_GREEN if b else C_DARK))
        draw.text((bvx0, bvy+bvh+5), "bit 0", font=self._f_tiny, fill=C_GREY)
        draw.text((bvx1-28, bvy+bvh+5), "79",  font=self._f_tiny, fill=C_GREY)

        # ── label topo ────────────────────────────────────────────────
        lbl = self.label.upper()
        bb5 = draw.textbbox((0,0), lbl, font=self._f_lbl)
        draw.text(((W-(bb5[2]-bb5[0]))//2, int(H*0.04)),
                  lbl, font=self._f_lbl, fill=C_WHITE)

        arr = np.array(img, dtype=np.uint8)
        arr[:,:,:3] = arr[:,:,[2,1,0]]
        return arr.tobytes()

    @property
    def audio_samples(self): return self.spf
