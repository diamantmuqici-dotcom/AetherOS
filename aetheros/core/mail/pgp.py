"""OpenPGP operations through the gpg binary.

All invocations use argv lists with shell=False. Untrusted plaintext and
ciphertext travel over stdin; only a validated fingerprint reaches argv.
"""

from __future__ import annotations

import re
import shutil
import subprocess

DEFAULT_TIMEOUT = 30
_FPR_RE = re.compile(r"^[0-9A-Fa-f]{16,40}$")


class PGPError(Exception):
    """Base class for OpenPGP failures."""


class GPGUnavailableError(PGPError):
    """gpg is missing or not executable."""


class GPGFailureError(PGPError):
    """gpg rejected the operation."""


def is_available() -> bool:
    return shutil.which("gpg") is not None


def require_gpg() -> str:
    executable = shutil.which("gpg")
    if not executable:
        raise GPGUnavailableError("gpg is not installed or is not on PATH")
    return executable


def _check_fpr(fingerprint: str) -> str:
    if not isinstance(fingerprint, str):
        raise PGPError("fingerprint must be a string")
    normalized = fingerprint.replace(" ", "").replace("\t", "")
    if not _FPR_RE.fullmatch(normalized):
        raise PGPError("fingerprint must be 16..40 hexadecimal characters")
    return normalized.upper()


def _run(args: list[str], data: bytes, timeout: int = DEFAULT_TIMEOUT) -> bytes:
    executable = require_gpg()
    cmd = [executable, "--batch", "--yes", "--no-tty", *args]
    try:
        proc = subprocess.run(
            cmd,
            input=data,
            capture_output=True,
            timeout=timeout,
            shell=False,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise GPGFailureError("gpg operation timed out") from exc
    except OSError as exc:
        raise GPGUnavailableError(f"gpg could not be started: {exc}") from exc
    if proc.returncode != 0:
        detail = (proc.stderr or b"").decode("utf-8", "replace").strip()[:1000]
        raise GPGFailureError(detail or f"gpg exited with status {proc.returncode}")
    return proc.stdout or b""


def encrypt(plaintext: str | bytes, recipient_fpr: str, timeout: int = DEFAULT_TIMEOUT) -> str:
    fpr = _check_fpr(recipient_fpr)
    data = plaintext.encode("utf-8") if isinstance(plaintext, str) else bytes(plaintext)
    if len(data) > 8 * 1024 * 1024:
        raise PGPError("plaintext exceeds the size limit")
    out = _run(["--armor", "--trust-model", "always", "--encrypt", "--recipient", fpr], data, timeout)
    text = out.decode("ascii", "replace")
    if "-----BEGIN PGP MESSAGE-----" not in text:
        raise GPGFailureError("gpg did not return an armored message")
    return text


def decrypt(ciphertext: str | bytes, timeout: int = DEFAULT_TIMEOUT) -> str:
    data = ciphertext.encode("utf-8") if isinstance(ciphertext, str) else bytes(ciphertext)
    if len(data) > 16 * 1024 * 1024:
        raise PGPError("ciphertext exceeds the size limit")
    return _run(["--decrypt"], data, timeout).decode("utf-8", "replace")


def sign(text: str, sender_fpr: str, timeout: int = DEFAULT_TIMEOUT) -> str:
    fpr = _check_fpr(sender_fpr)
    data = text.encode("utf-8")
    if len(data) > 8 * 1024 * 1024:
        raise PGPError("text exceeds the size limit")
    out = _run(["--armor", "--clearsign", "--local-user", fpr], data, timeout)
    signed = out.decode("utf-8", "replace")
    if "-----BEGIN PGP SIGNED MESSAGE-----" not in signed:
        raise GPGFailureError("gpg did not return a clearsigned message")
    return signed


def verify(signed_text: str | bytes, timeout: int = DEFAULT_TIMEOUT) -> str:
    data = signed_text.encode("utf-8") if isinstance(signed_text, str) else bytes(signed_text)
    if len(data) > 16 * 1024 * 1024:
        raise PGPError("signed text exceeds the size limit")
    return _run(["--verify"], data, timeout).decode("utf-8", "replace")
