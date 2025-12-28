import os
import firebase_admin
from firebase_admin import credentials, firestore, storage
from datetime import datetime, timedelta
import time
import requests
from urllib.parse import quote


#  Environment Variables
API_KEY = os.getenv("FIREBASE_API_KEY")
SERVICE_JSON = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
BUCKET_NAME = os.getenv("FIREBASE_BUCKET")

if not all([API_KEY, SERVICE_JSON, BUCKET_NAME]):
    raise RuntimeError("Missing Firebase environment variables.")


#  Firebase Admin Init
if not firebase_admin._apps:
    cred = credentials.Certificate(SERVICE_JSON)
    firebase_admin.initialize_app(cred, {"storageBucket": BUCKET_NAME})

db = firestore.client()
bucket = storage.bucket()


#  Auth REST APIs
def firebase_register(email, password):
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={API_KEY}"
    payload = {"email": email, "password": password, "returnSecureToken": True}

    r = requests.post(url, json=payload)
    try:
        r.raise_for_status()
    except requests.HTTPError:
        raise Exception(r.json()["error"]["message"])
    return r.json()


def firebase_login(email, password):
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={API_KEY}"
    payload = {"email": email, "password": password, "returnSecureToken": True}
    r = requests.post(url, json=payload)
    r.raise_for_status()
    return r.json()


#  Save / Load History
def save_history(uid, project_id, score, feedback, audio_path, slide_image_path):
    ts = int(time.time())

    # Upload recording (private)
    audio_path_cloud = f"users/{uid}/projects/{project_id}/recordings/{ts}.wav"
    bucket.blob(audio_path_cloud).upload_from_filename(
        audio_path, content_type="audio/wav"
    )

    # Upload slide preview (private)
    slide_path_cloud = f"users/{uid}/projects/{project_id}/slides/{ts}.png"
    bucket.blob(slide_path_cloud).upload_from_filename(
        slide_image_path, content_type="image/png"
    )

    # Firestore record (store only storage paths)
    project_ref = (
        db.collection("users")
        .document(uid)
        .collection("projects")
        .document(project_id)
    )

    project_ref.collection("history").add(
        {
            "score": score,
            "feedback": feedback,
            "audio_storage_path": audio_path_cloud,
            "slide_storage_path": slide_path_cloud,
            "timestamp": datetime.now(),
        }
    )


def load_history(uid, project_id):
    ref = (
        db.collection("users")
        .document(uid)
        .collection("projects")
        .document(project_id)
        .collection("history")
        .order_by("timestamp", direction=firestore.Query.DESCENDING)
    )
    return [d.to_dict() for d in ref.stream()]
