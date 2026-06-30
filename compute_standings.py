"""
compute_standings.py - build current group standings from live_results.csv.

Reads every FINISHED match, attributes wins/draws/losses and goals
for/against to each team, sorts within each group by FIFA tiebreakers
(points -> goal difference -> goals for), and writes a CSV the dashboard
can render directly.

Output: simulation_output/group_standings.csv
"""

import csv
import os
from collections import defaultdict

from data import load_groups

_DIR = os.path.dirname(os.path.abspath(__file__))
LIVE = os.path.join(_DIR, "live_results.csv")
OUT = os.path.join(_DIR, "simulation_output", "group_standings.csv")

FIELDS = ["group", "rank", "team", "played", "wins", "draws", "losses",
          "goals_for", "goals_against", "goal_diff", "points"]


def main():
    groups = load_groups()
    team_to_group = {t: g for g, ts in groups.items() for t in ts}

    # Initialize every team with zeroes so empty groups show up correctly
    stats = {}
    for letter, members in groups.items():
        for t in members:
            stats[t] = {"group": letter, "team": t, "played": 0, "wins": 0,
                        "draws": 0, "losses": 0, "goals_for": 0,
                        "goals_against": 0}

    # Aggregate played GROUP-STAGE matches only. Skipping the stage filter
    # was a bug: knockout games would inflate group standings (e.g. Paraguay
    # showing P4 in a 6-match group after their R32 game vs Germany).
    if os.path.exists(LIVE):
        with open(LIVE) as f:
            for r in csv.DictReader(f):
                if r.get("status") != "FINISHED":
                    continue
                if r.get("stage") != "GROUP_STAGE":
                    continue
                home, away = r["home_team"], r["away_team"]
                if home not in stats or away not in stats:
                    continue
                hg, ag = int(r["home_goals"]), int(r["away_goals"])
                stats[home]["played"] += 1
                stats[away]["played"] += 1
                stats[home]["goals_for"] += hg
                stats[home]["goals_against"] += ag
                stats[away]["goals_for"] += ag
                stats[away]["goals_against"] += hg
                if hg > ag:
                    stats[home]["wins"] += 1
                    stats[away]["losses"] += 1
                elif hg < ag:
                    stats[away]["wins"] += 1
                    stats[home]["losses"] += 1
                else:
                    stats[home]["draws"] += 1
                    stats[away]["draws"] += 1

    # Compute derived fields
    for r in stats.values():
        r["goal_diff"] = r["goals_for"] - r["goals_against"]
        r["points"] = r["wins"] * 3 + r["draws"]

    # Group rows, sort by FIFA tiebreakers (pts -> GD -> GF), assign rank
    by_group = defaultdict(list)
    for r in stats.values():
        by_group[r["group"]].append(r)

    out_rows = []
    for letter in sorted(by_group):
        rows = sorted(by_group[letter],
                       key=lambda r: (-r["points"], -r["goal_diff"],
                                       -r["goals_for"], r["team"]))
        for i, r in enumerate(rows, 1):
            r["rank"] = i
            out_rows.append({k: r[k] for k in FIELDS})

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(out_rows)

    played = sum(1 for r in out_rows if r["played"] > 0)
    print(f"Wrote {OUT} ({len(out_rows)} teams, "
          f"{played} have played at least one match).")
    # Show Group D as a sample
    print("\nGroup D current standings:")
    for r in out_rows:
        if r["group"] == "D":
            print(f"  {r['rank']}. {r['team']:<15}  "
                  f"P{r['played']}  W{r['wins']}  D{r['draws']}  L{r['losses']}  "
                  f"GF{r['goals_for']}  GA{r['goals_against']}  "
                  f"GD{r['goal_diff']:+d}  Pts{r['points']}")


if __name__ == "__main__":
    main()
