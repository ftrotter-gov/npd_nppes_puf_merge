#!/usr/bin/env python3
"""
Generate ./mock_data/npd_nppes_file_mockup_initial.csv

This simulates the eventual NPD export in the new V3 NPPES data format. It is a
stand-in until NPD publishes a real download link.

The mockup contains three records:

  1992931091  Individual (Entity Type 1), real/active NPI. Exercises the
              "NPD record replaces the NPPES record" merge path.
  1801327911  Organization (Entity Type 2), real/active NPI. Exercises the
              merge path for an organisation, including the authorized
              official credential normalisation.
  1234567893  Synthetic NPI. Passes the NPI Luhn check digit but is absent
              from the NPI registry, so it will never collide with a real
              NPPES record. Exercises the "NPD-only NPIs are appended to the
              end of the output file" path.

Base (V2) field values for the two real NPIs were taken from the public NPPES
registry API at https://npiregistry.cms.hhs.gov/api/ and the NPD specific
columns are populated as described in README.md:

  * EIN points at the uuid of the FHIR organization for the legal entity
  * Credential fields are FaCeT normalised into a pipe delimited list
  * The identifier data is dramatically reduced
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Dict, List

from nppes_v3 import (
    DEFAULT_FUTURE_CHANGE_DATE,
    MANAGED_BY_NPD,
    STATUS_ACTIVE,
    V2_COLUMN_COUNT,
    build_v3_header,
    read_header,
)

REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_HEADER_CSV = REPO_ROOT / "docs" / "npidata_pfile_20050523-20251012_fileheader.csv"
DEFAULT_OUTPUT = REPO_ROOT / "mock_data" / "npd_nppes_file_mockup_initial.csv"

# FHIR base urls for the NPD managed records.
FHIR_BASE = "https://directory.cms.gov/fhir/Practitioner"
FHIR_ORG_BASE = "https://directory.cms.gov/fhir/Organization"


def _record_1992931091() -> Dict[str, str]:
    """Individual provider, NPD managed."""
    return {
        "NPI": "1992931091",
        "Entity Type Code": "1",
        # Individuals do not carry an EIN in NPPES.
        "Employer Identification Number (EIN)": "",
        "Provider Last Name (Legal Name)": "TROTTER",
        "Provider First Name": "FREDERICK",
        "Provider Middle Name": "CLAYTON",
        "Provider Name Prefix Text": "MR.",
        # FaCeT normalised from "B.A., B.A., B.S." (note the de-duplication).
        "Provider Credential Text": "BA | BS",
        "Provider Other Last Name": "TROTTER",
        "Provider Other First Name": "FRED",
        "Provider Other Middle Name": "CLAYTON",
        "Provider Other Name Prefix Text": "MR.",
        # FaCeT normalised from "B.A., B.A., B.S."
        "Provider Other Credential Text": "BA | BS",
        "Provider Other Last Name Type Code": "5",
        "Provider First Line Business Mailing Address": "5103 CRAWFORD ST",
        "Provider Business Mailing Address City Name": "HOUSTON",
        "Provider Business Mailing Address State Name": "TX",
        "Provider Business Mailing Address Postal Code": "770045833",
        "Provider Business Mailing Address Country Code (If outside U.S.)": "US",
        "Provider Business Mailing Address Telephone Number": "7139654327",
        "Provider Business Mailing Address Fax Number": "7136362549",
        "Provider First Line Business Practice Location Address": "901 HST NE",
        "Provider Second Line Business Practice Location Address": "APT 224",
        "Provider Business Practice Location Address City Name": "WASHINGTON",
        "Provider Business Practice Location Address State Name": "DC",
        "Provider Business Practice Location Address Postal Code": "200024522",
        "Provider Business Practice Location Address Country Code (If outside U.S.)": "US",
        "Provider Business Practice Location Address Telephone Number": "7139654327",
        "Provider Business Practice Location Address Fax Number": "7136362549",
        "Provider Enumeration Date": "06/03/2009",
        "Last Update Date": "04/10/2025",
        "Provider Sex Code": "M",
        "Healthcare Provider Taxonomy Code_1": "246Y00000X",
        "Healthcare Provider Primary Taxonomy Switch_1": "Y",
        # The identifier data has been dramatically reduced under NPD, so the
        # legacy "Other (non-Medicare)" identifier is intentionally dropped.
        "Is Sole Proprietor": "Y",
        "Certification Date": "04/05/2025",
    }


def _record_1801327911() -> Dict[str, str]:
    """Organization provider, NPD managed."""
    return {
        "NPI": "1801327911",
        "Entity Type Code": "2",
        # Under V3 the EIN points at the uuid of the FHIR organization that
        # corresponds to the EIN of the legal entity, rather than the raw EIN.
        "Employer Identification Number (EIN)":
            f"{FHIR_ORG_BASE}/6f1a2c34-9b7e-4d58-8a3f-21c0de4b7a95",
        "Provider Organization Name (Legal Business Name)": "THE DOCGRAPH JOURNAL",
        "Provider First Line Business Mailing Address": "2900 WESLAYAN ST STE 555",
        "Provider Business Mailing Address City Name": "HOUSTON",
        "Provider Business Mailing Address State Name": "TX",
        "Provider Business Mailing Address Postal Code": "770275183",
        "Provider Business Mailing Address Country Code (If outside U.S.)": "US",
        "Provider Business Mailing Address Telephone Number": "7137665588",
        "Provider First Line Business Practice Location Address": "2900 WESLAYAN ST STE 555",
        "Provider Business Practice Location Address City Name": "HOUSTON",
        "Provider Business Practice Location Address State Name": "TX",
        "Provider Business Practice Location Address Postal Code": "770275183",
        "Provider Business Practice Location Address Country Code (If outside U.S.)": "US",
        "Provider Business Practice Location Address Telephone Number": "7137665588",
        "Provider Enumeration Date": "03/22/2017",
        "Last Update Date": "09/23/2020",
        "Authorized Official Last Name": "TROTTER",
        "Authorized Official First Name": "FREDERICK",
        "Authorized Official Middle Name": "CLAYTON",
        "Authorized Official Title or Position": "CTO",
        "Authorized Official Telephone Number": "7139654327",
        "Healthcare Provider Taxonomy Code_1": "247000000X",
        "Healthcare Provider Primary Taxonomy Switch_1": "Y",
        "Healthcare Provider Taxonomy Code_2": "103T00000X",
        "Healthcare Provider Primary Taxonomy Switch_2": "N",
        "Is Organization Subpart": "N",
        "Authorized Official Name Prefix Text": "MR.",
        # FaCeT normalised from "B.A., B.S, B.S" (note the de-duplication).
        "Authorized Official Credential Text": "BA | BS",
        "Healthcare Provider Taxonomy Group_1": "193200000X",
        "Healthcare Provider Taxonomy Group_2": "193200000X",
        "Certification Date": "09/23/2020",
    }


def _record_1234567893() -> Dict[str, str]:
    """
    Synthetic NPD-only provider.

    This NPI satisfies the NPI check digit algorithm but does not exist in
    NPPES, which makes it a safe way to exercise the code path where an NPI
    present in the NPD file is missing from the NPPES PUF and therefore has to
    be appended to the end of the output file.
    """
    return {
        "NPI": "1234567893",
        "Entity Type Code": "1",
        "Provider Last Name (Legal Name)": "EXAMPLE",
        "Provider First Name": "NPDONLY",
        "Provider Middle Name": "TEST",
        "Provider Credential Text": "MD | PHD",
        "Provider First Line Business Mailing Address": "7500 SECURITY BLVD",
        "Provider Business Mailing Address City Name": "BALTIMORE",
        "Provider Business Mailing Address State Name": "MD",
        "Provider Business Mailing Address Postal Code": "212441850",
        "Provider Business Mailing Address Country Code (If outside U.S.)": "US",
        "Provider Business Mailing Address Telephone Number": "4107866000",
        "Provider First Line Business Practice Location Address": "7500 SECURITY BLVD",
        "Provider Business Practice Location Address City Name": "BALTIMORE",
        "Provider Business Practice Location Address State Name": "MD",
        "Provider Business Practice Location Address Postal Code": "212441850",
        "Provider Business Practice Location Address Country Code (If outside U.S.)": "US",
        "Provider Business Practice Location Address Telephone Number": "4107866000",
        "Provider Enumeration Date": "01/15/2026",
        "Last Update Date": "01/15/2026",
        "Provider Sex Code": "F",
        "Healthcare Provider Taxonomy Code_1": "207Q00000X",
        "Provider License Number_1": "MD-000000",
        "Provider License Number State Code_1": "MD",
        "Healthcare Provider Primary Taxonomy Switch_1": "Y",
        "Is Sole Proprietor": "N",
        "Certification Date": "01/15/2026",
    }


# The NPD specific (V3) column values for each record.
NPD_V3_VALUES: Dict[str, Dict[str, str]] = {
    "1992931091": {
        "npi_activation_status": STATUS_ACTIVE,
        "npi_activation_change_reason_list": "",
        "npi_activation_future_change_date": DEFAULT_FUTURE_CHANGE_DATE,
        "npi_fhir_url": f"{FHIR_BASE}/1992931091",
    },
    "1801327911": {
        "npi_activation_status": STATUS_ACTIVE,
        "npi_activation_change_reason_list": "",
        "npi_activation_future_change_date": DEFAULT_FUTURE_CHANGE_DATE,
        "npi_fhir_url": f"{FHIR_ORG_BASE}/1801327911",
    },
    "1234567893": {
        "npi_activation_status": STATUS_ACTIVE,
        # Demonstrates the pipe delimited reason list.
        "npi_activation_change_reason_list": "Data Out of Date|Verification Required",
        "npi_activation_future_change_date": DEFAULT_FUTURE_CHANGE_DATE,
        "npi_fhir_url": f"{FHIR_BASE}/1234567893",
    },
}

RECORD_BUILDERS = [
    _record_1992931091,
    _record_1801327911,
    _record_1234567893,
]


def build_row(v3_header: List[str], values: Dict[str, str]) -> List[str]:
    """Expand a sparse {column_name: value} mapping into a full V3 row."""
    unknown = set(values) - set(v3_header)
    if unknown:
        raise KeyError(f"Unknown column name(s) for the V3 header: {sorted(unknown)}")
    return [values.get(column, "") for column in v3_header]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate the mock NPD V3 formatted NPPES PUF file.",
    )
    parser.add_argument(
        "--header-csv",
        default=str(DEFAULT_HEADER_CSV),
        help="CSV whose first row is the V2 main NPPES file header.",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="Where to write the mock NPD file.",
    )
    args = parser.parse_args()

    v2_header = read_header(args.header_csv)
    if len(v2_header) != V2_COLUMN_COUNT:
        raise ValueError(
            f"Expected {V2_COLUMN_COUNT} columns in the V2 header, "
            f"found {len(v2_header)} in {args.header_csv}"
        )
    v3_header = build_v3_header(v2_header)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, quoting=csv.QUOTE_ALL)
        writer.writerow(v3_header)

        for builder in RECORD_BUILDERS:
            values = builder()
            npi = values["NPI"]
            # Every record in the NPD file is, by definition, managed by NPD.
            values["npi_managed_by"] = MANAGED_BY_NPD
            values.update(NPD_V3_VALUES[npi])
            writer.writerow(build_row(v3_header, values))

    print(f"Wrote {len(RECORD_BUILDERS)} NPD records to {output_path}")
    print(f"V3 columns: {len(v3_header)} ({V2_COLUMN_COUNT} V2 + 5 new)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
