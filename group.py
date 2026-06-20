"""
Step 4 - simulate a four-team group and rank it with FIFA tiebreakers.

Each group plays a single round robin: six matches, every team meeting every
other once. Three points for a win, one for a draw.

Final ranking follows the official FIFA World Cup 2026 group-stage criteria:
  1. Points across all group matches.
  When two or more teams are level on points:
  2. Head-to-head points (mini-league of tied teams only).
  3. Head-to-head goal difference (in those mini-league matches).
  4. Head-to-head goals scored (in those mini-league matches).
  5. Overall group goal difference (across all group matches).
  6. Overall group goals scored (across all group matches).
  7. Fair play (yellow/red cards) - skipped, no disciplinary data.
  8. Drawing of lots.

Note on order: this is the post-2022 FIFA rule, where head-to-head is applied
BEFORE overall goal difference. The earlier convention (GD first, then H2H) was
retired - it allowed teams that had lost to each direct rival to advance on
goal-difference padding. The change matters in cases like Group D 2026: Turkey
finished tied with their direct rivals but had lost both head-to-head meetings,
making them 4th under the current rules.

For the 3rd-place ranking across groups (used to fill the 8 best-3rd spots),
teams in different groups never played each other, so the comparison falls
straight through to overall GD/GF. That logic lives in third_place.py - this
module only ranks within a single group.
"""

from itertools import combinations

from match import simulate_group_match, host_advantage

WIN_POINTS = 3
DRAW_POINTS = 1


def _blank_record():
    return {"played": 0, "won": 0, "drawn": 0, "lost": 0,
            "gf": 0, "ga": 0, "gd": 0, "points": 0}


def _apply_result(record, goals_for, goals_against):
    """Update one team's record with a single match result."""
    record["played"] += 1
    record["gf"] += goals_for
    record["ga"] += goals_against
    record["gd"] = record["gf"] - record["ga"]
    if goals_for > goals_against:
        record["won"] += 1
        record["points"] += WIN_POINTS
    elif goals_for == goals_against:
        record["drawn"] += 1
        record["points"] += DRAW_POINTS
    else:
        record["lost"] += 1


def _points_key(record):
    """Sort key for criterion 1: points only."""
    return (record["points"],)


def _h2h_key(record):
    """Sort key for criteria 2-4: head-to-head points, GD, GF."""
    return (record["points"], record["gd"], record["gf"])


def _overall_gd_key(record):
    """Sort key for criteria 5-6: overall group GD then GF."""
    return (record["gd"], record["gf"])


def _overall_key(record):
    """Sort key for cross-group comparisons (e.g. ranking the 12 third-placed
    teams against each other). Uses points -> overall GD -> overall GF.

    This is intentionally different from the within-group tiebreaker: teams in
    different groups never played each other, so head-to-head is undefined and
    we go straight to the overall criteria. tournament.py imports this for the
    best-third-place ranking.
    """
    return (record["points"], record["gd"], record["gf"])


def _tied_blocks(ordered, key_of):
    """Split an already-sorted list into runs of teams sharing the same key."""
    blocks = []
    i = 0
    while i < len(ordered):
        j = i
        while j + 1 < len(ordered) and key_of(ordered[j + 1]) == key_of(ordered[i]):
            j += 1
        blocks.append(ordered[i:j + 1])
        i = j + 1
    return blocks


def _h2h_records(block, results):
    """Build head-to-head-only records for a set of tied teams.

    `results` maps (team_a, team_b) -> (goals_a, goals_b) for all six group
    matches; only the matches *between teams in `block`* are counted here.
    """
    in_block = set(block)
    h2h = {team: _blank_record() for team in block}
    for (team_a, team_b), (goals_a, goals_b) in results.items():
        if team_a in in_block and team_b in in_block:
            _apply_result(h2h[team_a], goals_a, goals_b)
            _apply_result(h2h[team_b], goals_b, goals_a)
    return h2h


