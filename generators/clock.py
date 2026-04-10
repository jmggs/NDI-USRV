"""
Broadcast Clock — tempo acima da linha verde, tudo centrado verticalmente.
"""
import math, datetime
import numpy as np
from PIL import Image, ImageDraw, ImageFont

C_BG      = ( 15,  15,  15, 255)
C_FACE    = ( 20,  20,  20, 255)
C_RING    = ( 32,  34,  38, 255)
C_GREEN   = ( 57, 255, 110, 255)
C_GREEN_D = ( 18,  60,  30, 255)
C_WHITE   = (210, 215, 220, 255)
C_GREY    = ( 75,  82,  92, 255)
C_TICK_MJ = (120, 128, 138, 255)
C_TICK_MN = ( 38,  42,  48, 255)
C_RED     = (255,  50,  50, 255)


def _font(size):
    for p in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf",
        "/usr/share/fonts/truetype/ubuntu/UbuntuMono-B.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/System/Library/Fonts/Menlo.ttc",
        "C:/Windows/Fonts/consola.ttf",
    ]:
        try: return ImageFont.truetype(p, size)
        except: pass
    return ImageFont.load_default()


class ClockGenerator:
    def __init__(self, width=1920, height=1080, fps_n=25, fps_d=1,
                 sample_rate=48000, label="", use_gpu=False, **kw):
        self.width  = width
        self.height = height
        self.fps_n  = fps_n
        self.fps_d  = fps_d
        self.sample_rate = sample_rate
        self.label  = label or "NDI CLOCK"
        self.spf    = int(round(sample_rate * fps_d / fps_n))
        self._silence = np.zeros(self.spf * 2, dtype=np.float32).tobytes()

        H = height
        self._f_time  = _font(max(52, H // 10))   # hora
        self._f_frame = _font(max(36, H // 18))   # frames — maior
        self._f_date  = _font(max(28, H // 26))   # data — maior
        self._f_label = _font(max(24, H // 30))   # label — maior
        self._f_small = _font(max(18, H // 42))   # fps

    def _polar(self, cx, cy, r, deg):
        a = math.radians(deg - 90)
        return cx + r * math.cos(a), cy + r * math.sin(a)

    def _draw_face(self, draw, cx, cy, R):
        draw.ellipse([cx-R-14, cy-R-14, cx+R+14, cy+R+14], fill=C_RING)
        draw.ellipse([cx-R, cy-R, cx+R, cy+R], fill=C_FACE)
        draw.ellipse([cx-R, cy-R, cx+R, cy+R], outline=C_TICK_MJ, width=2)

    def _draw_ticks(self, draw, cx, cy, R):
        for i in range(60):
            major = (i % 5 == 0)
            r_out = R - 4
            r_in  = R - (20 if major else 8)
            x1,y1 = self._polar(cx, cy, r_in,  i*6)
            x2,y2 = self._polar(cx, cy, r_out, i*6)
            draw.line([x1,y1,x2,y2],
                      fill=(C_TICK_MJ if major else C_TICK_MN),
                      width=(3 if major else 1))

    def _draw_arc(self, draw, cx, cy, R, sec_frac):
        r   = R - 26
        box = [cx-r, cy-r, cx+r, cy+r]
        draw.arc(box, start=-90, end=270, fill=C_GREEN_D, width=6)
        if sec_frac > 0.001:
            draw.arc(box, start=-90, end=-90 + sec_frac*360, fill=C_GREEN, width=6)

    def _draw_hands(self, draw, cx, cy, R, now):
        total = now.hour*3600 + now.minute*60 + now.second + now.microsecond/1e6
        hx,hy = self._polar(cx, cy, R*0.46, (total/43200)*360)
        draw.line([cx,cy,hx,hy], fill=C_WHITE, width=max(6,R//28))
        ms = now.minute*60 + now.second + now.microsecond/1e6
        mx,my = self._polar(cx, cy, R*0.70, (ms/3600)*360)
        draw.line([cx,cy,mx,my], fill=C_WHITE, width=max(4,R//40))
        sf    = (now.second + now.microsecond/1e6) / 60
        sx,sy = self._polar(cx, cy, R*0.78, sf*360)
        tx,ty = self._polar(cx, cy, R*0.16, sf*360+180)
        draw.line([tx,ty,sx,sy], fill=C_RED, width=max(2,R//68))
        b = max(8, R//22)
        draw.ellipse([cx-b,cy-b,cx+b,cy+b], fill=C_RED, outline=C_WHITE, width=2)

    def _draw_digital(self, draw, px, R_clock, now):
        """
        px   = centro horizontal do painel
        R_clock = raio do relógio (usado para limitar a altura disponível)
        Âncora: tempo começa no topo da área disponível (cy - R_clock + margem)
        """
        H   = self.height
        cy  = H // 2
        lw  = int(self.width * 0.16)
        g   = int(H * 0.080)   # gap

        def tw_h(text, font):
            bb = draw.textbbox((0,0), text, font=font)
            return bb[2]-bb[0], bb[3]-bb[1]

        ts    = now.strftime("%H:%M:%S")
        fn    = min(now.microsecond // max(1, 1_000_000 // self.fps_n), self.fps_n-1)
        fr    = f":{fn:02d}"
        ds    = now.strftime("%Y-%m-%d")
        fps_s = f"{self.fps_n}/{self.fps_d} fps"
        lbl   = self.label.upper()

        ttw, tth = tw_h(ts,    self._f_time)
        _,   ffh = tw_h(fr,    self._f_frame)
        _,   ddh = tw_h(ds,    self._f_date)
        _,   ssh = tw_h(fps_s, self._f_small)
        _,   llh = tw_h(lbl,   self._f_label)
        line_h   = 2

        # altura total do bloco
        total_h = tth + g + line_h + g + ffh + g + ddh + g + ssh + g + llh

        # âncora: começar no topo do relógio + margem pequena
        top = cy - R_clock + int(H * 0.04)
        y   = top

        # ── HORA (topo) ───────────────────────────────────────────────
        draw.text((px - ttw//2 + 2, y + 2), ts, font=self._f_time, fill=C_GREEN_D)
        draw.text((px - ttw//2,     y),     ts, font=self._f_time, fill=C_GREEN)
        y += tth + g

        # ── linha verde ───────────────────────────────────────────────
        draw.rectangle([px-lw//2, y, px+lw//2, y+line_h], fill=C_GREEN)
        y += line_h + g

        # ── frames ───────────────────────────────────────────────────
        fw, _ = tw_h(fr, self._f_frame)
        draw.text((px - fw//2, y), fr, font=self._f_frame, fill=C_WHITE)
        y += ffh + g

        # ── data ─────────────────────────────────────────────────────
        dw, _ = tw_h(ds, self._f_date)
        draw.text((px - dw//2, y), ds, font=self._f_date, fill=C_WHITE)
        y += ddh + g

        # ── fps ──────────────────────────────────────────────────────
        sw, _ = tw_h(fps_s, self._f_small)
        draw.text((px - sw//2, y), fps_s, font=self._f_small, fill=C_GREEN_D)
        y += ssh + g

        # ── label ─────────────────────────────────────────────────────
        lw2, _ = tw_h(lbl, self._f_label)
        draw.text((px - lw2//2, y), lbl, font=self._f_label, fill=C_WHITE)

    def get_video_frame(self):
        now  = datetime.datetime.now()
        W, H = self.width, self.height
        img  = Image.new("RGBA", (W,H), C_BG)
        draw = ImageDraw.Draw(img)

        R  = int(min(W * 0.26, H * 0.37))
        cx = int(W * 0.30)
        cy = H // 2

        self._draw_face(draw, cx, cy, R)
        sf = (now.second + now.microsecond/1e6) / 60
        self._draw_arc(draw, cx, cy, R, sf)
        self._draw_ticks(draw, cx, cy, R)
        self._draw_hands(draw, cx, cy, R, now)

        right_edge = cx + R + int(W * 0.016)
        panel_w    = W - right_edge - int(W * 0.02)
        px         = right_edge + panel_w // 2

        self._draw_digital(draw, px, R, now)

        arr = np.array(img, dtype=np.uint8)
        arr[:,:,:3] = arr[:,:,[2,1,0]]
        return arr.tobytes()

    def get_audio_frame(self): return self._silence

    @property
    def audio_samples(self): return self.spf
