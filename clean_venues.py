#!/usr/bin/env python3
"""
Data cleanup pass for the IPL tables produced by parse_cricsheet.py.

What it does:

  1. Collapses duplicate spellings of the same physical ground onto a
     canonical name.
  2. Treats well-known venue renames as the same place:
       - Feroz Shah Kotla              -> Arun Jaitley Stadium      (Delhi, 2019)
       - Sardar Patel Stadium, Motera  -> Narendra Modi Stadium     (Ahmedabad, 2020)
       - Subrata Roy Sahara Stadium    -> Maharashtra Cricket Assoc.(Pune, 2016)
  3. Fills missing city values for the two overseas grounds without one
     (Dubai International Cricket Stadium, Sharjah Cricket Stadium).
  4. Standardises a few city spellings where merged variants disagreed
     (e.g. Bangalore/Bengaluru -> Bengaluru on Chinnaswamy).
  5. Appends ", <city>" to every venue name that doesn't already contain
     the city, so the venue list is consistently searchable.
  6. Consolidates duplicate team names:
       - Royal Challengers Bangalore  -> Royal Challengers Bengaluru   (rebrand, 2024)
       - Kings XI Punjab              -> Punjab Kings                  (rebrand, 2021)
       - Rising Pune Supergiant       -> Rising Pune Supergiants       (singular->plural)
  7. Rebuilds grounds.csv from the cleaned tables.

After this runs, regenerate the derived per-innings tables and the
dashboard so they pick up the new names:
    python3 build_innings_tables.py <build_dir>
    python3 build_dashboard.py       <build_dir> dashboard.html

Idempotent: safe to re-run. Originals can be regenerated any time by
re-running parse_cricsheet.py.

Usage:
    python3 clean_venues.py <build_dir>
"""

import argparse
import csv
import os
import sys
from collections import defaultdict
from pathlib import Path


# ---- Venue alias map (variant -> canonical short form) -----------------------
VENUE_ALIASES = {
    # Abu Dhabi
    "Zayed Cricket Stadium, Abu Dhabi": "Sheikh Zayed Stadium",

    # Ahmedabad
    "Sardar Patel Stadium, Motera":     "Narendra Modi Stadium",
    "Narendra Modi Stadium, Ahmedabad": "Narendra Modi Stadium",

    # Bengaluru
    "M Chinnaswamy Stadium, Bengaluru": "M Chinnaswamy Stadium",
    "M.Chinnaswamy Stadium":            "M Chinnaswamy Stadium",

    # Mohali / Chandigarh
    "Punjab Cricket Association IS Bindra Stadium, Mohali":             "Punjab Cricket Association IS Bindra Stadium",
    "Punjab Cricket Association IS Bindra Stadium, Mohali, Chandigarh": "Punjab Cricket Association IS Bindra Stadium",
    "Punjab Cricket Association Stadium, Mohali":                       "Punjab Cricket Association IS Bindra Stadium",

    # Chennai
    "MA Chidambaram Stadium, Chepauk":          "MA Chidambaram Stadium",
    "MA Chidambaram Stadium, Chepauk, Chennai": "MA Chidambaram Stadium",

    # Delhi
    "Feroz Shah Kotla":            "Arun Jaitley Stadium",
    "Arun Jaitley Stadium, Delhi": "Arun Jaitley Stadium",

    # Dharamsala
    "Himachal Pradesh Cricket Association Stadium, Dharamsala":
        "Himachal Pradesh Cricket Association Stadium",

    # Hyderabad
    "Rajiv Gandhi International Stadium, Uppal":            "Rajiv Gandhi International Stadium",
    "Rajiv Gandhi International Stadium, Uppal, Hyderabad": "Rajiv Gandhi International Stadium",

    # Jaipur
    "Sawai Mansingh Stadium, Jaipur": "Sawai Mansingh Stadium",

    # Kolkata
    "Eden Gardens, Kolkata": "Eden Gardens",

    # Mumbai
    "Brabourne Stadium, Mumbai": "Brabourne Stadium",
    "Wankhede Stadium, Mumbai":  "Wankhede Stadium",

    # Navi Mumbai
    "Dr DY Patil Sports Academy, Mumbai": "Dr DY Patil Sports Academy",

    # New Chandigarh
    "Maharaja Yadavindra Singh International Cricket Stadium, Mullanpur":
        "Maharaja Yadavindra Singh International Cricket Stadium",
    "Maharaja Yadavindra Singh International Cricket Stadium, New Chandigarh":
        "Maharaja Yadavindra Singh International Cricket Stadium",

    # Pune
    "Maharashtra Cricket Association Stadium, Pune": "Maharashtra Cricket Association Stadium",
    "Subrata Roy Sahara Stadium":                    "Maharashtra Cricket Association Stadium",

    # Raipur
    "Shaheed Veer Narayan Singh International Stadium, Raipur":
        "Shaheed Veer Narayan Singh International Stadium",

    # Visakhapatnam
    "Dr. Y.S. Rajasekhara Reddy ACA-VDCA Cricket Stadium, Visakhapatnam":
        "Dr. Y.S. Rajasekhara Reddy ACA-VDCA Cricket Stadium",

    # Nagpur (strip the "Jamtha" suffix; we'll append ", Nagpur" via city)
    "Vidarbha Cricket Association Stadium, Jamtha":
        "Vidarbha Cricket Association Stadium",
}


