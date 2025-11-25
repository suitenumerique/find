"""Document content conversion tools"""

from io import BytesIO, StringIO

from unstructured.documents import elements
from unstructured.partition.docx import partition_docx
from unstructured.partition.html import partition_html
from unstructured.partition.odt import partition_odt
from unstructured.partition.pptx import partition_pptx
from unstructured.partition.rst import partition_rst
from unstructured.partition.rtf import partition_rtf
from unstructured.partition.xlsx import partition_xlsx

from .albert import AlbertAI


def elements_to_markdown(parts):
    """Format unstructured elements as markdown"""
    output = StringIO()

    for part in parts:
        if isinstance(part, elements.Title):
            output.write("## ")
            output.write(part.text)
        elif isinstance(part, elements.ListItem):
            output.write(" - ")
            output.write(part.text)
        else:
            output.write(part.text)

        output.write("\n")

    return output.getvalue()


def pdf_to_markdown(content: BytesIO):
    """Convert PDF stream into markdown"""
    return AlbertAI().convert(content=content, mimetype="application/pdf")


def docx_to_markdown(content: BytesIO):
    """Convert docx stream into markdown"""
    return elements_to_markdown(partition_docx(file=content))


def pptx_to_markdown(content: BytesIO):
    """Convert pptx stream into markdown"""
    return elements_to_markdown(partition_pptx(file=content))


def xlsx_to_markdown(content: BytesIO):
    """Convert xlsx stream into markdown"""
    return elements_to_markdown(partition_xlsx(file=content))


def odt_to_markdown(content: BytesIO):
    """Convert odt stream into markdown"""
    return elements_to_markdown(partition_odt(file=content))


def html_to_markdown(content: BytesIO):
    """Convert html stream into markdown"""
    return elements_to_markdown(partition_html(file=content))


def rtf_to_markdown(content: BytesIO):
    """Convert rtf stream into markdown"""
    return elements_to_markdown(partition_rtf(file=content))


def rst_to_markdown(content: BytesIO):
    """Convert rst stream into markdown"""
    return elements_to_markdown(partition_rst(file=content))
