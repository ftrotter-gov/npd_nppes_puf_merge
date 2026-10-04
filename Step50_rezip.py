#!/usr/bin/env python3
"""
Step50 - Re-zip the merged output as a V3 dissemination archive.

Takes ./working_data/output.csv, renames it to the same name as the main CSV
that came out of the incoming V2 zip, and writes a new zip whose filename has
V3 in place of V2:

    NPPES_Data_Dissemination_September_2026_V2.zip   (input, untouched)
    NPPES_Data_Dissemination_September_2026_V3.zip   (output, written here)

Both archives end up side by side in ./working_data/.

Everything else in the V2 archive (the Other Name, Practice Location and
Endpoint reference files, plus the readme and code values PDFs) is copied
across unchanged so that the V3 zip is a drop-in replacement. Members are
streamed one at a time so that a ~10 GB CSV never has to be read into memory.
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
import zipfile
from pathlib import Path
from typing import List, Optional

REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT_CSV = REPO_ROOT / "working_data" / "output.csv"

# 64 KiB copy buffer when streaming members between archives.
COPY_BUFFER = 64 * 1024


def v3_zip_name(v2_zip_name: str) -> str:
    """
    Derive the V3 zip filename from the V2 one.

    NPPES_Data_Dissemination_September_2026_V2.zip
      -> NPPES_Data_Dissemination_September_2026_V3.zip
    """
    new_name, count = re.subn(r"V2(?=\.zip$)", "V3", v2_zip_name)
    if count == 0:
        # Fall back to appending the version if the name is unexpected.
        stem = Path(v2_zip_name).stem
        return f"{stem}_V3.zip"
    return new_name


def find_main_csv_name(v2_zip: Path) -> str:
    """
    Return the archive-relative name of the main npidata_pfile CSV inside the
    V2 zip. The header-only ``*_fileheader.csv`` companion is ignored.
    """
    with zipfile.ZipFile(v2_zip) as archive:
        candidates = [
            info
            for info in archive.infolist()
            if not info.is_dir()
            and Path(info.filename).name.lower().startswith("npidata_pfile_")
            and info.filename.lower().endswith(".csv")
            and "fileheader" not in info.filename.lower()
        ]

    if not candidates:
        raise RuntimeError(f"No npidata_pfile_*.csv found inside {v2_zip}")

    # The data file is by far the largest.
    return max(candidates, key=lambda info: info.file_size).filename


def _fileheader_member_for(main_csv_member: str) -> str:
    """
    Return the archive name of the header-only companion for the main CSV.

    npidata_pfile_20050523-20251012.csv
      -> npidata_pfile_20050523-20251012_fileheader.csv
    """
    path = Path(main_csv_member)
    return str(path.with_name(f"{path.stem}_fileheader{path.suffix}"))


def _read_first_line(csv_path: Path) -> bytes:
    """Read just the header line of a (potentially enormous) CSV."""
    with open(csv_path, "rb") as handle:
        line = handle.readline()
    if not line:
        raise ValueError(f"File is empty, no header row found: {csv_path}")
    return line


def rezip(
    output_csv: Path,
    v2_zip: Path,
    *,
    v3_zip: Optional[Path] = None,
    keep_original_output: bool = False,
    compresslevel: int = 6,
) -> Path:
    """Build the V3 zip next to the V2 zip."""
    if v3_zip is None:
        v3_zip = v2_zip.with_name(v3_zip_name(v2_zip.name))

    main_csv_member = find_main_csv_name(v2_zip)
    main_csv_basename = Path(main_csv_member).name

    # Rename output.csv to the name the CSV had inside the V2 archive.
    #
    # This is done inside a dedicated staging directory because the unzipped
    # V2 source CSV already occupies that filename in ./working_data/. Renaming
    # in place would silently overwrite the input to Step30, which would make
    # the next run merge an already merged file.
    staging_dir = output_csv.parent / "v3_staging"
    staging_dir.mkdir(parents=True, exist_ok=True)
    renamed_csv = staging_dir / main_csv_basename

    if renamed_csv.resolve() != output_csv.resolve():
        if keep_original_output:
            print(f"Copying {output_csv.name} -> {renamed_csv}")
            shutil.copy2(output_csv, renamed_csv)
        else:
            print(f"Renaming {output_csv.name} -> {renamed_csv}")
            output_csv.replace(renamed_csv)

    size_mb = renamed_csv.stat().st_size / 1024 / 1024
    print(f"Creating {v3_zip}")

    with zipfile.ZipFile(
        v3_zip, "w", compression=zipfile.ZIP_DEFLATED,
        compresslevel=compresslevel, allowZip64=True,
    ) as target:
        # 1. The merged V3 main data file.
        print(f"  adding {main_csv_member} ({size_mb:,.1f} MB)")
        target.write(renamed_csv, arcname=main_csv_member)

        # 2. Everything else from the V2 archive, streamed across unchanged.
        #    The main file's header-only companion is regenerated instead of
        #    copied, because the V3 file has five extra columns.
        header_member = _fileheader_member_for(main_csv_member)

        with zipfile.ZipFile(v2_zip) as source:
            for info in source.infolist():
                if info.is_dir() or info.filename == main_csv_member:
                    continue

                if info.filename == header_member:
                    v3_header_line = _read_first_line(renamed_csv)
                    print(f"  regenerating {info.filename} for the V3 layout")
                    target.writestr(info.filename, v3_header_line)
                    continue

                print(
                    f"  copying {info.filename} "
                    f"({info.file_size / 1024 / 1024:,.1f} MB)"
                )
                with source.open(info) as reader, \
                        target.open(info.filename, "w") as writer:
                    shutil.copyfileobj(reader, writer, COPY_BUFFER)

    print(f"Wrote {v3_zip} ({v3_zip.stat().st_size / 1024 / 1024:,.1f} MB)")

    # The staged CSV is now captured inside the zip; drop the loose copy so
    # that ./working_data/ does not hold two ~10 GB files.
    if not keep_original_output:
        renamed_csv.unlink(missing_ok=True)
        try:
            renamed_csv.parent.rmdir()
        except OSError:
            pass  # directory not empty, leave it alone

    return v3_zip


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Re-zip the merged V3 PUF alongside the incoming V2 zip.",
    )
    parser.add_argument(
        "--output-csv",
        default=str(DEFAULT_OUTPUT_CSV),
        help="The merged V3 CSV (default: ./working_data/output.csv).",
    )
    parser.add_argument(
        "--v2-zip",
        required=True,
        help="The incoming V2 zip, used for the filename and reference files.",
    )
    parser.add_argument(
        "--v3-zip",
        default=None,
        help="Override the output zip path (default: V2 name with V3 substituted).",
    )
    parser.add_argument(
        "--keep-output-csv",
        action="store_true",
        help="Copy rather than rename output.csv, leaving the original in place.",
    )
    parser.add_argument(
        "--compresslevel",
        type=int,
        default=6,
        help="Deflate compression level 0-9 (default: 6).",
    )
    args = parser.parse_args(argv)

    output_csv = Path(args.output_csv)
    v2_zip = Path(args.v2_zip)

    if not output_csv.is_file():
        print(f"ERROR: merged CSV not found: {output_csv}", file=sys.stderr)
        return 1
    if not v2_zip.is_file():
        print(f"ERROR: V2 zip not found: {v2_zip}", file=sys.stderr)
        return 1

    v3_zip = rezip(
        output_csv,
        v2_zip,
        v3_zip=Path(args.v3_zip) if args.v3_zip else None,
        keep_original_output=args.keep_output_csv,
        compresslevel=args.compresslevel,
    )
    print(f"V3_ZIP={v3_zip}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
