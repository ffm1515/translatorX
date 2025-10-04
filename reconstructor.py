import ebooklib
from ebooklib import epub
import fitz  # PyMuPDF
import os

from bs4 import BeautifulSoup

def reconstruct_epub(translated_segments, book_data, original_file_name, output_format="Replace Original Text"):
    """
    Reconstructs the EPUB file using block-level replacements based on unique IDs.
    """
    book = book_data['book']
    soups = book_data['soups']
    items = book_data['items']

    for segment in translated_segments:
        metadata = segment['metadata']
        item_name = metadata['item_name']
        block_id = metadata['block_id']
        original_html = segment['original_text']
        translated_html = segment['translated_text']

        soup = soups.get(item_name)
        if not soup:
            continue

        element_to_modify = soup.find(attrs={'data-translatorx-id': block_id})
        if not element_to_modify:
            continue

        # Clean up the ID after finding the element
        del element_to_modify['data-translatorx-id']

        if output_format == "Translation Below Original":
            # The original element is kept as is. A new element with the translation is inserted after it.
            new_tag = soup.new_tag("div")
            new_tag.attrs['style'] = "font-style: italic; color: #555; margin-top: 5px; margin-bottom: 5px; border-top: 1px solid #ccc; padding-top: 5px;"
            # The translated_html is parsed and appended to the new tag
            new_tag.append(BeautifulSoup(translated_html, 'html.parser'))
            element_to_modify.insert_after(new_tag)

        elif output_format == "Side-by-Side (Two Columns)":
            # The original element is replaced by a table containing both original and translated content.
            table = soup.new_tag("table")
            table.attrs['style'] = "width: 100%; border-collapse: collapse; margin-top: 10px; margin-bottom: 10px; border: 1px solid #ddd;"
            tr = soup.new_tag("tr")

            td_orig = soup.new_tag("td", attrs={'style': "width: 50%; padding: 8px; vertical-align: top; border: 1px solid #ddd;"})
            td_orig.append(BeautifulSoup(original_html, 'html.parser'))

            td_trans = soup.new_tag("td", attrs={'style': "width: 50%; padding: 8px; vertical-align: top; border: 1px solid #ddd;"})
            td_trans.append(BeautifulSoup(translated_html, 'html.parser'))

            tr.append(td_orig)
            tr.append(td_trans)
            table.append(tr)
            element_to_modify.replace_with(table)

        else:  # Default: "Replace Original Text"
            # Clear the original content and insert the translated HTML
            element_to_modify.clear()
            element_to_modify.append(BeautifulSoup(translated_html, 'html.parser'))

    # Write the modified soup content back to the ebook items
    for item in items:
        soup = soups.get(item.get_name())
        if soup:
            # Use decode_contents to avoid adding extra <html><body> tags, but rather just the content
            item.set_content(soup.encode_contents(formatter="html5"))


    # Define an output directory to avoid clutter
    output_dir = "temp_output"
    os.makedirs(output_dir, exist_ok=True)
    output_file_path = os.path.join(output_dir, "translated_" + os.path.basename(original_file_name))

    # Write the modified book object to a new file
    epub.write_epub(output_file_path, book, {})
    return output_file_path

from collections import defaultdict

from reportlab.lib.pagesizes import landscape, letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.lib import colors

