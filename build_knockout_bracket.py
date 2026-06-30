"""
build_knockout_bracket.py - per-engine bracket slot occupancy.

The Group Stage page shows qualification probability per team. The Knockout
Stage page needs something different: for each of the 31 knockout matches
(R32 -> R16 -> QF -> SF -> Final), which team is most likely to occupy each
of the two slots, and how confident are we?

Approach: run Monte Carlo per engine and, for each match in the bracket,
tally which team ends up in slot 'a' and slot 'b' (the bracket position,
not the winner). After N simulations these tallies become slot-occupancy
probabilities. We keep the top-3 candidates per slot to keep the output
compact while still showing uncertainty for slots that haven't fully resolved
(e.g. 'France 72% / Belgium 11% / Netherlands 8% to win Group I').

Played-match conditioning is applied the same way as run_engines.py: locked
results carry their real score so the bracket already reflects what's
actually happened in MD1-MD3.

Output: simulation_output/knockout_bracket.csv with columns
  engine,match_no,round,slot,rank,team,probability
"""

import csv
import os
from collections import Counter, defaultdict

import numpy as np

from data import (load_elo, load_groups, load_known_ko_results,
                  load_squad_values, load_third_place_table)
from rating_engines import engines as pure_engines
from squad_strength import effective_elo
from tournament import (FINAL_MATCH, QUARTER_FINALS, ROUND_OF_16, ROUND_OF_32,
                        SEMI_FINALS, THIRD_PLACE_MATCH, simulate_tournament)

try:
    from run_simulation import load_known_results
except ImportError:
    def load_known_results():
        return []


_DIR = os.path.dirname(os.path.abspath(__file__))
N_SIMULATIONS = 10000
RANDOM_SEED = 2026
TOP_K_PER_SLOT = 3  # keep the 3 most likely teams per slot

# Round label for each match number; used for grouping on the dashboard.
_ROUND_BY_MATCH = {}
for m in ROUND_OF_32:
    _ROUND_BY_MATCH[m] = "R32"
for m in ROUND_OF_16:
    _ROUND_BY_MATCH[m] = "R16"
for m in QUARTER_FINALS:
    _ROUND_BY_MATCH[m] = "QF"
for m in SEMI_FINALS:
    _ROUND_BY_MATCH[m] = "SF"
_ROUND_BY_MATCH[THIRD_PLACE_MATCH] = "3rd"
_ROUND_BY_MATCH[FINAL_MATCH] = "F"


def _tally_one_engine(name, ratings, groups, third_place_table,
                     known_results, known_ko_results, n):
    """Run n tournaments for one engine, return slot-occupancy AND matchup
    counters.

    Returns:
        slot_counts:    {(match_no, slot_letter): Counter({team: count})}
        matchup_counts: {match_no: Counter({(team_a, team_b): count})}
                        where (team_a, team_b) is the alphabetically-ordered
                        pair so each unique pairing maps to one key.
        winner_counts:  {(match_no, team_a, team_b): Counter({winner: count})}
    """
    rng = np.random.default_rng(RANDOM_SEED)
    slot_counts = defaultdict(Counter)
    matchup_counts = defaultdict(Counter)
    winner_counts = defaultdict(Counter)

    print(f"Running {n:,} simulations - {name} engine ...")
    for i in range(n):
        result = simulate_tournament(ratings, groups, third_place_table, rng,
                                     known_results=known_results,
                                     known_ko_results=known_ko_results)
        for match_no, slots in result["knockout"].items():
            a, b = slots["a"], slots["b"]
            slot_counts[(match_no, "a")][a] += 1
            slot_counts[(match_no, "b")][b] += 1
            pair = tuple(sorted([a, b]))
            matchup_counts[match_no][pair] += 1
            winner_counts[(match_no, pair[0], pair[1])][slots["winner"]] += 1
    return slot_counts, matchup_counts, winner_counts


def _emit_slot_rows(engine_name, slot_counts, n):
    """Convert raw slot counters to top-K rows."""
    rows = []
    for (match_no, slot), counter in slot_counts.items():
        top = counter.most_common(TOP_K_PER_SLOT)
        for rank, (team, count) in enumerate(top, start=1):
            rows.append({
                "engine": engine_name,
                "match_no": match_no,
                "round": _ROUND_BY_MATCH[match_no],
                "slot": slot,
                "rank": rank,
                "team": team,
                "probability": round(count / n, 4),
            })
    rows.sort(key=lambda r: (r["match_no"], r["slot"], r["rank"]))
    return rows


def _emit_matchup_rows(engine_name, matchup_counts, winner_counts, n,
                       top_k=3):
    """For each knockout match, emit the top-K most likely matchups with
    their occurrence probability and W/L split."""
    rows = []
    for match_no, counter in matchup_counts.items():
        top = counter.most_common(top_k)
        for rank, ((team_a, team_b), pair_count) in enumerate(top, start=1):
            winners = winner_counts[(match_no, team_a, team_b)]
            wa = winners.get(team_a, 0)
            wb = winners.get(team_b, 0)
            rows.append({
                "engine": engine_name,
                "match_no": match_no,
                "round": _ROUND_BY_MATCH[match_no],
                "rank": rank,
                "team_a": team_a,
                "team_b": team_b,
                "matchup_probability": round(pair_count / n, 4),
                "p_team_a_advance": round(wa / pair_count, 4) if pair_count else 0,
                "p_team_b_advance": round(wb / pair_count, 4) if pair_count else 0,
            })
    rows.sort(key=lambda r: (r["match_no"], r["rank"]))
    return rows


def main():
    groups = load_groups()
    third_place_table = load_third_place_table()
    known_results = load_known_results()
    known_ko_results = load_known_ko_results()
    if known_results or known_ko_results:
        print(f"Conditioning each engine on {len(known_results)} group-stage "
              f"+ {len(known_ko_results)} KO matches from live_results.csv.\n")

    pure = pure_engines()
    engines = {
        "Model": effective_elo(load_elo(), load_squad_values()),
        "Elo": pure["Elo"],
        "Squad value": pure["Squad value"],
        "FIFA ranking": pure["FIFA ranking"],
    }

    slot_rows = []
    matchup_rows = []
    for name, ratings in engines.items():
        slot_counts, matchup_counts, winner_counts = _tally_one_engine(
            name, ratings, groups, third_place_table,
            known_results, known_ko_results, N_SIMULATIONS)
        slot_rows.extend(_emit_slot_rows(name, slot_counts, N_SIMULATIONS))
        matchup_rows.extend(_emit_matchup_rows(name, matchup_counts,
                                               winner_counts, N_SIMULATIONS))

    SO = os.path.join(_DIR, "simulation_output")
    bracket_out = os.path.join(SO, "knockout_bracket.csv")
    with open(bracket_out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["engine", "match_no", "round",
            "slot", "rank", "team", "probability"])
        writer.writeheader()
        writer.writerows(slot_rows)
    print(f"\nWrote {bracket_out} ({len(slot_rows)} rows: 4 engines x ~62 slots "
          f"x <=3 candidates)")

    matches_out = os.path.join(SO, "knockout_match_predictions.csv")
    with open(matches_out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["engine", "match_no", "round",
            "rank", "team_a", "team_b", "matchup_probability",
            "p_team_a_advance", "p_team_b_advance"])
        writer.writeheader()
        writer.writerows(matchup_rows)
    print(f"Wrote {matches_out} ({len(matchup_rows)} rows: 4 engines x 31 KO "
          f"matches x top-3 matchups)")


if __name__ == "__main__":
    main()
