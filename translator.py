import google.generativeai as genai
import streamlit as st
from bs4 import BeautifulSoup, NavigableString
import time

def configure_gemini(api_key):
    """Configures the Gemini API with the provided key."""
    try:
        genai.configure(api_key=api_key)
        return True
    except Exception as e:
        st.error(f"Failed to configure Gemini API: {e}")
        return False

def get_translation_model():
    """Initializes and returns the Gemini model."""
    return genai.GenerativeModel('gemini-1.5-flash-latest')

def translate_text(text, target_language, glossary=None):
    """
    Translates a given text to the target language using the Gemini API.
    Includes rate-limiting awareness.
    """
    if not text or not text.strip():
        return ""

    model = get_translation_model()

    # The detailed prompt engineering from the project plan
    prompt = f"""
    You are a professional literary translator. Your task is to translate the following text into {target_language} with the highest fidelity to the original's style and tone.

    **Instructions:**
    1.  **Preserve Formatting/Tags:** If the text contains HTML tags (like <p>, <em>, <b>), maintain them exactly as they are. Translate only the text content within these tags. If there are no tags, translate the plain text.
    2.  **Literary Quality:** The translation must be of high literary quality, not a literal word-for-word translation.
    3.  **Glossary Adherence:** If a glossary is provided, you MUST use the specified translations for the given terms to ensure consistency.

    **Glossary:**
    {glossary if glossary else "No glossary provided."}

    **Text to Translate:**
    ---
    {text}
    ---

    **Translated Text:**
    """

    try:
        # A simple backoff mechanism can help with rate limiting errors.
        retries = 3
        for i in range(retries):
            try:
                response = model.generate_content(prompt)
                return response.text
            except Exception as e:
                if "rate limit" in str(e).lower() and i < retries - 1:
                    time.sleep(2 ** i) # Exponential backoff
                else:
                    raise e
    except Exception as e:
        st.error(f"An error occurred during translation: {e}")
        # Return original text on error to avoid breaking the reconstruction
        return text

def process_epub_content(book, target_language, glossary=None):
    """
    Processes and translates the content of an EPUB book object in-place.
    """
    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        soup = BeautifulSoup(item.get_content(), 'html.parser')

        # Find all text nodes in the document
        text_nodes = soup.find_all(string=True)

        for node in text_nodes:
            # We only want to translate NavigableString nodes that are not inside certain tags
            if isinstance(node, NavigableString) and node.parent.name not in ['style', 'script']:
                original_text = str(node)
                if original_text.strip():
                    translated_text = translate_text(original_text, target_language, glossary)
                    # Replace the node's content with the translation
                    node.replace_with(translated_text)

        # Update the book item with the modified HTML
        item.set_content(soup.prettify(encoding='utf-8'))

    return book


def process_pdf_content(pages_spans, target_language, glossary=None):
    """
    Processes and translates text from a list of PDF spans.
    Returns a data structure mapping original spans to translated text.
    """
    translated_pages = []
    for page_spans in pages_spans:
        page_translations = []
        for span in page_spans:
            original_text = span['text']
            translated_text = translate_text(original_text, target_language, glossary)

            # Create the mapping needed for the new reconstructor
            page_translations.append({
                'original_span': span,
                'translated_text': translated_text
            })
        translated_pages.append(page_translations)

    return translated_pages