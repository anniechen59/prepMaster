import streamlit as st
import os
import json
import time
import wave
import sys
import base64
import streamlit.components.v1 as components

# ==========================================
# 0. Module Imports
# ==========================================
sys.path.append(os.getcwd())
try:
    from utils.pdf_utils import process_pdf_for_pipeline
    from utils.whisper_utils import run_whisper_analysis
    from data.slides.keywords_expander import run_keyword_expansion
    from analysis.matcher import run_comprehensive_analysis
    from ai.coach import generate_coach_feedback
except ImportError as e:
    st.error(f"❌ Module Import Failed: {e}")

# ==========================================
# 1. Configuration & Styling
# ==========================================
st.set_page_config(page_title="PrepMaster AI - Auto Studio", layout="wide")

st.markdown("""
    <style>
    .stImage > img { max-height: 500px; object-fit: contain; border-radius: 10px; border: 1px solid #ddd; }
    .stMetric { background-color: #f8f9fb; padding: 15px; border-radius: 10px; }
    .report-container { background-color: #fdfdfd; padding: 25px; border-radius: 15px; border-left: 10px solid #FF4B4B; border: 1px solid #eee; margin-top: 20px; }
    .ignore-btn { color: #ff4b4b; cursor: pointer; border: 1px solid #ff4b4b; padding: 2px 5px; border-radius: 5px; font-size: 0.8em; }
    </style>
    """, unsafe_allow_html=True)

TEMP_DIR = "temp_data"
os.makedirs(TEMP_DIR, exist_ok=True)

# Pipeline Paths
PATH_PDF = os.path.join(TEMP_DIR, "presentation.pdf")
PATH_AUDIO_WAV = os.path.join(TEMP_DIR, "audio.wav")
PATH_TIMING = os.path.join(TEMP_DIR, "timing.json")
PATH_SLIDES_JSON = os.path.join(TEMP_DIR, "slides.json")
PATH_SLIDES_EXP = os.path.join(TEMP_DIR, "slides_expanded.json")
PATH_WHISPER_OUT = os.path.join(TEMP_DIR, "whisper_output.json")
PATH_FINAL_REPORT = os.path.join(TEMP_DIR, "final_report.json")
PATH_FEEDBACK_MD = os.path.join(TEMP_DIR, "feedback.md")

# Initialize Session State
if 'page_index' not in st.session_state: st.session_state.page_index = 0
if 'slide_timestamps' not in st.session_state: st.session_state.slide_timestamps = [] 
if 'practice_started' not in st.session_state: st.session_state.practice_started = False
if 'start_time_epoch' not in st.session_state: st.session_state.start_time_epoch = 0.0
if 'pdf_images' not in st.session_state: st.session_state.pdf_images = []
if 'ignored_keywords' not in st.session_state: st.session_state.ignored_keywords = set()

# ==========================================
# 2. 🔥 Auto-Trigger Workflow (Stage 1)
# ==========================================
def run_auto_analysis_stage_1(audio_file):
    """Trigger basic analysis with time calibration"""
    with st.status("🚀 AI analyzing your performance...", expanded=True) as status:
        # 1. 儲存音檔並獲取總長度
        with open(PATH_AUDIO_WAV, "wb") as f:
            f.write(audio_file.read())
        
        with wave.open(PATH_AUDIO_WAV, 'rb') as wf:
            total_duration = wf.getnframes() / wf.getframerate()

        # --- 核心修正：計算錄音開始的偏移量 ---
        # 你的 slide_timestamps 是相對於 start_time_epoch 的
        # 我們假設錄音是在最後一個步驟才發生的
        # 錄音組件被觸發的時間通常接近當下 time.time()
        
        current_time = time.time()
        # 這是錄音完成的時刻，錄音長度是 total_duration
        # 所以錄音開始的時刻（相對於 start_time_epoch）是：
        audio_start_in_session = (current_time - st.session_state.start_time_epoch) - total_duration

        final_timings = []
        ts = st.session_state.slide_timestamps

        for i in range(len(ts)):
            if ts[i]['page'] == "END":
                continue

            # 將翻頁時間校準到錄音檔的時間軸上
            # 錄音檔時間 = 翻頁時刻 - 錄音開始時刻
            raw_start = ts[i]['time'] - audio_start_in_session
            
            # 確保第一頁至少從 0.0 開始，且不為負數
            start_time = max(0.0, round(raw_start, 2))

            if i + 1 < len(ts) and ts[i+1]['page'] != "END":
                end_time = round(ts[i+1]['time'] - audio_start_in_session, 2)
            else:
                end_time = round(total_duration, 2)

            # --- 保護機制 ---
            # 1. 防止結束時間超過音檔總長
            end_time = min(end_time, round(total_duration, 2))
            # 2. 防止時間倒退或過短
            if end_time <= start_time:
                end_time = start_time + 0.1

            final_timings.append({
                "page_index": ts[i]['page'],
                "start_time": start_time,
                "end_time": end_time
            })

        # 如果校準後第一頁不是從 0 開始（通常是因為錄音開始得比第一頁晚）
        # 強制將第一頁 start_time 設為 0，確保分析完整性
        if final_timings:
            final_timings[0]['start_time'] = 0.0

        with open(PATH_TIMING, 'w', encoding='utf-8') as f:
            json.dump(final_timings, f, indent=2)

        # 2. 執行後續流程
        run_whisper_analysis(PATH_AUDIO_WAV, PATH_SLIDES_JSON, PATH_WHISPER_OUT)
        run_keyword_expansion(PATH_SLIDES_JSON, PATH_SLIDES_EXP)
        run_comprehensive_analysis(PATH_SLIDES_EXP, PATH_WHISPER_OUT, PATH_TIMING, PATH_AUDIO_WAV, PATH_FINAL_REPORT)
        
        if os.path.exists(PATH_FEEDBACK_MD): os.remove(PATH_FEEDBACK_MD)
        
        st.session_state.practice_started = False
        status.update(label="Analysis Complete! Timestamps Calibrated.", state="complete")
        st.toast("Ready! Audio and Slides are now synchronized.")
