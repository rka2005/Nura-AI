"""
neura_core.py  --  NEURA CORE: voice-reactive holographic sphere.

Self-contained renderer (pygame + numpy) used by frontend.py.

    core = NeuraCore()
    core.draw(surface, cx, cy, radius, t_ms, amplitude,
              theme=THEMES[current_theme], theme_id=current_theme,
              state=ASSISTANT_STATUS, bg=COLOR_BG)

amplitude : 0..1 microphone level (what frontend.py already computes)
state     : "LISTENING" | "SPEAKING" | "PROCESSING" | anything else = idle
            (SPEAKING synthesises a voice envelope so the core still "talks"
             while Neura's TTS is playing and the mic hears nothing)

Run this file directly for a stand-alone preview:   python neura_core.py
"""
import math

import numpy as np
import pygame

TAU = math.pi * 2

# cool "energy" colour paired with each theme's warm primary (like the blue/gold reference)
SECOND = {1: (40, 170, 255), 2: (70, 225, 255), 3: (70, 205, 255), 4: (255, 190, 80)}

_FONTS = {}
_SPRITES = {}


# ----------------------------------------------------------------- helpers
def _font(px, bold=True):
    px = max(8, int(px))
    key = (px, bold)
    if key not in _FONTS:
        _FONTS[key] = pygame.font.SysFont("consolas,couriernew,monospace", px, bold=bold)
    return _FONTS[key]


def _mix(a, b, t):
    t = 0.0 if t < 0 else (1.0 if t > 1 else t)
    return (int(a[0] + (b[0] - a[0]) * t), int(a[1] + (b[1] - a[1]) * t), int(a[2] + (b[2] - a[2]) * t))


def _lit(c, k):
    return (min(255, int(c[0] * k)), min(255, int(c[1] * k)), min(255, int(c[2] * k)))


