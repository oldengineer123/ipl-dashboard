#!/usr/bin/env python3
"""
IPL Dashboard — Asset Downloader
Run this once on your machine before building the dashboard:

    python3 download_assets.py

What it does:
  1. Downloads all 15 IPL team logos (current + defunct) from Wikimedia and saves
     them as base64 data-URIs in assets/team_logos.json
  2. Downloads the Cricsheet player register (people.csv), which maps the hex player
     IDs used in the match JSONs to ESPNCricinfo numeric player IDs
  3. Writes assets/player_cricinfo_ids.json  (player_name -> cricinfo_id)

After running this, rebuild the dashboard:
    python3 build_dashboard.py
"""

import os, csv, json, time, base64, urllib.request, urllib.error
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
ASSETS_DIR = SCRIPT_DIR / "assets"
LOGOS_DIR  = ASSETS_DIR / "logos"
ASSETS_DIR.mkdir(exist_ok=True)
LOGOS_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Team logos — Wikimedia direct file URLs
# ---------------------------------------------------------------------------
TEAM_LOGO_URLS = {
    "Chennai Super Kings":
        "https://upload.wikimedia.org/wikipedia/en/2/2b/Chennai_Super_Kings_Logo.svg",
    "Mumbai Indians":
        "https://upload.wikimedia.org/wikipedia/en/c/cd/Mumbai_Indians_Logo.svg",
    "Royal Challengers Bengaluru":
        "https://upload.wikimedia.org/wikipedia/en/2/2a/Royal_Challengers_Bangalore_2020.svg",
    "Kolkata Knight Riders":
        "https://upload.wikimedia.org/wikipedia/en/4/4c/Kolkata_Knight_Riders_Logo.svg",
    "Sunrisers Hyderabad":
        "https://upload.wikimedia.org/wikipedia/en/3/3f/Sunrisers_Hyderabad.svg",
    "Delhi Capitals":
        "https://upload.wikimedia.org/wikipedia/en/f/f5/Delhi_Capitals_Logo.svg",
    "Punjab Kings":
        "https://upload.wikimedia.org/wikipedia/en/d/d4/Punjab_Kings_Logo.svg",
    "Rajasthan Royals":
        "https://upload.wikimedia.org/wikipedia/en/6/60/Rajasthan_Royals_Logo.svg",
    "Gujarat Titans":
        "https://upload.wikimedia.org/wikipedia/en/0/09/Gujarat_Titans_Logo.svg",
    "Lucknow Super Giants":
        "https://upload.wikimedia.org/wikipedia/en/a/a9/Lucknow_Super_Giants_Logo.svg",
    "Deccan Chargers":
        "https://upload.wikimedia.org/wikipedia/en/7/7e/Deccan_Chargers.svg",
    "Rising Pune Supergiants":
        "https://upload.wikimedia.org/wikipedia/en/5/5e/Rising_Pune_Supergiants_Logo.svg",
    "Gujarat Lions":
        "https://upload.wikimedia.org/wikipedia/en/0/07/Gujarat_Lions_Logo.svg",
    "Kochi Tuskers Kerala":
        "https://upload.wikimedia.org/wikipedia/en/e/e9/Kochi_Tuskers.svg",
    "Pune Warriors":
        "https://upload.wikimedia.org/wikipedia/en/d/da/Pune_Warriors_India.svg",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Referer": "https://en.wikipedia.org/",
}


def fetch_url(url: str, timeout: int = 20) -> bytes:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


# ---------------------------------------------------------------------------
# Step 1: Download team logos
# ---------------------------------------------------------------------------
def download_logos() -> dict:
    print("\n── Downloading team logos ──────────────────────────")
    result: dict[str, str] = {}

    for team, url in TEAM_LOGO_URLS.items():
        ext  = url.rsplit(".", 1)[-1].lower()   # svg or png
        slug = team.replace(" ", "_").replace("/", "_")
        path = LOGOS_DIR / f"{slug}.{ext}"

        if path.exists():
            data = path.read_bytes()
            print(f"  [cached]  {team}")
        else:
            try:
                data = fetch_url(url)
                path.write_bytes(data)
                print(f"  [ok]      {team}  ({len(data):,} bytes)")
                time.sleep(0.25)           # be polite
            except Exception as exc:
                print(f"  [FAIL]    {team}: {exc}")
                continue

        mime = "image/svg+xml" if ext == "svg" else "image/png"
        result[team] = f"data:{mime};base64,{base64.b64encode(data).decode()}"

    return result


