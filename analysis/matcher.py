"""
MODULE ROLE: Data Correlation & Analytics Engine
DESCRIPTION: Synchronizes multi-modal data (Audio, Text, Timing) 
             to evaluate presentation performance based on weighted metrics.
"""

import json
import os
import string
import nltk
import math
import statistics
import librosa
import numpy as np
from nltk.stem import WordNetLemmatizer
from sentence_transformers import SentenceTransformer, util
import torch
from dotenv import load_dotenv


load_dotenv()

def load_config():
    """Load scoring weights and thresholds from environment variables."""
    return {
        "semantic_threshold_strict": float(os.getenv("SEMANTIC_THRESHOLD_STRICT", 0.28)),
        "semantic_threshold_weak": float(os.getenv("SEMANTIC_THRESHOLD_WEAK", 0.15)),
        "weight_content": float(os.getenv("WEIGHT_CONTENT", 0.3)),
        "weight_fluency": float(os.getenv("WEIGHT_FLUENCY", 0.4)),
        "weight_tone": float(os.getenv("WEIGHT_TONE", 0.3)),
        "ideal_wpm_low": int(os.getenv("IDEAL_WPM_LOW", 130)),
        "ideal_wpm_high": int(os.getenv("IDEAL_WPM_HIGH", 160))
    }

CONFIG = load_config()
STRICT_THR = CONFIG["semantic_threshold_strict"]
WEAK_THR = CONFIG["semantic_threshold_weak"]


# ---------------- NLP / MODEL INIT ---------------- #

lemmatizer = WordNetLemmatizer()
_semantic_model = None


def _get_model():
    """Singleton：SentenceTransformer 只載一次。"""
    global _semantic_model
    if _semantic_model is None:
        print("[INFO] Loading Semantic AI model (all-MiniLM-L6-v2)...")
        _semantic_model = SentenceTransformer("all-MiniLM-L6-v2")
    return _semantic_model


def _clean_and_lemmatize(text: str) -> set:

    """Normalize text using cleaning and lemmatization."""

    if not text:
        return set()
    text = text.lower()
    text = text.translate(str.maketrans("", "", string.punctuation))
    words = text.split()
    cleaned = set()
    for w in words:
        cleaned.add(lemmatizer.lemmatize(w, pos="n"))
        cleaned.add(lemmatizer.lemmatize(w, pos="v"))
        cleaned.add(w)
    return cleaned


# ---------------- AUDIO METRICS ---------------- #

def _calculate_pitch_variability(audio_path: str, start_t: float, end_t: float) -> float:
    """Calculate pitch standard deviation using librosa."""  
    try:
        if end_t <= start_t:
            return 0.0

        y, sr = librosa.load(audio_path, offset=start_t, duration=(end_t - start_t))

        pitches, _, _ = librosa.pyin(
            y,
            fmin=librosa.note_to_hz("C2"),
            fmax=librosa.note_to_hz("C7"),
        )

        if pitches is None:
            return 0.0

        valid = pitches[~np.isnan(pitches)]
        if len(valid) > 1:
            return round(float(np.std(valid)), 2)

        return 0.0
    except Exception as e:
        print(f"[WARN] Pitch analysis failed for segment {start_t}-{end_t}: {e}")
        return 0.0


# ---------------- CORE PIPELINE ---------------- #
def _calculate_overall_score(content_score, wpm, mumble_rate, filler_count, pitch_var, duration, has_text):
    """Weighted final score calculation (3:4:3 ratio)."""
    if not has_text or duration <= 0:
        return 0.0

    # 1. Content (30%)
    score_content = (content_score or 0.0) * CONFIG["weight_content"]

    # 2. Fulency (40%)
    low = CONFIG["ideal_wpm_low"]
    high = CONFIG["ideal_wpm_high"]
    if low <= wpm <= high:
        wpm_score = 100
    else:
        dist = min(abs(wpm - low), abs(wpm - high))
        wpm_score = max(0, 100 - dist * 1.5)
    
    mumble_penalty = mumble_rate * 2.0
    fpm = (filler_count / duration) * 60 
    filler_penalty = fpm * 5.0           
    
    score_fluency = max(0, (wpm_score - mumble_penalty - filler_penalty)) * CONFIG["weight_fluency"]

    # 3. Tone(30%)
    score_tone = min(100, (pitch_var / 15.0) * 100) * CONFIG["weight_tone"]

    return round(score_content + score_fluency + score_tone, 1)


