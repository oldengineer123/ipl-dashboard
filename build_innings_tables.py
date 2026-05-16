#!/usr/bin/env python3
"""
Build per-innings derived tables for IPL analysis.

Inputs (in <build_dir>):
    deliveries.csv

Outputs (written to the same folder):
    batter_innings.csv   one row per (match_id, innings_no, batter)
    bowler_innings.csv   one row per (match_id, innings_no, bowler)

batter_innings columns:
    match_id, season, match_date, innings_no, is_super_over,
    batting_team, bowling_team, venue,
    batter, batting_position,
    runs, balls, fours, sixes, dots, strike_rate,
    is_out, dismissal_kind, dismissed_by_bowler, fielders

bowler_innings columns:
    match_id, season, match_date, innings_no, is_super_over,
    bowling_team, batting_team, venue,
    bowler, overs, legal_balls, runs_conceded, wickets,
    maidens, dots, fours_conceded, sixes_conceded, economy

Conventions:
  * "balls" for a batter excludes wides (wides aren't a ball faced).
  * runs_conceded for a bowler = batter runs + wides + no-balls
    (byes / leg-byes / penalty runs are not charged to the bowler).
  * A maiden is an over where the bowler delivered 6 legal balls and conceded 0.
  * Wickets credited to the bowler exclude run outs, retired hurt/out,
    obstructing the field.
  * batting_position is the order each player first appeared in the innings
    (as batter or non-striker). Positions 1 and 2 are the two openers, with
    position 1 being on strike at ball 1.

Stdlib only. Idempotent — safe to re-run.

Usage:
    python3 build_innings_tables.py <build_dir>
"""

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path


BOWLER_CREDITED = {
    "bowled", "caught", "lbw", "stumped", "hit wicket", "caught and bowled",
}

BATTER_FIELDS = [
    "match_id", "season", "match_date", "innings_no", "is_super_over",
    "batting_team", "bowling_team", "venue",
    "batter", "batting_position",
    "runs", "balls", "fours", "sixes", "dots", "strike_rate",
    "is_out", "dismissal_kind", "dismissed_by_bowler", "fielders",
]

BOWLER_FIELDS = [
    "match_id", "season", "match_date", "innings_no", "is_super_over",
    "bowling_team", "batting_team", "venue",
    "bowler", "overs", "legal_balls", "runs_conceded", "wickets",
    "maidens", "dots", "fours_conceded", "sixes_conceded", "economy",
]


def init_batter(meta, batter):
    return {
        "match_id": meta["match_id"], "season": meta["season"], "match_date": meta["match_date"],
        "innings_no": meta["innings_no"], "is_super_over": meta["is_super_over"],
        "batting_team": meta["batting_team"], "bowling_team": meta["bowling_team"],
        "venue": meta["venue"],
        "batter": batter, "batting_position": None,
        "runs": 0, "balls": 0, "fours": 0, "sixes": 0, "dots": 0,
        "is_out": 0, "dismissal_kind": None, "dismissed_by_bowler": None, "fielders": None,
    }


