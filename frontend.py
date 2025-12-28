import pygame
import random
import math
import pyaudio
import struct
import cv2
import os
import sys
import subprocess
import psutil
from collections import deque
import json

# ------------- GLOBALS THAT WILL BE UPDATED -------------
CHAT_MESSAGES = deque(maxlen=25)
CHAT_SCROLL_OFFSET = 0
CHAT_BRIDGE_FILE = "chat_bridge.json"
LAST_CHAT_LEN = 0

WIDTH, HEIGHT = 500, 500
CENTER_X, CENTER_Y = WIDTH // 2, HEIGHT // 2

SPHERE_RADIUS_BASE = 250   # base radius
SPHERE_RADIUS = SPHERE_RADIUS_BASE
FOV = 650

BG_COLOR = (5, 8, 20)
SPHERE_OUTLINE_COLOR = (10, 10, 20)

ROT_Y_SPEED = 0.4
ROT_X_SPEED = 0.18

NUM_DOTS = 2000          # number of dots
GOLD = (160, 80, 255)

# Audio config (still used to react the HUD)
CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 44100

CPU_GRAPH = []
RAM_GRAPH = []
GPU_GRAPH = []
GRAPH_MAX_POINTS = 120

# --------- THEMES (for HUD inner colors) ---------
# Outer HUD stays cyan; only inner HUD colors change
THEMES = {
    1: {  # Blue + Orange/Gold (default)
        "name": "Orange / Gold",
        "quiet_core": (230, 120, 20),
        "loud_core": (255, 230, 80),
    },
    2: {  # Blue + Purple (cyber)
        "name": "Neon Purple",
        "quiet_core": (160, 80, 255),
        "loud_core": (255, 140, 255),
    },
    3: {  # White + Red (battle mode)
        "name": "Battle Red",
        "quiet_core": (230, 230, 230),
        "loud_core": (255, 80, 80),
    },
    4: {  # Green + Yellow (bio scanner)
        "name": "Bio Scanner",
        "quiet_core": (40, 200, 80),
        "loud_core": (220, 255, 140),
    },
}

current_theme = 1  # start with theme 1
ULTRA_BOLD = False  # toggle with 'U'

# --------- SPEAKING EFFECT (PULSES) ---------
VOICE_PULSES = []          # list of start times (ms)
VOICE_THRESHOLD = 0.15     # amplitude threshold to trigger a pulse
VOICE_PULSE_LIFE = 1200.0  # ms each pulse lives
last_amplitude = 0.0       # for edge detection


def recalc_layout(width, height):
    global WIDTH, HEIGHT, CENTER_X, CENTER_Y, SPHERE_RADIUS_BASE, SPHERE_RADIUS, FOV

    WIDTH, HEIGHT = width, height
    CENTER_X, CENTER_Y = WIDTH // 2, HEIGHT // 2

    # Sphere radius: use a percentage of the smallest dimension
    SPHERE_RADIUS_BASE = int(min(WIDTH, HEIGHT) * 0.32)
    SPHERE_RADIUS = SPHERE_RADIUS_BASE

    # FOV: scale with radius for consistent depth feeling
    FOV = SPHERE_RADIUS_BASE * 2.3


