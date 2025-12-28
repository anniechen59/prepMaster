import streamlit as st
import os
import json
import time
import wave
import sys
import base64
import streamlit.components.v1 as components
from urllib.parse import quote
from datetime import timedelta
from firebase_admin import storage

from firebase_config import (
    firebase_register,
    firebase_login,
    save_history,
    load_history,
    bucket
)

# Module Imports
sys.path.append(os.getcwd())
try:
    from utils.pdf_utils import process_pdf_for_pipeline
    from utils.whisper_utils import run_whisper_analysis
    from data.slides.keywords_expander import run_keyword_expansion
    from analysis.matcher import run_comprehensive_analysis
    from ai.coach import generate_coach_feedback
except ImportError as e:
    st.error(f" Module Import Failed: {e}")

# Configuration & Styling
st.set_page_config(page_title="PrepMaster AI - Auto Studio", layout="wide")

st.markdown("""
<style>

.stImage > img { 
    max-height: 500px; 
    object-fit: contain; 
    border-radius: 10px; 
    border: 1px solid #ddd; 
}

.stMetric { 
    background-color: #f8f9fb; 
    padding: 15px; 
    border-radius: 10px; 
}

.report-container { 
    background-color: #fdfdfd; 
    padding: 25px; 
    border-radius: 15px;
    border-left: 10px solid #FF4B4B; 
    border: 1px solid #eee; 
    margin-top: 20px; 
}

.ignore-btn { 
    color: #ff4b4b; 
    cursor: pointer; 
    border: 1px solid #ff4b4b;
    padding: 2px 5px; 
    border-radius: 5px; 
    font-size: 0.8em; 
}

.user-email {
    font-size: 0.9em;
    color: #555;
    margin-bottom: -2px;
}



</style>
""", unsafe_allow_html=True)


TEMP_DIR = "temp_data"
os.makedirs(TEMP_DIR, exist_ok=True)

# Paths
PATH_PDF = os.path.join(TEMP_DIR, "presentation.pdf")
PATH_AUDIO_WAV = os.path.join(TEMP_DIR, "audio.wav")
PATH_TIMING = os.path.join(TEMP_DIR, "timing.json")
PATH_SLIDES_JSON = os.path.join(TEMP_DIR, "slides.json")
PATH_SLIDES_EXP = os.path.join(TEMP_DIR, "slides_expanded.json")
PATH_WHISPER_OUT = os.path.join(TEMP_DIR, "whisper_output.json")
PATH_FINAL_REPORT = os.path.join(TEMP_DIR, "final_report.json")
PATH_FEEDBACK_MD = os.path.join(TEMP_DIR, "feedback.md")


