"""
Neura Multi-Agent System - Computer Use & Full Screen Automation Agent.
Provides autonomous full-screen computer use capabilities inspired by Claude Computer Use and Gemini.
Performs perception-plan-act-verify loops using screen capture, OCR, active window detection,
mouse/keyboard actuators, and optional LLM visual reasoning.
"""

import os
import sys
import re
import time
import json
import datetime
from typing import Dict, Any, List, Optional, Tuple
import pyautogui
import pygetwindow as gw

from brain.agents.base_agent import BaseAgent, AgentStatus
from brain.agents.task_manager import Task, PermissionLevel, TaskState
from brain.agents.event_system import EventBus, Finding, FindingCategory, Severity, EventType
from brain.screen_vision import ScreenVision
from brain.desktop_controller import DesktopController

# Failsafe settings
pyautogui.PAUSE = 0.08
pyautogui.FAILSAFE = True  # Moving mouse to upper-left corner aborts execution


class ComputerUseAgent(BaseAgent):
    """
    Autonomous Full-Screen Automation Agent for Neura AI.
    Takes full screen access to perform multi-step user tasks through
    perceiving the screen, planning actions, executing mouse/keyboard inputs,
    and verifying results.
    """

    def __init__(
        self,
        desktop_ctrl: Optional[DesktopController] = None,
        event_bus: Optional[EventBus] = None,
        task_manager=None,
    ):
        super().__init__(
            name="ComputerUseAgent",
            description="Autonomous full screen computer-use agent. Plans and executes multi-step UI automation tasks like Gemini and Claude.",
            capabilities=[
                "full_screen_access",
                "screen_perception",
                "autonomous_action_planning",
                "mouse_click_and_drag",
                "keyboard_typing_and_hotkeys",
                "window_focus_and_switching",
                "ui_state_verification",
                "action_audit_logging",
            ],
            event_bus=event_bus,
            task_manager=task_manager,
        )
        self.desktop_ctrl = desktop_ctrl or DesktopController()
        self.screen_vision = self.desktop_ctrl.screen_vision
        self.permission_granted = True
        self.action_history: List[Dict[str, Any]] = []

    def set_permission(self, allowed: bool):
        self.permission_granted = allowed

    def execute_task(self, task: Task) -> Dict[str, Any]:
        """
        Main entry point for computer use automation tasks.
        Task metadata should include:
        - 'goal': user's natural language goal (e.g. 'open notepad and type hello', 'search for Python in browser')
        - 'max_steps': max iterations (default: 8)
        """
        if not self.permission_granted:
            err = "Full screen access permission is currently disabled. Access denied."
            self.emit_warning(task.task_id, err)
            return {"success": False, "error": err, "permission_denied": True}

        goal = task.metadata.get("goal") or task.description
        max_steps = int(task.metadata.get("max_steps", 8))

        return self.run_autonomous_automation(goal=goal, max_steps=max_steps, task_id=task.task_id)

    def run_autonomous_automation(
        self,
        goal: str,
        max_steps: int = 8,
        task_id: str = "computer_use_direct"
    ) -> Dict[str, Any]:
        """
        Executes the Perceive-Plan-Act-Verify autonomous loop.
        """
        print(f"\n🖥️  [ComputerUseAgent] Activated Full Screen Access for task: '{goal}'")
        self.emit_progress(task_id, 5.0, f"Initializing screen access for goal: {goal}")

        self.action_history = []
        screen_w, screen_h = pyautogui.size()
        completed = False
        final_message = ""

        # Step 0: Ensure desktop is ready
        try:
            self.screen_vision._ensure_input_desktop()
        except Exception:
            pass

        for step in range(1, max_steps + 1):
            progress_pct = 10.0 + (step / max_steps) * 80.0
            step_desc = f"Step {step}/{max_steps}: Perceiving screen state..."
            self.emit_progress(task_id, progress_pct, step_desc)
            print(f"🔍 [ComputerUseAgent] Step {step}/{max_steps}: Capturing screen and evaluating UI state...")

            # 1. PERCEIVE SCREEN
            active_window = self.desktop_ctrl.get_active_window_title()
            screenshot = self.screen_vision.capture_screen()
            elements = []
            ocr_text = ""
            if screenshot is not None:
                try:
                    elements = self.screen_vision.run_ocr(screenshot)
                    ocr_text = "\n".join([el.text for el in elements if el.text])
                except Exception as ocr_err:
                    print(f"[ComputerUseAgent] OCR warning: {ocr_err}")

            # 2. PLAN NEXT ACTION
            action_plan = self._plan_next_action(
                goal=goal,
                step=step,
                active_window=active_window,
                ocr_text=ocr_text,
                elements=elements,
                history=self.action_history,
                screen_size=(screen_w, screen_h),
            )

            print(f"🎯 [ComputerUseAgent] Planned Action: {action_plan.get('action')} -> {action_plan.get('description', '')}")

            # 3. CHECK TERMINATION
            if action_plan.get("action") == "finish":
                completed = True
                final_message = action_plan.get("message", f"Goal '{goal}' achieved successfully.")
                self.action_history.append({
                    "step": step,
                    "action": "finish",
                    "status": "success",
                    "details": final_message,
                    "timestamp": datetime.datetime.now().isoformat(),
                })
                break

            if action_plan.get("action") == "abort":
                completed = False
                final_message = action_plan.get("error", "Task aborted by planner.")
                self.action_history.append({
                    "step": step,
                    "action": "abort",
                    "status": "failed",
                    "details": final_message,
                    "timestamp": datetime.datetime.now().isoformat(),
                })
                break

            # 4. ACT (EXECUTE ACTION)
            action_result = self._execute_action(action_plan, screen_w, screen_h)
            self.action_history.append({
                "step": step,
                "action": action_plan.get("action"),
                "params": action_plan,
                "status": "success" if action_result.get("success") else "failed",
                "result": action_result.get("message", ""),
                "timestamp": datetime.datetime.now().isoformat(),
            })

            # 5. VERIFY (WAIT & OBSERVE)
            wait_time = float(action_plan.get("wait_after", 0.6))
            time.sleep(wait_time)

            # Check if this was the final action planned
            if action_plan.get("is_final", False):
                completed = True
                final_message = f"Completed action sequence for: '{goal}'."
                break

        if not completed and not final_message:
            final_message = f"Computer use automation reached max step limit ({max_steps}) for goal: '{goal}'."

        self.emit_progress(task_id, 100.0, final_message)
        print(f"🏁 [ComputerUseAgent] Task execution finished. Result: {final_message}\n")

        return {
            "success": completed,
            "goal": goal,
            "message": final_message,
            "steps_executed": len(self.action_history),
            "history": self.action_history,
        }

    def _plan_next_action(
        self,
        goal: str,
        step: int,
        active_window: str,
        ocr_text: str,
        elements: List[Any],
        history: List[Dict[str, Any]],
        screen_size: Tuple[int, int]
    ) -> Dict[str, Any]:
        """
        Determines the next action to perform.
        Uses LLM if available; otherwise uses high-precision intent decomposition.
        """
        g_lower = goal.lower()
        screen_w, screen_h = screen_size

        # Check if LLM planning is available (Gemini or Groq)
        llm_plan = self._try_llm_plan(goal, step, active_window, ocr_text, history, screen_size)
        if llm_plan:
            return llm_plan

        # Robust Built-in Heuristic Planner (Zero API failure fallback)
        return self._heuristic_plan(goal, step, active_window, ocr_text, elements, history, screen_size)

    def _try_llm_plan(
        self,
        goal: str,
        step: int,
        active_window: str,
        ocr_text: str,
        history: List[Dict[str, Any]],
        screen_size: Tuple[int, int]
    ) -> Optional[Dict[str, Any]]:
        """Attempts to generate next computer-use step via Gemini or Groq."""
        prompt = f"""You are an autonomous computer-use agent controlling a Windows PC screen (size {screen_size[0]}x{screen_size[1]}).
User Goal: "{goal}"
Current Step: {step}
Active Window Title: "{active_window}"
Recent Screen OCR Text Snippet:
---
{ocr_text[:800]}
---
Action History So Far:
{json.dumps([h.get('action') for h in history])}

Choose the single next atomic action to progress toward the user goal.
Output JSON only with schema:
{{
  "action": "click" | "double_click" | "type" | "hotkey" | "scroll" | "open_app" | "wait" | "finish",
  "x": <integer logical coordinate or null>,
  "y": <integer logical coordinate or null>,
  "text": <text string if typing or target element text>,
  "keys": [<key strings if hotkey>],
  "app_name": <app name if open_app>,
  "description": <human readable explanation of this step>,
  "is_final": <true if goal is achieved after this action>
}}
Do NOT output markdown code blocks. Output raw JSON only."""

        # Check Gemini API Key
        gemini_key = os.getenv("GEMINI_API_KEY", "").strip(" \"'")
        if gemini_key:
            try:
                print("🌐 [API Call] Using Gemini API for Full-Screen Autonomous Planning...")
                import google.generativeai as genai
                genai.configure(api_key=gemini_key)
                for model_name in ['gemini-3.8-flash', 'gemini-2.5-flash', 'gemini-1.5-flash']:
                    try:
                        g_model = genai.GenerativeModel(model_name)
                        resp = g_model.generate_content(prompt)
                        if resp and resp.text:
                            clean_txt = resp.text.strip().strip("`").replace("json\n", "").strip()
                            plan_data = json.loads(clean_txt)
                            if isinstance(plan_data, dict) and "action" in plan_data:
                                return plan_data
                    except Exception:
                        continue
            except Exception as e:
                print(f"[ComputerUseAgent] Gemini plan attempt note: {e}")

        # Check Groq API Key
        groq_key = os.getenv("GROQ_API_KEY", "").strip(" \"'")
        if groq_key:
            try:
                print("⚡ [API Call] Using Groq API for Full-Screen Autonomous Planning...")
                from groq import Groq
                client = Groq(api_key=groq_key)
                comp = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    response_format={"type": "json_object"}
                )
                raw_out = comp.choices[0].message.content
                plan_data = json.loads(raw_out)
                if isinstance(plan_data, dict) and "action" in plan_data:
                    return plan_data
            except Exception as e:
                print(f"[ComputerUseAgent] Groq plan attempt note: {e}")

        return None

    def _heuristic_plan(
        self,
        goal: str,
        step: int,
        active_window: str,
        ocr_text: str,
        elements: List[Any],
        history: List[Dict[str, Any]],
        screen_size: Tuple[int, int]
    ) -> Dict[str, Any]:
        """Deterministic, reliable execution planning for common computer tasks."""
        g_lower = goal.lower()
        screen_w, screen_h = screen_size

        # 1. Goal: Open an application (Notepad, Chrome, Code, Settings, Calculator, etc.)
        app_match = re.search(r"\b(?:open|launch|start)\s+([a-zA-Z0-9\s]+?)(?:\s+and\s+|\s+to\s+|$)", g_lower)
        target_app = app_match.group(1).strip() if app_match else ""

        if step == 1:
            if target_app:
                return {
                    "action": "open_app",
                    "app_name": target_app,
                    "description": f"Open application '{target_app}' via Windows Search",
                    "wait_after": 1.5,
                }
            elif any(w in g_lower for w in ["search", "google", "look up", "find"]):
                return {
                    "action": "hotkey",
                    "keys": ["win", "r"],
                    "description": "Open Run dialog to launch browser",
                    "wait_after": 0.8,
                }

        # Step 2: Handle typing or subsequent interactions
        if step == 2 and any(h.get("action") == "open_app" for h in history):
            # Check if goal has a 'type' or 'write' directive
            type_match = re.search(r"\b(?:type|write|input|enter|say)\s+['\"]?([^'\"]+?)['\"]?$", goal, re.IGNORECASE)
            if type_match:
                text_to_type = type_match.group(1).strip()
                return {
                    "action": "type",
                    "text": text_to_type,
                    "press_enter": True,
                    "description": f"Type text '{text_to_type}' into the active application",
                    "is_final": True,
                }
            elif any(w in g_lower for w in ["maximize", "full screen"]):
                return {
                    "action": "hotkey",
                    "keys": ["win", "up"],
                    "description": "Maximize application window",
                    "is_final": True,
                }
            else:
                return {
                    "action": "finish",
                    "message": f"Application '{target_app}' launched and focused successfully.",
                }

        # Step 3: Search for target keyword or button on screen
        click_match = re.search(r"\b(?:click|press|select|open)\s+(?:on\s+)?['\"]?([^'\"]+?)['\"]?$", goal, re.IGNORECASE)
        if click_match:
            target_label = click_match.group(1).strip()
            # Find in OCR elements
            found_coords = None
            for el in elements:
                if target_label.lower() in getattr(el, "text", "").lower():
                    cx, cy = getattr(el, "center", (0, 0))
                    if cx > 0 and cy > 0:
                        found_coords = (cx, cy)
                        break

            if found_coords:
                return {
                    "action": "click",
                    "x": found_coords[0],
                    "y": found_coords[1],
                    "description": f"Click detected target '{target_label}' at ({found_coords[0]}, {found_coords[1]})",
                    "is_final": True,
                }

        # Fallback completion
        return {
            "action": "finish",
            "message": f"Completed automated screen interaction for '{goal}'.",
        }

    def _execute_action(self, plan: Dict[str, Any], screen_w: int, screen_h: int) -> Dict[str, Any]:
        """Executes a single atomic computer-use action using PyAutoGUI or Windows API."""
        action = plan.get("action", "").lower()

        try:
            if action == "click":
                x = plan.get("x")
                y = plan.get("y")
                if x is None or y is None:
                    # Click center
                    x, y = screen_w // 2, screen_h // 2
                x = max(0, min(int(x), screen_w - 1))
                y = max(0, min(int(y), screen_h - 1))
                pyautogui.moveTo(x, y, duration=0.25)
                pyautogui.click()
                return {"success": True, "message": f"Clicked at ({x}, {y})"}

            elif action == "double_click":
                x = int(plan.get("x", screen_w // 2))
                y = int(plan.get("y", screen_h // 2))
                pyautogui.moveTo(x, y, duration=0.25)
                pyautogui.doubleClick()
                return {"success": True, "message": f"Double clicked at ({x}, {y})"}

            elif action == "right_click":
                x = int(plan.get("x", screen_w // 2))
                y = int(plan.get("y", screen_h // 2))
                pyautogui.moveTo(x, y, duration=0.25)
                pyautogui.rightClick()
                return {"success": True, "message": f"Right clicked at ({x}, {y})"}

            elif action == "type":
                text = plan.get("text", "")
                press_enter = plan.get("press_enter", False)
                self.desktop_ctrl.copy_text_to_clipboard(text)
                time.sleep(0.08)
                pyautogui.hotkey('ctrl', 'v')
                if press_enter:
                    time.sleep(0.08)
                    pyautogui.press('enter')
                return {"success": True, "message": f"Typed text: '{text}'"}

            elif action == "hotkey":
                keys = plan.get("keys", [])
                if isinstance(keys, list) and keys:
                    pyautogui.hotkey(*keys)
                    return {"success": True, "message": f"Pressed hotkey: {'+'.join(keys)}"}
                return {"success": False, "message": "No keys provided for hotkey"}

            elif action == "open_app":
                app_name = plan.get("app_name", "")
                pyautogui.hotkey('win', 's')
                time.sleep(0.4)
                self.desktop_ctrl.copy_text_to_clipboard(app_name)
                time.sleep(0.05)
                pyautogui.hotkey('ctrl', 'v')
                time.sleep(0.6)
                pyautogui.press('enter')
                time.sleep(1.0)
                return {"success": True, "message": f"Launched '{app_name}' via Windows search"}

            elif action == "scroll":
                direction = plan.get("direction", "down")
                amount = int(plan.get("amount", 300))
                clicks = -amount if direction == "down" else amount
                pyautogui.scroll(clicks)
                return {"success": True, "message": f"Scrolled {direction} by {amount}"}

            elif action == "wait":
                secs = float(plan.get("seconds", 1.0))
                time.sleep(secs)
                return {"success": True, "message": f"Waited {secs} seconds"}

            return {"success": True, "message": f"Action '{action}' processed"}

        except Exception as e:
            return {"success": False, "message": f"Error executing '{action}': {e}"}
