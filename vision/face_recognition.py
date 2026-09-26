"""
Neura Vision - Face Recognition System
Pipeline: Camera -> Face Detection (YuNet) -> Face Embedding (SFace) -> Compare with Rohit's enrolled embedding -> Identity -> Neura's memory/state
"""

import os
import sys
import json
import time
import urllib.request
import datetime
import re
from typing import Dict, Any, List, Optional, Tuple
import cv2
import numpy as np

# Model URLs & default paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(BASE_DIR, "models")
DEFAULT_YUNET_PATH = os.path.join(MODELS_DIR, "face_detection_yunet_2023mar.onnx")
DEFAULT_SFACE_PATH = os.path.join(MODELS_DIR, "face_recognition_sface_2021dec.onnx")
DEFAULT_PROFILE_PATH = os.path.join(BASE_DIR, "owner_profile.json")
DEFAULT_KNOWN_FACES_PATH = os.path.join(BASE_DIR, "known_faces.json")

YUNET_URL = "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
SFACE_URL = "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx"

# Recommended OpenCV SFace thresholds
# Cosine Similarity: threshold ~0.363 (higher indicates same person)
# L2 Distance: threshold ~1.128 (lower indicates same person)
DEFAULT_COSINE_THRESHOLD = 0.363
DEFAULT_L2_THRESHOLD = 1.128


def clean_extracted_name(raw_text: str) -> str:
    """Extracts a clean human name from conversational speech or typed input."""
    if not raw_text:
        return ""
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
        stop_words = {"a", "an", "the", "hello", "hi", "hey", "please", "my", "name", "is", "am", "quit", "exit"}
        valid_words = [w for w in words if w.lower() not in stop_words]
        if valid_words:
            return " ".join(valid_words[:3]).title()
        return " ".join(words[:3]).title()
    return ""


def is_refusal_response(raw_text: str) -> bool:
    """Checks if speech/text is a refusal or negative answer ('no', 'nope', 'nah', etc.)."""
    if not raw_text:
        return False
    clean = raw_text.lower().strip()
    clean_no_punct = re.sub(r'[^\w\s]', '', clean).strip()
    words = clean_no_punct.split()

    refusal_words = {"no", "nope", "nah", "never", "dont", "wont", "not", "refuse", "skip", "pass"}
    refusal_phrases = [
        "no", "nope", "nah", "no thanks", "no thank you", "no i wont", "no i will not",
        "i dont want", "i do not want", "dont want", "dont want to tell", "do not want", "do not want to tell",
        "i wont tell", "wont tell", "not telling", "i am not telling", "i will not tell",
        "i will not", "i wont", "will not", "not now",
        "leave me", "skip", "pass", "no need", "never", "i dont know", "dont know",
        "not interested", "none of your business", "why should i"
    ]
    if clean_no_punct in refusal_phrases:
        return True
    if any(p in clean_no_punct for p in [
        "dont want", "do not want", "wont tell", "not telling", "will not tell",
        "no i will not", "no i dont", "dont tell", "i will not", "i wont",
        "no thanks", "no thank you", "not interested", "leave me"
    ]):
        return True
    if len(words) <= 2 and any(w in refusal_words for w in words):
        return True
    return False


def get_next_anonymous_name(system: Any) -> str:
    """
    Finds the next sequential anonymous label, e.g. 'Anonymous 1', 'Anonymous 2'.
    Supports multiple anonymous registered persons.
    """
    existing_nums = []
    if hasattr(system, "known_faces") and isinstance(system.known_faces, dict):
        for k in system.known_faces.keys():
            match = re.match(r'^anonymous(?:\s*(\d+))?$', k.strip(), re.IGNORECASE)
            if match:
                num = int(match.group(1)) if match.group(1) else 1
                existing_nums.append(num)
    if not existing_nums:
        return "Anonymous 1"
    return f"Anonymous {max(existing_nums) + 1}"


def ensure_models_exist(models_dir: str = MODELS_DIR) -> Tuple[str, str]:
    """Ensures YuNet and SFace ONNX models exist locally; downloads if missing."""
    os.makedirs(models_dir, exist_ok=True)
    yunet_path = os.path.join(models_dir, "face_detection_yunet_2023mar.onnx")
    sface_path = os.path.join(models_dir, "face_recognition_sface_2021dec.onnx")

    def _download(url: str, dest: str, name: str):
        if not os.path.exists(dest) or os.path.getsize(dest) < 1000:
            print(f"[Neura Vision] Downloading {name} model from OpenCV Zoo...")
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req) as resp, open(dest, "wb") as out_f:
                out_f.write(resp.read())
            print(f"[Neura Vision] {name} downloaded successfully ({os.path.getsize(dest)} bytes).")

    _download(YUNET_URL, yunet_path, "YuNet Face Detector")
    _download(SFACE_URL, sface_path, "SFace Face Recognizer")

    return yunet_path, sface_path


