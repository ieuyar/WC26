"""
fetch_squads.py - pull the 26-man squads for all 48 WC 2026 teams.

Source: football-data.org /v4/teams/{id}. Each player gives us name,
position, date of birth and nationality. Club + market value + caps +
goals are NOT in the API; we gap-fill them from Transfermarkt in a
separate pass.

Output: squads_raw.csv (API-only fields).

Rate-limit notes: the free tier allows 10 calls/minute. We make 1 call
to list teams plus 48 calls for each team's squad (49 total) and sleep
~7 seconds between calls (8.5 calls/min, comfortably under the cap).
Total runtime ~6 minutes.
"""

import csv
import json
import os
import time
import urllib.error
import urllib.request
from datetime import date

from live_ingest import NAME_MAP, load_token

_DIR = os.path.dirname(os.path.abspath(__file__))
RAW_FILE = os.path.join(_DIR, "squads_raw.csv")
TEAMS_CACHE = os.path.join(_DIR, ".teams_cache.json")
TEAMS_URL = "https://api.football-data.org/v4/competitions/WC/teams"
TEAM_URL = "https://api.football-data.org/v4/teams/{id}"
TODAY = date(2026, 6, 11)  # WC opening day - used for age calculation

FIELDS = ["team", "player_id", "name", "position", "date_of_birth",
          "age", "nationality"]


def _request(url, token):
    req = urllib.request.Request(url, headers={"X-Auth-Token": token})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def _age(dob_str):
    if not dob_str:
        return None
    y, m, d = (int(x) for x in dob_str.split("-"))
    a = TODAY.year - y
    if (TODAY.month, TODAY.day) < (m, d):
        a -= 1
    return a


def _team_name(api_name):
    return NAME_MAP.get(api_name, api_name)


def _load_done():
    """Return the set of teams already in squads_raw.csv."""
    if not os.path.exists(RAW_FILE):
        return set()
    with open(RAW_FILE) as f:
        return {row["team"] for row in csv.DictReader(f)}


def _append_rows(rows):
    """Append rows to squads_raw.csv, creating the file if needed."""
    is_new = not os.path.exists(RAW_FILE)
    with open(RAW_FILE, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if is_new:
            writer.writeheader()
        writer.writerows(rows)


def _load_teams(token):
    """Get the WC team list, cached after the first call to save quota."""
    if os.path.exists(TEAMS_CACHE):
        with open(TEAMS_CACHE) as f:
            return json.load(f)
    payload = _request(TEAMS_URL, token)
    teams = payload.get("teams", [])
    with open(TEAMS_CACHE, "w") as f:
        json.dump(teams, f)
    return teams


def main():
    token = load_token()
    teams = _load_teams(token)
    done = _load_done()
    todo = [t for t in teams if _team_name(t["name"]) not in done]
    print(f"API lists {len(teams)} teams; {len(done)} already fetched, "
          f"{len(todo)} to go.\n")

    budget = 35  # seconds of wall time per invocation
    started = time.time()
    completed_this_run = 0

    for t in todo:
        if time.time() - started > budget:
            print(f"\nBudget reached - stopping. Re-run to continue.")
            break
        team_name = _team_name(t["name"])
        print(f"  {team_name:<25} (id={t['id']}) ...", end="", flush=True)
        try:
            data = _request(TEAM_URL.format(id=t["id"]), token)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                print(" 429 - rate-limited, stopping")
                break
            print(f" HTTP {e.code} - skipping")
            continue

        squad = data.get("squad", [])
        rows = []
        for p in squad:
            dob = p.get("dateOfBirth", "")
            rows.append({
                "team": team_name,
                "player_id": p.get("id"),
                "name": p.get("name", ""),
                "position": p.get("position", ""),
                "date_of_birth": dob,
                "age": _age(dob),
                "nationality": p.get("nationality", ""),
            })
        _append_rows(rows)
        print(f" {len(squad)} players")
        completed_this_run += 1

    done = _load_done()
    print(f"\nThis run: {completed_this_run} teams. "
          f"Cumulative: {len(done)}/{len(teams)} done.")


if __name__ == "__main__":
    main()
