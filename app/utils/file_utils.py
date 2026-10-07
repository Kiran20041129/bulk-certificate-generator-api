"""File-name helpers."""
import re


def safe_filename(text: str, default: str = "certificate") -> str:
    """Turn arbitrary text into a safe file name (no slashes, spaces, etc.)."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("._")
    return cleaned[:60] or default
