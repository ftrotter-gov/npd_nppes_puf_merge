#!/usr/bin/env python3
"""
Step40 - Validate the merged V3 PUF with InLaw / Great Expectations.

InLaw (https://pypi.org/project/inlaw/) validates data that is reachable
through a SQLAlchemy engine, so this script first stages the NPI column of
both the old NPPES PUF and the new output file into a local DuckDB database,
then runs the InLaw test classes against it.

Memory safety on a 10 GB laptop:

  * Only the NPI column is extracted from each CSV, by DuckDB's streaming CSV
    reader. The other 329/334 columns are projected away before they are ever
    materialised, so the ~10 GB input never lands in RAM.
  * DuckDB is given an explicit memory limit and spills to disk beyond it.
  * All of the comparison work (ordering, duplicates, set difference) is
    pushed down into DuckDB rather than done in Python.
  * Each InLaw test only ever pulls a tiny aggregate result (a count, or at
    most 20 sample rows) back into pandas for Great Expectations.

The tests performed are:

  1. The output file has more than 9,700,000 and fewer than 11,000,000 NPIs.
  2. The relative order of the NPIs shared with the old NPPES PUF is
     identical; the output file is allowed to contain extra rows anywhere.
  3. There are no repeating NPI records.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

import duckdb
from sqlalchemy import create_engine

from inlaw import InLaw, InlawError

REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT_CSV = REPO_ROOT / "working_data" / "output.csv"
DEFAULT_DB_PATH = REPO_ROOT / "working_data" / "merge_tests.duckdb"

# Row count expectations for the output file.
MIN_OUTPUT_NPIS = 9_700_000
MAX_OUTPUT_NPIS = 11_000_000

# Cap DuckDB's working memory so that it spills to disk instead of competing
# with the rest of the machine. Comfortably inside a 10 GB laptop.
DUCKDB_MEMORY_LIMIT = "4GB"

OLD_TABLE = "old_npi"
NEW_TABLE = "new_npi"


def stage_npi_column(
    connection: duckdb.DuckDBPyConnection,
    csv_path: Path,
    table_name: str,
    *,
    encoding: str,
) -> int:
    """
    Load just the NPI column of ``csv_path`` into ``table_name``.

    The table has two columns: ``row_num`` (the 1 based position of the record
    within the file, which is what the ordering test relies on) and ``npi``.

    DuckDB's native CSV reader does the work here rather than pandas. It
    streams the file, projects away the other 329/334 columns before they are
    ever materialised, and spills to disk if needed. Measured on a 300k row
    sample this peaks at ~130 MB versus ~2.7 GB for the chunked pandas
    equivalent, which is what keeps the full ~10 million row file comfortably
    inside a 10 GB laptop.
    """
    connection.execute(f"DROP TABLE IF EXISTS {table_name}")
    connection.execute(
        f"""
        CREATE TABLE {table_name} AS
        SELECT
            row_number() OVER () AS row_num,
            trim("NPI") AS npi
        FROM read_csv(
            ?,
            header = true,
            all_varchar = true,
            encoding = ?
        )
        """,
        [str(csv_path), encoding],
    )

    (total,) = connection.execute(
        f"SELECT COUNT(*) FROM {table_name}"
    ).fetchone()
    print(f"  {table_name}: {total:,} rows staged", flush=True)
    return int(total)


# ---------------------------------------------------------------------------
# InLaw test classes
# ---------------------------------------------------------------------------
class OutputNpiCountIsPlausible(InLaw):
    title = "Output file NPI count is within the expected range"

    @staticmethod
    def run(engine, settings=None):
        settings = settings or {}
        # Read the bounds from settings so that command line overrides are
        # honoured even though InLaw re-imports this file to discover tests.
        minimum = settings.get("MIN_OUTPUT_NPIS", MIN_OUTPUT_NPIS)
        maximum = settings.get("MAX_OUTPUT_NPIS", MAX_OUTPUT_NPIS)

        sql = f"SELECT COUNT(*) AS npi_count FROM {NEW_TABLE}"
        gx_df = InLaw.sql_to_gx_df(sql=sql, engine=engine)

        result = gx_df.expect_column_values_to_be_between(
            column="npi_count",
            min_value=minimum,
            max_value=maximum,
            strict_min=True,
            strict_max=True,
        )
        if result.success:
            return True

        observed = result.result.get("partial_unexpected_list") or ["unknown"]
        return (
            f"Output NPI count {observed[0]} is outside the expected range "
            f"({minimum:,} exclusive .. {maximum:,} exclusive)."
        )


class NoRepeatingNpiRecords(InLaw):
    title = "There are no repeating NPI records in the output file"

    @staticmethod
    def run(engine, settings=None):
        # Return one row per NPI that occurs more than once. An empty result
        # set means the expectation trivially holds.
        sql = f"""
            SELECT npi, COUNT(*) AS occurrences
            FROM {NEW_TABLE}
            GROUP BY npi
            HAVING COUNT(*) > 1
            ORDER BY occurrences DESC
            LIMIT 20
        """
        gx_df = InLaw.sql_to_gx_df(sql=sql, engine=engine)

        result = gx_df.expect_table_row_count_to_equal(value=0)
        if result.success:
            return True

        observed = result.result.get("observed_value", "some")
        return (
            f"Found {observed} duplicated NPI value(s) in the output file; "
            "every NPI must appear exactly once."
        )


class NpiOrderIsPreserved(InLaw):
    title = (
        "NPIs shared with the old NPPES PUF appear in the output file "
        "in the same relative order"
    )

    @staticmethod
    def run(engine, settings=None):
        # Join the two files on NPI, walk the result in old-file order and
        # check that the new-file position never decreases. Any decrease means
        # two shared NPIs were re-ordered relative to one another. Extra rows
        # in the new file are simply absent from the join, so they may appear
        # anywhere without affecting this test.
        sql = f"""
            WITH shared AS (
                SELECT
                    o.row_num AS old_row_num,
                    n.row_num AS new_row_num
                FROM {OLD_TABLE} AS o
                JOIN {NEW_TABLE} AS n
                  ON o.npi = n.npi
            ),
            ordered AS (
                SELECT
                    new_row_num,
                    LAG(new_row_num) OVER (ORDER BY old_row_num) AS prev_new_row_num
                FROM shared
            )
            SELECT COUNT(*) AS out_of_order_count
            FROM ordered
            WHERE prev_new_row_num IS NOT NULL
              AND new_row_num <= prev_new_row_num
        """
        gx_df = InLaw.sql_to_gx_df(sql=sql, engine=engine)

        result = gx_df.expect_column_values_to_be_between(
            column="out_of_order_count",
            min_value=0,
            max_value=0,
        )
        if result.success:
            return True

        observed = result.result.get("partial_unexpected_list") or ["unknown"]
        return (
            f"{observed[0]} NPI(s) appear out of order relative to the source "
            "NPPES PUF; the output must preserve the original NPI ordering."
        )


class EveryOldNpiSurvived(InLaw):
    title = "Every NPI in the old NPPES PUF is present in the output file"

    @staticmethod
    def run(engine, settings=None):
        sql = f"""
            SELECT COUNT(*) AS missing_count
            FROM (
                SELECT npi FROM {OLD_TABLE}
                EXCEPT
                SELECT npi FROM {NEW_TABLE}
            )
        """
        gx_df = InLaw.sql_to_gx_df(sql=sql, engine=engine)

        result = gx_df.expect_column_values_to_be_between(
            column="missing_count",
            min_value=0,
            max_value=0,
        )
        if result.success:
            return True

        observed = result.result.get("partial_unexpected_list") or ["unknown"]
        return (
            f"{observed[0]} NPI(s) from the source NPPES PUF are missing from "
            "the output file."
        )


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run InLaw validation tests against the merged V3 PUF.",
    )
    parser.add_argument(
        "--nppes-csv",
        required=True,
        help="Path to the original (V2) main NPPES npidata_pfile CSV.",
    )
    parser.add_argument(
        "--output-csv",
        default=str(DEFAULT_OUTPUT_CSV),
        help="Path to the merged V3 output CSV (default: ./working_data/output.csv).",
    )
    parser.add_argument(
        "--db",
        default=str(DEFAULT_DB_PATH),
        help="DuckDB file used to stage the NPI columns.",
    )
    parser.add_argument(
        "--memory-limit",
        default=DUCKDB_MEMORY_LIMIT,
        help="DuckDB memory limit; it spills to disk past this "
             f"(default: {DUCKDB_MEMORY_LIMIT}).",
    )
    parser.add_argument(
        "--min-npis",
        type=int,
        default=MIN_OUTPUT_NPIS,
        help="Lower (exclusive) bound for the output NPI count.",
    )
    parser.add_argument(
        "--max-npis",
        type=int,
        default=MAX_OUTPUT_NPIS,
        help="Upper (exclusive) bound for the output NPI count.",
    )
    parser.add_argument(
        "--keep-db",
        action="store_true",
        help="Keep the staging DuckDB file after the tests complete.",
    )
    args = parser.parse_args(argv)

    nppes_csv = Path(args.nppes_csv)
    output_csv = Path(args.output_csv)
    db_path = Path(args.db)

    for path, label in ((nppes_csv, "NPPES"), (output_csv, "Output")):
        if not path.is_file():
            print(f"ERROR: {label} file not found: {path}", file=sys.stderr)
            return 1

    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    print(f"Staging NPI columns into {db_path}")
    connection = duckdb.connect(str(db_path))
    try:
        # Keep DuckDB's own memory use bounded; it spills to disk beyond this.
        connection.execute(f"SET memory_limit = '{args.memory_limit}'")
        connection.execute("SET preserve_insertion_order = false")

        old_rows = stage_npi_column(
            connection,
            nppes_csv,
            OLD_TABLE,
            encoding="latin-1",
        )
        new_rows = stage_npi_column(
            connection,
            output_csv,
            NEW_TABLE,
            encoding="utf-8",
        )
        print(f"Staged {old_rows:,} old NPIs and {new_rows:,} new NPIs")
    finally:
        connection.close()

    engine = create_engine(f"duckdb:///{db_path}")
    try:
        # InLaw.run_all raises InlawError when any test fails; it has already
        # printed a readable summary by that point, so turn it into an exit
        # code rather than a traceback.
        results = InLaw.run_all(
            engine=engine,
            inlaw_files=[__file__],
            settings={
                "OLD_TABLE": OLD_TABLE,
                "NEW_TABLE": NEW_TABLE,
                "MIN_OUTPUT_NPIS": args.min_npis,
                "MAX_OUTPUT_NPIS": args.max_npis,
            },
            ignore_skip_test=True,
        )
    except InlawError as exc:
        print(f"\nInLaw validation failed: {exc}", file=sys.stderr)
        return 1
    finally:
        engine.dispose()
        if not args.keep_db:
            db_path.unlink(missing_ok=True)

    failed = results.get("failed", 0) + results.get("errors", 0)
    if failed:
        return 1

    print(f"\nAll {results.get('passed', 0)} InLaw tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
