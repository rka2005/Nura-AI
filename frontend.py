import pygame
import random
import math
import pyaudio
import struct
import cv2
import os
import sys
import subprocess
import webbrowser
import psutil
from collections import deque
import json
import time
import datetime

# ------------- CONFIGURATION & BRIDGES -------------
CHAT_BRIDGE_FILE = "chat_bridge.json"
INPUT_BRIDGE_FILE = "input_bridge.json"
STATUS_BRIDGE_FILE = "status_bridge.json"

CHAT_MESSAGES = deque(maxlen=40)  # Stores dicts: {"role": ..., "message": ..., "time": ...}
CHAT_SCROLL_OFFSET = 0
LAST_CHAT_SIGNATURE = None

# Screen dimensions (dynamically updated)
WIDTH, HEIGHT = 1400, 850
CENTER_X, CENTER_Y = WIDTH // 2, HEIGHT // 2

# 3D Sphere Configuration
SPHERE_RADIUS_BASE = 240
SPHERE_RADIUS = SPHERE_RADIUS_BASE
FOV = 600
NUM_DOTS = 1800
ROT_Y_SPEED = 0.35
ROT_X_SPEED = 0.16

# Audio Configuration
CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 44100
SPECTRUM_BANDS = 24
spectrum_heights = [0.0] * SPECTRUM_BANDS

# Telemetry History
CPU_GRAPH = []
RAM_GRAPH = []
GPU_GRAPH = []
GRAPH_MAX_POINTS = 100
GPU_STATS = {"usage": None, "memory": None, "updated_at": 0.0}
MEMORY_CACHE = {"data": {}, "updated_at": 0.0}

# Action Status & Notifications
ACTION_STATUS = "SYSTEM OPERATIONAL // READY"
ACTION_STATUS_UNTIL = 0
ASSISTANT_STATUS = "READY"
LAST_STATUS_CHECK = 0.0

# Camera Controls
CAMERA_ENABLED = True
CAMERA_SURFACE = None

# Microphone Controls
MIC_MUTED = False

# Quick Actions
QUICK_ACTIONS = [
    ("JOKE", "joke", "tell a joke", (255, 200, 80)),
    ("WEATHER", "weather", "weather", (80, 210, 255)),
    ("MEMORY", "memory", "what do you know about me", (140, 240, 160)),
    ("MUSIC", "music", "open youtube", (255, 120, 120)),
    ("FILES", "files", "open files", (180, 150, 255)),
    ("TASKMGR", "taskmgr", "open task manager", (120, 255, 220)),
]

# Themes (HUD & Accent Palettes)
THEMES = {
    1: {
        "name": "Orange / Gold",
        "primary": (255, 175, 40),
        "primary_soft": (200, 130, 25),
        "accent": (255, 215, 80),
        "sphere_dots": (255, 190, 70),
        "quiet_core": (220, 110, 20),
        "loud_core": (255, 230, 90),
    },
    2: {
        "name": "Neon Purple",
        "primary": (170, 90, 255),
        "primary_soft": (130, 60, 210),
        "accent": (230, 130, 255),
        "sphere_dots": (180, 110, 255),
        "quiet_core": (150, 60, 240),
        "loud_core": (255, 160, 255),
    },
    3: {
        "name": "Battle Red",
        "primary": (255, 75, 75),
        "primary_soft": (200, 45, 45),
        "accent": (255, 140, 140),
        "sphere_dots": (255, 95, 95),
        "quiet_core": (200, 40, 40),
        "loud_core": (255, 120, 120),
    },
    4: {
        "name": "Bio Matrix",
        "primary": (50, 225, 130),
        "primary_soft": (35, 175, 95),
        "accent": (160, 255, 180),
        "sphere_dots": (70, 230, 140),
        "quiet_core": (30, 180, 80),
        "loud_core": (200, 255, 160),
    },
}

current_theme = 1
ULTRA_BOLD = False

# Voice Pulse Effect
VOICE_PULSES = []
VOICE_THRESHOLD = 0.14
VOICE_PULSE_LIFE = 1100.0
last_amplitude = 0.0

# Text Input State
USER_INPUT_TEXT = ""
INPUT_ACTIVE = True
CURSOR_VISIBLE = True
LAST_CURSOR_BLINK = 0

# Colors
COLOR_BG = (6, 10, 22)
COLOR_PANEL_BG = (10, 17, 36)
COLOR_PANEL_BORDER = (32, 58, 105)
COLOR_TEXT_WHITE = (235, 245, 255)
COLOR_TEXT_DIM = (135, 165, 205)
COLOR_CYAN = (0, 220, 255)
COLOR_CYAN_DIM = (0, 150, 190)

# Layout Rectangles (Computed dynamically)
LAYOUT = {}


