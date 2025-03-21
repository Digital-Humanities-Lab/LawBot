from io import BytesIO
import os
import tempfile
import PyPDF2
import docx


async def extract_text_from_doc(file_bytes: BytesIO) -> str:
    """Extract text from a .doc or .docx file"""
    with tempfile.NamedTemporaryFile(delete=False, suffix='.docx') as tmp_file:
        tmp_file.write(file_bytes.getvalue())
        tmp_file.flush()
        
        try:
            doc = docx.Document(tmp_file.name)
            text = '\n'.join([paragraph.text for paragraph in doc.paragraphs])
        finally:
            os.unlink(tmp_file.name)
    return text

async def extract_text_from_pdf(file_bytes: BytesIO) -> str:
    """Extract text from a PDF file"""
    pdf_reader = PyPDF2.PdfReader(file_bytes)
    text = ''
    for page in pdf_reader.pages:
        text += page.extract_text() + '\n'
    return text