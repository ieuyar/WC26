"""
Step 5 - simulate a full World Cup, group stage through to the final.

Sequence:
  1. Simulate all 12 groups (step 4).
  2. Rank the 12 third-placed teams; the best 8 join the knockout stage.
  3. Use FIFA's Annex C lookup to slot those 8 teams into the Round of 32.
  4. Play the bracket: Round of 32 -> 16 -> quarter-finals -> semi-finals ->
     third-place play-off and final.

The bracket is the official 2026 FIFA World Cup structure (matches 73-104).
Matches 73-88 are the Round of 32; the winner/runner-up pairings are fixed,
while the eight winner-vs-third-place ties depend on which third-placed teams
qualify (resolved via the Annex C table).
"""

from group import simulate_group, _overall_key
from match import simulate_knockout, host_advantage

GROUP_LETTERS = list("ABCDEFGHIJKL")

# Round of 32 (matches 73-88). Each entry describes how to find the two teams.
# Tokens: ('W', 'A') = winner of group A; ('R', 'C') = runner-up of group C;
# ('3', 'A') = the third-placed team allocated to winner-A's slot via Annex C.
ROUND_OF_32 = {
    73: (("R", "A"), ("R", "B")),
    74: (("W", "E"), ("3", "E")),
    75: (("W", "F"), ("R", "C")),
    76: (("W", "C"), ("R", "F")),
    77: (("W", "I"), ("3", "I")),
    78: (("R", "E"), ("R", "I")),
    79: (("W", "A"), ("3", "A")),
    80: (("W", "L"), ("3", "L")),
    81: (("W", "D"), ("3", "D")),
    82: (("W", "G"), ("3", "G")),
    83: (("R", "K"), ("R", "L")),
    84: (("W", "H"), ("R", "J")),
    85: (("W", "B"), ("3", "B")),
    86: (("W", "J"), ("R", "H")),
    87: (("W", "K"), ("3", "K")),
    88: (("R", "D"), ("R", "G")),
}

# Later rounds: each match feeds off the winners of two earlier matches.
ROUND_OF_16 = {
    89: (74, 77), 90: (73, 75), 91: (76, 78), 92: (79, 80),
    93: (83, 84), 94: (81, 82), 95: (86, 88), 96: (85, 87),
}
QUARTER_FINALS = {97: (89, 90), 98: (93, 94), 99: (91, 92), 100: (95, 96)}
SEMI_FINALS = {101: (97, 98), 102: (99, 100)}
FINAL_MATCH = 104
THIRD_PLACE_MATCH = 103

# Stage labels and an ordering so "furthest stage reached" can be compared.
STAGE_ORDER = {
    "group": 0, "R32": 1, "R16": 2, "QF": 3, "SF": 4, "final": 5, "champion": 6,
}


def _play(team_a, team_b, elo, rng):
    """Play one knockout match; return (winner, loser)."""
    home = host_advantage(team_a, team_b)
    result = simulate_knockout(elo[team_a], elo[team_b], home=home, rng=rng)
    if result["winner"] == "A":
        return team_a, team_b
    return team_b, team_a


def _rank_third_placed(group_results, rng):
    """Rank the 12 third-placed teams; return the 8 best group letters (sorted).

    Ranking uses the same overall criteria as group play - points, goal
    difference, goals scored - with a random draw breaking any remaining ties
    (FIFA's drawing of lots; fair-play points are not modelled).
    """
    def key(letter):
        team = group_results[letter]["standings"][2]
        record = group_results[letter]["stats"][team]
        return _overall_key(record) + (rng.random(),)

    ranked = sorted(GROUP_LETTERS, key=key, reverse=True)
    return sorted(ranked[:8])


