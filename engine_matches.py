"""
engine_matches.py - per-engine analytic match predictions.

For the dashboard's Match Predictions page when made engine-aware: the same
72 group-stage fixtures, each scored under all four rating engines (Model,
Elo, Squad value, FIFA ranking). Match probabilities come from the same
Elo -> Poisson analytic step the simulator uses for one match.

Output: simulation_output/engine_match_predictions.csv
"""

import csv
import os

from data import load_elo, load_groups, load_squad_values
from match import host_advantage, match_probabilities
from rating_engines import engines as pure_engines
from squad_strength import effective_elo

_DIR = os.path.dirname(os.path.abspath(__file__))

# Round-robin matchday pattern for a 4-team group (team positions 0-3).
_MATCHDAY_FIXTURES = {
    1: [(0, 1), (2, 3)],
    2: [(0, 2), (1, 3)],
    3: [(0, 3), (1, 2)],
}


def main():
    groups = load_groups()
    pure = pure_engines()
    engines = {
        "Model": effective_elo(load_elo(), load_squad_values()),
        "Elo": pure["Elo"],
        "Squad value": pure["Squad value"],
        "FIFA ranking": pure["FIFA ranking"],
    }

    rows = []
    for engine_name, ratings in engines.items():
        match_id = 0
        for matchday in (1, 2, 3):
            for letter in "ABCDEFGHIJKL":
                members = groups[letter]
                for i, j in _MATCHDAY_FIXTURES[matchday]:
                    team_a, team_b = members[i], members[j]
                    match_id += 1
                    home = host_advantage(team_a, team_b)
                    pr = match_probabilities(ratings[team_a],
                                              ratings[team_b], home=home)
                    rows.append({
                        "engine": engine_name,
                        "match_id": match_id,
                        "matchday": matchday,
                        "group": letter,
                        "team_a": team_a,
                        "team_b": team_b,
                        "p_team_a_win": round(pr["p_a_win"], 5),
                        "p_draw": round(pr["p_draw"], 5),
                        "p_team_b_win": round(pr["p_b_win"], 5),
                        "likely_scoreline": pr["likely_score"],
                    })

    out = os.path.join(_DIR, "simulation_output",
                       "engine_match_predictions.csv")
    with open(out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["engine", "match_id", "matchday",
            "group", "team_a", "team_b", "p_team_a_win", "p_draw",
            "p_team_b_win", "likely_scoreline"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {out} ({len(rows)} rows: "
          f"{len(engines)} engines x 72 fixtures)")


if __name__ == "__main__":
    main()