# Filled in only when the raw city is empty.
VENUE_CITY_FILL = {
    "Dubai International Cricket Stadium": "Dubai",
    "Sharjah Cricket Stadium":             "Sharjah",
}

# Always force this city for the given canonical venue.
CANONICAL_CITY = {
    "M Chinnaswamy Stadium":                                   "Bengaluru",
    "Dr DY Patil Sports Academy":                              "Navi Mumbai",
    "Punjab Cricket Association IS Bindra Stadium":            "Chandigarh",
    "Maharaja Yadavindra Singh International Cricket Stadium": "New Chandigarh",
}


# ---- Team alias map (variant -> canonical) -----------------------------------
TEAM_ALIASES = {
    "Royal Challengers Bangalore": "Royal Challengers Bengaluru",  # rebrand, 2024
    "Kings XI Punjab":             "Punjab Kings",                 # rebrand, 2021
    "Rising Pune Supergiant":      "Rising Pune Supergiants",      # 2017 dropped 's'
    "Delhi Daredevils":            "Delhi Capitals",               # rebrand, 2019
}


def canonicalize_team(team):
    if not team:
        return team
    return TEAM_ALIASES.get(team, team)


def canonicalize_venue(venue, city):
    """Alias-collapse the venue, fill / override its city, then append ', <city>'
    to the venue name when the city isn't already part of the name."""
    if not venue:
        return venue, city
    venue = VENUE_ALIASES.get(venue, venue)
    if not city:
        city = VENUE_CITY_FILL.get(venue, city)
    city = CANONICAL_CITY.get(venue, city)
    if city and city.lower() not in venue.lower():
        venue = f"{venue}, {city}"
    return venue, city


