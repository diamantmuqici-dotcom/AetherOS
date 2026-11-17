#!/usr/bin/env python3
"""Aether Mail — private mail launcher over the preinstalled mail engine."""
from __future__ import annotations

import shutil
import subprocess
import sys

ENGINES = ("thunderbird", "geary")


def main(argv: list[str]) -> int:
    for name in ENGINES:
        executable = shutil.which(name)
        if executable:
            try:
                return subprocess.call([executable, *argv[1:]])
            except OSError as exc:
                print(f"Aether Mail failed to start: {exc}", file=sys.stderr)
                return 1

    print(
        "Aether Mail engine is not installed. Run 'aether-fix' to repair it.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
