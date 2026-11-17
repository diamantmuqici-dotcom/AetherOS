# Aether Vault

## Status

The storage core (`aetheros/core/vault/secure_vault.py`) is implemented and tested.
The GTK interface launches on Debian but was not exercised in the audit environment.
This document describes the implemented format, not planned features.

## Container format (version 2)

| Field | Size | Meaning |
|---|---|---|
| magic | 12 bytes | `AETHERVAULT2` |
| version | 1 byte | 2 |
| reserved | 1 byte | 0 |
| memory_cost | 4 bytes LE | Argon2id memory, KiB |
| iterations | 4 bytes LE | Argon2id passes |
| parallelism | 4 bytes LE | Argon2id lanes |
| salt_len | 2 bytes LE | 16–64 |
| nonce_len | 2 bytes LE | 12 |
| ct_len | 8 bytes LE | ciphertext length incl. tag |
| salt | salt_len | random per write |
| nonce | 12 | random per write |
| ciphertext | ct_len | ChaCha20-Poly1305, 16-byte tag |

Key = Argon2id(master password, salt, stored parameters), 256-bit output.
The entire header including salt and nonce is AEAD associated data. There is no
nonce reuse: a new salt and nonce are generated on every save, and no nonce is
derived from data, counters, or the password.

## Guarantees

- Authentication is checked before any plaintext is returned.
- A new container is decrypted and compared with the intended payload before it
  replaces the old file. Writes use temp file → `fsync` → `os.replace` → directory
  `fsync` (POSIX).
- The previous container is written to `vault.enc.bak` before each save.
- `change-password` re-encrypts under a new master key and keeps a backup.
- v1 migration uses the legacy KDF, verifies the new container on disk, and
  renames the original to `vault.enc.v1` rather than deleting it.

## Limitations

- An application lock is not operating-system account security. A process running
  as the unlocked user can read memory and the container path.
- Encrypted data is only as recoverable as the master password and an intact
  backup. There is no magic recovery path that works without the key.
- Attacker-controlled changes to `.bak` are not signed; backup integrity depends
  on the same master password and AEAD tag.
- Secure deletion on SSD/journaled filesystems is not guaranteed.
- Argon2id defaults (64 MiB, 3, 4) require benchmarking on target hardware.

## Commands

```
aether-vault create
aether-vault unlock
aether-vault add --site example.org --user alice --secret '...'
aether-vault list
aether-vault save
aether-vault change-password
aether-vault migrate --from-file ~/.config/aether/vault.enc
```

## Tests

```
cd Aether
python -m unittest discover -s aetheros/tests -p 'test_secure_vault.py' -v
```

Result at time of writing: 15 tests, 0 failures (Windows/Python 3.12.10,
cryptography 50.0.2). Directory fsync executes only on POSIX.
