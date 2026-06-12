"""
build_squads.py - merge Wikipedia squad data into squads.csv.

Input:
  wc_squads_wikipedia.csv  - parsed from the 2026 World Cup squads page via
                              Claude in Chrome; one row per player with
                              position, age, DOB, caps, goals, club.

Output:
  squads.csv  - the canonical 26-player roster for each of the 48 teams,
                with team names matched to the project's groups.csv naming.
                market_value_eur is left empty (Transfermarkt pass next).
"""

import csv
import os
import re

_DIR = os.path.dirname(os.path.abspath(__file__))
WIKI = os.path.join(_DIR, "wc_squads_wikipedia.csv")
OUT = os.path.join(_DIR, "squads.csv")

# Wikipedia spells some national teams differently from groups.csv.
TEAM_RENAME = {
    "Czech Republic": "Czechia",
    "Ivory Coast": "Cote d'Ivoire",
    "Curaçao": "Curacao",
}

OUTPUT_FIELDS = ["team", "shirt_number", "player_name", "is_captain",
                 "position", "age", "date_of_birth", "nationality", "club",
                 "caps", "goals", "market_value_eur"]


def split_captain(name):
    """'Edin Džeko (captain)' -> ('Edin Džeko', 1)."""
    m = re.match(r"^(.*?)\s*\(captain\)\s*$", name)
    if m:
        return m.group(1).strip(), 1
    return name.strip(), 0


def _as_int(s):
    s = (s or "").strip()
    if not s:
        return ""
    try:
        return int(s)
    except ValueError:
        return s


def main():
    with open(WIKI) as f:
        rows = list(csv.DictReader(f))

    out = []
    for r in rows:
        team = TEAM_RENAME.get(r["team"], r["team"])
        name, is_captain = split_captain(r["player_name"])
        out.append({
            "team": team,
            "shirt_number": _as_int(r.get("", "")),
            "player_name": name,
            "is_captain": is_captain,
            "position": r["position"],
            "age": _as_int(r["age"]),
            "date_of_birth": r["date_of_birth"],
            "nationality": team,
            "club": r["club"],
            "caps": _as_int(r["caps"]),
            "goals": _as_int(r["goals"]),
            "market_value_eur": "",
        })

    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=OUTPUT_FIELDS)
        w.writeheader()
        w.writerows(out)

    teams = sorted(set(r["team"] for r in out))
    print(f"Wrote {OUT} ({len(out)} player rows across {len(teams)} teams).")
    print(f"  Filled: team, player_name, is_captain, position, age, "
          f"date_of_birth, nationality, club, caps, goals.")
    print(f"  TODO:   market_value_eur (Transfermarkt pass).")


if __name__ == "__main__":
    main()
