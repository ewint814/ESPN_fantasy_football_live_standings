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

import os
import logging
from datetime import datetime
from flask import Flask, render_template_string, jsonify
import threading
import time
from espn_api.football import League
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class FantasyTracker:
    def __init__(self):
        self.app = Flask(__name__)
        self.league = None
        self.live_scores = []
        self.last_update = None
        self.current_week = self._get_current_week()
        
        # Initialize ESPN connection
        self._connect_to_espn()
        
        # Set up web routes
        self._setup_routes()
        
        # Start background score updates
        self._start_score_updates()
    
    def _connect_to_espn(self):
        """Connect to ESPN Fantasy Football API"""
        try:
            league_id = os.getenv('ESPN_LEAGUE_ID', '637021')
            espn_s2 = os.getenv('ESPN_S2', 'AEBCCakbu%2B0%2FhbFeK5%2FgjfgBqJJfZKHfNjzHL2jCCx75d%2BXAUfjrRUGlUYOU%2BDcMyLnvZF9ASrpPFx%2Fd5IA4P8Yq1qMhcRE%2BqSa10zDy8NknbQWjzwKh3OVfI%2FCVZd2eKwMSzCNk54bD4FYRXMOMOVCp%2BwzXrZvHaoKs9nbe3Bsm%2BaKhCXOQ02AZbkrcGq%2B2naO9aSY3cXRoDjZaFgxYYcJnl7K23qiSoNPtt5MDZNjTeWFomxWJoC8Q84ob%2BrCve1L1ovlMK6Kg9KJ%2Br6UIYT2O')
            swid = os.getenv('ESPN_SWID', '{1BFA93C2-363A-4C34-A4BD-E6CE5E0C309B}')
            
            self.league = League(
                league_id=int(league_id),
                year=2025,
                espn_s2=espn_s2,
                swid=swid
            )
            
            logger.info(f"✅ Connected to ESPN league {league_id}")
            logger.info(f"🗓️  League year: {self.league.year}")
            logger.info(f"📅 Current week will be: {self._get_current_week()}")
            
        except Exception as e:
            logger.error(f"❌ Failed to connect to ESPN: {e}")
            self.league = None
    
    def _get_current_week(self):
        """Auto-detect the current NFL week."""
        try:
            if self.league:
                # Try to get current week from league settings
                current_week = getattr(self.league, 'current_week', None)
                if current_week:
                    return current_week
            
            now = datetime.now()
            
            # For 2025 NFL season (September 2025 onwards)
            if now.year == 2025 and now.month >= 9:
                # NFL season typically starts first Thursday of September
                # For 2025, let's estimate it started around September 5th
                season_start = datetime(2025, 9, 5)  # Approximate 2025 season start
                
                if now < season_start:
                    return 1
                
                days_since_start = (now - season_start).days
                week = min(18, max(1, (days_since_start // 7) + 1))
                return week
            
            # If it's early 2025 (before September), we're in offseason
            elif now.year == 2025 and now.month <= 3:
                return 1  # Offseason/early season
            
            # If it's September 2024 or later in 2024, calculate based on that season
            elif now.year == 2024 and now.month >= 9:
                first_thursday = 1 + (3 - datetime(2024, 9, 1).weekday()) % 7
                season_start = datetime(2024, 9, first_thursday)
                
                if now < season_start:
                    return 1
                
                days_since_start = (now - season_start).days
                week = min(18, max(1, (days_since_start // 7) + 1))
                return week
            
            # Default for any other case
            return 1
            
        except Exception as e:
            logger.warning(f"Could not determine current week, using week 1: {str(e)}")
            return 1
    
    def _get_live_scores(self):
        """Fetch current live scores and player info"""
        if not self.league:
            return []
        
        try:
            logger.info(f"🔍 Fetching scores for week {self.current_week}")
            box_scores = self.league.box_scores(week=self.current_week)
            teams_data = []
            
            for matchup in box_scores:
                # Process both home and away teams
                for team, lineup, score in [
                    (matchup.home_team, matchup.home_lineup, matchup.home_score),
                    (matchup.away_team, matchup.away_lineup, matchup.away_score)
                ]:
                    # Get team name safely
                    team_name = getattr(team, 'team_name', 'Unknown Team')
                    
                    # Analyze player statuses (simplified - no projections for now)
                    currently_playing = []
                    yet_to_play = []
                    finished_playing = []
                    total_starters = 0
                    
                    for player in lineup:
                        # Skip bench players
                        if player.slot_position == "BE":
                            continue
                            
                        total_starters += 1
                        player_name = getattr(player, 'name', 'Unknown')
                        player_points = getattr(player, 'points', 0)
                        
                        # Enhanced player status detection using game_played
                        game_played = getattr(player, 'game_played', None)
                        
                        if game_played == 0:
                            # Game hasn't started yet
                            yet_to_play.append(player_name)
                        elif game_played == 100:
                            # Game is finished
                            finished_playing.append(f"{player_name} ({player_points:.1f})")
                        elif game_played == 1:
                            # Game is in progress
                            currently_playing.append(f"{player_name} ({player_points:.1f})")
                        elif game_played == 2:
                            # Alternative finished status
                            finished_playing.append(f"{player_name} ({player_points:.1f})")
                        else:
                            # Fallback for unclear status - assume not played yet
                            yet_to_play.append(player_name)
                    
                    logger.info(f"📊 {team_name}: Live: {score}, Playing: {len(currently_playing)}, Remaining: {len(yet_to_play)}, Finished: {len(finished_playing)}")
                    
                    teams_data.append({
                        'team_name': team_name,
                        'live_score': float(score) if score else 0.0,
                        'currently_playing': currently_playing,
                        'yet_to_play': yet_to_play,
                        'finished_playing': finished_playing,
                        'players_playing_count': len(currently_playing),
                        'players_remaining_count': len(yet_to_play),
                        'players_finished_count': len(finished_playing),
                        'total_starters': total_starters
                    })
            
            # Sort by live score (highest first)
            teams_data.sort(key=lambda x: x['live_score'], reverse=True)
            
            # Add ranking and top 6 status
            for i, team in enumerate(teams_data):
                team['rank'] = i + 1
                team['is_top6'] = i < 6  # Top 6 get the extra win
            
            return teams_data
            
        except Exception as e:
            logger.error(f"Error fetching scores: {e}")
            return []
    
    def _update_scores(self):
        """Background function to update scores every 90 seconds"""
        while True:
            try:
                self.live_scores = self._get_live_scores()
                self.last_update = datetime.now()
                logger.info(f"📊 Updated scores - {len(self.live_scores)} teams")
                
            except Exception as e:
                logger.error(f"Error in score update: {e}")
                
            time.sleep(90)  # Update every 90 seconds
    
    def _start_score_updates(self):
        """Start the background score update thread"""
        thread = threading.Thread(target=self._update_scores, daemon=True)
        thread.start()
        logger.info("🔄 Started background score updates")
    
    def _setup_routes(self):
        """Set up Flask web routes"""
        
        @self.app.route('/')
        def dashboard():
            return self._render_dashboard()
        
        @self.app.route('/api/scores')
        def api_scores():
            return jsonify({
                'scores': self.live_scores,
                'last_update': self.last_update.isoformat() if self.last_update else None,
                'week': self.current_week
            })
    
    def _render_dashboard(self):
        """Render the main dashboard HTML"""
        template = """
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
            </div>
            
            <div class="container">
                {% if scores %}
                <div class="standings-table">
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
                            <tr class="{{ 'top6-row' if team.is_top6 else '' }}">
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
                                    {% if team.is_top6 %}
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
        
        return render_template_string(
            template,
            scores=self.live_scores,
            last_update=self.last_update,
            week=self.current_week
        )
    
    def run(self, host="0.0.0.0", port=None, debug=False):
        """Start the web server"""
        if port is None:
            port = int(os.getenv('PORT', 5000))
        
        logger.info(f"🚀 Starting Fantasy Tracker on http://{host}:{port}")
        self.app.run(host=host, port=port, debug=debug)

if __name__ == "__main__":
    tracker = FantasyTracker()
    tracker.run(debug=True)
