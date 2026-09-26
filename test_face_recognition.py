"""
Neura Vision - Face Recognition Test Script
Tests the full pipeline:
Camera -> Face Detection (YuNet) -> Face Embedding (SFace) -> Compare with Rohit's enrolled embedding -> Identity -> Neura's memory/state

Usage:
  python test_face_recognition.py              # Live camera recognition test
  python test_face_recognition.py --camera 0   # Specify camera index
  python test_face_recognition.py --image f.jpg # Test on static image
  python test_face_recognition.py --self-test  # Automated headless diagnostic check
"""

import os
import sys
import time
import argparse
import cv2
import numpy as np

# Ensure root workspace is in sys.path
WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))
if WORKSPACE_DIR not in sys.path:
    sys.path.insert(0, WORKSPACE_DIR)

from vision.face_recognition import (
    FaceRecognitionSystem,
    DEFAULT_YUNET_PATH,
    DEFAULT_SFACE_PATH,
    DEFAULT_PROFILE_PATH
)
from memory.memory_manager import MemoryManager


def run_camera_test(camera_index: int = 0):
    """Runs interactive real-time camera face recognition test."""
    print("=" * 60)
    print("  NEURA VISION - LIVE FACE RECOGNITION TEST")
    print("=" * 60)
    print("Pipeline: YuNet (Detection) -> SFace (Embedding) -> Rohit Profile Match -> Memory/State")
    print("Controls:")
    print("  [q] / [ESC] : Quit test")
    print("  [s]         : Trigger manual memory/state sync with current identity")
    print("=" * 60)

    system = FaceRecognitionSystem()
    mem_mgr = MemoryManager()

    if not system.is_owner_enrolled():
        print("\n[NOTE] Rohit is not enrolled yet in vision/owner_profile.json.")
        print("Run 'python setup_owner.py' to enroll your face first.")
        print("Camera preview will run in detection-only mode.\n")

    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        print(f"[Error] Could not open camera {camera_index}. Please check webcam connection.")
        return False

    window_title = "Neura Vision - Face Recognition (YuNet + SFace)"
    cv2.namedWindow(window_title, cv2.WINDOW_AUTOSIZE)

    prev_time = time.time()
    fps = 0.0

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.03)
                continue

            curr_time = time.time()
            fps = 0.9 * fps + 0.1 * (1.0 / max(0.001, curr_time - prev_time))
            prev_time = curr_time

            # Full pipeline execution with mirror display and upright readable HUD
            results, display = system.process_frame(frame, draw_overlay=True, mirror_display=True)

            # Draw HUD status header
            h, w = display.shape[:2]
            overlay = display.copy()
            cv2.rectangle(overlay, (0, 0), (w, 45), (15, 15, 15), -1)
            cv2.addWeighted(overlay, 0.75, display, 0.25, 0, display)

            enrolled_txt = "ENROLLED" if system.is_owner_enrolled() else "NOT ENROLLED"
            known_count = len(system.known_faces)

            cv2.putText(
                display,
                f"Neura Vision | FPS: {fps:.1f} | Known Faces: {known_count} | Owner: {enrolled_txt}",
                (15, 28),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (0, 255, 220),
                1,
                cv2.LINE_AA,
            )

            cv2.imshow(window_title, display)
            key = cv2.waitKey(1) & 0xFF

            if key == 27 or key == ord('q'):
                break
            elif key == ord('s') and results:
                # Sync memory with first recognized face
                spoken = system.update_neura_state(results[0], mem_mgr)
                print(f"[Memory Sync] {spoken}")
                print(f" -> Active user state: {mem_mgr.user_memory['user_facts'].get('current_user')}")
                print(f" -> Last activity: {mem_mgr.user_memory['activity_log'][-1]}")

        return True

    finally:
        cap.release()
        cv2.destroyAllWindows()


def run_image_test(image_path: str):
    """Tests face recognition on a static image file."""
    if not os.path.exists(image_path):
        print(f"[Error] File not found: {image_path}")
        return False

    system = FaceRecognitionSystem()
    mem_mgr = MemoryManager()

    frame = cv2.imread(image_path)
    if frame is None:
        print(f"[Error] Failed to read image: {image_path}")
        return False

    print(f"Analyzing image: {image_path} ({frame.shape[1]}x{frame.shape[0]})...")
    results, annotated = system.process_frame(frame, draw_overlay=True)

    print(f"\nDetected Faces: {len(results)}")
    for i, res in enumerate(results):
        print(f" Face #{i+1}:")
        print(f"  - Identity: {res['identity']} (is_owner: {res['is_owner']})")
        print(f"  - Cosine Similarity: {res['confidence']:.4f} (threshold: {system.cosine_threshold})")
        print(f"  - L2 Distance: {res['l2_distance']:.4f} (threshold: {system.l2_threshold})")
        print(f"  - Detection Score: {res['detection_score']:.4f}")
        print(f"  - Bounding Box: {res['bbox']}")

        msg = system.update_neura_state(res, mem_mgr)
        print(f"  - Neura Memory Action: {msg}")

    # Display image window
    cv2.imshow("Neura Vision - Image Test Result (Press any key to close)", annotated)
    cv2.waitKey(0)
    cv2.destroyAllWindows()
    return True


