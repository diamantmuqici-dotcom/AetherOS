#!/usr/bin/env python3
"""Aether Antivirus (light) — CLI-only front-end, no GTK and no network.

Verification, scanning and quarantine come from the sibling aether-av.py module
so both front-ends share one authenticated definition path.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import pathlib
import sys


def _load_core():
    candidate = pathlib.Path(__file__).resolve().with_name("aether-av.py")
    if not candidate.is_file():
        raise RuntimeError(f"missing AV core: {candidate}")
    spec = importlib.util.spec_from_file_location("aether_av_core", candidate)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load AV core: {candidate}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


CORE = _load_core()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aether-av-light")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="emit headless JSON status")
    group.add_argument("--scan", nargs="*", metavar="PATH", help="bounded scan of PATH(s)")
    group.add_argument("--verify-file", metavar="PATH", help="check one file against verified hashes")
    group.add_argument("--version", action="store_true", help="print version")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    if args.check:
        print(json.dumps(CORE.check(), sort_keys=True))
    elif args.scan is not None:
        print(json.dumps(CORE.scan(args.scan), sort_keys=True))
    elif args.verify_file:
        print(json.dumps(CORE.verify_file(args.verify_file), sort_keys=True))
    elif args.version:
        print(CORE.VERSION)
    return 0


if __name__ == "__main__":
    sys.exit(main())