def _glow(surface, cx, cy, r, color, strength=1.0):
    """Soft additive radial glow."""
    r = int(r)
    sq = int(strength * 8 + 0.5)
    if r < 4 or sq <= 0:
        return
    sq = min(8, sq)
    rq = max(8, (r // 8) * 8)
    key = ("g", color, rq, sq)
    spr = _SPRITES.get(key)
    if spr is None:
        if len(_SPRITES) > 300:
            _SPRITES.clear()
        n = rq * 2
        yy, xx = np.mgrid[0:n, 0:n]
        d = np.hypot(xx - rq + 0.5, yy - rq + 0.5) / rq
        fall = np.clip(1.0 - d, 0.0, 1.0) ** 2.2 * (sq / 8.0)
        arr = (np.array(color, float)[None, None, :] * fall[..., None]).astype(np.uint8)
        spr = pygame.surfarray.make_surface(arr)
        _SPRITES[key] = spr
    surface.blit(spr, (int(cx) - rq, int(cy) - rq), special_flags=pygame.BLEND_RGB_ADD)


def _orb_sprite(surface, cx, cy, r, warm, hot, strength=1.0):
    """Hot-centre energy ball (white -> hot -> warm -> ember), additive."""
    r = int(r)
    sq = min(8, int(strength * 8 + 0.5))
    if r < 4 or sq <= 0:
        return
    rq = max(6, (r // 4) * 4)
    key = ("o", warm, hot, rq, sq)
    spr = _SPRITES.get(key)
    if spr is None:
        if len(_SPRITES) > 300:
            _SPRITES.clear()
        n = rq * 2
        yy, xx = np.mgrid[0:n, 0:n]
        d = np.hypot(xx - rq + 0.5, yy - rq + 0.5) / rq
        white = np.array((255, 255, 255), float)
        hotc, warmc = np.array(hot, float), np.array(warm, float)
        ember = warmc * 0.28
        t1 = np.clip(d / 0.16, 0, 1)[..., None]
        t2 = np.clip((d - 0.16) / 0.50, 0, 1)[..., None]
        t3 = np.clip((d - 0.72) / 0.28, 0, 1)[..., None]
        col = white * (1 - t1) + hotc * t1
        col = col * (1 - t2) + warmc * 0.80 * t2
        col = col * (1 - t3) + ember * t3
        edge = np.clip((1.0 - d) / 0.06, 0, 1)[..., None]
        arr = (col * edge * (sq / 8.0)).clip(0, 255).astype(np.uint8)
        spr = pygame.surfarray.make_surface(arr)
        _SPRITES[key] = spr
    surface.blit(spr, (int(cx) - rq, int(cy) - rq), special_flags=pygame.BLEND_RGB_ADD)


def _arc_poly(cx, cy, r, a0, a1, w):
    steps = max(5, int(abs(a1 - a0) / 0.07))
    ro, ri = r + w / 2.0, max(1.0, r - w / 2.0)
    angs = [a0 + (a1 - a0) * i / steps for i in range(steps + 1)]
    outer = [(cx + ro * math.cos(a), cy + ro * math.sin(a)) for a in angs]
    inner = [(cx + ri * math.cos(a), cy + ri * math.sin(a)) for a in reversed(angs)]
    return outer + inner


def _fib(n):
    i = np.arange(n) + 0.5
    y = 1 - 2 * i / n
    r = np.sqrt(1 - y * y)
    th = math.pi * (1 + 5 ** 0.5) * i
    return np.stack([r * np.cos(th), y, r * np.sin(th)], 1)


# -------------------------------------------------------------------- core
class NeuraCore:
    NB = 32  # voice bands

    def __init__(self, seed=7, points=2800):
        rng = np.random.default_rng(seed)
        self.u = _fib(points)
        self.lon = np.arctan2(self.u[:, 2], self.u[:, 0])
        self.ph = rng.uniform(0, TAU, points)
        self.jit = rng.uniform(-1, 1, points)
        self.bri = rng.uniform(0.55, 1.0, points)
        self.spark = rng.random(points) > 0.985

        # geodesic mesh inside the orb
        self.mesh_v = _fib(26)
        d = np.linalg.norm(self.mesh_v[:, None, :] - self.mesh_v[None, :, :], axis=2)
        self.mesh_e = [(i, j) for i in range(26) for j in range(i + 1, 26) if d[i, j] < 0.98]
        self.mesh_ph = rng.uniform(0, TAU, 26)

        self.bands = np.zeros(self.NB)
        self.level = 0.0
        self.prev_drive = 0.0
        self.peak = 0.0
        self.avg = 0.0
        self.active = 0.0
        self.rot = 0.0
        self.orbit_ph = [0.0, 1.7, 3.9]
        self.waves = []
        self.last_wave = -9.0
        self.speak_clock = 0.0
        self._last_t = None
        self.time = 0.0

    # ------------------------------------------------------------ voice model
    def _voice(self, dt, amplitude, state):
        raw = max(0.0, min(1.0, amplitude * 1.7)) ** 0.8
        t = self.time
        if state == "SPEAKING":
            self.speak_clock += dt
            s = self.speak_clock
            env = (0.5 + 0.5 * math.sin(s * 9.0)) * (0.55 + 0.45 * math.sin(s * 2.3 + 1.0))
            env *= 0.75 + 0.25 * math.sin(s * 23.0 + math.sin(s * 3.0))
            raw = max(raw, 0.22 + 0.5 * env)
        else:
            self.speak_clock = 0.0
        if state == "PROCESSING":
            raw = max(raw, 0.10 + 0.07 * math.sin(t * 6.0))
        raw = max(raw, 0.035 + 0.02 * math.sin(t * 1.4))      # idle breathing

        k = 1.0 - math.exp(-dt * (26.0 if raw > self.level else 5.0))
        self.level += (raw - self.level) * k
        L = self.level

        for i in range(self.NB):
            shape = 0.45 + 0.55 * math.exp(-((i - self.NB * 0.28) / (self.NB * 0.42)) ** 2)
            n = abs(math.sin(i * 1.73 + t * (5.0 + i * 0.21))) * (0.55 + 0.45 * abs(math.sin(i * 0.61 - t * 2.9)))
            target = min(1.0, L * shape * (0.45 + 0.75 * n) * 1.35)
            rate = 30.0 if target > self.bands[i] else 7.0
            self.bands[i] += (target - self.bands[i]) * (1.0 - math.exp(-dt * rate))

        self.peak = max(self.peak - dt * 0.35, L)
        self.avg += (L - self.avg) * (1.0 - math.exp(-dt / 2.0))
        self.active += ((1.0 if L > 0.12 else 0.0) - self.active) * (1.0 - math.exp(-dt / 4.0))

        rising = L - self.prev_drive
        self.prev_drive = L
        if (L > 0.16 and rising > 0.012 and t - self.last_wave > 0.30) or \
                (state == "SPEAKING" and t - self.last_wave > 0.75):
            self.waves.append(t)
            self.last_wave = t
        self.waves = [w for w in self.waves if t - w < 1.3]

    # ------------------------------------------------------------------ draw
    def draw(self, surface, cx, cy, radius, t_ms, amplitude=0.0, theme=None, theme_id=1,
             state="IDLE", bg=(7, 10, 19)):
        t_s = t_ms * 0.001
        if self._last_t is None:
            self._last_t = t_s
        dt = max(0.001, min(0.1, t_s - self._last_t))
        self._last_t = t_s
        self.time += dt

        theme = theme or {}
        warm = tuple(theme.get("primary", (232, 190, 110)))
        warm_soft = tuple(theme.get("primary_soft", (150, 118, 64)))
        dotc = tuple(theme.get("sphere_dots", warm))
        hot = tuple(theme.get("loud_core", (255, 236, 170)))
        cool = SECOND.get(theme_id, SECOND[1])

        self._voice(dt, amplitude, state)
        L = self.level
        R = float(radius)
        cx, cy = int(cx), int(cy)
        t = self.time
        full = R >= 110
        mid = R >= 58
        fast = 1.0 + (1.2 if state == "PROCESSING" else 0.0)
        self.rot += dt * (0.30 + 0.9 * L) * fast
        w1 = 2 if R >= 160 else 1          # base line width
        bgc = bg

        # 1 ---- atmosphere
        _glow(surface, cx, cy, R * 1.65, warm_soft, 0.28 + 0.40 * L)
        _glow(surface, cx, cy, R * 1.05, cool, 0.10 + 0.22 * L)

        # 2 ---- base platform
        if full:
            py = cy + R * 1.36
            for k, (wm, a) in enumerate(((1.30, 0.55), (1.08, 0.7), (0.86, 0.85), (0.60, 1.0))):
                col = _mix(bgc, cool if k % 2 == 0 else warm, 0.30 + 0.55 * a * (0.5 + L))
                rect = pygame.Rect(0, 0, int(R * wm * 2), int(R * wm * 0.20))
                rect.center = (cx, int(py))
                pygame.draw.ellipse(surface, col, rect, 1)
            _glow(surface, cx, int(py), R * 0.9, cool, 0.12 + 0.2 * L)

        # 3 ---- outer ring system
        ring_c = _mix(bgc, cool, 0.45)
        pygame.draw.circle(surface, _mix(bgc, cool, 0.22), (cx, cy), int(R * 1.44), 1)
        pygame.draw.circle(surface, ring_c, (cx, cy), int(R * 1.28), 1)
        nt = 120 if full else (72 if mid else 40)
        spin = self.rot * 0.18
        for i in range(nt):
            a = spin + TAU * i / nt
            major = i % 5 == 0
            r0 = R * 1.28
            r1 = R * (1.37 if major else 1.325)
            c = _mix(bgc, warm if major else cool, 0.85 if major else 0.55)
            pygame.draw.line(surface, c, (cx + r0 * math.cos(a), cy + r0 * math.sin(a)),
                             (cx + r1 * math.cos(a), cy + r1 * math.sin(a)), 1)

        # gold brackets (left / right) that breathe with the voice
        br = R * (1.20 + 0.025 * L)
        bw = max(3.0, R * 0.032)
        for mid_a in (0.0, math.pi):
            half = math.radians(34)
            pygame.draw.polygon(surface, _lit(warm, 0.55 + 0.45 * (0.5 + L)),
                                _arc_poly(cx, cy, br, mid_a - half, mid_a + half, bw))
            pygame.draw.polygon(surface, hot, _arc_poly(cx, cy, br, mid_a - half * 0.82, mid_a + half * 0.82,
                                                        max(1.0, bw * 0.28)))
            for s in (-1, 1):
                a = mid_a + s * math.radians(44)
                pygame.draw.line(surface, warm, (cx + (R * 1.15) * math.cos(a), cy + (R * 1.15) * math.sin(a)),
                                 (cx + (R * 1.25) * math.cos(a), cy + (R * 1.25) * math.sin(a)), w1)

        # 4 ---- globe particles
        for k in range(3):
            pygame.draw.circle(surface, _mix(bgc, dotc, 0.22 - 0.06 * k + 0.25 * L), (cx, cy),
                               int(R * (1.0 + 0.012 * k + 0.03 * L)), 1)
        step = 1 if full else (2 if mid else 4)
        u = self.u[::step]
        lon, ph, jit, bri, spark = (self.lon[::step], self.ph[::step], self.jit[::step],
                                    self.bri[::step], self.spark[::step])
        yaw = self.rot
        pitch = 0.30 + 0.05 * math.sin(t * 0.35)
        cyaw, syaw, cp, sp = math.cos(yaw), math.sin(yaw), math.cos(pitch), math.sin(pitch)
        x1 = u[:, 0] * cyaw + u[:, 2] * syaw
        z1 = -u[:, 0] * syaw + u[:, 2] * cyaw
        y2 = u[:, 1] * cp - z1 * sp
        z2 = u[:, 1] * sp + z1 * cp

        band_idx = (((lon + math.pi) / TAU) * self.NB).astype(int) % self.NB
        bval = self.bands[band_idx]
        wob = 0.012 * np.sin(t * 1.3 + ph)
        burst = L * (0.05 + 0.10 * (0.5 + 0.5 * np.sin(ph * 3.0 + t * 11.0))) + bval * 0.12
        rad = 1.0 + wob + jit * 0.006 + burst
        px, py_, pz = x1 * rad, y2 * rad, z2 * rad
        persp = 1.0 / (1.0 - pz / 6.0)
        sx = (cx + px * R * persp).astype(int)
        sy = (cy + py_ * R * persp).astype(int)
        depth = np.clip((pz + 1.0) * 0.5, 0.0, 1.0)
        rho = np.hypot(px, py_) * persp
        rim = np.clip((rho - 0.46) / 0.54, 0.0, 1.0) ** 1.15
        bright = (0.30 + 0.70 * depth ** 1.1) * (0.26 + 0.74 * rim) * bri * (1.0 + 0.55 * L + 0.9 * bval)
        bright = np.clip(bright * 1.55, 0.0, 1.7)
        base = np.array(dotc, float)
        cols = np.clip(base[None, :] * bright[:, None], 0, 255).astype(np.uint8)
        big = R / 230.0
        size = np.where((depth > 0.55) & (rim > 0.35), 1 + (big > 0.6), 1)
        order = np.argsort(pz)
        sxl, syl, szl, cl = sx.tolist(), sy.tolist(), size.tolist(), cols.tolist()
        fill = surface.fill
        for i in order.tolist():
            s = szl[i]
            c = cl[i]
            if c[0] + c[1] + c[2] < 24:
                continue
            fill(c, (sxl[i], syl[i], s, s))
        if mid:
            bright_idx = np.where(spark & (pz > 0.1))[0]
            for i in bright_idx.tolist()[:40]:
                _glow(surface, sxl[i], syl[i], R * (0.035 + 0.04 * L), warm, 0.9)
                fill(hot, (sxl[i], syl[i], 2, 2))

        # 5 ---- tilted orbit rings with travelling nodes
        orbits = ((1.15, 0.25, 0.55, 1.10), (0.35, -0.85, -0.42, 1.14), (-0.75, 1.25, 0.31, 1.19))
        segs = 72 if full else 40
        for oi, (tx, tz, spd, rm) in enumerate(orbits):
            self.orbit_ph[oi] += dt * spd * (1.0 + 2.6 * L)
            ctx, stx, ctz, stz = math.cos(tx), math.sin(tx), math.cos(tz), math.sin(tz)
            precess = self.rot * (0.35 + 0.1 * oi)
            cpr, spr_ = math.cos(precess), math.sin(precess)

            def pt(phi):
                x, z = math.cos(phi), math.sin(phi)
                y_ = -z * stx
                z_ = z * ctx
                xx = x * ctz - y_ * stz
                yy = x * stz + y_ * ctz
                xr = xx * cpr + z_ * spr_
                zr = -xx * spr_ + z_ * cpr
                f = 1.0 / (1.0 - zr * rm / 6.0)
                return cx + xr * R * rm * f, cy + yy * R * rm * f, zr

            prev = pt(0.0)
            for k in range(1, segs + 1):
                cur = pt(TAU * k / segs)
                zf = (cur[2] + 1) * 0.5
                col = _mix(bgc, _mix(warm, hot, 0.35), 0.30 + 0.70 * zf * (0.8 + 0.4 * L))
                pygame.draw.line(surface, col, (prev[0], prev[1]), (cur[0], cur[1]), w1 + (1 if zf > 0.6 and R > 150 else 0))
                prev = cur
            for nd in range(2):
                nx, ny, nz = pt(self.orbit_ph[oi] + nd * math.pi)
                zf = (nz + 1) * 0.5
                _glow(surface, nx, ny, R * (0.05 + 0.03 * L) * (0.6 + 0.6 * zf), warm, 0.5 + 0.5 * zf)
                pygame.draw.circle(surface, hot if zf > 0.4 else warm, (int(nx), int(ny)),
                                   max(1, int(R * 0.012 * (0.7 + zf))))

        # 6 ---- cross-hair
        steps = 26
        ext = R * 1.30
        for dirx, diry in ((1, 0), (0, 1)):
            for sgn in (-1, 1):
                prev = (cx, cy)
                for k in range(1, steps + 1):
                    d = ext * k / steps
                    cur = (cx + dirx * d * sgn, cy + diry * d * sgn)
                    f = (k / steps) ** 0.75
                    c = _mix(_mix((210, 240, 255), cool, 0.35), bgc, f)
                    pygame.draw.line(surface, c, prev, cur, w1 + (1 if k < 7 and R > 150 else 0))
                    prev = cur
        _glow(surface, cx, cy, R * 0.55, cool, 0.18 + 0.3 * L)

        # 7 ---- inner HUD: thick blue arcs, gold dashed rings, voice equalizer
        spin_a = self.rot * 0.9
        for k in range(3):
            a0 = spin_a * (1.0 if True else -1) + k * TAU / 3
            r_arc = R * 0.70
            wd = max(3.0, R * (0.040 + 0.020 * L))
            pygame.draw.polygon(surface, _lit(cool, 0.75), _arc_poly(cx, cy, r_arc, a0, a0 + 1.25, wd))
            pygame.draw.polygon(surface, _mix(cool, (255, 255, 255), 0.55),
                                _arc_poly(cx, cy, r_arc, a0 + 0.05, a0 + 1.20, max(1.0, wd * 0.30)))
        for k in range(4):
            a0 = -spin_a * 1.3 + k * TAU / 4
            pygame.draw.polygon(surface, _lit(warm, 0.9), _arc_poly(cx, cy, R * 0.625, a0, a0 + 0.55,
                                                                    max(2.0, R * 0.018)))
        pygame.draw.circle(surface, _mix(bgc, warm, 0.7), (cx, cy), int(R * 0.585), 1)
        pygame.draw.circle(surface, _mix(bgc, cool, 0.5), (cx, cy), int(R * 0.755), 1)

        nb = 72 if full else (48 if mid else 30)
        r_in = R * 0.405
        for k in range(nb):
            a = -math.pi / 2 + TAU * k / nb + self.rot * 0.08
            idx = abs(((k + nb // 4) % nb) - nb / 2) / (nb / 2)
            bv = float(self.bands[min(self.NB - 1, int(idx * self.NB))])
            ln = R * (0.020 + 0.150 * bv)
            c = _mix(cool, (255, 255, 255), min(1.0, bv * 0.9))
            c = _lit(c, 0.55 + 0.6 * bv)
            pygame.draw.line(surface, c, (cx + r_in * math.cos(a), cy + r_in * math.sin(a)),
                             (cx + (r_in + ln) * math.cos(a), cy + (r_in + ln) * math.sin(a)), w1 + (1 if R > 190 else 0))

        # 8 ---- energy orb with geodesic mesh
        o_warm = dotc
        o_hot = _mix(dotc, (255, 255, 255), 0.55)
        r_orb = R * (0.255 + 0.050 * L)
        _glow(surface, cx, cy, r_orb * 2.7, o_warm, 0.30 + 0.45 * L)
        _orb_sprite(surface, cx, cy, r_orb, o_warm, o_hot, 0.62 + 0.38 * L)
        ym = self.rot * 1.7
        cy_, sy_ = math.cos(ym), math.sin(ym)
        cxt, sxt = math.cos(0.45), math.sin(0.45)
        mv = self.mesh_v * (1.0 + 0.10 * L * np.sin(self.mesh_ph + t * 12.0))[:, None]
        mx = mv[:, 0] * cy_ + mv[:, 2] * sy_
        mz = -mv[:, 0] * sy_ + mv[:, 2] * cy_
        my = mv[:, 1] * cxt - mz * sxt
        mz2 = mv[:, 1] * sxt + mz * cxt
        mxs, mys = cx + mx * r_orb * 0.96, cy + my * r_orb * 0.96
        for i, j in self.mesh_e:
            zf = (mz2[i] + mz2[j]) * 0.25 + 0.5
            c = _mix(o_hot, (255, 255, 255), 0.35 + 0.30 * zf)
            c = _lit(c, 0.60 + 0.40 * zf)
            pygame.draw.line(surface, c, (mxs[i], mys[i]), (mxs[j], mys[j]), 1 if zf < 0.55 or R < 140 else 2)
        for i in range(len(mxs)):
            if mz2[i] > -0.1:
                surface.fill(hot, (int(mxs[i]) - 1, int(mys[i]) - 1, 2, 2))
        pygame.draw.circle(surface, _lit(warm, 1.0), (cx, cy), int(r_orb * 1.04), w1)
        pygame.draw.circle(surface, _mix(bgc, warm, 0.8), (cx, cy), int(r_orb * 1.32), 1)
        _glow(surface, cx, cy, r_orb * 0.55, (255, 255, 255), 0.12 + 0.45 * L)

        # 9 ---- voice shock-waves
        for w in self.waves:
            p = (t - w) / 1.3
            rr = R * (0.30 + 1.0 * p)
            fade = (1.0 - p) ** 1.4
            c = _mix(bgc, _mix(cool, warm, p), 0.15 + 0.85 * fade)
            pygame.draw.circle(surface, c, (cx, cy), int(rr), max(1, int(w1 + (1 - p) * 2)))

        # 10 --- outer nodes + gauges
        for k in range(8):
            a = -spin * 0.6 + TAU * k / 8 + 0.39
            nx, ny = cx + R * 1.28 * math.cos(a), cy + R * 1.28 * math.sin(a)
            pulse = 0.55 + 0.45 * math.sin(t * 3 + k) + L
            _glow(surface, nx, ny, R * 0.05 * (1 + L), warm, min(1.0, 0.5 * pulse))
            pygame.draw.circle(surface, hot, (int(nx), int(ny)), max(1, int(R * 0.011)))

        if full:
            gauges = (("VOICE", self.level, -1, -1), ("PEAK", self.peak, 1, -1),
                      ("AVG", self.avg, -1, 1), ("ACTIVE", self.active, 1, 1))
            gr = max(15, int(R * 0.085))
            for label, val, sx_, sy2 in gauges:
                gx = cx + sx_ * R * 1.19
                gy = cy + sy2 * R * 0.64
                pygame.draw.circle(surface, (8, 14, 28), (int(gx), int(gy)), gr)
                pygame.draw.circle(surface, _mix(bgc, cool, 0.45), (int(gx), int(gy)), gr, 1)
                v = max(0.0, min(1.0, val))
                if v > 0.01:
                    rect = pygame.Rect(0, 0, gr * 2 - 4, gr * 2 - 4)
                    rect.center = (int(gx), int(gy))
                    pygame.draw.arc(surface, warm, rect, math.pi / 2 - TAU * v, math.pi / 2, 3)
                tx_ = _font(max(9, int(gr * 0.62))).render(f"{int(v * 100)}", True, (235, 242, 255))
                surface.blit(tx_, tx_.get_rect(center=(int(gx), int(gy))))
                lb = _font(max(8, int(gr * 0.46)), False).render(label, True, _mix(bgc, cool, 0.85))
                surface.blit(lb, lb.get_rect(center=(int(gx), int(gy + gr + 9))))


# ------------------------------------------------------------- preview app
if __name__ == "__main__":
    import sys
    pygame.init()
    scr = pygame.display.set_mode((1100, 800), pygame.RESIZABLE)
    pygame.display.set_caption("NEURA CORE preview  [1-4 theme | SPACE speaking | hold mouse = loud voice]")
    clock = pygame.time.Clock()
    themes = {
        1: dict(primary=(232, 190, 110), primary_soft=(150, 118, 64), sphere_dots=(255, 190, 70), loud_core=(255, 236, 170)),
        2: dict(primary=(158, 130, 255), primary_soft=(100, 80, 190), sphere_dots=(180, 110, 255), loud_core=(225, 205, 255)),
        3: dict(primary=(255, 118, 140), primary_soft=(180, 70, 92), sphere_dots=(255, 95, 95), loud_core=(255, 190, 200)),
        4: dict(primary=(80, 215, 205), primary_soft=(40, 140, 140), sphere_dots=(70, 230, 140), loud_core=(180, 255, 245)),
    }
    core, tid, speaking = NeuraCore(), 1, False
    while True:
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                sys.exit()
            if e.type == pygame.KEYDOWN:
                if e.key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4):
                    tid = e.key - pygame.K_0
                if e.key == pygame.K_SPACE:
                    speaking = not speaking
        t = pygame.time.get_ticks()
        amp = 0.0
        if pygame.mouse.get_pressed()[0]:
            amp = 0.25 + 0.5 * abs(math.sin(t * 0.011)) * abs(math.sin(t * 0.0033))
        w, h = scr.get_size()
        scr.fill((7, 10, 19))
        core.draw(scr, w // 2, int(h * 0.46), min(w, h) * 0.285, t, amp, themes[tid], tid,
                  "SPEAKING" if speaking else "LISTENING")
        pygame.display.flip()
        clock.tick(60)