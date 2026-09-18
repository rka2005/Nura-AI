"""
Desktop and Screen Automation Controller for Neura AI.
Handles active window detection, in-tab typing, browser automation,
hotkeys, screenshots, and first result navigation.
"""

import os
import time
import datetime
import subprocess
from typing import Optional, Tuple
import pyautogui
import pygetwindow as gw
import keyboard
import ctypes

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
            windows = gw.getWindowsWithTitle(keyword)
            if windows:
                win = windows[0]
                try:
                    if win.isMinimized:
                        win.restore()
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

    def open_first_search_result(self) -> str:
        """
        Attempts to click or navigate to the first video/link in the active browser tab.
        In YouTube: navigates down to the first video and presses Enter.
        """
        title = self.get_active_window_title().lower()
        if "youtube" in title:
            # In YouTube search results, Tab moves to filters then videos; pressing Tab 4 times or Down arrow
            pyautogui.press('tab')
            time.sleep(0.1)
            pyautogui.press('tab')
            time.sleep(0.1)
            pyautogui.press('enter')
            return "Opened the first video on YouTube, Sir."
        else:
            # In general web page: Tab + Enter or down
            pyautogui.press('tab')
            time.sleep(0.1)
            pyautogui.press('enter')
            return "Activated the top link in the current tab, Sir."

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
