# Testing AetherOS

This page covers the automated checks that ship with the repository: Python unit
tests, static checks in CI, and the ISO boot smoke test. It records what each
check covers, how to run it locally, the exit codes, and what is deliberately
out of scope.

## Test inventory

### `aetheros/tests/test_iso.py`

Pure helpers (always run, no QEMU needed):

- `parse_qemu_serial(text)` extracts boot milestones from a captured serial
  log: the `AetherOS` banner, a GDM/login prompt, `quiet splash` in the kernel
  command line, and the command-line text itself. Unit tests cover each signal
  plus empty and non-splash logs.
- `parse_result_json(raw)` normalizes the JSON written by `test-iso.sh` so the
  status, exit code, per-check results and skip notes can be asserted. Tests
  use simulated pass and skip payloads and verify malformed JSON raises.

Integration tests (skipped unless `qemu-system-x86_64` is on `PATH` and
`AETHER_ISO` points at a built image):

- the ISO path exists and is non-empty;
- `aetheros/scripts/test-iso.sh` exists and is readable or executable;
- one bounded, argv-only run of the script writes result JSON whose status and
  exit code agree with the process result.

### `aetheros/tests/test_secure_vault.py`

Cryptographic and data-integrity tests for the vault core: AEAD round-trip,
unique nonces, wrong-password and tamper rejection, atomic replace, password
change, lock enforcement, backup/restore, and legacy v1 migration. Requires the
`cryptography` package.

### `aetheros/scripts/test-iso.sh`

The ISO boot smoke test. It boots the image in QEMU with 4096 MB RAM, 2 cores,
OVMF when available, `-display none -serial file:<log> -monitor none`, and
`-drive file=<iso>,media=cdrom,readonly=on`. It polls the serial log on a
bounded loop (default 180 s) for a boot banner or login prompt, then runs a
grep-based checklist:

| Check | What it asserts |
|---|---|
| `boot_prompt` | serial log reaches an `AetherOS`/GDM/login milestone before the deadline |
| `kernel_cmdline` | `quiet splash` appears in the serial log or the ISO boot config |
| `plymouth_theme` | the Aether Plymouth theme is in the initramfs (best effort via `lsinitrd`) |
| `iso_payload` | Aether payload markers exist in the ISO listing/boot config (`isoinfo`, `7z`, `bsdtar`) |
| `screenshot` | a QEMU `screendump` framebuffer, when a display backend is enabled |

Two checklist items are soft: if `lsinitrd` is missing (or no initrd can be
extracted), `plymouth_theme` is recorded as `skip` with a note; if none of
`isoinfo`/`7z`/`bsdtar` is installed, `iso_payload` is recorded as `skip` with
a note. Soft skips do not fail the run.

With the default display settings there is no QEMU monitor to drive
`screendump`, so `screenshot` is recorded as `skip` and the serial log is the
boot artifact. Set `AETHER_TEST_SCREENDUMP=1` to enable an HMP monitor socket
and attempt a framebuffer capture (requires `socat` or `nc`); if no framebuffer
is produced the serial log remains the artifact.

### CI (`.github/workflows/ci.yml`)

- `static-checks` (ubuntu-24.04, Python 3.11): byte-compiles `aetheros`, runs
  the ISO/vault unit tests, tolerates the update/mail discovers while those
  workstreams' dependencies are absent, validates JSON and XML metadata, and
  verifies every `.desktop` `Exec=` target resolves to a launcher in
  `usr/local/bin` or a known system tool.
- `iso-boot-test` (ubuntu-24.04): installs QEMU/OVMF, builds the live ISO with
  the same Docker `live-build` command used by `build-iso.yml`, runs
  `test-iso.sh` against the result, and uploads the serial log, screenshot and
  result JSON as artifacts. All steps have bounded timeouts.

## Run locally

From the repository root:

```bash
# Pure unit tests (no QEMU, no ISO) - these always run.
python -m unittest discover -s aetheros/tests -p 'test_iso.py' -v

# Vault tests (needs cryptography).
python -m pip install cryptography
python -m unittest discover -s aetheros/tests -p 'test_secure_vault.py' -v

# Full ISO boot test (needs QEMU and a built image).
sudo apt-get install -y qemu-system-x86_64 ovmf isomd5sum
AETHER_ISO=./aetheros/iso/AetherOS-live-amd64.iso \
AETHER_TEST_TIMEOUT=180 \
AETHER_TEST_LOG=./serial.log \
AETHER_TEST_RESULT=./result.json \
bash aetheros/scripts/test-iso.sh
```

The ISO can also be passed as the first argument instead of `AETHER_ISO`:

```bash
bash aetheros/scripts/test-iso.sh ./aetheros/iso/AetherOS-live-amd64.iso
```

### Script environment

| Variable | Meaning | Default |
|---|---|---|
| `AETHER_ISO` / `$1` | ISO path (argument wins) | none (required) |
| `AETHER_TEST_TIMEOUT` | boot-wait deadline in seconds | `180` |
| `AETHER_TEST_LOG` | serial log output path | `aether-iso-serial.log` |
| `AETHER_TEST_SCREENSHOT` | screenshot output path | `aether-iso-screenshot.ppm` |
| `AETHER_TEST_RESULT` | result JSON path (written only if set) | unset |
| `AETHER_TEST_SCREENDUMP` | set to `1` to enable `screendump` capture | `0` |

## Exit codes

| Code | Meaning |
|---|---|
| `0` | every hard check passed (soft-check skips are allowed and noted) |
| `1` | a hard check failed (missing ISO, no boot milestone, bad cmdline, missing theme/payload when the tooling to check is present) |
| `77` | whole test skipped because `qemu-system-x86_64` is not installed |

Result JSON records per-check `pass`/`fail`/`skip` and a `notes` array; `77`
means the harness did not boot at all, while a per-check `skip` means that
single check lacked tooling and is reported in the notes.

## What is NOT covered

- **GTK UI runtime**: app windows, theme rendering, and interactivity are not
  exercised. The test only reaches the boot/login milestone and inspects the
  image contents.
- **Real hardware boot**: QEMU with OVMF is an emulated UEFI environment. No
  physical machine, Secure Boot enrollment, or vendor firmware is tested.
- **Installer, first-boot wizard, updates and recovery flows**: these need a
  persistent installed system and are outside this smoke test.
- **Network-dependent behaviour**: online repositories, update servers, and
  VPN auto-connect are not validated.
