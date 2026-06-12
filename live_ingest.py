"""
live_ingest.py - pull actual World Cup results from football-data.org.

During the tournament this fetches real match results so the model can be
re-run *conditioned on what has already happened* instead of simulating games
that have already been played. Run it before each re-run of run_simulation.py
(directly, or from the daily scheduled task).

Output: live_results.csv - one row per FINISHED match, with both team names
translated to the names used across this project, plus the final score.

Setup:
  1. Get a free token at https://www.football-data.org/client/register
  2. Paste it into api_token.txt (replace the placeholder line).
  3. Run: python3 live_ingest.py

Before the tournament kicks off there are no finished matches yet - the script
will simply report zero results, which is correct. The token is read from a
local file and never hard-coded, so it stays out of the codebase.
"""

import csv
import json
import os
import sys
import urllib.error
import urllib.request

_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(_DIR, "api_token.txt")
RESULTS_FILE = os.path.join(_DIR, "live_results.csv")
PLACEHOLDER = "PASTE_YOUR_FOOTBALL_DATA_ORG_TOKEN_HERE"

# football-data.org v4 endpoint; "WC" is its competition code for the World Cup.
API_URL = "https://api.football-data.org/v4/competitions/WC/matches"

# football-data.org spells some national teams differently from groups.csv.
# Map the API's spelling -> this project's spelling. If the script reports an
# unmatched name, add it here.
NAME_MAP = {
    "Turkiye": "Turkey", "Türkiye": "Turkey",
    "Cote d'Ivoire": "Cote d'Ivoire", "Côte d'Ivoire": "Cote d'Ivoire",
    "Ivory Coast": "Cote d'Ivoire",
    "Korea Republic": "South Korea", "South Korea": "South Korea",
    "United States": "United States", "USA": "United States",
    "Curacao": "Curacao", "Curaçao": "Curacao",
    "DR Congo": "DR Congo", "Congo DR": "DR Congo",
    "Democratic Republic of the Congo": "DR Congo",
    "Bosnia and Herzegovina": "Bosnia and Herzegovina",
    "Bosnia-Herzegovina": "Bosnia and Herzegovina",
    "Cape Verde": "Cape Verde", "Cabo Verde": "Cape Verde",
    "Cape Verde Islands": "Cape Verde",
    "Czechia": "Czechia", "Czech Republic": "Czechia",
}

RESULT_FIELDS = ["stage", "group", "home_team", "away_team",
                 "home_goals", "away_goals", "status"]


def load_token():
    """Read the API token from api_token.txt; exit with a clear message if
    it is missing or still holds the placeholder."""
    if not os.path.exists(TOKEN_FILE):
        sys.exit("No api_token.txt found next to live_ingest.py. Create it "
                 "and paste your football-data.org token inside.")
    with open(TOKEN_FILE) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                if line == PLACEHOLDER:
                    sys.exit("api_token.txt still holds the placeholder - "
                             "paste your real football-data.org token in it.")
                return line
    sys.exit("api_token.txt contains no token line.")


def fetch_matches(token):
    """Call football-data.org and return parsed JSON, or exit on error."""
    request = urllib.request.Request(API_URL, headers={"X-Auth-Token": token})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            sys.exit("football-data.org rejected the token (HTTP "
                     f"{exc.code}). Check api_token.txt.")
        if exc.code == 429:
            sys.exit("Rate limited by football-data.org (HTTP 429). The free "
                     "tier allows 10 requests/minute - wait and retry.")
        sys.exit(f"football-data.org returned HTTP {exc.code}.")
    except urllib.error.URLError as exc:
        sys.exit(f"Could not reach football-data.org: {exc.reason}")


def _map_name(api_name, known_teams, unmatched):
    """Translate an API team name to a project name; record any misses."""
    if api_name in NAME_MAP:
        return NAME_MAP[api_name]
    if api_name in known_teams:
        return api_name
    if api_name:
        unmatched.add(api_name)
    return None


def extract_finished(payload, known_teams):
    """Return (rows, unmatched_names) for every FINISHED match."""
    rows, unmatched = [], set()
    for match in payload.get("matches", []):
        if match.get("status") != "FINISHED":
            continue
        full_time = match.get("score", {}).get("fullTime", {})
        home_goals, away_goals = full_time.get("home"), full_time.get("away")
        if home_goals is None or away_goals is None:
            continue
        home = _map_name((match.get("homeTeam") or {}).get("name", ""),
                         known_teams, unmatched)
        away = _map_name((match.get("awayTeam") or {}).get("name", ""),
                         known_teams, unmatched)
        if home is None or away is None:
            continue
        rows.append({
            "stage": match.get("stage", ""),
            "group": (match.get("group") or "").replace("GROUP_", ""),
            "home_team": home,
            "away_team": away,
            "home_goals": int(home_goals),
            "away_goals": int(away_goals),
            "status": "FINISHED",
        })
    return rows, unmatched


def write_results(rows):
    with open(RESULTS_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=RESULT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main():
    from data import load_elo
    known_teams = set(load_elo())

    token = load_token()
    payload = fetch_matches(token)
    rows, unmatched = extract_finished(payload, known_teams)
    write_results(rows)

    total = len(payload.get("matches", []))
    finished = len(rows)
    group_stage = sum(1 for r in rows if r["stage"] == "GROUP_STAGE")
    print(f"football-data.org: {total} matches listed, {finished} finished "
          f"and saved to live_results.csv ({group_stage} group-stage).")
    if finished == 0:
        print("No finished matches yet - run_simulation.py will behave as a "
              "pre-tournament forecast. This is expected before kickoff.")
    if unmatched:
        print("\nWARNING - these API team names matched no project team. "
              "Add them to NAME_MAP in live_ingest.py:")
        for name in sorted(unmatched):
            print(f"  - {name!r}")


if __name__ == "__main__":
    main()
