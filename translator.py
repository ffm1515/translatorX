import google.generativeai as genai
import streamlit as st
from bs4 import BeautifulSoup
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
            # Simple retry logic for rate limiting
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
            # Instead of just logging, return a clear error message for the specific block.
            error_message = f"🔴 FEHLER: Gemini-API-Fehler - {type(e).__name__}"
            print(f"Error during Gemini translation: {e}") # Log the full error to console
            return error_message

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
        try:
            # Note: DeepL glossary handling is a premium feature and would require more setup.
            # This implementation passes the text directly.
            result = self.translator.translate_text(text, target_lang=target_language.upper())
            return result.text
        except deepl.DeepLException as e:
            error_message = f"🔴 FEHLER: DeepL-API-Fehler - {type(e).__name__}"
            print(f"Error during DeepL translation: {e}")
            return error_message
        except Exception as e:
            error_message = f"🔴 FEHLER: Unerwarteter Fehler - {type(e).__name__}"
            print(f"An unexpected error occurred during DeepL translation: {e}")
            return error_message

# --- Content Processing Functions ---

def process_epub_content(translator: BaseTranslator, book, target_language, glossary=None, css_selectors_to_ignore=None, prepare_only=False):
    """
    Processes EPUB content. Can operate in two modes:
    1. prepare_only=True: Extracts all translatable segments and returns them without translating.
    2. prepare_only=False: This mode is deprecated in the main app flow.
    """
    if css_selectors_to_ignore is None:
        css_selectors_to_ignore = []

    items = list(book.get_items_of_type(ebooklib.ITEM_DOCUMENT))
    segments_to_translate = []
    soups = {}
    block_id_counter = 0
    # Common block-level tags that usually contain translatable content.
    block_tags = ['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'blockquote', 'div']

    for item in items:
        soup = BeautifulSoup(item.get_content(), 'html.parser')

        # Decompose elements matching ignore selectors before processing
        if css_selectors_to_ignore:
            for selector in css_selectors_to_ignore:
                try:
                    for element in soup.select(selector):
                        element.decompose()
                except Exception as e:
                    # Log error for invalid selectors but don't stop the process
                    print(f"Warning: Invalid CSS selector '{selector}' skipped. Error: {e}")

        # Find all block-level elements that might contain text
        for element in soup.find_all(block_tags):
            # Only process elements that contain actual text
            if element.get_text(strip=True):
                unique_id = f"tx-block-{block_id_counter}"
                element['data-translatorx-id'] = unique_id
                block_id_counter += 1

                # Extract the inner HTML of the block to preserve formatting
                original_html = element.decode_contents()

                segments_to_translate.append({
                    'original_text': original_html,
                    'metadata': {'item_name': item.get_name(), 'block_id': unique_id}
                })

        soups[item.get_name()] = soup

    book_data = {'book': book, 'soups': soups, 'items': items}

    if prepare_only:
        return segments_to_translate, book_data
    else:
        # This mode is no longer used by the main application but is kept for potential future use.
        raise NotImplementedError("Direct translation within process_epub_content is deprecated.")


def process_pdf_content(translator: BaseTranslator, pages_spans, target_language, glossary=None, prepare_only=False):
    """
    Processes PDF content. Can operate in two modes:
    1. prepare_only=True: Extracts all translatable spans and returns them without translating.
    2. prepare_only=False: This mode is deprecated in the main app flow.
    """
    segments_to_translate = []
    for pno, page in enumerate(pages_spans):
        for span in page:
            # Add page number to each span's metadata for reconstruction
            span['pno'] = pno
            segments_to_translate.append({
                'original_text': span['text'],
                'metadata': span
            })

    if prepare_only:
        return segments_to_translate
    else:
        # This mode is no longer used by the main application.
        raise NotImplementedError("Direct translation within process_pdf_content is deprecated.")