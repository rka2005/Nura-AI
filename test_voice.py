
import asyncio
import base64
import json
import os
import tempfile
import time

import websockets
import pygame
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("SARVAM_API_KEY")

URI = (
    "wss://api.sarvam.ai/text-to-speech/ws"
    "?model=bulbul:v4-flash&send_completion_event=true"
)


async def generate_speech(text):
    if not API_KEY:
        raise RuntimeError(
            "SARVAM_API_KEY not found. Check your .env file."
        )

    audio_chunks = []

    print("[1/3] Connecting to Sarvam AI...")

    async with websockets.connect(
        URI,
        additional_headers={
            "Api-Subscription-Key": API_KEY
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
            "data": {
                "text": text
            },
        }))

        await ws.send(json.dumps({
            "type": "flush"
        }))

        print("[2/3] Generating voice...")

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
        raise RuntimeError(
            "No audio received from Sarvam AI."
        )

    return b"".join(audio_chunks)


def play_audio(audio_bytes):
    audio_path = None

    try:
        # Save the response using the MP3 format shown
        # in Sarvam's example.
        with tempfile.NamedTemporaryFile(
            suffix=".mp3",
            delete=False,
        ) as audio_file:
            audio_path = audio_file.name
            audio_file.write(audio_bytes)

        print("[3/3] Playing generated voice...")

        pygame.mixer.init()
        pygame.mixer.music.load(audio_path)
        pygame.mixer.music.play()

        while pygame.mixer.music.get_busy():
            time.sleep(0.1)

        print("Voice test completed successfully!")

    finally:
        if pygame.mixer.get_init():
            pygame.mixer.music.stop()
            pygame.mixer.quit()

        if audio_path and os.path.exists(audio_path):
            try:
                os.remove(audio_path)
            except OSError:
                print(f"Temporary audio remains at: {audio_path}")


async def main():
    text = (
        "Hello! I am Neura, your personal AI assistant. "
        "My voice is powered by Sarvam AI. "
        "I am ready to help you. "
        "This is a test of my voice generation system."
    )

    try:
        audio_bytes = await generate_speech(text)
        play_audio(audio_bytes)

    except Exception as error:
        print("\nVOICE TEST FAILED")
        print(f"Error: {type(error).__name__}: {error}")


if __name__ == "__main__":
    asyncio.run(main())