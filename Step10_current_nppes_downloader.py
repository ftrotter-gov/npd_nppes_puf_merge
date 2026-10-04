#!/usr/bin/env python3
"""
Step10 - Download the current monthly NPPES data dissemination file.

Scrapes https://download.cms.gov/nppes/NPI_Files.html looking for the monthly
V2 zip, whose href looks like:

    ./NPPES_Data_Dissemination_September_2026_V2.zip

The file is streamed into ./working_data/ and then unzipped in place. The zip
is roughly 1.1 GB and expands to roughly 10 GB, so everything is streamed and
nothing is held in memory.

Care is taken not to confuse the monthly file with the other links on the page:

    NPPES_Data_Dissemination_090726_091326_Weekly_V2.zip   (weekly update)
    NPPES_Deactivated_NPI_Report_091426_V2.zip             (deactivation report)
"""
from __future__ import annotations

import argparse
import re
import sys
import zipfile
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

NPPES_FILES_URL = "https://download.cms.gov/nppes/NPI_Files.html"

# The anchor id CMS uses for the monthly dissemination zip.
MONTHLY_ANCHOR_ID = "DDSMTH.ZIP.D"

# NPPES_Data_Dissemination_<Month>_<Year>_V<n>.zip
MONTHLY_ZIP_RE = re.compile(
    r"NPPES_Data_Dissemination_"
    r"(?P<month>January|February|March|April|May|June|July|August|September|"
    r"October|November|December)_"
    r"(?P<year>\d{4})_V(?P<version>\d+)\.zip$",
    re.IGNORECASE,
)

DEFAULT_WORKING_DIR = Path(__file__).resolve().parent / "working_data"

CHUNK_SIZE = 1024 * 1024  # 1 MiB
USER_AGENT = (
    "npd-nppes-puf-merge/1.0 "
    "(+https://github.com/ftrotter-gov/npd_nppes_puf_merge)"
)


