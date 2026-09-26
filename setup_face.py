"""
Neura Vision - Multi-Face Enrollment & Auto-Learning System (setup_face.py)
Supports:
  1. Image Folder Batch Enrollment: Reads all images in a folder; uses filenames as names.
  2. Single Image Enrollment: Reads an image; uses filename or specified name.
  3. Interactive Camera Enrollment: Step-by-step guidance for enrolling any person.
  4. Live Auto-Learning: Watches camera feed. When an unknown person appears, directly asks:
     "Please tell me your name", captures photos internally, and enrolls them automatically!
  5. List & Delete: Manage registered faces in vision/known_faces.json.

Usage:
  python setup_face.py --folder "images/"            # Batch enroll from folder
  python setup_face.py --image "sneha.jpg"           # Enroll single image (name: Sneha)
  python setup_face.py --image "pic.jpg" --name "Roy"# Enroll with custom name
  python setup_face.py --camera --name "Alex"        # Guided webcam enrollment
  python setup_face.py --auto                        # Live camera auto-learn & recognize
  python setup_face.py --list                        # Show all registered faces
  python setup_face.py --delete "Alex"               # Remove registered face
"""

import os
import sys
import time
import re
import argparse
import threading
from typing import Optional, Dict, List, Any, Tuple
import cv2
import numpy as np

# Configure console encoding safely for Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Ensure root workspace is in sys.path
WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))
if WORKSPACE_DIR not in sys.path:
    sys.path.insert(0, WORKSPACE_DIR)

from vision.face_recognition import (
    FaceRecognitionSystem,
    get_face_system,
    DEFAULT_KNOWN_FACES_PATH,
    DEFAULT_PROFILE_PATH,
    clean_extracted_name,
    is_refusal_response,
    get_next_anonymous_name
)
from memory.memory_manager import MemoryManager

# Optional speech recognition and Windows SAPI TTS
try:
    import speech_recognition as sr
    HAS_SR = True
except ImportError:
    HAS_SR = False

try:
    import win32com.client
    import pythoncom
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False


# -------------------------------------------------------------
# SPEECH & VOICE UTILITIES
# -------------------------------------------------------------

def speak(text: str):
    """Speaks text using native Windows SAPI in a separate thread."""
    print(f"\n[Neura Vision Voice]: \"{text}\"")

    def _worker():
        if HAS_WIN32:
            try:
                pythoncom.CoInitialize()
                speaker = win32com.client.Dispatch("SAPI.SpVoice")
                speaker.Rate = 1
                speaker.Speak(text)
            except Exception as e:
                print(f"[TTS Error]: {e}")
            finally:
                try:
                    pythoncom.CoUninitialize()
                except Exception:
                    pass
        else:
            try:
                import pyttsx3
                engine = pyttsx3.init()
                engine.say(text)
                engine.runAndWait()
            except Exception:
                pass

    t = threading.Thread(target=_worker, daemon=True)
    t.start()


def clean_extracted_name(raw_text: str) -> str:
    """Extracts a clean human name from conversational speech input."""
    clean = raw_text.lower().strip()
    clean = re.sub(r'[^\w\s]', '', clean)

    prefixes = [
        "my name is",
        "i am",
        "myself",
        "this is",
        "they call me",
        "call me",
        "name is",
        "it is",
        "im"
    ]
    for p in prefixes:
        if clean.startswith(p):
            clean = clean[len(p):].strip()
            break
        elif f" {p} " in clean:
            idx = clean.find(f" {p} ")
            clean = clean[idx + len(p) + 2:].strip()
            break

    words = clean.split()
    if words:
        # Take up to 3 words for name
        return " ".join(words[:3]).title()
    return ""


