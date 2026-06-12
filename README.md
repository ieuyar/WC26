# World Cup 2026 Analytics

Predictive dashboard for the 2026 FIFA World Cup. 50,000 Monte Carlo
simulations across four rating engines (Elo, FIFA ranking, squad value,
and a custom blend), benchmarked against bookmaker odds.

**Live dashboard:** [etemvisuals.com/analytics](https://etemvisuals.com/analytics)

## What's here

- `index.html` / `dashboard_live.html` — the dashboard front end (~35 KB)
- `wc2026_data.json` — the data the dashboard loads (~290 KB)
- `dashboard_live_template.html` — source template for rebuilds
- Python pipeline scripts at the root: simulator, engines, live ingest, builders
- `simulation_output/` — generated CSVs from the simulation pipeline
- `.github/workflows/daily-refresh.yml` — auto-refresh every morning
  during the tournament

## Daily refresh pipeline

```bash
python3 live_ingest.py              # pull overnight match results
python3 run_simulation.py            # re-run Monte Carlo with results conditioned in
python3 run_engines.py               # per-engine scenarios
python3 engine_matches.py            # per-engine match predictions
python3 reorder_to_fifa.py           # FIFA official schedule order
python3 compute_ranks.py             # rank columns per engine
python3 build_live_dashboard.py      # rebuild the HTML and JSON
```

GitHub Actions runs this automatically at 06:00 UTC each day.

## Data sources

- ClubElo (clubelo.com) — Elo ratings, scraped pre-tournament
- FIFA rankings (fifa.com) — official ranking snapshot
- Transfermarkt — per-player market values
- Wikipedia — 26-man squad rosters
- football-data.org — live match results (requires API token)
- DraftKings via RotoWire — bookmaker odds for model vs market

## Local development

```bash
echo "YOUR_TOKEN" > api_token.txt    # never commit this file
python3 build_live_dashboard.py
# Open dashboard_live.html in any browser
```

## Deployment

Cloudflare Pages auto-deploys from this repo on every push. The Shopify
page at etemvisuals.com/analytics embeds the Cloudflare URL via iframe.

The GitHub Actions workflow re-runs the full pipeline daily, commits the
updated JSON and HTML, pushes to main, Cloudflare picks up the change
within ~30 seconds.

## Methodology in one paragraph

For each fixture, expected goals come from a Poisson model whose lambdas
are derived from the Elo difference between the two teams (plus host
advantage for USA/CAN/MEX home games). 50,000 tournament runs produce
each team's probability of advancing through each stage. Group standings
follow the official FIFA tiebreakers (points → goal difference → goals
scored → head-to-head → drawing of lots). Knockout pairings follow the
Annex C bracket. Results conditioning: once a match is played, the
actual scoreline is locked in and the rest of the tournament is
re-simulated.

## License

This is a personal project, not affiliated with FIFA. Use the code freely
for learning and analysis; respect FIFA's trademarks on the WC 2026
emblem and the tournament marks.