def init_bowler(meta, bowler):
    return {
        "match_id": meta["match_id"], "season": meta["season"], "match_date": meta["match_date"],
        "innings_no": meta["innings_no"], "is_super_over": meta["is_super_over"],
        "bowling_team": meta["bowling_team"], "batting_team": meta["batting_team"],
        "venue": meta["venue"],
        "bowler": bowler,
        "legal_balls": 0, "runs_conceded": 0, "wickets": 0,
        "dots": 0, "fours_conceded": 0, "sixes_conceded": 0,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("build_dir", help="Folder containing deliveries.csv")
    args = ap.parse_args()

    bd = Path(args.build_dir).expanduser().resolve()
    deliveries_path = bd / "deliveries.csv"
    if not deliveries_path.exists():
        print(f"Missing: {deliveries_path}", file=sys.stderr)
        sys.exit(1)

    batters = {}            # (match_id, inn, batter)  -> stats dict
    bowlers = {}            # (match_id, inn, bowler)  -> stats dict
    positions = {}          # (match_id, inn)          -> {player: position}
    next_pos = {}           # (match_id, inn)          -> int
    over_acc = {}           # (match_id, inn, over, bowler) -> {runs, legal}

    n = 0
    with open(deliveries_path) as f:
        for row in csv.DictReader(f):
            n += 1
            match_id    = row["match_id"]
            inn         = int(row["innings_no"])
            is_super    = int(row["is_super_over"] or 0)
            batter      = row["batter"] or ""
            non_striker = row["non_striker"] or ""
            bowler      = row["bowler"] or ""
            runs_b      = int(row["runs_batter"] or 0)
            wides       = int(row["extras_wides"] or 0)
            noballs     = int(row["extras_noballs"] or 0)
            is_wicket   = int(row["is_wicket"] or 0)
            kind        = row["wicket_kind"] or ""
            player_out  = row["player_out"] or ""
            fielders    = row["fielders"] or None
            over_no     = int(row["over"] or 0)

            legal       = (wides == 0 and noballs == 0)
            bowler_runs = runs_b + wides + noballs

            meta = {
                "match_id": match_id, "season": row["season"], "match_date": row["match_date"],
                "innings_no": inn, "is_super_over": is_super,
                "batting_team": row["batting_team"], "bowling_team": row["bowling_team"],
                "venue": row["venue"],
            }

            # batting position tracker (positions assigned in order of first appearance)
            key_inn = (match_id, inn)
            if key_inn not in positions:
                positions[key_inn] = {}
                next_pos[key_inn] = 1
            pos_map = positions[key_inn]
            if batter and batter not in pos_map:
                pos_map[batter] = next_pos[key_inn]; next_pos[key_inn] += 1
            if non_striker and non_striker not in pos_map:
                pos_map[non_striker] = next_pos[key_inn]; next_pos[key_inn] += 1

            # ---- batter ----
            key_b = (match_id, inn, batter)
            if key_b not in batters:
                batters[key_b] = init_batter(meta, batter)
            b = batters[key_b]
            b["runs"] += runs_b
            if wides == 0:                  # wides are not balls faced
                b["balls"] += 1
                if runs_b == 0: b["dots"]  += 1
                elif runs_b == 4: b["fours"] += 1
                elif runs_b == 6: b["sixes"] += 1

            # dismissals (handle multi-wicket balls just in case)
            if is_wicket and player_out:
                outs  = player_out.split(";")
                kinds = kind.split(";")
                for i, who in enumerate(outs):
                    if not who:
                        continue
                    k = kinds[i] if i < len(kinds) else ""
                    key_who = (match_id, inn, who)
                    if key_who not in batters:
                        # non-striker run out before facing a ball etc.
                        batters[key_who] = init_batter(meta, who)
                    rec = batters[key_who]
                    rec["is_out"] = 1
                    rec["dismissal_kind"] = k
                    rec["dismissed_by_bowler"] = bowler if k in BOWLER_CREDITED else None
                    rec["fielders"] = fielders

            # ---- bowler ----
            key_w = (match_id, inn, bowler)
            if key_w not in bowlers:
                bowlers[key_w] = init_bowler(meta, bowler)
            bw = bowlers[key_w]
            bw["runs_conceded"] += bowler_runs
            if legal:
                bw["legal_balls"] += 1
                if bowler_runs == 0:
                    bw["dots"] += 1
            if   runs_b == 4: bw["fours_conceded"] += 1
            elif runs_b == 6: bw["sixes_conceded"] += 1
            if is_wicket and kind:
                for k in kind.split(";"):
                    if k in BOWLER_CREDITED:
                        bw["wickets"] += 1

            # over accumulator (for maidens)
            ok = (match_id, inn, over_no, bowler)
            o = over_acc.setdefault(ok, {"runs": 0, "legal": 0})
            o["runs"]  += bowler_runs
            o["legal"] += 1 if legal else 0

    # maidens: completed overs with 0 bowler runs
    maidens = defaultdict(int)
    for (mid, inn, ovr, bw), v in over_acc.items():
        if v["legal"] >= 6 and v["runs"] == 0:
            maidens[(mid, inn, bw)] += 1

    # ---- write batter_innings ----
    bat_path = bd / "batter_innings.csv"
    with open(bat_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=BATTER_FIELDS)
        w.writeheader()
        for (mid, inn, who), b in batters.items():
            b["batting_position"] = positions[(mid, inn)].get(who)
            b["strike_rate"] = round(100.0 * b["runs"] / b["balls"], 2) if b["balls"] else None
            w.writerow({k: b.get(k) for k in BATTER_FIELDS})

    # ---- write bowler_innings ----
    bowl_path = bd / "bowler_innings.csv"
    with open(bowl_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=BOWLER_FIELDS)
        w.writeheader()
        for (mid, inn, who), bw in bowlers.items():
            lb = bw["legal_balls"]
            bw["overs"]   = f"{lb // 6}.{lb % 6}" if lb else "0.0"
            bw["economy"] = round(6.0 * bw["runs_conceded"] / lb, 2) if lb else None
            bw["maidens"] = maidens.get((mid, inn, who), 0)
            w.writerow({k: bw.get(k) for k in BOWLER_FIELDS})

    print(f"Processed {n} deliveries.")
    print(f"  {bat_path}   ({len(batters)} batter innings)")
    print(f"  {bowl_path}  ({len(bowlers)} bowler innings)")


if __name__ == "__main__":
    main()
