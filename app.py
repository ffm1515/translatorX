import streamlit as st
import os
import pandas as pd
from parser import parse_epub, parse_pdf
from translator import BaseTranslator, GeminiTranslator, DeepLTranslator, process_epub_content, process_pdf_content
from reconstructor import reconstruct_epub, reconstruct_pdf
import shutil
import subprocess

# --- App Configuration ---
st.set_page_config(
    page_title="translatorX",
    page_icon="📚",
    layout="centered",
)

# --- Calibre Check ---
def check_calibre():
    """Checks if Calibre's ebook-convert tool is available in the system's PATH."""
    return shutil.which('ebook-convert') is not None

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
    # Flag for final download state
    if 'translation_complete' not in st.session_state:
        st.session_state.translation_complete = False
    # Flag to show the review UI
    if 'review_mode' not in st.session_state:
        st.session_state.review_mode = False
    # General flag to disable UI elements during any processing
    if 'processing' not in st.session_state:
        st.session_state.processing = False
    # Flag specifically for the iterative translation process
    if 'is_translating' not in st.session_state:
        st.session_state.is_translating = False
    # Directory for temporary files
    if 'temp_dir' not in st.session_state:
        st.session_state.temp_dir = f"temp_{os.getpid()}"
    # Stores segments that have been translated
    if 'translated_segments' not in st.session_state:
        st.session_state.translated_segments = []
    # Stores segments waiting for translation
    if 'segments_to_translate' not in st.session_state:
        st.session_state.segments_to_translate = []

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

    if not check_calibre():
        st.info("For formats other than EPUB and PDF, Calibre must be installed and 'ebook-convert' must be added to the system's PATH.")

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

        if not is_pdf:
            st.text_area(
                "Inhalte via CSS-Selektor ignorieren",
                help="Geben Sie einen Selektor pro Zeile ein (z.B. pre, code, .no-translate).",
                key="css_selectors_to_ignore"
            )

        st.header("📖 3. Add a Glossary (Optional)")
        glossary_file = st.file_uploader("Upload Glossary (CSV)", type=["csv"], help="Upload a two-column CSV.")

        st.header("🔄 Reset")
        if st.button("Start Over"):
            cleanup_temp_files()
            st.session_state.clear()
            st.rerun()

    st.header("📤 3. Upload Your Book")
    allowed_types = ["epub", "pdf", "azw3", "mobi"]
    uploaded_file = st.file_uploader("Upload a book file", type=allowed_types, disabled=st.session_state.processing)

    if uploaded_file is not None:
        st.session_state.original_file_name = uploaded_file.name
        st.session_state.uploaded_file_buffer = uploaded_file.getbuffer()
        original_extension = os.path.splitext(uploaded_file.name)[1].lower()
        st.session_state.original_extension = original_extension

        if original_extension not in [".epub", ".pdf"]:
            if not check_calibre():
                st.error("Cannot process this file. Calibre's 'ebook-convert' is required but not found.")
                st.stop()

            with st.spinner(f"Converting {uploaded_file.name} to EPUB..."):
                temp_dir = st.session_state.temp_dir
                os.makedirs(temp_dir, exist_ok=True)

                original_file_path = os.path.join(temp_dir, uploaded_file.name)
                converted_epub_path = os.path.join(temp_dir, f"{os.path.splitext(uploaded_file.name)[0]}.epub")

                with open(original_file_path, "wb") as f:
                    f.write(st.session_state.uploaded_file_buffer)

                try:
                    subprocess.run(
                        ['ebook-convert', original_file_path, converted_epub_path],
                        check=True, capture_output=True, text=True
                    )
                    st.session_state.uploaded_file_name = os.path.basename(converted_epub_path)
                    with open(converted_epub_path, "rb") as f:
                        st.session_state.uploaded_file_buffer = f.read()

                    st.info(f"✅ Converted '{uploaded_file.name}' to EPUB. File is ready.")

                except subprocess.CalledProcessError as e:
                    st.error(f"Failed to convert file with Calibre's ebook-convert: {e.stderr}")
                    st.stop()
                except FileNotFoundError:
                    st.error("Calibre's 'ebook-convert' is required but not found in your system's PATH.")
                    st.stop()
        else:
            st.session_state.uploaded_file_name = uploaded_file.name
            st.info(f"✅ File '{uploaded_file.name}' is ready.")


    st.header("🚀 4. Translate")
    # Disable button if processing, or if already translated, or if no file/API key
    translate_button_disabled = not api_key or 'uploaded_file_buffer' not in st.session_state or st.session_state.processing or st.session_state.is_translating or st.session_state.review_mode

    if st.button("Translate Book", disabled=translate_button_disabled):
        # --- 1. INITIAL SETUP ---
        st.session_state.processing = True
        st.session_state.is_translating = True
        st.session_state.translation_complete = False
        st.session_state.translated_segments = []
        st.session_state.segments_to_translate = []

        cleanup_temp_files()
        os.makedirs(st.session_state.temp_dir, exist_ok=True)
        file_path = os.path.join(st.session_state.temp_dir, st.session_state.uploaded_file_name)
        with open(file_path, "wb") as f:
            f.write(st.session_state.uploaded_file_buffer)
        st.session_state.temp_file_path = file_path

        try:
            # Store settings in session state for the iterative process
            st.session_state.engine_choice = engine_choice
            st.session_state.api_key = api_key
            st.session_state.target_language = target_language
            st.session_state.glossary = pd.read_csv(glossary_file).to_dict('records') if glossary_file else None
            st.session_state.translator = get_translator(st.session_state.engine_choice, st.session_state.api_key)

            # --- 2. PARSE AND PREPARE SEGMENTS (but don't translate yet) ---
            file_extension = os.path.splitext(file_path)[1].lower()
            if file_extension == ".epub":
                st.session_state.file_type = "epub"
                book = parse_epub(file_path)
                selectors_str = st.session_state.get('css_selectors_to_ignore', '')
                css_selectors_to_ignore = [s.strip() for s in selectors_str.split('\n') if s.strip()]
                # This function call now needs to be adapted to just prepare, not translate
                st.session_state.segments_to_translate, st.session_state.book_data = process_epub_content(None, book, target_language, st.session_state.glossary, css_selectors_to_ignore, prepare_only=True)

            elif file_extension == ".pdf":
                st.session_state.file_type = "pdf"
                pdf_data = parse_pdf(file_path)
                pages_spans = pdf_data["spans"]
                st.session_state.font_cache = pdf_data["font_cache"]
                st.session_state.segments_to_translate = process_pdf_content(None, pages_spans, target_language, st.session_state.glossary, prepare_only=True)

            st.session_state.total_segments = len(st.session_state.segments_to_translate)

        except Exception as e:
            st.error(f"An error occurred during preparation: {e}")
            st.session_state.is_translating = False
            st.session_state.processing = False

        st.rerun() # Rerun to start the iterative translation

    # --- 3. ITERATIVE TRANSLATION AND PROGRESS BAR ---
    # This section implements a non-blocking, iterative translation process.
    # Instead of using a background thread (e.g., with concurrent.futures), which can be
    # complex to manage with Streamlit's execution model, we use st.rerun().
    # The app translates a small CHUNK_SIZE of segments in each script run,
    # updating the session state and progress bar, then triggers a rerun.
    # This pattern is robust for long-running tasks in Streamlit, as it prevents
    # the server from timing out and provides a responsive UI.
    if st.session_state.is_translating and 'total_segments' in st.session_state:
        total_segments = st.session_state.total_segments
        if total_segments == 0:
            st.warning("No translatable text was found in the document.")
            st.session_state.is_translating = False
            st.session_state.processing = False
            st.rerun()

        progress_bar = st.progress(0, text=f"Translating... (0/{total_segments})")

        # Process a chunk of segments
        CHUNK_SIZE = 5 # Process 5 segments per rerun
        segments_chunk = st.session_state.segments_to_translate[:CHUNK_SIZE]

        # This part will be refactored to be more efficient later if needed
        original_texts = [seg['original_text'] for seg in segments_chunk]
        metadatas = [seg['metadata'] for seg in segments_chunk]

        delimiter = "[END_OF_TEXT_NODE]" if st.session_state.file_type == 'epub' else "[END_OF_SPAN]"
        full_text_chunk = delimiter.join(original_texts)

        translator = st.session_state.translator
        translated_full_text = translator.translate(full_text_chunk, st.session_state.target_language, st.session_state.glossary)
        translated_texts = translated_full_text.split(delimiter)

        # Handle cases where the translation API fails to preserve delimiters
        if len(translated_texts) != len(original_texts):
             # Fallback to individual translation for this chunk
            translated_texts = [translator.translate(text, st.session_state.target_language, st.session_state.glossary) for text in original_texts]

        for i, original_text in enumerate(original_texts):
            st.session_state.translated_segments.append({
                'original_text': original_text,
                'translated_text': translated_texts[i].strip(),
                'metadata': metadatas[i]
            })

        # Update the list of segments remaining
        st.session_state.segments_to_translate = st.session_state.segments_to_translate[CHUNK_SIZE:]

        # Update progress
        progress_value = len(st.session_state.translated_segments) / total_segments
        progress_text = f"Translating... ({len(st.session_state.translated_segments)}/{total_segments})"
        progress_bar.progress(progress_value, text=progress_text)

        # Check for completion
        if not st.session_state.segments_to_translate:
            st.session_state.is_translating = False
            st.session_state.processing = False
            st.session_state.review_mode = True
            progress_bar.progress(1.0, text="Translation complete!")
            st.success("Translation complete! Please review the segments below.")

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
                    # --- Error Validation ---
                    error_mask = st.session_state.review_df['Translation'].str.contains("🔴 FEHLER:", na=False)
                    if error_mask.any():
                        st.error("Please fix all translation errors (marked with 🔴) before finalizing the document.")
                    else:
                        # --- Finalize ---
                        for i, row in st.session_state.review_df.iterrows():
                            if i < len(st.session_state.translated_segments):
                                st.session_state.translated_segments[i]['translated_text'] = row['Translation']
                        st.session_state.review_mode = False
                        st.session_state.translation_complete = True
                        # Clean up session state for the next run
                        keys_to_delete = ['review_df', 'engine_choice', 'api_key', 'target_language', 'glossary', 'translator', 'total_segments', 'font_cache']
                        for key in keys_to_delete:
                            if key in st.session_state:
                                del st.session_state[key]
                        st.rerun()
        else:
            st.warning("No translatable text was found in the document.")

    if st.session_state.translation_complete:
        st.header("📥 6. Download Your Book")
        st.info("Your translated book is ready. Click the button below to download it.")
        try:
            reconstructed_path = ""
            with st.spinner("Finalizing your file..."):
                if st.session_state.file_type == "epub":
                    reconstructed_path = reconstruct_epub(translated_segments=st.session_state.translated_segments, book_data=st.session_state.book_data, original_file_name=st.session_state.original_file_name, output_format=st.session_state.output_format)
                elif st.session_state.file_type == "pdf":
                    reconstructed_path = reconstruct_pdf(translated_segments=st.session_state.translated_segments, original_file_path=st.session_state.temp_file_path, font_cache=st.session_state.get('font_cache', {}), output_format=st.session_state.output_format)

            final_output_path = reconstructed_path
            final_file_name = os.path.basename(reconstructed_path)
            mime_type = f"application/{'epub+zip' if st.session_state.file_type == 'epub' else 'pdf'}"

            original_ext = st.session_state.get('original_extension')
            if original_ext and original_ext not in [".epub", ".pdf"] and st.session_state.file_type == 'epub':
                 with st.spinner(f"Converting translated EPUB back to {original_ext}..."):
                    output_dir = os.path.dirname(reconstructed_path)
                    final_file_name = f"{os.path.splitext(st.session_state.original_file_name)[0]}_translated{original_ext}"
                    final_output_path = os.path.join(output_dir, final_file_name)
                    try:
                        subprocess.run(['ebook-convert', reconstructed_path, final_output_path], check=True, capture_output=True, text=True)
                        mime_type = "application/octet-stream"
                    except subprocess.CalledProcessError as e:
                        st.warning(f"Could not convert back to {original_ext}. Offering EPUB instead. Error: {e.stderr}")
                        final_output_path = reconstructed_path
                        final_file_name = os.path.basename(reconstructed_path)
                        mime_type = "application/epub+zip"
                    except FileNotFoundError:
                        st.warning(f"Could not convert back to {original_ext} because 'ebook-convert' was not found. Offering EPUB instead.")
                        final_output_path = reconstructed_path
                        final_file_name = os.path.basename(reconstructed_path)
                        mime_type = "application/epub+zip"

            with open(final_output_path, "rb") as file:
                st.download_button(label="Download Translated Book", data=file, file_name=final_file_name, mime=mime_type, on_click=cleanup_temp_files)
            st.warning("After downloading, click 'Start Over' in the sidebar to translate another book.")
        except Exception as e:
            st.error(f"Failed to create the final file: {e}")

if __name__ == "__main__":
    main()