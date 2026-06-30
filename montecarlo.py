"""
Step 6 - Monte Carlo: run the whole tournament many times and tally outcomes.

A single tournament is one random sample. Repeating it thousands of times and
counting how often each thing happens turns those samples into probabilities:
run the World Cup 10,000 times, see a team lift the trophy 1,540 times, and its
estimated title chance is 15.4%.

The run is seeded, so the same seed always reproduces the same probabilities -
a deliberate choice for a model built around a dated, frozen Elo snapshot.
"""

import numpy as np

from tournament import GROUP_LETTERS, STAGE_ORDER, simulate_tournament

# Cumulative milestones reported per team. "Reaching" a stage means getting at
# least that far, so the numbers step down monotonically across the row.
MILESTONES = ["R32", "R16", "QF", "SF", "final", "champion"]


def run_monte_carlo(elo, groups, third_place_table, n=10000, seed=2026,
                    progress=True, known_results=None, known_ko_results=None):
    """Run `n` tournament simulations and aggregate the outcomes.

    Returns a dict:
        n            - number of simulations
        seed         - RNG seed used
        teams        - {team: {...probabilities...}} for all 48 teams
        group_of     - {team: group_letter}
    Each team's entry holds:
        reach_R32 ... reach_champion - P(reaching at least that stage)
        win_title    - P(champion)            (same as reach_champion)
        bronze       - P(winning the third-place play-off)
        finish_1st..finish_4th       - P(that group-stage finishing position)
        qualify      - P(advancing to the knockout stage) (= reach_R32)
    """
    rng = np.random.default_rng(seed)
    all_teams = [team for letter in GROUP_LETTERS for team in groups[letter]]
    group_of = {team: letter for letter in GROUP_LETTERS
                for team in groups[letter]}

    # Integer counters, converted to probabilities at the end.
    reach = {team: {m: 0 for m in MILESTONES} for team in all_teams}
    bronze = {team: 0 for team in all_teams}
    finish = {team: [0, 0, 0, 0] for team in all_teams}  # 1st,2nd,3rd,4th

    for i in range(n):
        result = simulate_tournament(elo, groups, third_place_table, rng,
                                     known_results=known_results,
                                     known_ko_results=known_ko_results)

        for team in all_teams:
            rank = STAGE_ORDER[result["stage"][team]]
            for milestone in MILESTONES:
                if rank >= STAGE_ORDER[milestone]:
                    reach[team][milestone] += 1

        bronze[result["third_place"]] += 1

        for letter in GROUP_LETTERS:
            for position, team in enumerate(result["group_standings"][letter]):
                finish[team][position] += 1

        if progress and (i + 1) % 1000 == 0:
            print(f"  simulated {i + 1:,} / {n:,} tournaments")

    teams = {}
    for team in all_teams:
        teams[team] = {
            "reach_R32": reach[team]["R32"] / n,
            "reach_R16": reach[team]["R16"] / n,
            "reach_QF": reach[team]["QF"] / n,
            "reach_SF": reach[team]["SF"] / n,
            "reach_final": reach[team]["final"] / n,
            "win_title": reach[team]["champion"] / n,
            "bronze": bronze[team] / n,
            "qualify": reach[team]["R32"] / n,
            "finish_1st": finish[team][0] / n,
            "finish_2nd": finish[team][1] / n,
            "finish_3rd": finish[team][2] / n,
            "finish_4th": finish[team][3] / n,
        }

    return {"n": n, "seed": seed, "teams": teams, "group_of": group_of}


if __name__ == "__main__":
    from data import load_elo, load_groups, load_third_place_table

    elo = load_elo()
    groups = load_groups()
    table = load_third_place_table()

    # A short run, just to show the aggregation working.
    print("Quick Monte Carlo check (500 simulations)...")
    mc = run_monte_carlo(elo, groups, table, n=500, progress=False)

    ranked = sorted(mc["teams"].items(),
                    key=lambda kv: kv[1]["win_title"], reverse=True)
    print(f"\n{'Team':<22}{'Qualify':>9}{'Reach SF':>10}{'Win title':>11}")
    for team, p in ranked[:10]:
        print(f"{team:<22}{p['qualify']:>8.1%}{p['reach_SF']:>10.1%}"
              f"{p['win_title']:>11.1%}")
