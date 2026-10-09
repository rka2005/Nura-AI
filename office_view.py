"""
office_view.py  --  NEURA HQ: top-down animated agent office.

Drop-in replacement for the old AgentOffice3D.  Public API:
    view = OfficeView()
    view.sync_from_bridge(agents_dict)          # from status_bridge.json
    view.draw(surface, rect, t_ms, dt_ms)       # call every frame
Everything (movement, doors, task banners, click handling) lives in here.
"""
import math
import random
import pygame

LW, LH = 1000, 700          # logical office size (scaled to fit any rect)
TAU = math.pi * 2

# ----------------------------------------------------------------- helpers
_FONTS = {}


def _font(px, bold=True):
    px = max(9, int(px))
    key = (px, bold)
    if key not in _FONTS:
        _FONTS[key] = pygame.font.SysFont("segoeui,calibri,arial", px, bold=bold)
    return _FONTS[key]


def _lighten(col, a):
    return tuple(min(255, v + a) for v in col)


def _mix(a, b, t):
    t = max(0.0, min(1.0, t))
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


_GLOW = {}


def _glow_surf(col, r):
    r = max(3, int(r))
    key = (col, r)
    sf = _GLOW.get(key)
    if sf is None:
        sf = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
        steps = 12
        for i in range(steps):
            rad = int(r * (steps - i) / steps)
            a = int(150 * ((i + 1) / steps) ** 2.2)
            pygame.draw.circle(sf, (col[0], col[1], col[2], a), (r, r), max(1, rad))
        _GLOW[key] = sf
    return sf


