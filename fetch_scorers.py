"""
fetch_scorers.py - pull tournament goals + assists per player from
football-data.org and merge into squads.csv.

The free-tier scorers endpoint returns the top ~10 scorers; we add their
goals/assists into the squads roster so the dashboard's squad table can
display tournament-stage stats next to international-career caps/goals.

Output: squads.csv gets new columns tournament_goals + tournament_assists
(or 0 for players without entries).
"""

import csv
import json
import os
import sys
import unicodedata
import urllib.error
import urllib.request

from live_ingest import NAME_MAP, load_token


def _fold(s):
    """Lowercase, strip accents, collapse spaces."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.lower().split())


def _fold_reversed(s):
    """Reverse word order then fold - catches East Asian name order."""
    return " ".join(reversed(_fold(s).split()))

_DIR = os.path.dirname(os.path.abspath(__file__))
SQUADS = os.path.join(_DIR, "squads.csv")
SCORERS_URL = "https://api.football-data.org/v4/competitions/WC/scorers?limit=100"

# football-data.org uses different team names for some nations.
TEAM_NAME_MAP = dict(NAME_MAP)
TEAM_NAME_MAP.update({
    "USA": "United States",
    "Korea Republic": "South Korea",
    "Bosnia-H.": "Bosnia and Herzegovina",
    "Cape Verde Islands": "Cape Verde",
    "DR Congo": "DR Congo",
})


def _norm_name(name):
    return TEAM_NAME_MAP.get(name, name)


def fetch_scorers(token):
    req = urllib.request.Request(SCORERS_URL,
                                  headers={"X-Auth-Token": token})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r).get("scorers", [])


def main():
    token = load_token()
    try:
        scorers = fetch_scorers(token)
    except urllib.error.HTTPError as e:
        if e.code == 429:
            sys.exit("Rate limited by football-data.org - try again in a "
                     "minute.")
        sys.exit(f"football-data.org returned HTTP {e.code}.")

    # Build a multi-key lookup: try exact name, folded, folded-reversed,
    # and last-name only so we match across spelling/order variations.
    lookup = {}
    for s in scorers:
        team = _norm_name(s["team"].get("shortName") or s["team"]["name"])
        rec = {
            "goals": s.get("goals") or 0,
            "assists": s.get("assists") or 0,
        }
        for key in {
            s["player"]["name"],
            s["player"].get("lastName") or "",
        }:
            if not key:
                continue
            lookup[(team, _fold(key))] = rec
            lookup[(team, _fold_reversed(key))] = rec

    # Update squads.csv
    with open(SQUADS) as f:
        rows = list(csv.DictReader(f))
        fields = list(rows[0].keys())

    if "tournament_goals" not in fields:
        fields.append("tournament_goals")
    if "tournament_assists" not in fields:
        fields.append("tournament_assists")

    matched = 0
    for r in rows:
        name = r["player_name"]
        last = name.split()[-1] if name else ""
        candidates = [
            (r["team"], _fold(name)),
            (r["team"], _fold(last)),
            (r["team"], _fold_reversed(name)),
        ]
        rec = None
        for c in candidates:
            if c in lookup:
                rec = lookup[c]
                break
        if rec:
            r["tournament_goals"] = rec["goals"]
            r["tournament_assists"] = rec["assists"]
            matched += 1
        else:
            r.setdefault("tournament_goals", 0)
            r.setdefault("tournament_assists", 0)

    with open(SQUADS, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    print(f"Scorers from API: {len(scorers)}.")
    print(f"Matched to squads.csv: {matched}/{len(scorers)}.")
    if matched < len(scorers):
        print("\nUnmatched scorers (possibly different name spelling):")
        for s in scorers:
            team = _norm_name(s["team"].get("shortName")
                               or s["team"]["name"])
            name = s["player"]["name"]
            k1 = (team, name.lower())
            k2 = (team, (s["player"].get("lastName") or "").lower())
            if k1 not in lookup or all(
                (r["team"], r["player_name"].lower()) != k1 and
                (r["team"], r["player_name"].split()[-1].lower()) != k2
                for r in rows
            ):
                print(f"  {team}: {name}")


if __name__ == "__main__":
    main()