def _break_overall_gd(block, stats, rng):
    """Apply criteria 5-6 (overall GD, overall GF), then lots."""
    key_of = lambda team: _overall_gd_key(stats[team])
    ordered = sorted(block, key=key_of, reverse=True)
    final = []
    for sub in _tied_blocks(ordered, key_of):
        if len(sub) == 1:
            final.append(sub[0])
        else:
            # Still level after overall GD/GF: drawing of lots.
            sub = list(sub)
            rng.shuffle(sub)
            final.extend(sub)
    return final


def _break_h2h(block, stats, results, rng):
    """Order teams tied on points using head-to-head (criteria 2-4), then
    falling back to overall GD/GF (criteria 5-6), then lots.

    Important: per FIFA 2022+ rules, head-to-head is applied BEFORE overall
    goal difference. If three teams are tied, a mini-league is built from
    their matches against each other only. If that mini-league still leaves
    some teams tied, those still-tied teams are separated by overall GD/GF
    (computed from their full group record, not the mini-league).
    """
    h2h = _h2h_records(block, results)
    key_of = lambda team: _h2h_key(h2h[team])
    ordered = sorted(block, key=key_of, reverse=True)

    final = []
    for sub in _tied_blocks(ordered, key_of):
        if len(sub) == 1:
            final.append(sub[0])
        else:
            # Head-to-head couldn't split them; use overall GD/GF, then lots.
            final.extend(_break_overall_gd(sub, stats, rng))
    return final


def _rank(teams, stats, results, rng):
    """Return the four teams ordered 1st -> 4th by the full FIFA criteria."""
    key_of = lambda team: _points_key(stats[team])
    ordered = sorted(teams, key=key_of, reverse=True)

    final_order = []
    for block in _tied_blocks(ordered, key_of):
        if len(block) == 1:
            final_order.append(block[0])
        else:
            final_order.extend(_break_h2h(block, stats, results, rng))
    return final_order


def simulate_group(team_elos, rng, known_results=None):
    """Simulate one group.

    Args:
        team_elos:     {team_name: elo_rating} for exactly the four group teams.
        rng:           a numpy Generator (shared across the tournament).
        known_results: optional {frozenset({a, b}): {a: goals, b: goals}} of
                       matches already played. Any listed match uses its real
                       score instead of being simulated (results-conditioning);
                       the rest are simulated as normal.

    Returns a dict with:
        standings - the four teams ordered 1st -> 4th
        stats     - {team: record dict} across all group matches
        results   - {(team_a, team_b): (goals_a, goals_b)} for the six matches
    """
    teams = list(team_elos)
    stats = {team: _blank_record() for team in teams}
    results = {}

    for team_a, team_b in combinations(teams, 2):
        actual = known_results.get(frozenset((team_a, team_b))) \
            if known_results else None
        if actual is not None:
            # Match already played - lock in the real score.
            goals_a, goals_b = actual[team_a], actual[team_b]
        else:
            home = host_advantage(team_a, team_b)
            goals_a, goals_b = simulate_group_match(
                team_elos[team_a], team_elos[team_b], home=home, rng=rng)
        results[(team_a, team_b)] = (goals_a, goals_b)
        _apply_result(stats[team_a], goals_a, goals_b)
        _apply_result(stats[team_b], goals_b, goals_a)

    standings = _rank(teams, stats, results, rng)
    return {"standings": standings, "stats": stats, "results": results}


if __name__ == "__main__":
    import numpy as np
    from data import load_elo, load_groups

    elo = load_elo()
    groups = load_groups()
    rng = np.random.default_rng(2026)

    # Simulate Group C once and print the resulting table.
    letter = "C"
    members = groups[letter]
    result = simulate_group({t: elo[t] for t in members}, rng)

    print(f"Group {letter} - one simulated outcome")
    print(f"{'Pos':<4}{'Team':<22}{'Pld':>4}{'W':>3}{'D':>3}{'L':>3}"
          f"{'GF':>4}{'GA':>4}{'GD':>5}{'Pts':>5}")
    for pos, team in enumerate(result["standings"], start=1):
        r = result["stats"][team]
        print(f"{pos:<4}{team:<22}{r['played']:>4}{r['won']:>3}{r['drawn']:>3}"
              f"{r['lost']:>3}{r['gf']:>4}{r['ga']:>4}{r['gd']:>5}"
              f"{r['points']:>5}")