def listen_for_spoken_name(timeout: float = 6.0) -> Optional[str]:
    """Listens for a name using microphone and Google Speech Recognition."""
    if not HAS_SR:
        return None

    recognizer = sr.Recognizer()
    recognizer.energy_threshold = 300
    recognizer.dynamic_energy_threshold = True

    try:
        with sr.Microphone() as source:
            print("\n" + "=" * 50)
            print("  🎤 [LISTENING FOR NAME... Please speak your name clearly]")
            print("=" * 50)
            recognizer.adjust_for_ambient_noise(source, duration=0.8)
            audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=5)

            print("🔍 [Processing speech recognition...]")
            spoken = recognizer.recognize_google(audio, language="en-in")
            print(f"🗣️ Heard: \"{spoken}\"")
            if is_refusal_response(spoken):
                print("⚠️ [User replied with refusal ('no') -> will assign anonymous profile]")
                return "__ANONYMOUS__"
            name = clean_extracted_name(spoken)
            if name:
                print(f"✅ Extracted Name: {name}")
                return name
    except sr.WaitTimeoutError:
        print("⏱️ [Voice listen timed out - no speech detected]")
    except sr.UnknownValueError:
        print("❓ [Could not understand speech]")
    except Exception as e:
        print(f"⚠️ [Microphone error]: {e}")

    return None


# -------------------------------------------------------------
# 1. FOLDER BATCH ENROLLMENT
# -------------------------------------------------------------

def enroll_from_folder(system: FaceRecognitionSystem, folder_path: str):
    """
    Enrolls all photos in a folder.
    Uses each image file's base name as the person's name!
    e.g. sneha.jpg -> 'Sneha', rohit_adak.png -> 'Rohit Adak'
    """
    if not os.path.exists(folder_path) or not os.path.isdir(folder_path):
        print(f"[Error] Folder not found: {folder_path}")
        return False

    print("=" * 65)
    print(f"  NEURA VISION - BATCH IMAGE ENROLLMENT")
    print(f"  Folder: {os.path.abspath(folder_path)}")
    print("=" * 65)

    valid_exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    files = [
        f for f in sorted(os.listdir(folder_path))
        if os.path.splitext(f)[1].lower() in valid_exts
    ]

    if not files:
        print(f"[Warning] No image files ({', '.join(valid_exts)}) found in '{folder_path}'.")
        return False

    success_count = 0
    for idx, fname in enumerate(files, 1):
        fpath = os.path.join(folder_path, fname)
        base = os.path.splitext(fname)[0]
        person_name = base.replace("_", " ").replace("-", " ").strip().title()
        role = "owner" if person_name.lower() == "rohit" else "guest"

        print(f"\n[{idx}/{len(files)}] Processing: {fname} -> Target Name: '{person_name}'")
        ok, msg = system.enroll_person_from_image(fpath, name=person_name, role=role)
        if ok:
            print(f"  ✅ {msg}")
            success_count += 1
        else:
            print(f"  ❌ {msg}")

    print("\n" + "=" * 65)
    print(f"Batch Enrollment Finished: {success_count}/{len(files)} person(s) successfully enrolled!")
    print(f"Database saved to: {DEFAULT_KNOWN_FACES_PATH}")
    print("=" * 65)
    return success_count > 0


# -------------------------------------------------------------
# 2. SINGLE IMAGE ENROLLMENT
# -------------------------------------------------------------

def enroll_from_single_image(
    system: FaceRecognitionSystem,
    image_path: str,
    name: Optional[str] = None,
    role: str = "guest"
):
    """Enrolls a single photo file."""
    if not os.path.exists(image_path):
        print(f"[Error] Image not found: {image_path}")
        return False

    if not name or not name.strip():
        base = os.path.splitext(os.path.basename(image_path))[0]
        name = base.replace("_", " ").replace("-", " ").strip().title()
    else:
        name = name.strip()

    if name.lower() == "rohit":
        role = "owner"

    print("=" * 60)
    print(f"  NEURA VISION - ENROLLING FROM IMAGE")
    print(f"  Person: {name} ({role.upper()})")
    print(f"  Image : {image_path}")
    print("=" * 60)

    ok, msg = system.enroll_person_from_image(image_path, name=name, role=role)
    if ok:
        print(f"\n✅ {msg}")
        print(f"Database saved to: {DEFAULT_KNOWN_FACES_PATH}")
    else:
        print(f"\n❌ Enrollment failed: {msg}")
    return ok


