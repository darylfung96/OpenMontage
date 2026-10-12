"""Media helpers shared by the RunningHub provider tools."""

from __future__ import annotations

import mimetypes
import struct
from pathlib import Path
from urllib.parse import urlparse


def looks_like_url(value: str) -> bool:
    return urlparse(str(value)).scheme in ("http", "https")


def extension_from_url(url: str, default: str) -> str:
    name = urlparse(str(url)).path.rsplit("/", 1)[-1]
    if "." in name:
        ext = name.rsplit(".", 1)[-1].lower()
        if 0 < len(ext) <= 5 and ext.isalnum():
            return ext
    return default


def numbered_output_path(path: Path) -> Path:
    """Return *path*, or ``name_2.ext`` / ``name_3.ext`` when it already exists.

    RunningHub apps can return several files for one take, and re-running a take
    must never overwrite an earlier one.
    """
    if not path.exists():
        return path
    index = 2
    while True:
        candidate = path.with_name(f"{path.stem}_{index}{path.suffix}")
        if not candidate.exists():
            return candidate
        index += 1


def guess_media_type(filename: str, default: str = "application/octet-stream") -> str:
    return mimetypes.guess_type(filename)[0] or default


def image_dimensions(path: Path | str) -> tuple[int, int] | None:
    """Return ``(width, height)`` for an image file, or None when unreadable."""
    try:
        from PIL import Image

        with Image.open(path) as image:
            return image.size
    except Exception:
        return None


def fix_mov_to_mp4(file_path: Path | str) -> bool:
    """Rewrite a QuickTime ``ftyp`` box into a standard MP4 brand.

    The DMAD MiniMax H3 app delivers its output in a MOV container whose only
    non-MP4 part is the ``ftyp`` header -- the payload itself is h264/aac. This
    patches that header in place: no re-encode, no external tools. Returns True
    when the file was rewritten.
    """
    target = Path(file_path)
    try:
        with open(target, "rb") as handle:
            header = handle.read(64)
    except OSError:
        return False

    if len(header) < 16:
        return False

    box_size = struct.unpack(">I", header[0:4])[0]
    if header[4:8] != b"ftyp" or box_size < 16 or box_size > len(header):
        return False
    if header[8:12] != b"qt  ":
        return False

    minor_version = header[12:16]
    brands = [b"isom", b"iso2", b"avc1", b"mp41"]
    max_brands = (box_size - 16) // 4

    new_ftyp = struct.pack(">I", box_size) + b"ftyp" + b"isom" + minor_version
    for brand in brands[:max_brands]:
        new_ftyp += brand
    new_ftyp += b"\x00" * (box_size - len(new_ftyp))

    if len(new_ftyp) != box_size:
        return False

    with open(target, "r+b") as handle:
        handle.write(new_ftyp)
    return True
