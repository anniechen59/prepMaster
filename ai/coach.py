import json
import os
from openai import OpenAI
from dotenv import load_dotenv

# 加載環境變數
load_dotenv()

def generate_coach_feedback(input_report_path, output_feedback_path=None, ignored_keywords=None):
    """
    將分析數據發送給 OpenAI 並生成教練回饋報告。
    新增參數: ignored_keywords (set 或 list)，用於過濾不需要的關鍵字。
    """
    if ignored_keywords is None:
        ignored_keywords = set()
    else:
        ignored_keywords = set(ignored_keywords)

    # 1. 檢查 API Key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return "❌ 錯誤：找不到 OpenAI API Key。請檢查 .env 檔案。"

    # 2. 讀取分析資料
    if not os.path.exists(input_report_path):
        return f"❌ 錯誤：找不到分析檔案 {input_report_path}"

    with open(input_report_path, 'r', encoding='utf-8') as f:
        report_data = json.load(f)

    # 3. 整理數據 (加入動態過濾與重新計分邏輯)
    summary_for_ai = []
    # --- 在 summary_for_ai 的循環中修改 ---
    for slide in report_data:
        metrics = slide.get('metrics', {})
        content = slide.get('content_analysis', {})
        tone = slide.get('tone_analysis', {})

        # 這裡我們直接傳送你在 matcher.py 算好的 overall_score
        # 這樣 AI 給等地 (Grade) 時會更精確
        page_info = {
            "page": slide['page_index'] + 1,
            "overall_score": slide.get('overall_score', 0), # 這是 3:4:3 的總分
            "content_score": content.get('score', 0),       # 內容佔比 30%
            "wpm": metrics.get('wpm', 0),
            "filler_rate_pm": metrics.get('filler_rate_pm', 0), # 贅字率
            "mumble_rate": metrics.get('mumble_rate', 0),
            "pitch_variability": tone.get('pitch_variability', 0),
            "missing_keywords": [k for k in content.get('missed_keywords', []) if k not in ignored_keywords]
        }
        summary_for_ai.append(page_info)

    data_context = json.dumps(summary_for_ai, indent=2)

    # 4. 設定 Prompt

    system_prompt = """
    You are "PrepMaster AI", an elite executive coach. 
    Evaluate the presentation based on the following WEIGHTED STANDARDS:
    
    1. FLUENCY (40%): Ideal WPM is 130-160. Penalty for high Filler Rate (uh, um) and Mumble Rate.
    2. TONE (30%): Pitch Variability should be > 12.0 for dynamic delivery.
    3. CONTENT (30%): Keywords are concepts; exact wording is secondary. (Calibrated by user).

    

    GRADING SCALE:
    - S: Overall Score >= 90 (Masterful delivery).
    - A: Overall Score 80-89 (Professional).
    - B: Overall Score 70-79 (Competent but needs polish).
    - C: Overall Score 60-69 (Needs significant practice).
    - F: Overall Score < 60 (Incomplete or unclear).

    FEEDBACK REQUIREMENTS:
    1. **Final Grade**: Boldly state the S/A/B/C/F grade based on the weighted 'overall_score'.
    2. **Executive Summary**: A concise summary focusing on 'How' they spoke rather than just 'What' they said.
    3. **The "Paraphrase" Recognition**: If content scores are decent but missing words are few, praise their ability to explain concepts in their own words.
    4. **Filler Word Alert**: If 'filler_rate_pm' is > 5, provide a specific tip to use "Strategic Silence" instead.
    5. **Critical Slides**: Identify the top 2 slides needing improvement based on overall metrics.
    

    SCORING LOGIC:
    - Prioritize WPM and Clarity. If these are good, avoid giving an 'F' even if keywords are missed.
    - Encourage the speaker while being honest about bad data.

    TONE: Professional, concise, and direct. Use Markdown.
    """

    user_prompt = f"Here is my calibrated rehearsal data. Please provide the final audit:\n\n{data_context}"

    # 5. 呼叫 OpenAI API
    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o", 
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7
        )

        coach_feedback = response.choices[0].message.content

        # 6. 存檔
        if output_feedback_path:
            os.makedirs(os.path.dirname(output_feedback_path), exist_ok=True)
            with open(output_feedback_path, "w", encoding="utf-8") as f:
                f.write(coach_feedback)

        return coach_feedback

    except Exception as e:
        return f"❌ API 呼叫失敗：{str(e)}"