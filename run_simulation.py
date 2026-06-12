"""
Step 7 - the runner. Ties the pipeline together and writes three CSVs for the
Power BI dashboard.

Outputs (written to simulation_output/):
  match_predictions.csv  - the 72 group-stage fixtures with analytic Poisson
                           win/draw/loss probabilities and expected goals.
  simulation_results.csv - per-team tournament outcome probabilities from the
                           Monte Carlo run (qualify, reach each round, win it).
  group_outcomes.csv     - per-team group-stage finishing-position
                           probabilities (1st / 2nd / 3rd / 4th, qualify).

Run directly:  python3 run_simulation.py
"""

import csv
import os
from itertools import combinations

from data import (load_confederations, load_elo, load_groups,
                   load_known_results, load_squad_values,
                   load_third_place_table)
import match
from match import host_advantage, match_probabilities
from montecarlo import run_monte_carlo
from squad_strength import MARKET_VALUE_WEIGHT, effective_elo, strength_table
from tournament import GROUP_LETTERS

N_SIMULATIONS = 10000
RANDOM_SEED = 2026
# When True, the simulation runs on Elo adjusted by squad market value
# (see squad_strength.py); when False, on the raw Elo snapshot alone.
USE_SQUAD_ADJUSTMENT = True
# When True, host nations (USA/Canada/Mexico) get the home-advantage bonus;
# when False the whole tournament is modelled at neutral venues.
USE_HOST_ADVANTAGE = True
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "simulation_output")


def _round(value, places=5):
    return round(float(value), places)


# Round-robin matchday pattern for a 4-team group (team positions 0-3).
# MD1: T1 v T2, T3 v T4 | MD2: T1 v T3, T2 v T4 | MD3: T1 v T4, T2 v T3.
_MATCHDAY_FIXTURES = {
    1: [(0, 1), (2, 3)],
    2: [(0, 2), (1, 3)],
    3: [(0, 3), (1, 2)],
}


def write_match_predictions(elo, groups, path):
    """Analytic predictions for all 72 group-stage fixtures.

    Rows are emitted in FIFA matchday order: MD1 across all 12 groups,
    then MD2, then MD3. So sorting by match_id reproduces the schedule
    order.
    """
    rows = []
    match_id = 0
    for matchday in (1, 2, 3):
        for letter in GROUP_LETTERS:
            members = groups[letter]
            for i, j in _MATCHDAY_FIXTURES[matchday]:
                team_a, team_b = members[i], members[j]
                match_id += 1
                home = host_advantage(team_a, team_b)
                pr = match_probabilities(elo[team_a], elo[team_b], home=home)
                home_label = {"A": team_a, "B": team_b}.get(home, "neutral")
                rows.append({
                    "match_id": match_id,
                    "matchday": matchday,
                    "group": letter,
                    "team_a": team_a,
                    "team_b": team_b,
                    "elo_a": int(round(elo[team_a])),
                    "elo_b": int(round(elo[team_b])),
                    "home_advantage": home_label,
                    "expected_goals_a": _round(pr["lambda_a"], 3),
                    "expected_goals_b": _round(pr["lambda_b"], 3),
                    "p_team_a_win": _round(pr["p_a_win"]),
                    "p_draw": _round(pr["p_draw"]),
                    "p_team_b_win": _round(pr["p_b_win"]),
                    "likely_scoreline": pr["likely_score"],
                })

    fields = ["match_id", "matchday", "group", "team_a", "team_b",
              "elo_a", "elo_b", "home_advantage",
              "expected_goals_a", "expected_goals_b",
              "p_team_a_win", "p_draw", "p_team_b_win", "likely_scoreline"]
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def write_simulation_results(mc, elo, conf, path):
    """Per-team tournament outcome probabilities, ranked by title chance."""
    rows = []
    for team, p in mc["teams"].items():
        rows.append({
            "team": team,
            "group": mc["group_of"][team],
            "confederation": conf[team],
            "elo": int(round(elo[team])),
            "p_qualify": _round(p["qualify"]),
            "p_reach_r16": _round(p["reach_R16"]),
            "p_reach_qf": _round(p["reach_QF"]),
            "p_reach_sf": _round(p["reach_SF"]),
            "p_reach_final": _round(p["reach_final"]),
            "p_win_title": _round(p["win_title"]),
            "p_third_place": _round(p["bronze"]),
        })
    rows.sort(key=lambda r: r["p_win_title"], reverse=True)
    for rank, row in enumerate(rows, start=1):
        row["title_rank"] = rank

    fields = ["title_rank", "team", "group", "confederation", "elo",
              "p_qualify", "p_reach_r16", "p_reach_qf", "p_reach_sf",
              "p_reach_final", "p_win_title", "p_third_place"]
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def write_group_outcomes(mc, elo, conf, path):
    """Per-team group-stage finishing-position probabilities."""
    rows = []
    for team, p in mc["teams"].items():
        rows.append({
            "group": mc["group_of"][team],
            "team": team,
            "confederation": conf[team],
            "elo": int(round(elo[team])),
            "p_finish_1st": _round(p["finish_1st"]),
            "p_finish_2nd": _round(p["finish_2nd"]),
            "p_finish_3rd": _round(p["finish_3rd"]),
            "p_finish_4th": _round(p["finish_4th"]),
            "p_win_group": _round(p["finish_1st"]),
            "p_qualify_knockouts": _round(p["qualify"]),
        })
    # Order by group, then by qualification chance within the group.
    rows.sort(key=lambda r: (r["group"], -r["p_qualify_knockouts"]))

    fields = ["group", "team", "confederation", "elo", "p_finish_1st",
              "p_finish_2nd", "p_finish_3rd", "p_finish_4th", "p_win_group",
              "p_qualify_knockouts"]
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def write_team_strength(base_elo, squad_values, groups, conf, path):
    """Per-team strength breakdown: base Elo, squad value, the resulting
    adjustment and the adjusted Elo the simulation actually uses."""
    group_of = {t: g for g in GROUP_LETTERS for t in groups[g]}
    table = strength_table(base_elo, squad_values)
    rows = []
    for team, r in table.items():
        rows.append({
            "team": team,
            "group": group_of[team],
            "confederation": conf[team],
            "base_elo": int(round(r["base_elo"])),
            "squad_value_eur_millions": round(r["squad_value"], 2),
            "value_log_z": round(r["value_log_z"], 3),
            "elo_adjustment": round(r["elo_adjustment"], 1),
            "adjusted_elo": round(r["adjusted_elo"], 1),
        })
    rows.sort(key=lambda r: r["adjusted_elo"], reverse=True)
    for rank, row in enumerate(rows, start=1):
        row["strength_rank"] = rank

    fields = ["strength_rank", "team", "group", "confederation", "base_elo",
              "squad_value_eur_millions", "value_log_z", "elo_adjustment",
              "adjusted_elo"]
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def print_summary(mc):
    """Print the title-contender shortlist to the console."""
    ranked = sorted(mc["teams"].items(),
                    key=lambda kv: kv[1]["win_title"], reverse=True)
    print()
    print("=" * 62)
    print(f"  WORLD CUP 2026 - {mc['n']:,} Monte Carlo simulations "
          f"(seed {mc['seed']})")
    print("=" * 62)
    print(f"  {'Team':<20}{'Qualify':>9}{'Reach QF':>10}"
          f"{'Reach SF':>10}{'Win title':>11}")
    print("  " + "-" * 58)
    for team, p in ranked[:12]:
        print(f"  {team:<20}{p['qualify']:>8.1%}{p['reach_QF']:>10.1%}"
              f"{p['reach_SF']:>10.1%}{p['win_title']:>11.1%}")
    print("=" * 62)


