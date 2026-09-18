import pyttsx3
import speech_recognition as sr
import datetime
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
from art import text2art

from memory.memory_manager import MemoryManager
from brain.conversation import generate_ai_response
from brain.personality import IDENTITY, get_personality_prompt
from brain.intent_router import route_intent, IntentType
from brain.desktop_controller import DesktopController
from brain.file_manager import FileManager

CHAT_BRIDGE_FILE = "chat_bridge.json"
load_dotenv()
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

genai.configure(api_key = os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-2.0-flash')

# 3-Tier Memory Manager
memory_mgr = MemoryManager()
memory = memory_mgr.user_memory  # Reference for backward compatibility

# Desktop Automation & File CRUD Controllers
SCREEN_ACCESS_ALLOWED = True
desktop_ctrl = DesktopController()
file_mgr = FileManager()

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

    except Exception as e:
        print("Chat bridge error:", e)

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


def speak(audio):
    engine = pyttsx3.init('sapi5')
    voices = engine.getProperty('voices')
    engine.setProperty('voice', voices[1].id)
    engine.setProperty('rate', 180)

    send_to_frontend("neura", audio)
    engine.say(audio)
    engine.runAndWait()


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
    global SCREEN_ACCESS_ALLOWED

    rq = raw_query.lower()
    if any(p in rq for p in ["allow screen access", "grant screen access", "enable screen access"]):
        SCREEN_ACCESS_ALLOWED = True
        return True, "Screen access permission has been granted, Sir."

    if any(p in rq for p in ["stop screen access", "disable screen access", "revoke screen access"]):
        SCREEN_ACCESS_ALLOWED = False
        return True, "Screen access permission has been revoked, Sir."

    if not SCREEN_ACCESS_ALLOWED and intent in [
        IntentType.DESKTOP_SEARCH_IN_TAB, IntentType.DESKTOP_FIRST_LINK, 
        IntentType.DESKTOP_TYPE, IntentType.DESKTOP_HOTKEY, IntentType.DESKTOP_SCREENSHOT
    ]:
        return True, "Screen access is currently disabled. Say 'allow screen access' to enable it."

    if intent == IntentType.DESKTOP_SEARCH_IN_TAB:
        q = metadata.get("query", "")
        res = desktop_ctrl.search_in_active_window(q)
        return True, res

    elif intent == IntentType.DESKTOP_FIRST_LINK:
        res = desktop_ctrl.open_first_search_result()
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
            return True, f"Screenshot captured and saved at {path_or_err}, Sir."
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

def ask_neura(user_message):
    """
    Handles conversational queries, memory retrieval, web lookup, and selective LLM fallback.
    Avoids API calls whenever queries can be answered by memory, smalltalk, or Google search.
    """
    user_message_clean = user_message.strip()
    if not user_message_clean:
        return ""

    # Check Desktop Automation or File CRUD first (Zero API Call)
    intent, metadata = route_intent(user_message_clean)
    handled, res = execute_desktop_or_file_intent(intent, metadata, user_message_clean)
    if handled:
        speak(res)
        remember_interaction(user_message_clean, res)
        log_activity(f"Action {intent}: {res[:40]}")
        return res

    um_lower = user_message_clean.lower()

    # 1. Direct Memory Retrieval (Zero API Call)
    mem_reply = memory_mgr.answer_from_memory(user_message_clean)
    if mem_reply:
        speak(mem_reply)
        remember_interaction(user_message_clean, mem_reply)
        log_activity(f"Answered from memory: {user_message_clean[:40]}")
        return mem_reply

    # 2. Instant Fixed Identity & Conversational Status (Zero API Call)
    if any(phrase in um_lower for phrase in ["how are you", "how do you do"]):
        response = "I am doing well, Sir. How can I assist you today?"
    elif any(greet in um_lower.split() for greet in ["hello", "hi", "hey"]):
        response = "Hello Sir! It's good to hear from you."
    elif any(phrase in um_lower for phrase in ["what are you doing", "what r u doing", "what are you doing now"]):
        response = "I am standing by and monitoring your system, Sir. How can I help you?"
    elif "who are you" in um_lower or "your name" in um_lower:
        response = f"I am {IDENTITY['name']}, your personal AI assistant and desktop companion."
    elif "what can you do" in um_lower:
        response = "I can help you manage your computer, launch apps, write notes, monitor systems, and look up information."
    elif "rohit adak" in um_lower:
        response = "He is my creator! A brilliant mind who brought me to life. I am honored to assist him."
    elif "who is your god" in um_lower:
        response = "Sri Rohit Kumar Adak is my creator. He brought me to life."
    elif "thank you" in um_lower or "thanks" in um_lower:
        response = "You're welcome, Sir!"
    elif "time" in um_lower:
        current_time = datetime.datetime.now().strftime("%H:%M:%S")
        response = f"The time is {current_time}"
    else:
        # 3. Check automatic preference and mood learning
        learned = memory_mgr.auto_learn(user_message_clean)
        user_name = memory_mgr.user_memory.get("user_facts", {}).get("name")
        honorific = user_name if user_name else "Sir"

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
            # 4. Search & Web Lookup First (Zero API Call for search queries and entity lookups)
            is_search_query = any(k in um_lower for k in [
                "search", "find", "who is", "who was", "which", "tell me about", "what is", "where is", "google"
            ]) or (len(user_message_clean.split()) <= 4 and not any(k in um_lower for k in [
                "explain", "code", "write", "generate", "create", "why", "how do", "how to"
            ]))

            # Complex generative or reasoning queries that actually require LLM intelligence
            requires_llm = any(k in um_lower for k in [
                "explain", "code", "write", "debug", "how to", "how can i", "why is", "why does", "solve", "compare", "translate", "summarize", "advice", "opinion", "think about"
            ])

            if is_search_query and not requires_llm:
                # Clean query term
                clean_term = user_message_clean
                for prefix in [
                    "can you tell me which", "can you tell me who is", "can you tell me what is", 
                    "tell me which", "tell me who is", "tell me about", "search for", "search", 
                    "find", "who is", "who was", "which", "what is", "where is", "google"
                ]:
                    if clean_term.lower().startswith(prefix):
                        clean_term = clean_term[len(prefix):].strip()
                        break

                if not clean_term:
                    clean_term = user_message_clean

                response = safe_search_lookup(clean_term)
                return response

            else:
                # 5. Fallback to Brain LLM only for actual reasoning / generative queries
                speak("Let me think...")
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


def takeCommand():
    r = sr.Recognizer()
    with sr.Microphone(device_index=1) as source:
        print("Listening...")
        r.adjust_for_ambient_noise(source)
        try:
            audio = r.listen(source, timeout=4)
            print("Recognizing...")
            query = r.recognize_google(audio, language='en-in')
            print(f"User said: {query}")
            send_to_frontend("user", query)
            return query.lower()
        except sr.UnknownValueError:
            print("Sorry, I couldn't understand what you said. Please try again.")
            return ""
        except sr.RequestError as e:
            print(f"Could not request results; {e}")
            return ""
        except Exception as e:
            print(f"An error occurred: {e}")
            return ""

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


def access_camera():
    global SCREEN_ACCESS_ALLOWED

    if not SCREEN_ACCESS_ALLOWED:
        speak("Screen access is disabled. Please say allow screen access first.")
        return

    camera = cv2.VideoCapture(0)

    while True:
        ret, frame = camera.read()

        cv2.imshow('Camera Feed', frame)

        command = takeCommand()

        if 'capture' in command:
            image_name = "captured_image.jpg"
            cv2.imwrite(image_name, frame)
            speak("Image captured successfully.")
            break
        elif 'exit camera' in command:
            break

    # Release the camera
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
        sessions = AudioUtilities.GetAllSessions()
        for session in sessions:
            if session.State == 1:  # Active
                if session.Process:
                    return f"Media is playing from {session.Process.name()}"
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

    reminder_thread = threading.Thread(target=check_reminders, daemon=True)
    reminder_thread.start()

    while True:
        query = takeCommand()

        if 'good bye' in query or 'goodbye' in query or 'exit' in query or 'bye' in query or "quit" in query or "good night" in query:
            speak("Goodbye Sir!")
            break

        # Check Screen Access & Desktop Automation / File CRUD operations first
        intent, metadata = route_intent(query)
        handled, res = execute_desktop_or_file_intent(intent, metadata, query)
        if handled:
            speak(res)
            remember_interaction(query, res)
            log_activity(f"Action {intent}: {res[:40]}")
            continue

        if 'wikipedia' in query:
            clean_q = query.replace("wikipedia", "").strip()
            safe_search_lookup(clean_q)

        elif 'about' in query:
            clean_q = query.split('about', 1)[1].strip()
            safe_search_lookup(clean_q)

        elif 'who is' in query:
            clean_q = query.split('who is', 1)[1].strip()
            safe_search_lookup(clean_q)

        elif 'search' in query or 'find' in query:
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
            
            if not app_name:
                speak("Please specify which application you would like to close.")

            elif 'outlook' in close_app:
                speak("Sure Sir, closing Outlook.")
                close_outlook()

            else:
                find_and_close_app(close_app)

        elif "allow screen access" in query:
            SCREEN_ACCESS_ALLOWED = True
            speak("Screen access permission granted, Sir.")

        elif "stop screen access" in query or "disable screen access" in query:
            SCREEN_ACCESS_ALLOWED = False
            speak("Screen access permission revoked, Sir.")

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