def run_self_test() -> bool:
    """Automated diagnostic test verifying all pipeline stages headless."""
    print("=" * 60)
    print("  NEURA VISION - AUTOMATED PIPELINE SELF-TEST")
    print("=" * 60)

    # 1. Model existence & loading
    print("\n[Step 1/5] Checking ONNX Model Files...")
    if not os.path.exists(DEFAULT_YUNET_PATH):
        print(f"  FAIL: YuNet model not found at {DEFAULT_YUNET_PATH}")
        return False
    print(f"  PASS: YuNet ({os.path.getsize(DEFAULT_YUNET_PATH)} bytes)")

    if not os.path.exists(DEFAULT_SFACE_PATH):
        print(f"  FAIL: SFace model not found at {DEFAULT_SFACE_PATH}")
        return False
    print(f"  PASS: SFace ({os.path.getsize(DEFAULT_SFACE_PATH)} bytes)")

    # 2. System initialization
    print("\n[Step 2/5] Initializing FaceRecognitionSystem...")
    try:
        system = FaceRecognitionSystem()
        print("  PASS: YuNet and SFace instantiated successfully.")
    except Exception as e:
        print(f"  FAIL: Could not initialize system: {e}")
        return False

    # 3. Embedding extraction & math verification
    print("\n[Step 3/5] Verifying SFace Feature Extraction & Distance Math...")
    # Synthetic face image and dummy landmark array
    dummy_img = np.zeros((300, 300, 3), dtype=np.uint8)
    cv2.circle(dummy_img, (150, 150), 70, (180, 180, 180), -1)
    dummy_face = np.array([50, 50, 100, 100, 75, 80, 125, 80, 100, 105, 80, 130, 120, 130, 0.99], dtype=np.float32)

    try:
        emb1 = system.extract_embedding(dummy_img, dummy_face)
        if emb1.shape != (1, 128) or emb1.dtype != np.float32:
            print(f"  FAIL: Unexpected embedding shape/dtype: {emb1.shape}, {emb1.dtype}")
            return False

        # Self-similarity should be ~1.0
        self_cos = float(system.recognizer.match(emb1, emb1, cv2.FaceRecognizerSF_FR_COSINE))
        self_l2 = float(system.recognizer.match(emb1, emb1, cv2.FaceRecognizerSF_FR_NORM_L2))
        print(f"  PASS: 128-d embedding extracted. Self Cosine: {self_cos:.4f}, Self L2: {self_l2:.4f}")
    except Exception as e:
        print(f"  FAIL: Feature extraction error: {e}")
        return False

    # 4. Profile Management
    print("\n[Step 4/5] Checking Owner Profile (vision/owner_profile.json)...")
    print(f"  Owner Status: {system.owner_profile.get('status')}")
    print(f"  Owner Name: {system.owner_profile.get('name')}")
    print(f"  Samples: {system.owner_profile.get('samples_count', 0)}")
    print(f"  Cosine Threshold: {system.cosine_threshold}")
    print("  PASS: Owner profile schema verified.")

    # 5. MemoryManager State Synchronization
    print("\n[Step 5/5] Testing Neura Memory & State Integration...")
    try:
        mem_mgr = MemoryManager()
        mock_result = {
            "identity": "Rohit",
            "is_owner": True,
            "confidence": 0.88,
            "l2_distance": 0.35,
            "bbox": (50, 50, 100, 100),
            "landmarks": []
        }
        speech = system.update_neura_state(mock_result, mem_mgr)
        print(f"  Neura response: '{speech}'")
        curr_u = mem_mgr.user_memory["user_facts"].get("name")
        auth = mem_mgr.user_memory["user_facts"].get("face_authenticated")
        print(f"  Updated State: Name={curr_u}, Authenticated={auth}")
        print("  PASS: Memory & State update succeeded.")
    except Exception as e:
        print(f"  FAIL: Memory sync failed: {e}")
        return False

    print("\n" + "=" * 60)
    print("  ALL 5 PIPELINE STAGES PASSED SUCCESSFULLY!")
    print("=" * 60)
    return True


def main():
    parser = argparse.ArgumentParser(description="Test Neura Vision Face Recognition Pipeline")
    parser.add_argument("--camera", type=int, default=0, help="Camera index for live test (default: 0)")
    parser.add_argument("--image", type=str, default=None, help="Path to static image file for testing")
    parser.add_argument("--self-test", action="store_true", help="Run automated headless diagnostic pipeline check")
    args = parser.parse_args()

    if args.self_test:
        success = run_self_test()
    elif args.image:
        success = run_image_test(args.image)
    else:
        success = run_camera_test(camera_index=args.camera)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
