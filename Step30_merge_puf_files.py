#!/usr/bin/env python3
"""
Step30 - Merge the NPD and NPPES versions of the NPPES PUF into a V3 PUF.

The NPD file (currently ./mock_data/npd_nppes_file_mockup_initial.csv) is
loaded into memory, because it is small relative to the NPPES PUF. The main
NPPES file is then *streamed* row by row and written out to
./working_data/output.csv in the V3 format.

Ordering rules, per the project instructions:

  * Every NPI in the source NPPES PUF appears in the output file in exactly
    the same order.
  * Where an NPI is managed by NPD, the NPD record is emitted in place of the
    NPPES record (keeping the NPPES position).
  * Any NPI that is present in the NPD file but absent from the NPPES PUF is
    appended to the end of the output file.

Memory profile: the NPPES file is never loaded into memory. Only one row is
held at a time, so peak usage is dominated by the NPD file, which is tiny.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Dict, List, Optional

from nppes_v3 import (
    COL_NPI,
    DEFAULT_CHANGE_REASON_LIST,
    DEFAULT_FHIR_URL,
    DEFAULT_FUTURE_CHANGE_DATE,
    MANAGED_BY_NPPES,
    V2_COLUMN_COUNT,
    V3_NEW_COLUMNS,
    build_v3_header,
    default_activation_status,
)

REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_NPD_CSV = REPO_ROOT / "mock_data" / "npd_nppes_file_mockup_initial.csv"
DEFAULT_OUTPUT = REPO_ROOT / "working_data" / "output.csv"

# NPPES publishes these files in latin-1 / cp1252 rather than utf-8.
NPPES_ENCODING = "latin-1"

PROGRESS_EVERY = 500_000

# The csv module refuses very long fields by default; NPPES rows are wide.
csv.field_size_limit(10 * 1024 * 1024)


def load_npd_records(npd_csv: Path, expected_columns: int) -> Dict[str, List[str]]:
    """
    Load the NPD V3 file into an {NPI: row} mapping.

    The NPD file is expected to already be in the V3 format, i.e. it carries
    the 330 V2 columns plus the 5 new V3 columns.
    """
    records: Dict[str, List[str]] = {}

    with open(npd_csv, "r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration:
            raise ValueError(f"NPD file is empty: {npd_csv}")

        if len(header) != expected_columns:
            raise ValueError(
                f"NPD file {npd_csv} has {len(header)} columns, "
                f"expected {expected_columns} (330 V2 columns + "
                f"{len(V3_NEW_COLUMNS)} V3 columns)."
            )

        for line_number, row in enumerate(reader, start=2):
            if not row:
                continue
            if len(row) != expected_columns:
                raise ValueError(
                    f"NPD file {npd_csv} line {line_number} has {len(row)} "
                    f"columns, expected {expected_columns}."
                )

            npi = row[COL_NPI].strip()
            if not npi:
                raise ValueError(f"NPD file {npd_csv} line {line_number} has a blank NPI.")
            if npi in records:
                raise ValueError(f"NPD file {npd_csv} contains duplicate NPI {npi}.")

            records[npi] = row

    return records


def nppes_row_to_v3(row: List[str]) -> List[str]:
    """
    Convert a V2 NPPES row into a V3 row using the documented defaults.

    Per README.md, NPPES managed records get:
      npi_managed_by                    = "nppes"
      npi_activation_status             = mirrors the current record
      npi_activation_change_reason_list = blank
      npi_activation_future_change_date = "0000-00-00"
      npi_fhir_url                      = blank (NPD managed records only)
    """
    return row + [
        MANAGED_BY_NPPES,
        default_activation_status(row),
        DEFAULT_CHANGE_REASON_LIST,
        DEFAULT_FUTURE_CHANGE_DATE,
        DEFAULT_FHIR_URL,
    ]


def merge(
    nppes_csv: Path,
    npd_csv: Path,
    output_csv: Path,
    *,
    progress_every: int = PROGRESS_EVERY,
) -> Dict[str, int]:
    """Stream the NPPES PUF into ``output_csv``, overlaying the NPD records."""
    expected_v3_columns = V2_COLUMN_COUNT + len(V3_NEW_COLUMNS)

    npd_records = load_npd_records(npd_csv, expected_v3_columns)
    print(f"Loaded {len(npd_records):,} NPD records from {npd_csv}")

    # Track which NPD NPIs we have already emitted so the remainder can be
    # appended at the end of the file.
    unused_npd_npis = set(npd_records)

    output_csv.parent.mkdir(parents=True, exist_ok=True)

    rows_read = 0
    rows_replaced = 0

    with open(nppes_csv, "r", encoding=NPPES_ENCODING, newline="") as source, \
            open(output_csv, "w", encoding="utf-8", newline="") as target:
        reader = csv.reader(source)
        writer = csv.writer(target, quoting=csv.QUOTE_ALL)

        try:
            v2_header = next(reader)
        except StopIteration:
            raise ValueError(f"NPPES file is empty: {nppes_csv}")

        if len(v2_header) != V2_COLUMN_COUNT:
            raise ValueError(
                f"NPPES file {nppes_csv} has {len(v2_header)} columns, "
                f"expected {V2_COLUMN_COUNT}."
            )

        writer.writerow(build_v3_header(v2_header))

        for row in reader:
            if not row:
                continue
            rows_read += 1

            # Be tolerant of short/long rows rather than failing a 10 GB job.
            if len(row) < V2_COLUMN_COUNT:
                row = row + [""] * (V2_COLUMN_COUNT - len(row))
            elif len(row) > V2_COLUMN_COUNT:
                row = row[:V2_COLUMN_COUNT]

            npi = row[COL_NPI].strip()
            npd_row = npd_records.get(npi)

            if npd_row is not None:
                # NPD manages this NPI: emit the NPD record in the NPPES slot.
                writer.writerow(npd_row)
                unused_npd_npis.discard(npi)
                rows_replaced += 1
            else:
                writer.writerow(nppes_row_to_v3(row))

            if progress_every and rows_read % progress_every == 0:
                print(f"  {rows_read:,} NPPES rows processed", flush=True)

        # Any NPD NPI that never appeared in the NPPES PUF goes at the end,
        # in the order it appeared in the NPD file.
        appended = 0
        for npi, npd_row in npd_records.items():
            if npi in unused_npd_npis:
                writer.writerow(npd_row)
                appended += 1

    stats = {
        "nppes_rows": rows_read,
        "npd_records": len(npd_records),
        "npd_replaced": rows_replaced,
        "npd_appended": appended,
        "output_rows": rows_read + appended,
    }

    print(f"NPPES rows read:        {stats['nppes_rows']:,}")
    print(f"NPD records loaded:     {stats['npd_records']:,}")
    print(f"NPD records merged:     {stats['npd_replaced']:,}")
    print(f"NPD records appended:   {stats['npd_appended']:,}")
    print(f"Output rows written:    {stats['output_rows']:,}")
    print(f"Wrote {output_csv}")

    return stats


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Merge the NPD and NPPES PUF files into a V3 formatted PUF.",
    )
    parser.add_argument(
        "--nppes-csv",
        required=True,
        help="Path to the main NPPES npidata_pfile CSV (V2 format).",
    )
    parser.add_argument(
        "--npd-csv",
        default=str(DEFAULT_NPD_CSV),
        help="Path to the NPD managed V3 formatted CSV.",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="Where to write the merged V3 PUF (default: ./working_data/output.csv).",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=PROGRESS_EVERY,
        help="Print progress every N rows (0 disables).",
    )
    args = parser.parse_args(argv)

    nppes_csv = Path(args.nppes_csv)
    npd_csv = Path(args.npd_csv)
    output_csv = Path(args.output)

    for path, label in ((nppes_csv, "NPPES"), (npd_csv, "NPD")):
        if not path.is_file():
            print(f"ERROR: {label} file not found: {path}", file=sys.stderr)
            return 1

    merge(nppes_csv, npd_csv, output_csv, progress_every=args.progress_every)
    print(f"OUTPUT_CSV={output_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