class Canvas:
    """Scaled drawing helper: all coordinates are logical office units."""

    def __init__(self, surf, s, ox=0.0, oy=0.0):
        self.surf, self.s, self.ox, self.oy = surf, s, ox, oy

    def p(self, x, y):
        return (int(self.ox + x * self.s), int(self.oy + y * self.s))

    def n(self, v):
        return max(1, int(round(v * self.s)))

    def _r(self, x, y, w, h):
        return pygame.Rect(int(self.ox + x * self.s), int(self.oy + y * self.s),
                           max(1, int(w * self.s)), max(1, int(h * self.s)))

    def rect(self, col, x, y, w, h, r=0, bw=0):
        rc = self._r(x, y, w, h)
        pygame.draw.rect(self.surf, col, rc, self.n(bw) if bw else 0, border_radius=int(r * self.s))
        return rc

    def arect(self, col, x, y, w, h, r=0):
        rc = self._r(x, y, w, h)
        sf = pygame.Surface(rc.size, pygame.SRCALPHA)
        pygame.draw.rect(sf, col, sf.get_rect(), border_radius=int(r * self.s))
        self.surf.blit(sf, rc.topleft)

    def aellipse(self, col, x, y, w, h):
        rc = self._r(x, y, w, h)
        sf = pygame.Surface(rc.size, pygame.SRCALPHA)
        pygame.draw.ellipse(sf, col, sf.get_rect())
        self.surf.blit(sf, rc.topleft)

    def circle(self, col, x, y, r, width=0):
        pygame.draw.circle(self.surf, col, self.p(x, y), max(1, int(r * self.s)),
                           self.n(width) if width else 0)

    def line(self, col, a, b, w=1):
        pygame.draw.line(self.surf, col, self.p(*a), self.p(*b), self.n(w))

    def poly(self, col, pts, width=0):
        pygame.draw.polygon(self.surf, col, [self.p(*q) for q in pts], self.n(width) if width else 0)

    def arc(self, col, x, y, r, a0, a1, w=1):
        rad = max(2, int(r * self.s))
        cx, cy = self.p(x, y)
        pygame.draw.arc(self.surf, col, pygame.Rect(cx - rad, cy - rad, rad * 2, rad * 2), a0, a1, self.n(w))

    def glow(self, col, x, y, r, strength=1.0):
        sf = _glow_surf(col, max(3, int(r * self.s)))
        sf.set_alpha(int(255 * max(0.0, min(1.0, strength))))
        px, py = self.p(x, y)
        self.surf.blit(sf, (px - sf.get_width() // 2, py - sf.get_height() // 2))

    def font(self, size, bold=True):
        return _font(size * self.s, bold)

    def text(self, txt, size, col, x, y, anchor="c", bold=True):
        im = self.font(size, bold).render(txt, True, col)
        rc = im.get_rect()
        setattr(rc, {"c": "center", "l": "midleft", "r": "midright"}[anchor], self.p(x, y))
        self.surf.blit(im, rc)
        return rc

    def fit(self, txt, size, max_w, bold=True):
        f = self.font(size, bold)
        lim = max_w * self.s
        if f.size(txt)[0] <= lim:
            return txt
        while txt and f.size(txt + "...")[0] > lim:
            txt = txt[:-1]
        return txt.rstrip() + "..."


# ------------------------------------------------------------ room layout
ROOMS = {
    "project_tester": dict(
        name="QA LAB", rect=(30, 30, 300, 220), color=(0, 230, 255), carpet=(17, 42, 58),
        cx=180, side="S", seat=(145, 162), face=-math.pi / 2, banner="top",
        monitors=[(96, 106, 38, 8), (152, 106, 38, 8)]),
    "screen_vision": dict(
        name="VISION LAB", rect=(350, 30, 300, 220), color=(255, 75, 190), carpet=(44, 22, 52),
        cx=500, side="S", seat=(500, 162), face=-math.pi / 2, banner="top",
        monitors=[(446, 106, 40, 8), (514, 106, 40, 8), (385, 36, 230, 8)]),
    "memory_agent": dict(
        name="MEMORY VAULT", rect=(670, 30, 300, 220), color=(185, 115, 255), carpet=(36, 26, 58),
        cx=820, side="S", seat=(840, 162), face=-math.pi / 2, banner="top",
        monitors=[(800, 106, 40, 8), (850, 106, 40, 8)]),
    "system_monitor": dict(
        name="OPS CENTER", rect=(30, 450, 300, 220), color=(60, 255, 150), carpet=(16, 44, 36),
        cx=180, side="N", seat=(160, 489), face=math.pi / 2, banner="bottom",
        monitors=[(76, 524, 40, 8), (130, 524, 40, 8), (184, 524, 40, 8), (36, 490, 8, 120)]),
    "skill_runner": dict(
        name="TOOL BAY", rect=(670, 450, 300, 220), color=(255, 190, 45), carpet=(52, 40, 18),
        cx=820, side="N", seat=(785, 489), face=math.pi / 2, banner="bottom",
        monitors=[]),
}
CORE = dict(name="NEURA CORE", rect=(350, 450, 300, 220), color=(0, 220, 255), carpet=(14, 30, 48), cx=500)

for _aid, _R in ROOMS.items():
    _x, _y, _w, _h = _R["rect"]
    if _R["side"] == "S":
        _R["out"], _R["in"] = (_R["cx"], _y + _h + 18), (_R["cx"], _y + _h - 18)
    else:
        _R["out"], _R["in"] = (_R["cx"], _y - 18), (_R["cx"], _y + 18)

HALL_SPOTS = [(260, 300), (260, 400), (420, 330), (580, 370), (720, 310), (760, 405), (900, 385), (130, 290)]

LOOKS = {
    "project_tester": dict(skin=(236, 190, 150), hair=(52, 36, 28), shirt=(0, 160, 190), long=False),
    "screen_vision": dict(skin=(205, 155, 118), hair=(28, 22, 26), shirt=(214, 56, 156), long=True),
    "system_monitor": dict(skin=(245, 206, 172), hair=(172, 112, 52), shirt=(36, 176, 104), long=False),
    "skill_runner": dict(skin=(142, 100, 72), hair=(20, 18, 20), shirt=(226, 156, 28), long=False),
    "memory_agent": dict(skin=(226, 178, 142), hair=(206, 206, 216), shirt=(146, 92, 220), long=True),
}
META = {
    "project_tester": ("PROJECT_TESTER", "TESTER", "Running project test suite"),
    "screen_vision": ("SCREEN_VISION", "VISION", "Inspecting the screen"),
    "system_monitor": ("SYS_MONITOR", "MONITOR", "Monitoring system health"),
    "skill_runner": ("SKILL_RUNNER", "SKILLS", "Executing automation skill"),
    "memory_agent": ("MEMORY_ARCHIVIST", "MEMORY", "Updating memory archive"),
}
START_SPOT = {"project_tester": (260, 300), "screen_vision": (420, 330), "system_monitor": (260, 400),
              "skill_runner": (760, 405), "memory_agent": (720, 310)}
DEMO_TASKS = {
    "project_tester": ["Running unit tests on neura.py", "Auditing project for syntax errors"],
    "screen_vision": ["Scanning screen for UI elements", "Reading on-screen text (OCR)"],
    "system_monitor": ["Monitoring CPU, RAM and GPU load", "Checking running processes"],
    "skill_runner": ["Executing automation skill pipeline", "Opening apps and files for you"],
    "memory_agent": ["Indexing conversation memory", "Saving your preferences"],
}


def _inside(rect, x, y):
    rx, ry, rw, rh = rect
    return rx <= x <= rx + rw and ry <= y <= ry + rh


# ------------------------------------------------------------------ agent
class Agent:
    def __init__(self, aid):
        self.id = aid
        self.name, self.short, self.default_task = META[aid]
        self.room = ROOMS[aid]
        self.color = self.room["color"]
        self.look = LOOKS[aid]
        self.x, self.y = START_SPOT[aid]
        self.facing = random.uniform(0, TAU)
        self.status = "IDLE"
        self.phase = "idle"          # idle | to_room | working | to_hall
        self.task = ""
        self.path = []
        self.moving = False
        self.walk = random.random() * 6
        self.speed = 105.0
        self.t_work = 0.0
        self.wander = random.uniform(1.5, 5.0)
        self.seed = random.random() * 10
        self.particles = []
        self.spawn = 0.0

    # -- commands
    def set_busy(self, task=""):
        task = task or self.default_task
        self.pending_idle = False
        if self.status == "BUSY":
            self.task = task
            return
        self.status = "BUSY"
        self.task = task
        self.t_work = 0.0
        self.phase = "to_room"
        R = self.room
        if _inside(R["rect"], self.x, self.y):
            self.path = [R["seat"]]
        else:
            self.path = [R["out"], R["in"], R["seat"]]

    def set_idle(self):
        if self.status == "IDLE":
            return
        # If agent just started moving to room or just began working, give it a smooth visual working cycle
        if self.phase in ("to_room", "working") and self.t_work < 2.0:
            self.pending_idle = True
            return
        self.pending_idle = False
        self.status = "IDLE"
        R = self.room
        spot = random.choice(HALL_SPOTS)
        if _inside(R["rect"], self.x, self.y):
            self.path = [R["in"], R["out"], spot]
        else:
            self.path = [spot]
        self.phase = "to_hall"

    # -- simulation
    @staticmethod
    def _wrap(a):
        return (a + math.pi) % TAU - math.pi

    def _turn(self, target, rate):
        d = self._wrap(target - self.facing)
        self.facing += max(-rate, min(rate, d))

    def update(self, dt, t):
        self.moving = False
        if self.path:
            tx, ty = self.path[0]
            dx, dy = tx - self.x, ty - self.y
            d = math.hypot(dx, dy)
            step = self.speed * dt
            if d <= step:
                self.x, self.y = tx, ty
                self.path.pop(0)
            else:
                self.x += dx / d * step
                self.y += dy / d * step
                self.moving = True
                self._turn(math.atan2(dy, dx), 14 * dt)
            self.walk += dt * 11
        if not self.path and not self.moving:
            if self.phase == "to_room":
                self.phase = "working"
                if getattr(self, "pending_idle", False) and self.t_work >= 2.0:
                    self.set_idle()
            elif self.phase == "to_hall":
                self.phase = "idle"
                self.wander = random.uniform(3, 6)
        if self.phase == "working":
            self.t_work += dt
            if getattr(self, "pending_idle", False) and self.t_work >= 2.0:
                self.set_idle()
            self._turn(self.room["face"], 9 * dt)
            self.spawn -= dt
            if self.spawn <= 0:
                self.spawn = 0.11
                fx, fy = math.cos(self.facing), math.sin(self.facing)
                self.particles.append([self.x + fx * 24 + random.uniform(-14, 14) * -fy,
                                       self.y + fy * 24 + random.uniform(-14, 14) * fx,
                                       fx * 10, fy * 10, 0.0])
        elif self.phase == "idle" and not self.path:
            self.wander -= dt
            if self.wander <= 0:
                self.wander = random.uniform(4, 9)
                spots = [s for s in HALL_SPOTS if math.hypot(s[0] - self.x, s[1] - self.y) > 60]
                self.path = [random.choice(spots)]
        alive = []
        for p in self.particles:
            p[4] += dt
            if p[4] < 0.9:
                p[0] += p[2] * dt
                p[1] += p[3] * dt
                alive.append(p)
        self.particles = alive


# ------------------------------------------------------------ furniture
def _desk(c, x, y, w, h):
    c.arect((0, 0, 0, 90), x + 3, y + 5, w, h, 5)
    c.rect((118, 82, 54), x, y, w, h, 5)
    c.rect((142, 102, 70), x + 2, y + 2, w - 4, h - 4, 4)
    c.rect((90, 62, 40), x, y, w, h, 5, 1)


def _chair(c, x, y, face):
    c.aellipse((0, 0, 0, 80), x - 11, y - 7, 24, 22)
    c.circle((34, 40, 58), x, y, 11)
    c.circle((48, 56, 82), x, y, 8)
    c.circle((26, 30, 46), x - math.cos(face) * 9, y - math.sin(face) * 9, 6)


def _keyboard(c, x, y, w, h):
    c.rect((26, 30, 44), x, y, w, h, 2)
    for i in range(1, 4):
        c.line((60, 66, 92), (x + 3, y + h * i / 4), (x + w - 3, y + h * i / 4), 0.8)


def _plant(c, x, y, r=12):
    c.aellipse((0, 0, 0, 70), x - r + 2, y - r + 3, r * 2, r * 2)
    for i in range(8):
        a = i * TAU / 8
        g = (30 + (i * 9) % 26, 118 + (i * 17) % 50, 64 + (i * 5) % 18)
        c.circle(g, x + math.cos(a) * r * 0.55, y + math.sin(a) * r * 0.55, r * 0.5)
    c.circle((70, 160, 88), x, y, r * 0.5)
    c.circle((150, 100, 62), x, y, r * 0.2)


def _sofa(c, x, y, w, h, col, back="n"):
    c.arect((0, 0, 0, 90), x + 3, y + 5, w, h, 8)
    c.rect(col, x, y, w, h, 8)
    bt = h * 0.32
    dark = _mix(col, (0, 0, 0), 0.35)
    if back == "n":
        c.rect(dark, x, y, w, bt, 6)
        sy = y + bt
    else:
        c.rect(dark, x, y + h - bt, w, bt, 6)
        sy = y
    c.rect(dark, x, y, 8, h, 6)
    c.rect(dark, x + w - 8, y, 8, h, 6)
    for i in range(1, 3):
        c.line(dark, (x + w * i / 3, sy + 2), (x + w * i / 3, sy + h - bt - 2), 1)


def _round_table(c, x, y, r, col=(110, 78, 52)):
    c.aellipse((0, 0, 0, 90), x - r + 3, y - r + 4, r * 2, r * 2)
    c.circle(col, x, y, r)
    c.circle(_lighten(col, 22), x, y, r * 0.78)


def _bookshelf(c, x, y, w, h, seed):
    rnd = random.Random(seed)
    c.rect((60, 40, 28), x, y, w, h, 2)
    pal = [(180, 70, 70), (70, 120, 190), (220, 180, 70), (90, 160, 110), (170, 110, 200), (230, 230, 235)]
    if w >= h:
        px = x + 2
        while px < x + w - 4:
            bw = rnd.randint(3, 6)
            c.rect(rnd.choice(pal), px, y + 2, bw, h - 4)
            px += bw + 1
    else:
        py = y + 2
        while py < y + h - 4:
            bh = rnd.randint(3, 6)
            c.rect(rnd.choice(pal), x + 2, py, w - 4, bh)
            py += bh + 1


# ------------------------------------------------------------ office view
class OfficeView:
    def __init__(self):
        self.agents = {aid: Agent(aid) for aid in ROOMS}
        self.demo_mode = False
        self.demo_timer = 0.0
        self.selected = "project_tester"
        self.time = 0.0
        self._static = None
        self._static_s = None
        self.leds = []
        self.btn_demo = pygame.Rect(0, 0, 0, 0)
        self.btn_reset = pygame.Rect(0, 0, 0, 0)
        self.chips = {}
        self._prev_down = False
        self._geom = (1.0, 0.0, 0.0)

    # ---------------------------------------------------------- bridge
    def sync_from_bridge(self, agents_dict):
        if not agents_dict or not isinstance(agents_dict, dict) or self.demo_mode:
            return
        alias = {
            "project_tester": ["project_tester", "ProjectAgent", "project"],
            "screen_vision": ["screen_vision", "ScreenAgent", "vision"],
            "system_monitor": ["system_monitor", "MonitorAgent", "monitor"],
            "skill_runner": ["skill_runner", "SkillAgent", "task_delegator", "skills"],
            "memory_agent": ["memory_agent", "MemoryAgent", "ContextMemoryAgent", "memory"],
        }
        for aid, ag in self.agents.items():
            data = None
            for k in alias[aid]:
                if k in agents_dict and isinstance(agents_dict[k], dict):
                    data = agents_dict[k]
                    break
            if not data:
                continue
            st = str(data.get("status", "")).lower()
            task = data.get("current_task") or data.get("task") or ""
            if st in ("busy", "running", "working", "testing", "inspecting"):
                ag.set_busy(task or f"Active: {st.upper()}")
            elif st in ("idle", "stopped", "completed", "ready"):
                ag.set_idle()

    # ---------------------------------------------------------- static scene
    def _build_static(self, s):
        W, H = int(LW * s) + 4, int(LH * s) + 4
        surf = pygame.Surface((W, H))
        surf.fill((9, 12, 22))
        c = Canvas(surf, s)
        self.leds = []

        # hall wooden floor
        c.rect((62, 45, 35), 14, 14, 972, 672)
        for i, x in enumerate(range(14, 986, 26)):
            w = min(26, 986 - x)
            c.rect((67, 49, 38) if i % 2 == 0 else (60, 43, 33), x, 14, w, 672)
            c.line((44, 31, 25), (x, 14), (x, 686), 1)
            for y in range(14 + (i * 37) % 90, 686, 90):
                c.line((44, 31, 25), (x, y), (x + 26, y), 1)

        # central hall rug
        c.circle((30, 44, 72), 500, 350, 64)
        c.circle((52, 78, 120), 500, 350, 64, 2)
        c.circle((52, 78, 120), 500, 350, 50, 1)
        c.circle((52, 78, 120), 500, 350, 22, 1)
        for i in range(12):
            a = i * TAU / 12
            c.line((52, 78, 120), (500 + math.cos(a) * 22, 350 + math.sin(a) * 22),
                   (500 + math.cos(a) * 50, 350 + math.sin(a) * 50), 1)

        # room carpets + walls
        for aid, R in list(ROOMS.items()) + [("core", CORE)]:
            x, y, w, h = R["rect"]
            c.rect(R["carpet"], x, y, w, h)
            c.rect(_lighten(R["carpet"], 14), x + 8, y + 8, w - 16, h - 16, 3, 1)
            c.rect(_lighten(R["carpet"], 6), x + 40, y + 60, w - 80, h - 120, 10)
            c.rect(_lighten(R["carpet"], 20), x + 40, y + 60, w - 80, h - 120, 10, 1)

        # outer wall + windows
        for wx in (70, 200, 330, 460, 590, 720, 850):
            c.rect((120, 170, 215), wx, 12, 70, 4)
            c.rect((120, 170, 215), wx, 684, 70, 4)

        for aid, R in list(ROOMS.items()) + [("core", CORE)]:
            x, y, w, h = R["rect"]
            cx = R["cx"]
            gap = 70 if aid == "core" else 30
            south = aid == "core" or R.get("side") == "N"
            if aid == "core":
                south = False
            door_y = y if (aid == "core" or R.get("side") == "N") else y + h
            segs = [((x, y), (x, y + h)), ((x + w, y), (x + w, y + h))]
            if door_y == y + h:
                segs += [((x, y), (x + w, y)), ((x, y + h), (cx - gap, y + h)), ((cx + gap, y + h), (x + w, y + h))]
            else:
                segs += [((x, y + h), (x + w, y + h)), ((x, y), (cx - gap, y)), ((cx + gap, y), (x + w, y))]
            for a, b in segs:
                c.line((14, 10, 10), (a[0] + 3, a[1] + 4), (b[0] + 3, b[1] + 4), 5)
            for a, b in segs:
                c.line((198, 206, 224), a, b, 5)
            for ex in (cx - gap, cx + gap):
                c.circle((230, 235, 245), ex, door_y, 3)
            if aid != "core":
                inward = -26 if door_y == y + h else 26
                c.line((136, 96, 62), (cx - gap, door_y), (cx - gap, door_y + inward), 3)
        c.rect((198, 206, 224), 14, 14, 972, 672, 0, 6)

        # nameplates
        for aid, R in list(ROOMS.items()) + [("core", CORE)]:
            x, y, w, h = R["rect"]
            top = (aid != "core") and R["side"] == "S"
            py = 254 if top else 426
            px = R["cx"] - 135
            c.rect((14, 20, 36), px, py, 100, 22, 5)
            c.rect(R["color"], px, py, 100, 22, 5, 1)
            c.text(R["name"], 12.5, (235, 242, 255), px + 50, py + 11)

        # ---- QA LAB
        R = ROOMS["project_tester"]
        _desk(c, 80, 98, 130, 46)
        _keyboard(c, 112, 130, 64, 10)
        _chair(c, 145, 166, R["face"])
        self._rack(c, 278, 66, 36, 70, "project_tester")
        c.rect((235, 238, 245), 34, 70, 6, 90, 1)
        c.rect((200, 205, 215), 34, 70, 6, 90, 1, )
        for i in range(5):
            c.line((90, 110, 190), (35, 82 + i * 16), (39, 86 + i * 16), 1)
        c.rect((40, 50, 70), 250, 170, 62, 50, 4)
        c.rect((0, 230, 255), 250, 170, 62, 50, 4, 1)
        for i in range(3):
            c.rect((20, 24, 38), 256 + i * 18, 178, 14, 22, 2)
            c.circle((60, 255, 140) if i != 1 else (255, 90, 90), 263 + i * 18, 208, 2.5)
        c.rect((84, 66, 48), 44, 52, 36, 28, 3)
        c.rect((110, 90, 64), 48, 56, 28, 20, 2)
        _plant(c, 48, 218)

        # ---- VISION LAB
        R = ROOMS["screen_vision"]
        _desk(c, 430, 98, 140, 46)
        _keyboard(c, 470, 130, 64, 10)
        _chair(c, 500, 166, R["face"])
        c.circle((30, 30, 44), 612, 196, 12)
        c.circle((255, 75, 190), 612, 196, 12, 1)
        c.circle((14, 14, 22), 612, 196, 6)
        c.circle((255, 150, 220), 612, 196, 2.5)
        for a in (0.6, 2.7, 4.8):
            c.line((60, 60, 80), (612, 196), (612 + math.cos(a) * 20, 196 + math.sin(a) * 20), 2)
        _round_table(c, 392, 206, 15)
        c.circle((240, 240, 245), 392, 206, 4)
        c.circle((90, 60, 40), 392, 206, 2.5)
        c.circle((255, 215, 140), 380, 80, 7)
        c.circle((255, 235, 190), 380, 80, 3)
        _plant(c, 372, 62, 11)
        _plant(c, 628, 232, 10)

        # ---- MEMORY VAULT
        R = ROOMS["memory_agent"]
        _bookshelf(c, 690, 34, 260, 14, 11)
        _bookshelf(c, 676, 66, 12, 110, 12)
        _bookshelf(c, 954, 66, 12, 110, 13)
        _desk(c, 770, 98, 140, 46)
        _keyboard(c, 810, 130, 64, 10)
        c.rect((235, 232, 220), 776, 126, 22, 14, 1)
        c.line((130, 130, 150), (787, 127), (787, 139), 1)
        _chair(c, 840, 166, R["face"])
        c.rect((60, 40, 70), 920, 190, 34, 34, 6)
        c.circle((20, 14, 36), 937, 207, 12)
        c.poly((185, 115, 255), [(937, 196), (944, 207), (937, 218), (930, 207)])
        c.poly((235, 200, 255), [(937, 196), (944, 207), (937, 207)])
        _plant(c, 692, 224, 11)

        # ---- OPS CENTER
        R = ROOMS["system_monitor"]
        _desk(c, 60, 505, 200, 44)
        _keyboard(c, 125, 509, 64, 10)
        _chair(c, 160, 485, R["face"])
        for i in range(3):
            self._rack(c, 292, 470 + i * 40, 28, 34, "system_monitor")
        for i in range(4):
            self._rack(c, 60 + i * 52, 628, 44, 30, "system_monitor")
        c.rect((60, 66, 90), 232, 590, 44, 18, 3)
        _plant(c, 300, 640, 10)

        # ---- TOOL BAY
        R = ROOMS["skill_runner"]
        _desk(c, 700, 505, 170, 44)
        _chair(c, 785, 485, R["face"])
        c.rect((190, 50, 50), 712, 512, 36, 18, 3)
        c.rect((235, 90, 90), 712, 512, 36, 18, 3, 1)
        c.line((240, 240, 245), (722, 521), (738, 521), 2)
        for i, col in enumerate([(200, 200, 215), (255, 190, 45), (120, 200, 255)]):
            c.rect(col, 764 + i * 26, 516, 18, 5, 1)
        c.rect((40, 44, 62), 880, 478, 54, 54, 6)
        c.rect((255, 190, 45), 880, 478, 54, 54, 6, 1)
        c.rect((18, 22, 36), 888, 486, 38, 38, 3)
        c.circle((255, 190, 45), 907, 505, 7, 1)
        c.circle((80, 86, 110), 925, 620, 14)
        c.circle((46, 50, 70), 925, 620, 9)
        c.line((255, 190, 45), (925, 620), (900, 598), 5)
        c.line((200, 150, 40), (900, 598), (882, 612), 4)
        c.circle((255, 220, 120), 882, 612, 3)
        _bookshelf(c, 950, 540, 14, 80, 31)
        _plant(c, 692, 648, 11)

        # ---- CORE DECK
        c.circle((10, 22, 38), 500, 570, 56)
        c.circle((0, 220, 255), 500, 570, 56, 2)
        c.circle((30, 80, 110), 500, 570, 46, 1)
        for i in range(8):
            a = i * TAU / 8
            c.line((30, 80, 110), (500 + math.cos(a) * 46, 570 + math.sin(a) * 46),
                   (500 + math.cos(a) * 56, 570 + math.sin(a) * 56), 1)
        for (sx, sw) in ((366, 70), (564, 70)):
            _desk(c, sx, 500, sw, 26)
            c.rect((14, 20, 34), sx + 8, 506, sw - 16, 8, 2)
            c.rect((0, 220, 255), sx + 8, 506, sw - 16, 8, 2, 1)
        c.rect((26, 34, 56), 440, 636, 120, 20, 4)
        c.rect((0, 220, 255), 440, 636, 120, 20, 4, 1)
        _plant(c, 372, 648, 10)
        _plant(c, 628, 648, 10)

        # ---- hall decor
        _sofa(c, 40, 380, 110, 36, (46, 82, 112), "s")
        _round_table(c, 100, 345, 14)
        c.circle((240, 240, 245), 100, 345, 4)
        _sofa(c, 870, 290, 100, 34, (120, 56, 78), "n")
        _round_table(c, 920, 346, 13)
        c.circle((240, 240, 245), 920, 346, 4)
        for (px, py) in ((38, 268), (340, 268), (660, 268), (340, 430), (660, 430), (962, 430)):
            _plant(c, px, py)
        c.rect((60, 70, 100), 630, 262, 20, 20, 4)
        c.rect((90, 190, 240), 634, 266, 12, 12, 3)
        c.circle((200, 235, 255), 640, 272, 3)
        return surf

    def _rack(self, c, x, y, w, h, room):
        c.arect((0, 0, 0, 90), x + 2, y + 3, w, h, 2)
        c.rect((16, 20, 32), x, y, w, h, 2)
        c.rect((64, 78, 110), x, y, w, h, 2, 1)
        long_h = h >= w
        n = int((h if long_h else w) / 7)
        for i in range(1, n):
            if long_h:
                c.line((30, 36, 56), (x + 3, y + i * 7), (x + w - 3, y + i * 7), 1)
            else:
                c.line((30, 36, 56), (x + i * 7, y + 3), (x + i * 7, y + h - 3), 1)
        for i in range(max(2, n - 1)):
            if long_h:
                self.leds.append((x + w - 6, y + 6 + i * 7, random.random() * 6, room))
            else:
                self.leds.append((x + 6 + i * 7, y + h - 6, random.random() * 6, room))

    # ---------------------------------------------------------- update
    def _update(self, dt):
        self.time += dt
        if self.demo_mode:
            self.demo_timer -= dt
            if self.demo_timer <= 0:
                self.demo_timer = random.uniform(2.6, 4.2)
                aid = random.choice(list(self.agents))
                ag = self.agents[aid]
                if ag.status == "BUSY":
                    ag.set_idle()
                else:
                    ag.set_busy(random.choice(DEMO_TASKS[aid]))
        ags = list(self.agents.values())
        for a in ags:
            a.update(dt, self.time)
        for i in range(len(ags)):
            for j in range(i + 1, len(ags)):
                a, b = ags[i], ags[j]
                dx, dy = b.x - a.x, b.y - a.y
                d = math.hypot(dx, dy)
                if 0.01 < d < 18:
                    push = (18 - d) * 0.5
                    nx, ny = dx / d, dy / d
                    if a.phase != "working":
                        a.x -= nx * push
                        a.y -= ny * push
                    if b.phase != "working":
                        b.x += nx * push
                        b.y += ny * push

    # ---------------------------------------------------------- dynamic draw
    def _draw_rooms_dynamic(self, c, t):
        pulse = (math.sin(t * 3.2) + 1) * 0.5
        for aid, R in ROOMS.items():
            a = self.agents[aid]
            x, y, w, h = R["rect"]
            busy = a.status == "BUSY"
            col = R["color"]
            if busy:
                c.arect((col[0], col[1], col[2], int(10 + 14 * pulse)), x, y, w, h)
                c.rect(_mix(col, (255, 255, 255), 0.2 * pulse), x + 1, y + 1, w - 2, h - 2, 0, 2.5)
            # monitors
            for (mx, my, mw, mh) in R["monitors"]:
                c.rect((10, 14, 24), mx, my, mw, mh, 1)
                horiz = mw >= mh
                if busy and a.phase == "working":
                    c.glow(col, mx + mw / 2, my + mh / 2, max(mw, mh) * 0.7, 0.35)
                    n = 4
                    for i in range(n):
                        frac = ((t * 0.9 + i * 0.27 + mx * 0.01) % 1.0)
                        if horiz:
                            seg = 0.3 * mw
                            sx = mx + frac * (mw - seg)
                            c.rect(_mix(col, (255, 255, 255), 0.35), sx, my + 1.5 + (i % 2) * 2.5, seg, 1.6)
                        else:
                            seg = 0.2 * mh
                            sy = my + frac * (mh - seg)
                            c.rect(_mix(col, (255, 255, 255), 0.35), mx + 1.5 + (i % 2) * 2.5, sy, 1.6, seg)
                else:
                    c.rect(_mix(col, (10, 14, 24), 0.78), mx + 1, my + 1, max(1, mw - 2), max(1, mh - 2), 1)
        # server leds
        for (x, y, ph, room) in self.leds:
            a = self.agents[room]
            fast = 9.0 if a.status == "BUSY" else 1.6
            on = math.sin(t * fast + ph) > 0.1
            col = ROOMS[room]["color"] if a.status == "BUSY" else (70, 210, 120)
            c.circle(col if on else (28, 40, 52), x, y, 1.8)

    def _draw_core(self, c, t, busy_n):
        cx, cy = 500, 570
        energy = 0.35 + 0.13 * busy_n
        cyan = (0, 220, 255)
        c.glow(cyan, cx, cy, 78, min(1.0, energy))
        for i in range(3):
            r = (t * (14 + 6 * busy_n) + i * 14) % 42
            c.circle(_mix(cyan, (14, 30, 48), r / 42), cx, cy, 8 + r, 1)
        for k in range(3):
            a0 = t * (0.8 + 0.3 * k) * (1 if k % 2 == 0 else -1) + k * 2.1
            c.arc(_mix(cyan, (255, 255, 255), 0.25), cx, cy, 22 + k * 9, a0, a0 + 1.2, 2)
        c.circle((210, 250, 255), cx, cy, 5 + math.sin(t * 4) * 1.2)
        c.circle((255, 255, 255), cx, cy, 2)
        c.text("NEURA CORE", 11, (140, 220, 245), cx, 646 + 0)

    def _draw_hall_conduits(self, c, t):
        for aid, R in ROOMS.items():
            a = self.agents[aid]
            if a.status != "BUSY":
                continue
            col = R["color"]
            pts = [(500, 432), (500, 400), (R["cx"], 400), R["out"]] if R["side"] == "N" else \
                  [(500, 432), (500, 400), (R["cx"], 400), R["out"]]
            for i in range(len(pts) - 1):
                c.line(_mix(col, (40, 30, 24), 0.6), pts[i], pts[i + 1], 1.5)
            frac = (t * 0.5 + hash(aid) % 7 * 0.13) % 1.0
            total = sum(math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]) for i in range(len(pts) - 1))
            dist = frac * total
            for i in range(len(pts) - 1):
                seg = math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
                if dist <= seg and seg > 0:
                    f = dist / seg
                    c.circle(col, pts[i][0] + (pts[i + 1][0] - pts[i][0]) * f,
                             pts[i][1] + (pts[i + 1][1] - pts[i][1]) * f, 3)
                    break
                dist -= seg

    def _draw_agent(self, c, a, t):
        x, y = a.x, a.y
        f = a.facing
        fx, fy = math.cos(f), math.sin(f)
        px, py = -fy, fx
        look = a.look
        skin, hair, shirt = look["skin"], look["hair"], look["shirt"]
        dark = _mix(shirt, (0, 0, 0), 0.5)
        working = a.phase == "working"

        c.aellipse((0, 0, 0, 100), x - 10, y - 6, 22, 15)
        if a.status == "BUSY":
            c.glow(a.color, x, y, 30, 0.6)
        if a.id == self.selected:
            c.circle((255, 255, 255), x, y, 17, 1)

        sw = math.sin(a.walk) * 5.5 if a.moving else 0.0
        for side in (-1, 1):
            bx, by = x + px * side * 10, y + py * side * 10
            if working:
                jit = math.sin(t * 14 + side * 2 + a.seed) * 1.6
                hx = x + fx * (14 + jit) + px * side * 4.5
                hy = y + fy * (14 + jit) + py * side * 4.5
            else:
                hx = bx + fx * sw * side + px * side * 1.2
                hy = by + fy * sw * side + py * side * 1.2
            c.line(dark, (bx, by), (hx, hy), 5)
            c.line(shirt, (bx, by), (hx, hy), 3.4)
            c.circle(skin, hx, hy, 2.5)

        pts = []
        for i in range(18):
            th = TAU * i / 18
            ex, ey = math.cos(th) * 5.4, math.sin(th) * 11.5
            pts.append((x + fx * ex + px * ey, y + fy * ex + py * ey))
        c.poly(shirt, pts)
        c.poly(dark, pts, 1)
        c.line(a.color, (x - fx * 2 + px * 8, y - fy * 2 + py * 8), (x - fx * 2 - px * 8, y - fy * 2 - py * 8), 1.6)

        c.circle(skin, x + px * 6 + fx * 0.5, y + py * 6 + fy * 0.5, 1.8)
        c.circle(skin, x - px * 6 + fx * 0.5, y - py * 6 + fy * 0.5, 1.8)
        c.circle(skin, x, y, 5.9)
        if look["long"]:
            c.circle(hair, x - fx * 4.2, y - fy * 4.2, 5.3)
        c.circle(hair, x - fx * 1.7, y - fy * 1.7, 5.4)
        c.circle(_lighten(hair, 38), x - fx * 2.6 - px * 1.8, y - fy * 2.6 - py * 1.8, 1.7)

    def _draw_tag(self, c, a):
        x, y = a.x, a.y - 27
        col = a.color if a.status == "BUSY" else (120, 140, 175)
        w = 10 + len(a.short) * 6.4 + 10
        c.arect((8, 12, 26, 225), x - w / 2, y - 8, w, 16, 7)
        c.rect(col, x - w / 2, y - 8, w, 16, 7, 1)
        c.circle(col, x - w / 2 + 7, y, 2.6)
        c.text(a.short, 10.5, (238, 244, 255), x + 4, y)

    def _draw_banner(self, c, aid, a, t):
        R = ROOMS[aid]
        x, y, w, h = R["rect"]
        bw, bh = 276, 52
        bx = x + 12
        by = y + 8 if R["banner"] == "top" else y + h - bh - 8
        col = R["color"]
        if a.status == "BUSY" and a.phase == "to_room":
            head = "TASK ASSIGNED // ROUTING"
        elif a.status == "BUSY":
            head = "BACKGROUND TASK RUNNING"
        else:
            head = "TASK DONE // RETURNING"
        c.arect((7, 12, 26, 238), bx, by, bw, bh, 7)
        c.rect(col, bx, by, bw, bh, 7, 1.2)
        c.rect(col, bx, by + 6, 4, bh - 12, 2)
        pulse = (math.sin(t * 6) + 1) * 0.5
        if a.status == "BUSY":
            c.glow(col, bx + 17, by + 15, 11, 0.8)
        c.circle(col if a.status == "BUSY" else (90, 220, 130), bx + 17, by + 15, 3 + pulse * 1.4)
        c.text(head, 12.5, col if a.status == "BUSY" else (120, 235, 150), bx + 28, by + 15, "l")
        mm, ss = divmod(int(a.t_work), 60)
        if c.s >= 0.8:
            c.text(f"{mm:02d}:{ss:02d}", 12, (150, 170, 205), bx + bw - 10, by + 15, "r")
        task = a.task or a.default_task
        c.text(c.fit(task, 14, bw - 28), 14, (240, 246, 255), bx + 14, by + 32, "l", bold=False)
        c.rect((24, 32, 54), bx + 14, by + 43, bw - 28, 3.5, 1.5)
        if a.status == "BUSY" and a.phase == "working":
            seg = 70
            sx = bx + 14 + ((t * 0.55) % 1.0) * (bw - 28 - seg)
            c.rect(col, sx, by + 43, seg, 3.5, 1.5)
        elif a.status == "BUSY":
            c.rect(_mix(col, (20, 20, 30), 0.4), bx + 14, by + 43, (bw - 28) * 0.18, 3.5, 1.5)
        else:
            c.rect((90, 220, 130), bx + 14, by + 43, bw - 28, 3.5, 1.5)

    def _draw_lamps(self, c, t):
        for aid, R in ROOMS.items():
            a = self.agents[aid]
            ly = 264 if R["side"] == "S" else 436
            busy = a.status == "BUSY"
            col = (255, 90, 90) if busy else (90, 225, 130)
            if busy:
                c.glow(col, R["cx"] + 44, ly, 12, 0.7)
            c.circle(col, R["cx"] + 44, ly, 3.4)
            c.text("IN USE" if busy else "AVAILABLE", 11, col, R["cx"] + 53, ly, "l")
        c.circle((90, 225, 255), 544, 436, 3.4)
        c.text("ONLINE", 11, (90, 225, 255), 553, 436, "l")

    # ---------------------------------------------------------- main draw
    def draw(self, surface, rect, t_ms=0.0, dt_ms=16.0):
        dt = max(0.001, min(0.1, dt_ms * 0.001))
        self._update(dt)
        t = self.time

        title_h, roster_h = 36, 62
        scene = pygame.Rect(rect.x + 6, rect.y + title_h, rect.w - 12, rect.h - title_h - roster_h)
        s = min(scene.w / LW, scene.h / LH)
        s = max(0.3, s)
        ox = scene.x + (scene.w - LW * s) / 2
        oy = scene.y + (scene.h - LH * s) / 2
        self._geom = (s, ox, oy)

        # panel frame
        bg = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(bg, (12, 17, 31, 235), bg.get_rect(), border_radius=14)
        surface.blit(bg, rect.topleft)
        pygame.draw.rect(surface, (40, 50, 80), rect, 1, border_radius=14)

        key = round(s, 3)
        if self._static is None or self._static_s != key:
            self._static = self._build_static(s)
            self._static_s = key
        prev = surface.get_clip()
        surface.set_clip(scene)
        surface.blit(self._static, (int(ox), int(oy)))

        c = Canvas(surface, s, ox, oy)
        busy_n = sum(1 for a in self.agents.values() if a.status == "BUSY")
        self._draw_rooms_dynamic(c, t)
        self._draw_hall_conduits(c, t)
        self._draw_core(c, t, busy_n)
        self._draw_lamps(c, t)

        for a in self.agents.values():
            for p in a.particles:
                k = p[4] / 0.9
                c.rect(_mix(a.color, (20, 24, 40), k), p[0], p[1], 3, 3, 1)
        for a in sorted(self.agents.values(), key=lambda q: q.y):
            self._draw_agent(c, a, t)
        for a in self.agents.values():
            self._draw_tag(c, a)
        for aid, a in self.agents.items():
            if a.status == "BUSY" or a.phase == "to_hall":
                self._draw_banner(c, aid, a, t)
        surface.set_clip(prev)

        # title bar
        tf = _font(13)
        surface.blit(tf.render("NEURA HQ  //  AGENT OFFICE", True, (225, 235, 255)), (rect.x + 16, rect.y + 11))
        mp = pygame.mouse.get_pos()
        self.btn_demo = pygame.Rect(rect.x + 232, rect.y + 8, 84, 22)
        self.btn_reset = pygame.Rect(rect.x + 322, rect.y + 8, 62, 22)
        for r, lab, on in ((self.btn_demo, "DEMO ON" if self.demo_mode else "DEMO OFF", self.demo_mode),
                           (self.btn_reset, "RESET", False)):
            hov = r.collidepoint(mp)
            pygame.draw.rect(surface, (0, 74, 112) if on else ((28, 42, 72) if hov else (16, 24, 44)), r, border_radius=11)
            pygame.draw.rect(surface, (0, 220, 255) if on else (52, 76, 120), r, 1, border_radius=11)
            im = _font(11).render(lab, True, (235, 245, 255) if (on or hov) else (170, 190, 220))
            surface.blit(im, im.get_rect(center=r.center))
        cnt = _font(12).render(f"ACTIVE  {busy_n}/{len(self.agents)}", True,
                               (90, 235, 160) if busy_n else (130, 150, 185))
        surface.blit(cnt, (rect.right - cnt.get_width() - 16, rect.y + 11))

        # roster
        self.chips = {}
        n = len(self.agents)
        gap = 6
        cw = (rect.w - 12 - gap * (n - 1)) / n
        for i, (aid, a) in enumerate(self.agents.items()):
            r = pygame.Rect(int(rect.x + 6 + i * (cw + gap)), rect.bottom - roster_h + 8, int(cw), roster_h - 16)
            self.chips[aid] = r
            busy = a.status == "BUSY"
            sel = aid == self.selected
            pygame.draw.rect(surface, (20, 28, 50) if sel else (14, 20, 38), r, border_radius=8)
            pygame.draw.rect(surface, a.color if (busy or sel) else (40, 54, 86), r, 1, border_radius=8)
            pygame.draw.circle(surface, a.color if busy else (110, 130, 165), (r.x + 12, r.y + 13), 4)
            surface.blit(_font(11).render(a.short, True, (235, 242, 255)), (r.x + 22, r.y + 5))
            st = _font(10).render("BUSY" if busy else "IDLE", True, a.color if busy else (130, 150, 185))
            surface.blit(st, (r.right - st.get_width() - 8, r.y + 6))
            txt = (a.task or a.default_task) if busy else "Standing by"
            f = _font(10, False)
            while txt and f.size(txt)[0] > r.w - 16:
                txt = txt[:-1]
            surface.blit(f.render(txt, True, (170, 188, 218)), (r.x + 8, r.y + 24))

        # click handling (polled so the host loop needs no changes)
        down = pygame.mouse.get_pressed()[0]
        if down and not self._prev_down and rect.collidepoint(mp):
            self._click(mp)
        self._prev_down = down

    def _click(self, mp):
        if self.btn_demo.collidepoint(mp):
            self.demo_mode = not self.demo_mode
            self.demo_timer = 0.0
            if not self.demo_mode:
                for a in self.agents.values():
                    a.set_idle()
            return True
        if self.btn_reset.collidepoint(mp):
            self.demo_mode = False
            for a in self.agents.values():
                a.set_idle()
            return True
        for aid, r in self.chips.items():
            if r.collidepoint(mp):
                self.selected = aid
                return True
        s, ox, oy = self._geom
        lx, ly = (mp[0] - ox) / s, (mp[1] - oy) / s
        best, bd = None, 20
        for aid, a in self.agents.items():
            d = math.hypot(a.x - lx, a.y - ly)
            if d < bd:
                best, bd = aid, d
        if best:
            self.selected = best
            return True
        return False

    # compatibility with the old class
    def handle_click(self, mpos, inner_rect):
        return self._click(mpos)