def simulate_tournament(elo, groups, third_place_table, rng,
                        known_results=None, known_ko_results=None):
    """Simulate one complete tournament.

    known_results:    optional real group-stage scores to condition on (see
                      simulate_group); matches already played are locked in
                      rather than simulated.
    known_ko_results: optional dict of finished knockout matches keyed by
                      frozenset({team_a, team_b}). When the simulator's
                      bracket produces a matchup that has already been played
                      in real life, the actual winner is used instead of
                      simulating. This keeps the bracket viz consistent with
                      reality once knockouts begin.

    Returns a dict:
        group_standings - {letter: [team x4]} ordered 1st -> 4th
        group_stats     - {letter: {team: record}}
        qualified_thirds- sorted list of the 8 group letters whose third-placed
                          team advanced
        stage           - {team: furthest stage reached} for all 48 teams
        champion, runner_up, third_place, fourth_place
        knockout        - {match_no: {'a','b','winner','loser'}}
    """
    # --- 1. group stage --------------------------------------------------
    group_results = {}
    winners, runners, thirds = {}, {}, {}
    for letter in GROUP_LETTERS:
        members = groups[letter]
        res = simulate_group({t: elo[t] for t in members}, rng,
                             known_results)
        group_results[letter] = res
        winners[letter] = res["standings"][0]
        runners[letter] = res["standings"][1]
        thirds[letter] = res["standings"][2]

    # --- 2 & 3. best eight third-placed teams, slotted via Annex C -------
    qualified = _rank_third_placed(group_results, rng)
    allocation = third_place_table["".join(qualified)]
    # allocation maps a winner-slot letter -> the group whose 3rd-placed team
    # fills it, e.g. {'A': 'H'} => winner A faces the third-placed team of H.

    def resolve(token):
        kind, letter = token
        if kind == "W":
            return winners[letter]
        if kind == "R":
            return runners[letter]
        # kind == '3': look up which group's third-placed team takes this slot.
        return thirds[allocation[letter]]

    # --- 4. knockout bracket --------------------------------------------
    knockout = {}      # match_no -> {'a','b','winner','loser'}
    win = {}           # match_no -> winning team
    lose = {}          # match_no -> losing team

    def record(match_no, team_a, team_b):
        # If this exact pairing has already been played in real life, use
        # the actual result instead of simulating.
        actual = (known_ko_results.get(frozenset((team_a, team_b)))
                  if known_ko_results else None)
        if actual is not None:
            w = actual["winner"]
            l = team_b if w == team_a else team_a
        else:
            w, l = _play(team_a, team_b, elo, rng)
        knockout[match_no] = {"a": team_a, "b": team_b, "winner": w, "loser": l}
        win[match_no], lose[match_no] = w, l

    for match_no, (token_a, token_b) in ROUND_OF_32.items():
        record(match_no, resolve(token_a), resolve(token_b))
    for match_no, (src_a, src_b) in ROUND_OF_16.items():
        record(match_no, win[src_a], win[src_b])
    for match_no, (src_a, src_b) in QUARTER_FINALS.items():
        record(match_no, win[src_a], win[src_b])
    for match_no, (src_a, src_b) in SEMI_FINALS.items():
        record(match_no, win[src_a], win[src_b])
    record(THIRD_PLACE_MATCH, lose[101], lose[102])
    record(FINAL_MATCH, win[101], win[102])

    champion = win[FINAL_MATCH]
    runner_up = lose[FINAL_MATCH]
    third_place = win[THIRD_PLACE_MATCH]
    fourth_place = lose[THIRD_PLACE_MATCH]

    # --- furthest stage reached, per team -------------------------------
    stage = {team: "group" for letter in GROUP_LETTERS
             for team in groups[letter]}
    for match_no in range(73, 89):       # lost in the Round of 32
        stage[lose[match_no]] = "R32"
    for match_no in range(89, 97):       # lost in the Round of 16
        stage[lose[match_no]] = "R16"
    for match_no in range(97, 101):      # lost in the quarter-finals
        stage[lose[match_no]] = "QF"
    for match_no in (101, 102):          # lost in the semi-finals
        stage[lose[match_no]] = "SF"
    stage[runner_up] = "final"
    stage[champion] = "champion"

    return {
        "group_standings": {l: group_results[l]["standings"]
                            for l in GROUP_LETTERS},
        "group_stats": {l: group_results[l]["stats"] for l in GROUP_LETTERS},
        "qualified_thirds": qualified,
        "stage": stage,
        "champion": champion,
        "runner_up": runner_up,
        "third_place": third_place,
        "fourth_place": fourth_place,
        "knockout": knockout,
    }


if __name__ == "__main__":
    import numpy as np
    from data import load_elo, load_groups, load_third_place_table

    elo = load_elo()
    groups = load_groups()
    table = load_third_place_table()
    rng = np.random.default_rng(2026)

    result = simulate_tournament(elo, groups, table, rng)

    print("One simulated 2026 World Cup")
    print("-" * 40)
    for letter in GROUP_LETTERS:
        s = result["group_standings"][letter]
        print(f"Group {letter}: {s[0]} (W), {s[1]} (R), {s[2]} (3rd)")
    print("-" * 40)
    print(f"Best 8 third-placed groups: {', '.join(result['qualified_thirds'])}")
    print("-" * 40)
    for match_no in (101, 102):
        k = result["knockout"][match_no]
        print(f"Semi-final {match_no}: {k['a']} vs {k['b']} -> {k['winner']}")
    print(f"Final: {result['champion']} beat {result['runner_up']}")
    print(f"Third place: {result['third_place']}")
    print(f"\nCHAMPION: {result['champion']}")
