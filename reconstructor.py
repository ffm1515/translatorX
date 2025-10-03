import ebooklib
from ebooklib import epub
import fitz  # PyMuPDF
import os

def reconstruct_epub(book, original_file_name):
    """
    Saves the modified epub book object.
    The translation is now performed in-place on the book object, preserving its structure.
    """
    # Define an output directory to avoid clutter
    output_dir = "temp_output"
    os.makedirs(output_dir, exist_ok=True)
    output_file_path = os.path.join(output_dir, "translated_" + os.path.basename(original_file_name))

    # Write the modified book object to a new file
    epub.write_epub(output_file_path, book, {})
    return output_file_path

def _get_base_font_name(font_name):
    """
    A helper to get a valid base font name for PyMuPDF's built-in fonts.
    This is a compromise for handling fonts without embedding them.
    """
    lower_font = font_name.lower()
    if "courier" in lower_font:
        return "cour"
    if "times" in lower_font:
        return "timo"
    if "symbol" in lower_font:
        return "symb"
    # Default to Helvetica as it's a common sans-serif font
    return "helv"

def reconstruct_pdf(translated_data, original_file_path):
    """
    Reconstructs a PDF by replacing original text with translated text,
    with dynamic font resizing to fit content.
    'translated_data' is a list of pages, where each page is a list of dicts:
    {'original_span': span_dict, 'translated_text': '...'}
    """
    doc = fitz.open(original_file_path)

    for i, page_translations in enumerate(translated_data):
        page = doc.load_page(i)

        for item in page_translations:
            original_span = item['original_span']
            translated_text = item['translated_text'].strip()

            if not translated_text:
                continue

            bbox = fitz.Rect(original_span['bbox'])

            # 1. Erase the original text by drawing a white rectangle over it.
            page.draw_rect(bbox, color=(1, 1, 1), fill=(1, 1, 1), overlay=True)

            # 2. Set up font properties for insertion.
            fontname = _get_base_font_name(original_span['font'])
            fontsize = original_span['size']
            fontcolor_int = original_span['color']

            # Convert sRGB integer color to a (r, g, b) tuple for PyMuPDF.
            r = ((fontcolor_int >> 16) & 0xFF) / 255.0
            g = ((fontcolor_int >> 8) & 0xFF) / 255.0
            b = (fontcolor_int & 0xFF) / 255.0
            color_tuple = (r, g, b)

            # 3. Insert text with dynamic font size adjustment.
            min_fontsize = 4.0  # Don't allow text to become unreadably small.
            current_fontsize = fontsize

            # Use insert_textbox which returns the amount of text that did NOT fit.
            # We loop until the leftover text is negligible (less than 1).
            leftover_text = page.insert_textbox(
                bbox,
                translated_text,
                fontsize=current_fontsize,
                fontname=fontname,
                color=color_tuple,
                align=0
            )

            while leftover_text > 1 and current_fontsize > min_fontsize:
                current_fontsize -= 0.5  # Reduce font size
                # Erase the previous attempt before retrying
                page.draw_rect(bbox, color=(1, 1, 1), fill=(1, 1, 1), overlay=True)
                leftover_text = page.insert_textbox(
                    bbox,
                    translated_text,
                    fontsize=current_fontsize,
                    fontname=fontname,
                    color=color_tuple,
                    align=0
                )

    # Save the final modified PDF
    output_dir = "temp_output"
    os.makedirs(output_dir, exist_ok=True)
    final_path = os.path.join(output_dir, "translated_" + os.path.basename(original_file_path))

    # Use garbage collection to reduce file size
    doc.save(final_path, garbage=3, deflate=True)
    doc.close()

    return final_path