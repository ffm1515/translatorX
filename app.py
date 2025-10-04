import streamlit as st
import os
import pandas as pd
from parser import parse_epub, parse_pdf
from translator import BaseTranslator, GeminiTranslator, DeepLTranslator, process_epub_content, process_pdf_content
from reconstructor import reconstruct_epub, reconstruct_pdf
import shutil

# --- App Configuration ---
st.set_page_config(
    page_title="translatorX",
    page_icon="📚",
    layout="centered",
)

# --- Translator Factory ---
def get_translator(engine: str, api_key: str) -> BaseTranslator:
    """Factory function to get an instance of the selected translator."""
    if engine == "Gemini":
        return GeminiTranslator(api_key)
    elif engine == "DeepL":
        return DeepLTranslator(api_key)
    else:
        raise ValueError(f"Unknown translation engine: {engine}")

# --- Session State and File Handling ---
def init_session_state():
    """Initializes all necessary session state variables."""
    if 'translation_complete' not in st.session_state:
        st.session_state.translation_complete = False
    if 'processing' not in st.session_state:
        st.session_state.processing = False
    if 'temp_dir' not in st.session_state:
        st.session_state.temp_dir = f"temp_{os.getpid()}"

def cleanup_temp_files():
    """Removes the temporary directory and all its contents."""
    temp_dir = st.session_state.temp_dir
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
    if os.path.exists("temp_output"):
        shutil.rmtree("temp_output")

# --- Main Application UI ---
def main():
    """Main function to run the Streamlit application."""
    init_session_state()

    st.title("📚 translatorX")
    st.markdown("Translate EPUB and PDF files while preserving the original layout and formatting.")

    with st.sidebar:
        st.header("⚙️ 1. Configure Settings")
        engine_choice = st.selectbox(
            "Choose Translation Engine",
            ("Gemini", "DeepL"),
            help="Select the translation service you want to use."
        )
        api_key_label = f"Enter your {engine_choice} API Key"
        api_key = st.text_input(api_key_label, type="password", help=f"Your {engine_choice} API key is required.")
        target_language = st.text_input("Target Language", "German", help="Enter the language (e.g., 'German', 'EN-US' for DeepL).")

        st.header("📖 2. Add a Glossary (Optional)")
        glossary_file = st.file_uploader("Upload Glossary (CSV)", type=["csv"], help="Upload a two-column CSV.")

        st.header("🔄 Reset")
        if st.button("Start Over"):
            cleanup_temp_files()
            st.session_state.clear()
            st.rerun()

    st.header("📤 3. Upload Your Book")
    uploaded_file = st.file_uploader("Upload an EPUB or PDF file", type=["epub", "pdf"], disabled=st.session_state.processing)

    if uploaded_file is not None:
        st.session_state.uploaded_file_name = uploaded_file.name
        st.session_state.uploaded_file_buffer = uploaded_file.getbuffer()
        st.info(f"✅ File '{uploaded_file.name}' is ready.")

    st.header("🚀 4. Translate")
    translate_button_disabled = not api_key or 'uploaded_file_buffer' not in st.session_state or st.session_state.processing
    if st.button("Translate Book", disabled=translate_button_disabled):
        st.session_state.processing = True
        st.session_state.translation_complete = False

        cleanup_temp_files()
        os.makedirs(st.session_state.temp_dir, exist_ok=True)
        file_path = os.path.join(st.session_state.temp_dir, st.session_state.uploaded_file_name)

        with open(file_path, "wb") as f:
            f.write(st.session_state.uploaded_file_buffer)

        st.session_state.temp_file_path = file_path

        try:
            translator = get_translator(engine_choice, api_key)
            glossary = pd.read_csv(glossary_file).to_dict('records') if glossary_file else None

            with st.spinner(f"Translating with {engine_choice}... This can take a few minutes."):
                file_extension = os.path.splitext(file_path)[1].lower()
                if file_extension == ".epub":
                    st.session_state.file_type = "epub"
                    book = parse_epub(file_path)
                    st.session_state.translated_data = process_epub_content(translator, book, target_language, glossary)
                elif file_extension == ".pdf":
                    st.session_state.file_type = "pdf"
                    pages_spans = parse_pdf(file_path)
                    st.session_state.translated_data = process_pdf_content(translator, pages_spans, target_language, glossary)

            st.success("Translation complete! Your book is being prepared for download.")
            st.session_state.translation_complete = True

        except Exception as e:
            st.error(f"An error occurred: {e}")

        st.session_state.processing = False
        st.rerun()

    if st.session_state.translation_complete:
        st.header("📥 5. Download Your Book")
        st.info("Your translated book is ready. Click the button below to download it.")

        output_file_path = ""
        try:
            with st.spinner("Finalizing your file..."):
                if st.session_state.file_type == "epub":
                    output_file_path = reconstruct_epub(
                        st.session_state.translated_data,
                        st.session_state.uploaded_file_name
                    )
                elif st.session_state.file_type == "pdf":
                     output_file_path = reconstruct_pdf(
                        st.session_state.translated_data,
                        st.session_state.temp_file_path
                    )

            with open(output_file_path, "rb") as file:
                st.download_button(
                    label="Download Translated Book",
                    data=file,
                    file_name=os.path.basename(output_file_path),
                    mime=f"application/{'epub+zip' if st.session_state.file_type == 'epub' else 'pdf'}",
                    on_click=cleanup_temp_files
                )
            st.warning("After downloading, click 'Start Over' in the sidebar to translate another book.")

        except Exception as e:
            st.error(f"Failed to create the final file: {e}")

if __name__ == "__main__":
    main()