# -------------------- DOT ON SPHERE --------------------
class Dot:
    def __init__(self):
        # random point on sphere via spherical coordinates
        theta = random.uniform(0, 2 * math.pi)
        phi = random.uniform(0, math.pi)

        self.theta = theta
        self.phi = phi

        self.dtheta = random.uniform(-0.4, 0.4)
        self.dphi = random.uniform(-0.25, 0.25)

        self.x = 0
        self.y = 0
        self.z = 0

    def update(self, dt, rot_x, rot_y):
        # travel along the surface
        self.theta += self.dtheta * dt * 0.001
        self.phi += self.dphi * dt * 0.001

        # keep latitude in range
        if self.phi < 0:
            self.phi = -self.phi
            self.dphi *= -1
        elif self.phi > math.pi:
            self.phi = 2 * math.pi - self.phi
            self.dphi *= -1

        # spherical -> 3D cartesian (using current SPHERE_RADIUS)
        x = SPHERE_RADIUS * math.sin(self.phi) * math.cos(self.theta)
        y = SPHERE_RADIUS * math.cos(self.phi)
        z = SPHERE_RADIUS * math.sin(self.phi) * math.sin(self.theta)

        # rotate around Y axis
        cos_y = math.cos(rot_y)
        sin_y = math.sin(rot_y)
        xz = x * cos_y + z * sin_y
        zz = -x * sin_y + z * cos_y

        # rotate around X axis
        cos_x = math.cos(rot_x)
        sin_x = math.sin(rot_x)
        yz = y * cos_x - zz * sin_x
        zz2 = y * sin_x + zz * cos_x

        self.x, self.y, self.z = xz, yz, zz2

    def project(self):
        # camera along +z axis
        z_cam = self.z + SPHERE_RADIUS * 2.2
        if z_cam <= 1:
            z_cam = 1

        factor = FOV / z_cam

        sx = int(CENTER_X + self.x * factor)
        sy = int(CENTER_Y + self.y * factor)

        # depth factor [0..1], 1 = near front
        depth = max(0.0, min(1.0, 1 - (z_cam / (SPHERE_RADIUS_BASE * 3.0))))

        # radius scales with depth, min size ensures visibility
        radius = max(1, int(1 + depth * 3))

        r, g, b = GOLD
        brightness = 0.5 + depth * 0.7  # a bit brighter
        r = int(r * brightness)
        g = int(g * brightness)
        b = int(b * brightness)

        return sx, sy, radius, (r, g, b), depth


# -------------------- DRAW SHARP DOT --------------------
def draw_dot(surface, x, y, radius, color):
    pygame.draw.circle(surface, color, (x, y), radius)


# -------------------- UTILS --------------------
def lerp(a, b, t):
    return int(a + (b - a) * t)


def mix_color(c1, c2, t):
    """Blend two RGB colors with factor t in [0,1]."""
    return (
        lerp(c1[0], c2[0], t),
        lerp(c1[1], c2[1], t),
        lerp(c1[2], c2[2], t),
    )


