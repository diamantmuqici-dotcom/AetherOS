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
| Critical | Update path executes a shell script from disk with no signature or integrity verification; metadata fetched from GitHub with no verification | `apps/updater/aether-updater.py`, `core/update/`, `scripts/signing/sign-iso.sh` | FIXED — VERIFIED: Ed25519 manifest verification before any field is read; updater refuses apply unless signature VALID; 13 tests |
| Critical | ISO built from Debian Bookworm despite Trixie requirement | `.github/workflows/build-iso.yml`, nested workflow, package list, docs | FIXED — config only; ISO NOT rebuilt |
| High | Aether Mail is five buttons that call `notify-send`; no IMAP, SMTP, OAuth2, PGP, or storage | `apps/mail/aether-mail.py`, `core/mail/` | FIXED — VERIFIED: real IMAP/SMTP/PGP/sanitizer/Mail Lock; 19 tests. Live server untested |
| High | Browser app only prints a Chromium flag list; no browser is launched | `apps/browser/aether-browser.py`, Chromium managed policy, MV3 filter | FIXED — VERIFIED: real engine launch, policy enforced by Chromium, profile isolation, `--diagnose` |
| High | `shell=True` with interpolated paths in destructive commands (`rm -rf ~/{d}/*`, `pkill -9 ...; rm -rf ...`) | `apps/factory-reset/aether-factory-reset.py` | FIXED — VERIFIED: argv subprocesses + target allow/deny lists; 9 hardening tests |
| High | Antivirus pulled JSON from a GitHub release and acted on it without signature verification | `apps/antivirus/aether-av.py`, `aether-av-light.py`, launcher, desktop entry | FIXED — VERIFIED: Ed25519 verify before schema/expiry/hash interpretation; fail closed `SIGNATURE_MISSING`/`INVALID`; copy-before-delete quarantine verified by sha256; HTTPS-only/10s/1 MiB caps; 23 tests |
| Medium | Legacy vault swallowed decryption errors and continued with an empty payload | `apps/vault/aether-vault.py` (`save_password`) | FIXED — VERIFIED |
| Medium | AetherOS identity declared Trixie while build pipeline produced Bookworm | `iso/.../os-release.override` vs workflows | FIXED — config only |
| Medium | GameMode hook used `sudo nice` on `pgrep -f` matches (broad pattern, can hit unrelated processes) | `scripts/gamemode-hook.sh` + mirrors | FIXED — VERIFIED: PID-scoped (`--pids`/runtime dir/exact-name allowlist), `/proc` comm+exe verified, cap 64, no kill, `trap EXIT INT TERM` guaranteed restore with schema-checked snapshot; 16 tests, three copies byte-identical |
| Medium | Update path performed unverified GitHub release check and admitted unpinned apt packages | `scripts/update-push.py`, `core/update/apt_policy.py` | FIXED — VERIFIED: signature-verified manifest pins only; unpinned/mismatched plan denied whole; argv-only plan output, executes nothing; 23 tests |
| Medium | Backup used `rsync -a --delete` (destructive) and had no integrity verification | `apps/backup/aether-backup.py`, `core/backup/` | FIXED — VERIFIED: canonical sha256 manifest, no `--delete`, dry-run default, hash-verified non-destructive restore, source/target path-containment guards; 16 tests |
| Medium | Vault copied password/recovery phrase to clipboard with indefinite retention | `apps/vault/aether-vault.py`, `core/vault/clipboard.py` | FIXED — VERIFIED: 30s auto-clear timer, hash-only fingerprints in state, no plaintext at rest, deferred gi; 12 tests |
| Low | GTK Settings module evaluated `Adw.Application` base at import while `Adw=None`, crashing headless import | `settings/aether-settings.py` + mirror | FIXED — VERIFIED: class built in `make_settings_class()` after gi bound; module imports headless, py_compile clean |
| Medium | Secrets handling, privilege boundaries, and service hardening not yet audited end-to-end | systemd units, AppArmor profiles, `core/mail/credentials.py` | FIXED — VERIFIED: five services sandboxed, two AppArmor enforce profiles, SecretService-first credential store; 9 hardening + 19 mail tests |
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

## Full verification (integration pass 2 — all ten follow-up workstreams)

`python -m unittest discover -s aetheros/tests -p 'test_*.py' -v` → **235 tests, OK
(20 skips)**. Base suites: vault 15, vault-extras 16, update-signature 13, mail 19,
hardening 9, iso 27. Pass 2 suites: apt-policy 23, AV 23, mail-extras 23 (+ mail
core 19), backup 16, gamemode 16, clipboard 12, release-metadata 12,
gtk-readiness 4 (+13 tolerant skips), payload-sync 7. `compileall` clean; CI YAML,
GNOME schema XML, Chromium policy JSON, MV3 extension JSON all parse. 68/68
source→chroot payload pairs byte-identical (`scripts/sync-payloads.sh check`);
25/25 desktop Exec targets resolve. No private keys/tokens in source — only a
documented key path and a test-fixture password.

Skips are environment gates, not failures: QEMU/ISO integration (no QEMU image),
`bash`-dependent shell-syntax checks (no bash on the default shell), and 13 GTK
apps whose structure is statically reported in `docs/GTK-AUDIT.md` while parallel
edits were in flight.

NOT verified in this environment: ISO build and boot, GNOME Shell extension load,
Plymouth render, GTK UI runtime, live IMAP/SMTP. `scripts/test-iso.sh --self-test`
validates boot-check logic without QEMU; `.github/workflows/ci.yml` runs the real
boot test on a Linux runner. `scripts/gtk-smoke.sh --all` validates headless modes;
`docs/GTK-AUDIT.md` enumerates the owed desktop checks.

## Remaining work

See `IMPLEMENTATION_PLAN.md`. No OPEN findings remain in the table above. The
release and AV public keys are intentionally not generated on this bench; place
`aether-release.pub.pem` and `aether-av.pub.pem` in the ISO staging dir before a
signed build. The ISO was not built or booted here; no claim of a verified OS
build is made here.
