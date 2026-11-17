"""Aether Mail core — local-first mail primitives for AetherOS.

The submodules are dependency-light and importable without GTK.  Only the
application layer (apps/mail/aether-mail.py) touches gi.
"""

from __future__ import annotations

from .attachment import (
    Attachment,
    AttachmentError,
    attach_to_message,
    build_mime_message,
    prepare_attachments,
    sanitize_filename,
)
from .imap_idle import (
    IdleConnectionError,
    IdleError,
    IdleSession,
    parse_idle_unsolicited,
)

__version__ = "1.0.0"

__all__ = [
    "__version__",
    "Attachment",
    "AttachmentError",
    "attach_to_message",
    "build_mime_message",
    "prepare_attachments",
    "sanitize_filename",
    "IdleConnectionError",
    "IdleError",
    "IdleSession",
    "parse_idle_unsolicited",
]
