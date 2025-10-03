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
    Parses a PDF file and extracts all text spans with their metadata from each page.
    Returns a list of pages, where each page is a list of span dictionaries.
    """
    doc = fitz.open(file_path)
    pages_spans = []

    for page in doc:
        # Using get_text("dict") is the most detailed way to extract content.
        page_dict = page.get_text("dict", flags=fitz.TEXTFLAGS_PRESERVE_WHITESPACE)

        page_spans = []
        for block in page_dict.get("blocks", []):
            if block["type"] == 0:  # 0 indicates a text block
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        # We only care about spans with actual text content.
                        if span.get("text", "").strip():
                            page_spans.append(span)
        pages_spans.append(page_spans)

    doc.close()
    return pages_spans