import google.generativeai as genai
import streamlit as st
from bs4 import BeautifulSoup, NavigableString
import time
import ebooklib
from abc import ABC, abstractmethod
import deepl

# --- Abstract Base Class for Translators ---

class BaseTranslator(ABC):
    """
    Abstract base class for all translation engines.
    It defines the common interface that all concrete translator classes must implement.
    """
    def __init__(self, api_key: str):
        self.api_key = api_key
        self._configure_client()

    @abstractmethod
    def _configure_client(self):
        """
        Configures the specific API client for the translator (e.g., Gemini, DeepL).
        This method should be implemented by each subclass.
        """
        pass

    @abstractmethod
    def translate(self, text: str, target_language: str, glossary: dict | None = None) -> str:
        """
        Translates a given text.
        This method must be implemented by each subclass.
        """
        pass

# --- Concrete Translator Implementations ---

class GeminiTranslator(BaseTranslator):
    """Translator implementation for Google's Gemini API."""

    def _configure_client(self):
        """Configures the Gemini API client with the provided API key."""
        try:
            genai.configure(api_key=self.api_key)
        except Exception as e:
            st.error(f"Failed to configure Gemini API: {e}")
            raise

    def translate(self, text: str, target_language: str, glossary: dict | None = None) -> str:
        """Translates text using the Gemini 1.5 Flash model."""
        if not text or not text.strip():
            return ""

        model = genai.GenerativeModel('gemini-1.5-flash-latest')

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
            st.error(f"An error occurred during Gemini translation: {e}")
            return text

class DeepLTranslator(BaseTranslator):
    """Translator implementation for the DeepL API."""

    def _configure_client(self):
        """Initializes the DeepL translator client."""
        try:
            self.translator = deepl.Translator(self.api_key)
        except Exception as e:
            st.error(f"Failed to configure DeepL API: {e}")
            raise

    def translate(self, text: str, target_language: str, glossary: dict | None = None) -> str:
        """Translates text using the DeepL API."""
        if not text or not text.strip():
            return ""

        # DeepL's free API has a character limit, so we might need to split the text.
        # For this PoC, we assume the text is within limits.
        try:
            # DeepL uses target lang codes like 'DE', 'EN-US', 'EN-GB'. We'll try to be flexible.
            # A simple mapping could be added here if needed.
            result = self.translator.translate_text(text, target_lang=target_language.upper())
            return result.text
        except deepl.DeepLException as e:
            st.error(f"An error occurred during DeepL translation: {e}")
            return text
        except Exception as e:
            st.error(f"An unexpected error occurred during DeepL translation: {e}")
            return text

# --- Content Processing Functions ---

