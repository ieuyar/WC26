"""
reorder_to_fifa.py - rewrite match_predictions.csv and
engine_match_predictions.csv so team_a/team_b and match_id follow the
official FIFA WC 2026 schedule, not our algorithmic round-robin ordering.

For each fixture we check FIFA's home/away. If the pair matches but
sides are swapped vs our data, we:
  - swap team_a / team_b
  - swap p_team_a_win / p_team_b_win
  - reverse the likely_scoreline (e.g. "2-0" -> "0-2")
  - update match_id and matchday from FIFA's official numbering

The probabilities don't change (the model is symmetric).
"""

import csv
import os

_DIR = os.path.dirname(os.path.abspath(__file__))
SO = os.path.join(_DIR, "simulation_output")

# FIFA official date for each match_id (from Wikipedia schedule).
FIFA_DATES = {
    1:"2026-06-11", 2:"2026-06-11", 3:"2026-06-12", 4:"2026-06-12",
    5:"2026-06-13", 6:"2026-06-13", 7:"2026-06-13", 8:"2026-06-13",
    9:"2026-06-14", 10:"2026-06-14", 11:"2026-06-14", 12:"2026-06-14",
    13:"2026-06-15", 14:"2026-06-15", 15:"2026-06-15", 16:"2026-06-15",
    17:"2026-06-16", 18:"2026-06-16", 19:"2026-06-16", 20:"2026-06-16",
    21:"2026-06-17", 22:"2026-06-17", 23:"2026-06-17", 24:"2026-06-17",
    25:"2026-06-18", 26:"2026-06-18", 27:"2026-06-18", 28:"2026-06-18",
    29:"2026-06-19", 30:"2026-06-19", 31:"2026-06-19", 32:"2026-06-19",
    33:"2026-06-20", 34:"2026-06-20", 35:"2026-06-20", 36:"2026-06-20",
    37:"2026-06-21", 38:"2026-06-21", 39:"2026-06-21", 40:"2026-06-21",
    41:"2026-06-22", 42:"2026-06-22", 43:"2026-06-22", 44:"2026-06-22",
    45:"2026-06-23", 46:"2026-06-23", 47:"2026-06-23", 48:"2026-06-23",
    49:"2026-06-24", 50:"2026-06-24", 51:"2026-06-24", 52:"2026-06-24",
    53:"2026-06-24", 54:"2026-06-24",
    55:"2026-06-25", 56:"2026-06-25", 57:"2026-06-25", 58:"2026-06-25",
    59:"2026-06-25", 60:"2026-06-25",
    61:"2026-06-26", 62:"2026-06-26", 63:"2026-06-26", 64:"2026-06-26",
    65:"2026-06-26", 66:"2026-06-26",
    67:"2026-06-27", 68:"2026-06-27", 69:"2026-06-27", 70:"2026-06-27",
    71:"2026-06-27", 72:"2026-06-27",
}

# FIFA official schedule scraped from Wikipedia (matches FIFA.com).
# Format: (match_id, home, away) - match_id 1-24 = MD1, 25-48 = MD2, 49-72 = MD3.
FIFA_FIXTURES = [
    (1,  "Mexico", "South Africa"),
    (2,  "South Korea", "Czech Republic"),
    (3,  "Canada", "Bosnia and Herzegovina"),
    (4,  "United States", "Paraguay"),
    (5,  "Haiti", "Scotland"),
    (6,  "Australia", "Turkey"),
    (7,  "Brazil", "Morocco"),
    (8,  "Qatar", "Switzerland"),
    (9,  "Ivory Coast", "Ecuador"),
    (10, "Germany", "Curacao"),
    (11, "Netherlands", "Japan"),
    (12, "Sweden", "Tunisia"),
    (13, "Saudi Arabia", "Uruguay"),
    (14, "Spain", "Cape Verde"),
    (15, "Iran", "New Zealand"),
    (16, "Belgium", "Egypt"),
    (17, "France", "Senegal"),
    (18, "Iraq", "Norway"),
    (19, "Argentina", "Algeria"),
    (20, "Austria", "Jordan"),
    (21, "Ghana", "Panama"),
    (22, "England", "Croatia"),
    (23, "Portugal", "DR Congo"),
    (24, "Uzbekistan", "Colombia"),
    (25, "Czech Republic", "South Africa"),
    (26, "Switzerland", "Bosnia and Herzegovina"),
    (27, "Canada", "Qatar"),
    (28, "Mexico", "South Korea"),
    (29, "Brazil", "Haiti"),
    (30, "Scotland", "Morocco"),
    (31, "Turkey", "Paraguay"),
    (32, "United States", "Australia"),
    (33, "Germany", "Ivory Coast"),
    (34, "Ecuador", "Curacao"),
    (35, "Netherlands", "Sweden"),
    (36, "Tunisia", "Japan"),
    (37, "Uruguay", "Cape Verde"),
    (38, "Spain", "Saudi Arabia"),
    (39, "Belgium", "Iran"),
    (40, "New Zealand", "Egypt"),
    (41, "Norway", "Senegal"),
    (42, "France", "Iraq"),
    (43, "Argentina", "Austria"),
    (44, "Jordan", "Algeria"),
    (45, "England", "Ghana"),
    (46, "Panama", "Croatia"),
    (47, "Portugal", "Uzbekistan"),
    (48, "Colombia", "DR Congo"),
    (49, "Scotland", "Brazil"),
    (50, "Morocco", "Haiti"),
    (51, "Switzerland", "Canada"),
    (52, "Bosnia and Herzegovina", "Qatar"),
    (53, "Czech Republic", "Mexico"),
    (54, "South Africa", "South Korea"),
    (55, "Curacao", "Ivory Coast"),
    (56, "Ecuador", "Germany"),
    (57, "Japan", "Sweden"),
    (58, "Tunisia", "Netherlands"),
    (59, "Turkey", "United States"),
    (60, "Paraguay", "Australia"),
    (61, "Norway", "France"),
    (62, "Senegal", "Iraq"),
    (63, "Egypt", "Iran"),
    (64, "New Zealand", "Belgium"),
    (65, "Cape Verde", "Saudi Arabia"),
    (66, "Uruguay", "Spain"),
    (67, "Panama", "England"),
    (68, "Croatia", "Ghana"),
    (69, "Algeria", "Austria"),
    (70, "Jordan", "Argentina"),
    (71, "Colombia", "Portugal"),
    (72, "DR Congo", "Uzbekistan"),
]

