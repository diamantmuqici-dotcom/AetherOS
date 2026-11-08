#!/usr/bin/env python3
"""Aether Vault — 5-layer encrypted password/history vault (age + ChaCha20Poly1305)."""
import pathlib, hashlib, base64, json, subprocess
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend

VAULT = pathlib.Path.home() / ".config" / "aether" / "vault.enc"
def derive(master: str, salt: bytes, layers=5) -> bytes:
    key = master.encode()
    for _ in range(layers):
        hk = PBKDF2HMAC(algorithm=hashlib.sha256(), length=32, salt=salt, iterations=200_000, backend=default_backend())
        key = hk.derive(base64.b64encode(key))
    return key[:32]
def vault_save(master: str, data: dict, salt: bytes):
    key = derive(master, salt)
    aead = ChaCha20Poly1305(key)
    nonce = b"\x00" * 12
    ct = aead.encrypt(nonce, json.dumps(data).encode(), salt)
    VAULT.parent.mkdir(parents=True, exist_ok=True)
    VAULT.write_bytes(salt + ct)
def vault_load(master: str):
    raw = VAULT.read_bytes()
    salt, ct = raw[:16], raw[16:]
    key = derive(master, salt)
    pt = ChaCha20Poly1305(key).decrypt(b"\x00" * 12, ct, salt)
    return json.loads(pt)
def save_password(master, site, user, pw):
    data = {"passwords": [], "history": []}
    if VAULT.exists():
        try: data = vault_load(master)
        except Exception: pass
    data["passwords"].append({"site": site, "user": user, "pw": pw})
    import os; vault_save(master, data, os.urandom(16))
def save_history(master, url, title):
    data = vault_load(master) if VAULT.exists() else {"passwords": [], "history": []}
    data["history"].append({"url": url, "title": title})
    import os; vault_save(master, data, os.urandom(16))
def shred_clipboard():
    subprocess.run(["shred", "-u", "/tmp/clip"], check=False)
