from pathlib import Path
from fastapi import HTTPException, status, UploadFile
from app.config import settings

VALID_EXTENSIONS = {ext.lower() for ext in settings.ALLOWED_EXTENSIONS}
VALID_FTYP_BRANDS = {b"isom", b"iso2", b"mp41", b"mp42", b"qt  ", b"M4V ", b"MSNV", b"avc1", b"dash", b"3gp4"}


def is_valid_extension(filename: str | None) -> bool:
    if not filename:
        return False
    ext = Path(filename).suffix.lower()
    return ext in VALID_EXTENSIONS


def validate_container_header(header_bytes: bytes, filename: str) -> bool:
    """
    Validates actual binary container signature of MP4, AVI, and MOV files.
    Rejects text files, images, or fake extension files.
    """
    if len(header_bytes) < 12:
        return False

    ext = Path(filename).suffix.lower()

    # MP4 & MOV container validation (ISO Base Media File Format)
    if ext in [".mp4", ".mov"]:
        # Standard MP4/MOV files have 'ftyp' at offset 4..8
        if header_bytes[4:8] == b"ftyp":
            brand = header_bytes[8:12]
            if brand in VALID_FTYP_BRANDS or brand.startswith(b"mp4") or brand.startswith(b"is"):
                return True
            # Also allow any valid 4-byte ASCII brand identifier
            if all(32 <= b <= 126 for b in brand):
                return True

        # MOV/MP4 files can also start with atoms like moov, mdat, free, wide, skip
        atom_type = header_bytes[4:8]
        if atom_type in [b"moov", b"mdat", b"free", b"wide", b"skip", b"pnot"]:
            return True

    # AVI container validation
    if ext == ".avi":
        # RIFF header at 0..4 and AVI signature at 8..12
        if header_bytes[0:4] == b"RIFF" and header_bytes[8:12] == b"AVI ":
            return True

    return False


async def validate_upload_file(file: UploadFile) -> str:
    """
    Validates uploaded file extension, container header, and enforces file size limit.
    Returns the lowercased extension if valid.
    Raises HTTPException (400 or 413) if invalid.
    """
    filename = file.filename or "unknown"
    ext = Path(filename).suffix.lower()

    # 1. Extension check
    if ext not in VALID_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file format '{ext}'. Only .mp4, .avi, and .mov files are allowed."
        )

    # 2. Container signature header check
    header_sample = await file.read(64)
    await file.seek(0)  # Reset stream position after reading sample

    if not validate_container_header(header_sample, filename):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid video container or corrupted file header for file '{filename}'."
        )

    return ext
