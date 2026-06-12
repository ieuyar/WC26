"""
merge_market_values.py - merge Transfermarkt market values into squads.csv.

Match strategy: (team, player_name). Player name matching is exact first,
then a normalized-fuzzy fallback (strip accents, lowercase, collapse spaces)
to catch the inevitable Wikipedia-vs-Transfermarkt spelling drift.

Unmatched players keep market_value_eur blank; we report counts.
"""

import csv
import os
import unicodedata

_DIR = os.path.dirname(os.path.abspath(__file__))
TM = os.path.join(_DIR, "wc_squads_transfermarkt.csv")
SQUADS = os.path.join(_DIR, "squads.csv")
ALIASES = os.path.join(_DIR, "name_aliases.csv")

# Transfermarkt uses German-leaning team spellings; map to project naming.
TM_TEAM_RENAME = {
    "Turkiye": "Turkey",
    "Bosnia-Herzegovina": "Bosnia and Herzegovina",
    "Democratic Republic of the Congo": "DR Congo",
    "Ivory Coast": "Cote d'Ivoire",
    "Curaçao": "Curacao",
}


def fold(s):
    """Lowercase, strip accents, collapse spaces - for fuzzy matching."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.lower().split())


def fold_reversed(s):
    """fold() but with word order reversed - catches Western vs East Asian
    name conventions: 'Song Bum-keun' <-> 'Bum-keun Song'."""
    return " ".join(reversed(fold(s).split()))


def main():
    # Load TM values keyed by exact / folded / folded-reversed forms.
    tm_exact = {}
    tm_fold = {}
    tm_rev = {}
    with open(TM) as f:
        for r in csv.DictReader(f):
            team = TM_TEAM_RENAME.get(r["team"], r["team"])
            name = r["player_name"].strip()
            val = r["market_value_eur"].strip()
            if not val:
                continue
            tm_exact[(team, name)] = val
            tm_fold[(team, fold(name))] = val
            tm_rev[(team, fold_reversed(name))] = val

    # Walk squads.csv, fill market_value_eur
    with open(SQUADS) as f:
        rows = list(csv.DictReader(f))
        fieldnames = list(rows[0].keys())

    # Load curated aliases for names that don't match cleanly between sources.
    aliases = {}
    if os.path.exists(ALIASES):
        with open(ALIASES) as f:
            for r in csv.DictReader(f):
                aliases[(r["team"], r["wiki_name"])] = r["tm_name"]

    matched_exact = matched_fold = matched_rev = matched_alias = unmatched = 0
    unmatched_samples = []
    for row in rows:
        team = row["team"]
        name = row["player_name"]
        f = fold(name)
        if (team, name) in tm_exact:
            row["market_value_eur"] = tm_exact[(team, name)]
            matched_exact += 1
        elif (team, f) in tm_fold:
            row["market_value_eur"] = tm_fold[(team, f)]
            matched_fold += 1
        elif (team, f) in tm_rev:
            row["market_value_eur"] = tm_rev[(team, f)]
            matched_rev += 1
        elif (team, name) in aliases:
            tm_name = aliases[(team, name)]
            val = tm_exact.get((team, tm_name)) or tm_fold.get((team, fold(tm_name)))
            if val:
                row["market_value_eur"] = val
                matched_alias += 1
            else:
                unmatched += 1
                unmatched_samples.append(f"{team}: {name} (alias '{tm_name}' not in TM)")
        else:
            unmatched += 1
            if len(unmatched_samples) < 25:
                unmatched_samples.append(f"{team}: {name}")

    with open(SQUADS, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    total = matched_exact + matched_fold + matched_rev + matched_alias + unmatched
    print(f"Merged {total - unmatched}/{total} player rows "
          f"({matched_exact} exact, {matched_fold} fuzzy, "
          f"{matched_rev} reversed, {matched_alias} alias).")
    print(f"Unmatched: {unmatched}.")
    if unmatched_samples:
        print("\nFirst unmatched players:")
        for s in unmatched_samples:
            print(f"  - {s}")


if __name__ == "__main__":
    main()