def _reconstruct_pdf_side_by_side(translated_segments, original_file_path):
    """
    Creates a new side-by-side PDF using reportlab.
    """
    output_dir = "temp_output"
    os.makedirs(output_dir, exist_ok=True)
    file_name = "translated_side_by_side_" + os.path.basename(original_file_path)
    final_path = os.path.join(output_dir, file_name)

    doc = SimpleDocTemplate(final_path, pagesize=landscape(letter))
    styles = getSampleStyleSheet()
    styleN = styles['Normal']
    styleH = styles['h2']
    story = []

    segments_by_page = defaultdict(list)
    for segment in translated_segments:
        pno = segment['metadata'].get('pno')
        if pno is not None:
            segments_by_page[pno].append(segment)

    for pno in sorted(segments_by_page.keys()):
        story.append(Paragraph(f"--- Original Page: {pno + 1} ---", styleH))
        story.append(Spacer(1, 0.2 * inch))

        table_data = []
        for segment in segments_by_page[pno]:
            original_text = segment['original_text'].replace('\n', '<br/>')
            translated_text = segment['translated_text'].replace('\n', '<br/>')
            table_data.append([Paragraph(original_text, styleN), Paragraph(translated_text, styleN)])

        if table_data:
            table = Table(table_data, colWidths=[5 * inch, 5 * inch])
            table.setStyle(TableStyle([
                ('VALIGN', (0,0), (-1,-1), 'TOP'),
                ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
                ('BOX', (0,0), (-1,-1), 1, colors.black),
                ('BACKGROUND', (0,0), (0,-1), colors.whitesmoke),
            ]))
            story.append(table)
        story.append(Spacer(1, 0.3 * inch))

    doc.build(story)
    return final_path


def reconstruct_pdf(translated_segments, original_file_path, font_cache, output_format="Replace Original Text"):
    """
    Reconstructs a PDF based on the chosen output format, preserving original fonts.
    """
    if output_format == "Side-by-Side (Two Columns)":
        return _reconstruct_pdf_side_by_side(translated_segments, original_file_path)

    # Default behavior: Replace Original Text
    doc = fitz.open(original_file_path)

    # --- Font Handling Setup ---
    temp_font_dir = os.path.join("temp_output", "fonts")
    os.makedirs(temp_font_dir, exist_ok=True)
    font_paths = {}  # Cache for paths to temporary font files

    # --- Segment Processing ---
    segments_by_page = defaultdict(list)
    for segment in translated_segments:
        pno = segment['metadata'].get('pno')
        if pno is not None:
            segments_by_page[pno].append(segment)

    for pno, segments in segments_by_page.items():
        if pno >= len(doc):
            continue
        page = doc.load_page(pno)
        for segment in segments:
            original_span = segment['metadata']
            translated_text = segment['translated_text'].strip()
            if not translated_text:
                continue

            bbox = fitz.Rect(original_span['bbox'])
            page.draw_rect(bbox, color=(1, 1, 1), fill=(1, 1, 1), overlay=True)

            # --- Font Reconstruction ---
            font_xref = original_span.get('font_xref')
            font_info = font_cache.get(font_xref)
            fontfile = None
            fontname = "helv"  # Default fallback font

            if font_info and font_info.get("buffer"):
                if font_xref not in font_paths:
                    font_ext = font_info.get("ext", "ttf")
                    temp_font_path = os.path.join(temp_font_dir, f"font_{font_xref}.{font_ext}")
                    with open(temp_font_path, "wb") as f_out:
                        f_out.write(font_info["buffer"])
                    font_paths[font_xref] = temp_font_path

                fontfile = font_paths[font_xref]
                fontname = font_info.get("name", f"F{font_xref}")

            # --- Text Insertion ---
            fontsize = original_span['size']
            fontcolor_int = original_span['color']
            r = ((fontcolor_int >> 16) & 0xFF) / 255.0
            g = ((fontcolor_int >> 8) & 0xFF) / 255.0
            b = (fontcolor_int & 0xFF) / 255.0
            color_tuple = (r, g, b)

            min_fontsize = 4.0
            current_fontsize = fontsize
            leftover_text = page.insert_textbox(
                bbox, translated_text, fontsize=current_fontsize, fontname=fontname, fontfile=fontfile, color=color_tuple, align=0
            )
            while leftover_text > 1 and current_fontsize > min_fontsize:
                current_fontsize -= 0.5
                page.draw_rect(bbox, color=(1, 1, 1), fill=(1, 1, 1), overlay=True)
                leftover_text = page.insert_textbox(
                    bbox, translated_text, fontsize=current_fontsize, fontname=fontname, fontfile=fontfile, color=color_tuple, align=0
                )

    output_dir = "temp_output"
    os.makedirs(output_dir, exist_ok=True)
    final_path = os.path.join(output_dir, "translated_" + os.path.basename(original_file_path))
    doc.save(final_path, garbage=3, deflate=True)
    doc.close()
    return final_path