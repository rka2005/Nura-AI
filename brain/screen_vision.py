"""
Screen Vision Module for Neura AI.
Enables dynamic screen understanding, OCR, visual element detection,
spatial sorting, and adaptive mouse/keyboard actions without hardcoded coordinates.

Coordinate System Design:
    - OCR returns bounding boxes in SCREENSHOT PIXEL SPACE (physical pixels).
    - pyautogui.moveTo() expects LOGICAL (mouse) COORDINATE SPACE.
    - On Windows with DPI scaling (e.g. 125%, 150%), these differ.
    - We compute dpi_scale = screenshot_size / pyautogui.size() and divide
      all OCR coordinates by this factor so that element['center'] values
      can be passed directly to pyautogui.moveTo().
"""

import os
import sys
import re
import time
import asyncio
import ctypes
from typing import Dict, Any, List, Optional, Tuple
from PIL import Image, ImageGrab

# Configure stdout and stderr for safe UTF-8 output on Windows consoles
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# ──────────────────────────────────────────────────────────────
# DPI Awareness — MUST be set BEFORE importing pyautogui so
# that pyautogui.size() and GetSystemMetrics return physical px.
# ──────────────────────────────────────────────────────────────
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # Per-monitor DPI aware
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

import pyautogui
import pygetwindow as gw

# Optional OCR engines
try:
    import winocr
    HAS_WINOCR = True
except ImportError:
    HAS_WINOCR = False

try:
    import pytesseract
    HAS_PYTESSERACT = True
except ImportError:
    HAS_PYTESSERACT = False

# Configuration Flags
SCREEN_VISION_TEST_MODE = False  # When True: moves mouse to target & logs coordinates without clicking
SCREEN_CLOUD_VISION = False      # Privacy: do not send screenshots to cloud APIs by default
SCREEN_CONTEXT_TIMEOUT = 5.0     # Re-use screen analysis within 5 seconds if window title unchanged
CONFIDENCE_THRESHOLD = 0.50

ORDINAL_MAP = {
    'first': 1, '1st': 1, 'top': 1, 'one': 1, '1': 1,
    'second': 2, '2nd': 2, 'two': 2, '2': 2,
    'third': 3, '3rd': 3, 'three': 3, '3': 3,
    'fourth': 4, '4th': 4, 'four': 4, '4': 4,
    'fifth': 5, '5th': 5, 'five': 5, '5': 5,
    'sixth': 6, '6th': 6, 'six': 6, '6': 6,
    'seventh': 7, '7th': 7, 'seven': 7, '7': 7,
    'eighth': 8, '8th': 8, 'eight': 8, '8': 8,
    'ninth': 9, '9th': 9, 'nine': 9, '9': 9,
    'tenth': 10, '10th': 10, 'ten': 10, '10': 10
}

# Semantic Layout Dictionaries
GOOGLE_TABS = [
    "ai mode", "all", "images", "videos", "news", "forums", "short videos",
    "shopping", "maps", "books", "flights", "finance", "more", "tools",
    "perspectives", "web"
]

YOUTUBE_CHIPS = [
    "all", "music", "podcasts", "mixes", "live", "gaming", "news",
    "bengali cinema", "dramedy", "recently uploaded", "watched",
    "new to you", "playlists", "bengali", "hindi", "cinema", "action-adventure"
]

YOUTUBE_NAV_TABS = [
    "home", "shorts", "subscriptions", "you", "library", "history",
    "your videos", "watch later", "liked videos", "trending", "explore"
]


