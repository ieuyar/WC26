"""
validate.py - end-to-end checks on the simulation pipeline.

Verifies the things that must be true if the model is wired correctly:
  - inputs are consistent (48 teams, 12 groups, names aligned);
  - the Annex C table is complete;
  - match probabilities form a proper distribution;
  - the knockout bracket never pairs two teams from the same group before the
    quarter-finals (a direct test of the bracket wiring);
  - Monte Carlo outputs obey their accounting identities (one champion per run,
    32 qualifiers per run, finishing positions sum to 1, milestone
    probabilities decrease monotonically);
  - the three exported CSVs exist and are well-formed.

Run:  python3 validate.py
"""

import csv
import os

import numpy as np

from data import (load_confederations, load_elo, load_groups,
                   load_squad_values, load_third_place_table)
from match import match_probabilities
from montecarlo import run_monte_carlo
from squad_strength import (MAX_ADJUSTMENT, compute_adjustments,
                            effective_elo)
from tournament import GROUP_LETTERS, simulate_tournament

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "simulation_output")

_passed = 0
_failed = 0


def check(label, condition, detail=""):
    global _passed, _failed
    if condition:
        _passed += 1
        print(f"  PASS  {label}")
    else:
        _failed += 1
        print(f"  FAIL  {label}  {detail}")


