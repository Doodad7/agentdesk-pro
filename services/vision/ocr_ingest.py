# services/vision/ocr_ingest.py
from PIL import Image
import pytesseract
import os

def extract_text_from_image(path: str) -> str:
    """Return extracted text from an image path."""
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    img = Image.open(path)
    text = pytesseract.image_to_string(img)
    return text