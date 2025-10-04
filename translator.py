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

def process_epub_content(translator: BaseTranslator, book, target_language, glossary=None):
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
        full_translated_text = translator.translate(full_text_to_translate, target_language, glossary)
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
                            translated_text = translator.translate(original_text, target_language, glossary)
                            node.replace_with(translated_text)

                item.set_content(soup.prettify(encoding='utf-8'))

            return book
    else:
        return book

def process_pdf_content(translator: BaseTranslator, pages_spans, target_language, glossary=None):
    """
    Processes and translates text from a PDF using a global context strategy
    with a multi-layered page-by-page and span-by-span fallback.
    """
    all_spans = [span for page in pages_spans for span in page]
    all_original_texts = [span['text'] for span in all_spans]

    delimiter = "[END_OF_SPAN]"
    full_text_to_translate = delimiter.join(all_original_texts)

    if full_text_to_translate:
        full_translated_text = translator.translate(full_text_to_translate, target_language, glossary)
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

                page_translated_full_text = translator.translate(page_full_text, target_language, glossary)
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
                        translated_text = translator.translate(span['text'], target_language, glossary)
                        page_translations.append({
                            'original_span': span,
                            'translated_text': translated_text
                        })
                translated_pages.append(page_translations)
            return translated_pages
    else:
        return []