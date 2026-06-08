#!/usr/bin/env python3
"""Download NHAMCS ED public-use Stata files (2018–2022)."""

from __future__ import annotations

import argparse
import zipfile
from pathlib import Path
from urllib.request import urlretrieve

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "nhamcs"

# CDC FTP paths (Stata bundles per survey year).
_YEAR_URLS = {
    2018: "https://ftp.cdc.gov/pub/Health_Statistics/NCHS/dataset_documentation/nhamcs/stata/ed2018-stata.zip",
    2019: "https://ftp.cdc.gov/pub/Health_Statistics/NCHS/dataset_documentation/nhamcs/stata/ed2019-stata.zip",
    2020: "https://ftp.cdc.gov/pub/Health_Statistics/NCHS/dataset_documentation/nhamcs/stata/ed2020-stata.zip",
    2021: "https://ftp.cdc.gov/pub/Health_Statistics/NCHS/dataset_documentation/nhamcs/stata/ed2021-stata.zip",
    2022: "https://ftp.cdc.gov/pub/Health_Statistics/NCHS/dataset_documentation/nhamcs/stata/ed2022-stata.zip",
}


def download_year(year: int, dest_dir: Path) -> Path:
    """Download and unzip one NHAMCS ED Stata year."""
    url = _YEAR_URLS[year]
    zip_path = dest_dir / f"ed{year}-stata.zip"
    dta_path = dest_dir / f"ed{year}-stata.dta"
    if dta_path.exists():
        print(f"  {year}: already have {dta_path.name}")
        return dta_path

    print(f"  {year}: downloading {url}")
    dest_dir.mkdir(parents=True, exist_ok=True)
    urlretrieve(url, zip_path)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(dest_dir)
    if not dta_path.exists():
        # Some zips extract to subfolder
        candidates = list(dest_dir.glob(f"*{year}*.dta"))
        if len(candidates) == 1:
            candidates[0].rename(dta_path)
    print(f"  {year}: extracted {dta_path.name}")
    return dta_path


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Download NHAMCS ED Stata files")
    parser.add_argument(
        "--years",
        type=str,
        default="2022",
        help="Comma-separated years (2018-2022), default 2022 only",
    )
    args = parser.parse_args()
    years = [int(y.strip()) for y in args.years.split(",")]
    for year in years:
        if year not in _YEAR_URLS:
            raise SystemExit(f"Unsupported year: {year}")
        download_year(year, OUT_DIR)
    print("Done. Run: python scripts/build_rvc_codebook.py")


if __name__ == "__main__":
    main()
