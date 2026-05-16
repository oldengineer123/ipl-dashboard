#!/usr/bin/env python3
"""
Parse a folder of Cricsheet IPL match JSONs into four flat tables:

    deliveries.csv  - one row per ball bowled (the fact table)
    matches.csv     - one row per match
    players.csv     - one row per distinct player
    grounds.csv     - one row per venue

Usage:
    python3 parse_cricsheet.py <input_dir> [--out <output_dir>]

If --out is omitted, tables are written to <input_dir>/build/.

Stdlib only - works with the Python that ships with macOS.
"""

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path


DELIVERY_FIELDS = [
    "match_id", "season", "match_date",
    "innings_no", "is_super_over",
    "batting_team", "bowling_team",
    "over", "ball_in_over", "legal_ball_in_over", "ball_number",
    "phase",
    "batter", "non_striker", "bowler",
    "runs_batter", "runs_extras", "runs_total",
    "extras_wides", "extras_noballs", "extras_byes", "extras_legbyes", "extras_penalty",
    "is_wicket", "wicket_kind", "player_out", "fielders",
    "venue", "city",
]

MATCH_FIELDS = [
    "match_id", "season", "match_date",
    "venue", "city",
    "team1", "team2",
    "toss_winner", "toss_decision",
    "winner", "win_by_runs", "win_by_wickets", "method", "result",
    "player_of_match", "event_name", "match_number", "stage",
    "team1_total", "team1_wickets", "team1_overs",
    "team2_total", "team2_wickets", "team2_overs",
]

PLAYER_FIELDS = [
    "player_id", "player_name", "teams_played_for",
    "matches_played", "first_match_date", "last_match_date",
    "country",
]

GROUND_FIELDS = [
    "venue", "city",
    "matches_held", "first_match_date", "last_match_date",
]


def classify_phase(over_zero_indexed, is_super):
    """IPL phase by over number (0-indexed)."""
    if is_super:
        return "super_over"
    if over_zero_indexed <= 5:
        return "powerplay"   # overs 1-6
    if over_zero_indexed <= 14:
        return "middle"      # overs 7-15
    return "death"           # overs 16-20