def rewrite_csv(path, team_fields=(), team_list_fields=(),
                venue_field=None, city_field=None):
    """Stream-rewrite a CSV applying the canonicalization rules."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    rows_total = 0
    rows_touched = 0
    with open(path) as fin, open(tmp, "w", newline="") as fout:
        reader = csv.DictReader(fin)
        writer = csv.DictWriter(fout, fieldnames=reader.fieldnames)
        writer.writeheader()
        for row in reader:
            rows_total += 1
            touched = False

            # Plain team-name fields
            for f in team_fields:
                if f in row and row[f]:
                    new = canonicalize_team(row[f])
                    if new != row[f]:
                        row[f] = new
                        touched = True

            # Semicolon-separated team list fields (e.g. players.csv teams_played_for)
            for f in team_list_fields:
                if f in row and row[f]:
                    parts = [p.strip() for p in row[f].split(";") if p.strip()]
                    new_parts = [canonicalize_team(p) for p in parts]
                    seen, deduped = set(), []
                    for p in new_parts:
                        if p not in seen:
                            seen.add(p); deduped.append(p)
                    new_val = ";".join(deduped)
                    if new_val != row[f]:
                        row[f] = new_val
                        touched = True

            # Venue + city
            if venue_field and city_field:
                old_v, old_c = row.get(venue_field), row.get(city_field)
                new_v, new_c = canonicalize_venue(old_v, old_c)
                if new_v != old_v or new_c != old_c:
                    row[venue_field] = new_v
                    row[city_field]  = new_c
                    touched = True

            if touched:
                rows_touched += 1
            writer.writerow(row)
    os.replace(tmp, path)
    return rows_total, rows_touched


def rebuild_grounds(matches_path, grounds_path):
    """Recompute the grounds table from the cleaned matches.csv."""
    g = defaultdict(lambda: {"venue": None, "city": None, "matches": 0,
                             "first": None, "last": None})
    with open(matches_path) as f:
        for row in csv.DictReader(f):
            v = row.get("venue")
            if not v:
                continue
            entry = g[v]
            entry["venue"] = v
            entry["city"]  = row.get("city")
            entry["matches"] += 1
            d = row.get("match_date")
            if d:
                if entry["first"] is None or d < entry["first"]: entry["first"] = d
                if entry["last"]  is None or d > entry["last"]:  entry["last"]  = d

    with open(grounds_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "venue", "city", "matches_held", "first_match_date", "last_match_date",
        ])
        writer.writeheader()
        for e in sorted(g.values(), key=lambda x: (x["venue"] or "").lower()):
            writer.writerow({
                "venue":            e["venue"],
                "city":             e["city"],
                "matches_held":     e["matches"],
                "first_match_date": e["first"],
                "last_match_date":  e["last"],
            })
    return len(g)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("build_dir", help="The build/ folder produced by parse_cricsheet.py")
    args = ap.parse_args()

    bd = Path(args.build_dir).expanduser().resolve()
    required = [bd / "matches.csv", bd / "deliveries.csv", bd / "grounds.csv"]
    for p in required:
        if not p.exists():
            print(f"Missing file: {p}", file=sys.stderr); sys.exit(1)

    print(f"Cleaning data in {bd}\n")

    print("Rewriting matches.csv ...")
    n, t = rewrite_csv(bd / "matches.csv",
                       team_fields=("team1", "team2", "toss_winner", "winner"),
                       venue_field="venue", city_field="city")
    print(f"  {n} rows / {t} touched")

    print("Rewriting deliveries.csv ...")
    n, t = rewrite_csv(bd / "deliveries.csv",
                       team_fields=("batting_team", "bowling_team"),
                       venue_field="venue", city_field="city")
    print(f"  {n} rows / {t} touched")

    players_path = bd / "players.csv"
    if players_path.exists():
        print("Rewriting players.csv ...")
        n, t = rewrite_csv(players_path,
                           team_list_fields=("teams_played_for",))
        print(f"  {n} rows / {t} touched")

    print("Rebuilding grounds.csv ...")
    n = rebuild_grounds(bd / "matches.csv", bd / "grounds.csv")
    print(f"  {n} unique venues remain")

    # Per-innings derived tables and the dashboard are not modified here.
    # Regenerate them with:
    #   python3 build_innings_tables.py <build_dir>
    #   python3 build_dashboard.py       <build_dir> dashboard.html
    stale = [bd / "batter_innings.csv", bd / "bowler_innings.csv"]
    if any(p.exists() for p in stale):
        print()
        print("NOTE: batter_innings.csv / bowler_innings.csv may now be stale.")
        print("Regenerate by re-running build_innings_tables.py.")


if __name__ == "__main__":
    main()
