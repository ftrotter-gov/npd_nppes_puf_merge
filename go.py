#!/usr/bin/env python3
"""
go.py - Run the whole NPD / NPPES PUF merge pipeline.

    Step10_current_nppes_downloader.py   download + unzip the monthly V2 zip
    Step30_merge_puf_files.py            merge NPD over NPPES into a V3 CSV
    Step40_test_merge.py                 validate the result with InLaw
    Step50_rezip.py                      package the result as a V3 zip

This script works out all of the filenames (which monthly zip was downloaded,
what the main CSV inside it is called, what the V3 zip should be named) and
passes them to the individual steps as CLI arguments, so each step stays
independently runnable.

Examples:

    # Full run, downloading the current monthly file
    ./go.py

    # Re-run the merge and tests against an already downloaded file
    ./go.py --skip-download

    # Skip the (slow) validation step
    ./go.py --skip-tests
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional

REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_WORKING_DIR = REPO_ROOT / "working_data"
DEFAULT_NPD_CSV = REPO_ROOT / "mock_data" / "npd_nppes_file_mockup_initial.csv"
DEFAULT_OUTPUT_CSV = DEFAULT_WORKING_DIR / "output.csv"

STEP10 = REPO_ROOT / "Step10_current_nppes_downloader.py"
STEP30 = REPO_ROOT / "Step30_merge_puf_files.py"
STEP40 = REPO_ROOT / "Step40_test_merge.py"
STEP50 = REPO_ROOT / "Step50_rezip.py"


def python_executable() -> str:
    """
    Pick the interpreter to run the individual steps with.

    When go.py is launched via its shebang (./go.py) sys.executable is the
    system python, which will not have the project dependencies installed.
    Prefer the project virtualenv when one is present.
    """
    for candidate in (REPO_ROOT / ".venv" / "bin" / "python",
                      REPO_ROOT / "venv" / "bin" / "python"):
        if candidate.is_file():
            return str(candidate)
    return sys.executable


def run_step(script: Path, arguments: List[str], *, label: str) -> str:
    """Run one pipeline step, streaming and capturing its output."""
    command = [python_executable(), str(script), *arguments]

    print()
    print("=" * 72)
    print(f"  {label}")
    print(f"  {' '.join(command)}")
    print("=" * 72, flush=True)

    started = time.time()
    captured: List[str] = []

    process = subprocess.Popen(
        command,
        cwd=str(REPO_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert process.stdout is not None
    for line in process.stdout:
        sys.stdout.write(line)
        sys.stdout.flush()
        captured.append(line)

    returncode = process.wait()
    elapsed = time.time() - started

    if returncode != 0:
        raise SystemExit(f"\n{label} failed with exit code {returncode}")

    print(f"\n{label} completed in {elapsed:,.1f}s")
    return "".join(captured)


def parse_marker(output: str, marker: str) -> Optional[str]:
    """Pull a ``MARKER=value`` line out of a step's output."""
    prefix = f"{marker}="
    for line in reversed(output.splitlines()):
        line = line.strip()
        if line.startswith(prefix):
            return line[len(prefix):].strip()
    return None