def main():
    base_elo = load_elo()
    groups = load_groups()
    conf = load_confederations()
    third_place_table = load_third_place_table()
    squad_values = load_squad_values()
    known_results = load_known_results()
    match.HOST_ADVANTAGE_ENABLED = USE_HOST_ADVANTAGE
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"Host advantage: "
          f"{'ON' if USE_HOST_ADVANTAGE else 'OFF (neutral venues)'}.")

    # The simulation runs on `elo`: either the raw snapshot or the snapshot
    # adjusted by squad market value, depending on USE_SQUAD_ADJUSTMENT.
    if USE_SQUAD_ADJUSTMENT:
        elo = effective_elo(base_elo, squad_values)
        print(f"Squad market value folded into ratings "
              f"(weight {MARKET_VALUE_WEIGHT:.0f}).")
    else:
        elo = dict(base_elo)
        print("Running on raw Elo (squad adjustment off).")

    if known_results:
        print(f"Conditioning on {len(known_results)} completed group-stage "
              f"match(es) from live_results.csv.")
    else:
        print("No live results yet - running as a pre-tournament forecast.")

    print(f"Running {N_SIMULATIONS:,} tournament simulations "
          f"(seed {RANDOM_SEED})...")
    mc = run_monte_carlo(elo, groups, third_place_table,
                         n=N_SIMULATIONS, seed=RANDOM_SEED,
                         known_results=known_results)

    paths = {
        "match_predictions": os.path.join(OUTPUT_DIR, "match_predictions.csv"),
        "simulation_results": os.path.join(OUTPUT_DIR,
                                           "simulation_results.csv"),
        "group_outcomes": os.path.join(OUTPUT_DIR, "group_outcomes.csv"),
        "team_strength": os.path.join(OUTPUT_DIR, "team_strength.csv"),
    }
    n_matches = write_match_predictions(elo, groups, paths["match_predictions"])
    n_results = write_simulation_results(mc, elo, conf,
                                         paths["simulation_results"])
    n_groups = write_group_outcomes(mc, elo, conf, paths["group_outcomes"])
    n_strength = write_team_strength(base_elo, squad_values, groups, conf,
                                     paths["team_strength"])

    print(f"\nWrote 4 CSVs to {OUTPUT_DIR}:")
    print(f"  match_predictions.csv  ({n_matches} group fixtures)")
    print(f"  simulation_results.csv ({n_results} teams)")
    print(f"  group_outcomes.csv     ({n_groups} teams)")
    print(f"  team_strength.csv      ({n_strength} teams)")
    print_summary(mc)


if __name__ == "__main__":
    main()
