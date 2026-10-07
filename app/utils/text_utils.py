"""Text helpers."""

# The built-in PDF fonts (Helvetica, Times) use the Windows-1252 character set:
# English and Western-European names work, Devanagari/Chinese/etc. do not.
PDF_ENCODING = "cp1252"


def is_pdf_safe(text: str) -> bool:
    """True if every character can be printed with the built-in PDF fonts."""
    try:
        text.encode(PDF_ENCODING)
    except UnicodeEncodeError:
        return False
    return True
