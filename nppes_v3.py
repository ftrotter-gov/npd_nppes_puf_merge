#!/usr/bin/env python3
"""
Shared definitions for the V3 NPPES PUF format.

The V3 format is the existing (V2) main NPPES data dissemination file with five
additional columns appended to the end of every row. These columns are
documented in README.md and are reproduced here as the single source of truth
used by the Step* scripts.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import List

# ---------------------------------------------------------------------------
# The five new V3 columns, in the order they are appended to each row.
# ---------------------------------------------------------------------------
NPI_MANAGED_BY = "npi_managed_by"
NPI_ACTIVATION_STATUS = "npi_activation_status"
NPI_ACTIVATION_CHANGE_REASON_LIST = "npi_activation_change_reason_list"
NPI_ACTIVATION_FUTURE_CHANGE_DATE = "npi_activation_future_change_date"
NPI_FHIR_URL = "npi_fhir_url"

V3_NEW_COLUMNS: List[str] = [
    NPI_MANAGED_BY,
    NPI_ACTIVATION_STATUS,
    NPI_ACTIVATION_CHANGE_REASON_LIST,
    NPI_ACTIVATION_FUTURE_CHANGE_DATE,
    NPI_FHIR_URL,
]

# ---------------------------------------------------------------------------
# Allowed / default values
# ---------------------------------------------------------------------------
MANAGED_BY_NPPES = "nppes"
MANAGED_BY_NPD = "npd"

STATUS_ACTIVE = "active"
STATUS_DEACTIVE = "deactive"
# Reserved for future use; documented in README.md.
STATUS_SOON_TO_BE_DEACTIVATED = "soon_to_be_deactivated"

# "default value of '0000-00-00' for all values for now"
DEFAULT_FUTURE_CHANGE_DATE = "0000-00-00"
# "Default value is blank"
DEFAULT_CHANGE_REASON_LIST = ""
# Only NPD managed records carry a FHIR URL for the time being.
DEFAULT_FHIR_URL = ""

# ---------------------------------------------------------------------------
# Column positions within the V2 main file that the merge logic depends upon.
# These are positional (not by name) so that streaming stays cheap.
# ---------------------------------------------------------------------------
COL_NPI = 0
COL_ENTITY_TYPE_CODE = 1
COL_NPI_DEACTIVATION_DATE = 39
COL_NPI_REACTIVATION_DATE = 40

# Number of columns in the V2 main NPPES file.
V2_COLUMN_COUNT = 330


def default_activation_status(row: List[str]) -> str:
    """
    Derive ``npi_activation_status`` for an NPPES managed record.

    Per README.md the "default value mirrors activation status of the current
    record". NPPES expresses deactivation through the *NPI Deactivation Date*
    column, and a subsequent reactivation through the *NPI Reactivation Date*
    column. A record is therefore deactivated when it has a deactivation date
    that has not been superseded by a later reactivation date.
    """
    deactivation_date = _cell(row, COL_NPI_DEACTIVATION_DATE)
    reactivation_date = _cell(row, COL_NPI_REACTIVATION_DATE)

    if deactivation_date and not reactivation_date:
        return STATUS_DEACTIVE
    return STATUS_ACTIVE


def _cell(row: List[str], index: int) -> str:
    """Return a stripped cell value, tolerating short rows."""
    if index < len(row):
        return row[index].strip()
    return ""


def read_header(csv_path: str | Path) -> List[str]:
    """Read just the header row from a CSV file."""
    with open(csv_path, "r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        try:
            return next(reader)
        except StopIteration:
            raise ValueError(f"File is empty, no header row found: {csv_path}")


def build_v3_header(v2_header: List[str]) -> List[str]:
    """Append the five new V3 columns to a V2 header."""
    return list(v2_header) + list(V3_NEW_COLUMNS)
