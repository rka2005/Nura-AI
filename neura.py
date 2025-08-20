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

genai.configure(api_key = os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-2.5-flash')

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

def chat_with_gemini(prompt, chat_history=[]):
    try:
        # Build a controlled prompt to enforce concise and focused replies
        control_instruction = (
            "Answer clearly and concisely based only on the question asked. "
            "Avoid any extra explanation or details not explicitly requested. "
            "If clarification is needed, ask the user."
        )
        full_prompt = f"{control_instruction}\n\nUser: {prompt}"
        # Ensure chat history is a list of (user, bot) messages
        chat = model.start_chat(history=chat_history)
        response = chat.send_message(full_prompt)
        chat_history.append(("user", prompt))
        chat_history.append(("bot", response.text))
        return response.text, chat_history
    except Exception as e:
        return f"Error: {e}", chat_history

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
    elif "thank you" in user_message or "Thanks" in user_message:
        response = "You're welcome, Sir!"
    elif "time" in user_message:
        current_time = datetime.datetime.now().strftime("%H:%M:%S")
        response = f"The time is {current_time}"
    else:
        speak("Let me think...")
        response, chat_history = chat_with_gemini(user_message, chat_history)
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
        r.adjust_for_ambient_noise(source)  # Adjust for ambient noise
        try:
            audio = r.listen(source, timeout=4)  # Set a timeout of 5 seconds
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

if __name__ == "__main__":
    wishMe()
    wishtime()
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

        elif 'tell' in query:
            search_query = query.split('tell', 1)[1].strip()
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

        elif 'music' in query or 'song' in query:
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
        
        else:
            ask_neura(query)
