"""
data.py - centralised, path-robust loading of the simulator's input files.

Every loader resolves paths relative to this file, so the simulator runs
correctly no matter what the current working directory is.

Inputs (all produced earlier in the project):
  groups.csv                 - the 48-team draw, 12 groups of 4 (step 1)
  elo_ratings.csv            - dated Elo snapshot, Jan 2026 (step 1)
  third_place_allocation.csv - FIFA Annex C lookup (built by build_annex_c.py)
"""

import csv
import os

_DIR = os.path.dirname(os.path.abspath(__file__))

# Tournament hosts. A host nation is given a home-advantage Elo bonus in every
# match it plays (see match.py). This is a documented modelling simplification:
# in reality most but not all host matches are played on home soil.
HOST_NATIONS = {"United States", "Canada", "Mexico"}


def _path(name):
    return os.path.join(_DIR, name)


def load_elo():
    """Return {team_name: elo_rating} from the dated Elo snapshot."""
    elo = {}
    with open(_path("elo_ratings.csv"), newline="") as f:
        for row in csv.DictReader(f):
            elo[row["team"]] = float(row["elo"])
    return elo


def load_groups():
    """Return {group_letter: [team, team, team, team]} preserving CSV order."""
    groups = {}
    with open(_path("groups.csv"), newline="") as f:
        for row in csv.DictReader(f):
            groups.setdefault(row["group"], []).append(row["team"])
    return groups


def load_confederations():
    """Return {team_name: confederation} for reference / reporting."""
    conf = {}
    with open(_path("groups.csv"), newline="") as f:
        for row in csv.DictReader(f):
            conf[row["team"]] = row["confederation"]
    return conf


def load_third_place_table():
    """Return {qualified_groups_str: {winner_slot: third_place_group}}.

    Key example: 'ABCDEFGH'. Value example: {'A':'H','B':'G',...}, meaning the
    winner of group A faces the third-placed team of group H, and so on.
    """
    table = {}
    slots = ["A", "B", "D", "E", "G", "I", "K", "L"]
    with open(_path("third_place_allocation.csv"), newline="") as f:
        for row in csv.DictReader(f):
            table[row["qualified_groups"]] = {
                s: row[f"slot_1{s}"] for s in slots
            }
    return table


def load_squad_values():
    """Return {team: total squad market value, in EUR millions}.

    Source: Transfermarkt World Cup 2026 participants page, snapshot 20 May
    2026. Provisional - some final 26-man squads were not yet set, so squad
    sizes (and therefore totals) vary; refresh squad_values.csv when squads
    lock. The full per-team detail (squad size, average value) is in the CSV.
    """
    values = {}
    with open(_path("squad_values.csv"), newline="") as f:
        for row in csv.DictReader(f):
            values[row["team"]] = float(row["squad_value_eur_millions"])
    return values


def load_known_results():
    """Return actual GROUP-STAGE results already played, as
    {frozenset({team_a, team_b}): {team_a: goals_a, team_b: goals_b}}.

    Source: live_results.csv, written by live_ingest.py from football-data.org.
    Returns an empty dict if the file is absent (i.e. before the tournament),
    so the simulation simply runs as a pre-tournament forecast. Only group-
    stage matches are returned - knockout results are not used to condition
    the group simulation.
    """
    path = _path("live_results.csv")
    known = {}
    if not os.path.exists(path):
        return known
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            if row.get("stage") != "GROUP_STAGE":
                continue
            home, away = row["home_team"], row["away_team"]
            known[frozenset((home, away))] = {
                home: int(row["home_goals"]),
                away: int(row["away_goals"]),
            }
    return known


def load_known_ko_results():
    """Return actual KNOCKOUT-STAGE results, as
    {frozenset({team_a, team_b}): {"winner": team, "goals": (a, b)}}.

    Used by the tournament simulator to lock in real knockout matchups: if a
    simulated bracket happens to pair the same two teams that already met in
    real life (e.g. Netherlands vs Morocco in R32), use the actual winner
    rather than simulating it again. This keeps the bracket viz consistent
    with reality once knockout games start - otherwise a Netherlands who lost
    R32 in real life would keep advancing in simulations of later rounds.
    """
    path = _path("live_results.csv")
    known = {}
    if not os.path.exists(path):
        return known
    knockout_stages = {"LAST_32", "LAST_16", "QUARTER_FINALS",
                       "SEMI_FINALS", "THIRD_PLACE", "FINAL"}
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            if row.get("status") != "FINISHED":
                continue
            if row.get("stage") not in knockout_stages:
                continue
            home, away = row["home_team"], row["away_team"]
            hg, ag = int(row["home_goals"]), int(row["away_goals"])
            # Knockout matches don't end in a draw at the recorded level.
            # If goals_after_extra_time or penalty_shootout fields existed
            # we could be more careful; for now treat higher score as winner
            # and equal as a tie (shouldn't happen with FINISHED status).
            if hg > ag:
                winner = home
            elif ag > hg:
                winner = away
            else:
                winner = None  # unresolved - skip
            if winner:
                known[frozenset((home, away))] = {
                    "winner": winner,
                    "goals": {home: hg, away: ag},
                }
    return known


def load_fifa_rankings():
    """Return {team: FIFA ranking points}.

    Source: FIFA/Coca-Cola Men's World Ranking, April 2026 release (the last
    before the tournament). Dated snapshot. Cape Verde's points are
    interpolated from its published rank (69th); all others are exact.
    """
    points = {}
    with open(_path("fifa_rankings.csv"), newline="") as f:
        for row in csv.DictReader(f):
            points[row["team"]] = float(row["fifa_points"])
    return points


def load_all():
    """Convenience: load every input in one call."""
    return {
        "elo": load_elo(),
        "groups": load_groups(),
        "confederations": load_confederations(),
        "third_place_table": load_third_place_table(),
        "squad_values": load_squad_values(),
    }


if __name__ == "__main__":
    d = load_all()
    print(f"Teams with Elo ratings : {len(d['elo'])}")
    print(f"Groups                 : {len(d['groups'])}")
    print(f"Annex C combinations   : {len(d['third_place_table'])}")
    # Integrity: every drafted team must have an Elo rating, and vice versa.
    drafted = {t for teams in d["groups"].values() for t in teams}
    rated = set(d["elo"])
    assert drafted == rated, f"Name mismatch: {drafted ^ rated}"
    assert all(len(v) == 4 for v in d["groups"].values()), "Group not size 4"
    print("Integrity check passed: 48 teams, 12 groups of 4, names aligned.")
