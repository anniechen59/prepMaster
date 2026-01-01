
# PrepMaster AI: Intelligent Presentation Coaching System

**A verifiable evaluation engine that bridges the gap between slide content and spoken delivery through multi-modal analysis.**

## The Challenge: Beyond the "Black-Box"
Most AI coaching tools suffer from **"Black-Box Evaluation"** and **"Keyword Rigidity"**. If a speaker uses a synonym instead of the exact word on a slide, traditional systems fail to recognize the content. Furthermore, speakers often struggle to objectively self-assess their pacing and engagement.

**PrepMaster AI** was engineered to solve these challenges by leveraging ASR (Automatic Speech Recognition) and NLP technologies to deliver **quantitative, traceable, and objective** feedback.

## The Solution: Multi-Modal Analysis
PrepMaster AI goes beyond simple transcription. It performs a synchronized analysis of **speech audio, slide content, and presentation timing** to transform a non-structured rehearsal into a data-driven report.

### Key Innovations:
* **Transparent Evaluation:** Replaces vague AI guesses with a 3:4:3 weighted scoring model (Content, Fluency, Tone).
* **Intelligent Alignment:** Uses a hierarchical validation pipeline to ensure that what you *mean* is just as important as what you *say*.
* **Actionable Metrics:** Delivers measurable insights into speaking tempo (WPM), filler-word density, and key point coverage to make practice sessions targeted and efficient.

## Project Demonstration

<div>
  <a href="https://www.youtube.com/watch?v=aFXT7-qVwXc">
    <img src="https://img.youtube.com/vi/aFXT7-qVwXc/maxresdefault.jpg" alt="PrepMaster AI Demo" style="width:60%;">
  </a>
  <p><i>Click to watch the full walkthrough on YouTube</i></p>
</div>

## Technical Architecture & Three-Layer Validation

The system employs a **3:4:3 Weighted Scoring Model** (Content 30%, Fluency 40%, Tone 30%). At its core is a sophisticated **Three-Layer Keyword Validation** engine, designed to ensure highly accurate content tracking, even with nuanced speech:

1. **Level 1: Exact & Lemma Match**
Utilizes `nltk.WordNetLemmatizer` to normalize spoken words (e.g., "analyzing" becomes "analyze") for robust and fundamental keyword detection.
2. **Level 2: Phrase & Substring Match**
Cleanses punctuation and white spaces from the transcript to accurately detect multi-word phrases or keywords that might be spoken slightly differently than written on the slide.
3. **Level 3: Semantic Vector Match (AI-Powered)**
Employs `sentence-transformers` (specifically `all-MiniLM-L6-v2`) to convert both keywords and spoken sentences into high-dimensional semantic vectors. A configurable **Weak Threshold (0.15)** is applied to identify concepts expressed through synonyms or paraphrasing, significantly reducing false negatives in content analysis.

---

## Tech Stack

* **Speech-to-Text (ASR):** `faster-whisper` (Leveraging CTranslate2 for optimized performance)
* **Natural Language Processing:** `sentence-transformers`, `nltk`, `torch`
* **Audio Analysis:** `librosa`, `numpy`, `statistics`
* **User Interface:** `Streamlit`
* **Configuration Management:** `python-dotenv`

---

## Installation & Setup

To run PrepMaster AI, please ensure you have Python 3.9+ installed and follow these steps:

### 1. Install Required Python Packages

All necessary libraries are listed in the `requirements.txt` file. Execute the following command in your terminal:

```bash
pip install -r requirements.txt

```

### 2. Download NLTK Language Resources

The project utilizes NLTK for text preprocessing. Please ensure the required resources are downloaded:

```python
import nltk
nltk.download('punkt')
nltk.download('wordnet')

```

### 3. Environment Variables Configuration (.env)

For security, sensitive information like API keys is not committed to the repository. Please configure your environment variables:

1. Locate the `.env.example` file in the project's root directory.
2. Duplicate this file and rename the copy to `.env`.
3. Open the newly created `.env` file and fill in your personal `OPENAI_API_KEY`.
4. You can also customize various system thresholds (e.g., `SEMANTIC_THRESHOLD_WEAK`) or scoring weights (e.g., `WEIGHT_CONTENT`) within this file.

**Important:** Never commit your `.env` file containing sensitive keys to a public repository like GitHub. Ensure `.env` is listed in your `.gitignore`.

### 4. Launch the Application

Once the dependencies are installed and environment variables are set, start the Streamlit application:

```bash
streamlit run app.py

```

---

## Standard Workflow

1. **Slide Upload:** Upload your presentation in PDF format. The system automatically extracts text content and expands keywords using AI.
2. **Audio Input:** Record your practice session directly within the app or upload an existing audio file (`.wav`, `.mp3`).
3. **Auto-Synchronization:** The system detects page-turn timestamps from your presentation and intelligently aligns corresponding audio segments with each slide.
4. **Metric Generation:** The ASR engine transcribes speech, identifying filler words and mumbles. NLP models analyze content coverage, while `librosa` calculates pitch variability for tonal assessment.
5. **Review Report:** Access a detailed, slide-by-slide performance report, including an overall score, identified missed keywords, speech fluency metrics, and AI-generated coaching advice for improvement.

---