"""
CS6.201 Black-Box Facial Recognition Module
DO NOT MODIFY THIS FILE.

Dependencies (add to your uv project):
    uv add face-recognition numpy Pillow
"""

import base64
import io

import face_recognition
import numpy as np
from PIL import Image


def _to_bytes(data):
    """
    Accepts either raw bytes or a Base64-encoded string and always returns bytes.
    This allows callers to pass image data in either form.
    """
    if isinstance(data, (bytes, bytearray)):
        return bytes(data)
    if isinstance(data, str):
        return base64.b64decode(data)
    raise TypeError(f"Expected bytes or Base64 string, got {type(data).__name__}")


def get_face_encoding(image_data):
    """
    Accepts raw bytes or a Base64 string, locates the first face found,
    and returns its 128-d encoding. Returns None if no face is detected.
    """
    try:
        image_bytes = _to_bytes(image_data)
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        image_np = np.array(image)

        face_locations = face_recognition.face_locations(image_np)
        if not face_locations:
            return None

        encodings = face_recognition.face_encodings(image_np, face_locations)
        if not encodings:
            return None

        return encodings[0]

    except Exception as e:
        print(f"Error encoding image: {e}")
        return None


def find_closest_match(login_image_data, db_images_dict):
    """
    Compares a login attempt against a dictionary of known profile images.

    :param login_image_data:
        The webcam capture as raw bytes or a Base64 string.
    :param db_images_dict:
        A dictionary mapping { uid: image_data } fetched from MongoDB,
        where each value may be raw bytes or a Base64 string.
    :return:
        The UID of the closest matching face, or None if no face is
        detected in the login frame or no match clears the threshold.
    """
    print("Processing login frame...")
    login_encoding = get_face_encoding(login_image_data)

    if login_encoding is None:
        print("No face detected in login frame.")
        return None

    best_match_uid = None
    best_distance = float("inf")

    print(f"Comparing against {len(db_images_dict)} records in database...")
    for uid, db_img_data in db_images_dict.items():
        db_encoding = get_face_encoding(db_img_data)
        if db_encoding is None:
            continue

        distance = face_recognition.face_distance([db_encoding], login_encoding)[0]
        if distance < best_distance:
            best_distance = distance
            best_match_uid = uid

    threshold = 0.5
    if best_distance <= threshold:
        print(f"Match found: UID={best_match_uid}  distance={best_distance:.3f}")
        return best_match_uid

    print(
        f"No match found. Closest distance was {best_distance:.3f} "
        f"(threshold is <= {threshold})"
    )
    return None
