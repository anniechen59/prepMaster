import json
import os
from openai import OpenAI
from dotenv import load_dotenv


load_dotenv()

def generate_coach_feedback(input_report_path, output_feedback_path=None, ignored_keywords=None):

    if ignored_keywords is None:
        ignored_keywords = set()
    else:
        ignored_keywords = set(ignored_keywords)


    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return "❌ error: can't find OpenAI API Key。please check your .env file。"


    if not os.path.exists(input_report_path):
        return f"❌ error: can't find files {input_report_path}"

    with open(input_report_path, 'r', encoding='utf-8') as f:
        report_data = json.load(f)

   
    summary_for_ai = []

    for slide in report_data:
        metrics = slide.get('metrics', {})
        content = slide.get('content_analysis', {})
        tone = slide.get('tone_analysis', {})


        page_info = {
            "page": slide['page_index'] + 1,
            "overall_score": slide.get('overall_score', 0), 
            "content_score": content.get('score', 0),     
            "wpm": metrics.get('wpm', 0),
            "filler_rate_pm": metrics.get('filler_rate_pm', 0), 
            "mumble_rate": metrics.get('mumble_rate', 0),
            "pitch_variability": tone.get('pitch_variability', 0),
            "missing_keywords": [k for k in content.get('missed_keywords', []) if k not in ignored_keywords]
        }
        summary_for_ai.append(page_info)

    data_context = json.dumps(summary_for_ai, indent=2)



    system_prompt = """
        You are "PrepMaster AI", a world-class Executive Presentation Coach and Speech Analyst. 
        Your mission is to transform raw data into a high-impact diagnostic report that helps speakers reach "Mastery" level.

        --- CORE EVALUATION FRAMEWORK (WEIGHTED) ---
        1. FLUENCY (40%): 
        - Benchmark: 130-160 WPM. 
        - Penalties: High 'filler_rate_pm' (>5), high 'mumble_rate' (>10%).
        2. TONE & ENGAGEMENT (30%): 
        - Benchmark: Pitch Variability (SD) > 12.0 Hz. 
        - Insight: Low SD indicates "Monotone Risk," failing to sustain audience attention.
        3. CONTENT SEMANTICS (30%): 
        - Focus: Concept coverage. If 'content_score' is high but 'missing_keywords' exist, emphasize that "Paraphrasing" was successful.

        --- GRADING SCALE ---
        - S (>=90): Masterful. Ready for a Keynote stage.
        - A (80-89): Professional. Strong delivery with minor refinements needed.
        - B (70-79): Competent. Solid base, but lacks polish or engagement.
        - C (60-69): Under-rehearsed. Significant delivery or pacing issues.
        - F (<60): Critically Unclear. Requires full restructuring.

        --- DETAILED FEEDBACK REQUIREMENTS (MUST FOLLOW) ---
        1. **Strategic Grade**: State the Bold Final Grade based on 'overall_score'.
        2. **Executive Delivery Audit**: 
        - Don't just list data; interpret it. (e.g., "Your speed increased on Slide 4, suggesting anxiety").
        - Analyze the "Energy Curve" based on Pitch Variability across slides.
        3. **The "Silent Coach" Advice**: 
        - If 'filler_rate_pm' > 5, suggest a specific "Pause-Breath-Speak" technique.
        - If WPM is > 170, provide a "Speed-Control" anchor phrase.
        4. **Slide-Level Deep Dive**: 
        - Identify the "Golden Slide" (Best performing) and "Focus Slide" (Most room for improvement).
        - For the Focus Slide, explain *why* it failed (e.g., "Mumble rate spiked while explaining complex keywords").
        5. **Paraphrase vs. Omission**: 
        - Distinguish between "Saying it differently" (Good) and "Forgetting the point" (Bad). 
        - If missing_keywords are present but content_score > 70, praise their natural "Semantic Flexibility."
        6. **Next Step Prescription**: Give 3 concrete "Drills" for the next practice session.

        TONE: Elite, insightful, demanding yet highly encouraging. Use professional Markdown.
        LANGUAGE: Same as user input (or as specified).
    """

    user_prompt = f"Here is my calibrated rehearsal data. Please provide the final audit:\n\n{data_context}"


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


        if output_feedback_path:
            os.makedirs(os.path.dirname(output_feedback_path), exist_ok=True)
            with open(output_feedback_path, "w", encoding="utf-8") as f:
                f.write(coach_feedback)

        return coach_feedback

    except Exception as e:
        return f"❌ API failed:{str(e)}"