class ScreenVision:
    """
    Intelligent Screen Vision Engine for Neura AI.
    Performs dynamic screenshot capture, OCR text extraction, visual element grouping,
    spatial sorting, target finding, and coordinate resolution.
    
    All element coordinates stored in self.current_screen_context are in LOGICAL
    (pyautogui mouse) coordinate space, ready for direct use with pyautogui.moveTo().
    """

    def __init__(self, test_mode: bool = SCREEN_VISION_TEST_MODE):
        self.test_mode = test_mode
        self.screen_vision_enabled = True
        self.runtime_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "runtime", "screenshots")
        os.makedirs(self.runtime_dir, exist_ok=True)

        self.current_screen_context: Optional[Dict[str, Any]] = None
        self.dpi_scale: Tuple[float, float] = (1.0, 1.0)
        self._setup_tesseract_path()

    def _setup_tesseract_path(self):
        """Discovers Tesseract executable if installed in common Windows locations."""
        if HAS_PYTESSERACT:
            candidates = [
                r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
                os.path.expanduser(r"~\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"),
                r"C:\Tesseract-OCR\tesseract.exe"
            ]
            for p in candidates:
                if os.path.exists(p):
                    pytesseract.pytesseract.tesseract_cmd = p
                    break

    def _prune_temporary_screenshots(self, max_files: int = 3):
        """Maintains privacy and low disk usage by pruning temporary screenshots."""
        try:
            files = [
                os.path.join(self.runtime_dir, f)
                for f in os.listdir(self.runtime_dir)
                if f.endswith(('.png', '.jpg'))
            ]
            files.sort(key=os.path.getmtime)
            while len(files) > max_files:
                os.remove(files.pop(0))
        except Exception:
            pass

    # ================================================================
    #  DPI SCALE COMPUTATION
    # ================================================================

    def _compute_dpi_scale(self, screenshot_size: Tuple[int, int]) -> Tuple[float, float]:
        """
        Computes the DPI scale factor between screenshot pixel coordinates
        and pyautogui's logical mouse coordinate space.

        Example (125% Windows DPI):
            Screenshot:  1920 x 1080  (physical pixels)
            pyautogui:   1536 x 864   (logical coordinates)
            Scale:       1.25 x 1.25

        If SetProcessDpiAwareness(2) is fully effective, both spaces match
        and scale = (1.0, 1.0).  The math handles both cases transparently.
        """
        logical_w, logical_h = pyautogui.size()
        ss_w, ss_h = screenshot_size

        scale_x = ss_w / logical_w if logical_w > 0 else 1.0
        scale_y = ss_h / logical_h if logical_h > 0 else 1.0

        # Sanity checks
        if abs(scale_x - scale_y) > max(scale_x, scale_y) * 0.15:
            print(f"[Screen Vision] [!] Asymmetric DPI scale ({scale_x:.3f}x, {scale_y:.3f}y). "
                  f"Multi-monitor or unusual display config detected.")
        if scale_x > 2.5 or scale_y > 2.5:
            print(f"[Screen Vision] [!] Very high DPI scale ({scale_x:.3f}x, {scale_y:.3f}y). "
                  f"Screenshot may span multiple monitors.")

        return (scale_x, scale_y)

    # ================================================================
    #  WINDOW / DESKTOP HELPERS
    # ================================================================

    def get_active_window_info(self) -> Dict[str, str]:
        """Detects the foreground window title and associated application."""
        self._ensure_input_desktop()
        app_name = "Desktop"
        title = ""
        try:
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            buff = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buff, length + 1)
            title = buff.value.strip()

            # Infer application name
            t_lower = title.lower()
            if "brave" in t_lower:
                app_name = "Brave Browser"
            elif "chrome" in t_lower:
                app_name = "Google Chrome"
            elif "edge" in t_lower:
                app_name = "Microsoft Edge"
            elif "firefox" in t_lower:
                app_name = "Mozilla Firefox"
            elif "youtube" in t_lower:
                app_name = "YouTube"
            elif "antigravity" in t_lower:
                app_name = "Antigravity IDE"
            elif "code" in t_lower:
                app_name = "Visual Studio Code"
            elif "notepad" in t_lower:
                app_name = "Notepad"
            elif "calculator" in t_lower:
                app_name = "Calculator"
            elif "excel" in t_lower:
                app_name = "Microsoft Excel"
            elif "word" in t_lower:
                app_name = "Microsoft Word"
            elif title:
                app_name = title.split("-")[-1].strip() if "-" in title else title
        except Exception:
            pass

        return {"application": app_name, "window_title": title}

    def _ensure_input_desktop(self):
        """Attaches current thread to active Windows Input Desktop if needed."""
        try:
            user32 = ctypes.windll.user32
            hdesk = user32.OpenInputDesktop(0, False, 0x01FF)
            if hdesk:
                user32.SetThreadDesktop(hdesk)
        except Exception:
            pass

    # ================================================================
    #  SCREEN CAPTURE
    # ================================================================

    def capture_screen(self) -> Optional[Image.Image]:
        """
        Captures the current full desktop display and temporarily buffers it.
        Returns PIL Image in screenshot pixel space.
        """
        self._ensure_input_desktop()
        shot = None
        try:
            shot = ImageGrab.grab()
        except Exception:
            try:
                shot = pyautogui.screenshot()
            except Exception:
                pass

        if shot:
            try:
                timestamp = int(time.time() * 1000)
                temp_path = os.path.join(self.runtime_dir, f"capture_{timestamp}.png")
                shot.save(temp_path)
                self._prune_temporary_screenshots(max_files=3)
                print(f"[Screen Vision] Screenshot captured ({shot.size[0]}x{shot.size[1]})")
            except Exception:
                pass
            return shot

        print("[Screen Vision] Warning: Could not capture desktop display.")
        return None

    # ================================================================
    #  OCR
    # ================================================================

    def _ocr_image(self, image: Image.Image) -> List[Dict[str, Any]]:
        """
        Runs OCR on image and returns raw word/line bounding boxes
        in SCREENSHOT PIXEL SPACE (not yet scaled to mouse coordinates).
        """
        words = []

        # 1. Try Windows Media OCR (Native on Windows 10/11)
        if HAS_WINOCR:
            try:
                res = winocr.recognize_pil_sync(image, 'en')
                if isinstance(res, dict) and 'lines' in res:
                    for line in res['lines']:
                        line_words = line.get('words', [])
                        if not line_words:
                            continue
                        line_text = line.get('text', '').strip()
                        if not line_text:
                            continue
                        min_x = min(w['bounding_rect']['x'] for w in line_words)
                        min_y = min(w['bounding_rect']['y'] for w in line_words)
                        max_x = max(w['bounding_rect']['x'] + w['bounding_rect']['width'] for w in line_words)
                        max_y = max(w['bounding_rect']['y'] + w['bounding_rect']['height'] for w in line_words)

                        words.append({
                            "text": line_text,
                            "x": int(min_x),
                            "y": int(min_y),
                            "width": int(max_x - min_x),
                            "height": int(max_y - min_y),
                            "confidence": 0.94
                        })
                    if words:
                        return words
            except Exception as e:
                print(f"[Screen Vision] Windows OCR note: {e}")

        # 2. Try PyTesseract
        if HAS_PYTESSERACT:
            try:
                data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
                n_boxes = len(data.get('text', []))
                for i in range(n_boxes):
                    t = data['text'][i].strip()
                    conf = float(data.get('conf', [0])[i])
                    if t and conf > 20:
                        words.append({
                            "text": t,
                            "x": int(data['left'][i]),
                            "y": int(data['top'][i]),
                            "width": int(data['width'][i]),
                            "height": int(data['height'][i]),
                            "confidence": round(conf / 100.0, 2)
                        })
                if words:
                    return words
            except Exception as e:
                print(f"[Screen Vision] PyTesseract note: {e}")

        return words

    # ================================================================
    #  ELEMENT GROUPING (OCR → Structured Elements)
    # ================================================================

    def _group_words_into_elements(
        self,
        words: List[Dict[str, Any]],
        screen_w: int,
        screen_h: int,
        dpi_scale: Tuple[float, float] = (1.0, 1.0)
    ) -> List[Dict[str, Any]]:
        """
        Structures OCR words/lines into clean elements with precise bounding boxes
        and clickable centers.

        All output coordinates are converted from screenshot pixel space to
        LOGICAL (mouse) coordinate space using the provided dpi_scale factor,
        so that element['center'] can be passed directly to pyautogui.moveTo().
        """
        if not words:
            return []

        scale_x, scale_y = dpi_scale
        elements = []
        elem_id = 1

        for w in words:
            txt = w['text'].strip()
            if len(txt) < 2 and not txt.isdigit():
                continue

            # ── Convert from screenshot pixel space → logical mouse space ──
            raw_x = w['x']
            raw_y = w['y']
            raw_w = w['width']
            raw_h = w['height']

            min_x = int(raw_x / scale_x)
            min_y = int(raw_y / scale_y)
            width = int(raw_w / scale_x)
            height = int(raw_h / scale_y)
            max_x = min_x + width
            max_y = min_y + height

            # Click center: for wide text, click near the left portion
            # to hit the actual text, not trailing whitespace
            if width > 220:
                cx = int(min_x + min(width // 2, 110))
            else:
                cx = (min_x + max_x) // 2
            cy = (min_y + max_y) // 2

            txt_lower = txt.lower()

            # Classify element type
            elem_type = "text"
            if any(b in txt_lower for b in ["search", "submit", "login", "sign in", "subscribe", "cancel", "ok"]):
                elem_type = "button"
            elif any(v in txt_lower for v in ["views", "ago", "k views", "m views", "subscriber"]):
                elem_type = "metadata"
            elif any(s in txt_lower for s in ["song", "music", "audio", "lyrics", "track", "album"]):
                elem_type = "song"
            elif bool(re.search(r"\b\d+:\d{2}\b", txt)):
                elem_type = "timestamp"
            elif len(txt.split()) >= 2:
                elem_type = "link"

            elements.append({
                "id": elem_id,
                "type": elem_type,
                "text": txt,
                "bbox": [min_x, min_y, max_x, max_y],
                "center": [cx, cy],
                "confidence": w['confidence'],
                "width": width,
                "height": height
            })
            elem_id += 1

        return elements

    # ================================================================
    #  SEMANTIC PAGE & ELEMENT CLASSIFICATION
    # ================================================================

    def _detect_page_type(
        self,
        window_title: str,
        elements: List[Dict[str, Any]],
        screen_w: int,
        screen_h: int
    ) -> str:
        """
        Detects whether the active page is Google Search, YouTube, or general.
        Checks both window title and on-screen landmark keywords.
        """
        wt = (window_title or "").lower()
        if "youtube" in wt:
            return "youtube"
        if "google search" in wt or ("google" in wt and "search" in wt):
            return "google_search"

        # Check OCR landmarks if window title is generic (e.g. "Brave", "Chrome", "New Tab")
        first_text = " ".join(e["text"].lower() for e in elements[:35])
        if "youtube" in first_text or ("shorts" in first_text and "subscriptions" in first_text):
            return "youtube"
        if "google" in first_text and any(k in first_text for k in ["images", "videos", "short videos", "tools", "ai mode"]):
            return "google_search"

        return "general"

    def _classify_elements_semantically(
        self,
        elements: List[Dict[str, Any]],
        page_type: str,
        screen_w: int,
        screen_h: int
    ) -> List[Dict[str, Any]]:
        """
        Enriches elements with high-level semantic roles:
            - 'search_bar': Search input field on Google / YouTube
            - 'tab': Navigation / filter tabs & chips (AI Mode, Images, Videos, Music, Shorts, etc.)
            - 'link_title': Clickable title / headline of a result or video
            - 'link_description': Descriptive text / summary under a link
            - 'link_url': URL / breadcrumb text
            - 'video_title': Clickable title of a video
            - 'channel_name': Channel author or site name
            - 'video_metadata': Views, timestamps, duration
            - 'button': Clickable UI buttons
            - 'text': General text
        """
        if not elements:
            return []

        for elem in elements:
            cx, cy = elem["center"]
            txt = elem["text"].strip()
            txt_lower = txt.lower()
            word_count = len(txt.split())

            sem_type = elem.get("type", "text")
            sem_details: Dict[str, Any] = {}

            # ── 1. GOOGLE SEARCH PAGE ──
            if page_type == "google_search":
                # Google Search Bar (y ≈ 6% - 13%, x ≈ 10% - 72%)
                if int(screen_h * 0.06) <= cy <= int(screen_h * 0.13) and int(screen_w * 0.10) <= cx <= int(screen_w * 0.72):
                    if not any(k in txt_lower for k in ["http", "brave", "chrome", "gmail", "maps"]):
                        sem_type = "search_bar"
                        elem["type"] = "search_bar"
                        sem_details["role"] = "search_input"

                # Google Filter Tabs (y ≈ 12% - 18%, x ≈ 8% - 85%)
                elif int(screen_h * 0.12) <= cy <= int(screen_h * 0.18) and int(screen_w * 0.08) <= cx <= int(screen_w * 0.85):
                    matched_tab = None
                    for tab in GOOGLE_TABS:
                        if tab == txt_lower or (len(tab) > 3 and tab in txt_lower):
                            matched_tab = tab
                            break
                    if matched_tab or word_count <= 2:
                        sem_type = "tab"
                        elem["type"] = "tab"
                        sem_details["tab_name"] = matched_tab or txt_lower

            # ── 2. YOUTUBE PAGE ──
            elif page_type == "youtube":
                # YouTube Search Bar (y ≈ 3% - 9%, x ≈ 18% - 78%)
                if int(screen_h * 0.03) <= cy <= int(screen_h * 0.09) and int(screen_w * 0.18) <= cx <= int(screen_w * 0.78):
                    if "search" in txt_lower or word_count >= 1:
                        sem_type = "search_bar"
                        elem["type"] = "search_bar"
                        sem_details["role"] = "search_input"

                # Horizontal Filter Chips (y ≈ 7% - 15%, x ≈ 12% - 95%)
                elif int(screen_h * 0.07) <= cy <= int(screen_h * 0.15) and int(screen_w * 0.12) <= cx <= int(screen_w * 0.95):
                    matched_chip = None
                    for chip in YOUTUBE_CHIPS:
                        if chip == txt_lower or (len(chip) > 3 and chip in txt_lower):
                            matched_chip = chip
                            break
                    if matched_chip or word_count <= 3:
                        sem_type = "tab"
                        elem["type"] = "tab"
                        sem_details["tab_name"] = matched_chip or txt_lower

                # Left Sidebar Navigation Tabs (x <= 15%, y ≈ 8% - 90%)
                elif cx <= int(screen_w * 0.15) and int(screen_h * 0.08) <= cy <= int(screen_h * 0.90):
                    matched_nav = None
                    for nav in YOUTUBE_NAV_TABS:
                        if nav == txt_lower or nav in txt_lower:
                            matched_nav = nav
                            break
                    if matched_nav or word_count <= 2:
                        sem_type = "tab"
                        elem["type"] = "tab"
                        sem_details["tab_name"] = matched_nav or txt_lower

            # ── 3. GENERAL PAGE / FALLBACK ──
            else:
                if int(screen_h * 0.05) <= cy <= int(screen_h * 0.12) and int(screen_w * 0.15) <= cx <= int(screen_w * 0.75):
                    if any(w in txt_lower for w in ["search", "find", "query"]):
                        sem_type = "search_bar"
                        elem["type"] = "search_bar"

            # URL, Metadata, and Button generic fallbacks if not already set
            if sem_type == "text":
                if any(m in txt_lower for m in ["http://", "https://", "www.", ".com", ".org", ".edu", ".gov", " \u203a ", " > "]):
                    sem_type = "link_url"
                elif any(v in txt_lower for v in ["views", "ago", "k views", "m views", "subscriber"]):
                    sem_type = "video_metadata"
                elif bool(re.search(r"\b\d+:\d{2}\b", txt)):
                    sem_type = "video_metadata"
                elif any(b in txt_lower for b in ["search", "submit", "login", "sign in", "subscribe", "cancel", "ok"]):
                    sem_type = "button"

            elem["semantic_type"] = sem_type
            if sem_details:
                elem["semantic_details"] = sem_details

        # ── Second Pass: Content Card Clustering for Links & Descriptions ──
        content_top = int(screen_h * 0.16) if page_type == "google_search" else int(screen_h * 0.10)
        content_bot = int(screen_h * 0.95)
        content_elems = [e for e in elements if content_top <= e["center"][1] <= content_bot and e.get("semantic_type") not in ("tab", "search_bar")]

        if content_elems:
            card_gap = int(screen_h * 0.015) if page_type == "youtube" else int(screen_h * 0.035)
            cards = self._cluster_into_cards(content_elems, card_gap)
            for card in cards:
                ctx_type = "video" if page_type == "youtube" else "result"
                title_elem = self._pick_card_title(card, ctx_type)
                for item in card:
                    if item == title_elem:
                        item["semantic_type"] = "video_title" if page_type == "youtube" else "link_title"
                        item["type"] = "link"
                    elif item.get("semantic_type") in ("link_url", "video_metadata", "button", "tab", "search_bar"):
                        item["type"] = "text"
                        continue
                    else:
                        item["type"] = "text"
                        if item["center"][1] > title_elem["center"][1]:
                            item["semantic_type"] = "link_description"
                        elif len(item["text"].split()) <= 4:
                            item["semantic_type"] = "channel_name" if page_type == "youtube" else "site_badge"
                        else:
                            item["semantic_type"] = "link_description"

        return elements

    # ================================================================
    #  SCREEN ANALYSIS  (capture → OCR → structured context)
    # ================================================================

    def analyze_screen(self, screenshot: Optional[Image.Image] = None, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Captures or takes provided screenshot, executes OCR, groups elements,
        and constructs the structured Screen Representation.
        All element coordinates are in LOGICAL (pyautogui mouse) space.
        """
        win_info = self.get_active_window_info()

        # Check cached screen context
        if not force_refresh and self.current_screen_context:
            elapsed = time.time() - self.current_screen_context.get("timestamp", 0)
            if elapsed < SCREEN_CONTEXT_TIMEOUT and self.current_screen_context.get("window_title") == win_info["window_title"]:
                return self.current_screen_context

        if screenshot is None:
            screenshot = self.capture_screen()

        # Logical screen dimensions — what pyautogui uses for mouse coordinates
        screen_w, screen_h = pyautogui.size()

        # Compute DPI scale factor
        dpi_scale = (1.0, 1.0)
        if screenshot:
            dpi_scale = self._compute_dpi_scale(screenshot.size)
            self.dpi_scale = dpi_scale
            print(f"[Screen Vision] DPI Scale: {dpi_scale[0]:.3f}x, {dpi_scale[1]:.3f}y | "
                  f"Screenshot: {screenshot.size[0]}x{screenshot.size[1]} | "
                  f"Logical: {screen_w}x{screen_h}")

        elements = []
        page_type = "general"
        if screenshot:
            raw_words = self._ocr_image(screenshot)
            elements = self._group_words_into_elements(raw_words, screen_w, screen_h, dpi_scale)
            page_type = self._detect_page_type(win_info.get("window_title", ""), elements, screen_w, screen_h)
            elements = self._classify_elements_semantically(elements, page_type, screen_w, screen_h)
            print(f"[Screen Vision] Page Type: '{page_type}' | OCR detected {len(elements)} structured elements (all coords in logical space).")

        context = {
            "timestamp": time.time(),
            "screen_size": {"width": screen_w, "height": screen_h},
            "dpi_scale": dpi_scale,
            "application": win_info["application"],
            "window_title": win_info["window_title"],
            "page_type": page_type,
            "elements": elements
        }
        self.current_screen_context = context
        return context

    # ================================================================
    #  ORDINAL / CATEGORY PARSING
    # ================================================================

    def _extract_ordinal_and_keyword(self, target_description: str) -> Tuple[Optional[int], str, Optional[str]]:
        """
        Extracts ordinal index (1, 2, 3...), category, and topic/tab keyword.
        Supported Categories:
            - 'search_bar': Search input field on Google / YouTube
            - 'tab': Navigation / filter tab (AI Mode, Images, Videos, Music, Shorts, etc.)
            - 'link': Clickable title / headline of a result or webpage
            - 'description': Snippet / summary description text under a link
            - 'video': Video card or title
            - 'song': Song card or title
            - 'result': Search result
            - 'button': Clickable UI button
            - 'all': General fallback
        """
        desc = target_description.strip().lower()

        # 1. Detect Ordinal
        target_idx = None
        ord_pattern = r"\b(first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th|sixth|6th|seventh|7th|eighth|8th|ninth|9th|tenth|10th|top|\d+)\b"
        ord_match = re.search(ord_pattern, desc)
        if ord_match:
            tok = ord_match.group(1)
            target_idx = ORDINAL_MAP.get(tok)
            if target_idx is None and tok.isdigit():
                target_idx = int(tok)

        # 2. Detect Category
        category = "all"
        known_tab_names = [
            "ai mode", "short videos", "images", "videos", "news", "forums",
            "shopping", "maps", "books", "finance", "tools", "music",
            "shorts", "subscriptions", "library", "all"
        ]

        if any(w in desc for w in ["search bar", "search box", "search field", "search input", "search text box"]):
            category = "search_bar"
        elif any(w in desc for w in ["link description", "result description", "video description", "description", "snippet"]):
            category = "description"
        elif "tab" in desc or "tabs" in desc or "filter chip" in desc:
            category = "tab"
        elif any(f"{t} tab" in desc or f"tab {t}" in desc for t in known_tab_names):
            category = "tab"
        elif any(w in desc for w in ["video", "videos"]):
            category = "video"
        elif any(w in desc for w in ["song", "songs", "music", "track"]):
            category = "song"
        elif any(w in desc for w in ["search result", "search results", "result", "results"]):
            category = "result"
        elif any(w in desc for w in ["link", "links", "headline"]):
            category = "link"
        elif any(w in desc for w in ["button", "btn"]):
            category = "button"

        # 3. Detect Keyword / Specific Sub-Target
        keyword = None

        if category == "tab":
            clean_tab = re.sub(
                r"\b(open|play|click|select|choose|go\s+to|switch\s+to|the|first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th|tab|tabs|filter|chip|button|one|item)\b",
                "",
                desc
            ).strip()
            if clean_tab:
                keyword = clean_tab
            else:
                for t in known_tab_names:
                    if t in desc:
                        keyword = t
                        break

        elif category == "search_bar":
            keyword = None

        elif category in ("link", "result", "description", "video", "song"):
            kw_match = re.search(r"(?:about|called|named|with|for)\s+([a-zA-Z0-9\s]+)", desc)
            if kw_match:
                keyword = kw_match.group(1).strip()
            else:
                clean = re.sub(
                    r"\b(open|play|click|select|choose|go\s+to|switch\s+to|the|this|a|an|any|first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th|sixth|6th|seventh|7th|eighth|8th|ninth|9th|tenth|10th|video|videos|song|songs|link|links|result|results|google|search|description|snippet|summary|one|item|on|in|from|at|browser|web|website|webpage|page|screen|window|desktop|active|current)\b",
                    "",
                    desc
                ).strip()
                clean = re.sub(r"\s+", " ", clean).strip()
                if len(clean) > 2:
                    keyword = clean

        else:
            kw_match = re.search(r"(?:about|called|named|with|for)\s+([a-zA-Z0-9\s]+)", desc)
            if kw_match:
                keyword = kw_match.group(1).strip()
            else:
                clean = re.sub(
                    r"\b(open|play|click|select|choose|go\s+to|switch\s+to|the|this|a|an|any|first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th|sixth|6th|seventh|7th|eighth|8th|ninth|9th|tenth|10th|video|videos|song|songs|link|links|result|results|google|search|description|snippet|summary|one|item|on|in|from|at|browser|web|website|webpage|page|screen|window|desktop|active|current)\b",
                    "",
                    desc
                ).strip()
                clean = re.sub(r"\s+", " ", clean).strip()
                if len(clean) > 2:
                    keyword = clean

        return target_idx, category, keyword

    # ================================================================
    #  CARD-BASED CLUSTERING HELPERS
    # ================================================================

    def _cluster_into_cards(self, elements: List[Dict[str, Any]], gap_threshold: float) -> List[List[Dict[str, Any]]]:
        """
        Groups elements (sorted by Y) into distinct content "cards" based on
        vertical gaps between consecutive elements.

        Elements within the same card have small vertical gaps.
        A gap >= gap_threshold between consecutive elements indicates a new card.

        Args:
            elements:      Already-filtered content elements (unsorted is OK).
            gap_threshold:  Minimum vertical gap (logical px) to start a new card.

        Returns:
            List of cards, each card being a list of elements.
        """
        if not elements:
            return []

        sorted_elems = sorted(elements, key=lambda e: (e['center'][1], e['center'][0]))
        cards: List[List[Dict[str, Any]]] = []
        current_card: List[Dict[str, Any]] = [sorted_elems[0]]

        for i in range(1, len(sorted_elems)):
            prev = current_card[-1]
            curr = sorted_elems[i]

            # Edge-to-edge gap: bottom of previous → top of current
            edge_gap = curr['bbox'][1] - prev['bbox'][3]
            # Center-to-center distance
            center_gap = curr['center'][1] - prev['center'][1]

            # New card if edge gap is large, OR center gap is very large
            if edge_gap > gap_threshold or center_gap > gap_threshold * 2.0:
                cards.append(current_card)
                current_card = [curr]
            else:
                current_card.append(curr)

        if current_card:
            cards.append(current_card)

        return cards

    def _pick_card_title(self, card: List[Dict[str, Any]], context_type: str = "result") -> Dict[str, Any]:
        """
        Picks the primary clickable title/heading from a grouped content card.
        Decisively selects the clickable link title (e.g. blue <h3> search result heading
        or YouTube video title) and rejects description snippets, breadcrumb URLs,
        channel names, or metadata lines.
        """
        if not card:
            return {}
        if len(card) == 1:
            return card[0]

        metadata_markers = [
            'views', 'ago', 'subscriber', 'subscribers', 'k views', 'm views', 'duration',
            'cached', 'similar', 'translate this page', 'autoplay', 'queue', 'save', 'share',
            'report', 'download'
        ]
        nav_markers = {
            'all', 'images', 'videos', 'news', 'shopping', 'forums',
            'tools', 'more', 'feedback', 'settings', 'sign in', 'about',
            'home', 'trending', 'shorts', 'subscriptions', 'library', 'history'
        }
        header_patterns = [
            r'^people\s+also',
            r'^related\s+searches',
            r'^videos\b',
            r'^images\b',
            r'^shorts\b',
            r'^up\s*next\b',
            r'^recommended\b',
            r'^now\s*playing\b',
            r'^playlist\b',
            r'^mix\s*[-–]',
        ]

        desc_patterns = [
            r"\b(i\'m|i am|we are|he is|she is)\b",
            r"\b(student|specializing|passionate|developer who|profile on)\b",
            r"\b(connections|followers|following|reviews|ratings)\b",
            r"\b(missing:|must include:|published|hours ago|days ago|months ago|years ago)\b",
            r"(\.\.\.|\u2026)",
            r"(@gmail|@yahoo|\+\d{2})"
        ]

        # Determine maximum font height in this card
        max_h_in_card = max(it.get("height", it["bbox"][3] - it["bbox"][1]) for it in card)

        candidates = []
        for idx, item in enumerate(card):
            text = item['text']
            text_lower = text.lower().strip()
            words = text.split()
            word_count = len(words)
            h = item.get("height", item["bbox"][3] - item["bbox"][1])

            # 1. Single-word brand badges or icons (e.g. "Instagram", "LinkedIn", "YouTube", "GitHub")
            # A true search result link title is virtually never a single word.
            if word_count < 2 and len(text) < 15:
                continue

            # 2. Skip obvious URLs, breadcrumbs, and metadata lines
            if any(m in text_lower for m in ['http://', 'https://', 'www.', ' \u203a ', ' > ']) or re.search(r'\.[a-z]{2,4}/', text_lower):
                continue
            if any(m in text_lower for m in metadata_markers):
                continue
            if text_lower in nav_markers:
                continue
            if re.match(r'^\d+:\d{2}$', text.strip()):
                continue

            score = 25.0

            # 3. Position in card (headings/titles appear near the top of the card)
            if idx == 0:
                score += 20.0
            elif idx == 1:
                score += 15.0
            elif idx == 2:
                score += 5.0
            else:
                score -= (idx - 1) * 10.0

            # 4. Font height (clickable titles are styled with larger font sizes)
            if h == max_h_in_card and h >= 18:
                score += 25.0
            elif h >= 18:
                score += 15.0
            elif h <= 15 and max_h_in_card >= 18:
                score -= 15.0

            # 5. Length preference (titles are typically 3-10 words; descriptions are 14+ words)
            if 3 <= word_count <= 10:
                score += 15.0
            elif 11 <= word_count <= 13:
                score += 5.0
            elif word_count >= 14:
                score -= (word_count - 12) * 3.0

            # 6. Description markers penalty
            for pat in desc_patterns:
                if re.search(pat, text_lower):
                    score -= 35.0

            # 7. Section headers penalty
            if any(re.match(pat, text_lower) for pat in header_patterns):
                score -= 40.0

            # 8. Channel name heuristic for videos: "X of Y" or 1-2 words
            if context_type == "video" and word_count <= 2 and h < max_h_in_card:
                score -= 15.0

            candidates.append((item, score))

        if candidates:
            # Sort by highest score; break ties by position (earlier = higher)
            candidates.sort(key=lambda x: -x[1])
            return candidates[0][0]

        # Fallback: first multi-word item with length >= 2
        for item in card:
            if len(item['text'].split()) >= 2:
                return item
        return card[0]

    # ================================================================
    #  TARGET FINDING
    # ================================================================

    def find_target(self, target_description: str, screen_elements: Optional[List[Dict[str, Any]]] = None) -> Optional[Dict[str, Any]]:
        """
        Finds the exact target element from the visible screen based on the
        user's natural-language description.

        All coordinates are in LOGICAL (mouse) space, ready for pyautogui.moveTo().

        Pipeline:
            1. Parse ordinal, category, keyword from description.
            2. Filter screen elements to the main content area (exclude browser
               chrome, taskbar, sidebars) using PROPORTIONAL thresholds.
            3. Cluster filtered elements into distinct content "cards".
            4. Pick the clickable title from the requested card.
        """
        if screen_elements is None:
            ctx = self.analyze_screen()
            screen_elements = ctx.get("elements", [])
            screen_w = ctx.get("screen_size", {}).get("width", pyautogui.size()[0])
            screen_h = ctx.get("screen_size", {}).get("height", pyautogui.size()[1])
        else:
            screen_w, screen_h = pyautogui.size()

        if not screen_elements:
            print("[Screen Vision] No elements detected to search target.")
            return None

        target_idx, category, keyword = self._extract_ordinal_and_keyword(target_description)
        print(f"[Screen Vision] Target: '{target_description}' -> "
              f"Category={category}, Index={target_idx}, Keyword={keyword}")

        # ── Proportional thresholds (in logical coordinates) ──
        # Top: browser chrome / tabs / address bar ≈ top 14 %
        top_cutoff = int(screen_h * 0.14)
        # Bottom: Windows taskbar ≈ bottom 5 %
        bottom_cutoff = int(screen_h * 0.95)
        # Left: sidebar / navigation drawer ≈ left 10 %
        left_cutoff = int(screen_w * 0.10)
        # Right: keep main content column ≈ left 65 %
        right_cutoff = int(screen_w * 0.65)
        # Card gap: vertical gap between distinct content cards ≈ 3.5 % of height
        card_gap = int(screen_h * 0.035)

        # Special: does user want something in the chrome area?
        asking_for_chrome = any(k in target_description.lower() for k in
                                ["tab", "address", "url", "menu", "title bar", "taskbar", "clock"])

        # Common noise terms to exclude
        nav_noise = {'all', 'images', 'videos', 'news', 'shopping', 'forums',
                     'tools', 'more', 'settings', 'sign in', 'about', 'feedback'}
        system_noise = ['.py', '.json', '.md', 'powershell', 'terminal', 'venv', '__pycache__']

        # =============================================================
        # 1. SEARCH BAR  (Google, YouTube, etc.)
        # =============================================================
        if category == "search_bar":
            win_title_l = (self.current_screen_context.get("window_title", "") if self.current_screen_context else "").lower()
            is_yt = "youtube" in win_title_l

            sb_candidates = [e for e in screen_elements if e.get("semantic_type") == "search_bar"]
            if not sb_candidates:
                sb_y_min = int(screen_h * 0.03) if is_yt else int(screen_h * 0.06)
                sb_y_max = int(screen_h * 0.10) if is_yt else int(screen_h * 0.14)
                sb_x_min = int(screen_w * 0.12)
                sb_x_max = int(screen_w * 0.75)
                for e in screen_elements:
                    cx, cy = e["center"]
                    if sb_y_min <= cy <= sb_y_max and sb_x_min <= cx <= sb_x_max:
                        if not any(k in e["text"].lower() for k in ["http", "brave", "chrome", "gmail", "maps"]):
                            sb_candidates.append(e)

            if sb_candidates:
                sb_candidates.sort(key=lambda e: (e['center'][1], e['center'][0]))
                chosen = sb_candidates[0]
                print(f"[Screen Vision] -> Search Bar: '{chosen['text'][:40]}' @ center={chosen['center']}")
                return chosen

            # Geometric fallback: calibrated coordinates so search bar always succeeds
            if is_yt:
                cx = int(screen_w * 0.45)
                cy = int(screen_h * 0.055)
            else:
                cx = int(screen_w * 0.35)
                cy = int(screen_h * 0.10)

            fallback_sb = {
                "id": 9999,
                "type": "search_bar",
                "semantic_type": "search_bar",
                "text": "Search Bar",
                "bbox": [cx - 150, cy - 18, cx + 150, cy + 18],
                "center": [cx, cy],
                "confidence": 0.99,
                "width": 300,
                "height": 36
            }
            print(f"[Screen Vision] -> Search Bar (Calibrated Center): @ center={fallback_sb['center']}")
            return fallback_sb

        # =============================================================
        # 2. TABS & FILTER CHIPS  (Google tabs, YouTube chips/nav)
        # =============================================================
        if category == "tab":
            tab_candidates = [e for e in screen_elements if e.get("semantic_type") == "tab"]
            if not tab_candidates:
                tab_top = int(screen_h * 0.06)
                tab_bot = int(screen_h * 0.18)
                for e in screen_elements:
                    cx, cy = e["center"]
                    if tab_top <= cy <= tab_bot and e.get("width", 0) < screen_w * 0.25:
                        tab_candidates.append(e)

            if not tab_candidates:
                print("[Screen Vision] No tab candidates found.")
                return None

            # Keyword match (e.g. "images", "videos", "all", "short videos", "news", "music", "shorts", "tools")
            if keyword:
                kw_l = keyword.lower().strip()
                scored_tabs = []
                for t in tab_candidates:
                    t_txt = t["text"].lower().strip()
                    score = 0.0
                    if kw_l == t_txt:
                        score = 1.0
                    elif kw_l in t_txt:
                        score = 0.85
                    elif any(w in t_txt for w in kw_l.split()):
                        score = 0.65
                    if score > 0:
                        scored_tabs.append((t, score))

                if scored_tabs:
                    scored_tabs.sort(key=lambda x: -x[1])
                    chosen = scored_tabs[0][0]
                    print(f"[Screen Vision] -> Tab '{keyword}': '{chosen['text']}' @ center={chosen['center']}")
                    return chosen

            # Ordinal match: sort horizontally (left-to-right)
            tab_candidates.sort(key=lambda e: (e["center"][1] // int(screen_h * 0.03), e["center"][0]))
            idx = (target_idx or 1) - 1
            idx = min(max(0, idx), len(tab_candidates) - 1)
            chosen = tab_candidates[idx]
            print(f"[Screen Vision] -> Tab #{idx+1}: '{chosen['text']}' @ center={chosen['center']}")
            return chosen

        # =============================================================
        # 3. LINKS & SEARCH RESULTS  (Clickable titles only)
        # =============================================================
        if category in ("link", "result") or "search result" in target_description.lower():
            content = self._filter_content_area(
                screen_elements, top_cutoff, bottom_cutoff,
                left_cutoff, right_cutoff, nav_noise, system_noise
            )
            if not content:
                print("[Screen Vision] No link/result candidates found.")
                return None

            cards = self._cluster_into_cards(content, card_gap)
            self._log_cards(cards, "Link/Result")

            result_entries = []
            for c in cards:
                title_elem = next((e for e in c if e.get("semantic_type") in ("link_title", "video_title")), None)
                if not title_elem:
                    title_elem = self._pick_card_title(c, "result")
                    title_elem["semantic_type"] = "link_title"
                    title_elem["type"] = "link"
                result_entries.append(title_elem)

            if result_entries:
                if keyword:
                    kw_l = keyword.lower()
                    matched = [e for e in result_entries if kw_l in e["text"].lower()]
                    if matched:
                        chosen = matched[0]
                        print(f"[Screen Vision] -> Link about '{keyword}': '{chosen['text'][:60]}' @ center={chosen['center']}")
                        return chosen

                idx = (target_idx or 1) - 1
                idx = min(max(0, idx), len(result_entries) - 1)
                chosen = result_entries[idx]
                print(f"[Screen Vision] -> Link/Result #{idx+1}: '{chosen['text'][:60]}' @ center={chosen['center']}")
                return chosen

        # =============================================================
        # 4. LINK DESCRIPTIONS  (Snippet & summary text under links)
        # =============================================================
        if category == "description":
            content = self._filter_content_area(
                screen_elements, top_cutoff, bottom_cutoff,
                left_cutoff, right_cutoff, nav_noise, system_noise
            )
            if not content:
                print("[Screen Vision] No link description candidates found.")
                return None

            cards = self._cluster_into_cards(content, card_gap)
            desc_entries = []
            for c in cards:
                desc_elem = next((e for e in c if e.get("semantic_type") == "link_description"), None)
                if not desc_elem:
                    title = self._pick_card_title(c, "result")
                    for item in c:
                        if item != title and len(item["text"].split()) >= 3:
                            desc_elem = item
                            break
                if desc_elem:
                    desc_entries.append(desc_elem)

            if desc_entries:
                idx = (target_idx or 1) - 1
                idx = min(max(0, idx), len(desc_entries) - 1)
                chosen = desc_entries[idx]
                print(f"[Screen Vision] -> Link Description #{idx+1}: '{chosen['text'][:60]}' @ center={chosen['center']}")
                return chosen

        # =============================================================
        # 5. VIDEOS & SONGS  (YouTube, music sites)
        # =============================================================
        if category in ("video", "song"):
            win_title_l = (self.current_screen_context.get("window_title", "") if self.current_screen_context else "").lower()
            is_yt = "youtube" in win_title_l

            yt_right_cutoff = int(screen_w * 0.92) if is_yt else right_cutoff
            yt_card_gap = int(screen_h * 0.015) if is_yt else card_gap

            header_skip = ['music of', 'best of', 'top ', 'popular', 'trending',
                           'recommended', 'related', 'up next', 'now playing',
                           'playlist', 'queue', 'autoplay']

            content = []
            for e in screen_elements:
                cx, cy = e["center"]
                txt = e["text"]
                txt_l = txt.lower()

                if cy < top_cutoff or cy > bottom_cutoff:
                    continue
                if cx < left_cutoff or cx > yt_right_cutoff:
                    continue
                if txt_l.strip() in nav_noise:
                    continue
                if any(k in txt_l for k in system_noise):
                    continue
                if any(txt_l.startswith(h) for h in header_skip):
                    continue

                if is_yt and len(txt.split()) >= 2:
                    content.append(e)
                elif any(m in txt_l for m in ["views", "ago", "video", "subscribe",
                                                "song", "music", "audio", "lyrics",
                                                "track", "album"]):
                    content.append(e)
                elif bool(re.search(r"\b\d+:\d{2}\b", txt)):
                    content.append(e)

            if content:
                cards = self._cluster_into_cards(content, yt_card_gap)
                self._log_cards(cards, category.capitalize())

                media_entries = [self._pick_card_title(c, "video") for c in cards]

                if media_entries:
                    idx = (target_idx or 1) - 1
                    idx = min(idx, len(media_entries) - 1)
                    chosen = media_entries[idx]
                    print(f"[Screen Vision] -> {category.capitalize()} #{idx+1}: "
                          f"'{chosen['text'][:60]}' @ center={chosen['center']}")
                    return chosen

        # =============================================================
        # 6. GENERAL FLOW  (keyword / button / any element)
        # =============================================================
        general_candidates = []
        for elem in screen_elements:
            cx, cy = elem["center"]
            txt_l = elem["text"].lower()

            if not asking_for_chrome:
                if cy < top_cutoff or cy > bottom_cutoff:
                    continue

            # Keyword match (highest priority)
            if keyword and keyword.lower() in txt_l:
                general_candidates.append((elem, 1.0))
                continue

            if category == "button":
                if elem["type"] == "button" or any(b in txt_l for b in ["search", "submit", "login", "play", "pause"]):
                    general_candidates.append((elem, 0.9))
            elif category == "link":
                if elem.get("semantic_type") in ("link_title", "video_title"):
                    general_candidates.append((elem, 0.95))
                elif elem.get("type") == "link" and elem.get("semantic_type") != "link_description":
                    general_candidates.append((elem, 0.8))
            else:
                if len(elem["text"].split()) >= 2:
                    general_candidates.append((elem, 0.7))

        if not general_candidates:
            general_candidates = [
                (e, 0.5) for e in screen_elements
                if asking_for_chrome or (top_cutoff <= e["center"][1] <= bottom_cutoff)
            ]

        if not general_candidates:
            return None

        row_bucket = max(int(screen_h * 0.025), 15)
        sorted_candidates = [
            pair[0] for pair in sorted(
                general_candidates,
                key=lambda p: (p[0]["center"][1] // row_bucket, p[0]["center"][0])
            )
        ]

        if target_idx is not None and target_idx > 0:
            idx = min(target_idx, len(sorted_candidates)) - 1
            chosen = sorted_candidates[idx]
            print(f"[Screen Vision] -> General #{idx+1}: '{chosen['text'][:60]}' @ center={chosen['center']}")
            return chosen

        return sorted_candidates[0]

    # ── find_target helpers ──

    def _filter_content_area(
        self,
        elements: List[Dict[str, Any]],
        top: int, bottom: int, left: int, right: int,
        nav_noise: set, system_noise: list
    ) -> List[Dict[str, Any]]:
        """Returns elements inside the main content rectangle, excluding noise."""
        out = []
        for e in elements:
            cx, cy = e["center"]
            bx1, _, bx2, _ = e["bbox"]
            txt_l = e["text"].lower().strip()

            if cy < top or cy > bottom:
                continue
            if bx1 > right or bx2 < left:
                continue
            if txt_l in nav_noise:
                continue
            if any(f in txt_l for f in ["mode all", "all images", "tools", "feedback"]):
                continue
            if any(k in txt_l for k in system_noise):
                continue

            out.append(e)
        return out

    def _log_cards(self, cards: List[List[Dict[str, Any]]], label: str, limit: int = 6):
        """Prints diagnostic info about detected cards."""
        print(f"[Screen Vision] Found {len(cards)} {label} card(s):")
        for i, card in enumerate(cards[:limit]):
            title = self._pick_card_title(card)
            print(f"  Card {i+1}: '{title['text'][:55]}' | "
                  f"center={title['center']} | lines={len(card)}")

    # ================================================================
    #  MOUSE / KEYBOARD ACTIONS
    # ================================================================

    def click_target(self, target: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Safely moves mouse and clicks the target element's center.
        Center coordinates are already in LOGICAL (mouse) space.
        Adheres to SCREEN_VISION_TEST_MODE.
        """
        if not target:
            return False, "Target element not found on screen."

        cx, cy = target["center"]
        text = target.get("text", "")
        conf = target.get("confidence", 0.0)

        if conf < CONFIDENCE_THRESHOLD:
            return False, f"Target '{text}' detected with low confidence ({conf:.2f}). Clarify target to avoid misclicks."

        if self.test_mode:
            print(f"[Screen Vision] TEST MODE -> Moving cursor to '{text}' at ({cx}, {cy}) without clicking.")
            pyautogui.moveTo(cx, cy, duration=0.25)
            return True, f"[Test Mode] Located '{text}' at ({cx}, {cy}). Mouse cursor positioned without clicking."

        print(f"[Screen Vision] Executing click on '{text}' at ({cx}, {cy}).")
        pyautogui.moveTo(cx, cy, duration=0.2)
        time.sleep(0.06)
        pyautogui.click()
        time.sleep(0.3)

        # Invalidate cached screen context after click
        self.current_screen_context = None
        return True, f"Successfully clicked '{text}' on screen."

    def double_click_target(self, target: Dict[str, Any]) -> Tuple[bool, str]:
        """Double clicks the target element."""
        if not target:
            return False, "Target element not found."

        cx, cy = target["center"]
        text = target.get("text", "")

        if self.test_mode:
            pyautogui.moveTo(cx, cy, duration=0.25)
            return True, f"[Test Mode] Located '{text}' for double click at ({cx}, {cy})."

        pyautogui.moveTo(cx, cy, duration=0.2)
        time.sleep(0.06)
        pyautogui.doubleClick()
        self.current_screen_context = None
        return True, f"Double-clicked '{text}' on screen."

    def type_into_field(self, target: Dict[str, Any], text: str) -> Tuple[bool, str]:
        """Focuses field by clicking and types text."""
        if not target:
            return False, "Target field not found."

        cx, cy = target["center"]
        if self.test_mode:
            pyautogui.moveTo(cx, cy, duration=0.25)
            return True, f"[Test Mode] Positioned cursor at input field ({cx}, {cy}) to type '{text}'."

        pyautogui.moveTo(cx, cy, duration=0.2)
        pyautogui.click()
        time.sleep(0.15)
        # Insertion via Windows clipboard for accuracy
        try:
            import subprocess
            subprocess.run(['clip'], input=text.strip().encode('utf-16'), check=True)
            pyautogui.hotkey('ctrl', 'v')
        except Exception:
            pyautogui.write(text, interval=0.02)
        return True, f"Typed text into field at ({cx}, {cy})."

    def scroll(self, direction: str = "down", amount: int = 350) -> Tuple[bool, str]:
        """Scrolls the current window up or down."""
        scroll_val = -amount if direction.lower() in ["down", "bottom"] else amount
        pyautogui.scroll(scroll_val)
        time.sleep(0.3)
        self.current_screen_context = None
        return True, f"Scrolled {direction} by {amount} units."

    # ================================================================
    #  SCREEN DESCRIPTION
    # ================================================================

    def get_screen_description(self) -> str:
        """
        Produces a rich, concise summary of the current desktop and active window content.
        """
        ctx = self.analyze_screen(force_refresh=True)
        app = ctx.get("application", "Desktop")
        title = ctx.get("window_title", "Active Screen")
        page_type = ctx.get("page_type", "general")
        elements = ctx.get("elements", [])

        if not elements:
            return f"Currently on your screen: {app} is in the foreground with window title '{title}'. No visible text could be captured."

        # Extract semantic elements
        video_titles = [e["text"] for e in elements if e.get("semantic_type") == "video_title"]
        link_titles = [e["text"] for e in elements if e.get("semantic_type") == "link_title"]
        tabs = [e.get("semantic_details", {}).get("tab_name", e["text"]) for e in elements if e.get("semantic_type") == "tab"]
        tabs = list(dict.fromkeys(tabs))[:5]

        if page_type == "youtube":
            if video_titles:
                sample_videos = " | ".join(f"'{v}'" for v in video_titles[:3])
                desc = f"Currently on your screen: YouTube is active ({app} - '{title}'). Showing videos including: {sample_videos}."
                if tabs:
                    desc += f" Filter tabs: {', '.join(tabs[:4])}."
                return desc
            return f"Currently on your screen: YouTube is active ({app} - '{title}') with {len(elements)} elements detected."

        elif page_type == "google_search":
            if link_titles:
                sample_links = " | ".join(f"'{l}'" for l in link_titles[:3])
                desc = f"Currently on your screen: Google Search is open in {app} ('{title}'). Top search results include: {sample_links}."
                if tabs:
                    desc += f" Search tabs: {', '.join(tabs[:4])}."
                return desc
            return f"Currently on your screen: Google Search is open in {app} ('{title}')."

        # General application / desktop
        prominent_lines = [e["text"] for e in elements if len(e["text"].split()) >= 2 and not e["text"].startswith("http")]
        sample = "; ".join(prominent_lines[:4]) if prominent_lines else "standard interface elements"
        return f"Currently on your screen: {app} is in the foreground with title '{title}'. Visible items include: {sample}. Total of {len(elements)} interactive screen elements detected."

    # ================================================================
    #  CONVENIENCE API METHODS
    # ================================================================

    def find_text(self, text: str) -> Optional[Dict[str, Any]]:
        """Finds any screen element matching the given text."""
        return self.find_target(target_description=f"about {text}")

    def find_search_bar(self) -> Optional[Dict[str, Any]]:
        """Finds the search input bar on the current page."""
        return self.find_target("search bar")

    def find_tab(self, tab_name_or_index: Any = "all") -> Optional[Dict[str, Any]]:
        """Finds a navigation or filter tab (e.g. 'images', 'videos', 'music', 2)."""
        if isinstance(tab_name_or_index, int):
            return self.find_target(f"{tab_name_or_index} tab")
        return self.find_target(f"{tab_name_or_index} tab")

    def find_button(self, button_name: str) -> Optional[Dict[str, Any]]:
        """Finds a button element matching the button name."""
        return self.find_target(target_description=f"button called {button_name}")

    def find_link(self, link_description: str) -> Optional[Dict[str, Any]]:
        """Finds a link or headline matching the description."""
        return self.find_target(target_description=f"link about {link_description}")

    def find_link_description(self, target: Any = 1) -> Optional[Dict[str, Any]]:
        """Finds a link description snippet by ordinal index."""
        if isinstance(target, int):
            return self.find_target(f"description of result {target}")
        return self.find_target(f"description {target}")

    def find_result(self, target: Any = 1) -> Optional[Dict[str, Any]]:
        """Finds a search result by ordinal or description (e.g., 2, 'second result', 'result about Python')."""
        if isinstance(target, int):
            return self.find_target(target_description=f"result number {target}")
        return self.find_target(target_description=str(target))

    def find_video(self, target: Any = 1) -> Optional[Dict[str, Any]]:
        """Finds a video card by ordinal or topic (e.g., 3, 'third video')."""
        if isinstance(target, int):
            return self.find_target(target_description=f"{target} video")
        return self.find_target(target_description=str(target))

    def find_song(self, target: Any = 1) -> Optional[Dict[str, Any]]:
        """Finds a song item by ordinal or title (e.g., 2, 'second song')."""
        if isinstance(target, int):
            return self.find_target(target_description=f"{target} song")
        return self.find_target(target_description=str(target))

    def click_element(self, target: Dict[str, Any]) -> Tuple[bool, str]:
        """Alias for click_target."""
        return self.click_target(target)

    def double_click_element(self, target: Dict[str, Any]) -> Tuple[bool, str]:
        """Alias for double_click_target."""
        return self.double_click_target(target)

    def scroll_screen(self, direction: str = "down", amount: int = 350) -> Tuple[bool, str]:
        """Alias for scroll."""
        return self.scroll(direction=direction, amount=amount)

    def press_key(self, key: str) -> Tuple[bool, str]:
        """Safely presses a keyboard key."""
        try:
            pyautogui.press(key)
            return True, f"Pressed '{key}' key."
        except Exception as e:
            return False, f"Could not press '{key}': {e}"

    # ================================================================
    #  DIAGNOSTICS
    # ================================================================

    def run_diagnostics(self) -> Dict[str, Any]:
        """
        Runs a full diagnostic check and returns system info useful for debugging
        coordinate accuracy issues.
        """
        logical_w, logical_h = pyautogui.size()
        screenshot = self.capture_screen()

        diag = {
            "logical_screen": f"{logical_w}x{logical_h}",
            "screenshot_size": f"{screenshot.size[0]}x{screenshot.size[1]}" if screenshot else "N/A",
            "dpi_scale": self._compute_dpi_scale(screenshot.size) if screenshot else (1.0, 1.0),
            "dpi_scale_effective": self.dpi_scale != (1.0, 1.0),
            "winocr_available": HAS_WINOCR,
            "pytesseract_available": HAS_PYTESSERACT,
            "test_mode": self.test_mode,
            "active_window": self.get_active_window_info(),
        }

        if screenshot:
            raw_words = self._ocr_image(screenshot)
            scale = diag["dpi_scale"]
            elements = self._group_words_into_elements(raw_words, logical_w, logical_h, scale)
            diag["ocr_elements_count"] = len(elements)
            if elements:
                first = elements[0]
                diag["sample_element"] = {
                    "text": first["text"][:50],
                    "center_logical": first["center"],
                    "bbox_logical": first["bbox"]
                }
                # Show the RAW (unscaled) OCR coordinates of the first word for comparison
                if raw_words:
                    rw = raw_words[0]
                    diag["sample_raw_ocr"] = {
                        "text": rw["text"][:50],
                        "center_raw": [rw["x"] + rw["width"] // 2, rw["y"] + rw["height"] // 2],
                        "bbox_raw": [rw["x"], rw["y"], rw["x"] + rw["width"], rw["y"] + rw["height"]]
                    }

        print("\n[Screen Vision Diagnostics]")
        for k, v in diag.items():
            print(f"  {k}: {v}")
        print()

        return diag
