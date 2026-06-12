"""
squad_strength.py - turn Transfermarkt squad market values into an Elo nudge.

The simulation runs on Elo ratings. This module lets a second, independent
signal - how much each squad is worth on the transfer market - adjust those
ratings before a tournament is simulated.

Method (deliberately simple and transparent):
  1. Take each team's total squad market value (squad_values.csv).
  2. Work in log space: values span a ~100x range (Jordan ~16m to England
     ~1.6bn), so a raw scale would be swallowed by the giants.
  3. Convert each log-value to a z-score across the 48 teams.
  4. elo_adjustment = MARKET_VALUE_WEIGHT * z, clamped to a safe range.
  5. adjusted_elo = base_elo + elo_adjustment.

Because the z-score is mean-zero across the field, the adjustments sum to ~0:
this redistributes strength toward the market's view rather than inflating the
pool. MARKET_VALUE_WEIGHT is the single knob - raise it to let the transfer
market count for more, lower it to keep Elo dominant.

Caveats (documented openly):
  - Elo and squad value both proxy team strength, so blending them
    double-counts a little by design. The weight is kept modest so Elo stays
    the spine of the model.
  - The value snapshot (squad_values.csv) is provisional: as of 20 May 2026
    not all final 26-man squads were set, so squad sizes vary and totals will
    shift. Refresh the CSV when final squads lock (~1 June) and re-run.
"""

import math

from data import load_elo, load_squad_values

# How strongly the market valuation pulls the Elo rating. At this value a team
# one standard deviation above the field in (log) squad value gains ~40 Elo;
# one SD below loses ~40. Tunable: higher = market counts for more.
MARKET_VALUE_WEIGHT = 40.0

# Safety rail: no single team's adjustment may exceed this magnitude, so a
# provisional-data outlier cannot swing the simulation wildly.
MAX_ADJUSTMENT = 100.0


def _log_zscores(squad_values):
    """Return {team: z-score of log(market value)} across all teams."""
    teams = list(squad_values)
    logs = {t: math.log(squad_values[t]) for t in teams}
    mean = sum(logs.values()) / len(logs)
    std = math.sqrt(sum((v - mean) ** 2 for v in logs.values()) / len(logs))
    if std == 0:
        return {t: 0.0 for t in teams}
    return {t: (logs[t] - mean) / std for t in teams}


def compute_adjustments(squad_values, weight=MARKET_VALUE_WEIGHT):
    """Return {team: elo_adjustment} derived from squad market values."""
    z = _log_zscores(squad_values)
    adjustments = {}
    for team, z_score in z.items():
        delta = weight * z_score
        adjustments[team] = max(-MAX_ADJUSTMENT, min(MAX_ADJUSTMENT, delta))
    return adjustments


def effective_elo(base_elo, squad_values, weight=MARKET_VALUE_WEIGHT):
    """Return {team: adjusted_elo} = base Elo + market-value adjustment."""
    adj = compute_adjustments(squad_values, weight)
    return {team: base_elo[team] + adj.get(team, 0.0) for team in base_elo}


def strength_table(base_elo, squad_values, weight=MARKET_VALUE_WEIGHT):
    """Per-team breakdown for reporting and export.

    Returns {team: {base_elo, squad_value, value_log_z, elo_adjustment,
    adjusted_elo}}.
    """
    z = _log_zscores(squad_values)
    adj = compute_adjustments(squad_values, weight)
    table = {}
    for team in base_elo:
        table[team] = {
            "base_elo": base_elo[team],
            "squad_value": squad_values[team],
            "value_log_z": z.get(team, 0.0),
            "elo_adjustment": adj.get(team, 0.0),
            "adjusted_elo": base_elo[team] + adj.get(team, 0.0),
        }
    return table


if __name__ == "__main__":
    base = load_elo()
    values = load_squad_values()
    table = strength_table(base, values)

    ranked = sorted(table.items(), key=lambda kv: kv[1]["adjusted_elo"],
                    reverse=True)
    print(f"Squad-value Elo adjustment (weight {MARKET_VALUE_WEIGHT:.0f})")
    print(f"{'Team':<22}{'BaseElo':>8}{'Value m':>10}{'Adj':>7}{'AdjElo':>8}")
    print("-" * 55)
    for team, r in ranked:
        print(f"{team:<22}{r['base_elo']:>8.0f}{r['squad_value']:>10.1f}"
              f"{r['elo_adjustment']:>+7.0f}{r['adjusted_elo']:>8.0f}")

    total_adj = sum(r["elo_adjustment"] for r in table.values())
    print("-" * 55)
    print(f"Sum of adjustments: {total_adj:+.2f} (should be ~0)")
