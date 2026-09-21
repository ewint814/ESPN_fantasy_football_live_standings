# Fantasy Football Live Tracker

Real-time ESPN Fantasy Football standings for a private league. The dashboard updates in place over Server-Sent Events (no full page reload).

The live app is the original light table UI with two tabs: **Current Standings** and **Live Projections**. There is no Movement, Preview, or Sandbox tab.

## What it shows

- **Current Standings** — rank, team, live score, who is currently playing, who has yet to play, top-6 / last badges
- **Live Projections** — projected finish vs current score
- **Currently playing** — taken from the ESPN NFL scoreboard and Sleeper live flags (not ESPN fantasy’s `game_played` heuristic). Overtime still counts as playing until the game is actually final
- **Yet to play** — remaining starters with projection and kickoff time (Eastern)
- **Score flash** — score cell blinks green/red when it changes
- **Add to Home Screen** — bulletin on the dashboard plus a web app manifest (`FF Live`)
- **Mobile** — rows stack on a phone so player names and kickoffs do not break mid-word
- **Last updated** — Eastern Time
- Auto-detected NFL season year and week
- Error banner if ESPN credentials fail

Updates every **10 seconds** during game hours (12pm–11pm ET), **30 seconds** off-hours on game days, and **2 minutes** when no games are scheduled.

## Run locally

Needs Python 3.11+ and ESPN league cookies.

```bash
git clone https://github.com/ewint814/ESPN_fantasy_football_live_standings.git
cd ESPN_fantasy_football_live_standings
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# fill in ESPN_LEAGUE_ID, ESPN_S2, ESPN_SWID
python fantasy_tracker_realtime.py
```

Open [http://localhost:5000](http://localhost:5000).

`fantasy_tracker.py` is only a compatibility wrapper that starts the same app (older Render start commands).

## ESPN credentials

1. Log into [ESPN Fantasy Football](https://fantasy.espn.com/football)
2. DevTools → Application / Storage → Cookies → `espn.com`
3. Copy `espn_s2` and `SWID`
4. League ID is in the URL: `...?leagueId=123456`

```env
ESPN_LEAGUE_ID=123456
ESPN_S2=AE...
ESPN_SWID={XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}
PORT=5000
```

Cookies typically expire every few weeks. If the dashboard errors or `/health` shows `connected: false`, refresh them in Render (or `.env`).

## Project layout

```
fantasy_tracker_realtime.py   # Flask app, SSE, score classification
fantasy_tracker.py            # thin wrapper that runs the realtime app
templates/dashboard.html      # Current + Projected UI
config.py                     # env / validation
constants.py                  # update intervals, top-6 cutoff
nfl_utils.py                  # NFL year / week helpers
tests/test_game_status.py     # live / OT / Sleeper classification
tests/test_app.py             # import / config / week checks
render.yaml                   # Render service config
Procfile                      # python fantasy_tracker_realtime.py
```

There is no `src/` package and no active Dockerfile (Render runs Python directly).

## Endpoints

| Path | Description |
|------|-------------|
| `/` | Dashboard |
| `/stream` | SSE score updates |
| `/api/scores` | JSON scores |
| `/health` | Liveness / ESPN connection |
| `/manifest.webmanifest` | Add to Home Screen manifest |

```bash
curl http://localhost:5000/health
```

```json
{
  "status": "healthy",
  "connected": true,
  "teams_count": 12,
  "last_update": "2026-09-21T04:30:00",
  "nfl_year": 2026,
  "current_week": 2,
  "real_time": true
}
```

`/health` returns **503** until ESPN is connected and scores have loaded.

## Deploy on Render

1. Connect this GitHub repo
2. **Build:** `pip install -r requirements.txt`
3. **Start:** `python fantasy_tracker_realtime.py`
4. Set `ESPN_LEAGUE_ID`, `ESPN_S2`, `ESPN_SWID`, and `PORT=5000`

`render.yaml` already has that start command.

## Tests

```bash
python tests/test_app.py
python -c "import tests.test_game_status as t
[getattr(t, n)() for n in dir(t) if n.startswith('test_')]"
```

With dev extras (`pip install -r requirements-dev.txt`):

```bash
pytest tests/test_game_status.py -o addopts= -v
```

`pyproject.toml` still points pytest coverage at `src/`, which this repo does not use. Prefer the commands above.

## Troubleshooting

| Symptom | What to do |
|---------|------------|
| Missing credentials | Set the three ESPN vars in `.env` or Render |
| 401 / expired cookies | Refresh `ESPN_S2` and `ESPN_SWID` from espn.com |
| 404 league not found | Check `ESPN_LEAGUE_ID` in the ESPN URL |
| Loading spinner > 15s | Refresh; hit `/health` |
| Currently Playing is empty during OT | Should stay filled from ESPN + Sleeper after the latest deploy; hard-refresh if Render has not finished |
| Weird line breaks on a phone | Mobile stacking is on `main`; hard-refresh after deploy |

## License

MIT — see [LICENSE](LICENSE).

Uses [Flask](https://flask.palletsprojects.com/), [espn-api](https://github.com/cwendt94/espn-api), the ESPN NFL scoreboard, and Sleeper scores. Hosted on [Render](https://render.com/).