# Session State
defaults = {
    "page_index": 0,
    "slide_timestamps": [],
    "practice_started": False,
    "start_time_epoch": 0.0,
    "pdf_images": [],
    "ignored_keywords": set(),
    "user": None,
    "project_id": "default",
    "analysis_done": False
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# Firebase Login
st.title("PrepMaster AI")

if not st.session_state.user:
    st.header("Login")

    email = st.text_input("Email")
    password = st.text_input("Password", type="password")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("Sign In", type="primary", width="stretch"):
            try:
                data = firebase_login(email, password)
                st.session_state.user = {"uid": data["localId"], "email": email}
                st.success("Login successful")
                st.rerun()
            except Exception as e:
                st.error(f"Login failed: {e}")

    with col2:
        if st.button("Create Account", width="stretch"):
            try:
                data = firebase_register(email, password)
                st.session_state.user = {"uid": data["localId"], "email": email}
                st.success("Account created & logged in")
                st.rerun()
            except Exception as e:
                st.error(f"Sign-up failed: {e}")

    st.stop()

# Sidebar Navigation
st.sidebar.title("Navigation")
page = st.sidebar.radio("Go to", ["Studio", "History"])

with st.sidebar:
    if st.session_state.user:

        # 顯示使用者 email
        st.markdown(
            f"<div class='user-email'>👤 {st.session_state.user['email']}</div>",
            unsafe_allow_html=True
        )

        st.markdown('<div class="logout-btn">', unsafe_allow_html=True)

        if st.button("Logout", key="logout_sidebar"):
            files_to_clean = [
                PATH_AUDIO_WAV, PATH_FINAL_REPORT, PATH_FEEDBACK_MD,
                PATH_WHISPER_OUT, PATH_TIMING
            ]
            for f in files_to_clean:
                if os.path.exists(f):
                    os.remove(f)

            for key in list(st.session_state.keys()):
                del st.session_state[key]

            st.rerun()

        st.markdown('</div>', unsafe_allow_html=True)


# Auto Stage 1
def run_auto_analysis_stage_1(audio_file):
    with st.status("AI analyzing your performance...", expanded=True) as status:

        with open(PATH_AUDIO_WAV, "wb") as f:
            f.write(audio_file.read())

        with wave.open(PATH_AUDIO_WAV, 'rb') as wf:
            total_duration = wf.getnframes() / wf.getframerate()

        current_time = time.time()
        audio_start_in_session = (current_time - st.session_state.start_time_epoch) - total_duration

        final_timings = []
        ts = st.session_state.slide_timestamps

        for i in range(len(ts)):
            if ts[i]['page'] == "END":
                continue

            raw_start = ts[i]['time'] - audio_start_in_session
            start_time = max(0.0, round(raw_start, 2))

            if i + 1 < len(ts) and ts[i+1]['page'] != "END":
                end_time = round(ts[i+1]['time'] - audio_start_in_session, 2)
            else:
                end_time = round(total_duration, 2)

            end_time = min(end_time, round(total_duration, 2))
            if end_time <= start_time:
                end_time = start_time + 0.1

            final_timings.append({
                "page_index": ts[i]['page'],
                "start_time": start_time,
                "end_time": end_time
            })

        if final_timings:
            final_timings[0]['start_time'] = 0.0

        with open(PATH_TIMING, 'w') as f:
            json.dump(final_timings, f, indent=2)

        # pipeline
        run_whisper_analysis(PATH_AUDIO_WAV, PATH_SLIDES_JSON, PATH_WHISPER_OUT)
        run_keyword_expansion(PATH_SLIDES_JSON, PATH_SLIDES_EXP)
        run_comprehensive_analysis(
            PATH_SLIDES_EXP, PATH_WHISPER_OUT, PATH_TIMING,
            PATH_AUDIO_WAV, PATH_FINAL_REPORT
        )

        if os.path.exists(PATH_FEEDBACK_MD):
            os.remove(PATH_FEEDBACK_MD)

        st.session_state.analysis_done = True
        st.session_state.practice_started = False
        status.update(label="Analysis Complete!", state="complete")

# Studio Page
if page == "Studio":

    # PDF Upload 
    if not st.session_state.pdf_images:
        uploaded_pdf = st.file_uploader("Upload Presentation PDF", type="pdf")
        if uploaded_pdf:
            with open(PATH_PDF, "wb") as f:
                f.write(uploaded_pdf.read())
            slide_data = process_pdf_for_pipeline(
                PATH_PDF,
                os.path.join(TEMP_DIR, "images"),
                PATH_SLIDES_JSON
            )
            st.session_state.pdf_images = [item['image_path'] for item in slide_data]
            st.rerun()
    else:
        col_left, col_right = st.columns([7, 3], gap="large")

        # Right: Session control
        with col_right:
            st.subheader("📊 Session Control")

            if not st.session_state.practice_started:
                st.info("Click 'Start' to begin session.")
                if st.button("🚀 Start Session", type="primary", width="stretch"):
                    st.session_state.practice_started = True
                    st.session_state.start_time_epoch = time.time()
                    st.session_state.slide_timestamps = [{"page": 0, "time": 0.0}]
                    st.session_state.ignored_keywords = set()
                    st.rerun()
            else:
                st.success("🔴 Session Live")
                
                if st.button("🔄 Restart (Reset to Slide 1)", type="secondary", width="stretch"):
                    st.session_state.practice_started = False
                    st.session_state.page_index = 0 # 放回第一頁
                    st.session_state.slide_timestamps = []
                    st.rerun()

                audio_data = st.audio_input("Record your presentation")
                if audio_data:
                    run_auto_analysis_stage_1(audio_data)
                    st.rerun()

                elapsed = time.time() - st.session_state.start_time_epoch
                st.metric("Elapsed Time", f"{elapsed:.1f}s")

        # Left: Slide navigation 
        with col_left:
            curr = st.session_state.page_index
            total = len(st.session_state.pdf_images)
            st.image(st.session_state.pdf_images[curr], use_container_width=True)

            c1, c2 = st.columns(2)
            if c1.button("⬅️ Prev", disabled=curr == 0, width="stretch"):
                st.session_state.page_index -= 1
                st.rerun()

            if c2.button("Next ➡️", disabled=curr == total - 1, width="stretch"):
                if st.session_state.practice_started:
                    st.session_state.slide_timestamps.append({
                        "page": curr + 1,
                        "time": time.time() - st.session_state.start_time_epoch
                    })
                st.session_state.page_index += 1
                st.rerun()

        # Review Section 
        if st.session_state.analysis_done and os.path.exists(PATH_FINAL_REPORT) and not st.session_state.practice_started:
            st.divider()
            st.subheader("🧐 1. Review & Calibrate Keywords")
            st.caption(
                "Instructions: Click 'Ignore' on keywords that were not intended to be spoken "
                "(e.g., student IDs, course codes)."
            )

            with open(PATH_FINAL_REPORT, 'r', encoding='utf-8') as f:
                final_reports = json.load(f)

            current_idx = st.session_state.page_index
            current_data = final_reports[current_idx]
            start_t, end_t = current_data['start_time'], current_data['end_time']

            rev_left, rev_right = st.columns([1, 1], gap="large")

            # LEFT SIDE: slide + audio segment
            with rev_left:
                st.image(st.session_state.pdf_images[current_idx], use_container_width=True)

                selected_page_num = st.slider(
                    "Quick Navigate",
                    1,
                    len(final_reports),
                    current_idx + 1,
                    key="review_slider"
                )

                if selected_page_num - 1 != current_idx:
                    st.session_state.page_index = selected_page_num - 1
                    st.rerun()

                # Audio Segment Player
                with open(PATH_AUDIO_WAV, "rb") as f:
                    audio_url = f"data:audio/wav;base64,{base64.b64encode(f.read()).decode()}"

                audio_js = f"""
                    <div style="background:#f8f9fa;padding:10px;border-radius:8px;border:1px solid #ddd;">
                        <audio id="audio-player" controls style="width:100%;">
                            <source src="{audio_url}" type="audio/wav">
                        </audio>
                    </div>
                    <script>
                        var player=document.getElementById('audio-player');
                        player.currentTime={start_t};
                        player.ontimeupdate=function(){{
                            if(player.currentTime>={end_t}){{
                                player.pause(); player.currentTime={end_t};
                            }}
                        }};
                    </script>
                """
                components.html(audio_js, height=100)

            # RIGHT SIDE: transcript + keywords 
            with rev_right:
                st.markdown(f"### 📝 Slide {current_idx + 1} Insights")

                transcript = current_data['content_analysis'].get('transcript_extract', '')
                st.info(transcript if transcript.strip() else "⚠️ No speech detected.")

                st.markdown("**🎯 Content Calibration:**")

                covered = current_data['content_analysis'].get('covered_keywords', [])
                raw_missed = current_data['content_analysis'].get('missed_keywords', [])

                # apply ignore list
                active_missed = [
                    k for k in raw_missed
                    if k not in st.session_state.ignored_keywords
                ]

                c_cov, c_miss = st.columns(2)

                with c_cov:
                    st.success(f"✅ Covered ({len(covered)})")
                    for k in covered:
                        st.caption(f"• {k}")

                with c_miss:
                    st.error(f"❌ Missed ({len(active_missed)})")
                    for k in active_missed:
                        if st.button(
                            f"Ignore '{k}'",
                            key=f"ign_{k}_{current_idx}",
                            type="secondary",
                            width="stretch"
                        ):
                            st.session_state.ignored_keywords.add(k)
                            st.rerun()

                # dynamic score
                all_keys = covered + raw_missed
                remaining_keys = [
                    k for k in all_keys if k not in st.session_state.ignored_keywords
                ]
                total_valid = len(remaining_keys)
                adj_score = (len(covered) / total_valid * 100) if total_valid > 0 else 100.0

                st.divider()
                st.metric(
                    "Adjusted Page Score",
                    f"{adj_score:.1f}%",
                    help="Calculated based on non-ignored keywords."
                )

            # Final Coach Trigger (Stage 2)
            st.divider()
            st.subheader("2. Final Diagnosis")

            report_exists = os.path.exists(PATH_FEEDBACK_MD)

            if not report_exists:
                if st.button("✨ Generate AI Coach Report", type="primary", width="stretch"):
                    with st.spinner("PrepMaster AI is finalizing your executive report..."):
                        generate_coach_feedback(
                            PATH_FINAL_REPORT,
                            PATH_FEEDBACK_MD,
                            ignored_keywords=st.session_state.ignored_keywords
                        )
                        # SAVE TO CLOUD HISTORY
                        try:
                            uid = st.session_state.user["uid"]
                            pid = st.session_state.project_id

                            with open(PATH_FINAL_REPORT, "r", encoding="utf-8") as f:
                                reports = json.load(f)

                            if isinstance(reports, list) and "page_score" in reports[-1]:
                                score = reports[-1]["page_score"]
                            else:
                                score = reports[-1].get("overall_score", 100)

                            with open(PATH_FEEDBACK_MD, "r", encoding="utf-8") as f:
                                feedback_text = f.read()

                            st.write(">>> DEBUG: calling save_history")
                            save_history(uid, pid, score, feedback_text, PATH_AUDIO_WAV, st.session_state.pdf_images[0])

                            st.success("Saved to cloud history.")
                        except Exception as e:
                            import traceback
                            st.error("Cloud sync failed")
                            st.code(traceback.format_exc())

                        st.rerun()
            else:
                with open(PATH_FEEDBACK_MD, 'r', encoding='utf-8') as f:
                    st.markdown(f'<div class="report-container">{f.read()}</div>', unsafe_allow_html=True)

                st.write("")  # spacing

                st.subheader("🏁 Finish & Next Steps")
                c_finish1, c_finish2, c_finish3 = st.columns([1, 1, 1])
                
                with c_finish1:
                    if st.button("🔄 Practice Again", use_container_width=True, type="primary", help="針對同一份 PDF 重新練習並歸零"):
                        # 清理本地檔案，重置投影片至第一頁
                        files_to_clean = [PATH_AUDIO_WAV, PATH_FINAL_REPORT, PATH_FEEDBACK_MD, PATH_WHISPER_OUT, PATH_TIMING]
                        for f in files_to_clean:
                            if os.path.exists(f): os.remove(f)
                        
                        st.session_state.page_index = 0  # 歸零
                        st.session_state.practice_started = False
                        st.session_state.analysis_done = False
                        st.session_state.slide_timestamps = []
                        st.rerun()

                with c_finish2:
                    if st.button("📁 New Presentation", use_container_width=True, help="更換另一份 PDF 簡報"):
                        # 徹底重設 session
                        for key in list(st.session_state.keys()):
                            if key not in ["user"]: del st.session_state[key]
                        st.rerun()

                with c_finish3:
                    if st.button("🔄 Update Feedback", use_container_width=True, help="保留目前錄音，僅重新產生報告"):
                        if os.path.exists(PATH_FEEDBACK_MD):
                            os.remove(PATH_FEEDBACK_MD)
                        st.rerun()



def get_signed_audio(path):
    blob = storage.bucket().blob(path)
    return blob.generate_signed_url(expiration=3600)

# History Page
if page == "History":
    st.header("📜 Practice History")

    uid = st.session_state.user["uid"]
    pid = st.session_state.project_id

    history = load_history(uid, pid)

    if not history:
        st.info("No history yet.")
        st.stop()

    
    for h in history:
        st.write("---")
        st.caption(str(h.get("timestamp", "")))
        bucket = storage.bucket()

        # 1st page Slide（
        if h.get("slide_storage_path"):
            blob = bucket.blob(h["slide_storage_path"])
            slide_url = blob.generate_signed_url(
                version="v4",
                expiration=timedelta(hours=1),
                method="GET"
            )
            st.image(slide_url, caption="Slide Preview", use_container_width=280 )



        # Audio playback
        if h.get("audio_storage_path"):
            blob = bucket.blob(h["audio_storage_path"])
            audio_url = blob.generate_signed_url(
                version="v4",
                expiration=timedelta(hours=1),
                method="GET"
            )
            st.audio(audio_url)



        # Coach report
        with st.expander("📄 View Coach Report"):
            st.markdown(h.get("feedback", ""))
