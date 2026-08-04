#!/usr/bin/env python3
"""Seed PulseGrid with the NASA-HTTP access-log dataset (phase 3 — skeleton only).

The NASA-HTTP logs (Kennedy Space Center, July–August 1995, ~3.4 M requests)
give PulseGrid a realistic, publicly available traffic shape to demonstrate
forecasting and anomaly detection against — including a genuine multi-day
outage that the anomaly detector should find without being told about it.

Planned behaviour (phase 3):
    1. Stream the gzipped Common Log Format file line by line, so the 3.4 M
       rows never need to fit in memory.
    2. Parse each line into ``(time, endpoint, method, status_code, bytes)``.
    3. Normalise raw paths to endpoint templates (``/images/12.gif`` →
       ``/images/{file}``) so rollups group meaningfully.
    4. Synthesise a plausible ``latency_ms`` from response size and status,
       since the dataset records no timings.
    5. Optionally compress the 1995 timeline into a recent window
       (``--compress-to-hours``) so the dashboard shows live-looking data.
    6. Bulk-insert into ``request_log`` with psycopg's ``COPY``.

Usage (phase 3)::

    python scripts/seed_nasa.py --api-id 1 --input data/NASA_access_log_Jul95.gz
    python scripts/seed_nasa.py --api-id 1 --input <file> --limit 50000 --compress-to-hours 24
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

DATASET_URL = "https://ita.ee.lbl.gov/traces/NASA_access_log_Jul95.gz"


def build_parser() -> argparse.ArgumentParser:
    """Construct the command-line parser.

    Returns:
        argparse.ArgumentParser: The configured parser.
    """
    parser = argparse.ArgumentParser(
        prog="seed_nasa",
        description="Load the NASA-HTTP access log into PulseGrid's request_log table.",
        epilog=f"Dataset: {DATASET_URL}",
    )
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Path to the NASA access-log file (plain text or .gz).",
    )
    parser.add_argument(
        "--api-id",
        type=int,
        required=True,
        help="api_registry.id the seeded rows are attributed to.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Stop after N parsed lines. Useful for a quick smoke test.",
    )
    parser.add_argument(
        "--compress-to-hours",
        type=int,
        default=None,
        help="Rescale the 1995 timeline into the last N hours so the dashboard looks live.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10_000,
        help="Rows per COPY batch.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and report statistics without writing to the database.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point.

    Args:
        argv: Argument vector, defaulting to ``sys.argv[1:]``.

    Returns:
        int: Process exit code.
    """
    args = build_parser().parse_args(argv)
    print(f"seed_nasa is a phase-3 script; nothing to do yet (input={args.input}).")
    print("Phase 1 ships the CLI contract only — see the module docstring for the plan.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