def process_epub_content(translator: BaseTranslator, book, target_language, glossary=None, css_selectors_to_ignore=None):
    """
    Processes and translates EPUB content by treating block-level elements as translation units.
    This preserves inline formatting and improves translation context.
    """
    if css_selectors_to_ignore is None:
        css_selectors_to_ignore = []

    items = list(book.get_items_of_type(ebooklib.ITEM_DOCUMENT))
    segments = []
    all_original_html_blocks = []
    all_block_contexts = []
    soups = {}
    block_id_counter = 0

    # Define common block-level tags that should be translated as a whole unit.
    block_tags = ['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'blockquote', 'div']

    for item in items:
        soup = BeautifulSoup(item.get_content(), 'html.parser')

        # 1. Decompose ignored elements first
        if css_selectors_to_ignore:
            for selector in css_selectors_to_ignore:
                try:
                    for element in soup.select(selector):
                        element.decompose()
                except Exception as e:
                    print(f"Warning: Invalid CSS selector '{selector}' skipped. Error: {e}")

        # 2. Find, tag, and extract content from block-level elements
        for block_tag in block_tags:
            for element in soup.find_all(block_tag):
                # Only process elements that contain some text
                if element.get_text(strip=True):
                    # Assign a unique ID for reconstruction
                    unique_id = f"tx-block-{block_id_counter}"
                    element['data-translatorx-id'] = unique_id
                    block_id_counter += 1

                    # Extract the inner HTML of the block
                    original_html = element.decode_contents()
                    all_original_html_blocks.append(original_html)

                    # Store context needed for reconstruction
                    all_block_contexts.append({
                        'item_name': item.get_name(),
                        'block_id': unique_id
                    })

        soups[item.get_name()] = soup

    delimiter = "[END_OF_TEXT_NODE]"
    full_text_to_translate = delimiter.join(all_original_html_blocks)

    if not full_text_to_translate:
        return {'segments': [], 'book_data': None}

    # Attempt full-context translation of all HTML blocks
    full_translated_text = translator.translate(full_text_to_translate, target_language, glossary)
    all_translated_blocks = full_translated_text.split(delimiter)

    # Check for translation success
    if len(all_original_html_blocks) == len(all_translated_blocks):
        print("INFO: Global EPUB translation (block-level) successful.")
        for i, original_html in enumerate(all_original_html_blocks):
            segments.append({
                'original_text': original_html,
                'translated_text': all_translated_blocks[i].strip(),
                'metadata': all_block_contexts[i]
            })
    else:
        # Fallback to block-by-block translation
        print("WARNING: Global EPUB translation failed. Falling back to block-by-block mode.")
        segments = []
        for i, original_html in enumerate(all_original_html_blocks):
            translated_html = translator.translate(original_html, target_language, glossary)
            segments.append({
                'original_text': original_html,
                'translated_text': translated_html.strip(),
                'metadata': all_block_contexts[i]
            })

    # The 'soups' now contain the uniquely tagged elements, ready for reconstruction
    return {'segments': segments, 'book': book, 'soups': soups, 'items': items}


def process_pdf_content(translator: BaseTranslator, pages_spans, target_language, glossary=None):
    """
    Processes and translates text from a PDF.
    Returns a flat list of translation segments for review.
    Each segment is a dict: {'original_text': str, 'translated_text': str, 'metadata': span_dict_with_pno}
    """
    all_spans_with_pno = []
    for pno, page in enumerate(pages_spans):
        for span in page:
            span['pno'] = pno  # Add page number to span metadata
            all_spans_with_pno.append(span)

    if not all_spans_with_pno:
        return []

    all_original_texts = [span['text'] for span in all_spans_with_pno]
    delimiter = "[END_OF_SPAN]"
    full_text_to_translate = delimiter.join(all_original_texts)
    segments = []

    if not full_text_to_translate.strip():
        return []

    # Attempt full-context translation
    full_translated_text = translator.translate(full_text_to_translate, target_language, glossary)
    all_translated_texts = full_translated_text.split(delimiter)

    # If global translation is successful
    if len(all_original_texts) == len(all_translated_texts):
        print("INFO: Global PDF translation successful.")
        for i, span in enumerate(all_spans_with_pno):
            segments.append({
                'original_text': span['text'],
                'translated_text': all_translated_texts[i].strip(),
                'metadata': span
            })
        return segments
    else:
        # Fallback to page-by-page translation
        print("WARNING: Global PDF translation failed. Falling back to page-by-page mode.")
        segments = []  # Reset segments list
        for i, page_spans_item in enumerate(pages_spans):
            page_original_texts = [span['text'] for span in page_spans_item]
            if not any(s.strip() for s in page_original_texts):
                continue

            page_full_text = delimiter.join(page_original_texts)
            page_translated_full_text = translator.translate(page_full_text, target_language, glossary)
            page_translated_texts = page_translated_full_text.split(delimiter)

            if len(page_original_texts) == len(page_translated_texts):
                print(f"INFO: Page-by-page PDF translation successful for page {i + 1}.")
                for j, span in enumerate(page_spans_item):
                    span['pno'] = i  # Ensure pno is correct
                    segments.append({
                        'original_text': span['text'],
                        'translated_text': page_translated_texts[j].strip(),
                        'metadata': span
                    })
            else:
                # Further fallback to span-by-span for this page
                print(f"WARNING: Page-by-page PDF translation for page {i + 1} failed. Falling back to span-by-span mode.")
                for span in page_spans_item:
                    span['pno'] = i  # Ensure pno is correct
                    translated_text = translator.translate(span['text'], target_language, glossary)
                    segments.append({
                        'original_text': span['text'],
                        'translated_text': translated_text.strip(),
                        'metadata': span
                    })
        return segments