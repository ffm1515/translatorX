import ebooklib
from ebooklib import epub
import fitz  # PyMuPDF
import os

def reconstruct_epub(translated_segments, book_data, original_file_name, output_format="Replace Original Text"):
    """
    Reconstructs the EPUB file from the (potentially edited) translated segments,
    applying the specified output format.
    """
    book = book_data['book']
    soups = book_data['soups']
    items = book_data['items']

    # To prevent processing the same parent multiple times in side-by-side mode
    processed_parents = set()

    for segment in translated_segments:
        node = segment['metadata']['node']
        soup = segment['metadata']['soup']
        original_text = segment['original_text']
        translated_text = segment['translated_text']

        if output_format == "Translation Below Original":
            # Create a new <p> tag for the translation, style it, and insert it
            # after the parent of the original text node.
            new_p = soup.new_tag("p")
            new_p.string = translated_text
            new_p.attrs['style'] = "font-style: italic; color: #555; margin-top: 5px; margin-bottom: 5px;"
            if node.parent:
                # If the parent is the body, append the new paragraph.
                # Otherwise, insert it after the parent element (e.g., after the <p> tag).
                if node.parent.name == 'body':
                    node.parent.append(new_p)
                else:
                    node.parent.insert_after(new_p)

        elif output_format == "Side-by-Side (Two Columns)":
            # Replace the text node with a 2-column table
            table = soup.new_tag("table")
            table.attrs['style'] = "width: 100%; border-collapse: collapse; margin-top: 10px; margin-bottom: 10px; border: 1px solid #ddd;"
            tr = soup.new_tag("tr")

            td_orig = soup.new_tag("td", attrs={'style': "width: 50%; padding: 8px; vertical-align: top; border: 1px solid #ddd;"})
            td_orig.string = original_text

            td_trans = soup.new_tag("td", attrs={'style': "width: 50%; padding: 8px; vertical-align: top; border: 1px solid #ddd;"})
            td_trans.string = translated_text

            tr.append(td_orig)
            tr.append(td_trans)
            table.append(tr)

            node.replace_with(table)

        else:  # Default: "Replace Original Text"
            node.replace_with(translated_text)

    # Write the modified soup content back to the ebook items
    for item in items:
        # Find the corresponding soup object
        soup = soups.get(item.get_name())
        if soup:
            item.set_content(soup.prettify(encoding='utf-8'))

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

        # Sort segments by vertical position to maintain reading order
        page_segments = sorted(segments_by_page[pno], key=lambda s: s['metadata']['bbox'][1])

        table_data = []
        for segment in page_segments:
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


def reconstruct_pdf(translated_segments, original_file_path, output_format="Replace Original Text"):
    """
    Reconstructs a PDF based on the chosen output format.
    """
    if output_format == "Side-by-Side (Two Columns)":
        return _reconstruct_pdf_side_by_side(translated_segments, original_file_path)

    # Default behavior: Replace Original Text
    doc = fitz.open(original_file_path)
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

            fontname = _get_base_font_name(original_span['font'])
            fontsize = original_span['size']
            fontcolor_int = original_span['color']
            r = ((fontcolor_int >> 16) & 0xFF) / 255.0
            g = ((fontcolor_int >> 8) & 0xFF) / 255.0
            b = (fontcolor_int & 0xFF) / 255.0
            color_tuple = (r, g, b)

            min_fontsize = 4.0
            current_fontsize = fontsize
            leftover_text = page.insert_textbox(
                bbox, translated_text, fontsize=current_fontsize, fontname=fontname, color=color_tuple, align=0
            )
            while leftover_text > 1 and current_fontsize > min_fontsize:
                current_fontsize -= 0.5
                page.draw_rect(bbox, color=(1, 1, 1), fill=(1, 1, 1), overlay=True)
                leftover_text = page.insert_textbox(
                    bbox, translated_text, fontsize=current_fontsize, fontname=fontname, color=color_tuple, align=0
                )

    output_dir = "temp_output"
    os.makedirs(output_dir, exist_ok=True)
    final_path = os.path.join(output_dir, "translated_" + os.path.basename(original_file_path))
    doc.save(final_path, garbage=3, deflate=True)
    doc.close()
    return final_path