"""Document content conversion tools"""

from io import BytesIO

from .albert import AlbertAI


def pdf_to_markdown(content: BytesIO):
    """Convert PDF stream into markdown"""
    return AlbertAI().convert(content=content, mimetype="application/pdf")
