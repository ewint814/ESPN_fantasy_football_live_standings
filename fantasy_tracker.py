"""
Fantasy Football Live Tracker
=============================
A live scoring tracker for ESPN Fantasy Football that shows:
- Current live scores ranked by position
- Top 6 teams highlighted (for extra win scoring)
- Currently playing players
- Remaining players to play
- Real-time updates every 90 seconds
"""

import logging
import os
import threading
import time
from datetime import datetime
from typing import Optional

from flask import Flask, jsonify, render_template_string

from tracker import ScoreFetcher

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


DASHBOARD_TEMPLATE = """
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>🏈 Fantasy Football Live Tracker</title>
            <style>
                * {
                    margin: 0;
                    padding: 0;
                    box-sizing: border-box;
                }
                
                body {
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
                    background: #f5f5f5;
                    min-height: 100vh;
                    color: #333;
                    line-height: 1.5;
                    padding: 0;
                    margin: 0;
                }
                
                .header {
                    background: white;
                    border-bottom: 1px solid #ddd;
                    padding: 24px 20px;
                    text-align: center;
                    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
                }
                
                .header h1 {
                    font-size: 2em;
                    font-weight: 600;
                    color: #333;
                    margin-bottom: 8px;
                }
                
                .week-info {
                    font-size: 1em;
                    color: #666;
                    margin-bottom: 8px;
                    font-weight: normal;
                }
                
                .last-update {
                    font-size: 0.9em;
                    color: #888;
                }
                
                .api-error {
                    font-size: 0.9em;
                    color: #dc3545;
                    background: #f8d7da;
                    border: 1px solid #f5c6cb;
                    border-radius: 4px;
                    padding: 8px 12px;
                    margin-top: 8px;
                }
                
                .container {
                    max-width: 1000px;
                    margin: 0 auto;
                    padding: 24px 20px;
                }
                
                .legend {
                    background: rgba(255,255,255,0.95);
                    padding: 15px;
                    border-radius: 10px;
                    margin-bottom: 20px;
                    text-align: center;
                    box-shadow: 0 4px 15px rgba(0,0,0,0.1);
                }
                
                .legend h3 {
                    color: #2c3e50;
                    margin-bottom: 10px;
                }
                
                .legend-item {
                    display: inline-block;
                    margin: 0 15px;
                    font-weight: 600;
                }
                
                .top6-indicator {
                    color: #27ae60;
                    font-weight: bold;
                }
                
                
                .toggle-container {
                    display: flex;
                    justify-content: center;
                    gap: 12px;
                    margin-bottom: 24px;
                }
                
                .toggle-btn {
                    padding: 10px 20px;
                    border: 1px solid #ddd;
                    background: white;
                    color: #666;
                    border-radius: 4px;
                    cursor: pointer;
                    font-weight: normal;
                    transition: all 0.2s ease;
                }
                
                .toggle-btn:hover {
                    background: #f8f8f8;
                    color: #333;
                }
                
                .toggle-btn.active {
                    background: #333;
                    color: white;
                    border-color: #333;
                }

                .standings-cards {
                    display: flex;
                    flex-direction: column;
                    gap: 12px;
                }
                
                .team-movement-card {
                    background: white;
                    border-radius: 8px;
                    border: 1px solid #ddd;
                    padding: 16px;
                    transition: all 0.2s ease;
                    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
                }
                
                .team-movement-card:hover {
                    box-shadow: 0 4px 8px rgba(0, 0, 0, 0.15);
                }
                
                .team-movement-card.current-top6 {
                    border-left: 4px solid #28a745;
                    background: linear-gradient(90deg, rgba(40, 167, 69, 0.05) 0%, white 100%);
                }
                
                .card-header {
                    display: flex;
                    align-items: center;
                    justify-content: space-between;
                    margin-bottom: 12px;
                }
                
                .rank-badge {
                    background: #f8f9fa;
                    color: #495057;
                    font-weight: 700;
                    font-size: 1.2em;
                    padding: 8px 12px;
                    border-radius: 6px;
                    min-width: 50px;
                    text-align: center;
                }
                
                .current-top6 .rank-badge {
                    background: #28a745;
                    color: white;
                }
                
                .team-info {
                    flex: 1;
                    margin-left: 16px;
                }
                
                .team-name {
                    font-size: 1.1em;
                    font-weight: 600;
                    color: #333;
                    margin-bottom: 4px;
                }
                
                .status-badges {
                    display: flex;
                    gap: 8px;
                }
                
                .movement-indicator {
                    font-size: 1.1em;
                    font-weight: 700;
                }
                
                .movement-up {
                    color: #28a745;
                }
                
                .movement-down {
                    color: #dc3545;
                }
                
                .movement-same {
                    color: #6c757d;
                }
                
                .score-progression {
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    gap: 12px;
                    font-size: 1.3em;
                    font-weight: 700;
                    margin-bottom: 8px;
                }
                
                .current-score {
                    color: #dc3545;
                }
                
                .arrow {
                    color: #6c757d;
                    font-size: 1.1em;
                }
                
                .projected-score {
                    color: #007bff;
                }
                
                .movement-scores {
                    display: flex;
                    align-items: center;
                    gap: 8px;
                    font-weight: 600;
                }
                
                .movement-scores .current-score {
                    color: #dc3545;
                }
                
                .movement-scores .arrow {
                    color: #6c757d;
                }
                
                .movement-scores .projected-score {
                    color: #007bff;
                }
                
                .movement-cell {
                    text-align: center;
                    font-weight: 700;
                    font-size: 1.1em;
                }
                
                .standings-table {
                    background: white;
                    border-radius: 4px;
                    overflow: hidden;
                    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
                    border: 1px solid #ddd;
                }
                
                .standings {
                    width: 100%;
                    border-collapse: collapse;
                }
                
                .standings thead {
                    background: #f8f8f8;
                    color: #333;
                }
                
                .standings th {
                    padding: 12px;
                    text-align: left;
                    font-weight: 600;
                    font-size: 0.9em;
                    border-bottom: 1px solid #ddd;
                }
                
                .standings tbody tr {
                    border-bottom: 1px solid #eee;
                }
                
                .standings tbody tr:hover {
                    background: #f9f9f9;
                }
                
                .standings tbody tr.top6-row {
                    background: #f0f8f0;
                    border-left: 3px solid #28a745;
                }
                
                .standings td {
                    padding: 12px;
                    vertical-align: middle;
                }
                
                .rank-cell {
                    font-weight: 700;
                    font-size: 1.1em;
                    color: #666;
                    text-align: center;
                    width: 60px;
                }
                
                .top6-row .rank-cell {
                    color: #28a745;
                }
                
                .team-cell {
                    font-weight: 600;
                    color: #333;
                    font-size: 1em;
                }
                
                .score-cell {
                    font-weight: 700;
                    font-size: 1.1em;
                    color: #333;
                    text-align: right;
                    width: 100px;
                }
                
                .top6-row .score-cell {
                    color: #28a745;
                }
                
                .players-cell {
                    max-width: 300px;
                }
                
                .player-names {
                    font-size: 0.85em;
                    color: #666;
                    line-height: 1.3;
                }
                
                .no-players {
                    font-style: italic;
                    color: #999;
                    font-size: 0.85em;
                }
                
                .status-cell {
                    text-align: center;
                    width: 80px;
                }
                
                .status-badge {
                    color: white;
                    padding: 3px 6px;
                    border-radius: 3px;
                    font-size: 0.7em;
                    font-weight: 600;
                    text-transform: uppercase;
                    display: inline-block;
                }
                
                .current-badge {
                    background: #28a745;
                }
                
                .projected-badge {
                    background: #007bff;
                }
                
                .top-scorer-badge {
                    background: #ffd700;
                    color: #333;
                }
                
                .parlay-badge {
                    background: #dc3545;
                }
                
                .loading {
                    text-align: center;
                    color: white;
                    font-size: 1.2em;
                    padding: 50px;
                }
                
                @media (max-width: 768px) {
                    .header h1 {
                        font-size: 1.8em;
                    }
                    
                    .container {
                        padding: 20px 16px;
                    }
                    
                    .team-header {
                        flex-direction: column;
                        align-items: center;
                        text-align: center;
                        gap: 16px;
                    }
                    
                    .team-left {
                        flex-direction: column;
                        gap: 8px;
                    }
                    
                    .team-rank {
                        font-size: 2em;
                    }
                    
                    .team-name {
                        font-size: 1.2em;
                    }
                    
                    .team-scores {
                        align-items: center;
                    }
                    
                    .team-score {
                        font-size: 2em;
                    }
                }
            </style>
            <script>
                // Toggle between current, projected, and movement standings
                function showCurrent() {
                    document.getElementById('currentStandings').style.display = 'block';
                    document.getElementById('projectedStandings').style.display = 'none';
                    document.getElementById('movementStandings').style.display = 'none';
                    document.getElementById('currentBtn').classList.add('active');
                    document.getElementById('projectedBtn').classList.remove('active');
                    document.getElementById('movementBtn').classList.remove('active');
                }
                
                function showProjected() {
                    document.getElementById('currentStandings').style.display = 'none';
                    document.getElementById('projectedStandings').style.display = 'block';
                    document.getElementById('movementStandings').style.display = 'none';
                    document.getElementById('currentBtn').classList.remove('active');
                    document.getElementById('projectedBtn').classList.add('active');
                    document.getElementById('movementBtn').classList.remove('active');
                }
                
                function showMovement() {
                    document.getElementById('currentStandings').style.display = 'none';
                    document.getElementById('projectedStandings').style.display = 'none';
                    document.getElementById('movementStandings').style.display = 'block';
                    document.getElementById('currentBtn').classList.remove('active');
                    document.getElementById('projectedBtn').classList.remove('active');
                    document.getElementById('movementBtn').classList.add('active');
                }
                
                // Auto-refresh every 90 seconds
                setTimeout(() => {
                    location.reload();
                }, 90000);
                
                // Check for updates every 30 seconds
                setInterval(() => {
                    fetch('/api/scores')
                        .then(response => response.json())
                        .then(data => {
                            // Could add live updates here without full refresh
                        })
                        .catch(error => console.log('Update check failed:', error));
                }, 30000);
            </script>
        </head>
        <body>
            <div class="header">
                <h1>🏈 Fantasy Football Live Tracker</h1>
                <div class="week-info">Week {{ week }} • Live Scoring</div>
                {% if last_update %}
                <div class="last-update">Last updated: {{ last_update.strftime('%I:%M:%S %p') }}</div>
                {% endif %}
                {% if api_error %}
                <div class="api-error">{{ api_error }}</div>
                {% endif %}
            </div>
            
            <div class="container">
                
                {% if scores %}
                <div class="toggle-container">
                    <button id="currentBtn" class="toggle-btn active" onclick="showCurrent()">Current Standings</button>
                    <button id="projectedBtn" class="toggle-btn" onclick="showProjected()">Live Projections</button>
                    <button id="movementBtn" class="toggle-btn" onclick="showMovement()">Movement</button>
                </div>
                
                <!-- Current Standings Table -->
                <div id="currentStandings" class="standings-table">
                    <table class="standings">
                        <thead>
                            <tr>
                                <th>Rank</th>
                                <th>Team</th>
                                <th>Score</th>
                                <th>Yet to Play</th>
                                <th>Status</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for team in scores %}
                            <tr class="{{ 'top6-row' if team.is_current_top6 else '' }}">
                                <td class="rank-cell">{{ team.rank }}</td>
                                <td class="team-cell">{{ team.team_name }}</td>
                                <td class="score-cell">{{ "%.1f"|format(team.live_score) }}</td>
                                <td class="players-cell">
                                    {% if team.yet_to_play %}
                                        <div class="player-names">{{ team.yet_to_play | join(', ') }}</div>
                                    {% else %}
                                        <span class="no-players">All done</span>
                                    {% endif %}
                                </td>
                                <td class="status-cell">
                                    {% if team.rank == 1 %}
                                        <span class="status-badge top-scorer-badge">TOP SCORER</span>
                                    {% elif team.rank == scores|length %}
                                        <span class="status-badge parlay-badge">PARLAY</span>
                                    {% elif team.is_current_top6 %}
                                        <span class="status-badge current-badge">TOP 6</span>
                                    {% endif %}
                                </td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>

                <!-- Projected Standings Table -->
                <div id="projectedStandings" class="standings-table" style="display: none;">
                    <table class="standings">
                        <thead>
                            <tr>
                                <th>Rank</th>
                                <th>Team</th>
                                <th>Projected</th>
                                <th>Current</th>
                                <th>Status</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for team in scores|sort(attribute='projected_score', reverse=true) %}
                            <tr class="{{ 'top6-row' if team.is_projected_top6 else '' }}">
                                <td class="rank-cell">{{ team.projected_rank }}</td>
                                <td class="team-cell">{{ team.team_name }}</td>
                                <td class="score-cell">{{ "%.1f"|format(team.projected_score) }}</td>
                                <td class="current-score-cell">{{ "%.1f"|format(team.live_score) }}</td>
                                <td class="status-cell">
                                    {% if team.projected_rank == 1 %}
                                        <span class="status-badge top-scorer-badge">TOP SCORER</span>
                                    {% elif team.projected_rank == scores|length %}
                                        <span class="status-badge parlay-badge">PARLAY</span>
                                    {% elif team.is_projected_top6 %}
                                        <span class="status-badge projected-badge">TOP 6</span>
                                    {% endif %}
                                </td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>

                <!-- Movement Table -->
                <div id="movementStandings" class="standings-table" style="display: none;">
                    <table class="standings">
                        <thead>
                            <tr>
                                <th>Current Rank</th>
                                <th>Team</th>
                                <th>Current → Projected</th>
                                <th>Movement</th>
                                <th>Status</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for team in scores %}
                            {% set movement = team.rank - team.projected_rank %}
                            <tr class="{{ 'top6-row' if team.is_current_top6 else '' }}">
                                <td class="rank-cell">{{ team.rank }}</td>
                                <td class="team-cell">{{ team.team_name }}</td>
                                <td class="movement-scores">
                                    <span class="current-score">{{ "%.1f"|format(team.live_score) }}</span>
                                    <span class="arrow">→</span>
                                    <span class="projected-score">{{ "%.1f"|format(team.projected_score) }}</span>
                                </td>
                                <td class="movement-cell">
                                    {% if movement > 0 %}
                                        <span class="movement-up">↑{{ movement }}</span>
                                    {% elif movement < 0 %}
                                        <span class="movement-down">↓{{ movement|abs }}</span>
                                    {% else %}
                                        <span class="movement-same">—</span>
                                    {% endif %}
                                </td>
                                <td class="status-cell">
                                    {% if team.rank == 1 %}
                                        <span class="status-badge top-scorer-badge">TOP SCORER</span>
                                    {% elif team.rank == scores|length %}
                                        <span class="status-badge parlay-badge">PARLAY</span>
                                    {% elif team.is_current_top6 %}
                                        <span class="status-badge current-badge">TOP 6</span>
                                    {% endif %}
                                </td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
                {% else %}
                <div class="loading">
                    <p>🔄 Loading live scores...</p>
                    <p>Connecting to ESPN Fantasy API...</p>
                </div>
                {% endif %}
            </div>
        </body>
        </html>
        """
        
