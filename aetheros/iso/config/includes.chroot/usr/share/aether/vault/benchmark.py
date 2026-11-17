"""Bounded Argon2id parameter benchmark for the Aether Vault."""

from __future__ import annotations

import argparse
import json
import time

from cryptography.hazmat.primitives.kdf.argon2 import Argon2id

__all__ = [
    "LADDER_MEM_MIB",
    "LADDER_ITERS",
    "MAX_ATTEMPTS",
    "benchmark_argon2",
    "format_recommendation",
]

LADDER_MEM_MIB = (16, 32, 64, 128, 256, 512, 1024)
LADDER_ITERS = (1, 2, 3, 4)
LANES = 4
MAX_ATTEMPTS = 12
_SALT = b"aether-argon2-benchmark-salt"
_SECRET = b"aether-argon2-benchmark-probe"


def _measure(mem_mib: int, iterations: int) -> float:
    kdf = Argon2id(
        salt=_SALT,
        length=32,
        iterations=iterations,
        lanes=LANES,
        memory_cost=mem_mib * 1024,
    )
    start = time.perf_counter()
    kdf.derive(_SECRET)
    return (time.perf_counter() - start) * 1000.0


def benchmark_argon2(target_ms: float = 250, max_mem_mib: int = 1024) -> dict:
    """Measure a fixed candidate ladder and return the strongest combo under target_ms."""
    if not 1 <= target_ms <= 10_000:
        raise ValueError("target_ms must be between 1 and 10000")
    if max_mem_mib < LADDER_MEM_MIB[0]:
        raise ValueError(f"max_mem_mib must be at least {LADDER_MEM_MIB[0]}")
    levels = [m for m in LADDER_MEM_MIB if m <= max_mem_mib]
    candidates = [(mem, iters) for mem in levels for iters in LADDER_ITERS]
    candidates.sort(key=lambda item: (item[0] * item[1], item[0], item[1]))

    attempts = 0
    best: tuple[int, int, int, float] | None = None
    last: tuple[int, int, float] | None = None
    for mem, iters in candidates:
        if attempts >= MAX_ATTEMPTS:
            break
        measured = _measure(mem, iters)
        attempts += 1
        last = (mem, iters, measured)
        work = mem * iters
        if measured <= target_ms:
            if best is None or work > best[0]:
                best = (work, mem, iters, measured)
        elif best is not None:
            break
        else:
            # Ascending ladder: the smallest candidate already missed the target.
            break

    if best is None:
        if last is None:
            raise RuntimeError("benchmark produced no measurement")
        mem, iters, measured = last
        best = (mem * iters, mem, iters, measured)

    _, mem, iters, measured = best
    result = {
        "memory_cost_kib": mem * 1024,
        "mem_mib": mem,
        "iterations": iters,
        "parallelism": LANES,
        "salt_len": 16,
        "measured_ms": round(measured, 3),
        "target_ms": target_ms,
        "attempts": attempts,
    }
    result["recommendation"] = format_recommendation(result)
    return result


def format_recommendation(params: dict) -> str:
    return (
        f"Argon2id: {params['mem_mib']} MiB x {params['iterations']} iterations "
        f"({params['parallelism']} lanes, ~{params['measured_ms']:.0f} ms/run)"
    )


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit full parameters as JSON")
    parser.add_argument("--target-ms", type=float, default=250.0)
    parser.add_argument("--max-mem-mib", type=int, default=1024)
    args = parser.parse_args(argv)
    params = benchmark_argon2(args.target_ms, args.max_mem_mib)
    print(json.dumps(params, sort_keys=True) if args.json else params["recommendation"])
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
