"""
patch_squad_values.py - rebuild squad_values.csv from the per-player squads.csv.

The earlier squad_values.csv was scraped from Transfermarkt's tournament-
participants page, which aggregates the full national-team pool (~30 players).
Now that squads.csv has the official 26-man WC roster sums, this script
recomputes squad_values.csv from those.

This is the value that feeds squad_strength.py -> team_strength.csv ->
the simulation, so re-run the pipeline after this script.
"""

import csv
import os

_DIR = os.path.dirname(os.path.abspath(__file__))
SQUADS = os.path.join(_DIR, "squads.csv")
VALUES = os.path.join(_DIR, "squad_values.csv")


def main():
    # Sum 26-man squad market values per team.
    team_sum = {}
    matched_players = {}
    with open(SQUADS) as f:
        for r in csv.DictReader(f):
            team = r["team"]
            mv = r["market_value_eur"]
            if mv:
                team_sum[team] = team_sum.get(team, 0) + int(mv)
                matched_players[team] = matched_players.get(team, 0) + 1

    # Update squad_values.csv in place.
    with open(VALUES) as f:
        rows = list(csv.DictReader(f))
        fields = list(rows[0].keys())

    updated = 0
    diffs = []
    for r in rows:
        team = r["team"]
        if team in team_sum:
            old_val = float(r["squad_value_eur_millions"])
            new_val = round(team_sum[team] / 1_000_000, 1)
            r["squad_value_eur_millions"] = new_val
            updated += 1
            if abs(old_val - new_val) > 1:
                diffs.append((team, old_val, new_val,
                              matched_players.get(team, 0)))

    with open(VALUES, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    print(f"Updated {updated}/{len(rows)} teams' squad_value from 26-man "
          f"rosters.")
    print(f"\nBiggest swings (|old - new| > €1M):")
    for team, old_val, new_val, n in sorted(diffs,
                                              key=lambda x: abs(x[1] - x[2]),
                                              reverse=True)[:15]:
        delta = new_val - old_val
        print(f"  {team:<22}  old €{old_val:>7.1f}M -> new €{new_val:>7.1f}M "
              f"(Δ {delta:+7.1f}, {n} players)")


if __name__ == "__main__":
    main()
