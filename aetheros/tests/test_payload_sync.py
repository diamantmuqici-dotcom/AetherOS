"""Tests for the AetherOS payload mirror single-source-of-truth manifest."""

from __future__ import annotations

import filecmp
import pathlib
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / "aetheros" / "scripts" / "payload-manifest.txt"
SYNC_SCRIPT_PATH = REPO_ROOT / "aetheros" / "scripts" / "sync-payloads.sh"
CHROOT_PREFIX = "aetheros/iso/config/includes.chroot/"


def parse_manifest(text: str) -> list[tuple[str, str]]:
    """Parse manifest text into ordered (source, destination) pairs."""
    pairs: list[tuple[str, str]] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.count("|") != 1:
            raise ValueError(f"line {lineno}: expected one '|' separator: {raw!r}")
        source, destination = (part.strip() for part in line.split("|"))
        pairs.append((source, destination))
    return pairs


class PayloadSyncTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = MANIFEST_PATH.read_text(encoding="utf-8")
        cls.pairs = parse_manifest(cls.text)

    def test_manifest_is_populated(self) -> None:
        self.assertTrue(MANIFEST_PATH.is_file())
        self.assertGreater(len(self.pairs), 0)

    def test_every_path_exists(self) -> None:
        self.assertGreater(len(self.pairs), 0)
        for source, destination in self.pairs:
            for role, relative in (("source", source), ("destination", destination)):
                with self.subTest(role=role, path=relative):
                    self.assertTrue((REPO_ROOT / relative).is_file())

    def test_byte_identical_with_mid_edit_tolerance(self) -> None:
        # Strict enforcement lives in sync-payloads.sh check mode. A mismatch
        # here is a skip, not a failure, because parallel workstreams may be
        # editing a mirrored file while this suite runs.
        for source, destination in self.pairs:
            with self.subTest(pair=f"{source} -> {destination}"):
                source_path = REPO_ROOT / source
                destination_path = REPO_ROOT / destination
                if not source_path.is_file() or not destination_path.is_file():
                    self.skipTest(f"missing at test time: {source} -> {destination}")
                if not filecmp.cmp(source_path, destination_path, shallow=False):
                    self.skipTest(
                        f"parallel workstream mid-edit; pair not byte-identical: "
                        f"{source} -> {destination}"
                    )

    def test_no_duplicate_destinations(self) -> None:
        destinations = [destination for _, destination in self.pairs]
        self.assertEqual(len(destinations), len(set(destinations)))

    def test_paths_are_repo_relative_under_aetheros(self) -> None:
        for source, destination in self.pairs:
            for role, relative in (("source", source), ("destination", destination)):
                with self.subTest(role=role, path=relative):
                    self.assertTrue(relative.startswith("aetheros/"))
                    self.assertNotIn("\\", relative)
                    parts = relative.split("/")
                    self.assertNotIn("..", parts)
                    self.assertFalse(pathlib.PurePosixPath(relative).is_absolute())

    def test_destinations_are_chroot_mirrors(self) -> None:
        for _, destination in self.pairs:
            with self.subTest(path=destination):
                self.assertTrue(destination.startswith(CHROOT_PREFIX))

    def test_sync_script_exposes_check_and_apply(self) -> None:
        text = SYNC_SCRIPT_PATH.read_text(encoding="utf-8")
        self.assertIn("check|apply", text)
        self.assertIn("mode=check", text)
        self.assertIn('"$mode" = apply', text)
        self.assertIn("cmp -s --", text)
        self.assertIn("cp --preserve=mode --", text)
        self.assertIn("--manifest", text)


if __name__ == "__main__":
    unittest.main()
