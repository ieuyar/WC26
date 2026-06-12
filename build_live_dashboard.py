"""
build_live_dashboard.py - generate a self-contained dashboard_live.html.

Reads all simulation CSVs, embeds the data inline as JS constants, and
writes a single HTML file ready to host on Cloudflare Pages, Netlify,
GitHub Pages, or any static host. No fetch calls, no CORS, no backend.

Re-run this script whenever the CSVs update (after run_simulation.py,
live_ingest.py, etc.) and redeploy the resulting HTML.
"""

import csv
import json
import os
import sys
from datetime import datetime, timezone

_DIR = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(_DIR, "dashboard_live.html")
TEMPLATE = os.path.join(_DIR, "dashboard_live_template.html")
DATA_OUT = os.path.join(_DIR, "wc2026_data.json")


def _read(path):
    with open(path) as f:
        return list(csv.DictReader(f))


def _num(s, default=0):
    try:
        return float(s) if s else default
    except ValueError:
        return default


def build_data():
    """Read every CSV and reshape into compact JS-friendly structures."""
    SO = os.path.join(_DIR, "simulation_output")
    out = {}

    # 192 rows (4 engines x 48 teams), trim to what the dashboard uses
    out["engine_scenarios"] = [
        {
            "engine": r["engine"], "team": r["team"], "group": r["group"],
            "p_qualify": _num(r["p_qualify"]),
            "p_win_group": _num(r["p_win_group"]),
            "p_reach_qf": _num(r["p_reach_qf"]),
            "p_win_title": _num(r["p_win_title"]),
            "rank_win_title": int(_num(r["rank_win_title"], 0)),
        }
        for r in _read(os.path.join(SO, "engine_scenarios.csv"))
    ]

    # 48 rows - per-team production model results
    out["simulation_results"] = [
        {
            "team": r["team"], "group": r["group"],
            "p_qualify": _num(r["p_qualify"]),
            "p_reach_r16": _num(r["p_reach_r16"]),
            "p_reach_qf": _num(r["p_reach_qf"]),
            "p_reach_sf": _num(r["p_reach_sf"]),
            "p_reach_final": _num(r["p_reach_final"]),
            "p_win_title": _num(r["p_win_title"]),
        }
        for r in _read(os.path.join(SO, "simulation_results.csv"))
    ]

    # 48 rows - per-team strength
    out["team_strength"] = [
        {
            "team": r["team"], "group": r["group"],
            "base_elo": int(_num(r["base_elo"])),
            "squad_value_eur_millions": _num(r["squad_value_eur_millions"]),
            "elo_adjustment": round(_num(r["elo_adjustment"]), 1),
            "adjusted_elo": round(_num(r["adjusted_elo"]), 1),
        }
        for r in _read(os.path.join(SO, "team_strength.csv"))
    ]

    # Build a (team_a, team_b) -> "X-Y" lookup of actual results so far.
    # Keys frozenset to be order-agnostic.
    actual_scores = {}
    live_path = os.path.join(_DIR, "live_results.csv")
    if os.path.exists(live_path):
        for r in _read(live_path):
            home, away = r.get("home_team"), r.get("away_team")
            hg, ag = r.get("home_goals"), r.get("away_goals")
            if home and away and hg and ag:
                actual_scores[frozenset([home, away])] = {
                    "score": f"{hg}-{ag}",
                    "home": home, "away": away,
                    "home_goals": int(hg), "away_goals": int(ag),
                }

    def _score_for(team_a, team_b):
        """Return the actual score from team_a's perspective, or None."""
        key = frozenset([team_a, team_b])
        rec = actual_scores.get(key)
        if not rec:
            return None
        if rec["home"] == team_a:
            return f"{rec['home_goals']}-{rec['away_goals']}"
        return f"{rec['away_goals']}-{rec['home_goals']}"

    # 288 rows (4 engines x 72 fixtures) + match_date + actual_score
    out["engine_match_predictions"] = [
        {
            "engine": r["engine"], "matchday": int(r["matchday"]),
            "group": r["group"], "team_a": r["team_a"], "team_b": r["team_b"],
            "p_team_a_win": _num(r["p_team_a_win"]),
            "p_draw": _num(r["p_draw"]),
            "p_team_b_win": _num(r["p_team_b_win"]),
            "likely_scoreline": r["likely_scoreline"],
            "match_date": r.get("match_date", ""),
            "actual_score": _score_for(r["team_a"], r["team_b"]),
        }
        for r in _read(os.path.join(SO, "engine_match_predictions.csv"))
    ]

    # 48 rows - model vs market
    out["model_vs_market"] = [
        {
            "team": r["team"],
            "model_win_pct": _num(r["model_win_pct"]),
            "market_win_pct": _num(r["market_win_pct"]),
            "difference": _num(r["difference"]),
        }
        for r in _read(os.path.join(SO, "model_vs_market.csv"))
    ]

    # 1246 rows - squads
    out["squads"] = [
        {
            "team": r["team"], "name": r["player_name"],
            "is_captain": int(_num(r["is_captain"])),
            "position": r["position"], "age": int(_num(r["age"])),
            "club": r["club"], "caps": int(_num(r["caps"])),
            "goals": int(_num(r["goals"])),
            "market_value_eur": int(_num(r["market_value_eur"])),
        }
        for r in _read(os.path.join(_DIR, "squads.csv"))
    ]

    return out


def main():
    data = build_data()
    if not os.path.exists(TEMPLATE):
        sys.exit(f"Missing template: {TEMPLATE}")

    with open(TEMPLATE) as f:
        html = f.read()

    payload = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    # Inject build timestamp (UTC) so viewers see freshness on every page.
    now = datetime.now(timezone.utc).strftime("%B %d, %Y · %H:%M UTC")
    html = html.replace("__BUILD_TIMESTAMP__", now)

    # Write data and HTML separately so each stays under Shopify's 256 KB
    # per-template limit. The template fetches the JSON at runtime.
    with open(DATA_OUT, "w", encoding="utf-8") as f:
        f.write(payload)

    # Replace placeholder with a fetch loader (relative path - works in
    # both local file:// and Shopify asset hosting contexts).
    html = html.replace(
        "/*__DATA_PLACEHOLDER__*/",
        "null /* loaded asynchronously - see initData() below */"
    )

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)

    html_kb = os.path.getsize(OUT) / 1024
    data_kb = os.path.getsize(DATA_OUT) / 1024
    print(f"Built {OUT} ({html_kb:.0f} KB) + {DATA_OUT} ({data_kb:.0f} KB).")
    print(f"  engines: {len(set(r['engine'] for r in data['engine_scenarios']))}")
    print(f"  teams:   {len(data['simulation_results'])}")
    print(f"  players: {len(data['squads'])}")
    print(f"  fixtures: {len(data['engine_match_predictions']) // 4}")


if __name__ == "__main__":
    main()
