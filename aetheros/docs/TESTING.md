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
- `missing_check_keys(raw)` returns the check keys absent from a result JSON.
  The completeness tests require all six keys on pass, fail and early-exit
  results, and name every key when `checks` is missing or not an object.
- `normalize_timeout(value)` mirrors the script: decimal integers clamp to
  `30..900`, anything else falls back to `180`. Tests cover both bounds, the
  default, leading zeroes and malformed values.
- `parse_os_release(text)` and `os_release_has_aether_identity(text)` parse
  shell-style `KEY=VALUE` content and require both `NAME=AetherOS` and
  `VERSION_CODENAME=trixie`. Tests cover quoted values, wrong codename,
  missing fields, comments and single quotes.

Script-mode tests (need `bash` on `PATH`, but never QEMU or an ISO):

- `bash test-iso.sh --self-test` exits `0` and prints all assertions plus a
  `selftest N assertions, 0 failures` summary.
- `--self-test` still exits `0` with an out-of-range `--timeout`.
- A missing ISO with `--timeout 5` exits `1`, writes result JSON whose
  `timeout_seconds` is clamped to `30`, and whose `checks` map is complete.

Integration tests (skipped unless `qemu-system-x86_64` is on `PATH` and
`AETHER_ISO` points at a built image):

- the ISO path exists and is non-empty;
- `aetheros/scripts/test-iso.sh` exists and is readable or executable;
- one bounded, argv-only run (`--timeout 30`, 90 s process cap) writes result
  JSON whose status and exit code agree with the process result and whose
  `checks` map is complete.

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
| `boot_prompt` | serial log or optional QMP capture reaches an `AetherOS`/GDM/login milestone before the deadline |
| `kernel_cmdline` | `quiet splash` appears in the serial log, the ISO boot config or the optional QMP capture |
| `plymouth_theme` | the Aether Plymouth theme is in the initramfs (best effort via `lsinitrd`) |
| `iso_payload` | Aether payload markers exist in the ISO listing/boot config (`isoinfo`, `7z`, `bsdtar`) |
| `os_release` | `/etc/os-release` in the payload contains `NAME=AetherOS` and `VERSION_CODENAME=trixie` |
| `screenshot` | a QEMU `screendump` framebuffer, when a display backend is enabled |

Evidence for `boot_prompt` and `kernel_cmdline` is drawn from the serial log,
the boot config extracted from the ISO, and (when `AETHER_TEST_QMP_LOG` points
at a readable capture) QMP/monitor text. The pure matchers are shared by the
real run and `--self-test`.

Two checklist items are soft: if `lsinitrd` is missing (or no initrd can be
extracted), `plymouth_theme` is recorded as `skip` with a note; if none of
`isoinfo`/`7z`/`bsdtar` is installed, `iso_payload` is recorded as `skip` with
a note. `os_release` is also a skip when no ISO reader is installed, or when
`/etc/os-release` cannot be read from the ISO payload (on a live image it sits
inside `live/filesystem.squashfs`; `unsquashfs`, when present, is used as a deep
fallback). Soft skips do not fail the run.

With the default display settings there is no QEMU monitor to drive
`screendump`, so `screenshot` is recorded as `skip` and the serial log is the
boot artifact. Set `AETHER_TEST_SCREENDUMP=1` to enable an HMP monitor socket
and attempt a framebuffer capture (requires `socat` or `nc`); if no framebuffer
is produced the serial log remains the artifact.

### CI (`.github/workflows/ci.yml`)

Both jobs run on `ubuntu-24.04` with pinned actions (`actions/checkout@v4`,
`actions/setup-python@v5`, `actions/upload-artifact@v4`).

`static-checks` (20 min) runs, in order:

1. `python -m compileall -q aetheros`
2. `python -m pip install --quiet cryptography PyYAML`
3. `python -m unittest discover -s aetheros/tests -p 'test_*.py' -v` — strict,
   no `|| true`
4. shellcheck: install via `apt-get` on a best-effort basis, then
   `shellcheck aetheros/scripts/test-iso.sh || true` — the only tolerated
   `|| true` in the pipeline; an unavailable shellcheck prints a note
5. `bash aetheros/scripts/test-iso.sh --self-test` — strict, no VM required
6. a Python heredoc that `json.load`s the three pinned JSON files plus every
   `usr/share/**/*.json`, and `ET.parse`s every `iso/config/**/*.xml`
7. a Bash loop that resolves each `.desktop` `Exec=` command against
   `usr/local/bin` or a known system tool

