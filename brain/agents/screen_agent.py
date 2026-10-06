"""
Neura Multi-Agent System - Screen Agent.
Performs permission-controlled visual perception, active window inspection,
terminal and UI error detection, and targeted screen interaction.
"""

import os
import re
from typing import Dict, Any, List, Optional, Tuple
from brain.agents.base_agent import BaseAgent, AgentStatus
from brain.agents.task_manager import Task, PermissionLevel, TaskState
from brain.agents.event_system import (
    Finding,
    FindingCategory,
    Severity,
    EventType,
)
from brain.screen_vision import ScreenVision
from brain.desktop_controller import DesktopController

class ScreenAgent(BaseAgent):
    """
    Screen Agent provides visual perception and interaction only when permitted.
    Inspects active foreground applications, extracts visible text via OCR,
    and detects visible terminal/compiler exceptions.
    """
    def __init__(self, desktop_ctrl: Optional[DesktopController] = None, event_bus=None, task_manager=None):
        super().__init__(
            name="ScreenAgent",
            description="Perceives authorized screen state, active windows, OCR text, and visible terminal or application errors.",
            capabilities=[
                "screen_capture",
                "active_window_detection",
                "ocr_text_extraction",
                "error_pattern_detection",
                "ui_element_localization",
                "authorized_interaction",
            ],
            event_bus=event_bus,
            task_manager=task_manager,
        )
        self.desktop_ctrl = desktop_ctrl or DesktopController()
        self.screen_vision = self.desktop_ctrl.screen_vision
        self.permission_granted = True  # Can be checked/updated from Neura's SCREEN_ACCESS_ALLOWED

    def set_permission(self, allowed: bool):
        self.permission_granted = allowed

    def execute_task(self, task: Task) -> Dict[str, Any]:
        """
        Executes a screen-related task:
        - 'screen_inspect' / 'describe_screen': captures and describes visible screen
        - 'detect_errors' / 'terminal_errors': inspects screen for exceptions, tracebacks, error codes
        - 'active_window': detects active application
        - 'interact': clicks or targets element with user consent
        """
        if not self.permission_granted:
            err_msg = "Screen perception permission is disabled. Access denied."
            self.emit_warning(task.task_id, err_msg)
            return {
                "success": False,
                "error": err_msg,
                "permission_denied": True,
            }

        task_type = task.task_type.lower()
        self.emit_progress(task.task_id, 20.0, "Identifying foreground application and active window...")

        active_title = self.desktop_ctrl.get_active_window_title()

        if task_type in ["detect_errors", "terminal_errors", "screen_errors", "error_inspect"]:
            self.emit_progress(task.task_id, 50.0, "Performing OCR scan and error pattern matching on screen...")
            findings, visible_text = self.inspect_visible_errors(task.task_id)
            for f in findings:
                self.emit_finding(task.task_id, f)

            return {
                "success": True,
                "active_window": active_title,
                "findings": [f.to_dict() for f in findings],
                "visible_text_snippet": visible_text[:400],
            }

        elif task_type in ["active_window", "window_inspect"]:
            return {
                "success": True,
                "active_window": active_title,
            }

        elif task_type in ["interact", "click"]:
            target = task.metadata.get("target", "")
            action = task.metadata.get("action", "click")
            if not target:
                return {"success": False, "error": "No target specified for screen interaction."}
            
            self.emit_progress(task.task_id, 50.0, f"Locating target '{target}' on screen...")
            found, el_type, (cx, cy) = self.screen_vision.find_target(target)
            if found:
                import pyautogui
                pyautogui.click(cx, cy)
                msg = f"Successfully interacted with '{target}' ({el_type}) at coordinates ({cx}, {cy})."
                return {"success": True, "message": msg, "target": target, "coords": (cx, cy)}
            else:
                msg = f"Could not find target '{target}' on the visible screen."
                return {"success": False, "message": msg, "target": target}

        else:
            # Default: describe screen
            self.emit_progress(task.task_id, 60.0, "Analyzing visible screen layout and elements...")
            desc = self.desktop_ctrl.screen_describe()
            return {
                "success": True,
                "active_window": active_title,
                "description": desc,
            }

    def inspect_visible_errors(self, task_id: str) -> Tuple[List[Finding], str]:
        """
        Captures the screen and scans OCR output for standard developer error signatures:
        Traceback, Exception, Error, ModuleNotFoundError, 404, 500, SyntaxError.
        """
        findings: List[Finding] = []
        screen_text = ""

        try:
            # Capture screen via existing ScreenVision pipeline
            screenshot = self.screen_vision.capture_screen()
            if screenshot is None:
                return findings, ""

            # Run OCR
            elements = self.screen_vision.run_ocr(screenshot)
            extracted_lines = [el.text for el in elements if el.text]
            screen_text = "\n".join(extracted_lines)

            # Check for error patterns
            error_patterns = [
                (r"(Traceback\s+\(most recent call last\):.*)", "Python Traceback Exception", Severity.CRITICAL, FindingCategory.BUG),
                (r"(\w+Error:\s+[^\n]+)", "Runtime Error Detected", Severity.HIGH, FindingCategory.BUG),
                (r"(\w+Exception:\s+[^\n]+)", "Exception Raised", Severity.HIGH, FindingCategory.BUG),
                (r"(ModuleNotFoundError:\s+No module named\s+['\"][^'\"]+['\"])", "Missing Python Module", Severity.HIGH, FindingCategory.BUG),
                (r"(SyntaxError:\s+[^\n]+)", "Visible Syntax Error", Severity.CRITICAL, FindingCategory.BUG),
                (r"(Cannot GET\s+[^\n]+|404\s+Not Found)", "HTTP 404 Missing Endpoint", Severity.MEDIUM, FindingCategory.BUG),
                (r"(500\s+Internal Server Error)", "HTTP 500 Server Error", Severity.HIGH, FindingCategory.BUG),
                (r"(Failed to compile|Build failed)", "Compilation / Build Failure", Severity.HIGH, FindingCategory.BUG),
            ]

            for regex, title, severity, category in error_patterns:
                matches = re.findall(regex, screen_text, flags=re.IGNORECASE)
                if matches:
                    snippet = matches[0]
                    if isinstance(snippet, tuple):
                        snippet = snippet[0]
                    snippet_clean = snippet.strip()[:200]

                    findings.append(
                        Finding(
                            category=category,
                            severity=severity,
                            title=title,
                            description=f"Visible error on screen: {snippet_clean}",
                            suggestion="Inspect the active terminal or editor window and address the reported exception.",
                        )
                    )

        except Exception as e:
            self.emit_warning(task_id, f"Error inspecting screen for visible errors: {e}")

        return findings, screen_text
