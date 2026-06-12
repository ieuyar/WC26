"""
compare_engines.py - run the tournament under three rating engines and compare.

Runs the full 10,000-simulation Monte Carlo three times - once on Elo, once on
squad market value, once on FIFA ranking (see rating_engines.py) - and lines
the championship probabilities up against the betting market, the benchmark
(de-vigged odds from market_odds.csv).

The market is a yardstick, not an engine: bookmaker odds are an outright-winner
output, not a per-team rating you can play a tournament from. The closing
summary reports which engine's title odds land closest to the market.

Output: simulation_output/engine_comparison.csv
"""

import csv
import os

from compare_market import load_market
from data import load_confederations, load_groups, load_third_place_table
from montecarlo import run_monte_carlo
from rating_engines import engines

_DIR = os.path.dirname(os.path.abspath(__file__))
N_SIMULATIONS = 10000
RANDOM_SEED = 2026

_KEY = {"Elo": "title_elo", "Squad value": "title_value",
        "FIFA ranking": "title_fifa"}


def main():
    groups = load_groups()
    conf = load_confederations()
    third_place_table = load_third_place_table()
    market, _ = load_market()
    team_group = {t: g for g in groups for t in groups[g]}

    title = {}
    for name, ratings in engines().items():
        print(f"Running {N_SIMULATIONS:,} simulations - {name} engine ...")
        mc = run_monte_carlo(ratings, groups, third_place_table,
                             n=N_SIMULATIONS, seed=RANDOM_SEED, progress=False)
        title[name] = {t: mc["teams"][t]["win_title"] for t in mc["teams"]}

    rows = []
    for team in title["Elo"]:
        rows.append({
            "team": team,
            "group": team_group[team],
            "confederation": conf[team],
            "title_elo": round(title["Elo"][team] * 100, 2),
            "title_value": round(title["Squad value"][team] * 100, 2),
            "title_fifa": round(title["FIFA ranking"][team] * 100, 2),
            "market": round(market.get(team, 0.0) * 100, 2),
        })
    rows.sort(key=lambda r: r["title_elo"], reverse=True)

    out = os.path.join(_DIR, "simulation_output", "engine_comparison.csv")
    with open(out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["team", "group",
            "confederation", "title_elo", "title_value", "title_fifa",
            "market"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nWrote {out}\n")

    print(f"{'Team':<14}{'Elo':>8}{'Value':>8}{'FIFA':>8}{'Market':>8}")
    print("-" * 46)
    for r in rows[:10]:
        print(f"{r['team']:<14}{r['title_elo']:>7.1f}{r['title_value']:>8.1f}"
              f"{r['title_fifa']:>8.1f}{r['market']:>8.1f}")

    print("\nWhich engine tracks the betting market closest?")
    for name in ("Elo", "Squad value", "FIFA ranking"):
        key = _KEY[name]
        mae = sum(abs(r[key] - r["market"]) for r in rows) / len(rows)
        print(f"  {name:<14} mean absolute gap vs market: {mae:.2f} pp")


if __name__ == "__main__":
    main()
