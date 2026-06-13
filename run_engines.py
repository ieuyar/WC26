"""
run_engines.py - per-engine simulation outputs for the dashboard engine selector.

Runs the full 10,000-simulation Monte Carlo under each of four rating engines
and stacks the per-team outcomes into one file with an `engine` column - the
table a Power BI engine slicer needs to make the whole report engine-aware.

Engines:
  Model        - the production rating: Elo blended with squad market value.
  Elo          - the raw Elo snapshot.
  Squad value  - rating from Transfermarkt squad value alone.
  FIFA ranking - rating from FIFA ranking points alone.

Output: simulation_output/engine_scenarios.csv
"""

import csv
import os

from data import (load_elo, load_groups, load_squad_values,
                   load_third_place_table)
from montecarlo import run_monte_carlo
from rating_engines import engines as pure_engines
from squad_strength import effective_elo

try:
    from run_simulation import load_known_results
except ImportError:
    def load_known_results():
        return []

_DIR = os.path.dirname(os.path.abspath(__file__))
N_SIMULATIONS = 10000
RANDOM_SEED = 2026


def main():
    groups = load_groups()
    third_place_table = load_third_place_table()
    team_group = {t: g for g in groups for t in groups[g]}

    pure = pure_engines()
    engines = {
        "Model": effective_elo(load_elo(), load_squad_values()),
        "Elo": pure["Elo"],
        "Squad value": pure["Squad value"],
        "FIFA ranking": pure["FIFA ranking"],
    }

    # Apply the same results-conditioning as run_simulation.py - otherwise
    # the engine_scenarios.csv lags behind reality once matches are played.
    known_results = load_known_results()
    if known_results:
        print(f"Conditioning each engine on {len(known_results)} completed "
              f"match(es) from live_results.csv.")

    rows = []
    for name, ratings in engines.items():
        print(f"Running {N_SIMULATIONS:,} simulations - {name} engine ...")
        mc = run_monte_carlo(ratings, groups, third_place_table,
                             n=N_SIMULATIONS, seed=RANDOM_SEED,
                             known_results=known_results, progress=False)
        for team, p in mc["teams"].items():
            rows.append({
                "engine": name,
                "team": team,
                "group": team_group[team],
                "p_qualify": round(p["qualify"] * 100, 2),
                "p_win_group": round(p["finish_1st"] * 100, 2),
                "p_reach_qf": round(p["reach_QF"] * 100, 2),
                "p_win_title": round(p["win_title"] * 100, 2),
            })

    out = os.path.join(_DIR, "simulation_output", "engine_scenarios.csv")
    with open(out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["engine", "team", "group",
            "p_qualify", "p_win_group", "p_reach_qf", "p_win_title"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nWrote {out} ({len(rows)} rows: 4 engines x 48 teams)")


if __name__ == "__main__":
    main()