def discover_v2_zip(working_dir: Path) -> Optional[Path]:
    """Find an already downloaded monthly V2 zip in the working directory."""
    candidates = [
        path
        for path in working_dir.glob("NPPES_Data_Dissemination_*_V2.zip")
        if "Weekly" not in path.name and "Deactivated" not in path.name
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def discover_main_csv(working_dir: Path) -> Optional[Path]:
    """Find the unzipped main npidata_pfile CSV in the working directory."""
    candidates = [
        path
        for path in working_dir.glob("npidata_pfile_*.csv")
        if "fileheader" not in path.name.lower()
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_size)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the full NPD / NPPES PUF merge pipeline.",
    )
    parser.add_argument(
        "--working-dir",
        default=str(DEFAULT_WORKING_DIR),
        help="Working directory for downloads and output (default: ./working_data).",
    )
    parser.add_argument(
        "--npd-csv",
        default=str(DEFAULT_NPD_CSV),
        help="The NPD managed V3 formatted CSV.",
    )
    parser.add_argument(
        "--output-csv",
        default=str(DEFAULT_OUTPUT_CSV),
        help="Where the merged V3 CSV is written.",
    )
    parser.add_argument(
        "--nppes-csv",
        default=None,
        help="Use a specific NPPES main CSV instead of auto-discovering one.",
    )
    parser.add_argument(
        "--v2-zip",
        default=None,
        help="Use a specific V2 zip instead of auto-discovering one.",
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Skip Step10 and use the files already in the working directory.",
    )
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Skip the Step40 InLaw validation.",
    )
    parser.add_argument(
        "--skip-rezip",
        action="store_true",
        help="Skip the Step50 re-zip.",
    )
    parser.add_argument(
        "--keep-db",
        action="store_true",
        help="Keep the Step40 staging DuckDB file.",
    )
    parser.add_argument(
        "--min-npis",
        type=int,
        default=None,
        help="Override the Step40 lower bound on the output NPI count. "
             "Useful when running against a small test fixture.",
    )
    parser.add_argument(
        "--max-npis",
        type=int,
        default=None,
        help="Override the Step40 upper bound on the output NPI count.",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    working_dir = Path(args.working_dir).resolve()
    working_dir.mkdir(parents=True, exist_ok=True)

    npd_csv = Path(args.npd_csv).resolve()
    output_csv = Path(args.output_csv).resolve()

    if not npd_csv.is_file():
        print(f"ERROR: NPD file not found: {npd_csv}", file=sys.stderr)
        print(
            "Hint: run ./make_mock_npd_file.py to generate the mock NPD file.",
            file=sys.stderr,
        )
        return 1

    pipeline_started = time.time()

    nppes_csv = Path(args.nppes_csv).resolve() if args.nppes_csv else None
    v2_zip = Path(args.v2_zip).resolve() if args.v2_zip else None

    # ------------------------------------------------------------------
    # Step10 - download and unzip
    # ------------------------------------------------------------------
    if args.skip_download:
        print("Skipping Step10 (--skip-download)")
    else:
        step10_output = run_step(
            STEP10,
            ["--working-dir", str(working_dir)],
            label="Step10 - download the current monthly NPPES file",
        )
        zip_marker = parse_marker(step10_output, "ZIP_PATH")
        csv_marker = parse_marker(step10_output, "MAIN_CSV")
        if v2_zip is None and zip_marker:
            v2_zip = Path(zip_marker)
        if nppes_csv is None and csv_marker:
            nppes_csv = Path(csv_marker)

    # Fall back to discovery for anything we still do not know.
    if v2_zip is None:
        v2_zip = discover_v2_zip(working_dir)
    if nppes_csv is None:
        nppes_csv = discover_main_csv(working_dir)

    if nppes_csv is None or not nppes_csv.is_file():
        print(
            f"ERROR: could not find an npidata_pfile_*.csv in {working_dir}.\n"
            "Run without --skip-download, or pass --nppes-csv explicitly.",
            file=sys.stderr,
        )
        return 1

    print(f"\nNPPES main CSV: {nppes_csv}")
    print(f"NPD CSV:        {npd_csv}")
    print(f"V2 zip:         {v2_zip if v2_zip else '(not found)'}")

    # ------------------------------------------------------------------
    # Step30 - merge
    # ------------------------------------------------------------------
    run_step(
        STEP30,
        [
            "--nppes-csv", str(nppes_csv),
            "--npd-csv", str(npd_csv),
            "--output", str(output_csv),
        ],
        label="Step30 - merge the NPD and NPPES PUF files",
    )

    # ------------------------------------------------------------------
    # Step40 - validate
    # ------------------------------------------------------------------
    if args.skip_tests:
        print("\nSkipping Step40 (--skip-tests)")
    else:
        step40_args = [
            "--nppes-csv", str(nppes_csv),
            "--output-csv", str(output_csv),
            "--db", str(working_dir / "merge_tests.duckdb"),
        ]
        if args.keep_db:
            step40_args.append("--keep-db")
        if args.min_npis is not None:
            step40_args += ["--min-npis", str(args.min_npis)]
        if args.max_npis is not None:
            step40_args += ["--max-npis", str(args.max_npis)]
        run_step(
            STEP40,
            step40_args,
            label="Step40 - validate the merged file with InLaw",
        )

    # ------------------------------------------------------------------
    # Step50 - re-zip
    # ------------------------------------------------------------------
    if args.skip_rezip:
        print("\nSkipping Step50 (--skip-rezip)")
    elif v2_zip is None or not v2_zip.is_file():
        print(
            f"\nWARNING: no V2 zip found in {working_dir}, skipping Step50. "
            "Pass --v2-zip to re-zip explicitly.",
            file=sys.stderr,
        )
    else:
        run_step(
            STEP50,
            [
                "--output-csv", str(output_csv),
                "--v2-zip", str(v2_zip),
            ],
            label="Step50 - re-zip the merged file as V3",
        )

    elapsed = time.time() - pipeline_started
    print()
    print("=" * 72)
    print(f"  Pipeline complete in {elapsed / 60:,.1f} minutes")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
