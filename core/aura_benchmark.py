"""Fail-closed tombstone for the invalid legacy AURA benchmark.

The previous implementation did not evaluate an AURA response.  It scored a
hard-coded sentence, smoke-tested a hard-coded trivial tool, and reported
hard-coded Elo, win-rate, and throughput values as if they had been measured.

Keeping this module importable makes stale callers fail with an explicit,
auditable error instead of silently resurrecting fabricated evidence.  The
unaltered source and its SHA-256 live under the incident path below.
"""
from __future__ import annotations

import sys
from typing import NoReturn


INCIDENT_PATH = "docs/incidents/2026-08-08-fake-aura-benchmark"


class InvalidBenchmarkError(RuntimeError):
    """Raised whenever code tries to use the quarantined benchmark."""


def _raise_invalid_benchmark() -> NoReturn:
    raise InvalidBenchmarkError(
        "core.aura_benchmark was quarantined because its legacy results were "
        f"not measured. See {INCIDENT_PATH}. Use the Coding Arena contract instead."
    )


class AuraBenchmarkSuite:
    """Compatibility shell that refuses to manufacture benchmark results."""

    quarantined = True

    def __init__(self, *_args, **_kwargs) -> None:
        _raise_invalid_benchmark()

    def evaluate_ifeval(self, *_args, **_kwargs) -> NoReturn:
        _raise_invalid_benchmark()

    def evaluate_swe_bench_coding(self, *_args, **_kwargs) -> NoReturn:
        _raise_invalid_benchmark()

    def evaluate_technical_performance(self, *_args, **_kwargs) -> NoReturn:
        _raise_invalid_benchmark()

    def run_full_benchmark(self, *_args, **_kwargs) -> NoReturn:
        _raise_invalid_benchmark()


def main() -> int:
    try:
        _raise_invalid_benchmark()
    except InvalidBenchmarkError as exc:
        print(f"INVALID BENCHMARK: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