"""


class FantasyTracker:
    """Flask wrapper around the shared ScoreFetcher service."""

    def __init__(self):
        self.app = Flask(__name__)
        self.fetcher = ScoreFetcher()
        self.live_scores = []
        self.last_update: Optional[datetime] = None
        self.current_week = self.fetcher.current_week
        self.api_error: Optional[str] = None

        self._setup_routes()
        self._start_score_updates()

    # ------------------------------------------------------------------ #
    # Background refresh
    # ------------------------------------------------------------------ #
    def _start_score_updates(self):
        thread = threading.Thread(target=self._update_scores, daemon=True)
        thread.start()

    def _update_scores(self):
        consecutive_failures = 0

        while True:
            try:
                snapshot = self.fetcher.build_snapshot()
                self.live_scores = snapshot.get("scores", [])
                iso_timestamp = snapshot.get("last_update")
                self.current_week = snapshot.get("week", self.current_week)
                self.api_error = snapshot.get("api_error")

                if iso_timestamp:
                    self.last_update = datetime.fromisoformat(iso_timestamp)
                else:
                    self.last_update = datetime.utcnow()

                consecutive_failures = 0
            except Exception as exc:
                logger.warning("Score refresh failed: %s", exc)
                consecutive_failures += 1
                if "429" in str(exc) or "rate" in str(exc).lower():
                    self.api_error = "⚠️ ESPN rate limit hit, slowing down updates."
                elif "timeout" in str(exc).lower():
                    self.api_error = "⚠️ ESPN timeout. Retrying shortly."
                elif consecutive_failures > 3:
                    self.api_error = f"⚠️ Connection issues ({consecutive_failures} failures)."
                elif not self.api_error:
                    self.api_error = "⚠️ Temporary issue fetching scores."

            sleep_time = self._determine_sleep_interval(consecutive_failures)
            time.sleep(sleep_time)

    def _determine_sleep_interval(self, failures: int) -> int:
        if failures > 0:
            return min(600, 60 * (2 ** min(failures, 4)))

        try:
            has_games_today = self.fetcher.has_games_today()
        except Exception:
            has_games_today = False

        now = datetime.now()
        is_prime_time = 12 <= now.hour <= 23

        if has_games_today and is_prime_time:
            return 90
        if has_games_today:
            return 300
        return 600

    # ------------------------------------------------------------------ #
    # Routes
    # ------------------------------------------------------------------ #
    def _setup_routes(self):
        @self.app.route("/")
        def dashboard():
            return render_template_string(
                DASHBOARD_TEMPLATE,
                scores=self.live_scores,
                last_update=self.last_update,
                week=self.current_week,
                api_error=self.api_error,
            )

        @self.app.route("/api/scores")
        def api_scores():
            return jsonify(
                {
                    "scores": self.live_scores,
                    "last_update": self.last_update.isoformat() if self.last_update else None,
                    "week": self.current_week,
                    "api_error": self.api_error,
                }
            )

    def run(self, host="0.0.0.0", port: Optional[int] = None, debug: bool = False):
        if port is None:
            port = int(os.getenv("PORT", 5000))
        self.app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    tracker = FantasyTracker()
    tracker.run(debug=True)