# ---------------------------------------------------------------------------
# Step 2: Download Cricsheet people.csv  (hex ID → Cricinfo numeric ID)
# ---------------------------------------------------------------------------
PEOPLE_CSV_URL = "https://cricsheet.org/register/people.csv"

def download_people_csv() -> Path:
    path = ASSETS_DIR / "people.csv"
    if path.exists():
        print(f"\n  [cached]  people.csv")
        return path
    print("\n── Downloading Cricsheet people.csv ────────────────")
    try:
        data = fetch_url(PEOPLE_CSV_URL, timeout=30)
        path.write_bytes(data)
        print(f"  [ok]      people.csv  ({len(data):,} bytes)")
    except Exception as exc:
        print(f"  [FAIL]    people.csv: {exc}")
        print("  → You can download it manually from https://cricsheet.org/register/")
        print(f"    and place it at: {path}")
    return path


def build_player_cricinfo_map(people_csv: Path) -> dict:
    """Returns {player_name: cricinfo_id (int)} for all players in build/players.csv."""
    if not people_csv.exists():
        return {}

    # Parse people.csv — key columns vary by version; try both naming conventions
    cricsheet_to_cricinfo: dict[str, str] = {}
    with open(people_csv, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        cols = reader.fieldnames or []
        # Column that holds the Cricinfo ID differs across versions
        cricinfo_col = next(
            (c for c in ["cricinfo", "key_cricinfo", "identifier_cricinfo"] if c in cols),
            None
        )
        # Column that holds the Cricsheet hex ID
        id_col = next(
            (c for c in ["identifier", "key", "unique_name"] if c in cols),
            None
        )
        if not cricinfo_col or not id_col:
            print(f"  [warn]  Cannot find expected columns in people.csv. Cols: {cols}")
            return {}

        for row in reader:
            hex_id    = (row.get(id_col) or "").strip()
            cricinfo  = (row.get(cricinfo_col) or "").strip()
            if hex_id and cricinfo and cricinfo.isdigit():
                cricsheet_to_cricinfo[hex_id] = cricinfo

    print(f"  Loaded {len(cricsheet_to_cricinfo):,} Cricinfo ID mappings from people.csv")

    # Now map our player names using build/players.csv (which has hex IDs)
    players_csv = SCRIPT_DIR / "build" / "players.csv"
    if not players_csv.exists():
        print(f"  [warn]  {players_csv} not found — skipping player ID mapping")
        return {}

    name_to_cricinfo: dict[str, int] = {}
    unmatched = []
    with open(players_csv, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            hex_id = row["player_id"]
            name   = row["player_name"]
            cid    = cricsheet_to_cricinfo.get(hex_id, "")
            if cid:
                name_to_cricinfo[name] = int(cid)
            else:
                unmatched.append(name)

    print(f"  Matched {len(name_to_cricinfo):,} / "
          f"{len(name_to_cricinfo) + len(unmatched):,} players to Cricinfo IDs")
    if unmatched:
        print(f"  Unmatched ({len(unmatched)}): {', '.join(unmatched[:10])}"
              + (" …" if len(unmatched) > 10 else ""))

    return name_to_cricinfo


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("IPL Dashboard — Asset Downloader")
    print("=" * 50)

    logos          = download_logos()
    logos_out      = ASSETS_DIR / "team_logos.json"
    logos_out.write_text(json.dumps(logos, separators=(",", ":")))
    print(f"\n  Saved {len(logos)} team logos → {logos_out}")

    people_csv    = download_people_csv()
    cricinfo_map  = build_player_cricinfo_map(people_csv)
    ids_out       = ASSETS_DIR / "player_cricinfo_ids.json"
    ids_out.write_text(json.dumps(cricinfo_map, separators=(",", ":")))
    print(f"  Saved {len(cricinfo_map)} player IDs → {ids_out}")

    print("\n✓ Done!  Now run:  python3 build_dashboard.py\n")


if __name__ == "__main__":
    main()
