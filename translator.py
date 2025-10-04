import google.generativeai as genai
import streamlit as st
from bs4 import BeautifulSoup, NavigableString
import time
import ebooklib

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

    prompt = f"""
    You are a professional literary translator. Your task is to translate the following text into {target_language} with the highest fidelity to the original's style and tone.

    **Instructions:**
    1.  **Preserve Formatting/Tags:** If the text contains HTML tags (like <p>, <em>, <b>), maintain them exactly as they are. Translate only the text content within these tags. If there are no tags, translate the plain text.
    2.  **Preserve Delimiters:** The text may contain special delimiters like `[END_OF_TEXT_NODE]` or `[END_OF_SPAN]`. You MUST preserve these delimiters exactly as they appear in the output.
    3.  **Literary Quality:** The translation must be of high literary quality, not a literal word-for-word translation.
    4.  **Glossary Adherence:** If a glossary is provided, you MUST use the specified translations for the given terms to ensure consistency.

    **Glossary:**
    {glossary if glossary else "No glossary provided."}

    **Text to Translate:**
    ---
    {text}
    ---

    **Translated Text:**
    """

    try:
        retries = 3
        for i in range(retries):
            try:
                response = model.generate_content(prompt)
                return response.text
            except Exception as e:
                if "rate limit" in str(e).lower() and i < retries - 1:
                    time.sleep(2 ** i)
                else:
                    raise e
    except Exception as e:
        st.error(f"An error occurred during translation: {e}")
        return text

def process_epub_content(book, target_language, glossary=None):
    """
    Processes and translates the content of an EPUB book object using a global context strategy
    with a chapter-by-chapter fallback.
    """
    items = list(book.get_items_of_type(ebooklib.ITEM_DOCUMENT))
    soups = [BeautifulSoup(item.get_content(), 'html.parser') for item in items]

    all_text_nodes_for_global = []
    all_original_texts_for_global = []

    for soup in soups:
        text_nodes = soup.find_all(string=True)
        for node in text_nodes:
            if isinstance(node, NavigableString) and node.parent.name not in ['style', 'script']:
                original_text = str(node)
                if original_text.strip():
                    all_text_nodes_for_global.append(node)
                    all_original_texts_for_global.append(original_text)

    delimiter = "[END_OF_TEXT_NODE]"
    full_text_to_translate = delimiter.join(all_original_texts_for_global)

    if full_text_to_translate:
        full_translated_text = translate_text(full_text_to_translate, target_language, glossary)
        all_translated_texts = full_translated_text.split(delimiter)

        if len(all_original_texts_for_global) == len(all_translated_texts):
            print("INFO: Globale Rekonstruktion erfolgreich.")
            for i, node in enumerate(all_text_nodes_for_global):
                node.replace_with(all_translated_texts[i])

            for i, item in enumerate(items):
                item.set_content(soups[i].prettify(encoding='utf-8'))

            return book
        else:
            print("WARNUNG: Globale Rekonstruktion fehlgeschlagen. Wechsle zu robusterem Modus.")
            for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
                soup = BeautifulSoup(item.get_content(), 'html.parser')
                text_nodes_in_item = soup.find_all(string=True)

                for node in text_nodes_in_item:
                    if isinstance(node, NavigableString) and node.parent.name not in ['style', 'script']:
                        original_text = str(node)
                        if original_text.strip():
                            translated_text = translate_text(original_text, target_language, glossary)
                            node.replace_with(translated_text)

                item.set_content(soup.prettify(encoding='utf-8'))

            return book
    else:
        return book

def process_pdf_content(pages_spans, target_language, glossary=None):
    """
    Processes and translates text from a PDF using a global context strategy
    with a multi-layered page-by-page and span-by-span fallback.
    """
    all_spans = [span for page in pages_spans for span in page]
    all_original_texts = [span['text'] for span in all_spans]

    delimiter = "[END_OF_SPAN]"
    full_text_to_translate = delimiter.join(all_original_texts)

    if full_text_to_translate:
        full_translated_text = translate_text(full_text_to_translate, target_language, glossary)
        all_translated_texts = full_translated_text.split(delimiter)

        if len(all_original_texts) == len(all_translated_texts):
            print("INFO: Globale PDF-Rekonstruktion erfolgreich.")

            translated_spans_iterator = iter(all_translated_texts)
            translated_pages = []
            for page_spans in pages_spans:
                page_translations = []
                for span in page_spans:
                    page_translations.append({
                        'original_span': span,
                        'translated_text': next(translated_spans_iterator)
                    })
                translated_pages.append(page_translations)
            return translated_pages
        else:
            print("WARNUNG: Globale PDF-Rekonstruktion fehlgeschlagen. Wechsle zu robusterem Modus.")
            translated_pages = []
            for i, page_spans in enumerate(pages_spans):
                page_translations = []
                page_original_texts = [span['text'] for span in page_spans]
                page_full_text = delimiter.join(page_original_texts)

                if not page_full_text:
                    translated_pages.append([])
                    continue

                page_translated_full_text = translate_text(page_full_text, target_language, glossary)
                page_translated_texts = page_translated_full_text.split(delimiter)

                if len(page_original_texts) == len(page_translated_texts):
                    print(f"INFO: Seitenweise PDF-Rekonstruktion erfolgreich für Seite {i + 1}.")
                    for j, span in enumerate(page_spans):
                        page_translations.append({
                            'original_span': span,
                            'translated_text': page_translated_texts[j]
                        })
                else:
                    print(f"WARNUNG: Seitenweise PDF-Rekonstruktion für Seite {i + 1} fehlgeschlagen. Wechsle zu Span-für-Span-Modus.")
                    for span in page_spans:
                        translated_text = translate_text(span['text'], target_language, glossary)
                        page_translations.append({
                            'original_span': span,
                            'translated_text': translated_text
                        })
                translated_pages.append(page_translations)
            return translated_pages
    else:
        return []