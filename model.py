"""
WC2026 predictive model — Step 2: Elo ratings -> expected goals (lambda).

The pipeline for any single match:
    Elo difference  ->  win expectancy We  ->  expected goals for each side.

We is the standard World Football Elo win-expectancy:
    We = 1 / (10^(-dr/400) + 1)
where dr = (elo_A - elo_B), plus a home-advantage bonus if applicable.

Expected goals split a typical match goal budget by relative strength:
    lambda_A = TOTAL_GOALS * We
    lambda_B = TOTAL_GOALS * (1 - We)
These lambdas feed a Poisson model in Step 3 to produce scorelines.
"""

# --- Model constants (each one is defensible; document them on the dashboard) ---
TOTAL_GOALS = 2.7   # avg combined goals per international match (~2.5-2.8 typical)
HOME_ADV = 100      # Elo points added to a host/home side (standard Elo value)


def win_expectancy(elo_a, elo_b, home=None):
    """Win expectancy of A vs B. `home` can be 'A', 'B', or None (neutral)."""
    dr = elo_a - elo_b
    if home == 'A':
        dr += HOME_ADV
    elif home == 'B':
        dr -= HOME_ADV
    return 1.0 / (10 ** (-dr / 400.0) + 1.0)


def expected_goals(elo_a, elo_b, home=None):
    """Return (lambda_A, lambda_B): expected goals for each side."""
    we = win_expectancy(elo_a, elo_b, home)
    lam_a = TOTAL_GOALS * we
    lam_b = TOTAL_GOALS * (1.0 - we)
    return lam_a, lam_b


if __name__ == '__main__':
    import pandas as pd
    elo = pd.read_csv('elo_ratings.csv').set_index('team')['elo'].to_dict()

    # Sanity tests on real Group-stage matchups from the draw
    tests = [
        ('Brazil', 'Morocco', None),       # strong vs solid
        ('Spain', 'Cape Verde', None),     # heavy favorite
        ('England', 'Croatia', None),      # close, both strong
        ('Argentina', 'Argentina', None),  # identical -> must be symmetric
        ('Mexico', 'South Africa', 'A'),   # host edge (opener)
    ]
    print(f"{'Match':<34}{'We(A)':>7}{'xG_A':>7}{'xG_B':>7}")
    print('-' * 55)
    for a, b, home in tests:
        we = win_expectancy(elo[a], elo[b], home)
        la, lb = expected_goals(elo[a], elo[b], home)
        label = f"{a} vs {b}" + (f" (host {home})" if home else "")
        print(f"{label:<34}{we:>7.3f}{la:>7.2f}{lb:>7.2f}")
