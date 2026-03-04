"""Utility functions for file I/O and data processing."""

import os


def read_file_from_disk(path: str) -> str:
    """Reads file content (txt, md, csv, json, pdf).

    Args:
        path: File path

    Returns:
        str: File content

    Raises:
        ValueError: If file doesn't exist or format not supported
    """
    if not os.path.isfile(path):
        raise ValueError(f"File not found: {path}")

    ext = os.path.splitext(path)[1].lower()

    if ext in (".txt", ".md", ".csv", ".json"):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    elif ext == ".pdf":
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(path)
            return "\n\n".join(page.get_text() for page in doc)
        except ImportError:
            raise ValueError("PyMuPDF not installed. Install with: pip install PyMuPDF")
    else:
        # Try as generic text
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
        except Exception as e:
            raise ValueError(f"Error reading file {path}: {e}")