`iso-boot-test` (45 min) runs, in order:

1. `sudo apt-get update` and
   `sudo apt-get install -y qemu-system-x86_64 ovmf genisoimage`
2. a `docker run --rm --privileged` `debian:trixie-slim` `live-build` image
   build with a 35 min step cap, producing `AetherOS-live-amd64.iso` and a
   `*.iso.sha256`
3. `bash aetheros/scripts/test-iso.sh "$ISO" --timeout 180` with
   `AETHER_TEST_LOG`, `AETHER_TEST_SCREENSHOT` and `AETHER_TEST_RESULT` set —
   strict, no `|| true`
4. a skip guard reading `status` and `exit_code` from the result JSON with
   `python3`; it fails the job when status is `skip`, `exit_code` is `77`, or
   the result JSON is missing, so a missing VM cannot silently pass
5. `actions/upload-artifact@v4` uploads `aether-iso-serial.log`,
   `aether-iso-screenshot.ppm` and `aether-iso-result.json` as
   `aetheros-iso-boot-artifacts`, plus a second upload of
   `aether-iso-result.json` as `aetheros-iso-result`; both use `if: always()`

## Run locally

From the repository root:

```bash
# Pure unit tests (no QEMU, no ISO) - these always run.
python -m unittest discover -s aetheros/tests -p 'test_iso.py' -v

# Validate the boot-check logic without a VM (needs bash only).
bash aetheros/scripts/test-iso.sh --self-test

# Vault tests (needs cryptography).
python -m pip install cryptography
python -m unittest discover -s aetheros/tests -p 'test_secure_vault.py' -v

# Full ISO boot test (needs QEMU and a built image).
sudo apt-get install -y qemu-system-x86_64 ovmf isomd5sum
bash aetheros/scripts/test-iso.sh ./aetheros/iso/AetherOS-live-amd64.iso \
  --timeout 180
```

The env form is also accepted:

```bash
AETHER_ISO=./aetheros/iso/AetherOS-live-amd64.iso \
AETHER_TEST_TIMEOUT=180 \
AETHER_TEST_LOG=./serial.log \
AETHER_TEST_RESULT=./result.json \
bash aetheros/scripts/test-iso.sh
```

### Script options

| Option | Meaning |
|---|---|
| `--timeout <s>` | boot-wait deadline; integers clamp to `30..900`, malformed values use `180` (overrides `AETHER_TEST_TIMEOUT`) |
| `--self-test` | run the pure matchers and JSON/checks invariants against bundled samples, then exit; no QEMU, no ISO, no result JSON |
| `-h`, `--help` | print usage and exit `0` |
| first positional arg | ISO path; wins over `AETHER_ISO` |

### Script environment

| Variable | Meaning | Default |
|---|---|---|
| `AETHER_ISO` | ISO path fallback (positional argument wins) | none (required unless `--self-test`) |
| `AETHER_TEST_TIMEOUT` | boot-wait deadline fallback, still clamped to `30..900` | `180` |
| `AETHER_TEST_LOG` | serial log output path | `aether-iso-serial.log` |
| `AETHER_TEST_SCREENSHOT` | screenshot output path | `aether-iso-screenshot.ppm` |
| `AETHER_TEST_RESULT` | result JSON path (written only if set) | unset |
| `AETHER_TEST_SCREENDUMP` | set to `1` to enable `screendump` capture | `0` |
| `AETHER_TEST_QMP_LOG` | readable QMP/monitor capture folded into the boot/cmdline checks | unset |

### Result JSON invariant

`AETHER_TEST_RESULT` is always well-formed and always contains a `checks`
object with every key: `boot_prompt`, `kernel_cmdline`, `plymouth_theme`,
`iso_payload`, `os_release`, `screenshot`. On input validation failure, whole
test skip, or any other early exit, the checks that never ran are recorded as
`skip` and the reason goes into `notes`. Field `timeout_seconds` is the clamped
value actually used.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | every hard check passed (soft-check skips are allowed and noted) |
| `1` | a hard check failed, or input paths failed validation |
| `77` | whole test skipped because `qemu-system-x86_64` is not installed |

Result JSON records per-check `pass`/`fail`/`skip` and a `notes` array; `77`
means the harness did not boot at all, while a per-check `skip` means that
single check lacked tooling and is reported in the notes.

`77` is a skip only at the script level. In CI the `iso-boot-test` job has an
explicit guard that fails the job on `exit_code: 77` / `status: skip` (or a
missing result JSON), so a runner without QEMU cannot make the job pass.

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
