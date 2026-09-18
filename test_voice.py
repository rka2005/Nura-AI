import pyttsx3
import time

def speak(text):
    engine = pyttsx3.init("sapi5")

    voices = engine.getProperty("voices")
    engine.setProperty("voice", voices[1].id)
    engine.setProperty("rate", 150)
    engine.setProperty("volume", 1.0)

    engine.say(text)
    engine.runAndWait()
    engine.stop()


for i in range(5):
    print(i)
    speak(f"This is number {i}")
    time.sleep(1)