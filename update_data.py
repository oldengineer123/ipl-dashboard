#!/usr/bin/env python3
"""
Refresh IPL data from Cricsheet and rebuild all derived tables and the dashboard.

Run this whenever you want the dashboard to show the latest matches.
Cricsheet typically posts new IPL match data within 24 hours of a match
finishing.

What this does, in order:

  1. Downloads the latest IPL ball-by-ball JSONs from cricsheet.org
     (~30 MB zip). New matches get added; existing matches are
     overwritten in case Cricsheet corrects anything.
  2. Runs parse_cricsheet.py       (raw tables from JSON)
  3. Runs clean_venues.py          (team merges, venue+city cleanup)
  4. Runs build_innings_tables.py  (batter/bowler innings derived tables)
  5. Runs build_dashboard.py       (regenerates dashboard.html)

Stdlib only. Works with the Python that ships with macOS.

Usage:
    python3 update_data.py
"""

import io
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path


CRICSHEET_URL = "https://cricsheet.org/downloads/ipl_json.zip"


def fetch_zip(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Macintosh)"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read()


def main():
    here = Path(__file__).resolve().parent
    build_dir = here / "build"
    build_dir.mkdir(exist_ok=True)
    dashboard_path = here / "dashboard.html"

    print(f"Refreshing IPL data in: {here}\n")

    # ---- 1. Download ---------------------------------------------------------
    print(f"Step 1/5  Downloading {CRICSHEET_URL}")
    t0 = time.time()
    try:
        zbytes = fetch_zip(CRICSHEET_URL)
    except Exception as exc:
        print(f"\n  Download failed: {exc}")
        print(f"  If the URL has changed, visit https://cricsheet.org/downloads/")
        print(f"  and update CRICSHEET_URL at the top of this script.")
        sys.exit(1)
    print(f"          Got {len(zbytes) / 1024 / 1024:.1f} MB in {time.time()-t0:.1f}s")

    # ---- 2. Extract JSON files -----------------------------------------------
    print("\nStep 2/5  Extracting match JSONs")
    added = updated = skipped = 0
    with zipfile.ZipFile(io.BytesIO(zbytes)) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = Path(info.filename).name      # flatten any subfolders
            if not name.endswith(".json"):
                skipped += 1
                continue
            out = here / name
            existed = out.exists()
            with zf.open(info) as src, open(out, "wb") as dst:
                dst.write(src.read())
            if existed:
                updated += 1
            else:
                added += 1
    print(f"          {added} new match(es), {updated} updated, {skipped} non-JSON files skipped")

    # ---- 3-5. Pipeline -------------------------------------------------------
    steps = [
        ("parse_cricsheet.py",      [str(here / "parse_cricsheet.py"),      str(here)]),
        ("clean_venues.py",         [str(here / "clean_venues.py"),         str(build_dir)]),
        ("build_innings_tables.py", [str(here / "build_innings_tables.py"), str(build_dir)]),
        ("build_dashboard.py",      [str(here / "build_dashboard.py"),      str(build_dir), str(dashboard_path)]),
    ]
    for i, (name, args) in enumerate(steps, start=3):
        print(f"\nStep {i}/5  {name}")
        result = subprocess.run([sys.executable] + args)
        if result.returncode != 0:
            print(f"\n  {name} failed (exit {result.returncode}). Stopping.")
            sys.exit(1)

    print(f"\nDone.  Open dashboard.html to see the refreshed data:")
    print(f"   {dashboard_path}")


if __name__ == "__main__":
    main()
