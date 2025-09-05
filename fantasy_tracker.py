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
        self.current_week = 15  # Will auto-detect later
        
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
                year=2024,
                espn_s2=espn_s2,
                swid=swid
            )
            
            logger.info(f"✅ Connected to ESPN league {league_id}")
            
        except Exception as e:
            logger.error(f"❌ Failed to connect to ESPN: {e}")
            self.league = None
    
    def _get_live_scores(self):
        """Fetch current live scores and player info"""
        if not self.league:
            return []
        
        try:
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
                    total_starters = 0
                    
                    for player in lineup:
                        # Skip bench players
                        if player.slot_position == "BE":
                            continue
                            
                        total_starters += 1
                        player_name = getattr(player, 'name', 'Unknown')
                        
                        # Check if player is currently playing or yet to play
                        if hasattr(player, 'game_played'):
                            if player.game_played == 0:  # Game hasn't started
                                yet_to_play.append(player_name)
                            elif player.game_played == 1 and hasattr(player, 'points') and player.points > 0:
                                currently_playing.append(player_name)
                        else:
                            # Fallback: if they have points, assume playing
                            if hasattr(player, 'points') and player.points > 0:
                                currently_playing.append(player_name)
                            else:
                                yet_to_play.append(player_name)
                    
                    teams_data.append({
                        'team_name': team_name,
                        'live_score': float(score) if score else 0.0,
                        'currently_playing': currently_playing,
                        'yet_to_play': yet_to_play,
                        'players_playing_count': len(currently_playing),
                        'players_remaining_count': len(yet_to_play),
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
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
                    min-height: 100vh;
                    color: #333;
                }
                
                .header {
                    background: rgba(0,0,0,0.2);
                    color: white;
                    padding: 20px;
                    text-align: center;
                    backdrop-filter: blur(10px);
                }
                
                .header h1 {
                    font-size: 2.5em;
                    margin-bottom: 10px;
                    text-shadow: 2px 2px 4px rgba(0,0,0,0.5);
                }
                
                .week-info {
                    font-size: 1.2em;
                    opacity: 0.9;
                    margin-bottom: 10px;
                }
                
                .last-update {
                    font-size: 0.9em;
                    opacity: 0.8;
                }
                
                .container {
                    max-width: 1200px;
                    margin: 20px auto;
                    padding: 0 20px;
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
                
                .scores-grid {
                    display: grid;
                    gap: 15px;
                    grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
                }
                
                .team-card {
                    background: rgba(255,255,255,0.95);
                    border-radius: 15px;
                    padding: 20px;
                    box-shadow: 0 8px 25px rgba(0,0,0,0.15);
                    transition: transform 0.3s ease, box-shadow 0.3s ease;
                    border-left: 5px solid #ddd;
                }
                
                .team-card:hover {
                    transform: translateY(-5px);
                    box-shadow: 0 12px 35px rgba(0,0,0,0.2);
                }
                
                .team-card.top6 {
                    border-left: 5px solid #27ae60;
                    background: linear-gradient(135deg, rgba(39,174,96,0.1) 0%, rgba(255,255,255,0.95) 100%);
                }
                
                .team-header {
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    margin-bottom: 15px;
                }
                
                .team-rank {
                    font-size: 1.5em;
                    font-weight: bold;
                    color: #3498db;
                    min-width: 40px;
                }
                
                .team-name {
                    font-size: 1.3em;
                    font-weight: bold;
                    color: #2c3e50;
                    flex-grow: 1;
                    margin: 0 15px;
                }
                
                .team-score {
                    font-size: 2em;
                    font-weight: bold;
                    color: #e74c3c;
                }
                
                .top6 .team-score {
                    color: #27ae60;
                }
                
                .top6-badge {
                    background: #27ae60;
                    color: white;
                    padding: 4px 12px;
                    border-radius: 20px;
                    font-size: 0.8em;
                    font-weight: bold;
                    margin-left: 10px;
                    animation: pulse 2s infinite;
                }
                
                @keyframes pulse {
                    0% { opacity: 1; }
                    50% { opacity: 0.7; }
                    100% { opacity: 1; }
                }
                
                .player-info {
                    margin-top: 15px;
                }
                
                .player-section {
                    margin-bottom: 10px;
                }
                
                .player-label {
                    font-weight: bold;
                    color: #34495e;
                    margin-bottom: 5px;
                }
                
                .playing {
                    color: #27ae60;
                }
                
                .remaining {
                    color: #f39c12;
                }
                
                .player-list {
                    font-size: 0.9em;
                    line-height: 1.4;
                }
                
                .player-count {
                    display: inline-block;
                    background: #ecf0f1;
                    padding: 2px 8px;
                    border-radius: 12px;
                    font-size: 0.8em;
                    margin-left: 8px;
                }
                
                .loading {
                    text-align: center;
                    color: white;
                    font-size: 1.2em;
                    padding: 50px;
                }
                
                @media (max-width: 768px) {
                    .scores-grid {
                        grid-template-columns: 1fr;
                    }
                    
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
                <div class="legend">
                    <h3>Scoring System</h3>
                    <div class="legend-item">
                        <span class="top6-indicator">🏆 TOP 6</span> = Extra Win
                    </div>
                    <div class="legend-item">
                        Head-to-Head Win + Top 6 Bonus = 2 Wins Possible
                    </div>
                </div>
                
                {% if scores %}
                <div class="scores-grid">
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
                            <div class="player-section">
                                <div class="player-label playing">
                                    🟢 Currently Playing 
                                    <span class="player-count">{{ team.players_playing_count }}</span>
                                </div>
                                <div class="player-list">
                                    {{ team.currently_playing | join(', ') }}
                                </div>
                            </div>
                            {% endif %}
                            
                            {% if team.yet_to_play %}
                            <div class="player-section">
                                <div class="player-label remaining">
                                    ⏳ Yet to Play 
                                    <span class="player-count">{{ team.players_remaining_count }}</span>
                                </div>
                                <div class="player-list">
                                    {{ team.yet_to_play | join(', ') }}
                                </div>
                            </div>
                            {% endif %}
                            
                            {% if not team.currently_playing and not team.yet_to_play %}
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
