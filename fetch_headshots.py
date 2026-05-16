#!/usr/bin/env python3
"""
IPL Dashboard — headshot fetcher via Wikimedia Commons

Searches Wikimedia Commons file namespace directly for each player's full name.
Commons has a large, freely licensed collection of cricket player photos.

Run once, then rebuild:
    python3 fetch_headshots.py
    python3 build_dashboard.py build/ dashboard.html
"""

import json, re, time, urllib.request, urllib.parse
from pathlib import Path

SCRIPT_DIR   = Path(__file__).parent
ASSETS_DIR   = SCRIPT_DIR / "assets"

COMMONS_API  = "https://commons.wikimedia.org/w/api.php"
HEADERS      = {"User-Agent": "IPLDashboard/1.0 (personal cricket stats project)"}
THUMB_SIZE   = 300
SLEEP        = 0.4

# File types to accept
IMAGE_EXTS   = {".jpg", ".jpeg", ".png", ".webp"}
# Patterns that suggest it's NOT a portrait (jersey, kit, stadium, logo, flag…)
REJECT_WORDS = {"logo", "flag", "kit", "jersey", "shirt", "stadium", "ground",
                "trophy", "bat", "ball", "helmet", "cap", "jersey", "emblem",
                "field", "pitch", "map", "signature", "autograph", "wicket"}


def api_get(params: dict) -> dict:
    params["format"] = "json"
    url = COMMONS_API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=12) as r:
        return json.loads(r.read())


def is_likely_portrait(title: str) -> bool:
    """Heuristic: reject files that are clearly not player portraits."""
    t = title.lower()
    ext = "." + t.rsplit(".", 1)[-1] if "." in t else ""
    if ext not in IMAGE_EXTS:
        return False
    words = set(re.split(r"[\s_\-\.]+", t))
    return not words & REJECT_WORDS


def search_commons(full_name: str) -> str | None:
    """Search Wikimedia Commons file namespace for a player photo."""
    queries = [
        f"{full_name} cricketer",
        f"{full_name} cricket",
        f"{full_name} IPL",
        full_name,
    ]

    for query in queries:
        try:
            # generator=search over file namespace, with imageinfo in one call
            d = api_get({
                "action":      "query",
                "generator":   "search",
                "gsrsearch":   query,
                "gsrnamespace": 6,        # 6 = File namespace
                "gsrlimit":    10,
                "prop":        "imageinfo",
                "iiprop":      "url|mime",
                "iiurlwidth":  THUMB_SIZE,
            })
            pages = d.get("query", {}).get("pages", {})
            if not pages:
                time.sleep(SLEEP)
                continue

            for pg in pages.values():
                title = pg.get("title", "")
                ii    = pg.get("imageinfo", [{}])[0]
                mime  = ii.get("mime", "")
                thumb = ii.get("thumburl") or ii.get("url", "")

                # Accept only images, skip obvious non-portraits
                if not mime.startswith("image/"):
                    continue
                if not is_likely_portrait(title):
                    continue
                if thumb:
                    return thumb

        except Exception:
            pass
        time.sleep(SLEEP)

    return None


def main():
    ids_path = ASSETS_DIR / "player_cricinfo_ids.json"
    if not ids_path.exists():
        print("ERROR: assets/player_cricinfo_ids.json not found. Run download_assets.py first.")
        return
    cricinfo_map: dict[str, int] = json.loads(ids_path.read_text())

    fullnames_path = ASSETS_DIR / "player_fullnames.json"
    fullnames_map: dict[str, str] = {}
    if fullnames_path.exists():
        fullnames_map = json.loads(fullnames_path.read_text())

    all_abbrev = sorted(cricinfo_map.keys())

    headshots_path = ASSETS_DIR / "player_headshots.json"
    headshots: dict[str, str] = {}
    if headshots_path.exists():
        existing = json.loads(headshots_path.read_text())
        print(f"Found existing player_headshots.json ({len(existing)} entries).")
        ans = input("Re-fetch all (Y) or resume/skip already-fetched (n)? [Y/n]: ").strip().lower()
        headshots = {} if ans not in ("n", "no") else existing
        print("Starting fresh.\n" if not headshots else f"Resuming — {len(headshots)} cached.\n")

    total = len(all_abbrev)
    fetched = skipped = missed = 0

    print(f"Searching Wikimedia Commons for {total} players …\n")

    for i, abbrev in enumerate(all_abbrev, 1):
        if abbrev in headshots:
            skipped += 1
            continue

        full_name = fullnames_map.get(abbrev, abbrev)
        photo_url = search_commons(full_name)

        if photo_url:
            headshots[abbrev] = photo_url
            fetched += 1
            print(f"  [{i:>3}/{total}] ✓  {full_name}")
        else:
            missed += 1
            print(f"  [{i:>3}/{total}] –  {full_name}")

        headshots_path.write_text(json.dumps(headshots, ensure_ascii=False, indent=2))

    print(f"\n── Summary ─────────────────────────────────────────")
    print(f"  Photos found:  {fetched}")
    print(f"  No photo:      {missed}")
    print(f"  Already had:   {skipped}")
    print(f"  Total:         {total}")
    print(f"\n  Saved → {headshots_path}")
    print(f"\nNow rebuild:")
    print(f"  python3 build_dashboard.py build/ dashboard.html\n")


if __name__ == "__main__":
    main()
