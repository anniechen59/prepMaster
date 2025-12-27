import fitz  # PyMuPDF
import os
import json


def process_pdf_for_pipeline(pdf_path, output_image_folder, output_json_path):
    
    """
    Core function to decompose PDF slides for analysis.

    [DATA FLOW]
    - INPUT (Raw Data): 
        - pdf_path: The user-uploaded PDF file.
    - OUTPUT (Transformed Data): 
        - Files: Slide images (.png) and structured text content (.json).
        - Returns: A list of dictionaries containing metadata for each slide.
    - NEXT STEP (Downstream): 
        - Passes the JSON metadata to 'data/slides/keywords_expander.py' for context prompting.

    [DETAILS]
    - Extracts raw text per page for keyword coverage analysis.
    - Renders high-resolution images for UI display and visual reference.
    """

    # Ensure output directories exist
    os.makedirs(output_image_folder, exist_ok=True)
    os.makedirs(os.path.dirname(output_json_path), exist_ok=True)

    doc = fitz.open(pdf_path)
    slide_data = []

    for i in range(len(doc)):
        page = doc.load_page(i)

        # Extract text written on the slide
        slide_text = page.get_text().strip()

        # Render slide image
        pix = page.get_pixmap()
        img_path = os.path.join(output_image_folder, f"page_{i}.png")
        pix.save(img_path)

        slide_data.append({
            "page_index": i,
            "image_path": img_path,
            "slide_text": slide_text
        })

    doc.close()

    # Save as JSON for downstream pipeline use
    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(slide_data, f, indent=2, ensure_ascii=False)

    return slide_data


if __name__ == "__main__":
    process_pdf_for_pipeline(
        pdf_path="data/slides/preMasterSlide.pdf", 
        output_image_folder="data/slides/images", 
        output_json_path="data/slides/slides_text.json",
    )
