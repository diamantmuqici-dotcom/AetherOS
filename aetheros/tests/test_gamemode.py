"""GAMEMODE PID scoping + guaranteed restore assertions.

Run with:  python -m unittest discover -s aetheros/tests -p 'test_gamemode.py' -v
"""
from __future__ import annotations

import pathlib
import re
import shutil
import subprocess
import unittest

AETHEROS = pathlib.Path(__file__).resolve().parents[1]
CHROOT = AETHEROS / "iso" / "config" / "includes.chroot"
SCRIPT = AETHEROS / "scripts" / "gamemode-hook.sh"
MIRRORS = (
    SCRIPT,
    CHROOT / "usr" / "share" / "aether" / "scripts" / "gamemode-hook.sh",
    CHROOT / "usr" / "local" / "bin" / "gamemode-hook",
)
SCHEMA = "AETHER_GAMEMODE_STATE_V1"
PRESETS = ("performance", "balanced", "quiet")


# --- pure logic mirrors of the shell policy ---------------------------------
def valid_pid(token: str) -> bool:
    """Integer PID strictly greater than 1."""
    if not re.fullmatch(r"[0-9]+", token.strip()):
        return False
    return int(token) > 1


def parse_explicit_pids(raw: str, cap: int = 64) -> list[int]:
    """Scope --pids: valid ints, de-duplicated, order preserved, capped."""
    out: list[int] = []
    for token in raw.split(","):
        if not valid_pid(token):
            continue
        pid = int(token)
        if pid not in out:
            out.append(pid)
        if len(out) >= cap:
            break
    return out


def preset_flags(preset: str) -> tuple[bool, bool, bool]:
    """(change_profile, boost_nice, hide_banners) for a known preset."""
    return {
        "performance": (True, True, True),
        "balanced": (False, True, False),
        "quiet": (False, False, True),
    }[preset]


def state_valid(lines: list[str]) -> bool:
    """Schema marker, numeric timestamp and required keys."""
    if not lines or lines[0].strip() != SCHEMA:
        return False
    keys: dict[str, str] = {}
    for line in lines:
        if "=" in line:
            key, value = line.split("=", 1)
            keys[key] = value
    if not re.fullmatch(r"[0-9]+", keys.get("ts", "")):
        return False
    return all(k in keys for k in ("preset", "profile", "banners"))


class StaticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = SCRIPT.read_text(encoding="utf-8")
        cls.lower = cls.text.lower()

    def test_all_copies_exist(self) -> None:
        for path in MIRRORS:
            with self.subTest(path=path):
                self.assertTrue(path.is_file(), f"missing hook: {path}")

    def test_mirrors_byte_identical(self) -> None:
        blobs = [p.read_bytes() for p in MIRRORS]
        for blob in blobs[1:]:
            self.assertEqual(blob, blobs[0], "hook mirrors diverged")

    def test_trap_backed_restore(self) -> None:
        self.assertIn("trap cleanup EXIT INT TERM", self.text)
        for sig in ("EXIT", "INT", "TERM"):
            self.assertIn(sig, self.text)
        self.assertIn("cleanup()", self.text)
        self.assertIn("restore_from_state", self.text)
        self.assertIn("rm -f \"$STATE\"", self.text)

    def test_no_destructive_or_dynamic_exec(self) -> None:
        for banned in ("shell=true", "pkill", "kill -9", "killall"):
            self.assertNotIn(banned, self.lower)
        self.assertNotRegex(self.text, r"\beval\b")
        self.assertNotIn("pgrep -f", self.text)

    def test_pid_validation_and_allowlist(self) -> None:
        self.assertIn(r"^[0-9]+$", self.text)
        self.assertIn("ALLOWLIST=", self.text)
        self.assertIn("DENYLIST=", self.text)
        self.assertIn("/proc/$pid/comm", self.text)
        self.assertIn("readlink \"/proc/$pid/exe\"", self.text)
        self.assertIn("pgrep -x", self.text)

    def test_preset_set_and_explicit_pids(self) -> None:
        for preset in PRESETS:
            self.assertIn(preset, self.text)
        self.assertIn("performance|balanced|quiet", self.text)
        self.assertIn("--pids", self.text)
        self.assertIn("XDG_RUNTIME_DIR", self.text)
        self.assertIn("/gamemode", self.text)

    def test_bounded_cap(self) -> None:
        self.assertIn("MAX_PIDS=64", self.text)
        self.assertIn('"${#PIDS[@]}" -lt "$MAX_PIDS"', self.text)

    def test_state_schema(self) -> None:
        self.assertIn(SCHEMA, self.text)
        for field in ("ts=", "preset=", "profile=", "banners="):
            self.assertIn(field, self.text)
        self.assertIn("state_valid", self.text)
        self.assertIn("mv -f \"$TMP_STATE\" \"$STATE\"", self.text)

    def test_sudo_only_for_negative_renice(self) -> None:
        self.assertIn("sudo -n renice", self.text)
        self.assertIn("NICE_LEVEL=-5", self.text)
        self.assertIn("renice -n 0", self.text)

    def test_idempotent_start_and_scoped_paths(self) -> None:
        self.assertIn('if state_valid "$STATE"; then', self.text)
        self.assertIn('mkdir -p "$CONFIG_DIR"', self.text)
        self.assertIn('CONFIG_DIR="${HOME}/.config/aether/gamemode"', self.text)
        self.assertIn("run_bounded", self.text)


class LogicTests(unittest.TestCase):
    def test_valid_pid(self) -> None:
        self.assertTrue(valid_pid("123"))
        self.assertFalse(valid_pid("0"))
        self.assertFalse(valid_pid("-5"))
        self.assertFalse(valid_pid("12a"))
        self.assertFalse(valid_pid(""))

    def test_parse_explicit_pids(self) -> None:
        self.assertEqual(parse_explicit_pids("123,456"), [123, 456])
        self.assertEqual(parse_explicit_pids("123,abc,456,123,0,-1,7"), [123, 456, 7])

    def test_pid_cap(self) -> None:
        raw = ",".join(str(i) for i in range(2, 200))
        self.assertEqual(len(parse_explicit_pids(raw)), 64)

    def test_preset_flags(self) -> None:
        self.assertEqual(preset_flags("performance"), (True, True, True))
        self.assertEqual(preset_flags("balanced"), (False, True, False))
        self.assertEqual(preset_flags("quiet"), (False, False, True))
        with self.assertRaises(KeyError):
            preset_flags("unknown")

    def test_state_schema_validation(self) -> None:
        good = [SCHEMA, "ts=1700000000", "preset=performance",
                "profile=balanced", "banners=true"]
        self.assertTrue(state_valid(good))
        self.assertFalse(state_valid(good[1:]))
        self.assertFalse(state_valid([SCHEMA, "ts=abc"] + good[2:]))
        self.assertFalse(state_valid([line for line in good if not line.startswith("banners")]))


class SyntaxTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("bash"), "bash not available")
    def test_bash_syntax(self) -> None:
        for path in MIRRORS:
            with self.subTest(path=path):
                result = subprocess.run(
                    ["bash", "-n", str(path)],
                    capture_output=True, text=True, timeout=15,
                )
                self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
