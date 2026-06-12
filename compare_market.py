"""
compare_market.py - model vs market.

Compares the simulation's championship probabilities against bookmaker odds, a
benchmark of "what the market thinks". Two honest steps:

  1. Bookmaker odds carry a house margin, so the raw implied probabilities sum
     to well over 100% (the "overround"/"vig"). They are normalised to sum to
     100% - the de-vigged market probability - before any comparison.
  2. The comparison is a *benchmark, not a correction*. The point is to see
     where an independent Elo + squad-value model agrees with market consensus
     and where it takes a genuinely different view. Divergence is the finding,
     not an error to tune away.

Input : market_odds.csv          - dated odds snapshot (DraftKings via
                                    RotoWire, 18 May 2026), American odds.
Input : simulation_output/simulation_results.csv - the model's title odds.
Output: simulation_output/model_vs_market.csv
"""

import csv
import os

_DIR = os.path.dirname(os.path.abspath(__file__))


def _path(name):
    return os.path.join(_DIR, name)


def load_market():
    """Return ({team: de-vigged probability}, raw_overround_total)."""
    raw = {}
    with open(_path("market_odds.csv"), newline="") as f:
        for row in csv.DictReader(f):
            odds = float(row["american_odds"])
            # American odds (positive) -> implied probability, margin included.
            raw[row["team"]] = 100.0 / (odds + 100.0)
    total = sum(raw.values())
    de_vigged = {team: p / total for team, p in raw.items()}
    return de_vigged, total


def load_model():
    """Return {team: model championship probability}."""
    model = {}
    path = _path(os.path.join("simulation_output", "simulation_results.csv"))
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            model[row["team"]] = float(row["p_win_title"])
    return model


def main():
    market, overround = load_market()
    model = load_model()

    rows = []
    for team, m in model.items():
        k = market.get(team, 0.0)
        rows.append({
            "team": team,
            "model_win_pct": round(m * 100, 2),
            "market_win_pct": round(k * 100, 2),
            "difference": round((m - k) * 100, 2),
            "leans": ("model bullish" if m > k + 1e-9 else
                      "market bullish" if k > m + 1e-9 else "agree"),
        })
    rows.sort(key=lambda r: r["model_win_pct"], reverse=True)

    out = _path(os.path.join("simulation_output", "model_vs_market.csv"))
    with open(out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["team", "model_win_pct",
                                "market_win_pct", "difference", "leans"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"Bookmaker overround: raw implied probabilities summed to "
          f"{overround * 100:.1f}% — normalised to 100% for comparison.")
    print(f"Wrote {out}\n")
    print(f"{'Team':<16}{'Model':>9}{'Market':>9}{'Diff':>9}")
    print("-" * 43)
    for r in rows[:12]:
        print(f"{r['team']:<16}{r['model_win_pct']:>8.1f}%"
              f"{r['market_win_pct']:>8.1f}%{r['difference']:>+8.1f}")

    print("\nBiggest model-vs-market disagreements:")
    for r in sorted(rows, key=lambda r: abs(r["difference"]),
                    reverse=True)[:6]:
        print(f"  {r['team']:<16} model {r['model_win_pct']:>5.1f}%   "
              f"market {r['market_win_pct']:>5.1f}%   ({r['difference']:+.1f})")


if __name__ == "__main__":
    main()
