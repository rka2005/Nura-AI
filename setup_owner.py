"""
Neura Vision - Owner Profile Enrollment Script
Enrolls Rohit's facial embeddings using YuNet (Face Detection) and SFace (Face Recognition).
Saves the biometric profile to vision/owner_profile.json and links to Neura's memory system.

Usage:
  python setup_owner.py                 # Interactive enrollment via webcam
  python setup_owner.py --image me.jpg  # Enrollment from a photo file
  python setup_owner.py --samples 10    # Custom number of samples
"""

import os
import sys
import time
import argparse
from typing import Optional
import cv2
import numpy as np

# Ensure root workspace is in sys.path
WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))
if WORKSPACE_DIR not in sys.path:
    sys.path.insert(0, WORKSPACE_DIR)

from vision.face_recognition import FaceRecognitionSystem, DEFAULT_PROFILE_PATH
from memory.memory_manager import MemoryManager


def enroll_from_camera(
    system: FaceRecognitionSystem,
    owner_name: str = "Rohit",
    target_samples: int = 10,
    camera_index: int = 0
) -> bool:
    """Enrolls Rohit's face interactively via webcam."""
    print("=" * 60)
    print(f"  NEURA BIOMETRIC ENROLLMENT: {owner_name.upper()}")
    print("=" * 60)
    print("Instructions:")
    print(" 1. Sit in a well-lit area and face the camera.")
    print(" 2. The system will collect multiple diverse facial samples:")
    print("    - Look straight at the camera")
    print("    - Tilt slightly to the left and right")
    print("    - Smile or make slight natural expressions")
    print(" 3. Press 'c' to capture a sample manually, or wait for auto-capture.")
    print(" 4. Press 'q' or ESC at any time to cancel.")
    print("=" * 60)

    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        print(f"[Error] Could not open camera {camera_index}. Please check webcam connection.")
        return False

    collected_embeddings = []
    last_capture_time = 0.0
    capture_interval = 1.0  # seconds between auto-captures

    phases = [
        ("Look directly at the camera", target_samples // 3),
        ("Turn head slightly left & right", target_samples // 3),
        ("Natural smile / slight tilt", target_samples - (2 * (target_samples // 3)))
    ]

    phase_idx = 0
    phase_samples = 0

    window_title = f"Neura Vision - Enrolling {owner_name}"
    cv2.namedWindow(window_title, cv2.WINDOW_AUTOSIZE)

    try:
        while len(collected_embeddings) < target_samples:
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.03)
                continue

            # Mirror the camera frame for a natural mirror view
            display = cv2.flip(frame, 1)
            h, w = frame.shape[:2]

            # Detect faces with YuNet on original frame
            faces = system.detect_faces(frame)

            # Determine current instructional phase
            current_prompt, target_in_phase = phases[phase_idx]

            # Draw visual guidance overlay
            overlay = display.copy()
            cv2.rectangle(overlay, (0, 0), (w, 80), (20, 20, 20), -1)
            cv2.rectangle(overlay, (0, h - 50), (w, h), (20, 20, 20), -1)
            cv2.addWeighted(overlay, 0.7, display, 0.3, 0, display)

            # Banner info (rendered on mirrored display - upright and readable)
            progress_pct = int((len(collected_embeddings) / target_samples) * 100)
            cv2.putText(
                display,
                f"Enrolling {owner_name}: {len(collected_embeddings)}/{target_samples} samples ({progress_pct}%)",
                (20, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 200),
                2,
                cv2.LINE_AA,
            )
            cv2.putText(
                display,
                f"Step: {current_prompt}",
                (20, 60),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (255, 255, 255),
                1,
                cv2.LINE_AA,
            )

            # Draw progress bar at bottom
            bar_w = int((w - 40) * (len(collected_embeddings) / target_samples))
            cv2.rectangle(display, (20, h - 35), (w - 20, h - 20), (60, 60, 60), -1)
            if bar_w > 0:
                cv2.rectangle(display, (20, h - 35), (20 + bar_w, h - 20), (0, 220, 80), -1)

            face_detected = False
            best_face = None

            if faces:
                # Pick largest face
                best_face = max(faces, key=lambda f: f["bbox"][2] * f["bbox"][3])
                bx, by, bw, bh = best_face["bbox"]
                face_detected = True

                # Convert bounding box and landmarks to mirror coordinates
                bx_m = w - (bx + bw)
                by_m = by

                # Draw bounding box and landmarks on mirrored display
                cv2.rectangle(display, (bx_m, by_m), (bx_m + bw, by_m + bh), (0, 220, 80), 2)
                for lx, ly in best_face["landmarks"]:
                    lx_m = w - lx
                    cv2.circle(display, (lx_m, ly), 3, (0, 255, 255), -1)

                cv2.putText(
                    display,
                    f"Face Detected ({best_face['score']:.2f})",
                    (bx_m, max(20, by_m - 10)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    (0, 220, 80),
                    2,
                )
            else:
                cv2.putText(
                    display,
                    "Looking for face... Please center your face in the camera.",
                    (20, h - 60),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    (0, 140, 255),
                    1,
                )

            cv2.imshow(window_title, display)
            key = cv2.waitKey(1) & 0xFF

            if key == 27 or key == ord('q'):
                print("\n[Enrollment Cancelled by User]")
                return False

            now = time.time()
            capture_now = (key == ord('c')) or (face_detected and (now - last_capture_time >= capture_interval))

            if capture_now and best_face is not None:
                # Extract SFace embedding
                embedding = system.extract_embedding(frame, best_face["raw_face"])
                collected_embeddings.append(embedding)
                last_capture_time = now
                phase_samples += 1

                print(f" -> Captured sample {len(collected_embeddings)}/{target_samples} [Conf: {best_face['score']:.2f}]")

                # Advance phase if needed
                if phase_samples >= target_in_phase and phase_idx < len(phases) - 1:
                    phase_idx += 1
                    phase_samples = 0

                # Brief visual flash
                cv2.rectangle(display, (0, 0), (w, h), (255, 255, 255), 10)
                cv2.imshow(window_title, display)
                cv2.waitKey(80)

        # Save profile
        print("\nAll samples captured! Processing embeddings...")
        system.save_owner_profile(name=owner_name, embeddings=collected_embeddings)

        # Update Neura's memory
        _sync_enrollment_to_neura_memory(owner_name, len(collected_embeddings))

        # Show success screen
        for _ in range(30):
            ret, frame = cap.read()
            if ret:
                results, annotated = system.process_frame(frame, draw_overlay=True)
                cv2.putText(
                    annotated,
                    f"ENROLLMENT COMPLETE: {owner_name.upper()} VERIFIED!",
                    (30, 50),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.8,
                    (0, 255, 0),
                    2,
                )
                cv2.imshow(window_title, annotated)
                if cv2.waitKey(30) & 0xFF == 27:
                    break

        print(f"\n[Success] {owner_name} enrolled successfully with {len(collected_embeddings)} samples.")
        print(f"Profile saved to: {DEFAULT_PROFILE_PATH}")
        return True

    finally:
        cap.release()
        cv2.destroyAllWindows()


def enroll_from_image(
    system: FaceRecognitionSystem,
    image_path: str,
    owner_name: Optional[str] = None
) -> bool:
    """
    Enrolls owner's face from a static image file.
    If owner_name is not provided, automatically extracts the owner's name from
    the image title (filename), without fixing or hardcoding the owner's identity.
    """
    if not os.path.exists(image_path):
        print(f"[Error] Image file not found: {image_path}")
        return False

    # Derive owner name from image file title if not explicitly passed
    if not owner_name or not owner_name.strip():
        base_title = os.path.splitext(os.path.basename(image_path))[0]
        clean_name = base_title.replace("_", " ").replace("-", " ").strip().title()
    else:
        clean_name = owner_name.strip().title()

    owner_title = f"Sri {clean_name}" if "rohit" in clean_name.lower() else clean_name

    print(f"Loading image from: {image_path}")
    print(f"Derived Owner Identity: '{clean_name}' (Title: '{owner_title}')")

    frame = cv2.imread(image_path)
    if frame is None:
        print("[Error] Failed to read image file.")
        return False

    faces = system.detect_faces(frame)
    if not faces:
        print("[Error] No face detected in the provided image. Please use a clearer photo.")
        return False

    best_face = max(faces, key=lambda f: f["bbox"][2] * f["bbox"][3])
    print(f"Detected face with confidence: {best_face['score']:.2f}")

    embedding = system.extract_embedding(frame, best_face["raw_face"])
    system.save_owner_profile(name=clean_name, embeddings=[embedding], title=owner_title)

    _sync_enrollment_to_neura_memory(clean_name, 1)
    print(f"[Success] Enrolled '{clean_name}' as the Owner from image: {image_path}")
    return True


def _sync_enrollment_to_neura_memory(owner_name: str, sample_count: int):
    """Synchronizes enrollment status with Neura's MemoryManager."""
    try:
        mem_mgr = MemoryManager()
        mem_mgr.user_memory["user_facts"]["name"] = owner_name
        mem_mgr.user_memory["user_facts"]["owner_face_enrolled"] = True
        mem_mgr.user_memory["user_facts"]["enrollment_samples"] = sample_count
        mem_mgr.log_activity(f"Biometric Enrollment: {owner_name} enrolled as owner with {sample_count} face samples.")
        mem_mgr.save_user_memory()
        print(f"Updated Neura's memory: owner_face_enrolled = True (Owner: {owner_name})")
    except Exception as e:
        print(f"[Warning] Could not sync with MemoryManager: {e}")


def main():
    parser = argparse.ArgumentParser(description="Neura AI - Owner Face Biometric Enrollment")
    parser.add_argument("--name", type=str, default=None, help="Name of owner to enroll (default: derived from image title)")
    parser.add_argument("--image", type=str, default=None, help="Path to photo file for non-camera enrollment")
    parser.add_argument("--camera", type=int, default=0, help="Camera index (default: 0)")
    parser.add_argument("--samples", type=int, default=10, help="Number of samples to capture (default: 10)")
    args = parser.parse_args()

    system = FaceRecognitionSystem()

    if args.image:
        success = enroll_from_image(system, args.image, owner_name=args.name)
    else:
        chosen_name = args.name or system.owner_profile.get("name") or "Owner"
        success = enroll_from_camera(
            system,
            owner_name=chosen_name,
            target_samples=args.samples,
            camera_index=args.camera
        )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
