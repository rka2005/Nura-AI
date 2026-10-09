import sys
import pyttsx3
import speech_recognition as sr
import datetime

# Sarvam AI voice integration
import asyncio
import base64
import tempfile
import pygame
import websockets

import wikipedia
import webbrowser
import os
import pywhatkit
import pygetwindow as gw
import cv2
import google.generativeai as genai
from dotenv import load_dotenv
from groq import Groq
import screen_brightness_control as sbc
from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
import re
import threading
import time
import keyboard
import pyautogui
import requests
import json
import pyjokes
import psutil
from art import text2art
from typing import Any, Dict, List, Optional, Tuple

from memory.memory_manager import MemoryManager
from brain.conversation import generate_ai_response
from brain.personality import IDENTITY, get_personality_prompt
from brain.intent_router import route_intent, IntentType
from brain.desktop_controller import DesktopController
from brain.file_manager import FileManager
from vision.face_recognition import (
    get_face_system,
    recognize_owner_from_camera,
    clean_extracted_name,
    is_refusal_response
)

CHAT_BRIDGE_FILE = "chat_bridge.json"
INPUT_BRIDGE_FILE = "input_bridge.json"
STATUS_BRIDGE_FILE = "status_bridge.json"
AUTO_LEARN_BRIDGE_FILE = "auto_learn_bridge.json"
load_dotenv()
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

model = None
if os.getenv("GEMINI_API_KEY"):
    try:
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        for g_name in ['gemini-3.8-flash', 'gemini-2.5-flash', 'gemini-1.5-flash', 'gemini-1.5-pro']:
            try:
                model = genai.GenerativeModel(g_name)
                break
            except Exception:
                continue
    except Exception as e:
        print(f"[Neura] Gemini model setup note: {e}")

# 3-Tier Memory Manager
memory_mgr = MemoryManager()
memory = memory_mgr.user_memory  # Reference for backward compatibility

# Desktop Automation & File CRUD Controllers
SCREEN_ACCESS_ALLOWED = memory_mgr.get_preference("screen_access_allowed", True)
BACKGROUND_WORK_ALLOWED = memory_mgr.get_preference("background_work_allowed", True)
desktop_ctrl = DesktopController()
file_mgr = FileManager()

# Multi-Agent Subsystem Orchestrator
from brain.agents import get_orchestrator, Task, TaskState, PermissionLevel
agent_orchestrator = get_orchestrator()

# Configure Wikipedia User-Agent to comply with Wikimedia API policy
try:
    wikipedia.set_user_agent("NeuraAI/1.0 (DesktopAssistant; Windows; contact: neura@ai.local)")
except Exception as e:
    print(f"[Wikipedia User-Agent config note]: {e}")

