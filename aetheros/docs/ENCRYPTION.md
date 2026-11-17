# Aether Vault Encryption Upgrades

## Status

This document covers the keyfile second factor, recovery phrases, Argon2id
tuning, and the LUKS2 installer helper. The core format is unchanged
(`docs/VAULT.md`, version 2 container).

## Vault keyfile

A keyfile is a high-entropy file used as a second factor alongside the master
passphrase.

- `generate_keyfile(path, bits=256)` writes `bits / 8` CSPRNG bytes. Accepted
  sizes are 128, 192, 256, and 512 bits. Existing files are never replaced
  unless `force=True` is passed.
- Writes are atomic: a `0600` temp file in the target directory is written,
  fsynced, then moved over the destination with `os.replace`.
- `load_keyfile(path, max_bytes=4096)` requires an exact supported length and a
  regular file. It returns `(key, perms_ok)`; `perms_ok` is `False` when group
  or other permission bits are set. Callers surface that flag rather than
  silently accepting a world-readable key.
- `combine_passphrase_keyfile(passphrase, keyfile)` derives a 256-bit factor
  with HKDF-SHA256. The IKM is length-prefixed passphrase followed by
  length-prefixed key material, and the KDF uses a fixed domain-separated salt
  and info label. The result is deterministic and bound to both factors.

No keyfile bytes are stored in the vault container.

## Recovery phrase

`generate_recovery_phrase()` emits 24 words from a fixed in-module 256-word
list. Encoding uses 8-bit chunks: 23 bytes of CSPRNG entropy plus an 8-bit
SHA-256 checksum word give 192 bits, which map to 24 word indices.

`decode_phrase(mnemonic)` rejects wrong word counts, words outside the list,
and checksum mismatches with `RecoveryError`.

`mnemonic_to_key(mnemonic, salt)` validates the phrase first, then derives a
256-bit key with Argon2id at a fixed parameter set (64 MiB, 3 iterations, 4
lanes). The salt must be 16-64 bytes. No plaintext key or derived seed is
persisted; the phrase plus a stored salt are sufficient to regenerate it.

## Clipboard auto-clear

The GTK vault copies secrets (master password, record secrets, recovery
phrase) through `aetheros/core/vault/clipboard.py`, which wipes them on a timer.

- `arm_secret` puts the text on the board and claims a fresh owner token from
  `ClipboardTimer`. A new copy removes the pending GLib source and invalidates
  the old token, so a late callback from a previous copy cannot clear the new
  secret or be cleared by it.
- Timeout defaults to 30 seconds; `AETHER_CLIPBOARD_TIMEOUT` accepts whole
  seconds in 1..300 and invalid values fall back to the default.
- The timer uses injected monotonic time, so no wall-clock or GUI dependency is
  needed to verify before/at/after-deadline behaviour.
- Only a 128-bit SHA-256 prefix (`redact_fingerprint`) is available for state
  reporting. Plaintext is never persisted to a file or emitted to logs.
- `GtkBackend` writes to both CLIPBOARD and PRIMARY selections and defers its
  `gi` import until a method is called; `NullBackend` is the headless equivalent.

## Argon2id tuning

Run the tuner on the target machine before enrolling vaults:

```
aether-tune-vault            # installed launcher, 250 ms budget
aether-tune-vault 150        # custom per-attempt budget in ms
```

The launcher invokes `/usr/share/aether/vault/benchmark.py --json` under a
30-second timeout when `timeout` is available. The benchmark measures a fixed
ladder of memory costs (16-1024 MiB) and iteration counts (1-4), capped at 12
derivations, and selects the highest work factor whose measured time is within
the budget. The result is written atomically to
`~/.config/aether/vault-params.json` with `0600` permissions, and a one-line
recommendation is printed.

The in-repo equivalent is `scripts/aether-tune-vault.sh`. Parameters emitted by
the benchmark can be fed to `Argon2Params` in the vault core; container headers
record the parameters used for each write, so existing vaults remain readable
after retuning.

## LUKS2 installer option

`luks2-setup.sh` is an installer helper, not an auto-run hook. It formats a
target block device with LUKS2 and Argon2id:

```
AETHER_CONFIRM=LUKS luks2-setup /dev/nvme0n1p3
```

The device may also be supplied through `AETHER_DEVICE`. Both checks are
mandatory before any write: `AETHER_CONFIRM` must equal `LUKS`, and the target
path must exist and resolve to a block device. `cryptsetup luksFormat` is
called with `--type luks2 --pbkdf argon2id` and `--iter-time` taken from the
tuned `measured_ms` value in `vault-params.json` (clamped to 100-10000 ms).
Without tuned parameters, the iteration time defaults to 250 ms.

After formatting, the helper prints the recovery-key handling steps: store the
passphrase and recovery key on separate physical media, verify with
`cryptsetup luksOpen --test-passphrase`, add or replace keys with
`cryptsetup luksAddKey`, and back up the LUKS header with
`cryptsetup luksHeaderBackup`.

## Threat model

- Offline attacker with the container file: must break Argon2id for every
  guess; memory and iterations are set by the benchmark, and the salt is fresh
  per write. Keyfile factors add at least 128 bits of additional entropy.
- Attacker with the keyfile but not the passphrase: faces the master password
  search plus the KDF; the HKDF binding prevents substituting either factor
  independently.
- Attacker with the recovery phrase: can regenerate the derived key from the
  phrase and a known salt. The phrase is therefore equivalent to the vault key
  and must be stored with the same controls.
- Phrase tampering: the 8-bit checksum detects single-word corruption and
  arbitrary word substitution with probability 255/256; the KDF does not run
  on an invalid phrase.
- Header tampering: the vault AEAD authenticates KDF parameters, salt, and
  nonce, so downgrade attempts fail authentication.
- Clipboard exposure window: a copied secret is readable by other clients
  until the timer fires (30 seconds by default). Lowering
  `AETHER_CLIPBOARD_TIMEOUT` shortens that window. The timer is best-effort UI
  hygiene, not memory protection.
- Not covered: a process running as the unlocked user can read vault memory;
  SSD/journaled filesystems do not guarantee secure deletion; the recovery
  checksum is an integrity check, not an authentication tag against a
  determined attacker who can rewrite both phrase and salt.
