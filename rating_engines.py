"""
rating_engines.py - three interchangeable team-rating sources for the simulator.

The match engine turns a rating DIFFERENCE into a win probability via the Elo
curve, so any rating source has to be expressed on the Elo scale to be
comparable. Each engine below does that:

  - Elo          : the dated eloratings.net snapshot, used as-is.
  - Squad value  : log Transfermarkt squad value, z-scored across the 48 teams
                   and mapped onto the Elo scale.
  - FIFA ranking : FIFA ranking points, z-scored and mapped onto the Elo scale.

Mapping every source to the same mean and spread as the real Elo ratings keeps
the Poisson match model calibrated identically - so a difference between
engines reflects a genuine difference in how the SOURCE ranks teams, not a
scale artefact.

These engines are deliberately "pure" - one rating source each. The project's
production model (run_simulation.py) is a blend: Elo nudged by squad value.
This module exists for the side-by-side engine comparison (compare_engines.py).
"""

import math

from data import load_elo, load_fifa_rankings, load_squad_values


def _mean_std(values):
    n = len(values)
    mean = sum(values) / n
    std = math.sqrt(sum((v - mean) ** 2 for v in values) / n)
    return mean, std


def _to_elo_scale(metric, elo_mean, elo_std, log=False):
    """Z-score `metric` across teams, then map onto the Elo mean/spread."""
    xs = {t: (math.log(metric[t]) if log else metric[t]) for t in metric}
    m, s = _mean_std(list(xs.values()))
    if s == 0:
        return {t: elo_mean for t in xs}
    return {t: elo_mean + ((xs[t] - m) / s) * elo_std for t in xs}


def engines():
    """Return {engine_name: {team: rating}} for the three rating sources."""
    elo = load_elo()
    elo_mean, elo_std = _mean_std(list(elo.values()))
    return {
        "Elo": dict(elo),
        "Squad value": _to_elo_scale(load_squad_values(), elo_mean, elo_std,
                                     log=True),
        "FIFA ranking": _to_elo_scale(load_fifa_rankings(), elo_mean, elo_std),
    }


if __name__ == "__main__":
    eng = engines()
    order = sorted(eng["Elo"], key=lambda t: -eng["Elo"][t])
    print(f"{'Team':<22}{'Elo':>9}{'Value':>9}{'FIFA':>9}")
    print("-" * 49)
    for t in order[:15]:
        print(f"{t:<22}{eng['Elo'][t]:>9.0f}{eng['Squad value'][t]:>9.0f}"
              f"{eng['FIFA ranking'][t]:>9.0f}")
