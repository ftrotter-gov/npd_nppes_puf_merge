#!/usr/bin/env python3
"""
Build a small synthetic stand-in for the monthly NPPES dissemination zip.

This lets the whole pipeline (Step30 -> Step40 -> Step50) be exercised without
downloading the real 1.1 GB / 10 GB monthly file. The generated archive mimics
the real one:

  * npidata_pfile_<range>.csv            the main data file (V2, 330 columns)
  * npidata_pfile_<range>_fileheader.csv the header-only companion
  * othername_pfile_<range>.csv          reference file
  * pl_pfile_<range>.csv                 reference file
  * endpoint_pfile_<range>.csv           reference file
  * NPPES_Data_Dissemination_Readme.pdf  placeholder doc

Two of the three NPIs in the mock NPD file (1992931091 and 1801327911) are
deliberately included in the generated NPPES data so the merge/replace path is
exercised; 1234567893 is deliberately excluded so the append-at-end path is
exercised too. Deactivated NPIs are included so that the activation status
derivation is covered.
"""
from __future__ import annotations

import argparse
import csv
import random
import zipfile
from pathlib import Path
from typing import List, Optional

from nppes_v3 import V2_COLUMN_COUNT, read_header

REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_HEADER_CSV = REPO_ROOT / "docs" / "npidata_pfile_20050523-20251012_fileheader.csv"
DEFAULT_WORKING_DIR = REPO_ROOT / "working_data"

FILE_RANGE = "20050523-20251012"
ZIP_NAME = "NPPES_Data_Dissemination_September_2026_V2.zip"

# NPIs from the mock NPD file that must be present in the NPPES data.
NPD_NPIS_IN_NPPES = ["1992931091", "1801327911"]


def npi_check_digit(nine_digits: str) -> int:
    """Compute the NPI (Luhn over the 80840 prefix) check digit."""
    payload = "80840" + nine_digits
    total = 0
    for index, character in enumerate(reversed(payload)):
        digit = int(character)
        if index % 2 == 0:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return (10 - total % 10) % 10


def make_npi(serial: int) -> str:
    """Build a valid synthetic NPI from a serial number."""
    nine = f"{serial:09d}"
    return nine + str(npi_check_digit(nine))


def build_row(header: List[str], npi: str, index: int, *, deactivated: bool) -> List[str]:
    """Create one plausible V2 NPPES data row."""
    row = [""] * len(header)
    entity_type = "1" if index % 3 else "2"

    row[0] = npi
    row[1] = entity_type
    if entity_type == "2":
        row[4] = f"SYNTHETIC ORGANIZATION {index}"
        row[42] = f"OFFICIAL{index}"
        row[43] = "PAT"
        row[45] = "ADMINISTRATOR"
    else:
        row[5] = f"LASTNAME{index}"
        row[6] = f"FIRSTNAME{index}"
        row[10] = random.choice(["M.D.", "D.O.", "R.N.", "PH.D.", ""])
        row[41] = random.choice(["M", "F"])

    row[20] = f"{100 + index} MAIN ST"
    row[22] = "SPRINGFIELD"
    row[23] = random.choice(["TX", "MD", "CA", "NY", "IL"])
    row[24] = f"{10000 + index:09d}"
    row[25] = "US"
    row[28] = f"{100 + index} MAIN ST"
    row[30] = "SPRINGFIELD"
    row[31] = row[23]
    row[32] = row[24]
    row[33] = "US"
    row[36] = "01/02/2010"
    row[37] = "03/04/2024"

    if deactivated:
        # A deactivation date with no reactivation date => "deactive".
        row[38] = "DT"
        row[39] = "05/06/2023"

    row[47] = "207Q00000X"
    row[50] = "Y"
    row[307] = "Y" if entity_type == "1" else ""
    row[329] = "03/04/2024"
    return row


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate a small synthetic NPPES dissemination zip for testing.",
    )
    parser.add_argument("--rows", type=int, default=5000,
                        help="How many NPPES data rows to generate.")
    parser.add_argument("--working-dir", default=str(DEFAULT_WORKING_DIR),
                        help="Where to write the fixture zip.")
    parser.add_argument("--seed", type=int, default=20260101,
                        help="Random seed for reproducibility.")
    args = parser.parse_args(argv)

    random.seed(args.seed)

    header = read_header(DEFAULT_HEADER_CSV)
    if len(header) != V2_COLUMN_COUNT:
        raise ValueError(f"Unexpected header width: {len(header)}")

    working_dir = Path(args.working_dir).resolve()
    working_dir.mkdir(parents=True, exist_ok=True)

    main_csv_name = f"npidata_pfile_{FILE_RANGE}.csv"
    main_csv_path = working_dir / main_csv_name

    # Decide where the real NPD NPIs land inside the file.
    positions = {1: NPD_NPIS_IN_NPPES[0], args.rows // 2: NPD_NPIS_IN_NPPES[1]}

    with open(main_csv_path, "w", encoding="latin-1", newline="") as handle:
        writer = csv.writer(handle, quoting=csv.QUOTE_ALL)
        writer.writerow(header)

        for index in range(1, args.rows + 1):
            npi = positions.get(index) or make_npi(100_000_000 + index)
            # Make roughly every 50th record a deactivated one.
            deactivated = index % 50 == 0 and npi not in NPD_NPIS_IN_NPPES
            writer.writerow(build_row(header, npi, index, deactivated=deactivated))

    print(f"Wrote {main_csv_path} ({args.rows:,} rows)")

    # Assemble the zip the same way CMS does.
    zip_path = working_dir / ZIP_NAME
    docs = REPO_ROOT / "docs"
    reference_files = {
        f"othername_pfile_{FILE_RANGE}.csv":
            docs / f"othername_pfile_{FILE_RANGE}_fileheader.csv",
        f"pl_pfile_{FILE_RANGE}.csv":
            docs / f"pl_pfile_{FILE_RANGE}_fileheader.csv",
        f"endpoint_pfile_{FILE_RANGE}.csv":
            docs / f"endpoint_pfile_{FILE_RANGE}_fileheader.csv",
    }

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
        archive.write(main_csv_path, arcname=main_csv_name)
        archive.write(DEFAULT_HEADER_CSV,
                      arcname=f"npidata_pfile_{FILE_RANGE}_fileheader.csv")
        for arcname, source in reference_files.items():
            archive.write(source, arcname=arcname)
        archive.writestr("NPPES_Data_Dissemination_Readme.pdf",
                         "%PDF-1.4 placeholder readme for testing\n")

    print(f"Wrote {zip_path}")
    print(f"MAIN_CSV={main_csv_path}")
    print(f"ZIP_PATH={zip_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