# -------------------- RESPONSIVE LAYOUT ENGINE --------------------
def recalc_layout(width, height):
    global WIDTH, HEIGHT, CENTER_X, CENTER_Y, SPHERE_RADIUS_BASE, SPHERE_RADIUS, FOV, LAYOUT

    WIDTH = max(1000, width)
    HEIGHT = max(680, height)
    CENTER_X, CENTER_Y = WIDTH // 2, HEIGHT // 2

    # Proportional column sizing
    left_w = int(max(330, min(420, WIDTH * 0.27)))
    right_w = int(max(320, min(400, WIDTH * 0.26)))

    header_h = 52
    status_bar_h = 30
    pad = 14

    content_y = header_h + pad
    content_h = HEIGHT - content_y - status_bar_h - pad

    # Left Column: Chat & Interactive Command Hub
    left_x = pad
    input_box_h = 44
    quick_act_h = 76
    chat_h = content_h - input_box_h - quick_act_h - (pad * 2)

    LAYOUT["header"] = pygame.Rect(0, 0, WIDTH, header_h)
    LAYOUT["status_bar"] = pygame.Rect(0, HEIGHT - status_bar_h, WIDTH, status_bar_h)

    LAYOUT["chat_panel"] = pygame.Rect(left_x, content_y, left_w, chat_h)
    LAYOUT["quick_actions"] = pygame.Rect(left_x, content_y + chat_h + pad, left_w, quick_act_h)
    LAYOUT["input_box"] = pygame.Rect(left_x, content_y + chat_h + quick_act_h + (pad * 2), left_w, input_box_h)

    # Right Column: Vision, Memory, Hardware Performance
    right_x = WIDTH - right_w - pad
    cam_h = int(content_h * 0.31)
    mem_h = int(content_h * 0.30)
    perf_h = content_h - cam_h - mem_h - (pad * 2)

    LAYOUT["cam_panel"] = pygame.Rect(right_x, content_y, right_w, cam_h)
    LAYOUT["mem_panel"] = pygame.Rect(right_x, content_y + cam_h + pad, right_w, mem_h)
    LAYOUT["perf_panel"] = pygame.Rect(right_x, content_y + cam_h + mem_h + (pad * 2), right_w, perf_h)

    # Center Column Area
    center_w = right_x - (left_x + left_w) - (pad * 2)
    center_x = left_x + left_w + pad
    LAYOUT["center_area"] = pygame.Rect(center_x, content_y, center_w, content_h)

    # Center sphere placement
    CENTER_X = center_x + center_w // 2
    CENTER_Y = content_y + int(content_h * 0.44)

    SPHERE_RADIUS_BASE = int(min(center_w, content_h) * 0.31)
    SPHERE_RADIUS = SPHERE_RADIUS_BASE
    FOV = SPHERE_RADIUS_BASE * 2.3

    # Center bottom audio spectrum
    spectrum_w = min(460, center_w - 20)
    spectrum_h = 56
    LAYOUT["spectrum"] = pygame.Rect(CENTER_X - spectrum_w // 2, content_y + content_h - spectrum_h - 8, spectrum_w, spectrum_h)


# -------------------- 3D AUDIO-REACTIVE SPHERE --------------------
class Dot:
    def __init__(self):
        theta = random.uniform(0, 2 * math.pi)
        phi = random.uniform(0, math.pi)
        self.theta = theta
        self.phi = phi
        self.dtheta = random.uniform(-0.35, 0.35)
        self.dphi = random.uniform(-0.2, 0.2)
        self.x, self.y, self.z = 0, 0, 0

    def update(self, dt, rot_x, rot_y):
        self.theta += self.dtheta * dt * 0.001
        self.phi += self.dphi * dt * 0.001

        if self.phi < 0:
            self.phi = -self.phi
            self.dphi *= -1
        elif self.phi > math.pi:
            self.phi = 2 * math.pi - self.phi
            self.dphi *= -1

        x = SPHERE_RADIUS * math.sin(self.phi) * math.cos(self.theta)
        y = SPHERE_RADIUS * math.cos(self.phi)
        z = SPHERE_RADIUS * math.sin(self.phi) * math.sin(self.theta)

        cos_y = math.cos(rot_y)
        sin_y = math.sin(rot_y)
        xz = x * cos_y + z * sin_y
        zz = -x * sin_y + z * cos_y

        cos_x = math.cos(rot_x)
        sin_x = math.sin(rot_x)
        yz = y * cos_x - zz * sin_x
        zz2 = y * sin_x + zz * cos_x

        self.x, self.y, self.z = xz, yz, zz2

    def project(self):
        z_cam = self.z + SPHERE_RADIUS * 2.2
        if z_cam <= 1:
            z_cam = 1
        factor = FOV / z_cam

        sx = int(CENTER_X + self.x * factor)
        sy = int(CENTER_Y + self.y * factor)

        depth = max(0.0, min(1.0, 1.0 - (z_cam / (SPHERE_RADIUS_BASE * 3.0))))
        radius = max(1, int(1 + depth * 3))

        theme = THEMES.get(current_theme, THEMES[1])
        base_color = theme["sphere_dots"]
        brightness = 0.45 + depth * 0.65
        r = int(min(255, base_color[0] * brightness))
        g = int(min(255, base_color[1] * brightness))
        b = int(min(255, base_color[2] * brightness))

        return sx, sy, radius, (r, g, b)


# -------------------- MATH & COLOR HELPERS --------------------
def lerp(a, b, t):
    return int(a + (b - a) * t)

def mix_color(c1, c2, t):
    t = max(0.0, min(1.0, t))
    return (
        lerp(c1[0], c2[0], t),
        lerp(c1[1], c2[1], t),
        lerp(c1[2], c2[2], t),
    )

def wrap_text(font, text, max_width):
    lines = []
    paragraphs = text.split("\n")
    for para in paragraphs:
        if not para:
            lines.append("")
            continue
        words = para.split(" ")
        current = ""
        for word in words:
            test = word if not current else current + " " + word
            if font.size(test)[0] <= max_width:
                current = test
            else:
                if current:
                    lines.append(current)
                if font.size(word)[0] > max_width:
                    chunk = ""
                    for ch in word:
                        if font.size(chunk + ch)[0] <= max_width:
                            chunk += ch
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


# -------------------- FUTURISTIC HUD GLASS PANEL --------------------
def draw_glass_panel(surface, rect, title="", accent=None, badge=None):
    if accent is None:
        theme = THEMES.get(current_theme, THEMES[1])
        accent = theme["primary"]

    # Glass background with soft border
    bg_surf = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
    bg_surf.fill((10, 17, 36, 215))
    surface.blit(bg_surf, (rect.x, rect.y))

    pygame.draw.rect(surface, (28, 48, 90), rect, 1, border_radius=8)

    # Cyber Corner Brackets [+]
    bracket_len = 8
    pygame.draw.line(surface, accent, (rect.x, rect.y), (rect.x + bracket_len, rect.y), 2)
    pygame.draw.line(surface, accent, (rect.x, rect.y), (rect.x, rect.y + bracket_len), 2)
    pygame.draw.line(surface, accent, (rect.right - bracket_len, rect.y), (rect.right, rect.y), 2)
    pygame.draw.line(surface, accent, (rect.right, rect.y), (rect.right, rect.y + bracket_len), 2)
    pygame.draw.line(surface, accent, (rect.x, rect.bottom), (rect.x + bracket_len, rect.bottom), 2)
    pygame.draw.line(surface, accent, (rect.x, rect.bottom - bracket_len), (rect.x, rect.bottom), 2)
    pygame.draw.line(surface, accent, (rect.right - bracket_len, rect.bottom), (rect.right, rect.bottom), 2)
    pygame.draw.line(surface, accent, (rect.right, rect.bottom - bracket_len), (rect.right, rect.bottom), 2)

    # Top accent line
    pygame.draw.line(surface, accent, (rect.x + 14, rect.y + 1), (rect.x + 65, rect.y + 1), 2)

    # Header title
    if title:
        title_font = pygame.font.SysFont("consolas", 12, bold=True)
        t_surf = title_font.render(title, True, (215, 235, 255))
        surface.blit(t_surf, (rect.x + 14, rect.y + 8))

    # Badge in top right of panel
    if badge:
        b_font = pygame.font.SysFont("consolas", 10, bold=True)
        b_surf = b_font.render(badge, True, accent)
        surface.blit(b_surf, (rect.right - b_surf.get_width() - 14, rect.y + 9))


# -------------------- COMMAND & BRIDGE HELPERS --------------------
def send_command_to_backend(command_text):
    global ACTION_STATUS, ACTION_STATUS_UNTIL, CHAT_SCROLL_OFFSET
    if not command_text or not command_text.strip():
        return
    clean_cmd = command_text.strip()
    try:
        cmds = []
        if os.path.exists(INPUT_BRIDGE_FILE):
            try:
                with open(INPUT_BRIDGE_FILE, "r", encoding="utf-8") as f:
                    cmds = json.load(f)
                    if not isinstance(cmds, list):
                        cmds = []
            except Exception:
                cmds = []

        cmds.append(clean_cmd)
        temp_file = f"{INPUT_BRIDGE_FILE}.tmp"
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(cmds, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_file, INPUT_BRIDGE_FILE)

        # Optimistically record in chat panel
        now_str = datetime.datetime.now().strftime("%H:%M:%S")
        CHAT_MESSAGES.append({"role": "user", "message": clean_cmd, "time": now_str})
        CHAT_SCROLL_OFFSET = 0

        ACTION_STATUS = f"DISPATCHED: {clean_cmd.upper()[:28]}"
        ACTION_STATUS_UNTIL = pygame.time.get_ticks() + 2500
    except Exception as e:
        ACTION_STATUS = f"CMD BRIDGE ERR: {e}"
        ACTION_STATUS_UNTIL = pygame.time.get_ticks() + 2500


def clear_chat_history():
    global CHAT_MESSAGES, LAST_CHAT_SIGNATURE, ACTION_STATUS, ACTION_STATUS_UNTIL
    try:
        with open(CHAT_BRIDGE_FILE, "w", encoding="utf-8") as f:
            json.dump([], f)
        CHAT_MESSAGES.clear()
        LAST_CHAT_SIGNATURE = None
        ACTION_STATUS = "CHAT SESSION CLEARED"
        ACTION_STATUS_UNTIL = pygame.time.get_ticks() + 2000
    except Exception as e:
        ACTION_STATUS = f"CLEAR ERROR: {e}"
        ACTION_STATUS_UNTIL = pygame.time.get_ticks() + 2000


def fetch_chat_from_backend():
    global LAST_CHAT_SIGNATURE, CHAT_SCROLL_OFFSET

    if not os.path.exists(CHAT_BRIDGE_FILE):
        return

    try:
        with open(CHAT_BRIDGE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        signature = [(msg.get("time"), msg.get("role"), msg.get("message")) for msg in data]
        if signature != LAST_CHAT_SIGNATURE:
            old_signature = LAST_CHAT_SIGNATURE or []
            common_prefix = 0
            while common_prefix < len(old_signature) and common_prefix < len(signature):
                if old_signature[common_prefix] != signature[common_prefix]:
                    break
                common_prefix += 1

            new_msgs = data[common_prefix:]
            if common_prefix == 0:
                CHAT_MESSAGES.clear()

            for msg in new_msgs:
                role = msg.get("role", "neura")
                text = msg.get("message", "")
                mtime = msg.get("time", "")
                CHAT_MESSAGES.append({"role": role, "message": text, "time": mtime})
                CHAT_SCROLL_OFFSET = 0
            LAST_CHAT_SIGNATURE = signature

    except (OSError, json.JSONDecodeError, TypeError):
        pass


def update_assistant_status():
    global ASSISTANT_STATUS, LAST_STATUS_CHECK
    now = time.time()
    if now - LAST_STATUS_CHECK < 0.2:
        return
    LAST_STATUS_CHECK = now
    if os.path.exists(STATUS_BRIDGE_FILE):
        try:
            with open(STATUS_BRIDGE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                stat = data.get("status", "READY")
                ASSISTANT_STATUS = stat
        except Exception:
            pass


# -------------------- TOP CYBER HEADER BAR --------------------
def draw_header_bar(surface):
    global current_theme, ULTRA_BOLD, MIC_MUTED, CAMERA_ENABLED
    header_rect = LAYOUT["header"]
    theme = THEMES.get(current_theme, THEMES[1])
    accent = theme["primary"]

    # Header Background
    header_surf = pygame.Surface((header_rect.width, header_rect.height), pygame.SRCALPHA)
    header_surf.fill((8, 13, 28, 240))
    surface.blit(header_surf, (0, 0))
    pygame.draw.line(surface, (30, 52, 95), (0, header_rect.bottom - 1), (WIDTH, header_rect.bottom - 1), 1)
    pygame.draw.line(surface, accent, (0, header_rect.bottom - 2), (260, header_rect.bottom - 2), 2)

    mouse_pos = pygame.mouse.get_pos()

    # 1. Branding / Logo
    logo_font = pygame.font.SysFont("consolas", 16, bold=True)
    tag_font = pygame.font.SysFont("consolas", 10, bold=True)

    logo_text = logo_font.render("NEURA", True, (245, 250, 255))
    surface.blit(logo_text, (18, 12))

    core_tag = tag_font.render("// COGNITIVE CORE v2.5", True, accent)
    surface.blit(core_tag, (76, 17))

    # 2. Status Badge with pulsing indicator
    pulse = (math.sin(pygame.time.get_ticks() * 0.006) + 1.0) * 0.5
    status_x = 290
    status_y = 14
    status_w = 140
    status_h = 24
    status_rect = pygame.Rect(status_x, status_y, status_w, status_h)

    pygame.draw.rect(surface, (14, 24, 48), status_rect, border_radius=12)
    pygame.draw.rect(surface, (38, 65, 115), status_rect, 1, border_radius=12)

    # Status color
    if ASSISTANT_STATUS == "LISTENING":
        dot_color = (80, 255, 140)
    elif ASSISTANT_STATUS == "SPEAKING":
        dot_color = (255, 180, 60)
    elif ASSISTANT_STATUS == "PROCESSING":
        dot_color = (180, 100, 255)
    else:
        dot_color = (0, 220, 255)

    dot_r = 4 + int(pulse * 2)
    pygame.draw.circle(surface, dot_color, (status_x + 14, status_y + 12), dot_r)

    status_font = pygame.font.SysFont("consolas", 10, bold=True)
    stat_surf = status_font.render(ASSISTANT_STATUS, True, (220, 235, 255))
    surface.blit(stat_surf, (status_x + 26, status_y + 6))

    # 3. Interactive Theme Selectors
    theme_x = 460
    theme_btn_w = 54
    theme_btn_h = 24
    theme_font = pygame.font.SysFont("consolas", 9, bold=True)

    theme_names = {1: "GOLD", 2: "PURP", 3: "RED", 4: "BIO"}
    for t_id in range(1, 5):
        btn_rect = pygame.Rect(theme_x + (t_id - 1) * (theme_btn_w + 6), 14, theme_btn_w, theme_btn_h)
        is_active = (current_theme == t_id)
        is_hov = btn_rect.collidepoint(mouse_pos)

        t_accent = THEMES[t_id]["primary"]
        bg_col = (25, 42, 75) if is_hov else ((18, 30, 56) if is_active else (12, 19, 38))

        pygame.draw.rect(surface, bg_col, btn_rect, border_radius=5)
        border_col = t_accent if (is_active or is_hov) else (32, 54, 90)
        pygame.draw.rect(surface, border_col, btn_rect, 2 if is_active else 1, border_radius=5)

        pygame.draw.circle(surface, t_accent, (btn_rect.x + 8, btn_rect.y + 12), 3)
        t_label = theme_font.render(theme_names[t_id], True, (240, 245, 255) if is_active else (160, 185, 215))
        surface.blit(t_label, (btn_rect.x + 16, btn_rect.y + 7))

    # 4. Controls: MIC, CAM, BOLD, CLEAR
    ctrl_x = WIDTH - 390
    ctrl_btn_w = 64
    ctrl_btn_h = 24
    ctrl_font = pygame.font.SysFont("consolas", 10, bold=True)

    controls = [
        ("MIC", not MIC_MUTED, (80, 220, 120) if not MIC_MUTED else (255, 80, 80)),
        ("CAM", CAMERA_ENABLED, (80, 200, 255) if CAMERA_ENABLED else (140, 150, 170)),
        ("BOLD", ULTRA_BOLD, accent if ULTRA_BOLD else (130, 150, 180)),
        ("CLR", False, (220, 100, 120)),
    ]

    for i, (label, active, col) in enumerate(controls):
        btn_rect = pygame.Rect(ctrl_x + i * (ctrl_btn_w + 6), 14, ctrl_btn_w, ctrl_btn_h)
        is_hov = btn_rect.collidepoint(mouse_pos)
        fill = (22, 36, 68) if is_hov else (14, 22, 42)
        pygame.draw.rect(surface, fill, btn_rect, border_radius=5)
        pygame.draw.rect(surface, col if (active or is_hov) else (35, 55, 95), btn_rect, 1, border_radius=5)

        lbl = ctrl_font.render(label, True, col if active else (180, 200, 225))
        surface.blit(lbl, lbl.get_rect(center=(btn_rect.centerx, btn_rect.centery)))

    # 5. Live Digital Clock
    clock_str = datetime.datetime.now().strftime("%H:%M:%S")
    clock_font = pygame.font.SysFont("consolas", 13, bold=True)
    c_surf = clock_font.render(clock_str, True, (210, 235, 255))
    surface.blit(c_surf, (WIDTH - c_surf.get_width() - 20, 18))


def get_header_button_rects():
    theme_x = 460
    theme_btn_w = 54
    theme_btn_h = 24
    theme_rects = [
        (t_id, pygame.Rect(theme_x + (t_id - 1) * (theme_btn_w + 6), 14, theme_btn_w, theme_btn_h))
        for t_id in range(1, 5)
    ]

    ctrl_x = WIDTH - 390
    ctrl_btn_w = 64
    ctrl_btn_h = 24
    ctrl_rects = {
        "MIC": pygame.Rect(ctrl_x + 0 * (ctrl_btn_w + 6), 14, ctrl_btn_w, ctrl_btn_h),
        "CAM": pygame.Rect(ctrl_x + 1 * (ctrl_btn_w + 6), 14, ctrl_btn_w, ctrl_btn_h),
        "BOLD": pygame.Rect(ctrl_x + 2 * (ctrl_btn_w + 6), 14, ctrl_btn_w, ctrl_btn_h),
        "CLR": pygame.Rect(ctrl_x + 3 * (ctrl_btn_w + 6), 14, ctrl_btn_w, ctrl_btn_h),
    }
    return theme_rects, ctrl_rects


# -------------------- CHAT & CONVERSATION PANEL --------------------
def draw_chat_panel(surface):
    panel_rect = LAYOUT["chat_panel"]
    theme = THEMES.get(current_theme, THEMES[1])
    accent = theme["primary"]

    draw_glass_panel(surface, panel_rect, "NEURAL CONVERSATION FEED", accent, f"{len(CHAT_MESSAGES)} TURNS")

    inner_pad = 12
    view_x = panel_rect.x + inner_pad
    view_y = panel_rect.y + 36
    view_w = panel_rect.width - inner_pad * 2
    view_h = panel_rect.height - 46

    # Inner clipping area
    view_rect = pygame.Rect(view_x, view_y, view_w, view_h)
    prev_clip = surface.get_clip()
    surface.set_clip(view_rect)

    font_msg = pygame.font.SysFont("consolas", 12)
    font_meta = pygame.font.SysFont("consolas", 9, bold=True)

    bubble_pad = 7
    card_spacing = 8
    max_bubble_w = int(view_w * 0.90)

    # Pre-render cards to calculate total scrollable height
    rendered_cards = []
    total_content_h = 0

    for msg in CHAT_MESSAGES:
        role = msg.get("role", "neura")
        text = msg.get("message", "")
        mtime = msg.get("time", "")

        is_user = (role == "user")
        wrapped_lines = wrap_text(font_msg, text, max_bubble_w - (bubble_pad * 2))
        line_h = font_msg.get_linesize()
        bubble_h = max(24, len(wrapped_lines) * line_h) + bubble_pad * 2 + 16

        rendered_cards.append({
            "is_user": is_user,
            "role_label": "YOU" if is_user else "NEURA",
            "lines": wrapped_lines,
            "time": mtime,
            "height": bubble_h,
            "line_h": line_h
        })
        total_content_h += bubble_h + card_spacing

    max_scroll = max(0, total_content_h - view_h)
    scroll = min(CHAT_SCROLL_OFFSET, max_scroll)

    draw_y = view_y + view_h - total_content_h + scroll
    if total_content_h < view_h:
        draw_y = view_y

    for card in rendered_cards:
        c_h = card["height"]
        if draw_y + c_h >= view_y and draw_y <= view_y + view_h:
            card_w = max_bubble_w
            if card["is_user"]:
                card_x = view_x + (view_w - card_w)
                card_bg = (18, 30, 60, 220)
                card_border = (45, 90, 160)
                role_col = (110, 200, 255)
            else:
                card_x = view_x
                card_bg = (24, 18, 48, 220) if current_theme == 2 else (28, 26, 46, 220)
                card_border = theme["primary_soft"]
                role_col = accent

            b_rect = pygame.Rect(card_x, draw_y, card_w, c_h)
            card_surf = pygame.Surface((card_w, c_h), pygame.SRCALPHA)
            card_surf.fill(card_bg)
            surface.blit(card_surf, (card_x, draw_y))
            pygame.draw.rect(surface, card_border, b_rect, 1, border_radius=6)

            # Header inside bubble: Role & Timestamp
            r_surf = font_meta.render(card["role_label"], True, role_col)
            surface.blit(r_surf, (card_x + bubble_pad, draw_y + bubble_pad - 1))

            if card["time"]:
                t_surf = font_meta.render(card["time"], True, (130, 155, 190))
                surface.blit(t_surf, (card_x + card_w - t_surf.get_width() - bubble_pad, draw_y + bubble_pad - 1))

            # Lines of message
            text_y = draw_y + bubble_pad + 16
            for line in card["lines"]:
                line_surf = font_msg.render(line, True, COLOR_TEXT_WHITE)
                surface.blit(line_surf, (card_x + bubble_pad, text_y))
                text_y += card["line_h"]

        draw_y += c_h + card_spacing

    surface.set_clip(prev_clip)

    # Scrollbar indicator if scrollable
    if max_scroll > 0:
        bar_w = 3
        bar_x = panel_rect.right - 8
        bar_track_h = view_h
        thumb_h = max(20, int(bar_track_h * (view_h / total_content_h)))
        thumb_y = view_y + int((bar_track_h - thumb_h) * (1.0 - (scroll / max_scroll)))

        pygame.draw.rect(surface, (20, 35, 65), (bar_x, view_y, bar_w, bar_track_h), border_radius=2)
        pygame.draw.rect(surface, accent, (bar_x, thumb_y, bar_w, thumb_h), border_radius=2)


# -------------------- QUICK PROMPT ACTION CHIPS --------------------
def get_quick_action_rects():
    panel_rect = LAYOUT["quick_actions"]
    pad_x = 10
    pad_y = 26
    avail_w = panel_rect.width - pad_x * 2
    avail_h = panel_rect.height - pad_y - 8

    cols = 3
    rows = 2
    btn_w = (avail_w - (cols - 1) * 6) // cols
    btn_h = (avail_h - (rows - 1) * 6) // rows

    rects = []
    for i in range(len(QUICK_ACTIONS)):
        r = i // cols
        c = i % cols
        bx = panel_rect.x + pad_x + c * (btn_w + 6)
        by = panel_rect.y + pad_y + r * (btn_h + 6)
        rects.append(pygame.Rect(bx, by, btn_w, btn_h))
    return rects


def draw_quick_actions(surface):
    panel_rect = LAYOUT["quick_actions"]
    theme = THEMES.get(current_theme, THEMES[1])
    accent = theme["primary"]

    draw_glass_panel(surface, panel_rect, "TACTICAL COMMAND CHIPS", (255, 180, 80))

    mouse_pos = pygame.mouse.get_pos()
    label_font = pygame.font.SysFont("consolas", 10, bold=True)

    rects = get_quick_action_rects()
    for rect, (label, _, _, col) in zip(rects, QUICK_ACTIONS):
        is_hov = rect.collidepoint(mouse_pos)
        fill_col = (25, 38, 70) if is_hov else (14, 22, 45)
        border_col = col if is_hov else (32, 52, 90)

        pygame.draw.rect(surface, fill_col, rect, border_radius=4)
        pygame.draw.rect(surface, border_col, rect, 2 if is_hov else 1, border_radius=4)

        # Micro dot indicator
        pygame.draw.circle(surface, col, (rect.x + 8, rect.centery), 3)

        lbl = label_font.render(label, True, (240, 248, 255) if is_hov else (175, 195, 225))
        surface.blit(lbl, (rect.x + 16, rect.centery - lbl.get_height() // 2))


def activate_quick_action(action_key, prompt_text):
    global ACTION_STATUS, ACTION_STATUS_UNTIL
    if action_key == "music":
        webbrowser.open("https://www.youtube.com")
        ACTION_STATUS = "OPENED: YOUTUBE MEDIA"
    elif action_key == "files":
        os.startfile(os.path.expanduser("~"))
        ACTION_STATUS = "OPENED: EXPLORER HOME"
    elif action_key == "taskmgr":
        subprocess.Popen(["taskmgr.exe"])
        ACTION_STATUS = "LAUNCHED: TASK MANAGER"
    else:
        # Dispatch prompt directly to Neura assistant backend!
        send_command_to_backend(prompt_text)
        ACTION_STATUS = f"SENT: {prompt_text.upper()}"

    ACTION_STATUS_UNTIL = pygame.time.get_ticks() + 2500


# -------------------- INTERACTIVE TEXT INPUT BAR --------------------
def get_send_button_rect():
    box_rect = LAYOUT["input_box"]
    btn_w = 60
    btn_h = box_rect.height - 8
    btn_x = box_rect.right - btn_w - 4
    btn_y = box_rect.y + 4
    return pygame.Rect(btn_x, btn_y, btn_w, btn_h)


def draw_input_box(surface):
    global CURSOR_VISIBLE, LAST_CURSOR_BLINK
    box_rect = LAYOUT["input_box"]
    theme = THEMES.get(current_theme, THEMES[1])
    accent = theme["primary"]

    mouse_pos = pygame.mouse.get_pos()
    is_hov = box_rect.collidepoint(mouse_pos)

    # Input Container
    bg_col = (12, 20, 42) if INPUT_ACTIVE else (9, 15, 32)
    border_col = accent if (INPUT_ACTIVE or is_hov) else (35, 58, 105)

    pygame.draw.rect(surface, bg_col, box_rect, border_radius=6)
    pygame.draw.rect(surface, border_col, box_rect, 2 if INPUT_ACTIVE else 1, border_radius=6)

    # Input text font
    font = pygame.font.SysFont("consolas", 12)
    send_rect = get_send_button_rect()
    text_avail_w = send_rect.x - box_rect.x - 20

    # Draw text or placeholder
    now_ms = pygame.time.get_ticks()
    if now_ms - LAST_CURSOR_BLINK > 500:
        CURSOR_VISIBLE = not CURSOR_VISIBLE
        LAST_CURSOR_BLINK = now_ms

    if USER_INPUT_TEXT:
        # Trim from left if text exceeds width
        disp_text = USER_INPUT_TEXT
        while disp_text and font.size(disp_text)[0] > text_avail_w:
            disp_text = disp_text[1:]
        t_surf = font.render(disp_text, True, COLOR_TEXT_WHITE)
        surface.blit(t_surf, (box_rect.x + 10, box_rect.centery - t_surf.get_height() // 2))

        if INPUT_ACTIVE and CURSOR_VISIBLE:
            cx = box_rect.x + 10 + t_surf.get_width() + 2
            cy = box_rect.centery - 8
            pygame.draw.line(surface, accent, (cx, cy), (cx, cy + 16), 2)
    else:
        ph_surf = font.render("Type command or ask Neura (Enter to send)...", True, (100, 130, 170))
        surface.blit(ph_surf, (box_rect.x + 10, box_rect.centery - ph_surf.get_height() // 2))
        if INPUT_ACTIVE and CURSOR_VISIBLE:
            pygame.draw.line(surface, accent, (box_rect.x + 10, box_rect.centery - 8), (box_rect.x + 10, box_rect.centery + 8), 2)

    # Send Button
    btn_hov = send_rect.collidepoint(mouse_pos)
    btn_bg = accent if btn_hov else (20, 35, 68)
    pygame.draw.rect(surface, btn_bg, send_rect, border_radius=4)
    pygame.draw.rect(surface, accent, send_rect, 1, border_radius=4)

    btn_font = pygame.font.SysFont("consolas", 10, bold=True)
    b_text = btn_font.render("SEND ►", True, (10, 18, 32) if btn_hov else (220, 240, 255))
    surface.blit(b_text, b_text.get_rect(center=send_rect.center))


# -------------------- OPTICS / CAMERA VIEW MODULE --------------------
def draw_camera_panel(surface, t):
    global CAMERA_SURFACE, CAMERA_ENABLED
    panel_rect = LAYOUT["cam_panel"]
    accent = (0, 200, 255)

    badge = "REC ● LIVE" if CAMERA_ENABLED else "STANDBY"
    draw_glass_panel(surface, panel_rect, "NEURA OPTICS // SCANNER", accent, badge)

    cam_inner_x = panel_rect.x + 8
    cam_inner_y = panel_rect.y + 28
    cam_inner_w = panel_rect.width - 16
    cam_inner_h = panel_rect.height - 36
    inner_rect = pygame.Rect(cam_inner_x, cam_inner_y, cam_inner_w, cam_inner_h)

    if CAMERA_ENABLED and CAMERA_SURFACE is not None:
        scaled = pygame.transform.scale(CAMERA_SURFACE, (cam_inner_w, cam_inner_h))
        surface.blit(scaled, (cam_inner_x, cam_inner_y))

        # Sci-Fi Viewfinder Overlay
        # Scanlines
        scan_step = 6
        for sy in range(cam_inner_y, cam_inner_y + cam_inner_h, scan_step):
            pygame.draw.line(surface, (10, 20, 45), (cam_inner_x, sy), (cam_inner_x + cam_inner_w, sy), 1)

        # Center Reticle
        cx, cy = inner_rect.centerx, inner_rect.centery
        pygame.draw.circle(surface, (0, 220, 255), (cx, cy), 14, 1)
        pygame.draw.line(surface, (0, 220, 255), (cx - 20, cy), (cx - 8, cy), 1)
        pygame.draw.line(surface, (0, 220, 255), (cx + 8, cy), (cx + 20, cy), 1)
        pygame.draw.line(surface, (0, 220, 255), (cx, cy - 20), (cx, cy - 8), 1)
        pygame.draw.line(surface, (0, 220, 255), (cx, cy + 8), (cx, cy + 20), 1)

        # Tech telemetry text
        font_tech = pygame.font.SysFont("consolas", 8, bold=True)
        surface.blit(font_tech.render("FOV 84° // HD 1080P", True, (0, 220, 255)), (cam_inner_x + 6, cam_inner_y + 4))
        surface.blit(font_tech.render("LOCK: TRACKING", True, (0, 220, 255)), (cam_inner_x + 6, cam_inner_y + cam_inner_h - 14))
    else:
        # Standby Animated Cyber Radar Display
        pygame.draw.rect(surface, (8, 14, 30), inner_rect, border_radius=4)
        cx, cy = inner_rect.centerx, inner_rect.centery
        r_max = min(cam_inner_w, cam_inner_h) // 2 - 8

        # Radar concentric rings
        pygame.draw.circle(surface, (20, 40, 75), (cx, cy), r_max // 3, 1)
        pygame.draw.circle(surface, (25, 50, 90), (cx, cy), (r_max * 2) // 3, 1)
        pygame.draw.circle(surface, (30, 60, 110), (cx, cy), r_max, 1)

        # Crosshairs
        pygame.draw.line(surface, (25, 45, 80), (cx - r_max, cy), (cx + r_max, cy), 1)
        pygame.draw.line(surface, (25, 45, 80), (cx, cy - r_max), (cx, cy + r_max), 1)

        # Rotating sweep line
        ang = (t * 0.002) % (2 * math.pi)
        sx = cx + int(r_max * math.cos(ang))
        sy = cy + int(r_max * math.sin(ang))
        pygame.draw.line(surface, (0, 180, 255), (cx, cy), (sx, sy), 2)

        font_cam = pygame.font.SysFont("consolas", 10, bold=True)
        msg = font_cam.render("OPTICS STANDBY // PRIVACY MODE", True, (130, 160, 200))
        surface.blit(msg, msg.get_rect(center=(cx, cy + r_max // 2 + 12)))


# -------------------- NEURAL MEMORY CORE MODULE --------------------
def load_memory_snapshot():
    now = pygame.time.get_ticks() / 1000.0
    if now - MEMORY_CACHE["updated_at"] < 1.0:
        return MEMORY_CACHE["data"]

    base_dir = os.path.dirname(os.path.abspath(__file__))
    snapshot = {}
    try:
        with open(os.path.join(base_dir, "memory", "user_memory.json"), "r", encoding="utf-8") as file:
            snapshot["user"] = json.load(file)
        with open(os.path.join(base_dir, "memory", "conversation_memory.json"), "r", encoding="utf-8") as file:
            snapshot["conversation"] = json.load(file)
    except (OSError, json.JSONDecodeError):
        snapshot = MEMORY_CACHE["data"]

    MEMORY_CACHE["data"] = snapshot
    MEMORY_CACHE["updated_at"] = now
    return snapshot


def draw_memory_panel(surface):
    panel_rect = LAYOUT["mem_panel"]
    draw_glass_panel(surface, panel_rect, "NEURAL MEMORY MATRIX", (140, 230, 150))

    snapshot = load_memory_snapshot()
    user_memory = snapshot.get("user", {})
    conversation = snapshot.get("conversation", {})
    preferences = user_memory.get("preferences", {})
    facts = user_memory.get("user_facts", {})
    activity = user_memory.get("activity_log", [])
    recent = conversation.get("recent_messages", [])

    font_main = pygame.font.SysFont("consolas", 11, bold=True)
    font_sub = pygame.font.SysFont("consolas", 10)
    font_tiny = pygame.font.SysFont("consolas", 9)

    name = facts.get("name") or "User"
    preference_count = len([v for v in preferences.values() if v])
    fact_count = len([v for v in facts.values() if v])
    memory_score = min(100, preference_count * 12 + fact_count * 14 + min(len(activity), 10) * 2)

    px = panel_rect.x + 12
    py = panel_rect.y + 32

    # Identity pill
    id_text = font_main.render(f"PROFILE: {name.upper()}", True, (220, 245, 220))
    surface.blit(id_text, (px, py))

    stat_text = font_sub.render(f"{len(activity)} activities  |  {len(recent)} recent turns", True, (140, 180, 160))
    surface.blit(stat_text, (px, py + 18))

    # Retention Gauge Bar
    bar_y = py + 38
    bar_w = panel_rect.width - 24
    bar_h = 7
    bar_rect = pygame.Rect(px, bar_y, bar_w, bar_h)
    pygame.draw.rect(surface, (20, 36, 50), bar_rect, border_radius=3)

    fill_w = int(bar_w * (memory_score / 100.0))
    if fill_w > 0:
        fill_rect = pygame.Rect(px, bar_y, fill_w, bar_h)
        pygame.draw.rect(surface, (120, 230, 150), fill_rect, border_radius=3)

    gauge_lbl = font_tiny.render(f"RETENTION INDEX: {memory_score:02d}%", True, (140, 220, 165))
    surface.blit(gauge_lbl, (px, bar_y + 11))

    # Latest memory snippet
    latest = recent[-1] if recent else {}
    latest_text = latest.get("content", "Memory core initialized and receptive.").replace("\n", " ")
    max_char = int(panel_rect.width / 8.5)
    latest_text = latest_text[:max_char] + ("..." if len(latest_text) > max_char else "")

    trace_y = bar_y + 28
    surface.blit(font_tiny.render("LATEST CONTEXT TRACE:", True, (110, 160, 205)), (px, trace_y))
    surface.blit(font_sub.render(latest_text, True, (205, 225, 245)), (px, trace_y + 14))


# -------------------- HARDWARE PERFORMANCE MODULE --------------------
def draw_performance_panel(surface):
    panel_rect = LAYOUT["perf_panel"]
    draw_glass_panel(surface, panel_rect, "HARDWARE TELEMETRY // STATS", (80, 220, 120))

    # Gather system usage
    cpu_usage = psutil.cpu_percent(interval=0)
    ram_info = psutil.virtual_memory()
    ram_usage = ram_info.percent

    now = pygame.time.get_ticks() / 1000.0
    if now - GPU_STATS["updated_at"] >= 0.5:
        GPU_STATS["updated_at"] = now
        try:
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=utilization.gpu,memory.used,memory.total",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=0.25,
                check=False,
            )
            values = result.stdout.strip().split(",")
            if result.returncode == 0 and len(values) >= 3:
                GPU_STATS["usage"] = float(values[0].strip())
                GPU_STATS["memory"] = (float(values[1].strip()), float(values[2].strip()))
            else:
                GPU_STATS["usage"] = None
                GPU_STATS["memory"] = None
        except Exception:
            GPU_STATS["usage"] = None
            GPU_STATS["memory"] = None

    gpu_usage = GPU_STATS["usage"]

    CPU_GRAPH.append(cpu_usage)
    RAM_GRAPH.append(ram_usage)
    GPU_GRAPH.append(gpu_usage if gpu_usage is not None else 0)

    CPU_GRAPH[:] = CPU_GRAPH[-GRAPH_MAX_POINTS:]
    RAM_GRAPH[:] = RAM_GRAPH[-GRAPH_MAX_POINTS:]
    GPU_GRAPH[:] = GPU_GRAPH[-GRAPH_MAX_POINTS:]

    # Grid box
    graph_x = panel_rect.x + 10
    graph_y = panel_rect.y + 32
    graph_w = panel_rect.width - 20
    graph_h = panel_rect.height - 42

    pygame.draw.rect(surface, (8, 14, 30), (graph_x, graph_y, graph_w, graph_h), border_radius=4)
    pygame.draw.rect(surface, (25, 45, 80), (graph_x, graph_y, graph_w, graph_h), 1, border_radius=4)

    # Grid lines
    cols = 8
    rows = 4
    for i in range(1, cols):
        gx = graph_x + (i * graph_w) // cols
        pygame.draw.line(surface, (18, 30, 56), (gx, graph_y), (gx, graph_y + graph_h), 1)
    for j in range(1, rows):
        gy = graph_y + (j * graph_h) // rows
        pygame.draw.line(surface, (18, 30, 56), (graph_x, gy), (graph_x + graph_w, gy), 1)

    # Plot lines helper
    def draw_graph_line(history, color):
        if len(history) < 2:
            return
        pts = []
        for idx, val in enumerate(history):
            px = graph_x + int((idx / (GRAPH_MAX_POINTS - 1)) * graph_w)
            py = graph_y + graph_h - int((val / 100.0) * graph_h)
            py = max(graph_y, min(graph_y + graph_h, py))
            pts.append((px, py))
        pygame.draw.lines(surface, color, False, pts, 2)

    draw_graph_line(CPU_GRAPH, (80, 220, 120))
    draw_graph_line(RAM_GRAPH, (170, 90, 255))
    if gpu_usage is not None:
        draw_graph_line(GPU_GRAPH, (255, 180, 80))

    # Metric Badges
    font_tiny = pygame.font.SysFont("consolas", 9, bold=True)
    surface.blit(font_tiny.render(f"CPU: {cpu_usage:4.1f}%", True, (130, 255, 160)), (graph_x + 8, graph_y + 6))
    surface.blit(font_tiny.render(f"RAM: {ram_usage:4.1f}%", True, (210, 150, 255)), (graph_x + 88, graph_y + 6))

    if gpu_usage is not None:
        used, total = GPU_STATS["memory"]
        gpu_txt = f"GPU: {gpu_usage:4.1f}% [{int(used)}/{int(total)}MB]"
        surface.blit(font_tiny.render(gpu_txt, True, (255, 200, 120)), (graph_x + 168, graph_y + 6))
    else:
        surface.blit(font_tiny.render("GPU: N/A", True, (140, 160, 180)), (graph_x + 168, graph_y + 6))


# -------------------- MULTI-BAND AUDIO SPECTRUM VISUALIZER --------------------
def draw_audio_spectrum(surface, amplitude):
    global spectrum_heights
    spec_rect = LAYOUT["spectrum"]
    theme = THEMES.get(current_theme, THEMES[1])
    accent = theme["primary"]

    # Frame
    spec_surf = pygame.Surface((spec_rect.width, spec_rect.height), pygame.SRCALPHA)
    spec_surf.fill((8, 14, 30, 190))
    surface.blit(spec_surf, (spec_rect.x, spec_rect.y))
    pygame.draw.rect(surface, (28, 48, 88), spec_rect, 1, border_radius=6)

    bar_gap = 4
    total_gaps = (SPECTRUM_BANDS - 1) * bar_gap
    bar_w = max(3, (spec_rect.width - 24 - total_gaps) // SPECTRUM_BANDS)
    max_h = spec_rect.height - 18

    # Smooth animated heights
    for b in range(SPECTRUM_BANDS):
        # Bell curve factor around center frequencies + amplitude
        freq_factor = 1.0 - abs(b - (SPECTRUM_BANDS / 2)) / (SPECTRUM_BANDS / 2)
        target = min(1.0, amplitude * (0.8 + freq_factor * 1.5) + random.uniform(0.02, 0.08) * (amplitude > 0.05))
        spectrum_heights[b] += (target - spectrum_heights[b]) * 0.28

    start_x = spec_rect.x + (spec_rect.width - (SPECTRUM_BANDS * bar_w + total_gaps)) // 2
    base_y = spec_rect.bottom - 8

    for b in range(SPECTRUM_BANDS):
        h = max(2, int(spectrum_heights[b] * max_h))
        bx = start_x + b * (bar_w + bar_gap)
        by = base_y - h

        col = mix_color(theme["primary_soft"], accent, b / SPECTRUM_BANDS)
        pygame.draw.rect(surface, col, (bx, by, bar_w, h), border_radius=2)

    font_db = pygame.font.SysFont("consolas", 8, bold=True)
    amp_pct = int(amplitude * 100)
    db_surf = font_db.render(f"ACOUSTIC INPUT: {amp_pct:02d}%", True, accent)
    surface.blit(db_surf, (spec_rect.x + 10, spec_rect.y + 4))


# -------------------- ADVANCED JARVIS HUD CORE --------------------
def draw_sidd_hud(surface, t, amplitude):
    global ULTRA_BOLD, VOICE_PULSES

    center = (CENTER_X, CENTER_Y)
    ts = t * 0.001
    base = int(min(WIDTH, HEIGHT) * 0.11)
    amp = min(max(amplitude, 0.0), 1.0)
    amp_visual = amp ** 0.7

    CYAN = (0, 220, 255)
    CYAN_SOFT = (0, 160, 210)

    outer_w = 4 if ULTRA_BOLD else 2
    inner_w = 3 if ULTRA_BOLD else 1
    core_w = 5 if ULTRA_BOLD else 2

    r_inner = int(base * 0.85)
    r_outer = int(base * 1.35)
    r_glow = int(base * 1.55)

    pygame.draw.circle(surface, CYAN_SOFT, center, r_glow, 1)
    pygame.draw.circle(surface, CYAN, center, r_outer, outer_w)
    pygame.draw.circle(surface, CYAN, center, r_inner, inner_w)

    # Rotating cyber gap arcs
    gap_rect = pygame.Rect(0, 0, r_outer * 2, r_outer * 2)
    gap_rect.center = center
    for i in range(3):
        offset = ts * 0.6 + i * (2 * math.pi / 3)
        pygame.draw.arc(surface, CYAN_SOFT, gap_rect, offset, offset + math.pi / 7, outer_w)

    # Dynamic Theme Colors
    theme = THEMES.get(current_theme, THEMES[1])
    inner_color = mix_color(theme["quiet_core"], theme["loud_core"], amp_visual)

    # Pulsing core
    core_radius = int(base * (0.42 + 0.28 * amp_visual))
    pygame.draw.circle(surface, inner_color, center, core_radius, core_w)

    # Rotating processor polygon
    sides = 6
    poly_radius = int(core_radius * 0.75)
    poly_ang = ts * 1.2
    pts = [
        (CENTER_X + poly_radius * math.cos(poly_ang + 2 * math.pi * i / sides),
         CENTER_Y + poly_radius * math.sin(poly_ang + 2 * math.pi * i / sides))
        for i in range(sides)
    ]
    pygame.draw.polygon(surface, inner_color, pts, 2)

    # Inner Ticks
    tick_count = 20
    tick_rot = ts * 0.5
    for i in range(tick_count):
        ang = tick_rot + (2 * math.pi * i / tick_count)
        x0 = CENTER_X + (r_inner * 0.94) * math.cos(ang)
        y0 = CENTER_Y + (r_inner * 0.94) * math.sin(ang)
        x1 = CENTER_X + (r_inner * 1.02) * math.cos(ang)
        y1 = CENTER_Y + (r_inner * 1.02) * math.sin(ang)
        pygame.draw.line(surface, CYAN_SOFT, (x0, y0), (x1, y1), 1)

    # Reactive radial scanning lines
    num_lines = 16
    l_rot = ts * 1.6
    for i in range(num_lines):
        ang = l_rot + (2 * math.pi * i / num_lines)
        r0 = core_radius * 1.05
        r1 = r_inner * (0.90 + 0.18 * amp_visual)
        x0 = CENTER_X + r0 * math.cos(ang)
        y0 = CENTER_Y + r0 * math.sin(ang)
        x1 = CENTER_X + r1 * math.cos(ang)
        y1 = CENTER_Y + r1 * math.sin(ang)
        pygame.draw.line(surface, inner_color, (x0, y0), (x1, y1), 1)

    # Sweeping radar laser
    sweep_r = r_outer * 1.02
    sw_rect = pygame.Rect(0, 0, sweep_r * 2, sweep_r * 2)
    sw_rect.center = center
    sw_ang = ts * 1.4
    pygame.draw.arc(surface, (255, 255, 255), sw_rect, sw_ang, sw_ang + math.pi / 18, 3)

    # Orbiting satellite energy orb
    orb_ang = ts * 2.2
    ox = CENTER_X + (r_inner * 1.1) * math.cos(orb_ang)
    oy = CENTER_Y + (r_inner * 1.1) * math.sin(orb_ang)
    pygame.draw.circle(surface, mix_color(inner_color, (255, 255, 255), 0.6), (int(ox), int(oy)), 5)

    # Speaking expanding rings
    alive = []
    for start_t in VOICE_PULSES:
        age = t - start_t
        if 0 <= age <= VOICE_PULSE_LIFE:
            alive.append(start_t)
            p = age / VOICE_PULSE_LIFE
            pr = core_radius * 1.1 + p * (r_outer * 0.95 - core_radius * 1.1)
            pc = mix_color(inner_color, CYAN_SOFT, p)
            pygame.draw.circle(surface, pc, center, int(pr), 2)
    VOICE_PULSES = alive


# -------------------- BOTTOM STATUS BAR --------------------
def draw_status_bar(surface, fps):
    bar_rect = LAYOUT["status_bar"]
    theme = THEMES.get(current_theme, THEMES[1])
    accent = theme["primary"]

    pygame.draw.rect(surface, (7, 11, 24), bar_rect)
    pygame.draw.line(surface, (25, 45, 80), (0, bar_rect.y), (WIDTH, bar_rect.y), 1)

    font = pygame.font.SysFont("consolas", 10)

    # Left: Action Status
    global ACTION_STATUS, ACTION_STATUS_UNTIL
    status = ACTION_STATUS if pygame.time.get_ticks() < ACTION_STATUS_UNTIL else "SYSTEM OPERATIONAL // READY"
    stat_surf = font.render(f"[STATUS]: {status}", True, accent)
    surface.blit(stat_surf, (14, bar_rect.y + 8))

    # Center: Interactive Controls Hint
    hints = font.render("SHORTCUTS: [1-4] Themes | [U] Bold HUD | [ENTER] Send Command", True, (110, 140, 180))
    surface.blit(hints, hints.get_rect(center=(WIDTH // 2, bar_rect.centery)))

    # Right: FPS & System
    fps_surf = font.render(f"FPS: {int(fps):02d}  |  RES: {WIDTH}x{HEIGHT}", True, (140, 170, 205))
    surface.blit(fps_surf, (WIDTH - fps_surf.get_width() - 14, bar_rect.y + 8))


# -------------------- MAIN APPLICATION LOOP --------------------
def main():
    pygame.init()
    pygame.key.set_repeat(400, 35)

    global SPHERE_RADIUS, current_theme, ULTRA_BOLD, last_amplitude, VOICE_PULSES
    global USER_INPUT_TEXT, INPUT_ACTIVE, CHAT_SCROLL_OFFSET, CAMERA_SURFACE, CAMERA_ENABLED, MIC_MUTED

    # Start Neura Assistant Backend Process
    ai_process = None
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        ai_script = os.path.join(script_dir, "neura.py")
        ai_process = subprocess.Popen([sys.executable, ai_script])
        print("Neura AI backend daemon started:", ai_script)
    except Exception as e:
        print("Note: Could not spawn AI backend automatically:", e)

    # Display window initialization
    info = pygame.display.Info()
    start_w = min(1440, max(1100, int(info.current_w * 0.85)))
    start_h = min(900, max(720, int(info.current_h * 0.85)))

    recalc_layout(start_w, start_h)
    screen = pygame.display.set_mode((start_w, start_h), pygame.RESIZABLE)
    pygame.display.set_caption("NEURA AI // QUANTUM DESKTOP INTERFACE")

    clock = pygame.time.Clock()
    dots = [Dot() for _ in range(NUM_DOTS)]

    # Audio Setup with PyAudio
    pa = None
    stream = None
    try:
        pa = pyaudio.PyAudio()
        stream = pa.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=RATE,
            input=True,
            frames_per_buffer=CHUNK,
        )
    except Exception as e:
        print("Audio device warning:", e)

    # Camera Setup with OpenCV
    cam = None
    try:
        cam = cv2.VideoCapture(0)
        cam.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
        cam.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
    except Exception as e:
        print("Camera device warning:", e)

    rot_x = 0.0
    rot_y = 0.0
    t = 0.0
    running = True

    try:
        while running:
            dt = clock.tick(60)
            t += dt

            # Monitor backend health
            if ai_process is not None and ai_process.poll() is not None:
                print("Backend stopped. Closing frontend...")
                running = False
                break

            # Update live assistant status from bridge
            update_assistant_status()

            # Process Webcam
            if CAMERA_ENABLED and cam is not None and cam.isOpened():
                ret, frame = cam.read()
                if ret:
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    frame = cv2.flip(frame, 1)
                    CAMERA_SURFACE = pygame.surfarray.make_surface(frame.swapaxes(0, 1))
                else:
                    CAMERA_SURFACE = None
            else:
                CAMERA_SURFACE = None

            # Handle Pygame Events
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False

                elif event.type == pygame.VIDEORESIZE:
                    recalc_layout(event.w, event.h)
                    screen = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE)

                elif event.type == pygame.MOUSEBUTTONDOWN:
                    mpos = event.pos

                    # 1. Header controls & themes
                    theme_rects, ctrl_rects = get_header_button_rects()
                    for tid, trect in theme_rects:
                        if trect.collidepoint(mpos):
                            current_theme = tid

                    if ctrl_rects["MIC"].collidepoint(mpos):
                        MIC_MUTED = not MIC_MUTED
                    elif ctrl_rects["CAM"].collidepoint(mpos):
                        CAMERA_ENABLED = not CAMERA_ENABLED
                    elif ctrl_rects["BOLD"].collidepoint(mpos):
                        ULTRA_BOLD = not ULTRA_BOLD
                    elif ctrl_rects["CLR"].collidepoint(mpos):
                        clear_chat_history()

                    # 2. Quick Action Chips
                    for qrect, (_, akey, ptext, _) in zip(get_quick_action_rects(), QUICK_ACTIONS):
                        if qrect.collidepoint(mpos):
                            activate_quick_action(akey, ptext)
                            break

                    # 3. Input Box Focus & Send Button
                    send_btn = get_send_button_rect()
                    if send_btn.collidepoint(mpos):
                        if USER_INPUT_TEXT.strip():
                            send_command_to_backend(USER_INPUT_TEXT)
                            USER_INPUT_TEXT = ""
                    elif LAYOUT["input_box"].collidepoint(mpos):
                        INPUT_ACTIVE = True
                    else:
                        if not LAYOUT["chat_panel"].collidepoint(mpos):
                            INPUT_ACTIVE = True

                elif event.type == pygame.MOUSEWHEEL:
                    mx, my = pygame.mouse.get_pos()
                    if LAYOUT["chat_panel"].collidepoint(mx, my):
                        CHAT_SCROLL_OFFSET -= event.y * 24
                        CHAT_SCROLL_OFFSET = max(0, CHAT_SCROLL_OFFSET)

                elif event.type == pygame.KEYDOWN:
                    if INPUT_ACTIVE:
                        if event.key == pygame.K_RETURN:
                            if USER_INPUT_TEXT.strip():
                                send_command_to_backend(USER_INPUT_TEXT)
                                USER_INPUT_TEXT = ""
                        elif event.key == pygame.K_BACKSPACE:
                            USER_INPUT_TEXT = USER_INPUT_TEXT[:-1]
                        elif event.key == pygame.K_ESCAPE:
                            USER_INPUT_TEXT = ""
                        elif event.key == pygame.K_v and (pygame.key.get_mods() & pygame.KMOD_CTRL):
                            try:
                                import tkinter as tk
                                root = tk.Tk()
                                root.withdraw()
                                clip = root.clipboard_get()
                                root.destroy()
                                if clip:
                                    USER_INPUT_TEXT += clip.strip()
                            except Exception:
                                pass
                        else:
                            if event.unicode and len(event.unicode) == 1 and event.unicode.isprintable():
                                USER_INPUT_TEXT += event.unicode

                    # Global Theme hotkeys
                    if event.key == pygame.K_1:
                        current_theme = 1
                    elif event.key == pygame.K_2:
                        current_theme = 2
                    elif event.key == pygame.K_3:
                        current_theme = 3
                    elif event.key == pygame.K_4:
                        current_theme = 4
                    elif event.key == pygame.K_u and not INPUT_ACTIVE:
                        ULTRA_BOLD = not ULTRA_BOLD

            # Audio Processing
            amplitude = 0.0
            if stream is not None and not MIC_MUTED:
                try:
                    data = stream.read(CHUNK, exception_on_overflow=False)
                    samples = struct.unpack(str(CHUNK) + 'h', data)
                    sum_sq = sum(s * s for s in samples)
                    rms = math.sqrt(sum_sq / CHUNK)
                    amplitude = min(rms / 3000.0, 1.0)
                except Exception:
                    amplitude = 0.0

            if amplitude > VOICE_THRESHOLD and last_amplitude <= VOICE_THRESHOLD:
                VOICE_PULSES.append(t)
            last_amplitude = amplitude

            # Rotate 3D Sphere
            rot_y += ROT_Y_SPEED * dt * 0.001
            rot_x += ROT_X_SPEED * dt * 0.001

            for d in dots:
                d.update(dt, rot_x, rot_y)

            dots_sorted = sorted(dots, key=lambda d: d.z)

            # Synchronize Chat Messages from Bridge
            fetch_chat_from_backend()

            # Render UI
            screen.fill(COLOR_BG)

            # Central Atmospheric Radial Glow
            theme = THEMES.get(current_theme, THEMES[1])
            glow_surf = pygame.Surface((SPHERE_RADIUS_BASE * 3, SPHERE_RADIUS_BASE * 3), pygame.SRCALPHA)
            pygame.draw.circle(
                glow_surf,
                (*theme["primary_soft"], 18),
                (SPHERE_RADIUS_BASE * 3 // 2, SPHERE_RADIUS_BASE * 3 // 2),
                SPHERE_RADIUS_BASE * 1.3
            )
            screen.blit(glow_surf, (CENTER_X - SPHERE_RADIUS_BASE * 3 // 2, CENTER_Y - SPHERE_RADIUS_BASE * 3 // 2))

            # Sphere outline & dots
            pygame.draw.circle(screen, (15, 25, 48), (CENTER_X, CENTER_Y), int(SPHERE_RADIUS * 0.92), 1)
            for d in dots_sorted:
                sx, sy, radius, color = d.project()
                if 0 <= sx < WIDTH and 0 <= sy < HEIGHT:
                    pygame.draw.circle(screen, color, (sx, sy), radius)

            # Jarvis HUD Core (Center)
            draw_sidd_hud(screen, t, amplitude)

            # Multi-Band Audio Spectrum
            draw_audio_spectrum(screen, amplitude)

            # Left Column (Chat, Chips, Input)
            draw_chat_panel(screen)
            draw_quick_actions(screen)
            draw_input_box(screen)

            # Right Column (Vision, Memory, Performance)
            draw_camera_panel(screen, t)
            draw_memory_panel(screen)
            draw_performance_panel(screen)

            # Top Header & Bottom Status Bar
            draw_header_bar(screen)
            fps = clock.get_fps()
            draw_status_bar(screen, fps)

            pygame.display.flip()

    finally:
        if stream is not None:
            try:
                stream.stop_stream()
                stream.close()
            except Exception:
                pass
        if pa is not None:
            try:
                pa.terminate()
            except Exception:
                pass
        if cam is not None:
            try:
                cam.release()
            except Exception:
                pass

        pygame.quit()

        if ai_process is not None and ai_process.poll() is None:
            try:
                ai_process.terminate()
                ai_process.wait(timeout=5)
                print("AI backend terminated.")
            except Exception as e:
                print("Error terminating AI backend:", e)


if __name__ == "__main__":
    main()
