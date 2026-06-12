"""
compute_ranks.py - add per-engine rank columns to engine_scenarios.csv.

For each rating engine (Model, Elo, Squad value, FIFA ranking) we rank
the 48 teams by:
  - title odds (p_win_title)
  - qualification odds (p_qualify)
  - reach-QF odds (p_reach_qf)

These ranks let the dashboard show "Turkey is #14 by Model, #11 by Squad
value, #18 by Elo, #14 by FIFA ranking" - the cross-engine consensus view.

Output: engine_scenarios.csv (in-place, with new rank columns).
"""

import csv
import os

_DIR = os.path.dirname(os.path.abspath(__file__))
FILE = os.path.join(_DIR, "simulation_output", "engine_scenarios.csv")

RANK_BY = ["p_win_title", "p_qualify", "p_reach_qf", "p_win_group"]


def main():
    with open(FILE) as f:
        rows = list(csv.DictReader(f))
        fields = list(rows[0].keys())

    # Group by engine, rank each metric independently.
    by_engine = {}
    for r in rows:
        by_engine.setdefault(r["engine"], []).append(r)

    for engine, group_rows in by_engine.items():
        for metric in RANK_BY:
            # Sort descending by metric, assign rank 1..N (dense for ties).
            sorted_rows = sorted(group_rows,
                                  key=lambda r: float(r[metric]),
                                  reverse=True)
            prev_val = None
            prev_rank = 0
            actual_rank = 0
            for r in sorted_rows:
                actual_rank += 1
                val = float(r[metric])
                if prev_val is None or val != prev_val:
                    prev_rank = actual_rank
                    prev_val = val
                r[f"rank_{metric.replace('p_', '')}"] = prev_rank

    # Reorder columns: keep originals, append new ranks at the end.
    new_fields = fields + [f"rank_{m.replace('p_', '')}" for m in RANK_BY]

    with open(FILE, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=new_fields)
        w.writeheader()
        w.writerows(rows)

    print(f"Updated {FILE}: {len(rows)} rows, "
          f"added {len(RANK_BY)} rank columns per engine.")
    # Sanity check
    print("\nTurkey's ranks across engines:")
    for r in rows:
        if r["team"] == "Turkey":
            print(f"  {r['engine']:<15}  title #{r['rank_win_title']:<2}  "
                  f"qualify #{r['rank_qualify']:<2}  "
                  f"QF #{r['rank_reach_qf']:<2}")


if __name__ == "__main__":
    main()