# -------------------------------------------------------------
# 3. INTERACTIVE GUIDED CAMERA ENROLLMENT
# -------------------------------------------------------------

def enroll_from_camera_guided(
    system: FaceRecognitionSystem,
    name: str,
    target_samples: int = 8,
    camera_index: int = 0
):
    """Guides a person through webcam face enrollment."""
    clean_name = name.strip().title()
    role = "owner" if clean_name.lower() == "rohit" else "guest"

    print("=" * 65)
    print(f"  NEURA VISION - GUIDED WEBCAM ENROLLMENT: {clean_name.upper()}")
    print("=" * 65)
    print(f"Target Samples: {target_samples}")
    print("Controls:")
    print("  [c] : Capture manual sample")
    print("  [q] / [ESC] : Cancel")
    print("=" * 65)

    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        print(f"[Error] Could not open camera {camera_index}.")
        return False

    collected = []
    last_cap_time = 0.0
    cap_interval = 0.9

    window_title = f"Neura Vision - Enrolling {clean_name}"
    cv2.namedWindow(window_title, cv2.WINDOW_AUTOSIZE)

    speak(f"Starting enrollment for {clean_name}. Please look at the camera.")

    try:
        while len(collected) < target_samples:
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.03)
                continue

            display = cv2.flip(frame, 1)
            h, w = frame.shape[:2]
            faces = system.detect_faces(frame)

            # Draw HUD
            overlay = display.copy()
            cv2.rectangle(overlay, (0, 0), (w, 70), (25, 25, 25), -1)
            cv2.addWeighted(overlay, 0.75, display, 0.25, 0, display)

            cv2.putText(
                display,
                f"Enrolling: {clean_name} [{len(collected)}/{target_samples} samples]",
                (20, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.75,
                (0, 255, 220),
                2,
                cv2.LINE_AA,
            )
            cv2.putText(
                display,
                "Look at camera, tilt head gently or smile slightly",
                (20, 58),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (220, 220, 220),
                1,
                cv2.LINE_AA,
            )

            face_detected = False
            best_face = None

            if faces:
                best_face = max(faces, key=lambda f: f["bbox"][2] * f["bbox"][3])
                bx, by, bw, bh = best_face["bbox"]
                bx_m = w - (bx + bw)
                face_detected = True

                cv2.rectangle(display, (bx_m, by), (bx_m + bw, by + bh), (0, 255, 120), 2)
                cv2.putText(
                    display,
                    f"Face Detected ({best_face['score']:.2f})",
                    (bx_m, max(20, by - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    (0, 255, 120),
                    2,
                )

            cv2.imshow(window_title, display)
            key = cv2.waitKey(1) & 0xFF
            if key in (27, ord('q')):
                print("[Enrollment cancelled by user]")
                return False

            now = time.time()
            capture_now = (key == ord('c')) or (face_detected and (now - last_cap_time >= cap_interval))
            if capture_now and best_face is not None:
                emb = system.extract_embedding(frame, best_face["raw_face"])
                collected.append(emb)
                last_cap_time = now
                print(f" -> Captured sample {len(collected)}/{target_samples}")

        # Save enrolled person
        system.enroll_person(clean_name, collected, role=role)
        speak(f"Enrollment complete. Welcome {clean_name}!")
        print(f"\n[Success] {clean_name} enrolled with {len(collected)} samples.")
        return True

    finally:
        cap.release()
        cv2.destroyAllWindows()


# -------------------------------------------------------------
# 4. LIVE AUTO-LEARN & RECOGNITION (Direct Questioning Mode)
# -------------------------------------------------------------

def run_auto_recognition_and_learning(system: FaceRecognitionSystem, camera_index: int = 0):
    """
    Watches camera feed in real time:
    - If known person (Owner or Guest) appears: displays name and greeting.
    - If an UNKNOWN person appears:
      1. Directly speaks: 'Please tell me your name'
      2. Listens via microphone (or console input)
      3. Captures photos internally from stream
      4. Registers name into known_faces.json automatically!
    """
    print("=" * 65)
    print("  NEURA VISION - LIVE AUTO-RECOGNITION & LEARNING MODE")
    print("=" * 65)
    print("Known faces database:", list(system.known_faces.keys()))
    print("Instructions:")
    print("  - When you look at the camera, Neura recognizes you.")
    print("  - When a NEW person appears, Neura directly asks for their name,")
    print("    captures their face internally, and auto-learns their identity!")
    print("Controls:")
    print("  [q] / [ESC] : Quit")
    print("  [l]         : List known faces")
    print("=" * 65)

    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        print(f"[Error] Could not open camera {camera_index}.")
        return

    window_title = "Neura Vision - Auto Face Recognition & Learning"
    cv2.namedWindow(window_title, cv2.WINDOW_AUTOSIZE)

    # State variables for unknown person detection
    unknown_seen_frames = 0
    UNKNOWN_TRIGGER_FRAMES = 18  # ~1.2 seconds of stable detection
    is_learning_active = False
    last_prompt_time = 0.0
    PROMPT_COOLDOWN = 15.0  # seconds between repeated unknown prompts
    last_greeted_person = None
    last_greet_time = 0.0

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.03)
                continue

            results, display = system.process_frame(frame, draw_overlay=True, mirror_display=True)
            h, w = display.shape[:2]

            # Top HUD Bar
            cv2.rectangle(display, (0, 0), (w, 42), (18, 18, 18), -1)
            cv2.putText(
                display,
                f"Neura Vision | Known Persons: {len(system.known_faces)} | Press Q to Exit",
                (16, 28),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 255, 200),
                1,
                cv2.LINE_AA
            )

            # Prioritize faces: Owner (2) > Known Guest (1) > Unknown (0), largest area first
            def _face_priority(f):
                score = 2 if f.get("is_owner") else (1 if f.get("is_known") else 0)
                bb = f.get("bbox", [0, 0, 0, 0])
                area = bb[2] * bb[3] if len(bb) >= 4 else 0
                return (score, area)

            results = sorted(results, key=_face_priority, reverse=True)
            has_known = any(face.get("is_known", False) or face.get("is_owner", False) for face in results)
            has_unknown = any(not face.get("is_known", False) for face in results)

            now = time.time()

            # Rule: If a known face is found, do NOT ask for name; greet the known face instead!
            if has_known:
                top_known = results[0]
                k_name = top_known.get("identity", "Sir")
                if (k_name != last_greeted_person or (now - last_greet_time) > 8.0):
                    last_greeted_person = k_name
                    last_greet_time = now
                    if top_known.get("is_owner"):
                        speak(f"Hello Sir, identity verified! Welcome back, {k_name}.")
                    else:
                        speak(f"Hello {k_name}, welcome!")
                unknown_seen_frames = 0
            elif has_unknown and not is_learning_active:
                unknown_seen_frames += 1

                # Visual notice on HUD
                cv2.rectangle(display, (0, h - 45), (w, h), (0, 40, 220), -1)
                cv2.putText(
                    display,
                    "NEW PERSON DETECTED - PREPARING TO ASK NAME...",
                    (20, h - 16),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (255, 255, 255),
                    2,
                    cv2.LINE_AA
                )

                if unknown_seen_frames >= UNKNOWN_TRIGGER_FRAMES and (now - last_prompt_time >= PROMPT_COOLDOWN):
                    is_learning_active = True
                    last_prompt_time = now

                    # Show "Asking for name" on screen
                    cv2.imshow(window_title, display)
                    cv2.waitKey(10)

                    # Trigger interactive auto-learning
                    _execute_auto_learning_procedure(cap, system, window_title)

                    # Reset states after enrollment
                    unknown_seen_frames = 0
                    is_learning_active = False
            else:
                if not has_unknown:
                    unknown_seen_frames = max(0, unknown_seen_frames - 1)

            cv2.imshow(window_title, display)
            key = cv2.waitKey(1) & 0xFF
            if key in (27, ord('q')):
                break
            elif key == ord('l'):
                list_known_faces(system)

    finally:
        cap.release()
        cv2.destroyAllWindows()


def _execute_auto_learning_procedure(cap: cv2.VideoCapture, system: FaceRecognitionSystem, window_title: str):
    """
    Executes the conversational auto-learning sequence:
    1. Speaks: "Hello! Please tell me your name."
    2. Listens via voice or console.
    3. Captures 5 sample frames internally.
    4. Enrolls into known_faces.json!
    """
    print("\n" + "=" * 60)
    print("  👤 [UNKNOWN PERSON DETECTED] -> AUTO-LEARNING TRIGGERED")
    print("=" * 60)

    # 1. Ask person directly
    prompt_msg = "Hello! Please tell me your name."
    speak(prompt_msg)
    time.sleep(1.8)

    # 2. Listen for name
    new_name = None
    if HAS_SR:
        new_name = listen_for_spoken_name(timeout=6.0)

    # Check if refusal was spoken
    if new_name == "__ANONYMOUS__" or (new_name and is_refusal_response(new_name)):
        new_name = get_next_anonymous_name(system)
    elif not new_name:
        # Fallback to console input if speech recognition did not catch name
        print("\n[Input Prompt] (Voice not detected. You can type the name in console or 'no' for anonymous):")
        try:
            typed = input("Please enter name: ").strip()
            if typed:
                if is_refusal_response(typed):
                    new_name = get_next_anonymous_name(system)
                else:
                    new_name = clean_extracted_name(typed)
        except Exception:
            pass

    if not new_name:
        print("⚠️ [Could not acquire person's name. Aborting enrollment.]")
        return

    if "Anonymous" in new_name:
        print(f"\n📸 [User answered 'no' -> auto-assigning '{new_name}' and capturing photo samples...]")
        speak(f"Understood. Registering you as {new_name}. Hold still, capturing your photos...")
    else:
        print(f"\n📸 [Capturing photo samples internally for '{new_name}'...]")
        speak(f"Hold still, {new_name}, capturing your photos...")

    samples = []
    start_cap = time.time()

    # Capture 5 good frames internally
    while len(samples) < 5 and time.time() - start_cap < 6.0:
        ret, frame = cap.read()
        if not ret:
            time.sleep(0.03)
            continue

        faces = system.detect_faces(frame)
        if faces:
            best_face = max(faces, key=lambda f: f["bbox"][2] * f["bbox"][3])
            emb = system.extract_embedding(frame, best_face["raw_face"])
            samples.append(emb)

            # Save snapshot image on first sample
            if len(samples) == 1:
                try:
                    os.makedirs("images", exist_ok=True)
                    img_path = os.path.join("images", f"{new_name}.jpg")
                    cv2.imwrite(img_path, frame)
                    print(f"📸 Saved image snapshot to {img_path}")
                except Exception as err:
                    print(f"⚠️ Could not save photo: {err}")

            # Show visual capture feedback on screen
            display = cv2.flip(frame, 1)
            h, w = display.shape[:2]
            cv2.rectangle(display, (0, h - 50), (w, h), (0, 200, 100), -1)
            cv2.putText(
                display,
                f"Auto-capturing photos for {new_name}: {len(samples)}/5",
                (20, h - 16),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                (255, 255, 255),
                2,
                cv2.LINE_AA
            )
            cv2.imshow(window_title, display)
            cv2.waitKey(120)

    if samples:
        # Enroll and save
        system.enroll_person(new_name, samples, role="guest")
        try:
            mem = MemoryManager()
            mem.log_activity(f"Face auto-enrolled: {new_name} added to known faces.")
        except Exception:
            pass

        if "Anonymous" in new_name:
            confirm_msg = f"You have been registered as {new_name}. I will recognize you next time."
        else:
            confirm_msg = f"Thank you, {new_name}! I have saved your face and will remember you."
        speak(confirm_msg)
        print(f"✅ [SUCCESS] {new_name} is now registered in the known faces database!\n")
    else:
        print("❌ [Could not capture sufficient face samples.]")


# -------------------------------------------------------------
# 5. LIST & DELETE MANAGEMENT
# -------------------------------------------------------------

def list_known_faces(system: FaceRecognitionSystem):
    """Prints a structured table of all registered faces."""
    system.load_known_faces()
    persons = system.get_known_persons()

    print("\n" + "=" * 70)
    print("  NEURA VISION - REGISTERED FACES DATABASE")
    print(f"  Location: {DEFAULT_KNOWN_FACES_PATH}")
    print("=" * 70)

    if not persons:
        print("  (No faces enrolled yet. Use --folder, --image, or --auto to enroll)")
        print("=" * 70 + "\n")
        return

    print(f" {'#':<3} | {'NAME':<20} | {'ROLE':<10} | {'SAMPLES':<8} | {'ENROLLED AT':<20}")
    print("-" * 70)

    for idx, p in enumerate(persons, 1):
        role_str = "[OWNER]" if p["role"] == "owner" else "[GUEST]"
        enrolled_at = p.get("enrolled_at") or "Unknown"
        print(f" {idx:<3} | {p['name']:<20} | {role_str:<10} | {p['samples_count']:<8} | {enrolled_at:<20}")

    print("=" * 70 + "\n")


def delete_known_face(system: FaceRecognitionSystem, name: str):
    """Deletes an enrolled person by name."""
    ok = system.delete_person(name)
    if ok:
        print(f"✅ Successfully deleted '{name}' from known faces.")
    else:
        print(f"❌ Person '{name}' was not found in known faces database.")
    return ok


# -------------------------------------------------------------
# MAIN CLI ENTRYPOINT
# -------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Neura AI - Multi-Face Enrollment & Auto-Learning System",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--folder", "--dir", dest="folder", type=str, default=None,
                        help="Path to folder of named images to batch enroll (e.g. --folder images/)")
    parser.add_argument("--image", type=str, default=None,
                        help="Path to a single image file (e.g. --image sneha.jpg)")
    parser.add_argument("--name", type=str, default=None,
                        help="Name of person (optional; defaults to image filename)")
    parser.add_argument("--camera", action="store_true",
                        help="Guided webcam enrollment for a person")
    parser.add_argument("--samples", type=int, default=8,
                        help="Number of samples to capture in camera enrollment (default: 8)")
    parser.add_argument("--auto", "--live", dest="auto", action="store_true",
                        help="Run live camera auto-recognition & interactive unknown learning")
    parser.add_argument("--list", action="store_true",
                        help="List all registered individuals in known_faces.json")
    parser.add_argument("--delete", type=str, default=None,
                        help="Delete a person from known_faces.json by name")
    parser.add_argument("--cam-index", type=int, default=0,
                        help="Webcam device index (default: 0)")

    args = parser.parse_args()
    system = get_face_system()

    # Route command
    if args.list:
        list_known_faces(system)
    elif args.delete:
        delete_known_face(system, args.delete)
    elif args.folder:
        enroll_from_folder(system, args.folder)
    elif args.image:
        enroll_from_single_image(system, args.image, name=args.name)
    elif args.camera:
        person_name = args.name
        if not person_name:
            person_name = input("Enter person's name for enrollment: ").strip()
        if person_name:
            enroll_from_camera_guided(system, person_name, target_samples=args.samples, camera_index=args.cam_index)
        else:
            print("[Error] A valid person name is required for camera enrollment.")
    elif args.auto:
        run_auto_recognition_and_learning(system, camera_index=args.cam_index)
    else:
        # Default behavior when no flag passed: display list and options
        list_known_faces(system)
        print("💡 Usage Quick Reference:")
        print("  python setup_face.py --folder \"path/to/images/\"   # Batch enroll folder of images")
        print("  python setup_face.py --image \"sneha.jpg\"         # Enroll from image")
        print("  python setup_face.py --auto                        # Live camera auto-detection & unknown asking")
        print("  python setup_face.py --list                        # Show all registered faces\n")


if __name__ == "__main__":
    main()