class FaceRecognitionSystem:
    """
    Handles Face Detection (YuNet) and Face Recognition (SFace),
    comparing embeddings against Rohit's enrolled profile, and updating
    Neura's internal memory/state.
    """

    def __init__(
        self,
        yunet_path: Optional[str] = None,
        sface_path: Optional[str] = None,
        profile_path: str = DEFAULT_PROFILE_PATH,
        known_faces_path: str = DEFAULT_KNOWN_FACES_PATH,
        score_threshold: float = 0.6,
        nms_threshold: float = 0.3,
        cosine_threshold: float = DEFAULT_COSINE_THRESHOLD,
        l2_threshold: float = DEFAULT_L2_THRESHOLD,
    ):
        self.yunet_path = yunet_path or DEFAULT_YUNET_PATH
        self.sface_path = sface_path or DEFAULT_SFACE_PATH
        self.profile_path = profile_path
        self.known_faces_path = known_faces_path

        self.score_threshold = score_threshold
        self.nms_threshold = nms_threshold
        self.cosine_threshold = cosine_threshold
        self.l2_threshold = l2_threshold

        self.detector = None
        self.recognizer = None
        self.last_input_size = (320, 320)

        # Owner Profile State (Rohit)
        self.owner_profile: Dict[str, Any] = {
            "name": "Rohit",
            "title": "Sri Rohit Kumar Adak",
            "status": "not_enrolled",
            "enrolled_at": None,
            "samples_count": 0,
            "cosine_threshold": self.cosine_threshold,
            "l2_threshold": self.l2_threshold,
            "average_embedding": [],
            "sample_embeddings": []
        }
        self.owner_embeddings_np: List[np.ndarray] = []
        self.avg_embedding_np: Optional[np.ndarray] = None

        # Multi-person Registry (Rohit, Sneha, Family, Friends, etc.)
        self.known_faces: Dict[str, Dict[str, Any]] = {}
        self.known_embeddings_np: Dict[str, List[np.ndarray]] = {}
        self.known_avg_embeddings_np: Dict[str, np.ndarray] = {}

        self._init_models()
        self.load_owner_profile()
        self.load_known_faces()

    def _init_models(self):
        """Initializes OpenCV YuNet and SFace instances."""
        if not os.path.exists(self.yunet_path) or not os.path.exists(self.sface_path):
            self.yunet_path, self.sface_path = ensure_models_exist(MODELS_DIR)

        try:
            self.detector = cv2.FaceDetectorYN.create(
                model=self.yunet_path,
                config="",
                input_size=self.last_input_size,
                score_threshold=self.score_threshold,
                nms_threshold=self.nms_threshold,
                top_k=5000,
                backend_id=cv2.dnn.DNN_BACKEND_OPENCV,
                target_id=cv2.dnn.DNN_TARGET_CPU,
            )

            self.recognizer = cv2.FaceRecognizerSF.create(
                model=self.sface_path,
                config="",
                backend_id=cv2.dnn.DNN_BACKEND_OPENCV,
                target_id=cv2.dnn.DNN_TARGET_CPU,
            )
            print("[Neura Vision] YuNet and SFace models loaded successfully.")
        except Exception as e:
            print(f"[Neura Vision] Error initializing vision models: {e}")
            raise

    # ------------------ PROFILE MANAGEMENT ------------------

    def load_owner_profile(self, profile_path: Optional[str] = None) -> bool:
        """Loads Rohit's enrolled embedding profile from disk."""
        target_path = profile_path or self.profile_path
        if not os.path.exists(target_path):
            return False

        try:
            with open(target_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.owner_profile.update(data)

            # Update thresholds if stored in profile
            if "cosine_threshold" in data:
                self.cosine_threshold = float(data["cosine_threshold"])
            if "l2_threshold" in data:
                self.l2_threshold = float(data["l2_threshold"])

            # Convert embeddings to numpy arrays
            raw_samples = data.get("sample_embeddings", [])
            self.owner_embeddings_np = [
                np.array(emb, dtype=np.float32).reshape(1, 128)
                for emb in raw_samples
                if len(emb) == 128
            ]

            raw_avg = data.get("average_embedding", [])
            if raw_avg and len(raw_avg) == 128:
                self.avg_embedding_np = np.array(raw_avg, dtype=np.float32).reshape(1, 128)
            elif self.owner_embeddings_np:
                # Recalculate average if missing
                stacked = np.vstack(self.owner_embeddings_np)
                mean_vec = np.mean(stacked, axis=0, keepdims=True)
                norm = np.linalg.norm(mean_vec)
                self.avg_embedding_np = (mean_vec / norm).astype(np.float32) if norm > 0 else mean_vec
            else:
                self.avg_embedding_np = None

            is_enrolled = (self.owner_profile.get("status") == "enrolled" and self.avg_embedding_np is not None)
            return is_enrolled
        except Exception as e:
            print(f"[Neura Vision] Error reading owner profile: {e}")
            return False

    def save_owner_profile(
        self,
        name: str = "Rohit",
        embeddings: Optional[List[np.ndarray]] = None,
        title: Optional[str] = None,
        profile_path: Optional[str] = None
    ) -> bool:
        """
        Saves the owner's face embeddings into owner_profile.json.
        Dynamically sets owner name and title without hardcoding.
        """
        target_path = profile_path or self.profile_path
        if not embeddings:
            embeddings = self.owner_embeddings_np

        if not embeddings:
            raise ValueError("No embeddings provided to save.")

        clean_name = name.strip()
        if not title:
            clean_title = f"Sri {clean_name}" if "rohit" in clean_name.lower() else clean_name
        else:
            clean_title = title.strip()

        # Ensure all embeddings are shape (1, 128) float32
        formatted_samples = []
        for emb in embeddings:
            vec = np.array(emb, dtype=np.float32).reshape(1, 128)
            formatted_samples.append(vec)

        stacked = np.vstack(formatted_samples)
        mean_vec = np.mean(stacked, axis=0, keepdims=True)
        norm = np.linalg.norm(mean_vec)
        if norm > 0:
            avg_vec = (mean_vec / norm).astype(np.float32)
        else:
            avg_vec = mean_vec.astype(np.float32)

        self.owner_embeddings_np = formatted_samples
        self.avg_embedding_np = avg_vec

        profile_data = {
            "name": clean_name,
            "title": clean_title,
            "status": "enrolled",
            "enrolled_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "samples_count": len(formatted_samples),
            "cosine_threshold": float(self.cosine_threshold),
            "l2_threshold": float(self.l2_threshold),
            "average_embedding": avg_vec.flatten().tolist(),
            "sample_embeddings": [sample.flatten().tolist() for sample in formatted_samples]
        }

        self.owner_profile = profile_data

        try:
            os.makedirs(os.path.dirname(os.path.abspath(target_path)), exist_ok=True)
            with open(target_path, "w", encoding="utf-8") as f:
                json.dump(profile_data, f, indent=4)
            print(f"[Neura Vision] Owner profile saved successfully for '{clean_name}' (Title: '{clean_title}') with {len(formatted_samples)} sample(s).")
        except Exception as e:
            print(f"[Neura Vision] Error saving owner profile: {e}")
            return False

        # Demote any other person previously marked as owner in known_faces
        for k, v in list(self.known_faces.items()):
            if v.get("role") == "owner" and k.lower() != clean_name.lower():
                v["role"] = "guest"

        # Register this owner in known_faces
        self.known_faces[clean_name] = {
            "name": clean_name,
            "title": clean_title,
            "role": "owner",
            "status": "enrolled",
            "enrolled_at": profile_data["enrolled_at"],
            "samples_count": len(formatted_samples),
            "average_embedding": avg_vec.flatten().tolist(),
            "sample_embeddings": [sample.flatten().tolist() for sample in formatted_samples]
        }
        self.known_embeddings_np[clean_name] = formatted_samples
        self.known_avg_embeddings_np[clean_name] = avg_vec
        self.save_known_faces()
        return True

    def is_owner_enrolled(self) -> bool:
        """Returns True if Rohit's embeddings are enrolled and ready."""
        return (
            self.owner_profile.get("status") == "enrolled"
            and (self.avg_embedding_np is not None or len(self.owner_embeddings_np) > 0)
        )

    # ------------------ MULTI-PERSON REGISTRY (ALL FACES) ------------------

    def load_known_faces(self, known_faces_path: Optional[str] = None) -> int:
        """
        Loads all enrolled persons from known_faces.json into memory.
        If known_faces.json does not exist yet, seeds it with Rohit's owner profile.
        """
        target_path = known_faces_path or self.known_faces_path
        self.known_faces = {}
        self.known_embeddings_np = {}
        self.known_avg_embeddings_np = {}

        if not os.path.exists(target_path):
            # Seed with owner if owner profile exists on disk
            if self.is_owner_enrolled():
                owner_name = self.owner_profile.get("name") or "Owner"
                owner_title = self.owner_profile.get("title") or (f"Sri {owner_name}" if "rohit" in owner_name.lower() else owner_name)
                self.known_faces[owner_name] = {
                    "name": owner_name,
                    "title": owner_title,
                    "role": "owner",
                    "status": "enrolled",
                    "enrolled_at": self.owner_profile.get("enrolled_at"),
                    "samples_count": self.owner_profile.get("samples_count", len(self.owner_embeddings_np)),
                    "average_embedding": self.owner_profile.get("average_embedding", []),
                    "sample_embeddings": self.owner_profile.get("sample_embeddings", [])
                }
                self.save_known_faces(target_path)
            else:
                return 0

        try:
            with open(target_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    self.known_faces = data
        except Exception as e:
            print(f"[Neura Vision] Error reading known faces from {target_path}: {e}")
            return 0

        # Guarantee owner is always in known_faces if enrolled
        if self.is_owner_enrolled():
            owner_name = self.owner_profile.get("name") or "Owner"
            owner_title = self.owner_profile.get("title") or (f"Sri {owner_name}" if "rohit" in owner_name.lower() else owner_name)
            # Demote any other person previously marked as owner
            for k, v in self.known_faces.items():
                if v.get("role") == "owner" and k.lower() != owner_name.lower():
                    v["role"] = "guest"
            if owner_name not in self.known_faces:
                self.known_faces[owner_name] = {
                    "name": owner_name,
                    "title": owner_title,
                    "role": "owner",
                    "status": "enrolled",
                    "enrolled_at": self.owner_profile.get("enrolled_at"),
                    "samples_count": self.owner_profile.get("samples_count", len(self.owner_embeddings_np)),
                    "average_embedding": self.owner_profile.get("average_embedding", []),
                    "sample_embeddings": self.owner_profile.get("sample_embeddings", [])
                }
            else:
                self.known_faces[owner_name]["role"] = "owner"
                self.known_faces[owner_name]["title"] = owner_title

        # Cache float32 numpy arrays for fast matching
        count = 0
        for name, pdata in self.known_faces.items():
            raw_samples = pdata.get("sample_embeddings", [])
            sample_nps = [
                np.array(emb, dtype=np.float32).reshape(1, 128)
                for emb in raw_samples
                if len(emb) == 128
            ]
            self.known_embeddings_np[name] = sample_nps

            raw_avg = pdata.get("average_embedding", [])
            if raw_avg and len(raw_avg) == 128:
                self.known_avg_embeddings_np[name] = np.array(raw_avg, dtype=np.float32).reshape(1, 128)
            elif sample_nps:
                stacked = np.vstack(sample_nps)
                mean_vec = np.mean(stacked, axis=0, keepdims=True)
                norm = np.linalg.norm(mean_vec)
                self.known_avg_embeddings_np[name] = (mean_vec / norm).astype(np.float32) if norm > 0 else mean_vec
            else:
                self.known_avg_embeddings_np[name] = None
            count += 1

        print(f"[Neura Vision] Loaded {count} known person(s): {list(self.known_faces.keys())}")
        return count

    def save_known_faces(self, target_path: Optional[str] = None) -> bool:
        """Saves current known_faces dictionary to JSON disk."""
        path = target_path or self.known_faces_path
        try:
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.known_faces, f, indent=4)
            return True
        except Exception as e:
            print(f"[Neura Vision] Error saving known faces: {e}")
            return False

    def enroll_person(
        self,
        name: str,
        embeddings: List[np.ndarray],
        role: str = "guest",
        title: Optional[str] = None
    ) -> bool:
        """
        Enrolls any person (owner or guest) into known_faces.json.
        Averages and normalizes the sample embeddings.
        If role is 'owner' or name is 'Rohit', syncs to owner_profile.json.
        """
        if not embeddings:
            raise ValueError("No embeddings provided to enroll person.")

        clean_name = name.strip()
        formatted_samples = [
            np.array(emb, dtype=np.float32).reshape(1, 128)
            for emb in embeddings
        ]

        stacked = np.vstack(formatted_samples)
        mean_vec = np.mean(stacked, axis=0, keepdims=True)
        norm = np.linalg.norm(mean_vec)
        avg_vec = (mean_vec / norm).astype(np.float32) if norm > 0 else mean_vec.astype(np.float32)

        person_entry = {
            "name": clean_name,
            "title": title or (f"Sri {clean_name}" if role == "owner" else clean_name),
            "role": role,
            "status": "enrolled",
            "enrolled_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "samples_count": len(formatted_samples),
            "average_embedding": avg_vec.flatten().tolist(),
            "sample_embeddings": [sample.flatten().tolist() for sample in formatted_samples]
        }

        self.known_faces[clean_name] = person_entry
        self.known_embeddings_np[clean_name] = formatted_samples
        self.known_avg_embeddings_np[clean_name] = avg_vec

        self.save_known_faces()

        # If owner or named Rohit, also sync with owner profile
        if role == "owner" or clean_name.lower() == "rohit":
            self.save_owner_profile(
                name=clean_name,
                embeddings=formatted_samples,
                title=title or "Sri Rohit Kumar Adak"
            )

        print(f"[Neura Vision] Successfully enrolled {clean_name} ({role}) with {len(formatted_samples)} sample(s).")
        return True

    def enroll_person_from_image(
        self,
        image_path: str,
        name: Optional[str] = None,
        role: str = "guest"
    ) -> Tuple[bool, str]:
        """
        Enrolls a person from a static image file.
        If name is None, automatically infers name from image filename!
        """
        if not os.path.exists(image_path):
            return False, f"Image file not found: {image_path}"

        frame = cv2.imread(image_path)
        if frame is None:
            return False, f"Could not read image: {image_path}"

        faces = self.detect_faces(frame)
        if not faces:
            return False, f"No face detected in {image_path}"

        best_face = max(faces, key=lambda f: f["bbox"][2] * f["bbox"][3])
        embedding = self.extract_embedding(frame, best_face["raw_face"])

        if not name or not name.strip():
            base_name = os.path.splitext(os.path.basename(image_path))[0]
            clean_name = base_name.replace("_", " ").replace("-", " ").strip().title()
        else:
            clean_name = name.strip()

        # If name is Rohit, role is owner
        if clean_name.lower() == "rohit":
            role = "owner"

        self.enroll_person(clean_name, [embedding], role=role)
        return True, f"Successfully enrolled {clean_name} from {os.path.basename(image_path)}"

    def enroll_person_from_folder(self, folder_path: str) -> Dict[str, Any]:
        """
        Scans an image folder and enrolls all images.
        Uses each image's filename as the person's name!
        """
        if not os.path.exists(folder_path) or not os.path.isdir(folder_path):
            return {"success": False, "message": f"Folder not found: {folder_path}", "enrolled": []}

        valid_extensions = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
        files = [
            f for f in os.listdir(folder_path)
            if os.path.splitext(f)[1].lower() in valid_extensions
        ]

        if not files:
            return {"success": False, "message": f"No image files found in {folder_path}", "enrolled": []}

        results = []
        for file in files:
            full_path = os.path.join(folder_path, file)
            ok, msg = self.enroll_person_from_image(full_path)
            results.append({"file": file, "success": ok, "message": msg})

        success_count = sum(1 for r in results if r["success"])
        return {
            "success": True,
            "total_files": len(files),
            "enrolled_count": success_count,
            "details": results
        }

    def delete_person(self, name: str) -> bool:
        """Deletes an enrolled person by name."""
        clean_name = name.strip()
        matched_key = None
        for k in self.known_faces:
            if k.lower() == clean_name.lower():
                matched_key = k
                break

        if not matched_key:
            return False

        del self.known_faces[matched_key]
        if matched_key in self.known_embeddings_np:
            del self.known_embeddings_np[matched_key]
        if matched_key in self.known_avg_embeddings_np:
            del self.known_avg_embeddings_np[matched_key]

        self.save_known_faces()
        print(f"[Neura Vision] Removed {matched_key} from known faces.")
        return True

    def get_known_persons(self) -> List[Dict[str, Any]]:
        """Returns list of summaries of all known persons."""
        summaries = []
        for name, data in self.known_faces.items():
            summaries.append({
                "name": name,
                "role": data.get("role", "guest"),
                "samples_count": data.get("samples_count", 1),
                "enrolled_at": data.get("enrolled_at")
            })
        return summaries

    def compare_with_known_faces(self, test_embedding: np.ndarray) -> Tuple[bool, str, bool, float, float]:
        """
        Compares test embedding against all enrolled persons in known_faces.
        Returns:
            (is_match: bool, identity: str, is_owner: bool, best_cosine: float, best_l2: float)
        """
        if not self.known_faces and not self.is_owner_enrolled():
            return False, "Not Enrolled", False, 0.0, 999.0

        if test_embedding is None or test_embedding.size != 128:
            return False, "Invalid Embedding", False, 0.0, 999.0

        test_embedding = test_embedding.reshape(1, 128).astype(np.float32)

        best_person = None
        best_cosine = -1.0
        best_l2 = 999.0

        for name, avg_emb in self.known_avg_embeddings_np.items():
            person_best_cos = -1.0
            person_best_l2 = 999.0

            if avg_emb is not None:
                cos = float(self.recognizer.match(test_embedding, avg_emb, cv2.FaceRecognizerSF_FR_COSINE))
                l2 = float(self.recognizer.match(test_embedding, avg_emb, cv2.FaceRecognizerSF_FR_NORM_L2))
                person_best_cos = max(person_best_cos, cos)
                person_best_l2 = min(person_best_l2, l2)

            # Compare against individual sample embeddings for maximum sensitivity
            samples = self.known_embeddings_np.get(name, [])
            for s in samples:
                cos = float(self.recognizer.match(test_embedding, s, cv2.FaceRecognizerSF_FR_COSINE))
                l2 = float(self.recognizer.match(test_embedding, s, cv2.FaceRecognizerSF_FR_NORM_L2))
                if cos > person_best_cos:
                    person_best_cos = cos
                if l2 < person_best_l2:
                    person_best_l2 = l2

            if person_best_cos > best_cosine:
                best_cosine = person_best_cos
                best_l2 = person_best_l2
                best_person = name

        is_match = (best_cosine >= self.cosine_threshold) or (best_l2 <= self.l2_threshold)
        if is_match and best_person:
            p_data = self.known_faces.get(best_person, {})
            current_owner_name = self.owner_profile.get("name", "").strip().lower()
            is_owner = (p_data.get("role") == "owner" or (current_owner_name and best_person.lower() == current_owner_name))
            return True, best_person, is_owner, best_cosine, best_l2
        else:
            return False, "Unknown", False, best_cosine, best_l2

    # ------------------ DETECTION & EMBEDDING PIPELINE ------------------

    def detect_faces(self, frame: np.ndarray, score_threshold: Optional[float] = None) -> List[Dict[str, Any]]:
        """
        Runs YuNet face detector on input frame.
        Returns list of detected face dictionaries:
        [{"bbox": (x, y, w, h), "landmarks": [(x,y), ...], "score": float, "raw_face": ndarray}]
        """
        if frame is None or self.detector is None:
            return []

        h, w = frame.shape[:2]
        if (w, h) != self.last_input_size:
            self.detector.setInputSize((w, h))
            self.last_input_size = (w, h)

        if score_threshold is not None and score_threshold != self.score_threshold:
            self.detector.setScoreThreshold(score_threshold)
            self.score_threshold = score_threshold

        _, faces = self.detector.detect(frame)

        if faces is None or len(faces) == 0:
            return []

        results = []
        for face in faces:
            x, y, bw, bh = int(face[0]), int(face[1]), int(face[2]), int(face[3])
            # Bounding box safety clipping
            x = max(0, x)
            y = max(0, y)
            bw = min(w - x, bw)
            bh = min(h - y, bh)

            landmarks = face[4:14].reshape((5, 2)).astype(int)
            conf_score = float(face[14])

            results.append({
                "bbox": (x, y, bw, bh),
                "landmarks": landmarks,
                "score": conf_score,
                "raw_face": face
            })

        return results

    def extract_embedding(self, frame: np.ndarray, raw_face: np.ndarray) -> np.ndarray:
        """
        Uses SFace to crop, align, and extract a 128-dimensional embedding from the detected face.
        """
        if self.recognizer is None:
            raise RuntimeError("SFace recognizer is not initialized.")

        aligned_face = self.recognizer.alignCrop(frame, raw_face)
        embedding = self.recognizer.feature(aligned_face)
        return embedding

    def compare_with_owner(self, test_embedding: np.ndarray) -> Tuple[bool, str, float, float]:
        """
        Compares test embedding against Rohit's enrolled embeddings.
        Returns:
            (is_match: bool, identity: str, cosine_score: float, l2_score: float)
        """
        is_match, identity, is_owner, cos_score, l2_score = self.compare_with_known_faces(test_embedding)
        if is_owner:
            return True, identity, cos_score, l2_score
        return False, identity if is_match else "Unknown", cos_score, l2_score

    def process_frame(
        self,
        frame: np.ndarray,
        draw_overlay: bool = True,
        mirror_display: bool = True
    ) -> Tuple[List[Dict[str, Any]], np.ndarray]:
        """
        Executes complete pipeline on a single frame:
        YuNet Detection -> SFace Embedding -> Compare with Known Faces -> Identity Labeling.

        Args:
            frame: Raw camera frame (BGR).
            draw_overlay: If True, draws bounding boxes, landmarks, and identity pill.
            mirror_display: If True, creates a true mirror view (selfie camera) where moving
                           head right moves right, and HUD text is drawn readable and upright.
        """
        if draw_overlay:
            annotated_frame = cv2.flip(frame, 1) if mirror_display else frame.copy()
        else:
            annotated_frame = frame

        detected_faces = self.detect_faces(frame)
        results = []

        for face_info in detected_faces:
            raw_face = face_info["raw_face"]
            bbox = face_info["bbox"]
            landmarks = face_info["landmarks"]
            det_score = face_info["score"]

            # Extract SFace embedding from original frame
            embedding = self.extract_embedding(frame, raw_face)

            # Compare with all known faces (Rohit or others)
            is_match, identity, is_owner, cosine_score, l2_score = self.compare_with_known_faces(embedding)

            res = {
                "identity": identity,
                "is_owner": is_owner,
                "is_known": is_match,
                "confidence": cosine_score,
                "l2_distance": l2_score,
                "detection_score": det_score,
                "bbox": bbox,
                "landmarks": landmarks,
                "embedding": embedding,
                "raw_face": raw_face
            }
            results.append(res)

            if draw_overlay:
                self._draw_face_overlay(annotated_frame, res, is_mirrored=mirror_display)

        return results, annotated_frame

    def _draw_face_overlay(self, frame: np.ndarray, face_res: Dict[str, Any], is_mirrored: bool = False):
        """Draws visual HUD overlay bounding box and identity text."""
        x_raw, y_raw, w_raw, h_raw = face_res["bbox"]
        is_owner = face_res.get("is_owner", False)
        is_known = face_res.get("is_known", False)
        identity = face_res["identity"]
        cos_score = face_res["confidence"]
        landmarks_raw = face_res["landmarks"]
        frame_w = frame.shape[1]

        # Convert coordinates if frame was mirrored
        if is_mirrored:
            x = frame_w - (x_raw + w_raw)
            y = y_raw
            w = w_raw
            h = h_raw
            landmarks = [(frame_w - lx, ly) for lx, ly in landmarks_raw]
        else:
            x, y, w, h = x_raw, y_raw, w_raw, h_raw
            landmarks = landmarks_raw

        # Color scheme:
        # Green for Owner (Rohit)
        # Cyan / Sky Blue for Known Guests (Sneha, etc.)
        # Red for Unknown
        if not self.is_owner_enrolled() and not self.known_faces:
            box_color = (255, 180, 0) # Cyan/Yellow
            label_text = f"Face ({cos_score:.2f}) [No Profile]"
        elif is_owner:
            box_color = (0, 220, 60) # Neon Green
            label_text = f"{identity} (Owner) [{cos_score:.2f}]"
        elif is_known:
            box_color = (255, 200, 0) # Electric Cyan / Sky Blue in BGR
            label_text = f"{identity} [{cos_score:.2f}]"
        else:
            box_color = (0, 40, 220) # Bright Red
            label_text = f"Unknown [{cos_score:.2f}]"

        # Draw tech corner bounding box
        cv2.rectangle(frame, (x, y), (x + w, y + h), box_color, 2)
        corner_len = min(20, w // 4, h // 4)
        thickness = 3
        # Top-left corner
        cv2.line(frame, (x, y), (x + corner_len, y), box_color, thickness)
        cv2.line(frame, (x, y), (x, y + corner_len), box_color, thickness)
        # Top-right corner
        cv2.line(frame, (x + w, y), (x + w - corner_len, y), box_color, thickness)
        cv2.line(frame, (x + w, y), (x + w, y + corner_len), box_color, thickness)
        # Bottom-left corner
        cv2.line(frame, (x, y + h), (x + corner_len, y + h), box_color, thickness)
        cv2.line(frame, (x, y + h), (x, y + h - corner_len), box_color, thickness)
        # Bottom-right corner
        cv2.line(frame, (x + w, y + h), (x + w - corner_len, y + h), box_color, thickness)
        cv2.line(frame, (x + w, y + h), (x + w, y + h - corner_len), box_color, thickness)

        # Draw 5 facial landmarks (eyes, nose, mouth corners)
        landmark_colors = [
            (255, 0, 0),    # right eye (blue)
            (0, 0, 255),    # left eye (red)
            (0, 255, 0),    # nose tip (green)
            (255, 255, 0),  # right mouth corner
            (0, 255, 255),  # left mouth corner
        ]
        for idx, (lx, ly) in enumerate(landmarks):
            col = landmark_colors[idx] if idx < len(landmark_colors) else (255, 255, 255)
            cv2.circle(frame, (lx, ly), 3, col, -1)

        # Draw badge label with background pill
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.55
        (tw, th), baseline = cv2.getTextSize(label_text, font, font_scale, 1)

        pill_margin = 6
        if y - th - 12 >= 0:
            pill_y1 = y - th - 12
            pill_y2 = y
            text_y = y - 5
        else:
            pill_y1 = y + h
            pill_y2 = y + h + th + 12
            text_y = y + h + th + 6

        pill_x1 = max(0, x)
        pill_x2 = min(frame_w, x + tw + (pill_margin * 2))

        cv2.rectangle(frame, (pill_x1, pill_y1), (pill_x2, pill_y2), box_color, -1)
        cv2.putText(
            frame,
            label_text,
            (pill_x1 + pill_margin, text_y),
            font,
            font_scale,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )

    # ------------------ CAMERA CAPTURE PIPELINE ------------------

    def recognize_from_camera(
        self,
        camera_index: int = 0,
        timeout_seconds: float = 6.0,
        consecutive_matches: int = 3,
        show_window: bool = False,
        window_title: str = "Neura Vision - Face Recognition"
    ) -> Dict[str, Any]:
        """
        Activates webcam, streams frames, and performs real-time recognition.
        Returns when owner identity is confirmed or timeout expires.
        """
        cap = cv2.VideoCapture(camera_index)
        if not cap.isOpened():
            return {
                "success": False,
                "identity": "Unknown",
                "is_owner": False,
                "confidence": 0.0,
                "message": "Camera could not be accessed. Please ensure webcam is connected.",
                "frame": None
            }

        start_time = time.time()
        rohit_match_count = 0
        guest_match_count = 0
        unknown_match_count = 0
        best_guest_name = "Unknown"
        best_cosine = -1.0
        best_frame = None
        last_results = []

        try:
            while time.time() - start_time < timeout_seconds:
                ret, frame = cap.read()
                if not ret:
                    time.sleep(0.03)
                    continue

                # Process frame: mirror display feed with upright, readable HUD text
                results, annotated = self.process_frame(
                    frame,
                    draw_overlay=True,
                    mirror_display=True
                )

                if show_window:
                    cv2.imshow(window_title, annotated)
                    key = cv2.waitKey(1) & 0xFF
                    if key == 27 or key == ord('q'):
                        break

                if results:
                    last_results = results
                    # Check first/primary face
                    primary = results[0]
                    cos = primary["confidence"]
                    if cos > best_cosine:
                        best_cosine = cos
                        best_frame = frame.copy()

                    if primary["is_owner"]:
                        rohit_match_count += 1
                        if rohit_match_count >= consecutive_matches:
                            owner_name = self.owner_profile.get("name") or primary["identity"]
                            return {
                                "success": True,
                                "identity": owner_name,
                                "is_owner": True,
                                "confidence": best_cosine,
                                "message": f"Successfully recognized {owner_name} with confidence {best_cosine:.2f}.",
                                "frame": best_frame
                            }
                    elif primary.get("is_known", False):
                        guest_match_count += 1
                        best_guest_name = primary["identity"]
                        if guest_match_count >= consecutive_matches:
                            return {
                                "success": True,
                                "identity": best_guest_name,
                                "is_owner": False,
                                "confidence": best_cosine,
                                "message": f"Successfully recognized {best_guest_name} with confidence {best_cosine:.2f}.",
                                "frame": best_frame
                            }
                    else:
                        unknown_match_count += 1

                time.sleep(0.02)

            # Timeout reached: determine conclusion based on best detection
            owner_name = self.owner_profile.get("name") or "Owner"
            if rohit_match_count > 0 and best_cosine >= self.cosine_threshold:
                return {
                    "success": True,
                    "identity": owner_name,
                    "is_owner": True,
                    "confidence": best_cosine,
                    "message": f"Recognized {owner_name} with similarity {best_cosine:.2f}.",
                    "frame": best_frame
                }
            elif guest_match_count > 0 and best_cosine >= self.cosine_threshold:
                return {
                    "success": True,
                    "identity": best_guest_name,
                    "is_owner": False,
                    "confidence": best_cosine,
                    "message": f"Recognized {best_guest_name} with similarity {best_cosine:.2f}.",
                    "frame": best_frame
                }
            elif unknown_match_count > 0:
                return {
                    "success": False,
                    "identity": "Unknown",
                    "is_owner": False,
                    "confidence": max(0.0, best_cosine),
                    "message": "Human face detected, but identity is unknown.",
                    "frame": best_frame
                }
            else:
                return {
                    "success": False,
                    "identity": "None",
                    "is_owner": False,
                    "confidence": 0.0,
                    "message": "No face was detected in front of the camera.",
                    "frame": None
                }
        finally:
            cap.release()
            if show_window:
                cv2.destroyWindow(window_title)

    # ------------------ MEMORY / STATE SYNCHRONIZATION ------------------

    def update_neura_state(self, recognition_result: Dict[str, Any], memory_manager: Any = None) -> str:
        """
        Updates Neura's memory and state based on identity outcome.
        - Updates user_facts (name, identity_status, last_seen)
        - Logs to activity_log
        - Returns a spoken greeting/notification for Neura.
        """
        identity = recognition_result.get("identity", "Unknown")
        is_owner = recognition_result.get("is_owner", False)
        confidence = recognition_result.get("confidence", 0.0)

        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        owner_display_name = self.owner_profile.get("name") or "Sir"
        owner_display_title = self.owner_profile.get("title") or owner_display_name

        if memory_manager:
            try:
                if is_owner:
                    # Sync with owner's memory
                    memory_manager.user_memory["user_facts"]["name"] = owner_display_name
                    memory_manager.user_memory["user_facts"]["presence"] = "present"
                    memory_manager.user_memory["user_facts"]["face_authenticated"] = True
                    memory_manager.user_memory["user_facts"]["last_face_verification"] = now_str
                    memory_manager.log_activity(f"Visual authentication: {owner_display_name} verified with similarity {confidence:.2f}")
                    memory_manager.save_user_memory()
                elif identity != "Unknown" and identity != "None":
                    memory_manager.user_memory["user_facts"]["presence"] = f"guest_{identity}_present"
                    memory_manager.log_activity(f"Visual scan: Guest {identity} verified (similarity: {confidence:.2f})")
                    memory_manager.save_user_memory()
                elif identity == "Unknown":
                    memory_manager.user_memory["user_facts"]["presence"] = "unknown_person_present"
                    memory_manager.user_memory["user_facts"]["face_authenticated"] = False
                    memory_manager.log_activity(f"Visual scan: Unknown person detected (similarity: {confidence:.2f})")
                    memory_manager.save_user_memory()
                else:
                    memory_manager.user_memory["user_facts"]["presence"] = "absent"
                    memory_manager.log_activity("Visual scan: No face detected")
                    memory_manager.save_user_memory()
            except Exception as e:
                print(f"[Neura Vision] Error syncing with memory manager: {e}")

        # Generate response message for Neura to speak
        if is_owner:
            return f"Identity verified! Welcome back, {owner_display_name} Sir."
        elif identity != "Unknown" and identity != "None":
            return f"Hello {identity}! Nice to see you."
        elif identity == "Unknown":
            return "Unknown face detected. Please tell me your name."
        else:
            return "No face is detected in front of the camera, Sir."


# Singleton instance helper
_global_face_system: Optional[FaceRecognitionSystem] = None

def get_face_system() -> FaceRecognitionSystem:
    """Returns singleton instance of FaceRecognitionSystem."""
    global _global_face_system
    if _global_face_system is None:
        _global_face_system = FaceRecognitionSystem()
    return _global_face_system

def recognize_owner_from_camera(timeout_sec: float = 5.0, show_feed: bool = False) -> Dict[str, Any]:
    """Convenience helper to run camera face recognition pipeline."""
    system = get_face_system()
    return system.recognize_from_camera(timeout_seconds=timeout_sec, show_window=show_feed)
