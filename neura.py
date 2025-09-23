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

load_dotenv()
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

genai.configure(api_key = os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-2.0-flash')

engine = pyttsx3.init('sapi5')
voices = engine.getProperty('voices')
engine.setProperty('voice', voices[1].id)
chat_history = []


def speak(audio):
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

def chat_with_ai(prompt, chat_history=[]):
    try:
        # ✅ Try Gemini first
        control_instruction = (
            "Answer clearly and concisely based only on the question asked. "
            "Avoid any extra explanation or details not explicitly requested. "
            "If clarification is needed, ask the user."
        )
        full_prompt = f"{control_instruction}\n\nUser: {prompt}"

        # Ensure chat history works for Gemini
        chat = model.start_chat(history=chat_history)
        response = chat.send_message(full_prompt)

        # Check if Gemini gave a valid response
        if not response.text or response.text.strip() == "" or "error" in response.text.lower():
            raise ValueError("Gemini response invalid")

        chat_history.append(("user", prompt))
        chat_history.append(("bot", response.text))
        return response.text, chat_history

    except Exception as e:
        print(f"[Gemini failed: {e}] ⚡ Switching to Groq...")

        # ✅ Fallback to Groq
        try:
            messages = []
            for role, content in chat_history:
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

            chat_history.append(("user", prompt))
            chat_history.append(("bot", reply))

            return reply, chat_history

        except Exception as e2:
            return f"Both Gemini and Groq failed: {e2}", chat_history


def ask_neura(user_message):
    global chat_history
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
    elif "your name" in user_message:
        response = "My name is Neura. I was created to help you."
    elif "rohit" in user_message:
        response = "He is my creator! a brilliant mind who brought me to life! I am lucky to assist him."
    elif "thank you" in user_message or "thanks" in user_message:
        response = "You're welcome, Sir!"
    elif "time" in user_message:
        current_time = datetime.datetime.now().strftime("%H:%M:%S")
        response = f"The time is {current_time}"
    else:
        speak("Let me think...")
        response, chat_history = chat_with_ai(user_message, chat_history)
        print("Nura:",response)

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

def close_app(app_name):
    app_processes = {
        'whatsapp': 'whatsapp.exe',
        'word': 'WINWORD.EXE',
        'excel': 'EXCEL.EXE',
        'powerpoint': 'POWERPNT.EXE',
    }
    if app_name.lower() in app_processes:
        process_name = app_processes[app_name.lower()]
        os.system(f"taskkill /f /im {process_name}")
        print(f"{app_name.capitalize()} closed successfully.")
    else:
        print(f"Sorry, could not find a process to close for {app_name}.")


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
            # No match, use folder_input as subfolder of base_path
            return os.path.join(base_path, folder_input)

    # Otherwise, treat as full path
    return folder_input


def find_folder(base_path, spoken_name):
    """
    Searches for a folder in base_path that matches spoken_name using normalized comparison.
    Returns full path if found, else None.
    """
    spoken_norm = re.sub(r'[^a-z0-9]', '', spoken_name.lower())  # remove special chars and lowercase

    # List all folders in base_path
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
        speak("I found multiple folders matching your request. Please choose one:")
        for i, f in enumerate(matches, 1):
            speak(f"{i}. {f}")
        choice = takeCommand()
        numbers = re.findall(r'\d+', choice)
        if numbers:
            index = int(numbers[0]) - 1
            if 0 <= index < len(matches):
                return os.path.join(base_path, matches[index])
        # fallback
        return os.path.join(base_path, matches[0])
    else:
        # No matches
        return None


def access_camera():
    # Open the default camera (index 0)
    camera = cv2.VideoCapture(0)

    while True:
        # Capture frame-by-frame
        ret, frame = camera.read()

        # Display the resulting frame
        cv2.imshow('Camera Feed', frame)

        # Listen for voice command
        command = takeCommand()

        # Process voice command
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

if __name__ == "__main__":
    wishMe()
    wishtime()

    reminder_thread = threading.Thread(target=check_reminders, daemon=True)
    reminder_thread.start()

    while True:
        query = takeCommand()

        if 'good bye' in query or 'goodbye' in query or 'exit' in query or 'bye' in query or "quit" in query or "good night" in query:
            speak("Goodbye Sir!")
            break

        # Logic for executing tasks based on query
        elif 'wikipedia' in query:
            speak('Searching Wikipedia....')
            query = query.replace("wikipedia", "")
            try:
                results = wikipedia.summary(query, sentences=3)
                speak("According to Wikipedia")
                print(results)
                speak(results)
            except wikipedia.exceptions.WikipediaException as e:
                speak("Sorry, I couldn't find any information.")
                print(f"An error occurred: {e}")

        elif 'open youtube' in query:
            speak("Opening YouTube..")
            webbrowser.open("https://www.youtube.com")

        elif 'open google' in query:
            speak("Opening Google..")
            webbrowser.open("https://www.google.com")

        elif 'about' in query:
            search_query = query.split('about', 1)[1].strip()
            speak("Sure sir! Please let me find!")
            try:
                results = wikipedia.summary(search_query, sentences=3)
                print(results)
                speak(results)
            except wikipedia.exceptions.WikipediaException as e:
                speak("Sorry, I couldn't find any information.")
                print(f"An error occurred: {e}")

        elif 'search' in query or 'find' in query:
            search_query = query.split('search', 1)[1].strip() if 'search' in query else query.split('find', 1)[1].strip()
            speak("Sure sir!")
            if search_query:
                search_url = "https://www.google.com/search?q=" + '+'.join(search_query)
                speak("Here are the search results for " + search_query)
                webbrowser.open(search_url)
            else:
                speak("Sorry, I didn't catch the search query.")

        elif 'open' in query:
            app_name = query.split('open', 1)[1].strip()
            if app_name:
                speak(f"Opening {app_name}..")
                try:
                    search_url = f"https://www.{app_name.replace(' ', '')}.com"
                    webbrowser.open(search_url)
                except FileNotFoundError:
                    speak(f"Sorry, I couldn't find the application named {app_name}.")
            else:
                speak("Please specify the application you want to open.")

        elif 'open gmail' in query:
            speak("Opening Gmail..")
            webbrowser.open("https://mail.google.com")

        elif 'open stackoverflow' in query:
            speak("Opening stackoverflow..")
            webbrowser.open("https://stackoverflow.com")

        elif 'play' in query:
            song = query.replace('play', '').strip()
            if song:
                speak(f"Playing {song}")
                pywhatkit.playonyt(song)
            else:
                speak("Sorry Sir! Can you please repeat again?")

        elif 'play a music' in query or 'song' in query:
            speak("Sure! From where do you want to play music?")
            source = takeCommand().lower()
            if'YouTube' or 'youtube' in source:
                speak("Sure! Please tell me what you want to play?")
                yt_name = takeCommand()
                if yt_name:
                    speak(f"Playing {yt_name} on YouTube.")
                    pywhatkit.playonyt(yt_name)
                else:
                    speak("Sorry, I didn't catch the name.")

            elif 'desktop' in source:
                music_dir = 'D:\\Music'
                songs = os.listdir(music_dir)
                print(songs)
                os.startfile(os.path.join(music_dir, songs[1]))
            
            else: 
                speak("Sorry sir, I cannot understand.")
                continue

        elif 'time' in query:
            strTime = datetime.datetime.now().strftime("%H:%M:%S")
            speak(f"Sir, the time is {strTime}")

        elif 'open code' in query:
            codePath = "C:\\Users\\Admin\\AppData\\Local\\Programs\\Microsoft VS Code\\Code.exe"
            os.startfile(codePath)

        elif 'open whatsapp' in query:
            speak("Opening whatsapp..")
            whatsapp_dir = "C:\\Users\\rohit\\Desktop\\whatsapp"
            os.startfile(whatsapp_dir)

        elif 'close whatsapp' in query:
            speak("Sure Sir..")
            close_app('whatsapp')

        elif 'open word' in query:
            speak("Opening word..")
            word_dir = "C:\\Users\\rohit\\Desktop\\Computer\\word"
            os.startfile(word_dir)

        elif 'close word' in query:
            speak("Sure Sir..")
            close_app('word')

        elif 'open excel' in query:
            speak("Opening excel..")
            excel_dir = "C:\\Users\\rohit\\Desktop\\Computer\\Excel"
            os.startfile(excel_dir)

        elif 'close excel' in query:
            speak("Sure Sir..")
            close_app('excel')

        elif 'open powerpoint' in query:
            speak("Opening power point..")
            PowerPoint_dir = "C:\\Users\\rohit\\Desktop\\Computer\\PowerPoint"
            os.startfile(PowerPoint_dir)

        elif 'close powerpoint' in query:
            speak("Sure Sir..")
            close_app('powerpoint')

        elif 'open outlook' in query:
            speak("Opening outlook..")
            mail_dir = "C:\\Users\\rohit\\Desktop\\Computer\\Mail"
            os.startfile(mail_dir)

        elif 'close outlook' in query:
            speak("Sure Sir..")
            close_outlook()

        elif 'camera' in query:
            speak("Sure Sir, accessing camera..")
            access_camera()

        elif 'picture' in query:
            speak ("Sure Sir, opening the image..")
            photo_dir1 = 'Libraries\\Camera Roll'
            photos = os.listdir(photo_dir1)
            os.startfile(os.path.join(photo_dir1, photos[0]))

        elif 'pictures' in query:
            speak ("Sure Sir, opening the image..")
            photo_dir = 'D:\\Pictures\\Photos'
            photos = os.listdir(photo_dir)
            os.startfile(os.path.join(photo_dir, photos[0]))

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

        else:
            ask_neura(query)