# Wikipedia uses different spellings; normalize to our project naming.
NAME_MAP = {
    "Czech Republic": "Czechia",
    "Ivory Coast": "Cote d'Ivoire",
    "Curaçao": "Curacao",
}


def _norm(name):
    return NAME_MAP.get(name, name)


def reverse_scoreline(s):
    """'2-0' -> '0-2'"""
    parts = s.split("-")
    if len(parts) == 2:
        return f"{parts[1].strip()}-{parts[0].strip()}"
    return s


def matchday_from_id(mid):
    return ((mid - 1) // 24) + 1


def build_fifa_lookup():
    """Build {(team_set): (match_id, home, away)} for lookup."""
    lookup = {}
    for mid, home, away in FIFA_FIXTURES:
        h = _norm(home)
        a = _norm(away)
        key = frozenset([h, a])
        lookup[key] = (mid, h, a)
    return lookup


def reorder_file(path, has_engine=False):
    """Rewrite one CSV in-place with FIFA ordering."""
    fifa = build_fifa_lookup()

    with open(path) as f:
        rows = list(csv.DictReader(f))
        fields = list(rows[0].keys())

    # Add match_date column if not present.
    if "match_date" not in fields:
        fields.append("match_date")

    swaps = 0
    unmatched = []
    for r in rows:
        team_a = r["team_a"]
        team_b = r["team_b"]
        key = frozenset([team_a, team_b])
        if key not in fifa:
            unmatched.append(f"{team_a} vs {team_b}")
            continue
        mid, home, away = fifa[key]
        r["match_id"] = mid
        r["matchday"] = matchday_from_id(mid)
        r["match_date"] = FIFA_DATES.get(mid, "")
        if team_a == home and team_b == away:
            continue  # already correct
        # Need to swap
        r["team_a"], r["team_b"] = home, away
        r["p_team_a_win"], r["p_team_b_win"] = r["p_team_b_win"], r["p_team_a_win"]
        r["likely_scoreline"] = reverse_scoreline(r["likely_scoreline"])
        swaps += 1

    # Sort by match_id (and engine if engine-aware)
    if has_engine:
        engine_order = {"Model": 0, "Elo": 1, "Squad value": 2, "FIFA ranking": 3}
        rows.sort(key=lambda r: (engine_order.get(r["engine"], 99),
                                  int(r["match_id"])))
    else:
        rows.sort(key=lambda r: int(r["match_id"]))

    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    print(f"  {os.path.basename(path)}: swapped {swaps} fixtures, "
          f"{len(rows)} rows, {len(unmatched)} unmatched.")
    if unmatched:
        for u in unmatched[:5]:
            print(f"    unmatched: {u}")


def main():
    print("Reordering match_predictions.csv to FIFA official schedule...")
    reorder_file(os.path.join(SO, "match_predictions.csv"))

    print("Reordering engine_match_predictions.csv...")
    reorder_file(os.path.join(SO, "engine_match_predictions.csv"),
                  has_engine=True)

    print("\nDone. Probabilities unchanged - only team_a/team_b labels and "
          "match_id reordered.")


if __name__ == "__main__":
    main()
