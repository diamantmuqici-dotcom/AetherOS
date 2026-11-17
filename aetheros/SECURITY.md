# AetherOS Security Audit — Phase 1

Audit date: 2026-11-17
Branch: `hardening/aetheros-phase-1`
Scope: `Aether/aetheros` repository + build workflows. Findings are based on direct
source review of the files named below. A fix marked VERIFIED was executed in this
workspace; a fix marked OPEN is identified but not yet implemented.

## Severity summary

| Severity | Finding | Affected file(s) | Status |
|---|---|---|---|
| Critical | ChaCha20-Poly1305 nonce fixed to 12 zero bytes for every write (nonce reuse destroys AEAD confidentiality/integrity) | `apps/vault/aether-vault.py`, `iso/.../aether-vault.py` | FIXED — VERIFIED |
| Critical | PBKDF2 chained five times over base64 of prior key; nonstandard, unaudited KDF | `apps/vault/aether-vault.py` | FIXED — VERIFIED |
| Critical | Vault overwrite had no integrity check; corrupted or wrong-password writes could destroy data | `apps/vault/aether-vault.py` | FIXED — VERIFIED |
| Critical | Update path executes a shell script from disk with no signature or integrity verification; metadata fetched from GitHub with no verification | `apps/updater/aether-updater.py`, `scripts/update-push.py`, `scripts/auto-update.sh` | OPEN |
| Critical | ISO built from Debian Bookworm despite Trixie requirement | `.github/workflows/build-iso.yml`, nested workflow, package list, docs | FIXED — config only; ISO NOT rebuilt |
| High | Aether Mail is five buttons that call `notify-send`; no IMAP, SMTP, OAuth2, PGP, or storage | `apps/mail/aether-mail.py` | OPEN |
| High | Browser app only prints a Chromium flag list; no browser is launched | `apps/browser/aether-browser.py` | OPEN |
| High | `shell=True` with interpolated paths in destructive commands (`rm -rf ~/{d}/*`, `pkill -9 ...; rm -rf ...`) | `apps/factory-reset/aether-factory-reset.py`, `apps/antivirus/tamperguard.py` | OPEN |
| High | Antivirus pulls JSON from a GitHub release and acts on it without signature verification | `apps/antivirus/aether-av.py` | OPEN |
| Medium | Legacy vault swallowed decryption errors and continued with an empty payload | `apps/vault/aether-vault.py` (`save_password`) | FIXED — VERIFIED |
| Medium | AetherOS identity declared Trixie while build pipeline produced Bookworm | `iso/.../os-release.override` vs workflows | FIXED — config only |
| Medium | GameMode hook uses `sudo nice` on `pgrep -f` matches (broad pattern, can hit unrelated processes) | `scripts/gamemode-hook.sh`, `optimize-*.sh` | OPEN |
| Medium | Secrets handling, privilege boundaries, and service hardening not yet audited end-to-end | systemd units in `iso/config/includes.chroot/etc/systemd/system/` | OPEN |
| Low | Historical build logs still contain Bookworm strings | `iso/lb-config.log`, `iso/lb-build.log` | Intentional — historical records, not build config |

## Phase 1 remediation — Vault

Replaced the entire crypto path with `aetheros/core/vault/secure_vault.py`:

- Argon2id (64 MiB / 3 iterations / 4 lanes baseline), 256-bit random salt per write.
- ChaCha20-Poly1305 with a fresh 96-bit CSPRNG nonce per encryption. The header
  (version, KDF parameters, salt, nonce) is authenticated as AEAD associated data,
  so parameter downgrade and header tampering fail authentication.
- Plaintext is released only after tag verification; wrong password and corrupted
  files raise distinct errors.
- Atomic writes: temp file + `fsync` + `os.replace` + directory `fsync` on POSIX.
  A new container is decrypted and compared with the intended payload **before**
  it replaces the current one. The previous container is copied to `.bak`.
- Migration from the v1 format uses the exact legacy KDF, writes v2 atomically,
  verifies the on-disk result, and renames the original to `.v1` instead of
  deleting it. Failure at any step leaves both files intact.

The GUI app now imports this core and implements no cryptography of its own.

### Verification

`python -m unittest discover -s aetheros/tests -p 'test_secure_vault.py' -v`
result: **15 tests, 0 failures**, covering round-trip, nonce uniqueness, wrong
password, ciphertext corruption, KDF-parameter tampering, truncation, unknown
version, backup contents, interrupted `os.replace`, password change, lock state,
backup restore, and legacy migration (success and wrong-password failure).

Limitations: tests ran on Windows/Python 3.12/cryptography 50.0.2. Directory
`fsync` is skipped on Windows and active on the AetherOS target. GTK UI was not
launched here. Argon2id parameters require benchmarking on target hardware.

## Remaining work

See `IMPLEMENTATION_PLAN.md`. Items listed OPEN above are not fixed by this commit.
No ISO was built or booted in this environment; no claim of a verified OS build is
made here.
