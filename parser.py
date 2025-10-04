import ebooklib
from ebooklib import epub
import fitz  # PyMuPDF

def parse_epub(file_path):
    """
    Parses an EPUB file and returns the book object for in-place modification.
    """
    book = epub.read_epub(file_path)
    return book

def parse_pdf(file_path):
    """
    Parses a PDF, extracting text spans and caching embedded font data.
    Returns a dictionary containing the spans and the font cache.
    """
    doc = fitz.open(file_path)
    pages_spans = []
    font_cache = {}  # Cache font data by xref

    for page in doc:
        page_dict = page.get_text("rawdict", flags=fitz.TEXTFLAGS_PRESERVE_WHITESPACE)
        page_spans_list = []
        for block in page_dict.get("blocks", []):
            if block["type"] == 0:  # Text block
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        if span.get("text", "").strip():
                            font_xref = span.get("font_xref")
                            if font_xref and font_xref not in font_cache:
                                font_info = doc.extract_font(font_xref)
                                if font_info and font_info[4]: # Ensure buffer is not empty
                                    font_cache[font_xref] = {
                                        "buffer": font_info[4],
                                        "ext": font_info[1],
                                        "name": font_info[0]
                                    }
                            span['font_xref'] = font_xref
                            page_spans_list.append(span)
        pages_spans.append(page_spans_list)

    doc.close()
    return {"spans": pages_spans, "font_cache": font_cache}