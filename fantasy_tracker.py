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
            
            # For 2025 season, we're in the early weeks
            now = datetime.now()
            
            # If it's 2025 and before March, we're in the new season
            if now.year == 2025 and now.month <= 3:
                return 1  # Early 2025 season
            
            # If it's September 2024 or later in 2024, calculate based on that season
            if now.year == 2024:
                if now.month >= 9:
                    # Approximate first Thursday of September 2024
                    first_thursday = 1 + (3 - datetime(2024, 9, 1).weekday()) % 7
                    season_start = datetime(2024, 9, first_thursday)
                    
                    if now < season_start:
                        return 1
                    
                    days_since_start = (now - season_start).days
                    week = min(18, max(1, (days_since_start // 7) + 1))
                    return week
                else:
                    return 1
            
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
                    
                    # Analyze player statuses
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
                        
                        # Enhanced player status detection
                        game_played = getattr(player, 'game_played', None)
                        
                        if game_played == 0:  # Game hasn't started yet
                            yet_to_play.append(player_name)
                        elif game_played == 1:  # Game is in progress or finished
                            if player_points > 0:
                                # Player has scored points, likely playing or finished
                                if hasattr(player, 'game_date') and hasattr(player, 'game_status'):
                                    # Try to determine if game is still active
                                    currently_playing.append(f"{player_name} ({player_points:.1f})")
                                else:
                                    currently_playing.append(f"{player_name} ({player_points:.1f})")
                            else:
                                # Game played but no points yet (could be currently playing)
                                currently_playing.append(f"{player_name} (0.0)")
                        elif game_played == 2:  # Game finished
                            finished_playing.append(f"{player_name} ({player_points:.1f})")
                        else:
                            # Fallback logic based on points
                            if player_points > 0:
                                currently_playing.append(f"{player_name} ({player_points:.1f})")
                            else:
                                yet_to_play.append(player_name)
                    
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
            
            # Add ranking
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
                    background: #f8fafc;
                    min-height: 100vh;
                    color: #1e293b;
                    line-height: 1.5;
                    padding: 0;
                    margin: 0;
                }
                
                .header {
                    background: white;
                    border-bottom: 1px solid #e2e8f0;
                    padding: 24px 20px;
                    text-align: center;
                    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
                }
                
                .header h1 {
                    font-size: 2.2em;
                    font-weight: 700;
                    color: #1e293b;
                    margin-bottom: 8px;
                }
                
                .week-info {
                    font-size: 1.1em;
                    color: #64748b;
                    margin-bottom: 8px;
                    font-weight: 500;
                }
                
                .last-update {
                    font-size: 0.9em;
                    color: #94a3b8;
                }
                
                .container {
                    max-width: 900px;
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
                
                .scores-list {
                    display: flex;
                    flex-direction: column;
                    gap: 12px;
                }
                
                .team-card {
                    background: white;
                    border-radius: 8px;
                    border: 1px solid #e2e8f0;
                    transition: all 0.2s ease;
                    overflow: hidden;
                }
                
                .team-card:hover {
                    border-color: #cbd5e1;
                    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
                }
                
                .team-card.top6 {
                    border-left: 4px solid #10b981;
                    background: linear-gradient(90deg, rgba(16, 185, 129, 0.05) 0%, white 100%);
                }
                
                .team-header {
                    display: grid;
                    grid-template-columns: 60px 1fr 100px;
                    align-items: center;
                    padding: 20px;
                    background: #f8fafc;
                    border-bottom: 1px solid #e2e8f0;
                    gap: 16px;
                }
                
                .team-rank {
                    font-size: 2.2em;
                    font-weight: 800;
                    color: #64748b;
                    text-align: center;
                    line-height: 1;
                }
                
                .top6 .team-rank {
                    color: #10b981;
                }
                
                .team-name {
                    font-size: 1.2em;
                    font-weight: 600;
                    color: #1e293b;
                    line-height: 1.3;
                }
                
                .team-score {
                    font-weight: 700;
                    font-size: 1.8em;
                    color: #dc2626;
                    text-align: right;
                    line-height: 1;
                }
                
                .top6 .team-score {
                    color: #10b981;
                }
                
                .finished {
                    color: #95a5a6;
                    font-style: italic;
                }
                
                .top6-badge {
                    background: #10b981;
                    color: white;
                    padding: 4px 8px;
                    border-radius: 4px;
                    font-size: 0.7em;
                    font-weight: 600;
                    margin-left: 8px;
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                }
                
                .player-info {
                    padding: 16px 20px 20px;
                    background: white;
                }
                
                .player-section {
                    margin-bottom: 12px;
                    padding: 12px;
                    border-radius: 6px;
                    border: 1px solid #e2e8f0;
                }
                
                .player-section:last-child {
                    margin-bottom: 0;
                }
                
                .player-section.playing-section {
                    background: rgba(16, 185, 129, 0.05);
                    border-color: rgba(16, 185, 129, 0.2);
                }
                
                .player-section.remaining-section {
                    background: rgba(245, 158, 11, 0.05);
                    border-color: rgba(245, 158, 11, 0.2);
                }
                
                .player-section.finished-section {
                    background: rgba(107, 114, 128, 0.05);
                    border-color: rgba(107, 114, 128, 0.2);
                }
                
                .player-label {
                    font-weight: 600;
                    font-size: 0.9em;
                    margin-bottom: 8px;
                    display: flex;
                    align-items: center;
                    gap: 8px;
                }
                
                .playing .player-label {
                    color: #059669;
                }
                
                .remaining .player-label {
                    color: #d97706;
                }
                
                .finished .player-label {
                    color: #6b7280;
                }
                
                .player-list {
                    font-size: 0.85em;
                    line-height: 1.5;
                    color: #374151;
                }
                
                .player-count {
                    background: rgba(0, 0, 0, 0.1);
                    color: rgba(0, 0, 0, 0.7);
                    padding: 2px 6px;
                    border-radius: 12px;
                    font-size: 0.8em;
                    font-weight: 500;
                    min-width: 20px;
                    text-align: center;
                }
                
                .loading {
                    text-align: center;
                    color: white;
                    font-size: 1.2em;
                    padding: 50px;
                }
                
                @media (max-width: 768px) {
                    .header h1 {
                        font-size: 2em;
                    }
                    
                    .team-header {
                        flex-direction: column;
                        text-align: center;
                    }
                    
                    .team-name {
                        margin: 10px 0;
                    }
                    
                    .scores-list {
                        margin: 0 10px;
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
                <div class="scores-list">
                    {% for team in scores %}
                    <div class="team-card {{ 'top6' if team.is_top6 else '' }}">
                        <div class="team-header">
                            <div class="team-rank">#{{ team.rank }}</div>
                            <div class="team-name">{{ team.team_name }}</div>
                            <div class="team-score">
                                {{ "%.1f"|format(team.live_score) }}
                                {% if team.is_top6 %}
                                <span class="top6-badge">TOP 6</span>
                                {% endif %}
                            </div>
                        </div>
                        
                        <div class="player-info">
                            {% if team.currently_playing %}
                            <div class="player-section playing-section playing">
                                <div class="player-label">
                                    <span>🟢 Currently Playing</span>
                                    <span class="player-count">{{ team.players_playing_count }}</span>
                                </div>
                                <div class="player-list">
                                    {{ team.currently_playing | join(', ') }}
                                </div>
                            </div>
                            {% endif %}
                            
                            {% if team.yet_to_play %}
                            <div class="player-section remaining-section remaining">
                                <div class="player-label">
                                    <span>⏳ Yet to Play</span>
                                    <span class="player-count">{{ team.players_remaining_count }}</span>
                                </div>
                                <div class="player-list">
                                    {{ team.yet_to_play | join(', ') }}
                                </div>
                            </div>
                            {% endif %}
                            
                            {% if team.finished_playing %}
                            <div class="player-section finished-section finished">
                                <div class="player-label">
                                    <span>✅ Finished Playing</span>
                                    <span class="player-count">{{ team.players_finished_count }}</span>
                                </div>
                                <div class="player-list">
                                    {{ team.finished_playing | join(', ') }}
                                </div>
                            </div>
                            {% endif %}
                            
                            {% if not team.currently_playing and not team.yet_to_play and not team.finished_playing %}
                            <div class="player-section">
                                <div class="player-label">✅ All players finished</div>
                            </div>
                            {% endif %}
                        </div>
                    </div>
                    {% endfor %}
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