# ==========================================
# 3. Main UI Layout
# ==========================================
st.title("🎤 PrepMaster AI Studio")

if not st.session_state.pdf_images:
    uploaded_pdf = st.file_uploader("Upload Presentation PDF to begin", type="pdf")
    if uploaded_pdf:
        with open(PATH_PDF, "wb") as f: f.write(uploaded_pdf.read())
        slide_data = process_pdf_for_pipeline(PATH_PDF, os.path.join(TEMP_DIR, "images"), PATH_SLIDES_JSON)
        st.session_state.pdf_images = [item['image_path'] for item in slide_data]
        st.rerun()
else:
    col_left, col_right = st.columns([7, 3], gap="large")

    with col_right:
        st.subheader("📊 Session Control")
        
        if not st.session_state.practice_started:
            st.info("💡 **Ready?** Click 'Start' then use the recorder.")
            if st.button("🚀 Start Session", type="primary", use_container_width=True):
                st.session_state.practice_started = True
                st.session_state.start_time_epoch = time.time()
                st.session_state.slide_timestamps = [{"page": 0, "time": 0.0}]
                st.session_state.ignored_keywords = set() # Reset ignore list
                st.rerun()
        else:
            st.success("🔴 **Session Live**")
            audio_data = st.audio_input("Record your presentation")
            if audio_data:
                run_auto_analysis_stage_1(audio_data)
                st.rerun()
            
            elapsed = time.time() - st.session_state.start_time_epoch
            st.metric("Elapsed Time", f"{elapsed:.1f}s")

    with col_left:
        curr = st.session_state.page_index
        total = len(st.session_state.pdf_images)
        st.image(st.session_state.pdf_images[curr], use_container_width=True)
        
        c1, c2 = st.columns([1, 1])
        with c1:
            if st.button("⬅️ Prev", disabled=curr == 0, use_container_width=True):
                st.session_state.page_index -= 1
                st.rerun()
        with c2:
            if st.button("Next ➡️", disabled=curr == total - 1, use_container_width=True, type="secondary"):
                if st.session_state.practice_started:
                    st.session_state.slide_timestamps.append({
                        "page": curr + 1, "time": time.time() - st.session_state.start_time_epoch
                    })
                st.session_state.page_index += 1
                st.rerun()

    # ==========================================
    # 4. Review Section (Interactive Calibration)
    # ==========================================
    if os.path.exists(PATH_FINAL_REPORT) and not st.session_state.practice_started:
        st.divider()
        st.subheader("🧐 1. Review & Calibrate Keywords")
        st.caption("Instructions: Click 'Ignore' on keywords that were not intended to be spoken (e.g., student IDs, course codes).")
        
        with open(PATH_FINAL_REPORT, 'r', encoding='utf-8') as f:
            final_reports = json.load(f)
        
        current_idx = st.session_state.page_index
        current_data = final_reports[current_idx]
        start_t, end_t = current_data['start_time'], current_data['end_time']

        rev_left, rev_right = st.columns([1, 1], gap="large")
        
        with rev_left:
            st.image(st.session_state.pdf_images[current_idx], use_container_width=True)
            selected_page_num = st.slider("Quick Navigate", 1, len(final_reports), current_idx + 1, key="review_slider")
            if selected_page_num - 1 != current_idx:
                st.session_state.page_index = selected_page_num - 1
                st.rerun()

            # Audio Segment Player
            with open(PATH_AUDIO_WAV, "rb") as f:
                audio_url = f"data:audio/wav;base64,{base64.b64encode(f.read()).decode()}"
            audio_js = f"""
                <div style="background: #f8f9fa; padding: 10px; border-radius: 8px; border: 1px solid #ddd;">
                    <audio id="audio-player" controls style="width: 100%;"><source src="{audio_url}" type="audio/wav"></audio>
                </div>
                <script>
                    var player = document.getElementById('audio-player');
                    player.currentTime = {start_t};
                    player.ontimeupdate = function() {{ if (player.currentTime >= {end_t}) {{ player.pause(); player.currentTime = {end_t}; }} }};
                </script>"""
            components.html(audio_js, height=100)

        with rev_right:
            st.markdown(f"### 📝 Slide {current_idx + 1} Insights")
            
            # Transcript Display
            transcript = current_data['content_analysis'].get('transcript_extract', '')
            st.info(transcript if transcript.strip() else "⚠️ No speech detected.")
            
            # Interactive Keyword Section
            st.markdown("**🎯 Content Calibration:**")
            covered = current_data['content_analysis'].get('covered_keywords', [])
            raw_missed = current_data['content_analysis'].get('missed_keywords', [])
            
            # Filter missed based on ignore list
            active_missed = [k for k in raw_missed if k not in st.session_state.ignored_keywords]
            
            c_cov, c_miss = st.columns(2)
            with c_cov:
                st.success(f"✅ Covered ({len(covered)})")
                for k in covered: st.caption(f"• {k}")
            
            with c_miss:
                st.error(f"❌ Missed ({len(active_missed)})")
                for k in active_missed:
                    # Individual Ignore Buttons
                    if st.button(f"Ignore '{k}'", key=f"ign_{k}_{current_idx}", type="secondary", use_container_width=True):
                        st.session_state.ignored_keywords.add(k)
                        st.rerun()
            
            # Dynamic Score Calculation
            all_keys = covered + raw_missed
            remaining_keys = [k for k in all_keys if k not in st.session_state.ignored_keywords]
            total_valid = len(remaining_keys)
            adj_score = (len(covered) / total_valid * 100) if total_valid > 0 else 100.0
            
            st.divider()
            st.metric("Adjusted Page Score", f"{adj_score:.1f}%", help="Calculated based on non-ignored keywords.")

        # ==========================================
        # 5. Final Coach Trigger (Stage 2)
        # ==========================================
        # UI Button logic for Stage 2 (Final Diagnosis)
        st.divider()
        st.subheader("🚀 2. Final Diagnosis")
        
        # 檢查報告是否已存在
        report_exists = os.path.exists(PATH_FEEDBACK_MD)

        if not report_exists:
            # 第一階段：尚未產生報告
            if st.button("✨ Generate AI Coach Report", type="primary", use_container_width=True):
                with st.spinner("PrepMaster AI is finalizing your executive report..."):
                    # 確保將忽略清單傳入後端處理
                    generate_coach_feedback(
                        PATH_FINAL_REPORT, 
                        PATH_FEEDBACK_MD, 
                        ignored_keywords=st.session_state.ignored_keywords
                    )
                    st.rerun()
        else:
            # 第二階段：報告已產生，顯示報告與「重新產生」按鈕
            with open(PATH_FEEDBACK_MD, 'r', encoding='utf-8') as f:
                st.markdown(f'<div class="report-container">{f.read()}</div>', unsafe_allow_html=True)
            
            st.write("") # 增加一點間距
            
            # 使用兩欄佈局，讓重新產生的按鈕不要佔滿整個畫面，看起來比較精緻
            c_bot1, c_bot2 = st.columns([2, 1])
            with c_bot2:
                if st.button("🔄 Update & Regenerate", use_container_width=True):
                    # 刪除舊報告並重新執行，會抓取最新的忽略清單
                    os.remove(PATH_FEEDBACK_MD)
                    st.rerun()