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
    if 'review_mode' not in st.session_state:
        st.session_state.review_mode = False
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

        st.header("📖 2. Configure Output")

        is_pdf = 'uploaded_file_name' in st.session_state and st.session_state.uploaded_file_name.lower().endswith('.pdf')

        if is_pdf:
            output_options = ["Replace Original Text", "Side-by-Side (Two Columns)"]
            help_text = "- **Replace Original Text**: The default behavior.\n- **Side-by-Side**: Creates a new PDF with original and translated text in two columns."
        else:
            output_options = ["Replace Original Text", "Translation Below Original", "Side-by-Side (Two Columns)"]
            help_text = "- **Replace Original Text**: The default behavior.\n- **Translation Below Original**: Places the translation directly below the original text.\n- **Side-by-Side**: Creates a two-column table for original and translated text."

        output_format = st.selectbox("Output Format", output_options, help=help_text)
        st.session_state.output_format = output_format

        st.header("📖 3. Add a Glossary (Optional)")
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
            st.session_state.engine_choice = engine_choice
            st.session_state.api_key = api_key
            st.session_state.target_language = target_language
            glossary = pd.read_csv(glossary_file).to_dict('records') if glossary_file else None
            st.session_state.glossary = glossary
            translator = get_translator(st.session_state.engine_choice, st.session_state.api_key)

            with st.spinner(f"Translating with {st.session_state.engine_choice}..."):
                file_extension = os.path.splitext(file_path)[1].lower()
                if file_extension == ".epub":
                    st.session_state.file_type = "epub"
                    book = parse_epub(file_path)
                    processed_data = process_epub_content(translator, book, target_language, glossary)
                    st.session_state.translated_segments = processed_data.get('segments', [])
                    st.session_state.book_data = {'book': processed_data.get('book'), 'soups': processed_data.get('soups'), 'items': processed_data.get('items')}
                elif file_extension == ".pdf":
                    st.session_state.file_type = "pdf"
                    pages_spans = parse_pdf(file_path)
                    st.session_state.translated_segments = process_pdf_content(translator, pages_spans, target_language, glossary)

            st.success("Translation complete! Please review the segments below.")
            st.session_state.review_mode = True
            st.session_state.translation_complete = False

        except Exception as e:
            st.error(f"An error occurred: {e}")
            st.session_state.review_mode = False

        st.session_state.processing = False
        st.rerun()

    if st.session_state.review_mode and not st.session_state.translation_complete:
        st.header("👀 5. Review and Refine Translations")
        if 'translated_segments' in st.session_state and st.session_state.translated_segments:
            if 'review_df' not in st.session_state:
                review_data = {"Original": [seg['original_text'] for seg in st.session_state.translated_segments], "Translation": [seg['translated_text'] for seg in st.session_state.translated_segments]}
                st.session_state.review_df = pd.DataFrame(review_data)

            st.info("You can edit translations in the table below. Select rows and use the button to re-translate.")
            edited_df = st.data_editor(st.session_state.review_df, use_container_width=True, height=500, key="data_editor", column_config={"Original": st.column_config.TextColumn("Original Text", disabled=True, width="large"), "Translation": st.column_config.TextColumn("Editable Translation", width="large")})
            st.session_state.review_df = edited_df

            col1, col2, _ = st.columns([0.25, 0.3, 0.45])
            with col1:
                if st.button("Retranslate Selected"):
                    try:
                        selected_indices = st.session_state.data_editor.get('selection', {}).get('rows', [])
                        if not selected_indices:
                            st.toast("Please select one or more rows to retranslate.")
                        else:
                            with st.spinner("Retranslating selected segments..."):
                                translator = get_translator(st.session_state.engine_choice, st.session_state.api_key)
                                original_texts = [st.session_state.review_df.iloc[i]['Original'] for i in selected_indices]
                                delimiter = "[END_OF_TEXT_NODE]" if st.session_state.file_type == 'epub' else "[END_OF_SPAN]"
                                full_text = delimiter.join(original_texts)
                                translated_full_text = translator.translate(full_text, st.session_state.target_language, st.session_state.glossary)
                                new_translations = translated_full_text.split(delimiter)
                                if len(new_translations) == len(original_texts):
                                    for i, idx in enumerate(selected_indices):
                                        st.session_state.review_df.loc[idx, 'Translation'] = new_translations[i].strip()
                                    st.toast("Selected segments retranslated.")
                                else:
                                    for idx in selected_indices:
                                        original_text = st.session_state.review_df.iloc[idx]['Original']
                                        new_translation = translator.translate(original_text, st.session_state.target_language, st.session_state.glossary)
                                        st.session_state.review_df.loc[idx, 'Translation'] = new_translation.strip()
                                    st.toast("Selected segments retranslated individually.")
                            st.rerun()
                    except Exception as e:
                        st.error(f"Failed to retranslate: {e}")
            with col2:
                if st.button("✅ Finalize & Download"):
                    for i, row in st.session_state.review_df.iterrows():
                        if i < len(st.session_state.translated_segments):
                            st.session_state.translated_segments[i]['translated_text'] = row['Translation']
                    st.session_state.review_mode = False
                    st.session_state.translation_complete = True
                    for key in ['review_df', 'engine_choice', 'api_key', 'target_language', 'glossary']:
                        if key in st.session_state:
                            del st.session_state[key]
                    st.rerun()
        else:
            st.warning("No translatable text was found in the document.")

    if st.session_state.translation_complete:
        st.header("📥 6. Download Your Book")
        st.info("Your translated book is ready. Click the button below to download it.")
        output_file_path = ""
        try:
            with st.spinner("Finalizing your file..."):
                if st.session_state.file_type == "epub":
                    output_file_path = reconstruct_epub(translated_segments=st.session_state.translated_segments, book_data=st.session_state.book_data, original_file_name=st.session_state.uploaded_file_name, output_format=st.session_state.output_format)
                elif st.session_state.file_type == "pdf":
                    output_file_path = reconstruct_pdf(translated_segments=st.session_state.translated_segments, original_file_path=st.session_state.temp_file_path, output_format=st.session_state.output_format)
            with open(output_file_path, "rb") as file:
                st.download_button(label="Download Translated Book", data=file, file_name=os.path.basename(output_file_path), mime=f"application/{'epub+zip' if st.session_state.file_type == 'epub' else 'pdf'}", on_click=cleanup_temp_files)
            st.warning("After downloading, click 'Start Over' in the sidebar to translate another book.")
        except Exception as e:
            st.error(f"Failed to create the final file: {e}")

if __name__ == "__main__":
    main()