# -------------------- TEXT WRAP UTILITY --------------------
def wrap_text(font, text, max_width):
    lines = []
    words = text.split(" ")
    current = ""

    for word in words:
        test = word if not current else current + " " + word
        if font.size(test)[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            # If a single word exceeds max_width, hard-wrap it
            if font.size(word)[0] > max_width:
                chunk = ""
                for ch in word:
                    test_chunk = chunk + ch
                    if font.size(test_chunk)[0] <= max_width:
                        chunk = test_chunk
                    else:
                        if chunk:
                            lines.append(chunk)
                        chunk = ch
                current = chunk
            else:
                current = word

    if current:
        lines.append(current)
    return lines


# -------------------- ADVANCED JARVIS HUD --------------------
def draw_sidd_hud(surface, t, amplitude):
    global ULTRA_BOLD, VOICE_PULSES

    center = (CENTER_X, CENTER_Y)
    ts = t * 0.001  # ms -> seconds

    # base size relative to screen
    base = int(min(WIDTH, HEIGHT) * 0.12)

    # smoother amplitude curve
    amp = min(max(amplitude, 0.0), 1.0)
    amp_visual = amp ** 0.7  # keeps it moving even with small sound

    # ---------- CONSTANT CYAN OUTER FRAME ----------
    CYAN = (0, 220, 255)
    CYAN_SOFT = (0, 170, 220)

    # thickness presets
    if ULTRA_BOLD:
        outer_ring_w = 5
        inner_ring_w = 3
        glow_ring_w = 2
        gap_arc_w = 3
        core_outline_w = 6
        flicker_ring_w = 3
        polygon_w = 3
        arc_ring_w = 4
        tick_w = 2
        scan_line_w = 2
        sweep_w = 6
        micro_dot_r = 3
        orbit_dot_r = 7
        pulse_w = 4
    else:
        outer_ring_w = 2
        inner_ring_w = 1
        glow_ring_w = 1
        gap_arc_w = 2
        core_outline_w = 3
        flicker_ring_w = 1
        polygon_w = 1
        arc_ring_w = 2
        tick_w = 1
        scan_line_w = 1
        sweep_w = 3
        micro_dot_r = 2
        orbit_dot_r = 5
        pulse_w = 2

    # ring radii
    r_inner_frame = int(base * 0.85)
    r_outer_frame = int(base * 1.4)
    r_outer_glow = int(base * 1.6)

    # outermost thin ring
    pygame.draw.circle(surface, CYAN_SOFT, center, r_outer_glow, glow_ring_w)
    # main outer ring
    pygame.draw.circle(surface, CYAN, center, r_outer_frame, outer_ring_w)
    # inner frame ring
    pygame.draw.circle(surface, CYAN, center, r_inner_frame, inner_ring_w)

    # spinning cyan "gaps" on the outer frame for subtle motion (color still cyan)
    gap_rect = pygame.Rect(0, 0, r_outer_frame * 2, r_outer_frame * 2)
    gap_rect.center = center
    gap_speed = 0.6
    for i in range(3):
        offset = ts * gap_speed + i * (2 * math.pi / 3)
        start_angle = offset
        end_angle = offset + math.pi / 7
        pygame.draw.arc(surface, CYAN_SOFT, gap_rect, start_angle, end_angle, gap_arc_w)

    # ---------- THEME-BASED INNER COLORS ----------
    theme = THEMES.get(current_theme, THEMES[1])
    quiet_core = theme["quiet_core"]
    loud_core = theme["loud_core"]
    inner_color = mix_color(quiet_core, loud_core, amp_visual)

    # ---------- PULSING CORE ----------
    core_radius = int(base * (0.45 + 0.25 * amp_visual))
    # outer core outline
    pygame.draw.circle(surface, inner_color, center, core_radius, core_outline_w)
    # inner flicker ring
    flicker_radius = int(core_radius * (0.5 + 0.2 * math.sin(ts * 4)))
    flicker_radius = max(4, flicker_radius)
    pygame.draw.circle(surface, inner_color, center, flicker_radius, flicker_ring_w)

    # ---------- ROTATING POLYGON "PROCESSOR" ----------
    sides = 6
    poly_radius = int(core_radius * 0.75)
    poly_angle_offset = ts * 1.2  # rotation speed
    poly_points = []
    for i in range(sides):
        ang = poly_angle_offset + (2 * math.pi * i / sides)
        x = CENTER_X + poly_radius * math.cos(ang)
        y = CENTER_Y + poly_radius * math.sin(ang)
        poly_points.append((x, y))
    pygame.draw.polygon(surface, inner_color, poly_points, polygon_w)

    # ---------- ARC RING (REACTIVE) ----------
    arc_radius = int(base * 1.05)
    arc_rect = pygame.Rect(0, 0, arc_radius * 2, arc_radius * 2)
    arc_rect.center = center
    num_arcs = 5
    for i in range(num_arcs):
        ang_off = ts * (0.9 + 0.2 * i)
        span = (math.pi / 7) + amp_visual * (math.pi / 10)
        start_ang = ang_off + i * (2 * math.pi / num_arcs)
        end_ang = start_ang + span
        pygame.draw.arc(surface, inner_color, arc_rect, start_ang, end_ang, arc_ring_w)

    # ---------- CYAN TICKS ON INNER FRAME ----------
    tick_count = 24
    tick_rot = ts * 0.5
    for i in range(tick_count):
        ang = tick_rot + (2 * math.pi * i / tick_count)
        r0 = r_inner_frame * 0.95
        r1 = r_inner_frame * 1.02
        x0 = CENTER_X + r0 * math.cos(ang)
        y0 = CENTER_Y + r0 * math.sin(ang)
        x1 = CENTER_X + r1 * math.cos(ang)
        y1 = CENTER_Y + r1 * math.sin(ang)
        pygame.draw.line(surface, CYAN_SOFT, (x0, y0), (x1, y1), tick_w)

    # ---------- RADIAL SCANNING LINES (REACTIVE) ----------
    num_lines = 18
    line_rot = ts * 1.8
    for i in range(num_lines):
        ang = line_rot + (2 * math.pi * i / num_lines)
        inner_r = core_radius * 1.05
        outer_r = r_inner_frame * (0.9 + 0.2 * amp_visual)
        x1 = CENTER_X + inner_r * math.cos(ang)
        y1 = CENTER_Y + inner_r * math.sin(ang)
        x2 = CENTER_X + outer_r * math.cos(ang)
        y2 = CENTER_Y + outer_r * math.sin(ang)
        pygame.draw.line(surface, inner_color, (x1, y1), (x2, y2), scan_line_w)

    # ---------- SWEEPING SCANNER BEAM ----------
    sweep_radius = r_outer_frame * 1.02
    sweep_rect = pygame.Rect(0, 0, sweep_radius * 2, sweep_radius * 2)
    sweep_rect.center = center
    sweep_angle = ts * 1.3
    sweep_span = math.pi / 20
    sweep_color = mix_color(inner_color, (255, 255, 255), 0.4)  # a bit brighter
    pygame.draw.arc(surface, sweep_color, sweep_rect, sweep_angle, sweep_angle + sweep_span, sweep_w)

    # ---------- ORBITING ENERGY DOT (REACTIVE) ----------
    orbit_r = r_inner_frame * 1.1
    orb_angle = ts * 2.2
    ox = CENTER_X + orbit_r * math.cos(orb_angle)
    oy = CENTER_Y + orbit_r * math.sin(orb_angle)

    orb_quiet = mix_color(inner_color, (255, 255, 255), 0.2)
    orb_loud = mix_color(inner_color, (255, 255, 255), 0.7)
    orb_color = mix_color(orb_quiet, orb_loud, amp_visual)
    pygame.draw.circle(surface, orb_color, (int(ox), int(oy)), orbit_dot_r)

    # ---------- INNER MICRO-DOTS (REACTIVE TEXTURE) ----------
    micro_count = 12
    for i in range(micro_count):
        ang = ts * 0.7 + i * (2 * math.pi / micro_count)
        r_m = core_radius * (0.3 + 0.5 * ((i % 3) / 2))
        x = CENTER_X + r_m * math.cos(ang)
        y = CENTER_Y + r_m * math.sin(ang)
        pygame.draw.circle(surface, inner_color, (int(x), int(y)), micro_dot_r)

    # ---------- SPEAKING PULSES (VOICE RINGS) ----------
    # expanding circles from core when voice pulses trigger
    alive_pulses = []
    for start_t in VOICE_PULSES:
        age = t - start_t  # ms
        if age < 0 or age > VOICE_PULSE_LIFE:
            continue
        alive_pulses.append(start_t)

        # 0..1 progress
        p = age / VOICE_PULSE_LIFE
        # radius from just outside core to near outer frame
        pulse_radius = core_radius * 1.2 + p * (r_outer_frame * 0.95 - core_radius * 1.2)
        # fade color from bright inner_color to cyan soft
        pulse_color = mix_color(inner_color, CYAN_SOFT, p)
        pygame.draw.circle(surface, pulse_color, center, int(pulse_radius), pulse_w)

    VOICE_PULSES = alive_pulses


# -------------------- ANALYTICS PANELS OUTSIDE SPHERE --------------------
def draw_analytics(surface, t, amplitude, fps):
    global current_theme, ULTRA_BOLD

    # --- Colors ---
    panel_bg = (10, 15, 35)
    panel_border = (40, 60, 120)
    text_color = (200, 220, 255)

    theme = THEMES.get(current_theme, THEMES[1])
    theme_name = theme["name"]
    amp_pct = int(amplitude * 100)

    # smoother amp for visuals
    amp_visual = min(max(amplitude, 0.0), 1.0) ** 0.8

    # --- FONT ---
    font_small = pygame.font.SysFont("consolas", 16)
    font_tiny = pygame.font.SysFont("consolas", 13)

    # ---------- TOP-LEFT INFO PANEL ----------
    info_w, info_h = 230, 110
    info_x, info_y = 20, 20
    info_rect = pygame.Rect(info_x, info_y, info_w, info_h)

    pygame.draw.rect(surface, panel_bg, info_rect, border_radius=8)
    pygame.draw.rect(surface, panel_border, info_rect, 1, border_radius=8)

    lines = [
        f"NEURA — ANALYTICS",
        f"Ultra-Bold: {'ON' if ULTRA_BOLD else 'OFF'}",
        f"Amplitude: {amp_pct:3d} %",
        f"FPS: {int(fps):3d}",
    ]
    for i, text in enumerate(lines):
        surf = font_small.render(text, True, text_color)
        surface.blit(surf, (info_x + 10, info_y + 8 + i * 18))

    # ---------- BOTTOM-CENTER AUDIO LEVEL BAR ----------
    bar_w, bar_h = 320, 16
    bar_x = CENTER_X - bar_w // 2
    bar_y = HEIGHT - bar_h - 30

    outer_bar = pygame.Rect(bar_x, bar_y, bar_w, bar_h)
    pygame.draw.rect(surface, panel_bg, outer_bar, border_radius=8)
    pygame.draw.rect(surface, panel_border, outer_bar, 1, border_radius=8)

    # fill based on amplitude
    fill_w = int(bar_w * amp_visual)
    if fill_w > 0:
        # green → yellow → red based on amplitude
        low = (80, 200, 120)
        high = (255, 80, 80)
        fill_color = mix_color(low, high, amp_visual)
        inner_bar = pygame.Rect(bar_x + 2, bar_y + 2, fill_w - 4 if fill_w > 4 else 0, bar_h - 4)
        if inner_bar.width > 0:
            pygame.draw.rect(surface, fill_color, inner_bar, border_radius=6)

    # label
    label = font_tiny.render("VOICE LEVEL", True, text_color)
    surface.blit(label, (bar_x, bar_y - 16))

        # ---------- BOTTOM-RIGHT SYSTEM PERFORMANCE GRAPH ----------
        # ---------- TASK MANAGER STYLE PERFORMANCE PANEL ----------
    panel_w, panel_h = 300, 240
    panel_x = WIDTH - panel_w - 20
    panel_y = HEIGHT - panel_h - 30

    perf_rect = pygame.Rect(panel_x, panel_y, panel_w, panel_h)
    pygame.draw.rect(surface, panel_bg, perf_rect, border_radius=8)
    pygame.draw.rect(surface, panel_border, perf_rect, 1, border_radius=8)

    # -------- Collect System Stats --------
    cpu_usage = psutil.cpu_percent(interval=0)
    ram_info = psutil.virtual_memory()
    ram_usage = ram_info.percent

    # GPU temperature if available
    try:
        gpu_temp = psutil.sensors_temperatures().get("gpu", None)
        gpu_temp = gpu_temp[0].current if gpu_temp else None
    except:
        gpu_temp = None

    # -------- Update Graph Buffers --------
    CPU_GRAPH.append(cpu_usage)
    RAM_GRAPH.append(ram_usage)
    if gpu_temp:
        GPU_GRAPH.append(gpu_temp)
    else:
        GPU_GRAPH.append(0)

    # Trim graphs to max length
    CPU_GRAPH[:] = CPU_GRAPH[-GRAPH_MAX_POINTS:]
    RAM_GRAPH[:] = RAM_GRAPH[-GRAPH_MAX_POINTS:]
    GPU_GRAPH[:] = GPU_GRAPH[-GRAPH_MAX_POINTS:]

    # -------- Draw Grid Like Task Manager --------
    grid_cols = 12
    grid_rows = 6
    cell_w = panel_w / grid_cols
    cell_h = panel_h / grid_rows

    for i in range(grid_cols):
        x = panel_x + i * cell_w
        pygame.draw.line(surface, (30, 45, 70), (x, panel_y), (x, panel_y + panel_h), 1)

    for j in range(grid_rows):
        y = panel_y + j * cell_h
        pygame.draw.line(surface, (30, 45, 70), (panel_x, y), (panel_x + panel_w, y), 1)

    # -------- Helper: Draw a Line Graph (clipped to panel) --------
    def draw_line_graph(values, color, section_offset, section_height):
        """
        Draw a line graph within a specific section of the panel.
        section_offset: y-offset from panel_y where this section starts
        section_height: height allocated for this section
        """
        if len(values) < 2:
            return
        
        # Define the section bounds
        section_y = panel_y + section_offset
        section_bottom = section_y + section_height
        
        prev = None
        for i, v in enumerate(values):
            x = panel_x + 2 + (i / GRAPH_MAX_POINTS) * (panel_w - 4)
            # Scale value (0-100) to section height, baseline at bottom
            y = section_bottom - (v / 100.0) * section_height
            # Clamp y to section bounds
            y = max(section_y, min(section_bottom, y))
            
            if prev:
                pygame.draw.line(surface, color, prev, (x, y), 2)
            prev = (x, y)

    # Divide panel into 3 sections for CPU, RAM, GPU
    section_h = panel_h // 3
    
    # -------- CPU Graph (Green) - Top Section --------
    draw_line_graph(CPU_GRAPH, (80, 220, 120), 10, section_h - 15)

    # -------- RAM Graph (Purple) - Middle Section --------
    draw_line_graph(RAM_GRAPH, (160, 80, 255), section_h + 10, section_h - 15)

    # -------- GPU Graph (Orange) - Bottom Section --------
    if gpu_temp:
        draw_line_graph(GPU_GRAPH, (255, 180, 80), section_h * 2 + 10, section_h - 15)

    # -------- Text Labels --------
    label_cpu = font_tiny.render(f"CPU: {cpu_usage:.1f} %", True, (200, 255, 200))
    label_ram = font_tiny.render(f"Memory: {ram_usage:.1f} %", True, (230, 200, 255))
    label_gpu = font_tiny.render(f"GPU Temp: {gpu_temp:.1f}°C" if gpu_temp else "GPU: N/A", True, (255, 220, 170))

    surface.blit(label_cpu, (panel_x + 10, panel_y + 10))
    surface.blit(label_ram, (panel_x + 10, panel_y + 90))
    surface.blit(label_gpu, (panel_x + 10, panel_y + 170))


def fetch_chat_from_backend():
    global LAST_CHAT_LEN, CHAT_SCROLL_OFFSET

    if not os.path.exists(CHAT_BRIDGE_FILE):
        return

    try:
        with open(CHAT_BRIDGE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if len(data) > LAST_CHAT_LEN:
            new_msgs = data[LAST_CHAT_LEN:]
            for msg in new_msgs:
                prefix = "You" if msg["role"] == "user" else "Neura"
                CHAT_MESSAGES.append(f"{prefix}: {msg['message']}")
                CHAT_SCROLL_OFFSET = 0
            LAST_CHAT_LEN = len(data)

    except Exception as e:
        print("Frontend chat read error:", e)

# -------------------- Conversation Pannel --------------------
def draw_chat_panel(surface):
    # Medium size, positioned just below the top-left analytics panel
    panel_w = 300
    panel_h = int(HEIGHT * 0.5)
    panel_x = 20
    # Top-left analytics: info_y=20, info_h=110; add a slight gap (12px)
    panel_y = 20 + 110 + 12

    bg = (10, 15, 35)
    border = (40, 80, 160)

    panel_rect = pygame.Rect(panel_x, panel_y, panel_w, panel_h)
    pygame.draw.rect(surface, bg, panel_rect, border_radius=10)
    pygame.draw.rect(surface, border, panel_rect, 1, border_radius=10)

    font = pygame.font.SysFont("consolas", 15)

    inner_pad = 12
    inner_x = panel_x + inner_pad
    inner_y = panel_y + inner_pad + 3
    inner_w = panel_w - inner_pad * 2
    line_h = font.get_linesize()

    # Collect wrapped lines for all messages
    all_lines = []
    for msg in CHAT_MESSAGES:
        wrapped = wrap_text(font, msg, inner_w)
        all_lines.extend(wrapped)

    # Compute how many lines fit vertically
    max_lines = max(0, (panel_h - inner_pad * 2) // line_h)
    max_scroll = max(0, len(all_lines) - max_lines)
    scroll = min(CHAT_SCROLL_OFFSET, max_scroll)
    start_idx = max(0, len(all_lines) - max_lines - scroll)

    # Clip drawing to panel to prevent overflow
    prev_clip = surface.get_clip()
    surface.set_clip(panel_rect)

    y = inner_y
    for line in all_lines[start_idx:]:
        text = font.render(line, True, (200, 220, 255))
        surface.blit(text, (inner_x, y))
        y += line_h

    surface.set_clip(prev_clip)


# -------------------- MAIN LOOP --------------------
def main():
    pygame.init()

    global SPHERE_RADIUS, current_theme, ULTRA_BOLD, last_amplitude, VOICE_PULSES, CHAT_SCROLL_OFFSET

    # ---- START SIDD AI BACKEND (AI.py) ----
    ai_process = None
    try:
        # AI.py is assumed to be in the same folder as frontend.py
        script_dir = os.path.dirname(os.path.abspath(__file__))
        ai_script = os.path.join(script_dir, "neura.py")

        ai_process = subprocess.Popen([sys.executable, ai_script])
        print("AI backend started:", ai_script)
    except Exception as e:
        print("Could not start AI backend:", e)

    # get current display resolution and start in a resizable window
    info = pygame.display.Info()
    start_w, start_h = info.current_w // 1, info.current_h // 1

    recalc_layout(start_w, start_h)
    screen = pygame.display.set_mode((start_w, start_h), pygame.RESIZABLE)
    pygame.display.set_caption("Audio Reactive Golden Sphere + Jarvis HUD + Analytics")

    clock = pygame.time.Clock()

    dots = [Dot() for _ in range(NUM_DOTS)]

    # ---- Audio setup ----
    pa = pyaudio.PyAudio()
    stream = pa.open(
        format=FORMAT,
        channels=CHANNELS,
        rate=RATE,
        input=True,
        frames_per_buffer=CHUNK
    )

    # ---- CAMERA SETUP ----
    cam = cv2.VideoCapture(0)
    cam.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
    cam.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)


    rot_x = 0.0
    rot_y = 0.0
    t = 0.0  # time for animation (ms)

    running = True
    try:
        while running:
            dt = clock.tick(60)
            t += dt  # time in ms

            if ai_process is not None and ai_process.poll() is not None:
                print("Backend stopped. Closing frontend...")
                running = False
                break
            
            # ---- READ CAMERA FRAME ----
            ret, frame = cam.read()
            if ret:
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                frame = cv2.flip(frame, 1)
                cam_surface = pygame.surfarray.make_surface(frame.swapaxes(0, 1))
            else:
                cam_surface = None

            for event in pygame.event.get():
                if event.type == pygame.MOUSEWHEEL:
                    mx, my = pygame.mouse.get_pos()

                    panel_x = 20
                    panel_y = 20 + 110 + 12
                    panel_w = 300
                    panel_h = int(HEIGHT * 0.5)

                    if panel_x <= mx <= panel_x + panel_w and panel_y <= my <= panel_y + panel_h:
                        CHAT_SCROLL_OFFSET -= event.y * 3
                        CHAT_SCROLL_OFFSET = max(0, CHAT_SCROLL_OFFSET)

                if event.type == pygame.QUIT:
                    running = False

                # handle window resize
                if event.type == pygame.VIDEORESIZE:
                    new_w, new_h = event.w, event.h
                    recalc_layout(new_w, new_h)
                    screen = pygame.display.set_mode((new_w, new_h), pygame.RESIZABLE)

                # -------- THEME SWITCH KEYS (1–4) + ULTRA BOLD (U) --------
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_1:
                        current_theme = 1
                    elif event.key == pygame.K_2:
                        current_theme = 2
                    elif event.key == pygame.K_3:
                        current_theme = 3
                    elif event.key == pygame.K_4:
                        current_theme = 4
                    elif event.key == pygame.K_u:
                        ULTRA_BOLD = not ULTRA_BOLD

            # ---- Read audio chunk & compute amplitude ----
            data = stream.read(CHUNK, exception_on_overflow=False)
            samples = struct.unpack(str(CHUNK) + 'h', data)

            # RMS (root mean square) for volume
            sum_squares = 0.0
            for s in samples:
                sum_squares += s * s
            rms = math.sqrt(sum_squares / CHUNK)

            # Normalize RMS to [0,1] (tune 3000 for sensitivity)
            amplitude = min(rms / 3000.0, 1.0)

            # ----- SPEAKING PULSE TRIGGER (on rising edge over threshold) -----
            if amplitude > VOICE_THRESHOLD and last_amplitude <= VOICE_THRESHOLD:
                VOICE_PULSES.append(t)
            last_amplitude = amplitude

            # sphere radius fixed
            SPHERE_RADIUS = SPHERE_RADIUS_BASE

            # global sphere rotation
            rot_y += ROT_Y_SPEED * dt * 0.001
            rot_x += ROT_X_SPEED * dt * 0.001

            # update dot positions
            for d in dots:
                d.update(dt, rot_x, rot_y)

            # draw farthest first
            dots_sorted = sorted(dots, key=lambda d: d.z)

            # ---- DRAW ----
            fetch_chat_from_backend()
            screen.fill(BG_COLOR)

            # ---- DRAW CAMERA WINDOW ----
            if cam_surface:
                cam_w = 320
                cam_h = 240
                cam_x = WIDTH - cam_w - 30
                cam_y = 30

                # Background frame box
                pygame.draw.rect(screen, (15, 20, 40), (cam_x - 5, cam_y - 5, cam_w + 10, cam_h + 10), border_radius=8)

                # Border
                pygame.draw.rect(screen, (0, 180, 255), (cam_x - 5, cam_y - 5, cam_w + 10, cam_h + 10), 2, border_radius=8)

                # Camera feed
                screen.blit(pygame.transform.scale(cam_surface, (cam_w, cam_h)), (cam_x, cam_y))


            # sphere outline
            pygame.draw.circle(
                screen,
                SPHERE_OUTLINE_COLOR,
                (CENTER_X, CENTER_Y),
                int(SPHERE_RADIUS * 0.9),
                1
            )

            # sphere dots
            for d in dots_sorted:
                sx, sy, radius, color, depth = d.project()
                if 0 <= sx < WIDTH and 0 <= sy < HEIGHT:
                    draw_dot(screen, sx, sy, radius, color)

            # Jarvis HUD always on top, inside sphere
            draw_sidd_hud(screen, t, amplitude)

            # Working analytics around the sphere
            fps = clock.get_fps()
            # Draw chat first, then analytics so analytics appear above
            draw_analytics(screen, t, amplitude, fps)
            draw_chat_panel(screen)

            pygame.display.flip()
    finally:
        # clean up audio
        stream.stop_stream()
        stream.close()
        pa.terminate()
        pygame.quit()
        cam.release()

        # ---- STOP SIDD AI BACKEND ----
        if ai_process is not None and ai_process.poll() is None:
            try:
                ai_process.terminate()
                ai_process.wait(timeout=5)
                print("AI backend terminated.")
            except Exception as e:
                print("Error terminating AI backend:", e)


if __name__ == "__main__":
    main()
