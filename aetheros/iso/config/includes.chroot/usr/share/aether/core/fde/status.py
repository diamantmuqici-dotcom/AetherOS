"""Pure, headless LUKS2 full-disk-encryption status helpers.

No gi, no subprocess, no filesystem access at import time. Every function is
deterministic so it can be used by the offline verifier and by tests alike.
"""

from __future__ import annotations

import json
import re

# Required cryptsetup flags for a strong LUKS2 header. Kept as an exported
# constant so the installer helper and the verifier agree on the same bar.
REQUIRED_LUKS2_FLAGS: tuple[str, ...] = ("--type luks2", "--pbkdf argon2id")

_VERSION_RE = re.compile(r"^[ \t]*Version[ \t]*:[ \t]*(\d+)", re.IGNORECASE | re.MULTILINE)
_UUID_RE = re.compile(
    r"^[ \t]*UUID[ \t]*:[ \t]*([0-9A-Fa-f-]{8,})", re.IGNORECASE | re.MULTILINE
)
_CIPHER_RE = re.compile(r"^[ \t]*cipher[ \t]*:[ \t]*(\S+)", re.IGNORECASE | re.MULTILINE)
_PBKDF_RE = re.compile(r"^[ \t]*PBKDF[ \t]*:[ \t]*(\S+)", re.IGNORECASE | re.MULTILINE)
_ITER_RE = re.compile(
    r"^[ \t]*(?:Iteration|Time[ \t]+cost)[ \t]*:[ \t]*(\d+)",
    re.IGNORECASE | re.MULTILINE,
)
_SLOT_RE = re.compile(r"^[ \t]*\d+:[ \t]*luks2\b", re.IGNORECASE | re.MULTILINE)

_REQUIRED_SCALARS = ("version", "cipher", "pbkdf", "iterations", "uuid")


def parse_luks_dump(text: str) -> dict:
    """Extract LUKS2 header facts from ``cryptsetup luksDump`` text.

    Formatting is tolerated (case-insensitive keys, flexible horizontal
    whitespace). Values that cannot be found stay ``None``; the slot count
    defaults to zero. Missing fields are reported in ``missing`` so callers
    can fail closed instead of inventing state.
    """
    if not isinstance(text, str):
        raise TypeError("dump text must be a string")

    result: dict = {
        "version": None,
        "cipher": None,
        "pbkdf": None,
        "iterations": None,
        "keyslots_enabled": 0,
        "uuid": None,
    }

    match = _VERSION_RE.search(text)
    if match:
        result["version"] = int(match.group(1))

    match = _UUID_RE.search(text)
    if match:
        result["uuid"] = match.group(1).strip()

    match = _CIPHER_RE.search(text)
    if match:
        result["cipher"] = match.group(1)

    match = _PBKDF_RE.search(text)
    if match:
        result["pbkdf"] = match.group(1).lower()

    match = _ITER_RE.search(text)
    if match:
        result["iterations"] = int(match.group(1))

    result["keyslots_enabled"] = len(_SLOT_RE.findall(text))
    result["missing"] = [k for k in _REQUIRED_SCALARS if result[k] is None]
    return result


def fde_status(
    dump_text: str,
    bootloader_encrypted: bool = False,
    swap_encrypted: bool = False,
    keyfile_external: bool = False,
) -> dict:
    """Return a canonical FDE report from a luksDump plus coverage facts.

    ``bootloader_encrypted`` reflects the ESP/boot chain, ``swap_encrypted``
    the swap volume, and ``keyfile_external`` whether key material lives off
    the image. All default to False so an incomplete caller still fails closed.
    """
    parsed = parse_luks_dump(dump_text)

    luks2 = parsed["version"] == 2
    argon2id = parsed["pbkdf"] == "argon2id"
    keyslots = parsed["keyslots_enabled"]
    keyslots_ok = keyslots >= 1

    gaps: list[str] = []
    if not luks2:
        gaps.append("LUKS2 header missing or version is not 2")
    if not argon2id:
        gaps.append("PBKDF is not argon2id")
    if not keyslots_ok:
        gaps.append("no active LUKS key slot")
    if not bootloader_encrypted:
        gaps.append("bootloader/ESP not encrypted (cover with Secure Boot)")
    if not swap_encrypted:
        gaps.append("swap not encrypted")
    if not keyfile_external:
        gaps.append("key material stored in image, not on separate media")

    if not (luks2 and keyslots_ok):
        overall = "NOT_ENCRYPTED"
    elif gaps:
        overall = "FDE_PARTIAL"
    else:
        overall = "FDE_STRONG"

    return {
        "luks2": luks2,
        "argon2id": argon2id,
        "keyslots": keyslots,
        "keyslots_ok": keyslots_ok,
        "bootloader_encrypted": bool(bootloader_encrypted),
        "swap_encrypted": bool(swap_encrypted),
        "key_external": bool(keyfile_external),
        "overall": overall,
        "gaps": gaps,
    }


def render_report(report: dict) -> str:
    """Serialise a report as canonical, deterministic JSON."""
    return json.dumps(report, sort_keys=True, separators=(",", ":"))