def parse_match(path):
    """Parse a single Cricsheet JSON. Returns (match_row, delivery_rows, player_rows)."""
    with open(path) as f:
        data = json.load(f)

    info = data.get("info", {})
    match_id = Path(path).stem
    dates = info.get("dates", []) or []
    match_date = dates[0] if dates else None
    season = info.get("season")
    venue = info.get("venue")
    city = info.get("city")
    teams = (info.get("teams") or []) + [None, None]
    team1, team2 = teams[0], teams[1]
    toss = info.get("toss") or {}
    outcome = info.get("outcome") or {}
    by = outcome.get("by") or {}
    pom = info.get("player_of_match") or []
    event = info.get("event") or {}

    innings_totals = {}   # team -> (runs, wickets, overs_decimal) for the main game only

    delivery_rows = []
    for inn_idx, inning in enumerate(data.get("innings", []), start=1):
        batting_team = inning.get("team")
        bowling_team = team2 if batting_team == team1 else team1
        is_super = bool(inning.get("super_over"))

        ball_number = 0
        runs_total_inn = 0
        wickets_inn = 0
        legal_balls_inn = 0
        last_over_seen = -1
        legal_in_over = 0

        for over_block in inning.get("overs", []) or []:
            over_no = over_block.get("over")
            if over_no != last_over_seen:
                legal_in_over = 0
                last_over_seen = over_no
            for ball_idx, d in enumerate(over_block.get("deliveries", []) or [], start=1):
                ball_number += 1
                extras = d.get("extras") or {}
                is_legal = not (extras.get("wides") or extras.get("noballs"))
                if is_legal:
                    legal_in_over += 1
                    legal_balls_inn += 1

                wickets = d.get("wickets") or []
                is_wicket = bool(wickets)
                wicket_kinds = ";".join(w.get("kind", "") for w in wickets)
                players_out = ";".join(w.get("player_out", "") for w in wickets)
                fielders = []
                for w in wickets:
                    for fld in (w.get("fielders") or []):
                        if isinstance(fld, dict):
                            fielders.append(fld.get("name", ""))
                        else:
                            fielders.append(str(fld))
                fielders_str = ";".join(f for f in fielders if f)

                runs = d.get("runs") or {}
                runs_total = runs.get("total", 0) or 0
                runs_total_inn += runs_total
                if is_wicket:
                    wickets_inn += len(wickets)

                delivery_rows.append({
                    "match_id": match_id,
                    "season": season,
                    "match_date": match_date,
                    "innings_no": inn_idx,
                    "is_super_over": int(is_super),
                    "batting_team": batting_team,
                    "bowling_team": bowling_team,
                    "over": over_no,
                    "ball_in_over": ball_idx,
                    "legal_ball_in_over": legal_in_over if is_legal else None,
                    "ball_number": ball_number,
                    "phase": classify_phase(over_no, is_super),
                    "batter": d.get("batter"),
                    "non_striker": d.get("non_striker"),
                    "bowler": d.get("bowler"),
                    "runs_batter": runs.get("batter", 0) or 0,
                    "runs_extras": runs.get("extras", 0) or 0,
                    "runs_total": runs_total,
                    "extras_wides": extras.get("wides", 0) or 0,
                    "extras_noballs": extras.get("noballs", 0) or 0,
                    "extras_byes": extras.get("byes", 0) or 0,
                    "extras_legbyes": extras.get("legbyes", 0) or 0,
                    "extras_penalty": extras.get("penalty", 0) or 0,
                    "is_wicket": int(is_wicket),
                    "wicket_kind": wicket_kinds or None,
                    "player_out": players_out or None,
                    "fielders": fielders_str or None,
                    "venue": venue,
                    "city": city,
                })

        if not is_super and batting_team:
            overs_decimal = legal_balls_inn // 6 + (legal_balls_inn % 6) / 10
            innings_totals[batting_team] = (runs_total_inn, wickets_inn, overs_decimal)

    match_row = {
        "match_id": match_id,
        "season": season,
        "match_date": match_date,
        "venue": venue,
        "city": city,
        "team1": team1,
        "team2": team2,
        "toss_winner": toss.get("winner"),
        "toss_decision": toss.get("decision"),
        "winner": outcome.get("winner"),
        "win_by_runs": by.get("runs"),
        "win_by_wickets": by.get("wickets"),
        "method": outcome.get("method"),
        "result": outcome.get("result"),
        "player_of_match": ";".join(pom) if pom else None,
        "event_name": event.get("name"),
        "match_number": event.get("match_number"),
        "stage": event.get("stage"),
        "team1_total":   innings_totals.get(team1, (None, None, None))[0],
        "team1_wickets": innings_totals.get(team1, (None, None, None))[1],
        "team1_overs":   innings_totals.get(team1, (None, None, None))[2],
        "team2_total":   innings_totals.get(team2, (None, None, None))[0],
        "team2_wickets": innings_totals.get(team2, (None, None, None))[1],
        "team2_overs":   innings_totals.get(team2, (None, None, None))[2],
    }

    registry = ((info.get("registry") or {}).get("people")) or {}
    players_in_match = info.get("players") or {}
    player_rows = []
    seen = set()
    for team_name, players in players_in_match.items():
        for name in players:
            pid = registry.get(name)
            key = pid or name
            if key in seen:
                continue
            seen.add(key)
            player_rows.append({
                "player_id": pid,
                "player_name": name,
                "team": team_name,
                "match_date": match_date,
            })

    return match_row, delivery_rows, player_rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input_dir", help="Folder of Cricsheet IPL JSON files")
    ap.add_argument("--out", help="Output folder (default: <input_dir>/build)")
    args = ap.parse_args()

    in_dir = Path(args.input_dir).expanduser().resolve()
    out_dir = Path(args.out).expanduser().resolve() if args.out else in_dir / "build"
    out_dir.mkdir(parents=True, exist_ok=True)

    json_paths = sorted(in_dir.glob("*.json"))
    if not json_paths:
        print(f"No .json files in {in_dir}", file=sys.stderr)
        sys.exit(1)
    print(f"Parsing {len(json_paths)} matches from {in_dir} ...")

    deliveries_path = out_dir / "deliveries.csv"
    matches_path    = out_dir / "matches.csv"
    players_path    = out_dir / "players.csv"
    grounds_path    = out_dir / "grounds.csv"

    player_agg = {}
    ground_agg = defaultdict(lambda: {"venue": None, "city": None,
                                      "matches": set(), "first": None, "last": None})

    delivery_count = 0
    match_count = 0
    skipped = 0

    with open(deliveries_path, "w", newline="") as fd, \
         open(matches_path, "w", newline="") as fm:
        d_writer = csv.DictWriter(fd, fieldnames=DELIVERY_FIELDS)
        d_writer.writeheader()
        m_writer = csv.DictWriter(fm, fieldnames=MATCH_FIELDS)
        m_writer.writeheader()

        for i, jp in enumerate(json_paths, start=1):
            try:
                match_row, delivery_rows, player_rows = parse_match(jp)
            except Exception as exc:
                print(f"  ! skipped {jp.name}: {exc}", file=sys.stderr)
                skipped += 1
                continue

            m_writer.writerow(match_row)
            match_count += 1
            for row in delivery_rows:
                d_writer.writerow(row)
            delivery_count += len(delivery_rows)

            mdate = match_row["match_date"]
            v = match_row["venue"]
            if v:
                g = ground_agg[v]
                g["venue"] = v
                g["city"]  = match_row["city"]
                g["matches"].add(match_row["match_id"])
                if mdate:
                    if g["first"] is None or mdate < g["first"]: g["first"] = mdate
                    if g["last"]  is None or mdate > g["last"]:  g["last"]  = mdate

            for pr in player_rows:
                key = pr["player_id"] or pr["player_name"]
                p = player_agg.setdefault(key, {
                    "player_id": pr["player_id"],
                    "player_name": pr["player_name"],
                    "teams": set(),
                    "matches": set(),
                    "first": None,
                    "last": None,
                })
                p["teams"].add(pr["team"])
                p["matches"].add(match_row["match_id"])
                if pr["match_date"]:
                    if p["first"] is None or pr["match_date"] < p["first"]: p["first"] = pr["match_date"]
                    if p["last"]  is None or pr["match_date"] > p["last"]:  p["last"]  = pr["match_date"]

            if i % 200 == 0:
                print(f"  ... {i}/{len(json_paths)}")

    with open(players_path, "w", newline="") as fp:
        w = csv.DictWriter(fp, fieldnames=PLAYER_FIELDS)
        w.writeheader()
        for p in sorted(player_agg.values(), key=lambda x: (x["player_name"] or "").lower()):
            w.writerow({
                "player_id": p["player_id"],
                "player_name": p["player_name"],
                "teams_played_for": ";".join(sorted(t for t in p["teams"] if t)),
                "matches_played": len(p["matches"]),
                "first_match_date": p["first"],
                "last_match_date": p["last"],
                "country": None,  # placeholder - enrich later for "international vs domestic" cuts
            })

    with open(grounds_path, "w", newline="") as fg:
        w = csv.DictWriter(fg, fieldnames=GROUND_FIELDS)
        w.writeheader()
        for g in sorted(ground_agg.values(), key=lambda x: (x["venue"] or "").lower()):
            w.writerow({
                "venue": g["venue"],
                "city": g["city"],
                "matches_held": len(g["matches"]),
                "first_match_date": g["first"],
                "last_match_date": g["last"],
            })

    print()
    print("Done.")
    print(f"  {matches_path}     ({match_count} matches, {skipped} skipped)")
    print(f"  {deliveries_path}  ({delivery_count} deliveries)")
    print(f"  {players_path}     ({len(player_agg)} players)")
    print(f"  {grounds_path}     ({len(ground_agg)} grounds)")


if __name__ == "__main__":
    main()
