"""
apply_elo_updates.py - update elo_ratings.csv based on tournament results.

The simulation already conditions on played scores, but it kept using
pre-tournament Elo ratings to estimate remaining matches. That caused
clear underperformers (Turkey on 0 points) to still look like world
top-12 teams in qualify probability.

This script reads a frozen pre-tournament snapshot and live_results.csv,
applies standard FIFA-style Elo updates after every played match, and
writes the updated table back to elo_ratings.csv so the next simulation
pass uses ratings that reflect actual tournament form.

K factor uses the FIFA WC weight (60). Goal-difference scaling follows
the World Football Elo Ratings convention: 1.0 for one-goal wins, 1.5
for two, then +0.75 per extra goal beyond that.

Idempotent: re-runnable. Always derives the current ratings from the
pre-tournament snapshot + ALL finished matches, so running it twice
gives the same result.
"""

import csv
import os
import shutil

_DIR = os.path.dirname(os.path.abspath(__file__))
PRE = os.path.join(_DIR, "elo_ratings_pre_tournament.csv")
CURRENT = os.path.join(_DIR, "elo_ratings.csv")
LIVE = os.path.join(_DIR, "live_results.csv")

K_BASE = 60.0          # FIFA WC weight
HOST_ADV_ELO = 100.0   # match.host_advantage equivalent for the Elo update


def goal_diff_multiplier(diff):
    """Standard WFE goal difference multiplier."""
    d = abs(diff)
    if d <= 1:
        return 1.0
    if d == 2:
        return 1.5
    return 1.5 + (d - 2) * 0.75


def expected_score(rating_a, rating_b):
    """Logistic expectation that A beats B given Elo ratings."""
    return 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / 400.0))


def main():
    # First-run bootstrap: snapshot the current elo_ratings.csv as the
    # pre-tournament baseline so future runs are idempotent.
    if not os.path.exists(PRE):
        shutil.copyfile(CURRENT, PRE)
        print(f"Created pre-tournament snapshot: {PRE}")

    # Load pre-tournament ratings (the frozen baseline).
    ratings = {}
    with open(PRE) as f:
        for r in csv.DictReader(f):
            ratings[r["team"]] = float(r["elo"])

    # Load and order live results by finished sequence (file order is fine -
    # live_ingest writes them in API order which is roughly chronological).
    finished = []
    if os.path.exists(LIVE):
        with open(LIVE) as f:
            for r in csv.DictReader(f):
                if r.get("status") == "FINISHED":
                    finished.append(r)

    if not finished:
        print("No finished matches yet - ratings unchanged.")
        return

    # Apply updates in order. Each match shifts both teams.
    HOSTS = {"United States", "Canada", "Mexico"}
    for r in finished:
        home, away = r["home_team"], r["away_team"]
        if home not in ratings or away not in ratings:
            continue
        hg, ag = int(r["home_goals"]), int(r["away_goals"])
        home_adv = HOST_ADV_ELO if home in HOSTS else (
            -HOST_ADV_ELO if away in HOSTS else 0.0)
        exp_home = expected_score(ratings[home] + home_adv, ratings[away])
        if hg > ag:
            actual_home = 1.0
        elif hg < ag:
            actual_home = 0.0
        else:
            actual_home = 0.5
        mult = goal_diff_multiplier(hg - ag)
        delta_home = K_BASE * mult * (actual_home - exp_home)
        ratings[home] += delta_home
        ratings[away] -= delta_home   # symmetric update

    # Write updated ratings back to elo_ratings.csv.
    out_rows = sorted(
        [{"team": t, "elo": round(e)} for t, e in ratings.items()],
        key=lambda r: -r["elo"],
    )
    with open(CURRENT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["team", "elo"])
        w.writeheader()
        w.writerows(out_rows)

    # Verbose summary of biggest movers.
    pre_ratings = {}
    with open(PRE) as f:
        for r in csv.DictReader(f):
            pre_ratings[r["team"]] = float(r["elo"])
    deltas = sorted(
        [(t, ratings[t] - pre_ratings[t]) for t in ratings],
        key=lambda x: -abs(x[1]),
    )[:8]
    print(f"Applied Elo updates from {len(finished)} matches.\n")
    print("Biggest movers vs pre-tournament:")
    for t, d in deltas:
        print(f"  {t:<25}  {pre_ratings[t]:>4.0f} -> {ratings[t]:>4.0f}  "
              f"({d:+.0f})")


if __name__ == "__main__":
    main()
