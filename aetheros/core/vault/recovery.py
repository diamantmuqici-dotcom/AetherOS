"""Wordlist-based vault recovery phrases with checksum and Argon2id key derivation."""

from __future__ import annotations

import hashlib
import os

from cryptography.hazmat.primitives.kdf.argon2 import Argon2id

__all__ = [
    "RecoveryError",
    "WORDLIST",
    "WORD_COUNT",
    "ENTROPY_BYTES",
    "generate_recovery_phrase",
    "encode_entropy",
    "decode_phrase",
    "mnemonic_to_key",
]

# Fixed 256-word list: one word index maps to exactly one byte (8 bits).
WORDLIST: tuple[str, ...] = tuple(
    """
    able acid aged also amid anchor ancient anger angle ant apex apple april arch arctic armor
    arrow ash atlas atom audio awful axis baby badger baker basic basil beach bench berry better
    beyond bird bitter black blade blame blank blast bleak blend bless blind block bloom blue blur
    boat body boil bold bolt bomb bone book boost bound brake branch brass brave bread brick
    bridge bright brisk broad broom brown brush build burst cabin cable cactus cake calm camera canal
    candy cannon canvas canyon cap carbon card cargo carpet carrot cart case cash castle catalog catch
    cause cedar cell center chalk chamber charm chart chase cheap check cheese cherry chest chief child
    chill china chip chocolate choice chord chorus chrome church circle clay clean clerk clear cliff climb
    clock close cloth cloud clown coach coast cobra cocoa coffee coil coin cold color comet corner
    cosmic cotton couch cough country course cousin cover crack craft crane crash crate crawl crazy cream
    creek crest cricket crime crisp crown cruise crumb crush crust crystal cube culture cup curl curve
    cycle daily dance danger daring dark dash data dawn deal debate debris decade decimal deck deep
    deer delta dense depot depth devil diary dice diesel diet differ digital dinner direct dirt disk
    dive dock doe dog dove dragon drawer dream dress drift drill drink drive drop drum dual
    duck dull dust eager eagle earth easel eight elbow elder electric elite empty enemy enjoy enter
    equal error event every exact exam exit expert eye fabric face factor fade fair fall false
    """.split()
)
if len(WORDLIST) != 256 or len(set(WORDLIST)) != 256:
    raise RuntimeError("recovery wordlist must contain exactly 256 unique words")

_WORD_INDEX = {word: index for index, word in enumerate(WORDLIST)}

WORD_BITS = 8
CHECKSUM_BITS = 8
WORD_COUNT = 24
ENTROPY_BYTES = WORD_COUNT - 1  # 23 data bytes + 1 checksum byte = 24 words
KEY_LEN = 32
SALT_LEN = 16
RECOVERY_MEMORY_KIB = 65_536
RECOVERY_ITERATIONS = 3
RECOVERY_LANES = 4


class RecoveryError(Exception):
    """A recovery phrase failed validation or derivation."""


def _checksum(entropy: bytes) -> int:
    return hashlib.sha256(entropy).digest()[0]


def encode_entropy(entropy: bytes) -> str:
    """Encode 23 entropy bytes plus an 8-bit SHA-256 checksum into 24 words."""
    if len(entropy) != ENTROPY_BYTES:
        raise RecoveryError(f"entropy must be exactly {ENTROPY_BYTES} bytes")
    value = (int.from_bytes(entropy, "big") << CHECKSUM_BITS) | _checksum(entropy)
    words = [
        WORDLIST[(value >> (WORD_BITS * (WORD_COUNT - 1 - i))) & 0xFF]
        for i in range(WORD_COUNT)
    ]
    return " ".join(words)


def decode_phrase(mnemonic: str) -> bytes:
    """Validate a 24-word phrase and return its entropy bytes."""
    if not isinstance(mnemonic, str):
        raise RecoveryError("mnemonic must be a string")
    tokens = mnemonic.split()
    if len(tokens) != WORD_COUNT:
        raise RecoveryError(f"mnemonic must contain exactly {WORD_COUNT} words")
    value = 0
    for token in tokens:
        try:
            index = _WORD_INDEX[token.lower()]
        except KeyError as exc:
            raise RecoveryError(f"unknown recovery word: {token}") from exc
        value = (value << WORD_BITS) | index
    checksum = value & 0xFF
    entropy = (value >> CHECKSUM_BITS).to_bytes(ENTROPY_BYTES, "big")
    if checksum != _checksum(entropy):
        raise RecoveryError("recovery phrase checksum mismatch")
    return entropy


def generate_recovery_phrase() -> str:
    """Generate a new 24-word phrase from CSPRNG entropy."""
    return encode_entropy(os.urandom(ENTROPY_BYTES))


def mnemonic_to_key(mnemonic: str, salt: bytes) -> bytes:
    """Derive a 256-bit vault key from a validated phrase via Argon2id."""
    if not isinstance(salt, (bytes, bytearray)):
        raise TypeError("salt must be bytes")
    salt_bytes = bytes(salt)
    if not SALT_LEN <= len(salt_bytes) <= 64:
        raise RecoveryError(f"salt must be {SALT_LEN}-64 bytes")
    entropy = decode_phrase(mnemonic)
    kdf = Argon2id(
        salt=salt_bytes,
        length=KEY_LEN,
        iterations=RECOVERY_ITERATIONS,
        lanes=RECOVERY_LANES,
        memory_cost=RECOVERY_MEMORY_KIB,
    )
    return kdf.derive(entropy)
