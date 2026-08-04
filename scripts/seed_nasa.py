#!/usr/bin/env python3
"""Seed PulseGrid with the NASA-HTTP access-log dataset.

The NASA-HTTP logs (Kennedy Space Center, July-August 1995, ~3.4 M requests)
give PulseGrid a realistic, publicly available traffic shape to demonstrate
forecasting and anomaly detection against — including a genuine multi-day
outage the anomaly detector should find without being told about it.

What it does
------------
1. Streams the (optionally gzipped) Common Log Format file line by line, so
   3.4 M rows never need to fit in memory.
2. Parses each line into ``(time, endpoint, method, status_code, bytes)``.
3. Normalises raw paths to endpoint templates via the same
   :func:`app.routers.ingest.normalise_endpoint` the live collectors use — if
   the seeder grouped differently, seeded and live rollups would not be
   comparable.
4. Synthesises a plausible ``latency_ms`` from response size and status, since
   the dataset records no timings. This is *derived*, not measured; see
   :func:`synthesise_latency`.
5. Optionally compresses the 1995 timeline into a recent window
   (``--compress-to-hours``) so the dashboard shows live-looking data.
6. Bulk-inserts into ``request_log`` in batches.

Usage::

    python scripts/seed_nasa.py --api-id 1 --input data/NASA_access_log_Jul95.gz
    python scripts/seed_nasa.py --api-id 1 --input <file> --limit 50000 --compress-to-hours 24
    python scripts/seed_nasa.py --api-id 1 --input <file> --dry-run
"""

from __future__ import annotations

import argparse
import gzip
import random
import re
import sys
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

# The script lives beside the backend package rather than inside it.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from sqlmodel import Session, select  # noqa: E402

from app.database import engine  # noqa: E402
from app.models import ApiRegistry, LogSource, RequestLog  # noqa: E402
from app.routers.ingest import normalise_endpoint  # noqa: E402

DATASET_URL = "https://ita.ee.lbl.gov/traces/NASA_access_log_Jul95.gz"

#: Common Log Format: host - - [timestamp] "METHOD path PROTOCOL" status bytes
_LINE = re.compile(
    r"^(?P<host>\S+)\s+\S+\s+\S+\s+\[(?P<time>[^\]]+)\]\s+"
    r'"(?P<method>[A-Z]+)\s+(?P<path>\S+)(?:\s+\S+)?"\s+'
    r"(?P<status>\d{3})\s+(?P<bytes>\d+|-)\s*$"
)

_TIME_FORMAT = "%d/%b/%Y:%H:%M:%S %z"

#: Synthetic latency model. Fixed overhead plus a size-proportional term, since
#: 1995 static-file serving was dominated by transfer time.
_BASE_LATENCY_MS = 12.0
_MS_PER_KILOBYTE = 1.8
_ERROR_LATENCY_MS = 4.0
_JITTER = 0.25


def open_log(path: Path):
    """Open a plain or gzipped log file as latin-1 text.

    latin-1 rather than UTF-8 because 1995 request paths contain arbitrary
    bytes; latin-1 maps every byte to a character, so no line is ever dropped
    for being undecodable.

    Args:
        path: File to read.

    Returns:
        A text-mode file object.
    """
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="latin-1", errors="replace")
    return path.open("rt", encoding="latin-1", errors="replace")


def synthesise_latency(response_bytes: int, status_code: int, rng: random.Random) -> float:
    """Derive a plausible latency for a record that has none.

    The dataset records no timings, so this is an explicitly *synthetic* value:
    a fixed overhead plus a term proportional to response size, with jitter.
    Errors return early and so return fast. It exists to give the latency
    signal a realistic shape; it is not a measurement, and nothing should be
    concluded from its absolute values.

    Args:
        response_bytes: Response size in bytes.
        status_code: HTTP status.
        rng: Seeded generator, so a given file always produces the same series.

    Returns:
        float: Latency in milliseconds.
    """
    if status_code >= 400:
        base = _ERROR_LATENCY_MS
    else:
        base = _BASE_LATENCY_MS + (response_bytes / 1024.0) * _MS_PER_KILOBYTE
    return round(max(0.5, base * rng.uniform(1.0 - _JITTER, 1.0 + _JITTER)), 3)


def parse_lines(handle, limit: int | None) -> Iterator[tuple[datetime, str, str, int, int]]:
    """Parse log lines, skipping ones that do not match the format.

    Args:
        handle: Open text file.
        limit: Stop after this many *parsed* records. ``None`` reads all.

    Yields:
        tuple: ``(time, path, method, status_code, response_bytes)``.
    """
    parsed = 0
    for line in handle:
        match = _LINE.match(line.strip())
        if match is None:
            continue
        try:
            when = datetime.strptime(match["time"], _TIME_FORMAT).astimezone(UTC)
        except ValueError:
            continue
        raw_bytes = match["bytes"]
        yield (
            when,
            match["path"],
            match["method"],
            int(match["status"]),
            0 if raw_bytes == "-" else int(raw_bytes),
        )
        parsed += 1
        if limit is not None and parsed >= limit:
            return


