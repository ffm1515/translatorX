import streamlit as st
import os
import pandas as pd
from parser import parse_epub, parse_pdf
from translator import configure_gemini, process_epub_content, process_pdf_content
from reconstructor import reconstruct_epub, reconstruct_pdf
import shutil

# --- App Configuration ---
st.set_page_config(
    page_title="Visual Book Translator",
    page_icon="📚",
    layout="centered",
)

# --- Session State Initialization ---
def init_session_state():
    """Initializes all necessary session state variables."""
    if 'translation_complete' not in st.session_state:
        st.session_state.translation_complete = False
    if 'processing' not in st.session_state:
        st.session_state.processing = False
    # Use a more robust temp directory name
    if 'temp_dir' not in st.session_state:
        st.session_state.temp_dir = f"temp_{os.getpid()}"

def cleanup_temp_files():
    """Removes the temporary directory and all its contents."""
    temp_dir = st.session_state.temp_dir
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
    # Also clean up the output directory if it exists
    if os.path.exists("temp_output"):
        shutil.rmtree("temp_output")


def main():
    """Main function to run the Streamlit application."""
    init_session_state()

    st.title("📚 Visual Book Translator")
    st.markdown("Translate EPUB and PDF files while preserving the original layout and formatting.")

    # --- Sidebar for Settings and Controls ---
    with st.sidebar:
        st.header("⚙️ 1. Configure Settings")
        api_key = st.text_input("Enter your Gemini API Key", type="password", help="Your API key is required to use the translation service.")
        target_language = st.text_input("Target Language", "German", help="Enter the language you want to translate the book into.")

        st.header("📖 2. Add a Glossary (Optional)")
        glossary_file = st.file_uploader("Upload Glossary (CSV)", type=["csv"], help="Upload a two-column CSV with 'Original' and 'Translation' headers for consistent term translation.")

        # --- Reset Button ---
        st.header("🔄 Reset")
        if st.button("Start Over"):
            cleanup_temp_files()
            st.session_state.clear()
            st.rerun()

    # --- Main Application Flow ---
    st.header("📤 3. Upload Your Book")
    uploaded_file = st.file_uploader("Upload an EPUB or PDF file", type=["epub", "pdf"], disabled=st.session_state.processing)

    if uploaded_file is not None:
        st.session_state.uploaded_file_name = uploaded_file.name
        st.session_state.uploaded_file_buffer = uploaded_file.getbuffer()
        st.info(f"✅ File '{uploaded_file.name}' is ready.")

    # --- Translate Button ---
    st.header("🚀 4. Translate")
    translate_button_disabled = not api_key or 'uploaded_file_buffer' not in st.session_state or st.session_state.processing
    if st.button("Translate Book", disabled=translate_button_disabled):
        st.session_state.processing = True
        st.session_state.translation_complete = False

        # Create a unique temp directory for this session
        cleanup_temp_files()
        os.makedirs(st.session_state.temp_dir, exist_ok=True)
        file_path = os.path.join(st.session_state.temp_dir, st.session_state.uploaded_file_name)

        with open(file_path, "wb") as f:
            f.write(st.session_state.uploaded_file_buffer)

        st.session_state.temp_file_path = file_path

        if not configure_gemini(api_key):
            st.error("API Key is invalid or configuration failed.")
            st.session_state.processing = False
            st.stop()

        glossary = None
        if glossary_file is not None:
            try:
                glossary = pd.read_csv(glossary_file).to_dict('records')
                st.info("Glossary loaded successfully.")
            except Exception as e:
                st.warning(f"Could not load glossary: {e}")

        file_extension = os.path.splitext(file_path)[1].lower()

        try:
            with st.spinner("Translating... This is the magic part and can take a few minutes."):
                if file_extension == ".epub":
                    st.session_state.file_type = "epub"
                    book = parse_epub(file_path)
                    # The book object is translated in-place
                    st.session_state.translated_data = process_epub_content(book, target_language, glossary)

                elif file_extension == ".pdf":
                    st.session_state.file_type = "pdf"
                    pages_spans = parse_pdf(file_path)
                    # The result is a mapping of original spans to translations
                    st.session_state.translated_data = process_pdf_content(pages_spans, target_language, glossary)

            st.success("Translation complete! Your book is being prepared for download.")
            st.session_state.translation_complete = True

        except Exception as e:
            st.error(f"An error occurred during translation: {e}")

        st.session_state.processing = False
        st.rerun()

    # --- Download Section ---
    if st.session_state.translation_complete:
        st.header("📥 5. Download Your Book")
        st.info("Your translated book is ready. Click the button below to download it.")

        output_file_path = ""
        try:
            with st.spinner("Finalizing your file..."):
                if st.session_state.file_type == "epub":
                    output_file_path = reconstruct_epub(
                        st.session_state.translated_data, # This is the modified book object
                        st.session_state.uploaded_file_name
                    )
                elif st.session_state.file_type == "pdf":
                     output_file_path = reconstruct_pdf(
                        st.session_state.translated_data, # This is the page-by-page translation mapping
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