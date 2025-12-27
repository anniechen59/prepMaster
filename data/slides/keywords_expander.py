import json
import nltk
import os
import string
from nltk.corpus import wordnet
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize


def _ensure_nltk_resources():
    resources = ['punkt', 'wordnet', 'stopwords', 'averaged_perceptron_tagger', 'omw-1.4']
    for res in resources:
        try:
            nltk.data.find(res)
        except LookupError:
            nltk.download(res, quiet=True)

def _get_synonyms(word):
    synonyms = set()
    synonyms.add(word.lower()) 
    for syn in wordnet.synsets(word):
        for lemma in syn.lemmas():
            clean_word = lemma.name().replace('_', ' ').lower()
            synonyms.add(clean_word)
    return list(synonyms)

def _extract_keywords_with_synonyms(text):
    stop_words = set(stopwords.words('english'))
    custom_stops = {
        'page', 'slide', 'click', 'link', 'agenda', 'summary', 
        'overview', 'introduction', 'conclusion', 'reference'
    }
    
    text = text.replace('\n', ' ').translate(str.maketrans('', '', string.punctuation))
    tokens = word_tokenize(text)
    tagged = nltk.pos_tag(tokens)
    
    keywords_map = {}
    for word, tag in tagged:
        word_lower = word.lower()
        if (word_lower not in stop_words and 
            word_lower not in custom_stops and 
            len(word_lower) > 2):
            
            if tag.startswith('N') or tag.startswith('V'):
                if word_lower not in keywords_map:
                    keywords_map[word_lower] = _get_synonyms(word_lower)
    return keywords_map


def run_keyword_expansion(input_json_path, output_json_path):
    """
    Input: 包含原始文字的 slides.json 路徑
    Output: 包含同義詞擴充的 slides 資料 (並存檔)
    """

    _ensure_nltk_resources()

    if not os.path.exists(input_json_path):
        raise FileNotFoundError(f"找不到輸入檔: {input_json_path}")

    with open(input_json_path, 'r', encoding='utf-8') as f:
        slides_data = json.load(f)

    processed_slides = []
    for slide in slides_data:
        raw_text = slide.get('slide_text', "")
        keyword_data = _extract_keywords_with_synonyms(raw_text)
        

        slide['keywords_expanded'] = keyword_data
        processed_slides.append(slide)


    with open(output_json_path, 'w', encoding='utf-8') as f:
        json.dump(processed_slides, f, indent=2, ensure_ascii=False)

    return processed_slides

if __name__ == "__main__":
    run_keyword_expansion("temp_data/slides.json", "temp_data/slides_expanded.json")