"""
Desktop and Screen Automation Controller for Neura AI.
Handles active window detection, in-tab typing, browser automation,
hotkeys, screenshots, and first result navigation.
"""

import os
import re
import time
import datetime
import subprocess
from typing import Optional, Tuple, Any
import pyautogui
import pygetwindow as gw
import keyboard
import ctypes
from brain.screen_vision import ScreenVision

# Disable pyautogui fail-safe pause for faster response
pyautogui.PAUSE = 0.05
pyautogui.FAILSAFE = False

class DesktopController:
    """
    Controls screen actions, active window interactions, keyboard typing,
    browser tab searching, and shortcuts.
    """
    def __init__(self, screenshots_dir: str = None):
        if not screenshots_dir:
            pictures_dir = os.path.join(os.path.expanduser("~"), "Pictures")
            self.screenshots_dir = os.path.join(pictures_dir, "Screenshots")
        else:
            self.screenshots_dir = screenshots_dir
        os.makedirs(self.screenshots_dir, exist_ok=True)
        self.screen_vision = ScreenVision()


    def get_active_window_title(self) -> str:
        """Returns the title of the current foreground window."""
        try:
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            buff = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buff, length + 1)
            title = buff.value.strip()
            if title:
                return title
        except Exception:
            pass

        try:
            win = gw.getActiveWindow()
            if win and win.title:
                return win.title.strip()
        except Exception:
            pass

        return ""

    def focus_window_by_keyword(self, keyword: str) -> bool:
        """Attempts to find and bring a window matching keyword to the foreground."""
        try:
            kw = keyword.strip().lower()
            all_wins = gw.getAllWindows()
            matching = [w for w in all_wins if kw in w.title.lower() and w.title.strip()]
            if matching:
                win = matching[0]
                try:
                    if win.isMinimized:
                        win.restore()
                    hwnd = getattr(win, '_hWnd', None)
                    if hwnd:
                        ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                        ctypes.windll.user32.SetForegroundWindow(hwnd)
                    else:
                        win.activate()
                    time.sleep(0.3)
                    return True
                except Exception:
                    try:
                        win.activate()
                        time.sleep(0.3)
                        return True
                    except Exception:
                        pass
        except Exception:
            pass
        return False

    def copy_text_to_clipboard(self, text: str):
        """Copies text to the Windows clipboard via Windows API."""
        try:
            subprocess.run(['clip'], input=text.strip().encode('utf-16'), check=True)
        except Exception:
            pass

    def type_text(self, text: str, press_enter: bool = False):
        """
        Types text into the active window at the cursor position.
        Uses clipboard paste for flawless Unicode, spacing, and punctuation.
        """
        if not text:
            return

        try:
            # Fast, accurate insertion via clipboard paste
            self.copy_text_to_clipboard(text)
            time.sleep(0.1)
            pyautogui.hotkey('ctrl', 'v')
            time.sleep(0.1)
            if press_enter:
                pyautogui.press('enter')
        except Exception:
            # Fallback to direct typewrite
            pyautogui.typewrite(text, interval=0.01)
            if press_enter:
                pyautogui.press('enter')

    def search_in_active_window(self, query: str) -> str:
        """
        Context-aware in-app search:
        - If in YouTube: presses '/' (YouTube search hotkey), enters query, and hits Enter.
        - If in Browser (Chrome/Edge/Brave/Firefox): presses Ctrl+E or Ctrl+K or '/', searches, and hits Enter.
        - If in Code editor: presses Ctrl+F, enters query.
        - Otherwise: launches search in active window or opens browser.
        """
        title = self.get_active_window_title().lower()
        print(f"[DesktopController] Active window title: '{title}'")

        # 1. YouTube Active Tab / Window
        if "youtube" in title or "you tube" in title:
            # YouTube universal search bar shortcut is '/'
            pyautogui.press('/')
            time.sleep(0.2)
            # Select all and replace if existing text
            pyautogui.hotkey('ctrl', 'a')
            time.sleep(0.1)
            self.type_text(query, press_enter=True)
            return f"Searched for '{query}' directly on YouTube."

        # 2. General Web Browser (Chrome, Edge, Firefox, Brave, Opera)
        elif any(browser in title for browser in ["chrome", "edge", "firefox", "brave", "opera"]):
            # Use Ctrl+E (Focus search engine in browser address/search bar)
            pyautogui.hotkey('ctrl', 'e')
            time.sleep(0.2)
            self.type_text(query, press_enter=True)
            return f"Searched for '{query}' in your browser tab."

        # 3. Code / Text Editor (VS Code, Notepad, Sublime)
        elif any(ed in title for ed in ["visual studio code", "code", "notepad", "sublime"]):
            pyautogui.hotkey('ctrl', 'f')
            time.sleep(0.2)
            self.type_text(query, press_enter=True)
            return f"Searched for '{query}' in your text editor."

        # 4. Default: Try to focus browser or open YouTube search
        else:
            # Check if YouTube window is open anywhere in background
            if self.focus_window_by_keyword("YouTube"):
                time.sleep(0.3)
                pyautogui.press('/')
                time.sleep(0.2)
                pyautogui.hotkey('ctrl', 'a')
                self.type_text(query, press_enter=True)
                return f"Switched to YouTube and searched for '{query}'."

            # Check if Chrome / Edge is open in background
            for b in ["Chrome", "Edge", "Firefox", "Brave"]:
                if self.focus_window_by_keyword(b):
                    time.sleep(0.3)
                    pyautogui.hotkey('ctrl', 't')  # new tab
                    time.sleep(0.2)
                    self.type_text(f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}", press_enter=True)
                    return f"Opened YouTube search for '{query}' in {b}."

            # Fallback: Open in default browser
            import webbrowser
            webbrowser.open(f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}")
            return f"Opened YouTube search for '{query}' in your browser."

    def open_nth_search_result(self, index: int = 1) -> str:
        """
        Activates or plays the nth video, link, or search result on the active screen/window.
        - Brings YouTube or browser to the foreground.
        - Distinguishes between YouTube search and Google search layouts.
        - Accurately targets the clickable title/thumbnail for the requested index.
        - Performs clean mouse hover and click without pressing Enter to prevent focus hijacking.
        """
        if index < 1:
            index = 1

        # 1. Ensure browser/YouTube/Google window is in focus
        active_title = self.get_active_window_title().lower()
        if not any(k in active_title for k in ["youtube", "google", "search", "chrome", "edge", "brave", "firefox", "opera"]):
            for kw in ["YouTube", "Google", "Search", "Chrome", "Edge", "Brave", "Firefox", "Opera"]:
                if self.focus_window_by_keyword(kw):
                    time.sleep(0.35)
                    active_title = self.get_active_window_title().lower()
                    break

        screen_w, screen_h = pyautogui.size()
        is_youtube = "youtube" in active_title
        is_google = not is_youtube and any(k in active_title for k in ["google", "search"])

        # 1. Screen Vision Dynamic Element Detection First (No Fixed Coordinates)
        try:
            target_desc = f"{index} video" if is_youtube else f"{index} link"
            target_elem = self.screen_vision.find_target(target_desc)
            if target_elem:
                success, msg = self.screen_vision.click_target(target_elem)
                if success:
                    item_type = "video" if is_youtube else "link"
                    return f"Opening {item_type} number {index} on screen, Sir."
        except Exception as e:
            print(f"[DesktopController] Screen Vision dynamic target note: {e}")

        if is_youtube:
            try:
                # Video cards are vertically stacked in the main column
                target_x = int(screen_w * 0.35)

                if index <= 3:
                    # Items 1 to 3 fit comfortably on screen without scrolling
                    target_y = int(screen_h * (0.23 + (index - 1) * 0.21))
                else:
                    # Scroll down so the target video enters the viewport
                    scroll_steps = index - 2
                    pyautogui.scroll(-320 * scroll_steps)
                    time.sleep(0.35)
                    target_y = int(screen_h * 0.50)

                # Smooth cursor glide and clean left click (NO enter key to prevent opening video #1)
                pyautogui.moveTo(target_x, target_y, duration=0.18)
                time.sleep(0.06)
                pyautogui.click()
                return f"Playing video number {index} on YouTube, Sir."
            except Exception as e:
                return f"Could not open video {index} on YouTube: {e}"

        elif is_google:
            try:
                # Google search result titles (<h3> blue links) are left-aligned
                target_x = int(screen_w * 0.20)

                if index <= 6:
                    target_y = int(screen_h * (0.24 + (index - 1) * 0.12))
                else:
                    scroll_steps = index - 5
                    pyautogui.scroll(-220 * scroll_steps)
                    time.sleep(0.35)
                    target_y = int(screen_h * 0.50)

                # Smooth cursor glide and clean left click
                pyautogui.moveTo(target_x, target_y, duration=0.18)
                time.sleep(0.06)
                pyautogui.click()
                return f"Opening search result number {index} from Google, Sir."
            except Exception as e:
                return f"Could not open Google search result {index}: {e}"

        else:
            try:
                target_x = int(screen_w * 0.25)
                if index <= 5:
                    target_y = int(screen_h * (0.25 + (index - 1) * 0.12))
                else:
                    scroll_steps = index - 4
                    pyautogui.scroll(-200 * scroll_steps)
                    time.sleep(0.35)
                    target_y = int(screen_h * 0.50)

                pyautogui.moveTo(target_x, target_y, duration=0.18)
                time.sleep(0.06)
                pyautogui.click()
                return f"Activated item number {index} on screen, Sir."
            except Exception as e:
                return f"Could not activate item {index} on screen: {e}"

    def open_first_search_result(self) -> str:
        """Attempts to click or navigate to the first video/link in the active browser tab."""
        return self.open_nth_search_result(1)

    def perform_hotkey(self, action: str) -> str:
        """Performs common desktop hotkeys and window operations."""
        action = action.strip().lower()

        if action in ["new tab", "open tab", "new_tab"]:
            pyautogui.hotkey('ctrl', 't')
            return "Opened a new tab, Sir."

        elif action in ["close tab", "close this tab", "close_tab"]:
            pyautogui.hotkey('ctrl', 'w')
            return "Closed the current tab, Sir."

        elif action in ["switch tab", "next tab", "switch_tab"]:
            pyautogui.hotkey('ctrl', 'tab')
            return "Switched to the next tab, Sir."

        elif action in ["previous tab", "last tab"]:
            pyautogui.hotkey('ctrl', 'shift', 'tab')
            return "Switched to the previous tab, Sir."

        elif action in ["scroll down", "page down", "down"]:
            pyautogui.press('pagedown')
            return "Scrolled down, Sir."

        elif action in ["scroll up", "page up", "up"]:
            pyautogui.press('pageup')
            return "Scrolled up, Sir."

        elif action in ["enter", "press enter"]:
            pyautogui.press('enter')
            return "Pressed Enter, Sir."

        elif action in ["select all", "select_all"]:
            pyautogui.hotkey('ctrl', 'a')
            return "Selected all text, Sir."

        elif action in ["copy", "copy this"]:
            pyautogui.hotkey('ctrl', 'c')
            return "Copied to clipboard, Sir."

        elif action in ["paste", "paste this"]:
            pyautogui.hotkey('ctrl', 'v')
            return "Pasted from clipboard, Sir."

        elif action in ["save", "save file", "save this"]:
            pyautogui.hotkey('ctrl', 's')
            return "Saved, Sir."

        elif action in ["undo"]:
            pyautogui.hotkey('ctrl', 'z')
            return "Undone, Sir."

        elif action in ["refresh", "reload"]:
            pyautogui.press('f5')
            return "Refreshed the page, Sir."

        elif action in ["maximize", "full screen"]:
            pyautogui.hotkey('win', 'up')
            return "Maximized window, Sir."

        elif action in ["minimize"]:
            pyautogui.hotkey('win', 'down')
            return "Minimized window, Sir."

        return f"Unknown hotkey action: {action}"

    def take_screenshot(self, filename: Optional[str] = None) -> Tuple[bool, str]:
        """Captures the full desktop screen and saves it."""
        try:
            if not filename:
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"screenshot_{timestamp}.png"

            filepath = os.path.join(self.screenshots_dir, filename)
            screenshot = pyautogui.screenshot()
            screenshot.save(filepath)
            return True, filepath
        except Exception as e:
            return False, str(e)

    # ==========================================
    # High-Level Screen Vision Actions
    # ==========================================

    def _ensure_foreground_window_for_target(self, description: str):
        """Ensures the appropriate application window is in the foreground for screen actions."""
        d = description.lower()
        if any(k in d for k in ["google", "search", "result", "video", "youtube", "song", "browser", "link", "website", "tab", "bar", "box", "description"]):
            title = self.get_active_window_title().lower()
            if not any(k in title for k in ["google", "youtube", "brave", "chrome", "edge", "firefox", "search"]):
                for kw in ["Google", "YouTube", "Brave", "Chrome", "Edge", "Firefox", "Search"]:
                    if self.focus_window_by_keyword(kw):
                        time.sleep(0.35)
                        break

    def screen_click_target(self, description: str) -> Tuple[bool, str]:
        """
        Dynamically analyzes the visible screen, locates the target element,
        and clicks its calculated center coordinates.
        """
        self._ensure_foreground_window_for_target(description)
        target = self.screen_vision.find_target(description)
        if not target:
            return False, f"Could not find '{description}' on your screen, Sir."
        return self.screen_vision.click_target(target)

    def screen_open_target(self, description: str) -> Tuple[bool, str]:
        """
        Dynamically locates a visible link, search result, or item and opens it.
        """
        self._ensure_foreground_window_for_target(description)
        target = self.screen_vision.find_target(description)
        if not target:
            return False, f"Could not find '{description}' on the screen to open, Sir."
        return self.screen_vision.click_target(target)

    def click_link(self, description_or_index: Any = 1) -> Tuple[bool, str]:
        """
        Uses DesktopController to bring the browser to foreground and click any link.
        Handles:
            - Numerical index: 1, 2, 3
            - Ordinal phrases: "first link", "second link", "3rd link"
            - Generic requests: "any link", "link on the browser", "a link"
            - Topic links: "link about Python", "link about YouTube"
        """
        # 1. Bring browser window to foreground
        self._ensure_foreground_window_for_target("browser link")

        # 2. Formulate search target
        if isinstance(description_or_index, int):
            target_desc = f"{description_or_index} link"
            idx = description_or_index
        else:
            target_desc = str(description_or_index).strip()
            # Extract ordinal if present
            ord_match = re.search(r"\b(\d+|first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th|sixth|6th|seventh|7th|eighth|8th|ninth|9th|tenth|10th)\b", target_desc.lower())
            idx = 1
            if ord_match:
                tok = ord_match.group(1).lower()
                ord_dict = {"first": 1, "1st": 1, "second": 2, "2nd": 2, "third": 3, "3rd": 3, "fourth": 4, "4th": 4, "fifth": 5, "5th": 5,
                            "sixth": 6, "6th": 6, "seventh": 7, "7th": 7, "eighth": 8, "8th": 8, "ninth": 9, "9th": 9, "tenth": 10, "10th": 10}
                idx = ord_dict.get(tok)
                if idx is None and tok.isdigit():
                    idx = int(tok)
                idx = idx or 1

        # 3. Dynamic Screen Vision detection
        try:
            target = self.screen_vision.find_target(target_desc)
            if target:
                success, msg = self.screen_vision.click_target(target)
                if success:
                    link_txt = target.get("text", "")[:50]
                    return True, f"Clicked link '{link_txt}' on your browser, Sir."
        except Exception as e:
            print(f"[DesktopController] click_link dynamic target note: {e}")

        # 4. Fallback: Calibrated viewport navigation via open_nth_search_result
        try:
            fallback_res = self.open_nth_search_result(idx)
            return True, fallback_res
        except Exception as e:
            return False, f"Could not click link on browser: {e}"

    def screen_type(self, description: str, text: str) -> Tuple[bool, str]:
        """
        Dynamically finds an on-screen input field or element and enters text.
        """
        self._ensure_foreground_window_for_target(description)
        target = self.screen_vision.find_target(description)
        if not target:
            # Fallback to typing at current cursor position
            self.type_text(text)
            return True, f"Typed '{text}' at the current cursor position, Sir."
        return self.screen_vision.type_into_field(target, text)

    def screen_scroll(self, direction: str = "down", amount: int = 350) -> Tuple[bool, str]:
        """Scrolls the active window viewport."""
        return self.screen_vision.scroll(direction=direction, amount=amount)

    def screen_describe(self) -> str:
        """Analyzes and describes what is currently visible on the screen."""
        try:
            self.screen_vision._ensure_input_desktop()
        except Exception:
            pass
        return self.screen_vision.read_and_summarize_screen(mode="describe")

    def screen_read_and_summarize(self, query: str = "", mode: str = "describe") -> str:
        """Reads OCR text from the visible screen and generates a natural summary or reading."""
        try:
            self.screen_vision._ensure_input_desktop()
        except Exception:
            pass
        return self.screen_vision.read_and_summarize_screen(query=query, mode=mode)

    def get_background_activity(self) -> str:
        """
        Inspects and summarizes active background user applications, top resource
        consumers, media playback, and overall system load.
        """
        try:
            user32 = ctypes.windll.user32
            hdesk = user32.OpenInputDesktop(0, False, 0x01FF)
            if hdesk:
                user32.SetThreadDesktop(hdesk)
        except Exception:
            pass

        fg_hwnd = None
        try:
            fg_hwnd = ctypes.windll.user32.GetForegroundWindow()
        except Exception:
            pass

        bg_windows = []
        ignored = {
            'program manager', 'windows input experience', 'default ime', 'msctfime ui',
            'dwm', 'task view', 'settings'
        }

        try:
            import win32gui
            def _enum_win_proc(hwnd, _):
                if hwnd == fg_hwnd or not win32gui.IsWindowVisible(hwnd):
                    return
                t = win32gui.GetWindowText(hwnd).strip()
                if not t or t.lower() in ignored:
                    return
                try:
                    rect = win32gui.GetWindowRect(hwnd)
                    w, h = rect[2] - rect[0], rect[3] - rect[1]
                    if w > 120 and h > 120 and t not in bg_windows:
                        bg_windows.append(t)
                except Exception:
                    if t not in bg_windows:
                        bg_windows.append(t)

            win32gui.EnumWindows(_enum_win_proc, None)
        except Exception:
            try:
                all_wins = gw.getAllWindows()
                for w in all_wins:
                    t = w.title.strip()
                    if t and t.lower() not in ignored and getattr(w, '_hWnd', None) != fg_hwnd and t not in bg_windows:
                        bg_windows.append(t)
            except Exception:
                pass

        cpu_pct = 0.0
        ram_pct = 0.0
        try:
            import psutil
            cpu_pct = psutil.cpu_percent(interval=0.1)
            ram_pct = psutil.virtual_memory().percent
        except Exception:
            pass

        media_msg = ""
        try:
            from pycaw.pycaw import AudioUtilities
            sessions = AudioUtilities.GetAllSessions()
            for s in sessions:
                if s.State == 1 and s.Process:
                    pname = s.Process.name()
                    if pname.lower() not in ["python.exe", "system"]:
                        media_msg = f"Audio playback is active from {pname}."
                        break
        except Exception:
            pass

        clean_apps = []
        for w in bg_windows:
            w_clean = w
            if len(w_clean) > 35:
                w_clean = w_clean[:32] + "..."
            clean_apps.append(f"'{w_clean}'")

        if clean_apps:
            apps_text = ", ".join(clean_apps[:4])
            more_text = f" and {len(clean_apps) - 4} more" if len(clean_apps) > 4 else ""
            desc = f"In the background, you have {len(clean_apps)} application{'s' if len(clean_apps) > 1 else ''} running: {apps_text}{more_text}. Overall system background load is {cpu_pct:.0f}% CPU and {ram_pct:.0f}% RAM."
        else:
            desc = f"In the background, there are no other user application windows open. Overall system background load is {cpu_pct:.0f}% CPU and {ram_pct:.0f}% RAM with background services running smoothly."

        if media_msg:
            desc += f" {media_msg}"

        return desc

    def get_screen_and_background_activity(self) -> str:
        """
        Produces a unified, comprehensive intelligence report of both foreground
        screen state and background activity.
        """
        try:
            self.screen_vision._ensure_input_desktop()
        except Exception:
            pass
        screen_desc = self.screen_describe()
        bg_desc = self.get_background_activity()
        return f"{screen_desc} {bg_desc}"

