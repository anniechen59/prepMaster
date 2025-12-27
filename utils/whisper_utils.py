import json
import os
import re
from faster_whisper import WhisperModel
from dotenv import load_dotenv

load_dotenv()

# Environment Configurations
WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "base")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", 0.75))
MAX_GAP_DURATION = float(os.getenv("MAX_GAP_DURATION", 0.7))

# Common English filler words for detection
FILLER_WORDS_LIST = {"uh", "um", "ah", "er", "uhm", "well", "like", "know"}

def _generate_whisper_prompt(json_path):
    if not os.path.exists(json_path):
        return None
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            slides = json.load(f)
    except Exception:
        return None

    keywords = set()
    for slide in slides:
        text = slide.get("slide_text", "").replace("\n", " ")
        words = re.findall(r'\b[A-Za-z0-9-]{3,}\b', text)
        for w in words:
            if w[0].isupper() or any(c.isdigit() for c in w) or len(w) > 4:
                keywords.add(w)
    
    # Guide Whisper to preserve filler sounds and focus on slide context
    filler_guide = "Uh, um, ah, er, you know, like... "
    prompt_str = filler_guide + "Context: " + ", ".join(sorted(list(keywords)))
    return prompt_str[:800]

def create_segment_object(seg_id, words, threshold):
    text = "".join([w.word for w in words]).strip()
    low_conf_words = []
    filler_words = []
    
    for w in words:
        word_str = w.word.strip().lower().replace(".", "").replace(",", "")
        
        # Detect Mumbles (Low Confidence)
        if w.probability < threshold:
            low_conf_words.append({
                "word": w.word.strip(),
                "conf": round(w.probability, 2),
                "start": round(w.start, 2)
            })
            
        # Detect Fillers
        if word_str in FILLER_WORDS_LIST:
            filler_words.append({
                "word": word_str,
                "start": round(w.start, 2),
                "end": round(w.end, 2)
            })

    return {
        "id": seg_id,
        "voice_start": round(words[0].start, 2),
        "voice_end": round(words[-1].end, 2),
        "text": text,
        "mumbled_words": low_conf_words,
        "filler_words": filler_words
    }

def run_whisper_analysis(audio_path, slide_json_path, output_json_path):
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    my_prompt = _generate_whisper_prompt(slide_json_path)
    
    print(f"[INFO] Initializing Whisper ({WHISPER_MODEL_SIZE}) on {WHISPER_DEVICE}...")
    model = WhisperModel(
        WHISPER_MODEL_SIZE, 
        device=WHISPER_DEVICE, 
        compute_type=WHISPER_COMPUTE_TYPE
    )

    segments_generator, info = model.transcribe(
        audio_path,
        language="en",
        initial_prompt=my_prompt,
        word_timestamps=True,
        beam_size=5,
        vad_filter=True, 
        vad_parameters=dict(min_silence_duration_ms=300), 
        condition_on_previous_text=False 
    )

    all_words = []
    for seg in segments_generator:
        if seg.words:
            all_words.extend(seg.words)

    if not all_words:
        return {"segments": []}

    # Re-segmenting based on silence gaps to align with slide transitions
    refined_segments = []
    current_group = [all_words[0]]
    
    for i in range(1, len(all_words)):
        prev_w = all_words[i-1]
        curr_w = all_words[i]
        gap = curr_w.start - prev_w.end
        is_sentence_end = prev_w.word.strip().endswith(('.', '?', '!'))
        
        if gap > MAX_GAP_DURATION or is_sentence_end:
            refined_segments.append(
                create_segment_object(len(refined_segments), current_group, CONFIDENCE_THRESHOLD)
            )
            current_group = []
        current_group.append(curr_w)
    
    if current_group:
        refined_segments.append(
            create_segment_object(len(refined_segments), current_group, CONFIDENCE_THRESHOLD)
        )

    final_output = {
        "segments": refined_segments,
        "language": info.language,
        "total_filler_count": sum(len(s["filler_words"]) for s in refined_segments)
    }

    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(final_output, f, indent=2, ensure_ascii=False)

    print(f"[SUCCESS] Analysis saved to {output_json_path}")
    return final_output