def build_rescaler(
    first: datetime, last: datetime, compress_to_hours: int | None
):  # -> Callable[[datetime], datetime]
    """Build the function that maps a 1995 timestamp onto the output timeline.

    Args:
        first: Earliest timestamp in the data.
        last: Latest timestamp in the data.
        compress_to_hours: Window to compress the span into, ending now.
            ``None`` keeps the original timestamps.

    Returns:
        A callable mapping an original timestamp to its output timestamp.
    """
    if compress_to_hours is None:
        return lambda when: when

    span = (last - first).total_seconds() or 1.0
    end = datetime.now(UTC)
    start = end - timedelta(hours=compress_to_hours)
    target = (end - start).total_seconds()

    def rescale(when: datetime) -> datetime:
        return start + timedelta(seconds=(when - first).total_seconds() / span * target)

    return rescale


def scan(path: Path, limit: int | None) -> tuple[list[tuple], datetime, datetime]:
    """Read and parse the file into memory-resident records.

    A compressed timeline needs the *first and last* timestamps before it can
    place any row, which means one pass to learn the span. For the full 3.4 M
    rows use ``--limit`` (or accept the memory cost); for the sizes a demo
    actually loads this is a few hundred megabytes at worst.

    Args:
        path: Log file to read.
        limit: Maximum records to parse.

    Returns:
        tuple: The records plus the first and last timestamps seen.

    Raises:
        SystemExit: If the file yields no parsable records.
    """
    with open_log(path) as handle:
        records = list(parse_lines(handle, limit))

    if not records:
        raise SystemExit(f"no parsable records in {path}")

    times = [record[0] for record in records]
    return records, min(times), max(times)


def seed(
    records: list[tuple],
    api_id: int,
    rescale,
    batch_size: int,
    dry_run: bool,
) -> int:
    """Insert parsed records into ``request_log``.

    Args:
        records: Parsed records from :func:`scan`.
        api_id: Registry id the rows are attributed to.
        rescale: Timestamp mapping from :func:`build_rescaler`.
        batch_size: Rows per flush.
        dry_run: Parse and report without writing.

    Returns:
        int: Number of rows written (or that would have been written).

    Raises:
        SystemExit: If ``api_id`` is not registered.
    """
    rng = random.Random(1995)  # noqa: S311 - synthetic latency, not crypto

    if dry_run:
        return len(records)

    with Session(engine) as session:
        if session.exec(select(ApiRegistry).where(ApiRegistry.id == api_id)).first() is None:
            raise SystemExit(f"api_id {api_id} is not registered; create it via POST /v1/apis")

        written = 0
        batch: list[RequestLog] = []
        for when, path, method, status_code, response_bytes in records:
            batch.append(
                RequestLog(
                    time=rescale(when),
                    api_id=api_id,
                    endpoint=normalise_endpoint(path),
                    method=method,
                    status_code=status_code,
                    latency_ms=synthesise_latency(response_bytes, status_code, rng),
                    response_bytes=response_bytes or None,
                    is_error=status_code >= 500,
                    source=LogSource.SDK,
                )
            )
            if len(batch) >= batch_size:
                session.add_all(batch)
                session.commit()
                written += len(batch)
                batch.clear()
                print(f"  ... {written:,} rows", flush=True)

        if batch:
            session.add_all(batch)
            session.commit()
            written += len(batch)

    return written


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
        help="Rows per insert batch.",
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

    if not args.input.exists():
        print(f"no such file: {args.input}\ndownload it from {DATASET_URL}", file=sys.stderr)
        return 1

    print(f"parsing {args.input} ...", flush=True)
    records, first, last = scan(args.input, args.limit)
    print(f"parsed {len(records):,} records spanning {first.date()} to {last.date()}")

    rescale = build_rescaler(first, last, args.compress_to_hours)
    if args.compress_to_hours:
        print(f"compressing that span into the last {args.compress_to_hours}h")

    written = seed(records, args.api_id, rescale, args.batch_size, args.dry_run)

    if args.dry_run:
        print(f"dry run: {written:,} rows would be written to api_id {args.api_id}")
    else:
        print(f"wrote {written:,} rows to api_id {args.api_id}")
        print("the rollup job will aggregate them within one interval")
    return 0


if __name__ == "__main__":
    sys.exit(main())