def find_monthly_zip_url(page_url: str = NPPES_FILES_URL, *, timeout: int = 60) -> str:
    """Return the absolute URL of the current monthly NPPES dissemination zip."""
    response = requests.get(page_url, timeout=timeout, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    candidates: List[Tuple[int, str]] = []
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        if not MONTHLY_ZIP_RE.search(href):
            continue
        # Skip the weekly and deactivation files. They never match the
        # Month_Year pattern, but be defensive anyway.
        if "weekly" in href.lower() or "deactivated" in href.lower():
            continue

        # Prefer the anchor that CMS tags as the monthly download.
        priority = 0 if anchor.get("id") == MONTHLY_ANCHOR_ID else 1
        candidates.append((priority, urljoin(page_url, href)))

    if not candidates:
        raise RuntimeError(
            f"Could not find a monthly NPPES dissemination zip link on {page_url}. "
            "The page layout may have changed."
        )

    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


def download_file(url: str, destination: Path, *, skip_if_exists: bool = True) -> Path:
    """Stream ``url`` to ``destination``, showing simple progress."""
    if skip_if_exists and destination.exists() and destination.stat().st_size > 0:
        size_mb = destination.stat().st_size / 1024 / 1024
        print(f"Already downloaded, skipping: {destination} ({size_mb:,.1f} MB)")
        return destination

    destination.parent.mkdir(parents=True, exist_ok=True)
    # Download to a temporary name so an interrupted run cannot leave a
    # truncated file behind that looks complete.
    partial = destination.with_suffix(destination.suffix + ".part")

    print(f"Downloading {url}")
    print(f"         to {destination}")

    with requests.get(
        url, stream=True, timeout=(30, 300), headers={"User-Agent": USER_AGENT}
    ) as response:
        response.raise_for_status()
        total = int(response.headers.get("Content-Length", 0))
        written = 0
        last_report = 0.0

        with open(partial, "wb") as handle:
            for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                if not chunk:
                    continue
                handle.write(chunk)
                written += len(chunk)

                megabytes = written / 1024 / 1024
                if megabytes - last_report >= 50:
                    last_report = megabytes
                    if total:
                        pct = written / total * 100
                        print(
                            f"  {megabytes:,.0f} MB / {total / 1024 / 1024:,.0f} MB"
                            f" ({pct:.1f}%)",
                            flush=True,
                        )
                    else:
                        print(f"  {megabytes:,.0f} MB", flush=True)

    if total and written != total:
        partial.unlink(missing_ok=True)
        raise IOError(
            f"Download incomplete: expected {total} bytes but received {written}"
        )

    partial.replace(destination)
    print(f"Downloaded {written / 1024 / 1024:,.1f} MB")
    return destination


def unzip_file(zip_path: Path, extract_dir: Path) -> List[Path]:
    """Extract ``zip_path`` into ``extract_dir``, returning the member paths."""
    extract_dir.mkdir(parents=True, exist_ok=True)
    extracted: List[Path] = []
    resolved_root = extract_dir.resolve()

    print(f"Unzipping {zip_path.name} into {extract_dir}")
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            # Guard against path traversal in the archive.
            target = (extract_dir / member.filename).resolve()
            if not str(target).startswith(str(resolved_root)):
                raise RuntimeError(f"Unsafe path in zip archive: {member.filename}")

            archive.extract(member, path=extract_dir)
            extracted.append(extract_dir / member.filename)
            print(f"  {member.filename} ({member.file_size / 1024 / 1024:,.1f} MB)")

    return extracted


def find_main_data_file(extract_dir: Path) -> Optional[Path]:
    """
    Locate the main npidata_pfile CSV among the extracted files.

    The archive also contains a ``..._fileheader.csv`` for each data file,
    which must not be mistaken for the data itself.
    """
    candidates = [
        path
        for path in extract_dir.glob("npidata_pfile_*.csv")
        if "fileheader" not in path.name.lower()
    ]
    if not candidates:
        return None
    # If several exist, take the largest, which is the real data file.
    return max(candidates, key=lambda path: path.stat().st_size)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Download and unzip the current monthly NPPES dissemination file.",
    )
    parser.add_argument(
        "--working-dir",
        default=str(DEFAULT_WORKING_DIR),
        help="Directory to download into and unzip within (default: ./working_data).",
    )
    parser.add_argument(
        "--url",
        default=None,
        help="Download a specific zip URL instead of scraping the CMS listing page.",
    )
    parser.add_argument(
        "--page-url",
        default=NPPES_FILES_URL,
        help=f"The CMS listing page to scrape (default: {NPPES_FILES_URL}).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download even if the zip is already present.",
    )
    parser.add_argument(
        "--no-unzip",
        action="store_true",
        help="Download the zip but do not extract it.",
    )
    parser.add_argument(
        "--url-only",
        action="store_true",
        help="Print the resolved download URL and exit without downloading.",
    )
    args = parser.parse_args(argv)

    working_dir = Path(args.working_dir).resolve()

    zip_url = args.url or find_monthly_zip_url(args.page_url)
    print(f"Monthly NPPES zip: {zip_url}")

    if args.url_only:
        return 0

    zip_name = zip_url.rsplit("/", 1)[-1]
    zip_path = working_dir / zip_name

    download_file(zip_url, zip_path, skip_if_exists=not args.force)

    if args.no_unzip:
        print(f"ZIP_PATH={zip_path}")
        return 0

    unzip_file(zip_path, working_dir)

    main_csv = find_main_data_file(working_dir)
    if main_csv is None:
        print(
            "WARNING: could not locate an npidata_pfile_*.csv in the extracted files.",
            file=sys.stderr,
        )
    else:
        print(f"Main NPPES data file: {main_csv}")

    # Emit machine readable results for go.py to consume.
    print(f"ZIP_PATH={zip_path}")
    if main_csv is not None:
        print(f"MAIN_CSV={main_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