def run_comprehensive_analysis(
    slide_json_path: str,
    whisper_json_path: str,
    timing_json_path: str,
    audio_path: str,
    output_json_path: str,
):

    semantic_model = _get_model()

    if not all(
        os.path.exists(p)
        for p in [slide_json_path, whisper_json_path, timing_json_path, audio_path]
    ):
        raise FileNotFoundError(
            "Required input files are missing (slides, whisper, timing, or audio)."
        )

    print("[INFO] Starting comprehensive analysis pipeline...")

    with open(slide_json_path, "r", encoding="utf-8") as f:
        slides = json.load(f)
    with open(whisper_json_path, "r", encoding="utf-8") as f:
        segments = json.load(f)["segments"]
    with open(timing_json_path, "r", encoding="utf-8") as f:
        timings = json.load(f)

    
    HAS_SPEECH_THRESHOLD = 0.30

    for i, slide in enumerate(slides):

        # -------- A. TIME ALIGNMENT -------- #
        if i < len(timings):
            start_t = timings[i]["start_time"]
            end_t = timings[i]["end_time"]

            if end_t < start_t:
                end_t = start_t

            slide["start_time"] = start_t
            slide["end_time"] = end_t
        else:
            slide["start_time"] = None
            slide["end_time"] = None
            slide["content_analysis"] = {"error": "No timing data"}
            slide["tone_analysis"] = {"error": "No timing data"}
            slide["metrics"] = {"error": "No timing data"}
            print(f"[WARN] Page {slide.get('page_index', i)} has no timing entry.")
            continue

        # -------- B. SEGMENT COLLECTION -------- #
        page_texts = []
        page_logprobs = []
        matched_segments = []
        mumbled = []
        fillers = []  
        total_words = 0

        for seg in segments:
            seg_start = seg.get("voice_start", seg.get("start", 0.0))
            seg_end = seg.get("voice_end", seg.get("end", 0.0))

            overlap = min(end_t, seg_end) - max(start_t, seg_start)

            if overlap > 0.15:
                if seg.get("no_speech_prob", 0.0) > 0.97:
                    continue

                text = seg.get("text", "")
                page_texts.append(text)
                page_logprobs.append(seg.get("avg_logprob", -1.0))
                matched_segments.append(seg)

                total_words += len(text.split())
                if "mumbled_words" in seg:
                    mumbled.extend(seg["mumbled_words"])

                if "filler_words" in seg:
                    fillers.extend(seg["filler_words"])

        full_text = " ".join(t for t in page_texts if t)

        # -------- C. SEMANTIC EMBEDDINGS -------- #
        sentences = nltk.sent_tokenize(full_text) if full_text else []
        if not sentences and full_text:
            sentences = [full_text]

        user_embeddings = (
            semantic_model.encode(sentences, convert_to_tensor=True)
            if sentences
            else None
        )

        # -------- D. CONFIDENCE -------- #
        if page_logprobs:
            confidence_score = math.exp(statistics.mean(page_logprobs)) * 100
        else:
            confidence_score = 0.0
        confidence_level = "High" if confidence_score >= 60 else "Low"

        # -------- E. KEYWORD MATCHING -------- #
        spoken = _clean_and_lemmatize(full_text)
        keywords_map = slide.get("keywords_expanded", {})
        clean_str = full_text.replace(" ", "").lower()

        #  prenormalize synonyms
        normalized = {}
        for k, syns in keywords_map.items():
            norm = set()
            for s in syns:
                norm |= _clean_and_lemmatize(s)
            normalized[k] = norm

        covered = []
        missed = []

        for original_key, synonyms in keywords_map.items():
            is_match = False

            # Level 1: exact / lemma
            if not normalized[original_key].isdisjoint(spoken):
                is_match = True

            # Level 2: substring 
            elif any(s.replace(" ", "").lower() in clean_str for s in synonyms):
                is_match = True

            # Level 3: semantic 
            if not is_match and user_embeddings is not None:
                candidates = [original_key] + list(synonyms)
                key_emb = semantic_model.encode(candidates, convert_to_tensor=True)
                cosine = util.cos_sim(key_emb, user_embeddings)
                best = torch.max(cosine).item()

                if best >= WEAK_THR:
                    is_match = True

            if is_match:
                covered.append(original_key)
            else:
                missed.append(original_key)

        # -------- F. SCORES / METRICS -------- #
        total = len(keywords_map)
        content_score = (len(covered) / total * 100) if total > 0 else 100.0

        pitch_var = _calculate_pitch_variability(audio_path, start_t, end_t)

        overlap_speech = 0.0
        for seg in segments:
            seg_start = seg.get("voice_start", seg.get("start", 0.0))
            seg_end = seg.get("voice_end", seg.get("end", 0.0))
            overlap = min(end_t, seg_end) - max(start_t, seg_start)
            if overlap > 0:
                overlap_speech += overlap
        wpm = 0.0
        mumble_rate = 0.0
        content_status = "OK"

        # Case 1: segments match
        if matched_segments:
            real_start = matched_segments[0].get(
                "voice_start", matched_segments[0].get("start", start_t)
            )
            real_end = matched_segments[-1].get(
                "voice_end", matched_segments[-1].get("end", end_t)
            )

            duration = max(1e-6, real_end - real_start)

            if total_words > 0:
                wpm = (total_words / duration) * 60.0
                mumble_rate = (len(mumbled) / total_words) * 100.0
            else:
                wpm = 0.0
                mumble_rate = 0.0

        # Case 2:no match 
        elif overlap_speech > HAS_SPEECH_THRESHOLD:
            content_status = "Speech Not Captured"
            wpm = 0.0
            mumble_rate = 0.0

        # Case 3: No Speech Detected
        else:
            content_status = "No Speech Detected"
            pitch_var = 0.0
            wpm = 0.0
            mumble_rate = 0.0

        has_text = bool(matched_segments)
        duration = max(1e-6, end_t - start_t) 

        total_overall = _calculate_overall_score(
            content_score, wpm, mumble_rate, len(fillers), pitch_var, duration, has_text
        )

        slide["overall_score"] = total_overall

        # 2. Content
        slide["content_analysis"] = {
            "score": round(content_score, 1) if has_text else 0.0,
            "covered_keywords": covered if has_text else [],
            "missed_keywords": missed if has_text else [],
            "filler_count": len(fillers), 
            "transcript_extract": full_text if has_text else "",
            "confidence_score": round(confidence_score, 1) if has_text else 0.0,
            "confidence_level": confidence_level if has_text else "None",
            "status": content_status,
        }

        # 3. Tone
        slide["tone_analysis"] = {
            "pitch_variability": pitch_var,
            "status": (
                "Dynamic"
                if pitch_var > 12.0 and overlap_speech > HAS_SPEECH_THRESHOLD
                else (
                    "Monotone"
                    if overlap_speech > HAS_SPEECH_THRESHOLD
                    else "Unknown"
                )
            ),
        }

        slide["metrics"] = {
            "wpm": round(wpm, 1),
            "mumble_rate": round(mumble_rate, 1),
            "filler_rate_pm": round((len(fillers) / duration) * 60, 1), # 贅字率
            "status": (
                "Excellent" if total_overall >= 85 else
                "Pass" if has_text and mumble_rate <= 20.0 else 
                ("Unclear Speech" if has_text else content_status)
            ),
        }

        print(
            f"Page {slide.get('page_index', i)}: "
            f"Overall={total_overall} | "
            f"Content={slide['content_analysis']['score']} | "
            f"Filler/min={slide['metrics']['filler_rate_pm']}"
        )

    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(slides, f, indent=2, ensure_ascii=False)

    print("--------------------------------")
    print(f"[SUCCESS] Final report saved: {output_json_path}")
    return slides


if __name__ == "__main__":
    run_comprehensive_analysis(
        slide_json_path="data/slides/slides_with_synonyms.json",
        whisper_json_path="temp_data/whisper_output.json",
        timing_json_path="data/slides/changePage.json",
        audio_path="temp_data/audio.wav",
        output_json_path="temp_data/final_report.json",
    )
