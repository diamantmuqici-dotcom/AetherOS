"""Safe outbound attachment handling for Aether Mail.

Extension claims and sniffed magic must both agree on an allowed MIME type.
Executable types are blocked unconditionally. No shell or exec is used.
"""

from __future__ import annotations

import mimetypes
import pathlib
import stat
from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import Iterable, Sequence

MAX_TOTAL_BYTES = 20 * 1024 * 1024
MAX_EACH_BYTES = 10 * 1024 * 1024
MAX_ATTACHMENTS = 20
MAX_FILENAME_LEN = 120
HARD_MAX_TOTAL_BYTES = 64 * 1024 * 1024
HARD_MAX_EACH_BYTES = 20 * 1024 * 1024

DEFAULT_ALLOWED_TYPES = frozenset({
    "text/plain",
    "text/csv",
    "image/png",
    "image/jpeg",
    "image/gif",
    "application/pdf",
    "application/zip",
})

EXECUTABLE_EXTENSIONS = frozenset({
    ".exe", ".dll", ".so", ".dylib", ".app", ".com", ".scr", ".msi", ".msp",
    ".bat", ".cmd", ".ps1", ".sh", ".bash", ".zsh", ".csh", ".ksh", ".vbs",
    ".js", ".jse", ".wsf", ".wsh", ".hta", ".pif", ".reg", ".py", ".pyc",
    ".pyw", ".pl", ".rb", ".php", ".cgi", ".jar", ".war", ".class", ".o",
    ".a", ".obj", ".elf", ".bin", ".deb", ".rpm", ".apk", ".appimage",
})

_TEXT_TYPES = frozenset({"text/plain", "text/csv"})

# Windows' mimetypes registry reports legacy aliases for common types.
_MIME_ALIASES = {
    "application/x-zip-compressed": "application/zip",
    "application/x-zip": "application/zip",
    "image/jpg": "image/jpeg",
    "image/pjpeg": "image/jpeg",
    "text/x-csv": "text/csv",
}

_MAGIC: tuple[tuple[bytes, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"%PDF-", "application/pdf"),
    (b"PK\x03\x04", "application/zip"),
    (b"PK\x05\x06", "application/zip"),
    (b"PK\x07\x08", "application/zip"),
)


class AttachmentError(ValueError):
    """An attachment failed policy validation."""


@dataclass(frozen=True)
class Attachment:
    filename: str
    content_type: str
    data: bytes
    size: int = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.data, (bytes, bytearray)):
            raise AttachmentError("attachment data must be bytes")
        object.__setattr__(self, "data", bytes(self.data))
        object.__setattr__(self, "size", len(self.data))


def sanitize_filename(name: object) -> str:
    """Return a safe basename with no path parts, controls or separators."""
    text = str(name).replace("\\", "/").rsplit("/", 1)[-1]
    text = "".join(
        ch for ch in text
        if ord(ch) >= 0x20 and ch != "\x7f" and ch not in ':*?"<>|'
    )
    text = text.strip().strip(".")
    if not text:
        text = "attachment"
    return text[:MAX_FILENAME_LEN]


def _sniff(data: bytes) -> str | None:
    for signature, mime in _MAGIC:
        if data.startswith(signature):
            return mime
    head = data[:4096]
    if b"\x00" in head:
        return None
    try:
        head.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return "text/plain"


def _compatible(extension_mime: str, sniffed_mime: str | None) -> bool:
    if sniffed_mime is None:
        return False
    if extension_mime == sniffed_mime:
        return True
    return extension_mime in _TEXT_TYPES and sniffed_mime in _TEXT_TYPES


def _bounded(value: int, label: str, ceiling: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise AttachmentError(f"{label} must be an integer")
    if value < 1 or value > ceiling:
        raise AttachmentError(f"{label} must be in 1..{ceiling}")
    return value


def prepare_attachments(
    files: Iterable[pathlib.Path | str],
    max_total: int = MAX_TOTAL_BYTES,
    max_each: int = MAX_EACH_BYTES,
    allowed_types: Iterable[str] = DEFAULT_ALLOWED_TYPES,
    max_count: int = MAX_ATTACHMENTS,
) -> list[Attachment]:
    """Read and validate files against the attachment policy, fail-closed."""
    total_cap = _bounded(max_total, "max_total", HARD_MAX_TOTAL_BYTES)
    each_cap = _bounded(max_each, "max_each", HARD_MAX_EACH_BYTES)
    count_cap = _bounded(max_count, "max_count", 64)
    allowed = frozenset(str(item).lower() for item in allowed_types)
    if not allowed:
        raise AttachmentError("allowed_types must not be empty")

    paths = [pathlib.Path(item) for item in files]
    if len(paths) > count_cap:
        raise AttachmentError(f"at most {count_cap} attachments are allowed")

    prepared: list[Attachment] = []
    total = 0
    for path in paths:
        try:
            info = path.stat()
        except OSError as exc:
            raise AttachmentError(f"cannot stat {sanitize_filename(path.name)!r}") from exc
        if not stat.S_ISREG(info.st_mode):
            raise AttachmentError(f"not a regular file: {sanitize_filename(path.name)!r}")
        if info.st_size > each_cap:
            raise AttachmentError(f"{sanitize_filename(path.name)!r} exceeds the per-file limit")

        try:
            with path.open("rb") as handle:
                data = handle.read(each_cap + 1)
        except OSError as exc:
            raise AttachmentError(f"cannot read {sanitize_filename(path.name)!r}") from exc
        if len(data) > each_cap:
            raise AttachmentError(f"{sanitize_filename(path.name)!r} exceeds the per-file limit")

        total += len(data)
        if total > total_cap:
            raise AttachmentError("attachments exceed the total size limit")

        filename = sanitize_filename(path.name)
        extension = pathlib.Path(filename).suffix.lower()
        if extension in EXECUTABLE_EXTENSIONS:
            raise AttachmentError(f"executable attachment type rejected: {extension}")
        guessed = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        extension_mime = _MIME_ALIASES.get(guessed, guessed)
        if extension_mime not in allowed:
            raise AttachmentError(f"disallowed attachment type: {extension_mime}")
        sniffed_mime = _sniff(data)
        if sniffed_mime not in allowed or not _compatible(extension_mime, sniffed_mime):
            raise AttachmentError(f"content does not match {extension_mime}: {filename}")

        prepared.append(Attachment(filename, extension_mime, data))
    return prepared


def attach_to_message(message: EmailMessage, attachments: Sequence[Attachment]) -> EmailMessage:
    """Add validated attachments to an existing message using base64."""
    for item in attachments:
        if not isinstance(item, Attachment):
            raise AttachmentError("attachments must be Attachment instances")
        maintype, _, subtype = item.content_type.partition("/")
        if not maintype or not subtype:
            raise AttachmentError(f"invalid content type: {item.content_type}")
        message.add_attachment(
            item.data,
            maintype=maintype,
            subtype=subtype,
            filename=sanitize_filename(item.filename),
            cte="base64",
        )
    return message


def build_mime_message(text: str, attachments: Sequence[Attachment]) -> EmailMessage:
    """Build a multipart EmailMessage with base64-encoded attachments."""
    if not isinstance(text, str):
        raise AttachmentError("text must be a string")
    message = EmailMessage()
    message.set_content(text)
    return attach_to_message(message, attachments)
