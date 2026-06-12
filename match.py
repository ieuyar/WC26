"""
Step 3 - simulate a single match.

The chain, building on step 2 (model.py):
    Elo ratings -> expected goals (lambda) -> Poisson draw -> scoreline.

Each side's goal count is drawn from an independent Poisson distribution whose
mean is that side's expected goals. The Poisson is the standard model for
football scorelines: goals are rare, roughly independent events spread over the
match, which is exactly what a Poisson process describes.

Two entry points:
  simulate_group_match - group stage; a draw is a valid result.
  simulate_knockout    - knockout stage; always resolved to one winner via
                         extra time and, if needed, a penalty shootout.
"""

import numpy as np

from model import expected_goals

# Extra time is 30 minutes against 90 of regulation, so the expected-goals rate
# for the extra period is scaled to one third.
EXTRA_TIME_FRACTION = 30.0 / 90.0

# Penalty shootouts are modelled as a 50/50 coin flip. Shootouts are widely
# treated as near-random; keeping them unbiased avoids over-claiming precision.
PENALTY_WIN_PROB = 0.5

# Host nations receive this designation so callers can apply home advantage.
from data import HOST_NATIONS

# Master switch for host advantage. run_simulation.py flips this to model a
# neutral-venue tournament - host advantage off for all three host nations.
HOST_ADVANTAGE_ENABLED = True


def host_advantage(team_a, team_b):
    """Return 'A', 'B', or None - which side (if any) gets home advantage.

    A host nation gets the edge whenever it plays a non-host. If both sides are
    hosts (or neither is), the match is treated as neutral. When the module
    flag HOST_ADVANTAGE_ENABLED is False, every match is treated as neutral.
    """
    if not HOST_ADVANTAGE_ENABLED:
        return None
    a_host = team_a in HOST_NATIONS
    b_host = team_b in HOST_NATIONS
    if a_host and not b_host:
        return "A"
    if b_host and not a_host:
        return "B"
    return None


def simulate_group_match(elo_a, elo_b, home=None, rng=None):
    """Simulate a group-stage match. Return (goals_a, goals_b); draws allowed."""
    if rng is None:
        rng = np.random.default_rng()
    lam_a, lam_b = expected_goals(elo_a, elo_b, home)
    return int(rng.poisson(lam_a)), int(rng.poisson(lam_b))


def simulate_knockout(elo_a, elo_b, home=None, rng=None):
    """Simulate a knockout match; always returns a winner.

    Returns a dict with keys:
        winner      - 'A' or 'B'
        goals_a/b   - goals after regulation + extra time (shootout not counted)
        decided_by  - 'regulation', 'extra_time', or 'penalties'
    """
    if rng is None:
        rng = np.random.default_rng()
    lam_a, lam_b = expected_goals(elo_a, elo_b, home)

    goals_a = int(rng.poisson(lam_a))
    goals_b = int(rng.poisson(lam_b))
    if goals_a != goals_b:
        return {"winner": "A" if goals_a > goals_b else "B",
                "goals_a": goals_a, "goals_b": goals_b,
                "decided_by": "regulation"}

    # Level after 90: play 30 minutes of extra time.
    goals_a += int(rng.poisson(lam_a * EXTRA_TIME_FRACTION))
    goals_b += int(rng.poisson(lam_b * EXTRA_TIME_FRACTION))
    if goals_a != goals_b:
        return {"winner": "A" if goals_a > goals_b else "B",
                "goals_a": goals_a, "goals_b": goals_b,
                "decided_by": "extra_time"}

    # Still level: penalty shootout.
    winner = "A" if rng.random() < PENALTY_WIN_PROB else "B"
    return {"winner": winner, "goals_a": goals_a, "goals_b": goals_b,
            "decided_by": "penalties"}


def _poisson_pmf(k, lam):
    """Poisson probability mass P(X = k) for mean lam."""
    # exp(-lam) * lam**k / k!  -- computed in log space for numerical safety.
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    log_p = -lam + k * np.log(lam)
    for i in range(2, k + 1):
        log_p -= np.log(i)
    return float(np.exp(log_p))


def match_probabilities(elo_a, elo_b, home=None, max_goals=12):
    """Analytic outcome probabilities for a single match under the Poisson model.

    Rather than sampling, this sums the joint scoreline distribution exactly,
    so it gives stable predictions for the match_predictions export. Returns a
    dict with the expected goals, win/draw/win probabilities, and the single
    most likely scoreline.
    """
    lam_a, lam_b = expected_goals(elo_a, elo_b, home)
    pa = [_poisson_pmf(i, lam_a) for i in range(max_goals + 1)]
    pb = [_poisson_pmf(j, lam_b) for j in range(max_goals + 1)]

    p_a = p_draw = p_b = 0.0
    best_score, best_p = (0, 0), -1.0
    for i in range(max_goals + 1):
        for j in range(max_goals + 1):
            p = pa[i] * pb[j]
            if i > j:
                p_a += p
            elif i == j:
                p_draw += p
            else:
                p_b += p
            if p > best_p:
                best_p, best_score = p, (i, j)

    # Normalise: the truncation at max_goals drops a negligible tail.
    total = p_a + p_draw + p_b
    return {
        "lambda_a": lam_a,
        "lambda_b": lam_b,
        "p_a_win": p_a / total,
        "p_draw": p_draw / total,
        "p_b_win": p_b / total,
        "likely_score": f"{best_score[0]}-{best_score[1]}",
    }


if __name__ == "__main__":
    # Quick demonstration on a couple of plausible matchups.
    from data import load_elo
    elo = load_elo()
    rng = np.random.default_rng(2026)

    print("Sample group match - Brazil vs Morocco:")
    for _ in range(5):
        ga, gb = simulate_group_match(elo["Brazil"], elo["Morocco"], rng=rng)
        print(f"  Brazil {ga} - {gb} Morocco")

    print("\nAnalytic prediction - Brazil vs Morocco:")
    pr = match_probabilities(elo["Brazil"], elo["Morocco"])
    print(f"  Brazil win {pr['p_a_win']:.1%} | draw {pr['p_draw']:.1%} | "
          f"Morocco win {pr['p_b_win']:.1%} | likely {pr['likely_score']}")

    print("\nSample knockout - England vs Croatia:")
    for _ in range(5):
        r = simulate_knockout(elo["England"], elo["Croatia"], rng=rng)
        print(f"  winner {r['winner']}  {r['goals_a']}-{r['goals_b']}  "
              f"({r['decided_by']})")
