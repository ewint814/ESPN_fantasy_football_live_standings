# AGENTS.md — ESPN fantasy football live tracker

Real-time ESPN fantasy football standings dashboard. Flask + Server-Sent
Events, no page reloads. Private league. Phone-first UI.

## Run

- Python 3.11+. Entry point: `python fantasy_tracker_realtime.py` (port 5000).
- Needs ESPN league cookies: `ESPN_LEAGUE_ID`, `ESPN_S2`, `ESPN_SWID`
  (env vars or `.env`). `PORT` for deploy.
- Deploy: Render (`render.yaml`, `Procfile`, gunicorn).

## Test & lint

- Tests run as scripts: `python tests/test_app.py`, `python tests/test_game_status.py`
- Do NOT use pytest coverage as configured — `pyproject.toml` still points it
  at a `src/` tree that doesn't exist. Flat layout, no `src/` package. Ever.
- Ruff: line length 100, target py311 (isort + bugbear on, E501 ignored).
- mypy: `disallow_untyped_defs` — type your function signatures.

## Conventions

- Flat files at repo root. Don't invent a `src/` package.
- All times Eastern.
- UI is a light table with exactly two tabs: Current Standings, Live Projections.
  Don't add tabs.
- Phone layout matters: rows stack, no mid-word breaks on player names or kickoffs.
- "Currently playing" comes from the ESPN NFL scoreboard + Sleeper live flags —
  not ESPN fantasy's `game_played` heuristic. Overtime counts as playing until final.
- If ESPN credentials fail, the dashboard shows an error banner — check cookies first.

## Working agreement

- Ask before assuming. Change nothing until Eli approves.
- Update cadence is intentional: 10s during game hours (12pm–11pm ET),
  30s off-hours on game days, 2 min otherwise. Don't "simplify" it.