def send_to_frontend(role, message):
    payload = {
        "time": datetime.datetime.now().strftime("%H:%M:%S"),
        "role": role,
        "message": message
    }

    for attempt in range(5):
        try:
            if os.path.exists(CHAT_BRIDGE_FILE):
                with open(CHAT_BRIDGE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
            else:
                data = []

            data.append(payload)

            temp_bridge_file = f"{CHAT_BRIDGE_FILE}.tmp"
            with open(temp_bridge_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_bridge_file, CHAT_BRIDGE_FILE)
            break
        except (OSError, PermissionError) as e:
            if attempt < 4:
                time.sleep(0.04)
            else:
                print("Chat bridge error:", e)
        except Exception as e:
            print("Chat bridge error:", e)
            break

def set_status_bridge_field(key: str, value: Any):
    """Safely updates a key in status_bridge.json without disrupting other fields."""
    try:
        data = {}
        if os.path.exists(STATUS_BRIDGE_FILE):
            try:
                with open(STATUS_BRIDGE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}
        data[key] = value
        temp_bridge = f"{STATUS_BRIDGE_FILE}.tmp"
        with open(temp_bridge, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_bridge, STATUS_BRIDGE_FILE)
    except Exception:
        pass

def load_memory():
    """Load or initialize memory structure via MemoryManager."""
    memory_mgr.load_all()
    return memory_mgr.user_memory

def save_memory(mem=None):
    """Write memory dict to disk."""
    memory_mgr.save_user_memory()

def llm_history_to_pairs():
    return memory_mgr.get_recent_history_pairs()

def append_llm_history(role, content):
    # Appended automatically via append_turn in MemoryManager
    pass

def remember_interaction(user_input, neura_response):
    memory_mgr.append_turn(user_input, neura_response)
    memory_mgr.log_activity(f"Interaction: {user_input[:40]}")

def update_preference(key, value):
    memory_mgr.set_preference(key, value)

def log_activity(action):
    memory_mgr.log_activity(action)

def recall_preference(key, default=None):
    return memory_mgr.get_preference(key, default)

def analyze_memory_on_start():
    """Run light analysis on startup and show memory summary."""
    prefs = memory_mgr.user_memory.get("preferences", {})
    facts = memory_mgr.user_memory.get("user_facts", {})
    recent = memory_mgr.conv_memory.get("recent_messages", [])
    summary = memory_mgr.conv_memory.get("summary", "")

    print("🧠 [Neura Memory System Loaded]")
    if prefs:
        print("🔁 Loaded preferences:")
        for k, v in prefs.items():
            print(f"  - {k}: {v}")
    if facts:
        print("👤 Loaded user facts:")
        for k, v in facts.items():
            if v:
                print(f"  - {k}: {v}")
    if summary:
        print(f"📝 Previous conversation summary: {summary[:80]}...")
    print(f"💬 Active conversation window turns: {len(recent) // 2}")

# Sarvam AI voice generation

async def _generate_sarvam_audio(text):
    """Generate speech using Sarvam AI's WebSocket TTS API."""

    api_key = os.getenv("SARVAM_API_KEY")
    if not api_key:
        raise RuntimeError("SARVAM_API_KEY is missing from .env")

    uri = (
        "wss://api.sarvam.ai/text-to-speech/ws"
        "?model=bulbul:v4-flash&send_completion_event=true"
    )

    audio_chunks = []

    async with websockets.connect(
        uri,
        additional_headers={
            "Api-Subscription-Key": api_key
        },
        open_timeout=20,
        close_timeout=10,
    ) as ws:

        await ws.send(json.dumps({
            "type": "config",
            "data": {
                "model": "bulbul:v4-flash",
                "target_language_code": "en-IN",
                "speaker": "ishita_enhi_companion",
                "pace": 1,
                "speech_sample_rate": "24000",
            },
        }))

        await ws.send(json.dumps({
            "type": "text",
            "data": {"text": text},
        }))

        await ws.send(json.dumps({"type": "flush"}))

        async for raw in ws:
            message = json.loads(raw)
            message_type = message.get("type")

            if message_type == "audio":
                encoded_audio = message.get(
                    "data", {}
                ).get("audio")

                if encoded_audio:
                    audio_chunks.append(
                        base64.b64decode(encoded_audio)
                    )

            elif message_type == "error":
                raise RuntimeError(
                    message.get("data", {}).get(
                        "message", str(message)
                    )
                )

            elif message_type == "event":
                if message.get("data", {}).get(
                    "event_type"
                ) == "final":
                    break

    if not audio_chunks:
        raise RuntimeError("Sarvam returned no audio data.")

    return b"".join(audio_chunks)


def _play_sarvam_audio(audio_bytes):
    """Play the generated MP3 audio on Windows."""

    audio_path = None

    try:
        with tempfile.NamedTemporaryFile(
            suffix=".mp3",
            delete=False,
        ) as audio_file:
            audio_path = audio_file.name
            audio_file.write(audio_bytes)

        if not pygame.mixer.get_init():
            pygame.mixer.init()

        pygame.mixer.music.load(audio_path)
        pygame.mixer.music.play()

        while pygame.mixer.music.get_busy():
            time.sleep(0.05)

    finally:
        try:
            if pygame.mixer.get_init():
                pygame.mixer.music.stop()
                pygame.mixer.music.unload()
                pygame.mixer.quit()
        except Exception:
            pass

        if audio_path and os.path.exists(audio_path):
            try:
                os.remove(audio_path)
            except OSError:
                pass

def speak(audio):
    """Speak through Sarvam AI, falling back to Windows TTS."""

    if audio is None:
        return

    text = str(audio).strip()
    if not text:
        return

    # Preserve Neura's existing frontend chat integration.
    send_to_frontend("neura", text)

    # Prefer Sarvam AI voice.
    try:
        print("[Neura Voice] Generating Sarvam speech...", flush=True)

        audio_bytes = asyncio.run(
            _generate_sarvam_audio(text)
        )

        _play_sarvam_audio(audio_bytes)

        print("[Neura Voice] Speech completed.", flush=True)
        return

    except Exception as exc:
        print(
            f"[Sarvam TTS Error] {type(exc).__name__}: {exc}",
            flush=True,
        )
        print(
            "[Neura Voice] Falling back to Windows speech.",
            flush=True,
        )

    # Fallback: your original local TTS.
    engine = None

    try:
        engine = pyttsx3.init("sapi5")
        voices = engine.getProperty("voices")

        if len(voices) > 1:
            engine.setProperty("voice", voices[1].id)

        engine.setProperty("rate", 180)
        engine.setProperty("volume", 1.0)

        engine.say(text)
        engine.runAndWait()

    except Exception as exc:
        print(f"[Windows TTS Error] {exc}", flush=True)

    finally:
        if engine is not None:
            try:
                engine.stop()
            except Exception:
                pass


def wishMe():
    speak('Hello Sir!')

def wishtime():
    hour = datetime.datetime.now().hour
    if 0 <= hour < 12:
        speak("Good Morning!")
    elif 12 <= hour < 18:
        speak("Good Afternoon!")
    elif 18 <= hour < 20:
        speak("Good Evening!")
    else:
        speak("Good Night!")
    speak("I am Neura. Please tell, how may I help you?")

def chat_with_ai(prompt, chat_history_pairs=None):
    """
    Invokes Neura's brain conversation orchestrator combining
    fixed personality, user memory, and temporary conversation context.
    """
    reply = generate_ai_response(prompt, memory_mgr)
    return reply, memory_mgr.get_recent_history_pairs()

def safe_search_lookup(search_query):
    """
    Safely searches Wikipedia with a custom User-Agent and comprehensive exception handling.
    Catches all JSONDecodeError, RequestException, and DisambiguationError.
    If Wikipedia fails or is ambiguous, automatically opens Google Search without crashing.
    """
    clean_query = search_query.strip()
    if not clean_query:
        speak("What would you like me to look up, Sir?")
        return "No search query provided."

    try:
        wikipedia.set_user_agent("NeuraAI/1.0 (DesktopAssistant; Windows; contact: neura@ai.local)")
        speak(f"Looking up {clean_query}...")
        results = wikipedia.summary(clean_query, sentences=2)
        if results and "may refer to" not in results.lower():
            print(f"Wikipedia: {results}")
            speak(f"According to Wikipedia: {results}")
            remember_interaction(search_query, results)
            log_activity(f"Wikipedia search: {clean_query}")
            return results
    except Exception as e:
        print(f"[Wikipedia note: {e} -> Opening Google Search...]")

    # Fallback to Google Search
    try:
        search_url = "https://www.google.com/search?q=" + clean_query.replace(" ", "+")
        webbrowser.open(search_url)
        msg = f"Here are the Google search results for {clean_query}, Sir."
        speak(msg)
        remember_interaction(search_query, f"Opened Google search for {clean_query}")
        log_activity(f"Google search: {clean_query}")
        return msg
    except Exception as e:
        msg = f"Sorry Sir, I could not complete the search: {e}"
        speak(msg)
        return msg

def execute_desktop_or_file_intent(intent, metadata, raw_query: str = ""):
    """
    Executes screen, desktop, or file CRUD actions deterministically without API calls.
    Returns (handled: bool, response_message: str).
    """
    global SCREEN_ACCESS_ALLOWED, BACKGROUND_WORK_ALLOWED

    rq = raw_query.lower()

    # Handle explicit permission requests
    if intent == IntentType.SYSTEM_PERMISSION:
        action = metadata.get("action", "grant")
        if action == "revoke" or any(p in rq for p in ["stop screen access", "disable screen access", "revoke screen access", "revoke background", "disable background"]):
            SCREEN_ACCESS_ALLOWED = False
            BACKGROUND_WORK_ALLOWED = False
            try:
                update_preference("screen_access_allowed", False)
                update_preference("background_work_allowed", False)
            except Exception:
                pass
            return True, "Screen access and background work permissions have been revoked, Sir."
        else:
            SCREEN_ACCESS_ALLOWED = True
            BACKGROUND_WORK_ALLOWED = True
            try:
                update_preference("screen_access_allowed", True)
                update_preference("background_work_allowed", True)
            except Exception:
                pass
            return True, "Screen access and background work permissions have been granted, Sir."

    # If action was accompanied by permission grant metadata, guarantee permissions are saved
    if metadata.get("permission_granted"):
        SCREEN_ACCESS_ALLOWED = True
        BACKGROUND_WORK_ALLOWED = True
        try:
            update_preference("screen_access_allowed", True)
            update_preference("background_work_allowed", True)
        except Exception:
            pass

    # Automatically ensure screen access and background execution are active
    if not SCREEN_ACCESS_ALLOWED:
        SCREEN_ACCESS_ALLOWED = True
        try:
            update_preference("screen_access_allowed", True)
            update_preference("background_work_allowed", True)
        except Exception:
            pass

    if intent == IntentType.DESKTOP_SEARCH_IN_TAB:
        q = metadata.get("query", "")
        res = desktop_ctrl.search_in_active_window(q)
        return True, res

    elif intent == IntentType.SYSTEM_FOLDER_OPEN:
        folder_name = metadata.get("folder", "")
        location = metadata.get("location", "")
        return True, open_folder_from_location(folder_name, location)

    elif intent == IntentType.SYSTEM_FILE_OPEN:
        file_name = metadata.get("file", "")
        location = metadata.get("location")
        return True, open_file_from_system(file_name, location)

    elif intent == IntentType.DESKTOP_FIRST_LINK:
        idx = metadata.get("index", 1)
        success, res = desktop_ctrl.click_link(idx)
        return True, res

    elif intent == IntentType.DESKTOP_TYPE:
        text = metadata.get("text", "")
        desktop_ctrl.type_text(text)
        return True, f"Typed text for you, Sir."

    elif intent == IntentType.DESKTOP_HOTKEY:
        action = metadata.get("action", "")
        res = desktop_ctrl.perform_hotkey(action)
        return True, res

    elif intent == IntentType.DESKTOP_SCREENSHOT:
        success, path_or_err = desktop_ctrl.take_screenshot()
        if success:
            return True, f"Screenshot captured and saved, Sir."
        return True, f"Could not capture screenshot: {path_or_err}"

    elif intent == IntentType.FILE_CREATE:
        ftype = metadata.get("type", "file")
        fpath = metadata.get("path", "")
        if ftype == "folder":
            success, msg = file_mgr.create_folder(fpath)
        else:
            content = metadata.get("content", "")
            success, msg = file_mgr.create_file(fpath, content)
        return True, msg

    elif intent == IntentType.FILE_READ:
        fpath = metadata.get("path", "")
        success, msg = file_mgr.read_file(fpath)
        return True, msg

    elif intent == IntentType.FILE_UPDATE:
        fpath = metadata.get("path", "")
        content = metadata.get("content", "")
        success, msg = file_mgr.append_to_file(fpath, content)
        return True, msg

    elif intent == IntentType.FILE_DELETE:
        ftype = metadata.get("type", "file")
        fpath = metadata.get("path", "")
        if ftype == "folder":
            success, msg = file_mgr.delete_folder(fpath)
        else:
            success, msg = file_mgr.delete_file(fpath)
        return True, msg

    elif intent == IntentType.FILE_LIST:
        fpath = metadata.get("path", "")
        success, msg = file_mgr.list_files(fpath)
        return True, msg

    return False, ""

def execute_screen_vision_intent(intent, metadata, raw_query: str = ""):
    """
    Executes Screen Vision capabilities:
    - SCREEN_DESCRIBE: Screen content inspection and verbal summary
    - SYSTEM_SCREEN_AND_BACKGROUND_STATUS: Comprehensive dual foreground & background intelligence
    - SYSTEM_BACKGROUND_STATUS: Background applications, tasks, and system resource inspection
    - SCREEN_CLICK: Dynamic element targeting and click action
    - SCREEN_OPEN: Dynamic link, result, or video opening
    - SCREEN_PLAY: Dynamic song/video playback from screen
    - SCREEN_SCROLL: Scroll viewport or compound scroll and open
    - SCREEN_TYPE: Typing into detected on-screen fields
    Returns (handled: bool, response_message: str).
    """
    global SCREEN_ACCESS_ALLOWED, BACKGROUND_WORK_ALLOWED

    perm_prefix = ""
    if metadata.get("permission_granted"):
        SCREEN_ACCESS_ALLOWED = True
        BACKGROUND_WORK_ALLOWED = True
        try:
            update_preference("screen_access_allowed", True)
            update_preference("background_work_allowed", True)
        except Exception:
            pass
        perm_prefix = "Screen access and background work permissions have been granted, Sir. "

    if intent == IntentType.SCREEN_DESCRIBE:
        mode = metadata.get("mode", "describe")
        query_text = metadata.get("query", raw_query)
        summary = desktop_ctrl.screen_read_and_summarize(query=query_text, mode=mode)
        return True, f"{perm_prefix}{summary}"

    elif intent == IntentType.SYSTEM_SCREEN_AND_BACKGROUND_STATUS:
        summary = desktop_ctrl.get_screen_and_background_activity()
        return True, f"{perm_prefix}{summary}"

    elif intent == IntentType.SYSTEM_BACKGROUND_STATUS:
        summary = desktop_ctrl.get_background_activity()
        return True, f"{perm_prefix}{summary}"

    elif intent == IntentType.SCREEN_CLICK:
        target = metadata.get("target", "")
        if "link" in target.lower():
            success, msg = desktop_ctrl.click_link(target)
        else:
            success, msg = desktop_ctrl.screen_click_target(target)
        return True, f"{perm_prefix}{msg}"

    elif intent == IntentType.SCREEN_OPEN:
        target = metadata.get("target", "")
        if "link" in target.lower():
            success, msg = desktop_ctrl.click_link(target)
        else:
            success, msg = desktop_ctrl.screen_open_target(target)
        return True, f"{perm_prefix}{msg}"

    elif intent == IntentType.SCREEN_PLAY:
        target = metadata.get("target", "")
        success, msg = desktop_ctrl.screen_open_target(target)
        return True, f"{perm_prefix}{msg}"

    elif intent == IntentType.SCREEN_SCROLL:
        direction = metadata.get("direction", "down")
        desktop_ctrl.screen_scroll(direction)
        then_act = metadata.get("then_action")
        then_tgt = metadata.get("then_target")
        if then_act and then_tgt:
            time.sleep(0.4)
            success, msg = desktop_ctrl.screen_open_target(then_tgt)
            return True, f"{perm_prefix}Scrolled {direction}. {msg}"
        return True, f"{perm_prefix}Scrolled {direction} on screen, Sir."

    elif intent == IntentType.SCREEN_TYPE:
        target = metadata.get("target", "")
        text = metadata.get("text", "")
        success, msg = desktop_ctrl.screen_type(target, text)
        return True, f"{perm_prefix}{msg}"

    elif intent == IntentType.SCREEN_INTERACT:
        target = metadata.get("target", "")
        success, msg = desktop_ctrl.screen_click_target(target)
        return True, f"{perm_prefix}{msg}"

    return False, ""

def execute_youtube_play_intent(intent, metadata):
    """Open YouTube and start the requested search result."""
    if intent != IntentType.SYSTEM_YOUTUBE_PLAY:
        return False, ""

    song = metadata.get("song", "").strip()
    if not song:
        return True, "Please tell me what you would like me to play on YouTube."

    try:
        pywhatkit.playonyt(song)
        update_preference("last_played_song", song)
        remember_interaction(f"open youtube and play {song}", f"Played {song} on YouTube")
        log_activity(f"Played on YouTube: {song}")
        return True, f"Opening YouTube and playing {song}."
    except Exception as e:
        print(f"YouTube compound play error: {e}")
        return True, f"I could not play {song} on YouTube: {e}"

def execute_youtube_search_intent(intent, metadata):
    """Open YouTube search results in default browser."""
    if intent != IntentType.SYSTEM_YOUTUBE_SEARCH:
        return False, ""

    search_query = metadata.get("query", "").strip()
    if not search_query:
        return True, "Please tell me what you would like to search on YouTube."

    try:
        import urllib.parse
        encoded_query = urllib.parse.quote_plus(search_query)
        search_url = f"https://www.youtube.com/results?search_query={encoded_query}"
        webbrowser.open(search_url)
        msg = f"Opening YouTube and searching for {search_query}."
        remember_interaction(f"search youtube for {search_query}", msg)
        log_activity(f"YouTube search: {search_query}")
        return True, msg
    except Exception as e:
        print(f"YouTube search error: {e}")
        return True, f"I encountered an error trying to search YouTube: {e}"

def execute_alert_intent(intent, metadata, raw_query: str = ""):
    """
    Executes Alert, Alarm, and Reminder commands:
    - SYSTEM_ALERT_SET: Schedules new alert/alarm with relative offset calculation.
    - SYSTEM_ALERT_LIST: Returns overview of pending alerts.
    - SYSTEM_ALERT_CANCEL: Cancels alerts matching criteria or all alerts.
    - SYSTEM_ALERT_STOP: Silences ringing alarms.
    - SYSTEM_REMINDER: Backwards-compatible alias for reminders.
    """
    valid_intents = [
        getattr(IntentType, "SYSTEM_ALERT_SET", "SYSTEM_ALERT_SET"),
        getattr(IntentType, "SYSTEM_ALERT_LIST", "SYSTEM_ALERT_LIST"),
        getattr(IntentType, "SYSTEM_ALERT_CANCEL", "SYSTEM_ALERT_CANCEL"),
        getattr(IntentType, "SYSTEM_ALERT_STOP", "SYSTEM_ALERT_STOP"),
        getattr(IntentType, "SYSTEM_REMINDER", "SYSTEM_REMINDER"),
    ]
    if intent not in valid_intents:
        return False, ""

    from brain.alert_service import get_alert_service, parse_alert_request
    service = get_alert_service(voice_speaker_fn=speak)

    if intent == getattr(IntentType, "SYSTEM_ALERT_STOP", "SYSTEM_ALERT_STOP"):
        service.stop_ringing()
        return True, "Alarm has been silenced, Sir."

    if intent == getattr(IntentType, "SYSTEM_ALERT_LIST", "SYSTEM_ALERT_LIST"):
        summary = service.format_active_alerts_summary()
        return True, summary

    if intent == getattr(IntentType, "SYSTEM_ALERT_CANCEL", "SYSTEM_ALERT_CANCEL"):
        target_label = metadata.get("label", "all")
        count, msg = service.cancel_alerts(target_label)
        return True, msg

    # SYSTEM_ALERT_SET or SYSTEM_REMINDER
    if metadata.get("success") and metadata.get("delay_seconds"):
        delay = float(metadata["delay_seconds"])
        label = metadata.get("label", "Alarm")
        target_dt = metadata.get("target_time")
        explanation = metadata.get("explanation", "")
        trigger_speech = metadata.get("trigger_speech")

        service.schedule_alert(
            label=label,
            delay_seconds=delay,
            target_time=target_dt,
            explanation=explanation,
            source_query=raw_query,
            trigger_speech=trigger_speech
        )

        from brain.alert_service import format_duration_friendly
        clean_lbl = label
        for p in ["that i have", "i have", "there is", "we have"]:
            if clean_lbl.lower().startswith(p):
                clean_lbl = clean_lbl[len(p):].strip()
        clean_lbl = re.sub(r"^(?:an?|the|your|my)\s+", "", clean_lbl, flags=re.IGNORECASE).strip()
        clean_lbl = re.sub(r"\s*\(in\s+[^)]+\)", "", clean_lbl).strip()

        if clean_lbl.lower() not in ["alarm", "timer", "scheduled task", "alert me"]:
            resp = f"Sure Sir! I am setting an alert for {format_duration_friendly(delay)} from now for your {clean_lbl.lower()}. I will remind you when it's time."
        else:
            resp = f"Sure Sir! I am setting an alert for {format_duration_friendly(delay)} from now. I will notify you when it's time."
        return True, resp
    else:
        # Fallback parsing in case metadata was empty or came from generic SYSTEM_REMINDER
        data = parse_alert_request(raw_query)
        if data.get("action") == "list":
            return True, service.format_active_alerts_summary()
        elif data.get("action") == "cancel":
            count, msg = service.cancel_alerts(data.get("label", "all"))
            return True, msg
        elif data.get("action") == "stop":
            service.stop_ringing()
            return True, "Alarm has been silenced, Sir."
        elif data.get("success") and data.get("delay_seconds"):
            delay = float(data["delay_seconds"])
            label = data.get("label", "Alarm")
            target_dt = data.get("target_time")
            explanation = data.get("explanation", "")
            trigger_speech = data.get("trigger_speech")

            service.schedule_alert(
                label=label,
                delay_seconds=delay,
                target_time=target_dt,
                explanation=explanation,
                source_query=raw_query,
                trigger_speech=trigger_speech
            )
            from brain.alert_service import format_duration_friendly
            clean_lbl = label
            for p in ["that i have", "i have", "there is", "we have"]:
                if clean_lbl.lower().startswith(p):
                    clean_lbl = clean_lbl[len(p):].strip()
            clean_lbl = re.sub(r"^(?:an?|the|your|my)\s+", "", clean_lbl, flags=re.IGNORECASE).strip()
            clean_lbl = re.sub(r"\s*\(in\s+[^)]+\)", "", clean_lbl).strip()

            if clean_lbl.lower() not in ["alarm", "timer", "scheduled task", "alert me"]:
                resp = f"Sure Sir! I am setting an alert for {format_duration_friendly(delay)} from now for your {clean_lbl.lower()}. I will remind you when it's time."
            else:
                resp = f"Sure Sir! I am setting an alert for {format_duration_friendly(delay)} from now. I will notify you when it's time."
            return True, resp
        elif data.get("error"):
            return True, f"Sir, I could not set that alert: {data['error']}"
        else:
            return True, "Sir, please tell me after how many minutes or at what time you would like me to set the alert."

def classify_terminal_permission_reply(reply: str) -> Optional[bool]:
    """
    Classifies user reply for terminal permission into:
    - True ('yes'): user allows terminal access (e.g. 'yes', 'yes access the terminal', 'ok, access the terminal', 'allow')
    - False ('no'): user denies terminal access (e.g. 'no', 'don't access the terminal', 'deny', 'without terminal')
    - None: unnecessary or ambiguous answer requiring clarification.
    """
    if not reply:
        return None
    r = reply.strip().lower().replace(",", " ").replace(".", " ")
    r = " ".join(r.split())

    # 1. Negative / Denial indicators (checked first to prevent false positive on compound phrases like "no access")
    no_indicators = [
        "no", "nope", "nah", "deny", "disallow", "cancel", "skip", "negative", "reject"
    ]
    is_negation = (
        r in no_indicators
        or any(r.startswith(p) for p in ["no ", "nope ", "deny ", "don't ", "dont ", "do not "])
        or any(p in r for p in [
            "no access", "deny access", "don't access", "dont access", "do not access",
            "without terminal", "no terminal", "deny permission", "don't allow", "dont allow",
            "do not allow", "access denied", "not granted", "not allowed", "skip terminal"
        ])
    )
    if is_negation:
        return False

    # 2. Affirmative / Granting indicators
    is_affirmative = (
        r in ["yes", "yeah", "yep", "yup", "sure", "allow", "grant", "ok", "okay", "proceed"]
        or any(r.startswith(p) for p in ["yes ", "yeah ", "yep ", "sure ", "allow ", "grant ", "ok ", "okay "])
        or any(p in r for p in [
            "access the terminal", "access terminal", "use terminal", "allow terminal",
            "grant terminal", "give terminal", "terminal access", "terminal permission",
            "allow access", "grant access", "proceed with terminal", "run in terminal",
            "yes access", "ok access", "okay access", "sure access"
        ])
        or (any(w in r for w in ["ok", "okay", "sure", "yes", "allow"]) and "terminal" in r)
    )
    if is_affirmative:
        return True

    return None


def prompt_user_for_terminal_permission(target_desc: str, timeout: float = 10.0, max_retries: int = 3) -> bool:
    """
    Prompts user via voice and chat bridge for terminal access permission.
    Waits 10 seconds per attempt for user reply (voice or text).
    If an unnecessary/ambiguous answer is received, asks user again up to 3 times:
      "Terminal access is granted or not? Say 'yes' to allow access or say 'no' to deny the access."
    If no reply is received after 3 attempts, defaults to 'no' (False) and proceeds.
    """
    import sys
    is_test_env = (
        "unittest" in sys.modules
        or os.environ.get("NEURA_TEST_MODE") == "1"
    )

    for attempt in range(1, max_retries + 1):
        if attempt == 1:
            spoken_prompt = (
                f"To test and debug {target_desc}, I need terminal access. "
                f"Terminal access is granted or not? Say 'yes' to allow access or say 'no' to deny the access."
            )
            frontend_card = (
                f"⚠️ **Terminal Access Permission Required (Attempt 1 of {max_retries})**\n\n"
                f"To execute dynamic tests and terminal debugging on **{target_desc}**, Neura needs terminal access.\n\n"
                f"* **Grant Access**: Type or speak `yes`, `allow`, `grant`, or `ok, access the terminal`\n"
                f"* **Deny / Safe Test**: Type or speak `no`, `deny`, or `don't access the terminal`\n\n"
                f"*(Waiting 10 seconds for your reply...)*"
            )
        else:
            spoken_prompt = (
                "Terminal access is granted or not? Say 'yes' to allow access or say 'no' to deny the access."
            )
            frontend_card = (
                f"⚠️ **Terminal Permission Clarification (Attempt {attempt} of {max_retries})**\n\n"
                f"Terminal access is granted or not?\n"
                f"* Say or type **'yes'** to allow access\n"
                f"* Say or type **'no'** to deny the access\n\n"
                f"*(Waiting 10 seconds for your reply...)*"
            )

        print(f"\n[Terminal Permission] Prompting user (Attempt {attempt}/{max_retries}): {spoken_prompt}")
        send_to_frontend("neura", frontend_card)
        speak(spoken_prompt)

        # In unit tests, check input bridge right away
        if is_test_env:
            quick_cmd = check_input_bridge()
            if quick_cmd:
                decision = classify_terminal_permission_reply(quick_cmd)
                if decision is True:
                    return True
                elif decision is False:
                    return False
            elif timeout <= 1.0:
                # Fast fallback for automated test runs without inputs
                return False

        # Active listening for this attempt (10 seconds)
        result_holder = {"raw_reply": None, "decision": None}
        stop_event = threading.Event()

        def _voice_listener():
            try:
                r = sr.Recognizer()
                try:
                    mic_src = sr.Microphone(device_index=1)
                except Exception:
                    mic_src = sr.Microphone()
                with mic_src as source:
                    r.adjust_for_ambient_noise(source, duration=0.25)
                    while not stop_event.is_set():
                        try:
                            audio = r.listen(source, timeout=1.5, phrase_time_limit=4.0)
                            query = r.recognize_google(audio, language='en-in').lower().strip()
                            print(f"[Terminal Permission] Voice captured: '{query}'")
                            send_to_frontend("user", query)
                            decision = classify_terminal_permission_reply(query)
                            result_holder["raw_reply"] = query
                            result_holder["decision"] = decision
                            return
                        except (sr.WaitTimeoutError, sr.UnknownValueError, sr.RequestError):
                            continue
            except Exception as e:
                print(f"[Terminal Permission] Voice listener error: {e}")

        listener_thread = threading.Thread(target=_voice_listener, daemon=True)
        listener_thread.start()

        start_time = time.time()
        while (time.time() - start_time) < timeout:
            # 1. Check chat GUI input bridge (every 100ms)
            bridge_cmd = check_input_bridge()
            if bridge_cmd:
                norm = bridge_cmd.lower().strip()
                print(f"[Terminal Permission] Chat input captured: '{norm}'")
                decision = classify_terminal_permission_reply(norm)
                result_holder["raw_reply"] = norm
                result_holder["decision"] = decision
                stop_event.set()
                break

            # 2. Check voice listener result
            if result_holder["raw_reply"] is not None:
                stop_event.set()
                break

            time.sleep(0.1)

        stop_event.set()

        decision = result_holder["decision"]
        raw = result_holder["raw_reply"]

        if decision is True:
            confirm_msg = "Terminal access granted. Proceeding with terminal testing, Sir."
            print(f"[Terminal Permission] Decision: YES (reply: '{raw}')")
            send_to_frontend("neura", "✅ **Terminal Permission: GRANTED**. Accessing terminal to run dynamic tests and debugging.")
            speak(confirm_msg)
            return True
        elif decision is False:
            deny_msg = "Terminal access denied. Proceeding with general static testing, Sir."
            print(f"[Terminal Permission] Decision: NO (reply: '{raw}')")
            send_to_frontend("neura", "ℹ️ **Terminal Permission: NOT GRANTED**. Performing general static testing.")
            speak(deny_msg)
            return False
        else:
            if raw:
                print(f"[Terminal Permission] Unnecessary/unrecognized answer: '{raw}'. Requesting clarification (attempt {attempt}/{max_retries}).")
            else:
                print(f"[Terminal Permission] No reply received within {timeout}s (attempt {attempt}/{max_retries}).")

    # If all 3 attempts exhausted without valid response:
    fallback_msg = "No reply received after 3 attempts. Setting terminal permission to 'no' and proceeding with general test, Sir."
    print(f"[Terminal Permission] All {max_retries} attempts exhausted without reply. Defaulting to 'no'.")
    send_to_frontend("neura", "⚠️ **No response received after 3 attempts.** Setting terminal permission to **'no'** and proceeding with general static testing.")
    speak(fallback_msg)
    return False

def execute_agent_intent(intent, metadata, raw_query: str = ""):
    """
    Executes specialized agent workflows via the AgentOrchestrator:
    - AGENT_PROJECT_TEST: Inspects project structure, dependencies, AST, and runs test suites.
    - AGENT_PROJECT_DIAGNOSTIC: Multi-agent failure diagnostic (Project + Screen + Monitor).
    - AGENT_MONITOR_START: Initiates non-blocking background surveillance of tasks/processes.
    - AGENT_MONITOR_STOP: Stops active monitoring sessions.
    - AGENT_STATUS: Reports active task lifecycles and agent states ("What are you doing?").
    - AGENT_SKILL_LEARN: Learns, validates, and registers reusable automation skills.
    - AGENT_SKILL_RUN: Executes a learned skill safely.
    - AGENT_SCREEN_INSPECT: Inspects screen for terminal tracebacks and compiler errors.
    Returns (handled: bool, response_message: str).
    """
    global SCREEN_ACCESS_ALLOWED, BACKGROUND_WORK_ALLOWED
    orch = get_orchestrator()
    orch.screen_agent.set_permission(SCREEN_ACCESS_ALLOWED)
    orch.assign_agents_for_intent(intent, metadata, raw_query)

    if intent == IntentType.AGENT_PROJECT_TEST:
        target_type = metadata.get("target_type", "project")
        target_name = metadata.get("target_name")
        from_screen = metadata.get("from_screen", False)
        perm_granted = metadata.get("terminal_permission_granted")

        target_file = None
        target_ws = orch.workspace
        target_desc = "current project"

        # 1. Screen-based Target Resolution
        if from_screen or target_type == "screen":
            screen_info = desktop_ctrl.detect_target_from_screen()
            sc_proj = screen_info.get("project_name")
            sc_file = screen_info.get("file_name")

            if target_type == "file" or (target_name and target_name.endswith(('.py', '.js', '.ts', '.html', '.css', '.json'))):
                target_file = target_name or sc_file
                target_desc = f"file '{target_file}'"
            elif sc_file and target_name in ["current_file", "this file"]:
                target_file = sc_file
                target_desc = f"active file '{sc_file}'"
            elif sc_proj:
                target_desc = f"project '{sc_proj}' on your screen"
                parent_dir = os.path.dirname(orch.workspace)
                if os.path.basename(orch.workspace).lower() == sc_proj.lower():
                    target_ws = orch.workspace
                elif os.path.exists(os.path.join(orch.workspace, sc_proj)):
                    target_ws = os.path.join(orch.workspace, sc_proj)
                elif os.path.exists(os.path.join(parent_dir, sc_proj)):
                    target_ws = os.path.join(parent_dir, sc_proj)
            else:
                target_desc = f"current project '{os.path.basename(target_ws)}'"

        # 2. File-based Target Resolution
        elif target_type == "file" and target_name:
            target_file = target_name
            target_desc = f"file '{target_name}'"

        # 3. Named Project Target Resolution (e.g. "whatsapp bot project")
        elif target_type == "named_project" and target_name:
            norm_name = re.sub(r'[^a-zA-Z0-9]', '', target_name.lower())
            found_folder = None
            try:
                for item in os.listdir(orch.workspace):
                    full_item = os.path.join(orch.workspace, item)
                    if os.path.isdir(full_item):
                        if norm_name in re.sub(r'[^a-zA-Z0-9]', '', item.lower()):
                            found_folder = full_item
                            break
            except Exception:
                pass

            if found_folder:
                target_ws = found_folder
                target_desc = f"project '{os.path.basename(found_folder)}'"
            else:
                target_desc = f"project '{target_name}'"

        else:
            target_desc = f"project '{os.path.basename(target_ws)}'"

        # 4. Terminal Permission Gating (Voice / Text confirmation)
        if perm_granted is True:
            terminal_allowed = True
            speak(f"Terminal permission recognized. Accessing terminal to test and debug {target_desc}, Sir.")
        elif perm_granted is False:
            terminal_allowed = False
            speak(f"Terminal access disabled. Performing general static analysis on {target_desc}, Sir.")
        else:
            terminal_allowed = prompt_user_for_terminal_permission(target_desc)

        # 5. Execute Project / File Testing via Orchestrator
        if target_file:
            msg = orch.test_project(
                workspace=target_ws,
                target_file=target_file,
                terminal_allowed=terminal_allowed,
                target_name=target_desc,
                from_screen=from_screen
            )
        else:
            msg = orch.test_project(
                workspace=target_ws,
                terminal_allowed=terminal_allowed,
                target_name=target_desc,
                from_screen=from_screen
            )

        # 6. Push Full Markdown Report to Frontend Chat
        if hasattr(orch, "last_test_result") and orch.last_test_result:
            full_report = orch.last_test_result.get("full_report")
            if full_report:
                send_to_frontend("neura", full_report)

        orch.release_agents(grace_period=3.5)
        return True, msg

    elif intent == IntentType.AGENT_PROJECT_DIAGNOSTIC:
        msg = orch.investigate_project_failure()
        return True, msg

    elif intent == IntentType.AGENT_MONITOR_START:
        task_name = metadata.get("name", "Background Task")
        msg = orch.start_monitoring(name=task_name)
        return True, msg

    elif intent == IntentType.AGENT_MONITOR_STOP:
        msg = orch.stop_monitoring()
        return True, msg

    elif intent == IntentType.AGENT_STATUS:
        msg = orch.get_status_overview()
        return True, msg

    elif intent == IntentType.AGENT_SKILL_LEARN:
        skill_name = metadata.get("name", "learned_workflow")
        perm_granted = metadata.get("permission_granted", False)
        msg = orch.learn_workflow(name=skill_name, permission_granted=perm_granted)
        return True, msg

    elif intent == IntentType.AGENT_SKILL_RUN:
        skill_name = metadata.get("name", "")
        res = orch.skill_agent.run_skill(skill_name, "user_request")
        msg = res.get("message") or res.get("error", "Skill execution completed.")
        return True, msg

    elif intent == IntentType.AGENT_SCREEN_INSPECT:
        findings, text = orch.screen_agent.inspect_visible_errors("user_request")
        if findings:
            err_items = [f"• [{f.severity.value}] {f.title}: {f.description}" for f in findings]
            msg = f"I scanned your screen and detected {len(findings)} visible error(s):\n" + "\n".join(err_items)
        else:
            msg = "I inspected your visible screen and found no active compiler or terminal exception tracebacks."
        return True, msg

    elif intent == IntentType.AGENT_OFFICE_SHOW:
        set_status_bridge_field("show_agent_office", True)
        if hasattr(orch, "get_agents_status_dict"):
            set_status_bridge_field("agents", orch.get_agents_status_dict())
        return True, "Opening the Agent Workspace, Sir. You can see all agents and their operations."

    elif intent == IntentType.AGENT_OFFICE_CLOSE:
        set_status_bridge_field("show_agent_office", False)
        return True, "Closing the Agent Workspace and returning to the main HUD, Sir."

    elif intent == IntentType.AGENT_COMPUTER_USE:
        goal = metadata.get("goal") or raw_query
        speak("Taking full screen access to perform the automation task, Sir.")
        msg = orch.execute_computer_use(goal=goal)
        return True, msg

    elif intent == IntentType.AGENT_VULNERABILITY_SCAN:
        speak("Starting automated security and vulnerability scan on your project, Sir.")
        res = orch.audit_and_generate_report(voice_speaker_fn=None)
        return True, res.get("summary", "Vulnerability scan completed.")

    elif intent == IntentType.AGENT_ERROR_AUDIT:
        speak("Auditing project error logs and diagnostic tracebacks, Sir.")
        report = orch.audit_system_errors()
        stats = report.get("stats", {})
        msg = (
            f"Log audit completed. Analyzed {stats.get('log_files_scanned', 0)} log files and "
            f"identified {stats.get('total_errors', 0)} exception entries with causes and handling suggestions."
        )
        return True, msg

    elif intent == IntentType.AGENT_FULL_AUDIT_REPORT:
        speak("Commencing security vulnerability scan and error audit. Generating your Word document report...")
        force_email = metadata.get("force_email", False)
        res = orch.audit_and_generate_report(voice_speaker_fn=None, force_email=force_email)
        return True, res.get("summary", "Complete audit finished and report generated.")

    elif intent == IntentType.MEMORY_REMEMBER:
        note_body = metadata.get("note") or raw_query
        orch.memory_agent.record_task_success(
            command=raw_query,
            task_name="store_explicit_memory",
            result_summary=f"Stored explicit user note: {note_body}",
            details={"explicit_note": note_body}
        )
        return True, f"I have committed that to my fixed memory, Sir: '{note_body}'."

    elif intent == IntentType.MEMORY_CONTEXT_QUERY:
        ans = orch.memory_agent.answer_from_context_memory(raw_query)
        if ans:
            return True, ans
        return True, "I checked my dual-tier context memory, Sir, but didn't find specific matching details."

    return False, ""

def ask_neura(user_message):
    """
    Handles conversational queries, memory retrieval, web lookup, and selective LLM fallback.
    Avoids API calls whenever queries can be answered by memory, smalltalk, or Google search.
    """
    user_message_clean = user_message.strip()
    if not user_message_clean:
        return ""

    orch = get_orchestrator()
    orch.memory_agent.record_incoming_command_parallel(user_message_clean)

    um_lower = user_message_clean.lower()

    # Visual Biometric Face Identity Verification ("who am i")
    if any(p in um_lower for p in ["who am i", "who i am", "tell me who i am", "do you know who i am", "do you know who am i"]):
        return identify_user_by_face()

    # Check Desktop Automation or File CRUD first (Zero API Call)
    intent, metadata = route_intent(user_message_clean)
    orch.assign_agents_for_intent(intent, metadata, user_message_clean)

    # Check Alert / Alarm Subsystem
    handled, res = execute_alert_intent(intent, metadata, user_message_clean)
    if handled:
        orch.release_agents(grace_period=3.5)
        speak(res)
        remember_interaction(user_message_clean, res)
        log_activity(f"Alert {intent}: {res[:40]}")
        return res

    # Check Audibility & Microphone/Speaker Hardware Check (Zero API Call)
    handled, res = execute_audibility_check_intent(intent, metadata, user_message_clean)
    if handled:
        orch.release_agents(grace_period=3.5)
        speak(res)
        remember_interaction(user_message_clean, res)
        orch.memory_agent.record_task_success(user_message_clean, str(intent), res)
        log_activity(f"Audibility Check {intent}: {res[:40]}")
        return res

    # Multi-Agent Orchestration Check
    handled, res = execute_agent_intent(intent, metadata, user_message_clean)
    if handled:
        orch.release_agents(grace_period=3.5)
        speak(res)
        remember_interaction(user_message_clean, res)
        log_activity(f"Agent {intent}: {res[:40]}")
        return res

    handled, res = execute_screen_vision_intent(intent, metadata, user_message_clean)
    if handled:
        speak(res)
        remember_interaction(user_message_clean, res)
        log_activity(f"Screen Vision {intent}: {res[:40]}")
        return res
    handled, res = execute_system_diagnostic_intent(intent)
    if handled:
        speak(res)
        remember_interaction(user_message_clean, res)
        log_activity(f"Diagnostic {intent}: {res[:40]}")
        return res
    handled, res = execute_youtube_play_intent(intent, metadata)
    if handled:
        speak(res)
        return res
    handled, res = execute_youtube_search_intent(intent, metadata)
    if handled:
        speak(res)
        return res
    handled, res = execute_desktop_or_file_intent(intent, metadata, user_message_clean)
    if handled:
        speak(res)
        remember_interaction(user_message_clean, res)
        log_activity(f"Action {intent}: {res[:40]}")
        return res

    um_lower = user_message_clean.lower()

    # 0. Direct Dual-Tier Context Memory Agent Retrieval (Zero API Call)
    orch = get_orchestrator()
    ctx_reply = orch.memory_agent.answer_from_context_memory(user_message_clean)
    if ctx_reply:
        speak(ctx_reply)
        remember_interaction(user_message_clean, ctx_reply)
        log_activity(f"Answered from context memory: {user_message_clean[:40]}")
        return ctx_reply

    # 1. Direct Memory Retrieval (Zero API Call)
    mem_reply = memory_mgr.answer_from_memory(user_message_clean)
    if mem_reply:
        speak(mem_reply)
        remember_interaction(user_message_clean, mem_reply)
        log_activity(f"Answered from memory: {user_message_clean[:40]}")
        return mem_reply

    # 2. Instant Fixed Identity & Conversational Status (Zero API Call)
    user_name = memory_mgr.user_memory.get("user_facts", {}).get("name")
    honorific = user_name if user_name else "Sir"

    if any(phrase in um_lower for phrase in [
        "it's very nice", "its very nice", "very nice", "ohh it's very nice", "oh it's very nice",
        "that's very nice", "thats very nice", "that's nice", "thats nice", "so nice", "looks nice",
        "it is very nice", "that is very nice", "that is nice", "this is very nice", "this is nice",
        "you are doing well", "you're doing well", "doing well", "good job", "great job", "well done",
        "awesome", "that's awesome", "thats awesome", "cool", "that's cool", "thats cool", "wonderful",
        "amazing", "perfect", "sounds good", "nice work", "superb", "brilliant", "love it", "great work"
    ]):
        response = f"Thank you, {honorific}! I'm glad you think so. I am always happy to assist you."
    elif any(um_lower == w for w in ["ok", "okay", "alright", "all right", "got it", "understood", "sure", "fine", "cool", "great", "perfect"]):
        response = f"Understood, {honorific}! Let me know whenever you need anything."
    elif any(phrase in um_lower for phrase in ["how are you", "how do you do"]):
        response = "I am doing well, Sir. How can I assist you today?"
    elif any(greet in um_lower.split() for greet in ["hello", "hi", "hey"]):
        response = "Hello Sir! It's good to hear from you."
    elif any(phrase in um_lower for phrase in ["what are you doing", "what r u doing", "what are you doing now"]):
        response = "I am standing by and monitoring your system, Sir. How can I help you?"
    elif "who are you" in um_lower or "your name" in um_lower:
        response = f"I am {IDENTITY['name']}, your personal AI assistant and desktop companion."
    elif any(phrase in um_lower for phrase in [
        "what can you do", "what can you perform", "what all can you do", "what are your capabilities",
        "what tasks can you perform", "what are your features", "tell me what you can do",
        "tell me what you can perform", "tell me your capabilities", "what can be done by you",
        "what can you do for me", "what are your functions", "what do you perform"
    ]):
        response = (
            "Sir, I can perform the following functions:\n"
            "• Screen Vision & Perception: Inspect and summarize your active screen, read text via OCR, click buttons, and open links.\n"
            "• System Diagnostics: Check real-time CPU, RAM, disk usage, battery status, and test internet speed.\n"
            "• Desktop Automation: Open and close desktop applications, manage files and folders, adjust volume and screen brightness.\n"
            "• Media & YouTube: Search YouTube, play videos or songs, and provide mood-based music recommendations.\n"
            "• Personal Assistance: Set alarms and reminders, write notes, store explicit facts, and remember your preferences.\n"
            "• Multi-Agent Systems: Run background surveillance, code syntax diagnostics, and autonomous skill learning."
        )
    elif "rohit adak" in um_lower:
        response = "He is my creator! A brilliant mind who brought me to life. I am honored to assist him."
    elif "who is your god" in um_lower:
        response = "Rohit Kumar Adak is my creator. He brought me to life."
    elif "thank you" in um_lower or "thanks" in um_lower:
        response = "You're welcome, Sir!"
    elif "time" in um_lower:
        current_time = datetime.datetime.now().strftime("%H:%M:%S")
        response = f"The time is {current_time}"
    else:
        # 3. Check automatic preference and mood learning
        learned = memory_mgr.auto_learn(user_message_clean)

        if learned and "mood" in learned:
            mood = learned["mood"]
            last_song = memory_mgr.get_preference("last_played_song")
            song_offer = f"like '{last_song}'" if last_song else "on YouTube"

            if mood in ["bored", "boring"]:
                response = f"I'm sorry to hear that you're feeling bored, {honorific}! Would you like me to play some music {song_offer}, tell you a joke, or search for something fun on YouTube?"
            elif mood in ["tired", "exhausted", "sleepy"]:
                response = f"You've been working hard, {honorific}. Would you like me to play some relaxing music, dim the screen brightness, or let you rest?"
            elif mood in ["sad", "unhappy", "lonely"]:
                response = f"I'm right here with you, {honorific}. Would you like to hear a funny joke or listen to some uplifting music to cheer you up?"
            else:
                response = f"I hear you, {honorific}. What can I do to help you feel better — maybe some music or a quick joke?"

        elif learned and "response_style" in learned:
            style = learned["response_style"]
            response = f"Got it, {honorific}. I have set my response style to {style}."
        elif learned and "song_preferences" in learned:
            response = f"Got it, {honorific} — I've noted that you like {learned['song_preferences']} music."
        elif learned and "profession" in learned:
            response = f"Noted, {honorific}! It's great to know you work as a {learned['profession']}."
        elif learned and "name" in learned:
            response = f"Pleasure to address you, {learned['name']}."
        else:
            # Check if query targets YouTube
            if "youtube" in um_lower:
                yt_term = user_message_clean
                for prefix in [
                    "open youtube and search for", "open youtube and search", "open youtube and find",
                    "search on youtube for", "search in youtube for", "search youtube for",
                    "search on youtube", "search in youtube", "on youtube", "in youtube", "youtube"
                ]:
                    yt_term = re.sub(re.escape(prefix), "", yt_term, flags=re.IGNORECASE).strip()
                yt_term = yt_term.strip(" '\"")
                handled, res = execute_youtube_search_intent(IntentType.SYSTEM_YOUTUBE_SEARCH, {"query": yt_term or "trending"})
                speak(res)
                return res

            # 4. Search & Web Lookup First (Strictly for explicit search requests and factual entity questions)
            search_explicit_prefixes = [
                "search for", "search on google for", "search in google for", "search google for",
                "search on wikipedia for", "search wikipedia for", "search for me", "search",
                "find information on", "look up on google", "look up", "lookup",
                "tell me about", "who was", "where is"
            ]
            
            is_search_query = any(um_lower.startswith(p) for p in search_explicit_prefixes) or "search on google" in um_lower or "search on wikipedia" in um_lower

            # Informational 'who is' (excluding who is your creator/god/identity)
            if um_lower.startswith("who is ") and not any(k in um_lower for k in ["your", "my", "rohit", "god", "creator", "playing"]):
                is_search_query = True

            # Informational 'what is' entity lookups (excluding assistant status, screen, time, background)
            if (um_lower.startswith("what is ") or um_lower.startswith("what's ")) and not any(k in um_lower for k in [
                "your", "my", "screen", "background", "playing", "time", "date", "weather", "doing", "up", "going on", "neura"
            ]):
                is_search_query = True

            # Complex generative or reasoning queries that actually require LLM intelligence
            requires_llm = any(k in um_lower for k in [
                "explain", "code", "write", "debug", "how to", "how can i", "why is", "why does", "solve", "compare", "translate", "summarize", "advice", "opinion", "think about", "feel"
            ])

            if is_search_query and not requires_llm:
                # Clean query term
                clean_term = user_message_clean
                for prefix in [
                    "can you tell me which", "can you tell me who is", "can you tell me what is", 
                    "tell me which", "tell me who is", "tell me about", "search for", "search", 
                    "find information on", "find", "who is", "who was", "which", "what is", "where is", "google"
                ]:
                    if clean_term.lower().startswith(prefix):
                        clean_term = clean_term[len(prefix):].strip()
                        break

                if not clean_term:
                    clean_term = user_message_clean

                response = safe_search_lookup(clean_term)
                return response

            else:
                # 4.5. Guard: If an audibility query reached here, check hardware with Zero API Calls
                if any(p in um_lower for p in ["can you hear me", "am i audible", "hear my voice", "are you able to hear me", "can you hear", "check microphone", "check speaker"]):
                    handled, res = execute_audibility_check_intent(IntentType.SYSTEM_AUDIBILITY_CHECK, {}, user_message_clean)
                    if handled:
                        speak(res)
                        return res

                # 5. Fallback to Brain LLM for natural human conversations and reasoning
                response = generate_ai_response(user_message_clean, memory_mgr)
                print(f"{IDENTITY['name']}: {response}")

    log_activity(f"Handled query: {user_message_clean[:40]}")
    speak(response)
    return response

def close_outlook():
    outlook_windows = gw.getWindowsWithTitle('mail')
    if outlook_windows:
        outlook_window = outlook_windows[0]
        outlook_window.close()
        speak("Outlook closed successfully.")
    else:
        speak("Outlook window not found.")

def find_and_close_app(spoken_name):
    """
    Finds and closes an application by mapping a spoken name to a process name.
    """
    app_processes = {
        'whatsapp': 'whatsapp.exe',
        'word': 'WINWORD.EXE',
        'excel': 'EXCEL.EXE',
        'powerpoint': 'POWERPNT.EXE',
        'code': 'Code.exe',
        'chrome': 'chrome.exe',
        'notepad': 'notepad.exe'
    }

    spoken_name_lower = spoken_name.lower()
    process_to_kill = None
    app_keyword_found = None

    for keyword, process in app_processes.items():
        if keyword in spoken_name_lower:
            process_to_kill = process
            app_keyword_found = keyword
            break

    if process_to_kill:
        try:
            os.system(f"taskkill /f /im {process_to_kill}")
            speak(f"{app_keyword_found.capitalize()} closed successfully.")
        except Exception as e:
            speak(f"I found {app_keyword_found}, but failed to close it. Error: {e}")
    else:
        speak(f"Sorry, I don't know how to close {spoken_name}. The app may not be in my list.")


def check_input_bridge() -> str:
    """Checks and pops any pending user commands from input_bridge.json."""
    if not os.path.exists(INPUT_BRIDGE_FILE):
        return ""
    try:
        with open(INPUT_BRIDGE_FILE, "r", encoding="utf-8") as f:
            cmds = json.load(f)
        if isinstance(cmds, list) and cmds:
            next_cmd = cmds.pop(0)
            temp_file = f"{INPUT_BRIDGE_FILE}.tmp"
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(cmds, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_file, INPUT_BRIDGE_FILE)
            if next_cmd and next_cmd.strip():
                clean = next_cmd.strip()
                print(f"[Input Bridge] Processing queued GUI command: '{clean}'")
                return clean.lower()
    except Exception:
        pass
    return ""

def takeCommand():
    # 1. Immediately prioritize queued commands from frontend GUI chat
    gui_cmd = check_input_bridge()
    if gui_cmd:
        return gui_cmd

    r = sr.Recognizer()
    try:
        with sr.Microphone(device_index=1) as source:
            print("Listening...")
            r.adjust_for_ambient_noise(source, duration=0.4)
            # Recheck bridge right before blocking on listen
            gui_cmd = check_input_bridge()
            if gui_cmd:
                return gui_cmd
            try:
                audio = r.listen(source, timeout=3.5, phrase_time_limit=8.0)
                print("Recognizing...")
                query = r.recognize_google(audio, language='en-in')
                print(f"User said: {query}")
                send_to_frontend("user", query)
                return query.lower()
            except sr.WaitTimeoutError:
                return check_input_bridge()
            except sr.UnknownValueError:
                print("Sorry, I couldn't understand what you said. Please try again.")
                return check_input_bridge()
            except sr.RequestError as e:
                print(f"Could not request results; {e}")
                return check_input_bridge()
            except Exception as e:
                print(f"An error occurred: {e}")
                return check_input_bridge()
    except Exception:
        time.sleep(0.4)
        return check_input_bridge()

def resolve_folder(folder_input, base_path=None):
    """
    Returns the full path of a folder, matching common or custom folder names.
    If base_path is given, searches inside it for fuzzy matches.
    """
    folder_input = folder_input.lower().strip()
    home = os.path.expanduser("~")
    folder_map = {
        "desktop": ["desktop", "my desktop", "desk"],
        "documents": ["documents", "document", "my documents", "docs"],
        "downloads": ["downloads", "download", "my downloads"]
    }

    # Match common folders first
    for key, variations in folder_map.items():
        for var in variations:
            if var in folder_input:
                return os.path.join(home, key.capitalize())

    # If base_path is given, search for fuzzy match in that path
    if base_path and os.path.exists(base_path):
        spoken_norm = re.sub(r'[^a-z0-9]', '', folder_input)
        folders = [f for f in os.listdir(base_path) if os.path.isdir(os.path.join(base_path, f))]
        matches = []
        for folder in folders:
            folder_norm = re.sub(r'[^a-z0-9]', '', folder.lower())
            if spoken_norm in folder_norm or folder_norm in spoken_norm:
                matches.append(folder)
        if len(matches) == 1:
            return os.path.join(base_path, matches[0])
        elif len(matches) > 1:
            # Multiple matches, ask user to choose
            speak("I found multiple folders. Please tell me the number of the folder you want.")
            for i, f in enumerate(matches, 1):
                speak(f"{i}. {f}")
            choice = takeCommand()
            numbers = re.findall(r'\d+', choice)
            if numbers:
                index = int(numbers[0]) - 1
                if 0 <= index < len(matches):
                    return os.path.join(base_path, matches[index])
            return os.path.join(base_path, matches[0])
        else:
            return os.path.join(base_path, folder_input)

    return folder_input


def open_folder_from_location(folder_name, location):
    """Open a named folder only within the requested Windows user directory."""
    home = os.path.expanduser("~")
    location_map = {
        "desktop": os.path.join(home, "Desktop"),
        "downloads": os.path.join(home, "Downloads"),
        "documents": os.path.join(home, "Documents"),
        "music": os.path.join(home, "Music"),
        "pictures": os.path.join(home, "Pictures"),
    }
    base_path = location_map.get(location.lower())
    if not base_path or not os.path.isdir(base_path):
        return f"I could not find the {location} folder on this computer."

    target_path = resolve_folder(folder_name, base_path)
    if not os.path.isdir(target_path):
        return f"I could not find a folder named {folder_name} in {location}."

    try:
        os.startfile(target_path)
        return f"Opening the {folder_name} folder from {location}."
    except OSError as exc:
        print(f"Folder open error for '{target_path}': {exc}")
        return f"I found the {folder_name} folder, but could not open it."


def open_file_from_system(file_name, location=None):
    """Find and launch a file from a requested or standard user directory."""
    home = os.path.expanduser("~")
    location_map = {
        "desktop": os.path.join(home, "Desktop"),
        "downloads": os.path.join(home, "Downloads"),
        "documents": os.path.join(home, "Documents"),
        "music": os.path.join(home, "Music"),
        "pictures": os.path.join(home, "Pictures"),
    }
    search_roots = [location_map[location.lower()]] if location and location.lower() in location_map else [
        path for path in location_map.values() if os.path.isdir(path)
    ]
    requested = file_name.strip().strip("\"'")

    def normalize_file_phrase(value):
        """Remove spoken type words and normalize a file name for matching."""
        value = os.path.splitext(value)[0].lower().replace("_", " ")
        value = re.sub(
            r"\b(?:excel|spreadsheet|xlsx|xls|word|docx?|pdf|powerpoint|"
            r"pptx?|text|txt|csv|rtf|odt|ods|image|picture|photo|"
            r"file|document|sheet)\b",
            " ",
            value,
        )
        return re.sub(r"[^a-z0-9]+", " ", value).strip()

    def file_tokens(value):
        tokens = normalize_file_phrase(value).split()
        return {token[:-1] if len(token) > 3 and token.endswith("s") else token for token in tokens}

    direct_path = os.path.expandvars(os.path.expanduser(requested))
    if os.path.isfile(direct_path):
        matches = [direct_path]
    else:
        requested_tokens = file_tokens(os.path.basename(requested))
        requested_norm = "".join(sorted(requested_tokens))
        matches = []
        for root in search_roots:
            if not os.path.isdir(root):
                continue
            for current_root, _, files in os.walk(root):
                for candidate in files:
                    candidate_tokens = file_tokens(candidate)
                    candidate_norm = "".join(sorted(candidate_tokens))
                    if (
                        requested_tokens
                        and (
                            requested_tokens <= candidate_tokens
                            or requested_norm in candidate_norm
                        )
                    ):
                        matches.append(os.path.join(current_root, candidate))

    if not matches:
        scope = f" in {location}" if location else ""
        return f"I could not find the file '{file_name}'{scope}."
    if len(matches) > 1:
        return f"I found multiple files named '{file_name}'. Please include its folder location."

    target_path = matches[0]
    try:
        os.startfile(target_path)
        return f"Opening {os.path.basename(target_path)}."
    except OSError as exc:
        print(f"File open error for '{target_path}': {exc}")
        return f"I found {os.path.basename(target_path)}, but could not open it."


def find_folder(base_path, spoken_name):
    """
    Searches for a folder in base_path that matches spoken_name using normalized comparison.
    Returns full path if found, else None.
    """
    spoken_norm = re.sub(r'[^a-z0-9]', '', spoken_name.lower())

    folders = [f for f in os.listdir(base_path) if os.path.isdir(os.path.join(base_path, f))]

    matches = []
    for folder in folders:
        folder_norm = re.sub(r'[^a-z0-9]', '', folder.lower())
        if spoken_norm in folder_norm or folder_norm in spoken_norm:
            matches.append(folder)

    if len(matches) == 1:
        return os.path.join(base_path, matches[0])
    elif len(matches) > 1:
        speak("I found multiple folders matching your request. Please choose one:")
        for i, f in enumerate(matches, 1):
            speak(f"{i}. {f}")
        choice = takeCommand()
        numbers = re.findall(r'\d+', choice)
        if numbers:
            index = int(numbers[0]) - 1
            if 0 <= index < len(matches):
                return os.path.join(base_path, matches[index])
        return os.path.join(base_path, matches[0])
    else:
        return None


def perform_face_recognition(show_window: bool = True):
    """
    Executes the Face Recognition pipeline:
    Camera -> Face Detection (YuNet) -> Face Embedding (SFace) -> Compare with Rohit's enrolled embedding -> Identity -> Neura's memory/state
    """
    global SCREEN_ACCESS_ALLOWED
    if not SCREEN_ACCESS_ALLOWED:
        speak("Screen access is disabled. Please say allow screen access first.")
        return

    speak("Activating camera for biometric face recognition...")
    system = get_face_system()
    res = system.recognize_from_camera(timeout_seconds=5.0, show_window=show_window)
    speech = system.update_neura_state(res, memory_mgr)
    speak(speech)
    remember_interaction("Face recognition via camera", speech)
    return res


def identify_user_by_face():
    """
    Biometric face verification to answer 'who am i'.
    Detects face from camera:
    - If enrolled owner (Rohit Kumar Adak): 'You are my owner, Rohit Kumar Adak'
    - If known registered person (e.g. Sneha): 'You are Sneha.'
    - Otherwise: 'Sorry, I don't know who you are.'
    """
    global SCREEN_ACCESS_ALLOWED
    if not SCREEN_ACCESS_ALLOWED:
        speak("Screen access is disabled. Please say allow screen access first.")
        return "Screen access disabled"

    system = get_face_system()
    is_owner = False
    identity = "Unknown"
    camera = None

    # 1. Attempt live capture and recognition with YuNet + SFace
    try:
        camera = cv2.VideoCapture(0)
        if camera.isOpened():
            camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            frame = None
            for _ in range(5):
                ret, tmp = camera.read()
                if ret and tmp is not None:
                    frame = tmp
                time.sleep(0.03)

            if frame is not None:
                results, _ = system.process_frame(frame, draw_overlay=False, mirror_display=False)
                if results and len(results) > 0:
                    primary = results[0]
                    if primary.get("is_owner"):
                        is_owner = True
                        identity = system.owner_profile.get("name") or "Owner"
                    elif primary.get("is_known"):
                        identity = primary.get("identity", "Unknown")
    except Exception as e:
        print(f"[Face ID Camera Error]: {e}")
    finally:
        if camera is not None:
            camera.release()

    # 2. Fallback to shared presence/state if camera was locked by frontend
    if not is_owner and identity == "Unknown":
        try:
            memory_mgr.load_all()
            facts = memory_mgr.user_memory.get("user_facts", {})
            presence = facts.get("presence", "")
            if facts.get("face_authenticated", False) and presence == "present":
                is_owner = True
                identity = system.owner_profile.get("name") or "Owner"
            elif presence.startswith("guest_"):
                guest_name = presence.replace("guest_", "").replace("_present", "").strip()
                if guest_name:
                    identity = guest_name
        except Exception:
            pass

    owner_name = system.owner_profile.get("name") or "Owner"
    owner_title = system.owner_profile.get("title") or (f"Rohit Kumar Adak" if "rohit" in owner_name.lower() else owner_name)

    if is_owner:
        memory_mgr.add_fact("face_authenticated", True)
        memory_mgr.add_fact("presence", "present")
        response = f"You are my owner, {owner_title}"
    elif identity != "Unknown" and identity != "None":
        response = f"You are {identity}."
    else:
        response = "Sorry, I don't know who you are."

    speak(response)
    remember_interaction("who am i", response)
    log_activity(f"Visual ID answer: {response}")
    return response


def access_camera():
    global SCREEN_ACCESS_ALLOWED

    if not SCREEN_ACCESS_ALLOWED:
        speak("Screen access is disabled. Please say allow screen access first.")
        return

    system = get_face_system()
    camera = cv2.VideoCapture(0)

    if not camera.isOpened():
        speak("Unable to access the camera, Sir.")
        return

    active_person_spoken = None
    candidate_person = None
    candidate_streak = 0
    no_face_start_time = 0.0
    last_spoken_time = 0.0

    def async_camera_speak(text: str):
        threading.Thread(target=speak, args=(text,), daemon=True).start()

    window_title = 'Neura Vision Feed - [Q] Exit | [C] Capture'

    try:
        while True:
            ret, frame = camera.read()
            if not ret:
                break

            # Process frame with YuNet face detection & SFace recognition overlay (mirrored display for natural preview)
            results, annotated = system.process_frame(frame, draw_overlay=True, mirror_display=True)
            now = time.time()

            if results and len(results) > 0:
                no_face_start_time = 0.0
                primary = results[0]
                is_owner = primary.get("is_owner", False)
                is_known = primary.get("is_known", False)
                identity_name = primary.get("identity", "Unknown")

                if is_owner:
                    cand = system.owner_profile.get("name") or identity_name
                elif is_known:
                    cand = identity_name
                else:
                    cand = "UNKNOWN"

                if cand == candidate_person:
                    candidate_streak += 1
                else:
                    candidate_person = cand
                    candidate_streak = 1

                # If face is stable for >= 3 frames and identity changed, tell the name as per HUD text
                if candidate_streak >= 3 and cand != active_person_spoken:
                    if (now - last_spoken_time) >= 1.5:
                        active_person_spoken = cand
                        last_spoken_time = now
                        if is_owner:
                            async_camera_speak(f"Hello Sir, identity verified! Welcome, {cand}.")
                        elif is_known:
                            async_camera_speak(f"Hello {cand}, welcome!")
                        else:
                            active_person_spoken = "UNKNOWN"
                            try:
                                from setup_face import _execute_auto_learning_procedure
                                _execute_auto_learning_procedure(camera, system, window_title)
                                system.load_known_faces()
                            except Exception as e:
                                print(f"[Neura Camera Auto-Learn Error]: {e}")
                                async_camera_speak("Unknown face detected.")
            else:
                candidate_person = None
                candidate_streak = 0
                if no_face_start_time == 0.0:
                    no_face_start_time = now
                elif (now - no_face_start_time) >= 1.5:
                    if active_person_spoken != "NO_FACE":
                        active_person_spoken = "NO_FACE"
                        last_spoken_time = now
                        async_camera_speak("No face is detected.")

            cv2.imshow(window_title, annotated)

            key = cv2.waitKey(1) & 0xFF
            if key in (ord('q'), ord('Q'), 27):
                break
            elif key in (ord('c'), ord('C')):
                image_name = f"captured_{int(time.time())}.jpg"
                cv2.imwrite(image_name, frame)
                async_camera_speak("Image captured successfully.")

    finally:
        camera.release()
        cv2.destroyAllWindows()

# ============================================================
# WINDOWS VOLUME CONTROL
# ============================================================

def get_volume_controller():
    """
    Get the Windows default audio output volume controller.
    Compatible with newer pycaw versions.
    """

    try:
        devices = AudioUtilities.GetSpeakers()

        # Newer pycaw versions
        if hasattr(devices, "EndpointVolume"):
            return devices.EndpointVolume

        # Older pycaw versions
        interface = devices.Activate(
            IAudioEndpointVolume._iid_,
            CLSCTX_ALL,
            None
        )

        return cast(
            interface,
            POINTER(IAudioEndpointVolume)
        )

    except Exception as e:
        print(f"[Volume Controller Error] {e}")
        return None

def get_current_volume():
    """
    Return current master volume as percentage (0-100).
    """

    try:
        volume = get_volume_controller()

        if volume is None:
            return None

        current = volume.GetMasterVolumeLevelScalar()

        return int(round(current * 100))

    except Exception as e:
        print(f"[Get Volume Error] {e}")
        return None


def change_volume(action):
    """
    Increase, decrease, mute or unmute Windows master volume.
    """

    try:
        volume = get_volume_controller()

        if volume is None:
            speak("Sorry Sir, I could not access the system volume.")
            return

        current = volume.GetMasterVolumeLevelScalar()

        print(f"[Volume] Current volume: {int(current * 100)}%")


        # Volume UP
        if action == "up":

            new_volume = min(current + 0.10, 1.0)

            volume.SetMasterVolumeLevelScalar(
                new_volume,
                None
            )

            percentage = int(round(new_volume * 100))

            print(f"[Volume] New volume: {percentage}%")

            speak(f"Volume increased to {percentage} percent.")


        # Volume DOWN
        elif action == "down":

            new_volume = max(current - 0.10, 0.0)

            volume.SetMasterVolumeLevelScalar(
                new_volume,
                None
            )

            percentage = int(round(new_volume * 100))

            print(f"[Volume] New volume: {percentage}%")

            speak(f"Volume decreased to {percentage} percent.")


        # MUTE
        elif action == "mute":

            volume.SetMute(1, None)

            print("[Volume] Muted")

            speak("Volume muted.")


        # UNMUTE
        elif action == "unmute":

            volume.SetMute(0, None)

            print("[Volume] Unmuted")

            speak("Volume unmuted.")


    except Exception as e:

        print(f"[Volume Control Error] {e}")

        speak("Sorry Sir, I could not change the volume.")

def set_volume(level):
    """
    Set Windows master volume to an exact percentage.
    """

    try:

        level = int(level)

        # Limit between 0 and 100
        level = max(0, min(level, 100))

        volume = get_volume_controller()

        if volume is None:
            speak("Sorry Sir, I could not access the system volume.")
            return

        scalar = level / 100.0

        volume.SetMasterVolumeLevelScalar(
            scalar,
            None
        )

        actual = volume.GetMasterVolumeLevelScalar()

        print(
            f"[Volume] Requested: {level}% | "
            f"Actual: {int(round(actual * 100))}%"
        )

        speak(f"Volume set to {level} percent.")

    except Exception as e:

        print(f"[Set Volume Error] {e}")

        speak("Sorry Sir, I could not set the volume.")

def change_brightness(action):
    try:
        current = sbc.get_brightness(display=0)[0]  # get current brightness
        if action == "up":
            new_level = min(current + 10, 100)
            sbc.set_brightness(new_level)
            speak("Brightness increased")
        elif action == "down":
            new_level = max(current - 10, 0)
            sbc.set_brightness(new_level)
            speak("Brightness decreased")
    except Exception as e:
        print(f"Brightness error: {e}")
        speak("Sorry sir, I could not change the brightness.")

def set_brightness(level):
    try:
        if 0 <= level <= 100:
            sbc.set_brightness(level)
            speak(f"Brightness set to {level} percent")
        else:
            speak("Please give me a number between 0 and 100.")
    except Exception as e:
        print(f"Brightness error: {e}")
        speak("Sorry sir, I could not set the brightness.")

def take_note():
    speak("What would you like me to write down, Sir?")
    note = takeCommand()
    if not note:
        speak("Sorry, I didn't catch that.")
        return

    speak("Where should I save this note?")
    folder_input = takeCommand()
    folder_path = resolve_folder(folder_input)

    # Create folder if it doesn't exist
    if not os.path.exists(folder_path):
        speak(f"Folder does not exist. I will create it at {folder_path}.")
        os.makedirs(folder_path)

    speak("What should be the file name?")
    filename = takeCommand()
    if not filename.endswith(".txt"):
        filename += ".txt"

    file_path = os.path.join(folder_path, filename)

    try:
        with open(file_path, "a") as f:
            f.write(f"{note}\n")
        speak(f"Note saved successfully in {file_path}")
        print(f"Note saved in: {file_path}")
    except Exception as e:
        speak(f"Sorry Sir, I could not save the note. Error: {e}")

def read_note_from_folder():
    speak("Please tell me the folder where your notes are saved, Sir.")
    folder_input = takeCommand()
    
    base_path = os.path.expanduser("~")
    folder_path = resolve_folder(folder_input, base_path)

    if not os.path.exists(folder_path):
        speak(f"Sorry sir, the folder {folder_path} does not exist.")
        return

    # List all text files
    files = [f for f in os.listdir(folder_path) if f.endswith('.txt')]
    if not files:
        speak(f"No text files found in {folder_path}.")
        return

    speak("Here are the notes I found:")
    for i, file in enumerate(files, 1):
        print(f"{i}. {file}")
        speak(f"{i}. {file}")

    speak("Please tell me the number or name of the note you want to read.")
    choice = takeCommand()
    
    numbers = re.findall(r'\d+', choice)
    if numbers:
        index = int(numbers[0]) - 1
        if 0 <= index < len(files):
            filename = files[index]
        else:
            speak("Invalid number. Please try again.")
            return
    else:
        # Fuzzy match by name
        spoken_norm = re.sub(r'[^a-z0-9]', '', choice.lower())
        matches = [f for f in files if spoken_norm in re.sub(r'[^a-z0-9]', '', f.lower())]
        if matches:
            filename = matches[0]
        else:
            speak("Could not find a matching note. Please try again.")
            return

    file_path = os.path.join(folder_path, filename)
    try:
        with open(file_path, "r") as f:
            content = f.read()
        if content.strip():
            speak(f"Reading the contents of {filename}")
            print(content)
            speak(content)
        else:
            speak(f"The file {filename} is empty.")
    except Exception as e:
        speak(f"Sorry sir, I could not read the file. Error: {e}")

def set_reminder():
    speak("What reminder should I set, Sir?")
    reminder = takeCommand()
    if not reminder:
        speak("Sorry, I didn't catch that.")
        return

    speak("When should I remind you? sir!")
    time_input = takeCommand().lower().strip()

    now = datetime.datetime.now()

    try:
        import re
        match = re.match(r"(\d+)\s*(minute|minutes|hour|hours)", time_input)
        if match:
            value = int(match.group(1))
            unit = match.group(2)
            if "minute" in unit:
                reminder_time = now + datetime.timedelta(minutes=value)
            else: 
                reminder_time = now + datetime.timedelta(hours=value)
        else:
            reminder_time = datetime.datetime.strptime(time_input, "%H:%M")
            if reminder_time.time() < now.time():
                reminder_time = datetime.datetime.combine(now.date() + datetime.timedelta(days=1), reminder_time.time())
        filename = "Nura_Reminders.txt"
        with open(filename, "a") as f:
            f.write(f"{reminder_time.strftime('%Y-%m-%d %H:%M')}: {reminder}\n")

        speak(f"Reminder set for {reminder_time.strftime('%H:%M')}.")

    except Exception as e:
        speak(f"Sorry Sir, I could not set the reminder. Error: {e}")


def check_reminders():
    filename = "Nura_Reminders.txt"
    while True:
        if os.path.exists(filename):
            now = datetime.datetime.now()
            reminders_to_keep = []

            with open(filename, "r") as f:
                lines = f.readlines()

            for line in lines:
                try:
                    dt_str, reminder_text = line.strip().split(": ", 1)
                    reminder_time = datetime.datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
                    
                    if now >= reminder_time:
                        speak(f"Sir, this is your reminder: {reminder_text}")
                    else:
                        reminders_to_keep.append(line)
                except:
                    continue
            with open(filename, "w") as f:
                f.writelines(reminders_to_keep)

        time.sleep(30)

def find_and_open(name):
    """
    Searches for and opens an application or file by its name.
    Prioritizes Start Menu and Program Files for efficiency.
    Returns True if found and opened, False otherwise.
    """
    app_name = name.lower().strip()
    # Remove common words that don't help the search
    app_name = app_name.replace("application", "").replace("program", "").strip()

    # Photos is a Microsoft Store app and has no searchable .exe/.lnk entry.
    if app_name in {"photo", "photos", "picture", "pictures", "photo app", "pictures app"}:
        try:
            os.startfile("ms-photos:")
            speak("Opening Photos.")
            return True
        except OSError as exc:
            print(f"Photos app launch error: {exc}")
            return False

    # Define common paths where applications are likely to be found
    search_paths = [
        os.path.join(os.getenv('APPDATA'), 'Microsoft\\Windows\\Start Menu\\Programs'),
        'C:\\ProgramData\\Microsoft\\Windows\\Start Menu\\Programs',
        'C:\\Program Files',
        'C:\\Program Files (x86)',
        'C:\\Windows\\System32',
    ]

    print(f"Searching for '{app_name}' on the system...")

    for path in search_paths:
        if not os.path.exists(path):
            continue
        
        for root, dirs, files in os.walk(path):
            for file in files:
                file_base, file_ext = os.path.splitext(file)
                if app_name in file_base.lower() and file_ext.lower() in ['.exe', '.lnk']:
                    try:
                        full_path = os.path.join(root, file)
                        speak(f"Found and opening {file_base}")
                        print(f"Opening: {full_path}")
                        os.startfile(full_path)
                        return True
                    except Exception as e:
                        print(f"Failed to open {file}: {e}")
                        speak(f"Sorry, I found {file_base} but could not open it.")
                        return False

    return False

def open_app_with_windows_search(app_name):
    try:
        keyboard.press_and_release('win+s')
        time.sleep(1)
        pyautogui.typewrite(app_name)
        time.sleep(1.5) 
        
        if app_name == "clipchamp": 
            keyboard.press_and_release('enter')
            return True
        
        else:
            web_search_result = pyautogui.locateOnScreen('web_icon.png', confidence=0.8)

            if web_search_result is not None:
                keyboard.press_and_release('esc')
                return False
            else:
                keyboard.press_and_release('enter')
                return True

    except Exception as e:
        print(f"Error: {e}")
        keyboard.press_and_release('esc')
        return False


def get_weather(city):
    API_KEY = os.getenv("WEATHER_API")
    if not API_KEY:
        return "Weather API key is missing in your environment file."

    BASE_URL = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={API_KEY}&units=metric"

    try:
        response = requests.get(BASE_URL, timeout=5)
        data = response.json()

        if data.get("cod") != 200:
            return f"Sorry, I couldn't find weather information for {city}."

        weather = data["weather"][0]["description"].capitalize()
        temp = data["main"]["temp"]
        feels_like = data["main"]["feels_like"]
        humidity = data["main"]["humidity"]
        wind_speed = data["wind"]["speed"]
        country = data["sys"]["country"]

        return (
            f"The weather in {city.capitalize()}, {country} is {weather}. "
            f"The temperature is {temp}°C, feels like {feels_like}°C, "
            f"with humidity at {humidity} percent and wind speed {wind_speed} meters per second."
        )

    except Exception as e:
        print(f"Weather error: {e}")
        return "Sorry, there was an issue fetching the weather data."


def _fast_com_test_urls():
    """Resolve the current Fast.com test token and download targets."""
    session = requests.Session()
    homepage = session.get("https://fast.com/", timeout=8)
    homepage.raise_for_status()
    script_match = re.search(r'<script[^>]+src="([^"]+)"', homepage.text, re.IGNORECASE)
    if not script_match:
        raise RuntimeError("Fast.com test script was not found.")

    script_url = requests.compat.urljoin(homepage.url, script_match.group(1))
    script = session.get(script_url, timeout=8)
    script.raise_for_status()
    token_match = re.search(r'token:"([^"]+)"', script.text)
    if not token_match:
        raise RuntimeError("Fast.com test token was not found.")

    config_url = (
        "https://api.fast.com/netflix/speedtest"
        f"?https=true&token={token_match.group(1)}&urlCount=3"
    )
    config = session.get(config_url, timeout=8)
    config.raise_for_status()
    targets = [item.get("url") for item in config.json() if item.get("url")]
    if not targets:
        raise RuntimeError("Fast.com returned no test targets.")
    return session, targets


def _measure_fast_download(session, targets, duration=5.0):
    """Measure download throughput against Fast.com targets."""
    started = time.perf_counter()
    deadline = started + duration
    received = 0
    response = None
    try:
        response = session.get(targets[0], stream=True, timeout=(8, duration + 8))
        response.raise_for_status()
        for chunk in response.iter_content(chunk_size=256 * 1024):
            if chunk:
                received += len(chunk)
            if time.perf_counter() >= deadline:
                break
    finally:
        if response is not None:
            response.close()
    elapsed = max(time.perf_counter() - started, 0.001)
    return (received * 8) / elapsed / 1_000_000


def _measure_fast_upload(session, target, duration=4.0):
    """Measure upload throughput using Fast.com's speed-test endpoint."""
    payload = os.urandom(4 * 1024 * 1024)
    started = time.perf_counter()
    response = session.post(
        target,
        data=payload,
        headers={"Content-Type": "application/octet-stream"},
        timeout=(8, duration + 8),
    )
    response.raise_for_status()
    elapsed = max(time.perf_counter() - started, 0.001)
    return (len(payload) * 8) / elapsed / 1_000_000


def get_network_speed():
    """Return Fast.com download and upload measurements in Mbps."""
    try:
        session, targets = _fast_com_test_urls()
        download_samples = [
            _measure_fast_download(session, [target], duration=3.0)
            for target in targets[:2]
        ]
        download_mbps = max(download_samples)
        upload_mbps = _measure_fast_upload(session, targets[0])
        return (
            f"Your internet speed is approximately {download_mbps:.1f} Mbps download "
            f"and {upload_mbps:.1f} Mbps upload, measured using Fast.com."
        )
    except (requests.RequestException, ValueError, RuntimeError) as exc:
        print(f"Fast.com speed test error: {exc}")
        return "I could not complete the Fast.com network speed test. Please check your internet connection."


def get_system_condition():
    """Return current CPU, memory, disk, and battery status."""
    cpu_percent = psutil.cpu_percent(interval=0.5)
    memory_info = psutil.virtual_memory()
    disk_info = psutil.disk_usage(os.path.abspath(os.sep))
    details = [
        f"CPU usage is {cpu_percent:.0f} percent",
        f"RAM usage is {memory_info.percent:.0f} percent",
        f"disk usage is {disk_info.percent:.0f} percent",
    ]
    battery = psutil.sensors_battery()
    if battery is not None:
        charging = "and charging" if battery.power_plugged else "and not charging"
        details.append(f"battery is at {battery.percent:.0f} percent {charging}")
    return "System condition: " + ", ".join(details) + "."


def check_microphone_and_speaker_status() -> Tuple[bool, Dict[str, Any], str]:
    """
    Actively inspects the microphone (default input device, channels, format) and
    speaker (output endpoint, volume level scalar, mute state) to verify if Neura
    can hear audio properly and speak audibly to the user.
    Returns (healthy: bool, details_dict: dict, verbal_response: str).
    """
    mic_name = "Default Microphone"
    mic_healthy = False
    mic_channels = 1
    mic_rate = 44100
    mic_index = 1

    try:
        p = sr.Microphone.get_pyaudio().PyAudio()
        try:
            default_info = p.get_default_input_device_info()
            mic_name = default_info.get("name", "Default Microphone")
            mic_channels = default_info.get("maxInputChannels", 1)
            mic_rate = int(default_info.get("defaultSampleRate", 44100))
            mic_index = default_info.get("index", 1)
            mic_healthy = (mic_channels > 0)
        except Exception:
            try:
                dev_info = p.get_device_info_by_index(1)
                mic_name = dev_info.get("name", "Microphone Array")
                mic_channels = dev_info.get("maxInputChannels", 1)
                mic_rate = int(dev_info.get("defaultSampleRate", 44100))
                mic_healthy = (mic_channels > 0)
            except Exception:
                names = sr.Microphone.list_microphone_names()
                if names:
                    mic_name = names[0]
                    mic_healthy = True
        finally:
            p.terminate()
    except Exception as e:
        mic_name = f"Microphone Unavailable ({e})"
        mic_healthy = False

    clean_mic_name = mic_name.replace("\r", "").replace("\n", "").strip()

    speaker_name = "Speakers"
    volume_level = 100
    is_muted = False
    speaker_healthy = False

    try:
        speakers = AudioUtilities.GetSpeakers()
        if hasattr(speakers, "FriendlyName") and speakers.FriendlyName:
            speaker_name = speakers.FriendlyName
        vol_ctrl = get_volume_controller()
        if vol_ctrl is not None:
            scalar = vol_ctrl.GetMasterVolumeLevelScalar()
            volume_level = int(round(scalar * 100))
            is_muted = bool(vol_ctrl.GetMute())
            speaker_healthy = True
    except Exception as e:
        speaker_name = f"Speakers Unavailable ({e})"

    clean_speaker_name = speaker_name.replace("\r", "").replace("\n", "").strip()

    can_hear = mic_healthy
    can_speak = speaker_healthy and (volume_level > 0) and (not is_muted)

    details = {
        "microphone": {
            "name": clean_mic_name,
            "healthy": mic_healthy,
            "channels": mic_channels,
            "sample_rate": mic_rate,
            "device_index": mic_index,
        },
        "speaker": {
            "name": clean_speaker_name,
            "healthy": speaker_healthy,
            "volume": volume_level,
            "is_muted": is_muted,
        },
        "can_hear": can_hear,
        "can_speak": can_speak,
    }

    if can_hear and can_speak:
        speech = (
            f"Yes Sir, I can hear you loud and clear! I checked your audio devices: "
            f"your microphone ({clean_mic_name}) is working properly and receiving audio, "
            f"and your speaker ({clean_speaker_name}) is active at {volume_level} percent volume and unmuted. "
            f"You are completely audible to me."
        )
    elif can_hear and is_muted:
        speech = (
            f"Yes Sir, I can hear you clearly! Your microphone ({clean_mic_name}) is working properly, "
            f"but note that your speaker ({clean_speaker_name}) is currently muted. "
            f"Please unmute your speaker so you can hear my voice."
        )
    elif can_hear and volume_level == 0:
        speech = (
            f"Yes Sir, I can hear you! Your microphone ({clean_mic_name}) is working properly, "
            f"but your speaker volume is currently at 0 percent."
        )
    elif not can_hear and speaker_healthy:
        speech = (
            f"Sir, I checked your audio devices: I am having trouble detecting an active microphone ({clean_mic_name}), "
            f"though your speaker ({clean_speaker_name}) is working at {volume_level} percent volume. "
            f"Please verify that your microphone is plugged in and allowed in Windows settings."
        )
    else:
        speech = (
            f"Sir, I checked your audio devices: your microphone status is {clean_mic_name} "
            f"and speaker status is {clean_speaker_name} at {volume_level} percent volume."
        )

    return can_hear, details, speech


def execute_audibility_check_intent(intent, metadata=None, raw_query: str = "") -> Tuple[bool, str]:
    """
    Executes audibility check without external LLM API calls:
    Inspects microphone and speaker hardware and sends an audio status report to the frontend.
    """
    if intent != IntentType.SYSTEM_AUDIBILITY_CHECK:
        rq = raw_query.lower()
        if not (
            any(p in rq for p in ["can you hear me", "am i audible", "are you able to hear me", "can you hear my voice", "check microphone", "check speaker", "can you hear properly"])
            or re.search(r"\b(?:hear\s+me|am\s+i\s+audible|audible\s+to\s+you)\b", rq)
        ):
            return False, ""

    can_hear, details, speech = check_microphone_and_speaker_status()

    mic = details["microphone"]
    spk = details["speaker"]
    mute_label = "Muted ⚠️" if spk["is_muted"] else "Unmuted ✅"
    mic_status_label = "Active & Receiving Audio ✅" if mic["healthy"] else "Not Detected ❌"

    card = (
        f"🎤 **Audio Hardware & Audibility Status**\n\n"
        f"• **Microphone**: {mic['name']} ({mic_status_label})\n"
        f"  - Channels: {mic['channels']} | Sample Rate: {mic['sample_rate']} Hz\n"
        f"• **Speaker**: {spk['name']} (Active at {spk['volume']}% | {mute_label})\n"
        f"• **Audibility Verdict**: {'100% Audible & Functioning Properly ✅' if can_hear else 'Microphone Inactive ⚠️'}\n\n"
        f"*{speech}*"
    )

    send_to_frontend("neura", card)
    return True, speech


def execute_system_diagnostic_intent(intent, metadata=None, raw_query: str = ""):
    if intent == IntentType.SYSTEM_AUDIBILITY_CHECK:
        return execute_audibility_check_intent(intent, metadata or {}, raw_query)
    if intent == IntentType.SYSTEM_NETWORK_SPEED:
        return True, get_network_speed()
    if intent == IntentType.SYSTEM_CONDITION:
        return True, get_system_condition()
    if intent == IntentType.SYSTEM_BACKGROUND_STATUS:
        return True, desktop_ctrl.get_background_activity()
    if intent == IntentType.SYSTEM_SCREEN_AND_BACKGROUND_STATUS:
        return True, desktop_ctrl.get_screen_and_background_activity()
    return False, ""


# ---------- MEDIA CONTROLS ----------
def pause_or_resume_media():
    keyboard.press_and_release('play/pause media')
    speak("Media playback toggled.")

def next_media():
    keyboard.press_and_release('next track')
    speak("Playing next track.")

def previous_media():
    keyboard.press_and_release('previous track')
    speak("Playing previous track.")

def detect_media_activity():
    """
    Detect if media is playing using system heuristics.
    """
    try:
        from pycaw.pycaw import AudioUtilities
        sessions = AudioUtilities.GetAllSessions()
        for session in sessions:
            if session.State == 1:  # Active
                if session.Process:
                    pname = session.Process.name()
                    if pname.lower() not in ["python.exe", "system"]:
                        return f"Media is playing from {pname}"
        return "No active media playback detected."
    except Exception:
        return "Unable to detect media status."



if __name__ == "__main__":

    # ---------- RESET CHAT SESSION ----------
    with open(CHAT_BRIDGE_FILE, "w", encoding="utf-8") as f:
        json.dump([], f)

    # Print startup banner once
    art = text2art("Neura", font='block', chr_ignore=True)
    print("\n" + art + "\n")
    wishMe()
    wishtime()
    analyze_memory_on_start()

    pref_city = memory_mgr.get_preference("weather_city")
    pref_songs = memory_mgr.get_preference("song_preferences")
    if pref_city:
        speak(f"I remember your preferred weather city is {pref_city}.")
    if pref_songs:
        if isinstance(pref_songs, list) and pref_songs:
            speak(f"You've told me you like {', '.join(pref_songs[:3])}.")
        elif pref_songs:
            speak(f"You've told me you like {pref_songs} music.")

    from brain.alert_service import get_alert_service
    get_alert_service(voice_speaker_fn=speak)

    reminder_thread = threading.Thread(target=check_reminders, daemon=True)
    reminder_thread.start()

    while True:
        # Check proactive announcements from background agents
        try:
            announcements = agent_orchestrator.get_proactive_announcements()
            for ann in announcements:
                print(f"📢 [Neura Proactive Alert]: {ann}")
                speak(ann)
        except Exception as e:
            print(f"[Proactive Announcement Error]: {e}")

        query = takeCommand()
        if not query:
            time.sleep(0.05)
            continue

        # Parallel Context Memory Analysis & Routing
        agent_orchestrator.memory_agent.record_incoming_command_parallel(query)

        if 'good bye' in query or 'goodbye' in query or 'exit' in query or 'bye' in query or "quit" in query or "good night" in query:
            speak("Goodbye Sir!")
            break

        # Check if auto-learning was triggered by frontend (asking unknown person for their name)
        if os.path.exists(AUTO_LEARN_BRIDGE_FILE):
            try:
                with open(AUTO_LEARN_BRIDGE_FILE, "r", encoding="utf-8") as f:
                    bridge_data = json.load(f)
                if bridge_data.get("active", False) and not bridge_data.get("acquired_name"):
                    if is_refusal_response(query):
                        bridge_data["acquired_name"] = "__ANONYMOUS__"
                        with open(AUTO_LEARN_BRIDGE_FILE, "w", encoding="utf-8") as f:
                            json.dump(bridge_data, f)
                        print("👤 [Neura Backend] User replied 'no' -> registered as __ANONYMOUS__")
                        continue
                    extracted = clean_extracted_name(query)
                    if extracted and len(extracted) >= 2 and extracted.lower() not in ["none", "quit", "exit"]:
                        bridge_data["acquired_name"] = extracted
                        with open(AUTO_LEARN_BRIDGE_FILE, "w", encoding="utf-8") as f:
                            json.dump(bridge_data, f)
                        print(f"👤 [Neura Backend] Captured name for auto-learning: {extracted}")
                        continue
            except Exception:
                pass

        # Check Alert / Alarm Subsystem
        intent, metadata = route_intent(query)
        agent_orchestrator.assign_agents_for_intent(intent, metadata, query)

        handled, res = execute_alert_intent(intent, metadata, query)
        if handled:
            agent_orchestrator.release_agents(grace_period=3.5)
            speak(res)
            remember_interaction(query, res)
            agent_orchestrator.memory_agent.record_task_success(query, str(intent), res)
            log_activity(f"Alert {intent}: {res[:40]}")
            continue

        # Check Audibility & Microphone/Speaker Hardware Check (Zero API Call)
        handled, res = execute_audibility_check_intent(intent, metadata, query)
        if handled:
            agent_orchestrator.release_agents(grace_period=3.5)
            speak(res)
            remember_interaction(query, res)
            agent_orchestrator.memory_agent.record_task_success(query, str(intent), res)
            log_activity(f"Audibility Check {intent}: {res[:40]}")
            continue

        # Check Multi-Agent Subsystem first
        handled, res = execute_agent_intent(intent, metadata, query)
        if handled:
            agent_orchestrator.release_agents(grace_period=3.5)
            speak(res)
            remember_interaction(query, res)
            agent_orchestrator.memory_agent.record_task_success(query, str(intent), res)
            log_activity(f"Agent {intent}: {res[:40]}")
            continue

        # Check Screen Access & Desktop Automation / File CRUD operations
        handled, res = execute_screen_vision_intent(intent, metadata, query)
        if handled:
            speak(res)
            remember_interaction(query, res)
            agent_orchestrator.memory_agent.record_task_success(query, str(intent), res)
            log_activity(f"Screen Vision {intent}: {res[:40]}")
            continue
        handled, res = execute_system_diagnostic_intent(intent)
        if handled:
            speak(res)
            remember_interaction(query, res)
            agent_orchestrator.memory_agent.record_task_success(query, str(intent), res)
            log_activity(f"Diagnostic {intent}: {res[:40]}")
            continue
        handled, res = execute_youtube_play_intent(intent, metadata)
        if handled:
            speak(res)
            agent_orchestrator.memory_agent.record_task_success(query, str(intent), res)
            continue
        handled, res = execute_youtube_search_intent(intent, metadata)
        if handled:
            speak(res)
            agent_orchestrator.memory_agent.record_task_success(query, str(intent), res)
            continue
        handled, res = execute_desktop_or_file_intent(intent, metadata, query)
        if handled:
            speak(res)
            remember_interaction(query, res)
            agent_orchestrator.memory_agent.record_task_success(query, str(intent), res)
            log_activity(f"Action {intent}: {res[:40]}")
            continue

        if 'wikipedia' in query:
            clean_q = query.replace("wikipedia", "").strip()
            safe_search_lookup(clean_q)

        elif any(query.startswith(p) for p in ['tell me about', 'information about', 'search about']):
            clean_q = re.sub(r'^(?:tell me about|information about|search about)\s*', '', query).strip()
            if clean_q:
                safe_search_lookup(clean_q)

        elif (query.startswith('who is ') or query.startswith('who was ')) and not any(k in query for k in ['your creator', 'your god', 'in front of the camera', 'at the camera']):
            clean_q = query.split('who is' if 'who is' in query else 'who was', 1)[1].strip()
            if clean_q:
                safe_search_lookup(clean_q)

        elif 'search' in query or 'find' in query:
            if 'youtube' in query:
                yt_term = query
                for prefix in [
                    "open youtube and search for", "open youtube and search", "open youtube and find",
                    "search on youtube for", "search in youtube for", "search youtube for",
                    "search on youtube", "search in youtube", "on youtube", "in youtube", "youtube"
                ]:
                    yt_term = re.sub(re.escape(prefix), "", yt_term, flags=re.IGNORECASE).strip()
                yt_term = yt_term.strip(" '\"")
                handled, res = execute_youtube_search_intent(IntentType.SYSTEM_YOUTUBE_SEARCH, {"query": yt_term or "trending"})
                speak(res)
            else:
                clean_q = query.split('search', 1)[1].strip() if 'search' in query else query.split('find', 1)[1].strip()
                safe_search_lookup(clean_q)

        elif 'weather' in query:
            city = ""
            match = re.search(r'weather (in|of|at)?\s*(.*)', query)
            if match and match.group(2):
                city = match.group(2).strip()

            if not city:
                speak("Would you like me to detect your location or do you want to tell the city?")
                choice = takeCommand().lower()

                if any(word in choice for word in ["detect", "auto", "current", "yes"]):
                    try:
                        ipinfo = requests.get("https://ipinfo.io").json()
                        city = ipinfo.get("city", "")
                        if city:
                            speak(f"Detected your location as {city}.")
                        else:
                            speak("Sorry, I couldn’t detect your location. Please tell me the city name.")
                            city = takeCommand().lower()
                    except Exception as e:
                        speak("Sorry, I couldn’t detect your location. Please tell me the city name.")
                        city = takeCommand().lower()
                else:
                    speak("Please tell me the location you want.")
                    city = takeCommand().lower()

            
            if city:
                speak(f"Detecting weather information for {city}, please wait...")
                weather_info = get_weather(city)
                print(weather_info)
                speak(weather_info)
                remember_interaction(query, weather_info)
            else:
                speak("Sorry, I couldn't understand the location you mentioned.")


        elif 'open' in query:
            app_name = query.split('open', 1)[1].strip()

            if app_name:
                speak(f"Sure Sir, I will try to open {app_name}.")
                
                was_opened = find_and_open(app_name)
                
                if not was_opened:
                    file_result = open_file_from_system(app_name)
                    if file_result.startswith("Opening "):
                        speak(file_result)
                        remember_interaction(query, file_result)
                        continue

                    is_photos_request = app_name.lower().strip() in {
                        "photo", "photos", "picture", "pictures",
                        "photo app", "pictures app",
                    }
                    if is_photos_request:
                        speak("I could not open the Photos app.")
                        continue

                    speak(f"Sorry sir! I couldn't find '{app_name}' on your system. I am trying another way...")
                    success = open_app_with_windows_search(app_name)
                    
                    if not success:
                        try:
                            search_url = f"https://www.{app_name.replace(' ', '')}.com"
                            webbrowser.open(search_url)
                            speak(f"Opening {app_name}")
                            remember_interaction(query, f"Opened website for {app_name}")
                        except Exception as e:
                            speak(f"Sorry, I couldn't find the application named {app_name}.")
            else:
                speak("Please specify the application you want to open.")

        elif "pause music" in query or "pause song" in query:
            pause_or_resume_media()

        elif "resume music" in query or "play music" in query:
            pause_or_resume_media()

        elif "next song" in query or "next track" in query:
            next_media()

        elif "previous song" in query or "previous track" in query:
            previous_media()

        elif "what is playing" in query or "what's playing" in query:
            status = detect_media_activity()
            speak(status)

        elif 'song' in query:
            song = query.replace('play', '').strip()
            if song:
                speak(f"Playing {song}")
                pywhatkit.playonyt(song)
                update_preference("last_played_song", song)
                if any(x in song for x in ["lofi", "romantic", "classical", "rock", "pop", "jazz"]):
                    update_preference("song_preferences", song)
                remember_interaction(query, f"Played {song}")
                log_activity(f"Played song: {song}")
            else:
                speak("Sorry Sir! Can you please repeat again?")

        elif 'music' in query:
            speak("Sure! From where do you want to play music? I can use YouTube, your local files, or open Spotify.")
            source = takeCommand().lower()

            if not source:
                speak("I didn't catch that. I'll use YouTube by default.")
                source = 'youtube'

            if 'youtube' in source:
                speak("What would you like me to play on YouTube?")
                yt_name = takeCommand().lower().strip()
                if "previous" in yt_name:
                    last = recall_preference("last_played_song")
                    if last:
                        speak(f"Sure sir! Playing your last song: {last}.")
                        try:
                            pywhatkit.playonyt(last)
                            log_activity(f"Played last preference on YouTube: {last}")
                        except Exception as e:
                            speak("Sorry, I couldn't play your last song on YouTube.")
                            print(f"YouTube play error (fallback): {e}")
                    else:
                        speak("I don't have a record of your last song. Please tell me what to play.")
                elif yt_name:
                    speak(f"Playing {yt_name} on YouTube.")
                    try:
                        pywhatkit.playonyt(yt_name)
                        update_preference("last_played_song", yt_name)
                        remember_interaction(query, f"Played {yt_name} on YouTube")
                        log_activity(f"Played on YouTube: {yt_name}")
                    except Exception as e:
                        speak("Sorry, I couldn't play that on YouTube.")
                        print(f"YouTube play error: {e}")
                else:
                    last = recall_preference("last_played_song")
                    if last:
                        speak(f"I couldn't hear the name. Playing your last song: {last}.")
                        try:
                            pywhatkit.playonyt(last)
                            log_activity(f"Played last preference on YouTube: {last}")
                        except Exception as e:
                            speak("Sorry, I couldn't play your last song on YouTube.")
                            print(f"YouTube play error (fallback): {e}")
                    else:
                        speak("I don't have a record of your last song. Please tell me what to play.")

            elif any(x in source for x in ['desktop', 'local', 'computer', 'file', 'folder']):
                speak("Looking for music on your computer. Please tell me the folder name or say 'music' to use your Music folder.")
                folder_input = takeCommand()
                base = os.path.expanduser("~")
                folder_path = resolve_folder(folder_input or 'music', base)

                if not os.path.exists(folder_path):
                    speak(f"Folder '{folder_path}' not found.")
                else:
                    songs = [f for f in os.listdir(folder_path) if f.lower().endswith(('.mp3', '.wav', '.m4a', '.flac'))]
                    if songs:
                        speak(f"Found {len(songs)} songs. Playing the first one.")
                        try:
                            os.startfile(os.path.join(folder_path, songs[0]))
                            update_preference("last_played_song", songs[0])
                            remember_interaction(query, f"Played local song {songs[0]}")
                            log_activity(f"Played local song: {songs[0]}")
                        except Exception as e:
                            speak("Sorry, I couldn't play that file.")
                            print(f"Local play error: {e}")
                    else:
                        speak("No audio files found in that folder.")

            elif 'spotify' in source:
                speak("I can't control Spotify directly yet. I can open Spotify for you.")
                find_and_open('spotify')

            else:
                speak("Sorry, I couldn't understand the source. Try saying 'YouTube', 'desktop', or 'Spotify'.")

        elif 'time' in query:
            strTime = datetime.datetime.now().strftime("%H:%M:%S")
            speak(f"Sir, the time is {strTime}")
            remember_interaction(query, strTime)

        elif 'close' in query:
            close_app = query.split('close', 1)[1].strip()
            
            if not close_app:
                speak("Please specify which application you would like to close.")

            elif any(v in close_app.lower() for v in ['visualisation', 'visualization', 'office', '3d', 'workspace', 'facility', 'popup']):
                handled, res = execute_agent_intent(IntentType.AGENT_OFFICE_CLOSE, {})
                speak(res)

            elif 'outlook' in close_app.lower():
                speak("Sure Sir, closing Outlook.")
                close_outlook()

            else:
                find_and_close_app(close_app)

        elif any(p in query for p in [
            "allow screen access", "grant screen access", "enable screen access",
            "take screen permission", "take the screen permission", "screen permission",
            "allow screen permission", "grant screen permission", "enable screen permission",
            "take background permission", "take the background permission", "take background work permission",
            "grant background permission", "grant background work permission",
            "allow background work", "enable background work", "background permission", "background work permission"
        ]):
            SCREEN_ACCESS_ALLOWED = True
            BACKGROUND_WORK_ALLOWED = True
            try:
                update_preference("screen_access_allowed", True)
                update_preference("background_work_allowed", True)
            except Exception:
                pass
            speak("Screen access and background work permissions have been granted, Sir.")

        elif any(p in query for p in ["stop screen access", "disable screen access", "revoke screen access", "revoke background", "disable background"]):
            SCREEN_ACCESS_ALLOWED = False
            BACKGROUND_WORK_ALLOWED = False
            try:
                update_preference("screen_access_allowed", False)
                update_preference("background_work_allowed", False)
            except Exception:
                pass
            speak("Screen access and background work permissions have been revoked, Sir.")

        elif any(phrase in query for phrase in [
            'who am i', 'who i am', 'tell me who i am', 'do you know who i am', 'do you know who am i'
        ]):
            identify_user_by_face()

        elif any(phrase in query for phrase in [
            'recognize face', 'recognize my face', 'face recognition', 'scan my face',
            'scan face', 'verify face', 'verify identity', 'verify my identity',
            'who is in front of the camera', 'who is at the camera', 'who is in camera',
            'look at me', 'scan my identity', 'identify me', 'identify face'
        ]):
            perform_face_recognition(show_window=True)

        elif 'camera' in query:
            speak("Sure Sir, accessing camera..")
            access_camera()

        elif 'picture' in query:
            speak ("Sure Sir, opening the image..")
            photo_dir1 = 'Libraries\\Camera Roll'
            try:
                photos = os.listdir(photo_dir1)
                os.startfile(os.path.join(photo_dir1, photos[0]))
                remember_interaction(query, f"Opened image {photos[0]}")
            except Exception:
                speak("Could not access pictures folder.")

        elif 'pictures' in query:
            speak ("Sure Sir, opening the image..")
            photo_dir = 'D:\\Pictures\\Photos'
            try:
                photos = os.listdir(photo_dir)
                os.startfile(os.path.join(photo_dir, photos[0]))
                remember_interaction(query, f"Opened image {photos[0]}")
            except Exception:
                speak("Could not access pictures folder.")

        elif 'volume up' in query:
            change_volume("up")

        elif 'volume down' in query:
            change_volume("down")

        elif 'mute volume' in query or 'mute' in query:
            change_volume("mute")

        elif 'unmute volume' in query or 'unmute' in query:
            change_volume("unmute")

        elif 'volume' in query:
            numbers = re.findall(r'\d+', query)
            if numbers:
                level = int(numbers[0])
                if 0 <= level <= 100:
                    set_volume(level)
                else:
                    speak("Please give me a number between 0 and 100.")
            else:
                speak("Can you please repeat with volume percentage?")
        
        elif 'brightness up' in query or 'increase brightness' in query:
            change_brightness("up")
        elif 'brightness down' in query or 'decrease brightness' in query:
            change_brightness("down")
        elif 'brightness' in query or 'brightness' in query:
            numbers = re.findall(r'\d+', query)
            if numbers:
                level = int(numbers[0])
                if 0 <= level <= 100:
                    set_brightness(level)
                else:
                    speak("Please give me a number between 0 and 100.")
            else:
                speak("Can you please repeat with brightness percentage?")
        
        elif 'take a note' in query or 'write a note' in query:
            take_note()
        
        elif 'note' in query:
            read_note_from_folder()

        elif 'reminder' in query:
            set_reminder()

        elif 'joke' in query or 'jokes' in query:
            joke = pyjokes.get_joke()
            speak(joke)
            remember_interaction(query, joke)
        
        elif 'clear memory' in query or 'reset memory' in query:
            memory_mgr.clear_all()
            speak("All stored memories and preferences have been cleared, Sir.")
            log_activity("Cleared memory by user command")

        elif 'clear conversation' in query or 'reset chat' in query:
            memory_mgr.clear_conversation_only()
            speak("Conversation session has been reset, Sir.")
            log_activity("Reset conversation session")

        elif 'what do you know' in query or 'my preferences' in query or 'show memory' in query:
            prof = memory_mgr.get_user_profile_prompt()
            speak("Here is what I remember about your profile and preferences, Sir.")
            print(prof)
        
        else:
            ask_neura(query)
