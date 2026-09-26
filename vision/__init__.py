"""
Neura Vision Module
Provides Face Detection (YuNet) and Face Recognition (SFace) pipeline.
"""

from .face_recognition import (
    FaceRecognitionSystem,
    get_face_system,
    recognize_owner_from_camera,
    ensure_models_exist,
    DEFAULT_COSINE_THRESHOLD,
    DEFAULT_L2_THRESHOLD
)

__all__ = [
    "FaceRecognitionSystem",
    "get_face_system",
    "recognize_owner_from_camera",
    "ensure_models_exist",
    "DEFAULT_COSINE_THRESHOLD",
    "DEFAULT_L2_THRESHOLD"
]
