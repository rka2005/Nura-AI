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

CHAT_BRIDGE_FILE = "chat_bridge.json"
load_dotenv()
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

genai.configure(api_key = os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-2.0-flash')

engine = pyttsx3.init('sapi5')
voices = engine.getProperty('voices')
engine.setProperty('voice', voices[1].id)
engine.setProperty('rate', 180)

MEMORY_FILE = "neura_memory.json"

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

        with open(CHAT_BRIDGE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    except Exception as e:
        print("Chat bridge error:", e)

def load_memory():
    """Load or initialize memory structure."""
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Ensure required keys exist
                data.setdefault("preferences", {})
                data.setdefault("interaction_history", [])
                data.setdefault("activity_log", [])
                data.setdefault("llm_history", [])
                return data
        except json.JSONDecodeError:
            # If file corrupted, reset
            pass
    # default structure
    return {
        "preferences": {},
        "interaction_history": [],
        "activity_log": [],
        "llm_history": []
    }

def save_memory(mem):
    """Write memory dict to disk."""
    try:
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(mem, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"[Memory save error]: {e}")

memory = load_memory()

def llm_history_to_pairs():
    pairs = []
    for msg in memory.get("llm_history", []):
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "user":
            pairs.append(("user", content))
        else:
            pairs.append(("bot", content))
    return pairs

def append_llm_history(role, content):
    memory["llm_history"].append({"role": role, "content": content})
    save_memory(memory)
def remember_interaction(user_input, neura_response):
    memory["interaction_history"].append({
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "user": user_input,
        "neura": neura_response
    })
    save_memory(memory)

def update_preference(key, value):
    # If value is list-like or multiple preferences, store as list
    prev = memory["preferences"].get(key)
    if prev:
        # Avoid duplicates for simple strings
        if isinstance(prev, list):
            if value not in prev:
                prev.append(value)
                memory["preferences"][key] = prev
        else:
            if prev != value:
                memory["preferences"][key] = value
    else:
        # If key likely to be multiple (like song_preferences), prefer list
        if key.endswith("_preferences") or key.endswith("songs"):
            memory["preferences"][key] = [value]
        else:
            memory["preferences"][key] = value
    save_memory(memory)

def log_activity(action):
    memory["activity_log"].append({
        "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "action": action
    })
    save_memory(memory)

def recall_preference(key, default=None):
    return memory["preferences"].get(key, default)

def analyze_memory_on_start():
    """Run light analysis on startup and optionally speak summary."""
    prefs = memory.get("preferences", {})
    interactions = memory.get("interaction_history", [])
    if prefs:
        print("🔁 Loaded preferences:")
        for k, v in prefs.items():
            print(f"  - {k}: {v}")
    if interactions:
        print(f"🗂️  Interaction history length: {len(interactions)}")
        last = interactions[-1]
        print(f"  Last: {last.get('timestamp')} | user: {last.get('user')}")


def speak(audio):
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
    prompt: user string
    chat_history_pairs: list of tuples [("user", "..."), ("bot","..."), ...]
    Returns: (reply_text, updated_chat_history_pairs)
    """
    if chat_history_pairs is None:
        chat_history_pairs = llm_history_to_pairs()

    try:
        # ✅ Try Gemini first
        control_instruction = (
            "Answer clearly and concisely based only on the question asked. "
            "Avoid any extra explanation or details not explicitly requested. "
            "If clarification is needed, ask the user."
        )
        full_prompt = f"{control_instruction}\n\nUser: {prompt}"

        # Ensure chat history works for Gemini
        chat = model.start_chat(history=chat_history_pairs)
        response = chat.send_message(full_prompt)

        # Check if Gemini gave a valid response
        if not response.text or response.text.strip() == "" or "error" in response.text.lower():
            raise ValueError("Gemini response invalid")

        chat_history_pairs.append(("user", prompt))
        chat_history_pairs.append(("bot", response.text))
        append_llm_history("user", prompt)
        append_llm_history("assistant", response.text)
        return response.text, chat_history_pairs

    except Exception as e:
        print(f"[Gemini failed: {e}] ⚡ Switching to Groq...")

        # ✅ Fallback to Groq
        try:
            messages = []
            for role, content in chat_history_pairs:
                messages.append({
                    "role": "user" if role == "user" else "assistant",
                    "content": content
                })

            messages.append({"role": "user", "content": prompt})

            response = groq_client.chat.completions.create(
                model="llama3-70b-8192",
                messages=messages,
                temperature=0.7,
            )

            reply = response.choices[0].message.content

            chat_history_pairs.append(("user", prompt))
            chat_history_pairs.append(("bot", reply))
            append_llm_history("user", prompt)
            append_llm_history("assistant", reply)

            return reply, chat_history_pairs

        except Exception as e2:
            return f"Both Gemini and Groq failed: {e2}", chat_history_pairs


def ask_neura(user_message):
    """
    Handles conversational queries and memory updates.
    """

    user_message = user_message.lower()

    if not user_message:
        return
    
     # Greeting and wellbeing
    if any(phrase in user_message for phrase in ["how are you", "how do you do"]):
        response = "I am fine. How can I assist you?"
    elif any(greet in user_message.split() for greet in ["hello", "hi"]):
        response = "Hello Sir! It's good to hear from you."
    elif "who are you" in user_message:
        response = "I am Neura, your personal AI assistant."
    elif "what can you do" in user_message:
        response = "I can help you with various tasks like answering questions, managing files, setting reminders, and more."
    elif "your name" in user_message:
        response = "My name is Neura. I was created to help you."
    elif "rohit adak" in user_message:
        response = "He is my creator! a brilliant mind who brought me to life! I am lucky to assist him."
    elif "thank you" in user_message or "thanks" in user_message:
        response = "You're welcome, Sir!"
    elif "time" in user_message:
        current_time = datetime.datetime.now().strftime("%H:%M:%S")
        response = f"The time is {current_time}"
    elif re.search(r"\bi like\b", user_message) or re.search(r"\bi prefer\b", user_message):
        m = re.search(r"i like (.+)", user_message) or re.search(r"i prefer (.+)", user_message)
        if m:
            pref_text = m.group(1).strip()
            if any(word in pref_text for word in ["music", "song", "songs", "genre", "rock", "lofi", "pop", "romantic", "classical"]):
                existing = memory["preferences"].get("song_preferences", [])
                if isinstance(existing, list):
                    if pref_text not in existing:
                        existing.append(pref_text)
                        memory["preferences"]["song_preferences"] = existing
                else:
                    memory["preferences"]["song_preferences"] = [existing, pref_text] if existing else [pref_text]
                save_memory(memory)
                response = f"Got it — I've noted you like {pref_text} music."
            else:
                update_preference_key = "general_likes"
                existing = memory["preferences"].get(update_preference_key, [])
                if isinstance(existing, list):
                    if pref_text not in existing:
                        existing.append(pref_text)
                        memory["preferences"][update_preference_key] = existing
                else:
                    memory["preferences"][update_preference_key] = [pref_text]
                save_memory(memory)
                response = f"Noted that you like {pref_text}."
        else:
            response = "Tell me what you like, Sir."
    else:
        speak("Let me think...")
        response, _ = chat_with_ai(user_message)
        print("Nura:", response)

    remember_interaction(user_message, response)
    log_activity(f"Handled query: {user_message}")

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

def change_volume(action):
    devices = AudioUtilities.GetSpeakers()
    interface = devices.Activate(
        IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    volume = cast(interface, POINTER(IAudioEndpointVolume))

    current_volume = volume.GetMasterVolumeLevelScalar()

    if action == "up":
        volume.SetMasterVolumeLevelScalar(min(current_volume + 0.1, 1.0), None)
        speak("Volume increased")
    elif action == "down":
        volume.SetMasterVolumeLevelScalar(max(current_volume - 0.1, 0.0), None)
        speak("Volume decreased")
    elif action == "mute":
        volume.SetMute(1, None)
        speak("Volume muted")
    elif action == "unmute":
        volume.SetMute(0, None)
        speak("Volume unmuted")

def set_volume(level):
    """
    Set volume to a specific percentage (0–100).
    """
    try:
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(
            IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = cast(interface, POINTER(IAudioEndpointVolume))

        # Convert percentage to scalar (0.0 – 1.0)
        scalar = max(0.0, min(level / 100.0, 1.0))
        volume.SetMasterVolumeLevelScalar(scalar, None)

        speak(f"Volume set to {level} percent")
    except Exception as e:
        print(f"Error setting volume: {e}")
        speak("Sorry sir, I could not set the volume.")

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

    pref_city = recall_preference("weather_city")
    pref_songs = memory["preferences"].get("song_preferences")
    if pref_city:
        speak(f"I remember your preferred weather city is {pref_city}.")
    if pref_songs:
        if isinstance(pref_songs, list):
            speak(f"You've told me you like {', '.join(pref_songs[:3])}.")
        else:
            speak(f"You've told me you like {pref_songs} music.")

    reminder_thread = threading.Thread(target=check_reminders, daemon=True)
    reminder_thread.start()

    while True:
        query = takeCommand()

        if 'good bye' in query or 'goodbye' in query or 'exit' in query or 'bye' in query or "quit" in query or "good night" in query:
            speak("Goodbye Sir!")
            break
        
        elif 'wikipedia' in query:
            speak('Searching Wikipedia....')
            query = query.replace("wikipedia", "").strip()
            try:
                results = wikipedia.summary(query, sentences=3)
                speak("According to Wikipedia")
                print(results)
                speak(results)
                remember_interaction(query, results)
                log_activity(f"Wikipedia search: {query}")
            except wikipedia.exceptions.WikipediaException as e:
                speak("Sorry, I couldn't find any information.")
                print(f"An error occurred: {e}")
                remember_interaction(query, "wikipedia search failed")

        elif 'about' in query:
            search_query = query.split('about', 1)[1].strip()
            speak("Sure sir! Please let me find!")
            try:
                results = wikipedia.summary(search_query, sentences=3)
                print(results)
                speak(results)
                remember_interaction(query, results)
            except wikipedia.exceptions.WikipediaException as e:
                speak("Sorry, I couldn't find any information.")
                print(f"An error occurred: {e}")
                remember_interaction(query, "about search failed")

        elif 'who is' in query:
            search_query = query.split('who is', 1)[1].strip()
            speak("Sir! ")
            try:
                results = wikipedia.summary(search_query, sentences=3)
                print(results)
                speak(results)
                remember_interaction(query, results)
            except wikipedia.exceptions.WikipediaException as e:
                speak("Sorry, I couldn't find any information.")
                print(f"An error occurred: {e}")
                remember_interaction(query, "who is search failed")

        elif 'search' in query or 'find' in query:
            search_query = query.split('search', 1)[1].strip() if 'search' in query else query.split('find', 1)[1].strip()
            speak("Sure sir!")
            if search_query:
                search_url = "https://www.google.com/search?q=" + '+'.join(search_query)
                speak("Here are the search results for " + search_query)
                webbrowser.open(search_url)
                remember_interaction(query, f"Opened google search for {search_query}")
                log_activity(f"Search: {search_query}")
            else:
                speak("Sorry, I didn't catch the search query.")

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
            memory.clear()
            memory.update({
                "preferences": {},
                "interaction_history": [],
                "activity_log": [],
                "llm_history": []
            })
            save_memory(memory)
            speak("All stored memories have been cleared, Sir.")
            log_activity("Cleared memory by user command")
        
        else:
            ask_neura(query)