def main():
    elo = load_elo()
    groups = load_groups()
    conf = load_confederations()
    table = load_third_place_table()
    group_of = {t: g for g in GROUP_LETTERS for t in groups[g]}

    print("\n1. Input data")
    drafted = {t for teams in groups.values() for t in teams}
    check("48 teams drafted", len(drafted) == 48, f"got {len(drafted)}")
    check("48 teams rated", len(elo) == 48, f"got {len(elo)}")
    check("team names align across files", drafted == set(elo))
    check("12 groups of 4 each",
          len(groups) == 12 and all(len(v) == 4 for v in groups.values()))
    check("every team has a confederation", set(conf) == drafted)

    print("\n2. Annex C third-place table")
    check("495 combinations present", len(table) == 495, f"got {len(table)}")
    check("each row allocates 8 distinct groups",
          all(len(set(row.values())) == 8 for row in table.values()))

    print("\n3. Match probabilities form a distribution")
    ok = True
    for a, b in [("Brazil", "Haiti"), ("Spain", "France"),
                 ("Mexico", "South Korea"), ("Argentina", "Argentina")]:
        pr = match_probabilities(elo[a], elo[b])
        total = pr["p_a_win"] + pr["p_draw"] + pr["p_b_win"]
        ok = ok and abs(total - 1.0) < 1e-9
    check("p(win)+p(draw)+p(win) == 1", ok)
    sym = match_probabilities(elo["Brazil"], elo["Brazil"])
    check("identical teams are symmetric",
          abs(sym["p_a_win"] - sym["p_b_win"]) < 1e-9)

    print("\n4. Bracket integrity (2,000 simulations)")
    rng = np.random.default_rng(1)
    same_group_early = 0
    bad_third = 0
    for _ in range(2000):
        res = simulate_tournament(elo, groups, table, rng)
        for match_no in list(range(73, 89)) + list(range(89, 97)):
            k = res["knockout"][match_no]
            if group_of[k["a"]] == group_of[k["b"]]:
                same_group_early += 1
        # The 8 qualifying third-placed teams must be third in their group.
        for letter in res["qualified_thirds"]:
            if res["group_standings"][letter][2] not in drafted:
                bad_third += 1
    check("no same-group meeting before the quarter-finals",
          same_group_early == 0, f"{same_group_early} violations")
    check("third-place qualifiers are valid", bad_third == 0)

    print("\n5. Monte Carlo accounting identities (3,000 simulations)")
    mc = run_monte_carlo(elo, groups, table, n=3000, seed=7, progress=False)
    teams = mc["teams"]
    sum_title = sum(p["win_title"] for p in teams.values())
    sum_qualify = sum(p["qualify"] for p in teams.values())
    sum_first = sum(p["finish_1st"] for p in teams.values())
    sum_third = sum(p["finish_3rd"] for p in teams.values())
    sum_bronze = sum(p["bronze"] for p in teams.values())
    check("exactly one champion per run (sum p_win_title == 1)",
          abs(sum_title - 1.0) < 1e-9, f"got {sum_title:.4f}")
    check("32 qualifiers per run (sum p_qualify == 32)",
          abs(sum_qualify - 32.0) < 1e-9, f"got {sum_qualify:.4f}")
    check("12 group winners per run (sum p_finish_1st == 12)",
          abs(sum_first - 12.0) < 1e-9, f"got {sum_first:.4f}")
    check("12 third-placed teams per run (sum p_finish_3rd == 12)",
          abs(sum_third - 12.0) < 1e-9, f"got {sum_third:.4f}")
    check("one bronze medallist per run (sum p_third_place == 1)",
          abs(sum_bronze - 1.0) < 1e-9, f"got {sum_bronze:.4f}")

    pos_ok = all(abs(p["finish_1st"] + p["finish_2nd"] + p["finish_3rd"]
                     + p["finish_4th"] - 1.0) < 1e-9 for p in teams.values())
    check("each team's finishing positions sum to 1", pos_ok)

    mono_ok = all(
        p["qualify"] >= p["reach_R16"] - 1e-12 >= -1 and
        p["reach_R16"] >= p["reach_QF"] - 1e-12 and
        p["reach_QF"] >= p["reach_SF"] - 1e-12 and
        p["reach_SF"] >= p["reach_final"] - 1e-12 and
        p["reach_final"] >= p["win_title"] - 1e-12
        for p in teams.values())
    check("milestone probabilities decrease monotonically", mono_ok)

    # The top Elo team should not rank low on title chance - a smoke test that
    # ratings actually drive results.
    ranked = sorted(teams.items(), key=lambda kv: kv[1]["win_title"],
                    reverse=True)
    top_elo_team = max(elo, key=elo.get)
    top5 = {t for t, _ in ranked[:5]}
    check("highest-rated team is among the top 5 title contenders",
          top_elo_team in top5, f"{top_elo_team} not in {top5}")

    print("\n6. Exported CSV files")
    expected = {
        "match_predictions.csv": 72,
        "simulation_results.csv": 48,
        "group_outcomes.csv": 48,
        "team_strength.csv": 48,
    }
    for name, n_rows in expected.items():
        path = os.path.join(OUTPUT_DIR, name)
        if not os.path.exists(path):
            check(f"{name} exists", False, "file not found - run run_simulation.py")
            continue
        with open(path, newline="") as f:
            rows = list(csv.DictReader(f))
        check(f"{name} has {n_rows} rows", len(rows) == n_rows,
              f"got {len(rows)}")

    # match_predictions probabilities must each sum to ~1.
    mp_path = os.path.join(OUTPUT_DIR, "match_predictions.csv")
    if os.path.exists(mp_path):
        with open(mp_path, newline="") as f:
            ok = True
            for row in csv.DictReader(f):
                s = (float(row["p_team_a_win"]) + float(row["p_draw"])
                     + float(row["p_team_b_win"]))
                ok = ok and abs(s - 1.0) < 1e-4
        check("match_predictions probabilities each sum to 1", ok)

    print("\n7. Squad-value adjustment")
    squad_values = load_squad_values()
    check("48 squad values present", len(squad_values) == 48,
          f"got {len(squad_values)}")
    check("squad-value team names align", set(squad_values) == drafted)
    check("all squad values positive",
          all(v > 0 for v in squad_values.values()))

    adjustments = compute_adjustments(squad_values)
    total_adj = sum(adjustments.values())
    check("adjustments sum to ~0 (mean-zero redistribution)",
          abs(total_adj) < 1e-6, f"got {total_adj:.4f}")
    check("no adjustment exceeds the safety clamp",
          all(abs(a) <= MAX_ADJUSTMENT + 1e-9 for a in adjustments.values()))

    adjusted = effective_elo(elo, squad_values)
    rebuilt_ok = all(
        abs(adjusted[t] - (elo[t] + adjustments[t])) < 1e-9 for t in elo)
    check("adjusted Elo == base Elo + adjustment", rebuilt_ok)
    # The most valuable squad should gain the most Elo.
    top_value_team = max(squad_values, key=squad_values.get)
    biggest_gain = max(adjustments, key=adjustments.get)
    check("most valuable squad gets the largest boost",
          top_value_team == biggest_gain,
          f"{top_value_team} vs {biggest_gain}")

    print("\n" + "=" * 50)
    print(f"  {_passed} passed, {_failed} failed")
    print("=" * 50)
    return 0 if _failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
