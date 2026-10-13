"""File validation: extension, size, magic bytes and container integrity."""
import hashlib
import zipfile
from pathlib import Path

from .config import DEFAULT, Settings

OOXML_MAIN_PART = {".docx": "word/document.xml", ".pptx": "ppt/presentation.xml"}


class ValidationError(Exception):
    pass


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def validate(path, settings: Settings = DEFAULT) -> dict:
    """Return basic file facts or raise ValidationError with a clear reason."""
    path = Path(path)
    if not path.exists():
        raise ValidationError("file not found")
    ext = path.suffix.lower()
    if ext not in settings.allowed_ext:
        raise ValidationError(f"unsupported file type '{ext}' (supported: {', '.join(settings.allowed_ext)})")
    size = path.stat().st_size
    if size == 0:
        raise ValidationError("file is empty")
    if size > settings.max_file_mb * 1024 * 1024:
        raise ValidationError(f"file exceeds {settings.max_file_mb} MB limit")
    with open(path, "rb") as f:
        head = f.read(8)
    if ext == ".pdf":
        if not head.startswith(b"%PDF"):
            raise ValidationError("not a valid PDF (missing %PDF header)")
        import pymupdf
        try:
            with pymupdf.open(path) as d:
                if d.page_count == 0:
                    raise ValidationError("PDF has no pages")
                if d.needs_pass:
                    raise ValidationError("PDF is password-protected")
        except ValidationError:
            raise
        except Exception as e:  # corrupt structure
            raise ValidationError(f"PDF could not be opened: {type(e).__name__}")
    else:
        if not head.startswith(b"PK"):
            raise ValidationError(f"not a valid {ext} (not a ZIP/OOXML container)")
        try:
            with zipfile.ZipFile(path) as z:
                bad = z.testzip()
                if bad:
                    raise ValidationError(f"corrupt archive member: {bad}")
                if OOXML_MAIN_PART[ext] not in z.namelist():
                    raise ValidationError(f"{ext} is missing {OOXML_MAIN_PART[ext]}")
        except zipfile.BadZipFile:
            raise ValidationError(f"{ext} archive is corrupt")
    return {"filetype": ext.lstrip("."), "size_bytes": size, "sha256": sha256(path)}
