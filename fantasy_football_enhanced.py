import os
import logging
from datetime import datetime, timedelta
from flask import Flask, render_template_string, jsonify
import threading
import time
from espn_api.football import League
import requests
from typing import List, Dict, Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('fantasy_football.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class FantasyFootballApp:
    def __init__(self):
        self.app = Flask(__name__)
        self.league = None
        self.scores_and_players = []
        self.current_week = None
        self.last_update = None
        self.update_interval = 90  # seconds
        
        # Initialize league connection
        self._initialize_league()
        
        # Set up routes
        self._setup_routes()
        
        # Start background thread for fetching scores
        self._start_background_thread()
    
    def _initialize_league(self):
        """Initialize the ESPN Fantasy League connection with error handling."""
        try:
            # Try to get credentials from environment variables first
            league_id = os.getenv('ESPN_LEAGUE_ID', '637021')
            espn_s2 = os.getenv('ESPN_S2', 'AEBCCakbu%2B0%2FhbFeK5%2FgjfgBqJJfZKHfNjzHL2jCCx75d%2BXAUfjrRUGlUYOU%2BDcMyLnvZF9ASrpPFx%2Fd5IA4P8Yq1qMhcRE%2BqSa10zDy8NknbQWjzwKh3OVfI%2FCVZd2eKwMSzCNk54bD4FYRXMOMOVCp%2BwzXrZvHaoKs9nbe3Bsm%2BaKhCXOQ02AZbkrcGq%2B2naO9aSY3cXRoDjZaFgxYYcJnl7K23qiSoNPtt5MDZNjTeWFomxWJoC8Q84ob%2BrCve1L1ovlMK6Kg9KJ%2Br6UIYT2O')
            swid = os.getenv('ESPN_SWID', '{1BFA93C2-363A-4C34-A4BD-E6CE5E0C309B}')
            
            self.league = League(
                league_id=int(league_id), 
                year=2024, 
                espn_s2=espn_s2, 
                swid=swid
            )
            
            # Get current week
            self.current_week = self._get_current_week()
            logger.info(f"Successfully connected to league {league_id}, current week: {self.current_week}")
            
        except Exception as e:
            logger.error(f"Failed to initialize league connection: {str(e)}")
            self.league = None
    
    def _get_current_week(self) -> int:
        """Auto-detect the current NFL week."""
        try:
            if self.league:
                # Try to get current week from league settings
                current_week = getattr(self.league, 'current_week', None)
                if current_week:
                    return current_week
            
            # Fallback: Calculate based on NFL season start (approximate)
            # NFL season typically starts first Thursday in September
            # This is a simplified calculation
            now = datetime.now()
            
            # If it's before September, return week 1
            if now.month < 9:
                return 1
            
            # If it's September, calculate weeks since season start
            if now.month == 9:
                # Approximate first Thursday of September
                first_thursday = 1 + (3 - datetime(now.year, 9, 1).weekday()) % 7
                season_start = datetime(now.year, 9, first_thursday)
                
                if now < season_start:
                    return 1
                
                days_since_start = (now - season_start).days
                week = min(18, max(1, (days_since_start // 7) + 1))
                return week
            
            # For other months, use a reasonable default
            if now.month in [10, 11, 12]:
                return min(18, 8 + (now.month - 10) * 4)
            
            return 1
            
        except Exception as e:
            logger.warning(f"Could not determine current week, using week 15: {str(e)}")
            return 15
    
    def _setup_routes(self):
        """Set up Flask routes."""
        @self.app.route('/')
        def index():
            return self._render_main_page()
        
        @self.app.route('/api/scores')
        def api_scores():
            return jsonify({
                'scores': self.scores_and_players,
                'last_update': self.last_update.isoformat() if self.last_update else None,
                'current_week': self.current_week
            })
        
        @self.app.route('/health')
        def health():
            return jsonify({
                'status': 'healthy' if self.league else 'unhealthy',
                'league_connected': self.league is not None,
                'last_update': self.last_update.isoformat() if self.last_update else None
            })
    
    def _start_background_thread(self):
        """Start the background thread for fetching scores."""
        thread = threading.Thread(target=self._fetch_scores_loop, daemon=True)
        thread.start()
        logger.info("Background score fetching thread started")
    
    def _fetch_scores_loop(self):
        """Continuously fetch scores every update_interval seconds."""
        while True:
            try:
                if self.league:
                    self.scores_and_players = self._get_team_scores_with_starters()
                    self.last_update = datetime.now()
                    logger.info(f"Updated scores for {len(self.scores_and_players)} teams")
                else:
                    logger.warning("League not connected, skipping score update")
                    
            except Exception as e:
                logger.error(f"Error fetching scores: {str(e)}")
            
            time.sleep(self.update_interval)
    
    def _get_team_scores_with_starters(self) -> List[Dict]:
        """
        Fetch live scores and determine player statuses with enhanced error handling.
        """
        try:
            box_scores = self.league.box_scores(week=self.current_week)
            scores_and_players = []

            for game in box_scores:
                # Process both home and away teams
                teams_data = [
                    (game.home_team, game.home_lineup, game.home_score),
                    (game.away_team, game.away_lineup, game.away_score)
                ]
                
                for team, lineup, score in teams_data:
                    try:
                        # Get team name safely
                        team_name = getattr(team, 'team_name', 'Unknown Team')
                        if not team_name or team_name == 'Unknown Team':
                            # Try alternative attributes
                            team_name = getattr(team, 'team_abbrev', f'Team {getattr(team, "team_id", "Unknown")}')
                        
                        # Analyze player statuses
                        currently_playing = []
                        not_started = []
                        finished_playing = []
                        
                        for player in lineup:
                            if player.slot_position == "BE":  # Skip bench players
                                continue
                            
                            player_name = getattr(player, 'name', 'Unknown Player')
                            
                            # Determine player status
                            if hasattr(player, 'game_played') and player.game_played == 1:
                                if hasattr(player, 'points') and player.points > 0:
                                    currently_playing.append(player_name)
                                else:
                                    finished_playing.append(player_name)
                            elif hasattr(player, 'game_played') and player.game_played == 0:
                                not_started.append(player_name)
                            else:
                                # Fallback logic based on points
                                if hasattr(player, 'points') and player.points > 0:
                                    currently_playing.append(player_name)
                                else:
                                    not_started.append(player_name)
                        
                        # Format player lists
                        currently_playing_str = ", ".join(currently_playing) if currently_playing else "No players currently playing"
                        not_started_str = ", ".join(not_started) if not_started else "All players have played"
                        finished_playing_str = ", ".join(finished_playing) if finished_playing else "No players finished"
                        
                        scores_and_players.append({
                            'Team Name': team_name,
                            'Live Score': float(score) if score else 0.0,
                            'Starters Currently Playing': currently_playing_str,
                            'Starters Yet to Play': not_started_str,
                            'Finished Playing': finished_playing_str,
                            'Total Starters': len([p for p in lineup if p.slot_position != "BE"])
                        })
                        
                    except Exception as e:
                        logger.error(f"Error processing team data: {str(e)}")
                        # Add a placeholder entry for this team
                        scores_and_players.append({
                            'Team Name': 'Error Loading Team',
                            'Live Score': 0.0,
                            'Starters Currently Playing': 'Error loading data',
                            'Starters Yet to Play': 'Error loading data',
                            'Finished Playing': 'Error loading data',
                            'Total Starters': 0
                        })

            # Sort by live score (descending)
            scores_and_players.sort(key=lambda x: x['Live Score'], reverse=True)
            
            return scores_and_players
            
        except Exception as e:
            logger.error(f"Error in _get_team_scores_with_starters: {str(e)}")
            return [{
                'Team Name': 'Error Loading Data',
                'Live Score': 0.0,
                'Starters Currently Playing': f'Error: {str(e)}',
                'Starters Yet to Play': 'Unable to load',
                'Finished Playing': 'Unable to load',
                'Total Starters': 0
            }]
    
    def _render_main_page(self):
        """Render the main HTML page with enhanced UI."""
        html_template = """
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>🏈 Live Fantasy Football Scores</title>
            <style>
                * {
                    margin: 0;
                    padding: 0;
                    box-sizing: border-box;
                }
                
                body {
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    min-height: 100vh;
                    padding: 20px;
                    color: #333;
                }
                
                .container {
                    max-width: 1200px;
                    margin: 0 auto;
                    background: rgba(255, 255, 255, 0.95);
                    border-radius: 20px;
                    box-shadow: 0 20px 40px rgba(0, 0, 0, 0.1);
                    overflow: hidden;
                    backdrop-filter: blur(10px);
                }
                
                .header {
                    background: linear-gradient(135deg, #2c3e50 0%, #3498db 100%);
                    color: white;
                    padding: 30px;
                    text-align: center;
                }
                
                .header h1 {
                    font-size: 2.5em;
                    margin-bottom: 10px;
                    text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.3);
                }
                
                .header .subtitle {
                    font-size: 1.1em;
                    opacity: 0.9;
                    margin-bottom: 15px;
                }
                
                .status-bar {
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    background: rgba(255, 255, 255, 0.1);
                    padding: 15px 30px;
                    margin-top: 20px;
                    border-radius: 10px;
                }
                
                .status-item {
                    display: flex;
                    align-items: center;
                    gap: 8px;
                }
                
                .status-indicator {
                    width: 12px;
                    height: 12px;
                    border-radius: 50%;
                    background: #2ecc71;
                    animation: pulse 2s infinite;
                }
                
                @keyframes pulse {
                    0% { opacity: 1; }
                    50% { opacity: 0.5; }
                    100% { opacity: 1; }
                }
                
                .table-container {
                    padding: 30px;
                    overflow-x: auto;
                }
                
                table {
                    width: 100%;
                    border-collapse: collapse;
                    border-radius: 15px;
                    overflow: hidden;
                    box-shadow: 0 10px 25px rgba(0, 0, 0, 0.1);
                }
                
                th {
                    background: linear-gradient(135deg, #34495e 0%, #2c3e50 100%);
                    color: white;
                    padding: 20px 15px;
                    text-align: left;
                    font-weight: 600;
                    font-size: 0.95em;
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                }
                
                td {
                    padding: 18px 15px;
                    border-bottom: 1px solid #ecf0f1;
                    transition: all 0.3s ease;
                }
                
                tr:nth-child(even) {
                    background-color: #f8f9fa;
                }
                
                tr:hover {
                    background-color: #e3f2fd;
                    transform: scale(1.01);
                    box-shadow: 0 5px 15px rgba(0, 0, 0, 0.1);
                }
                
                .team-name {
                    font-weight: 700;
                    color: #2c3e50;
                    font-size: 1.1em;
                }
                
                .score {
                    font-weight: 700;
                    font-size: 1.3em;
                    color: #e74c3c;
                    text-align: center;
                }
                
                .score.top-score {
                    color: #27ae60;
                    text-shadow: 0 0 10px rgba(39, 174, 96, 0.3);
                }
                
                .player-list {
                    font-size: 0.9em;
                    line-height: 1.4;
                    max-width: 300px;
                }
                
                .playing {
                    color: #27ae60;
                    font-weight: 500;
                }
                
                .not-started {
                    color: #f39c12;
                    font-weight: 500;
                }
                
                .finished {
                    color: #7f8c8d;
                    font-style: italic;
                }
                
                .footer {
                    background: #ecf0f1;
                    padding: 20px 30px;
                    text-align: center;
                    color: #7f8c8d;
                    font-size: 0.9em;
                }
                
                .loading {
                    text-align: center;
                    padding: 50px;
                    font-size: 1.2em;
                    color: #7f8c8d;
                }
                
                .error {
                    background: #e74c3c;
                    color: white;
                    padding: 15px;
                    border-radius: 10px;
                    margin: 20px;
                    text-align: center;
                }
                
                @media (max-width: 768px) {
                    .container {
                        margin: 10px;
                        border-radius: 15px;
                    }
                    
                    .header {
                        padding: 20px;
                    }
                    
                    .header h1 {
                        font-size: 2em;
                    }
                    
                    .status-bar {
                        flex-direction: column;
                        gap: 10px;
                        text-align: center;
                    }
                    
                    .table-container {
                        padding: 15px;
                    }
                    
                    th, td {
                        padding: 12px 8px;
                        font-size: 0.85em;
                    }
                    
                    .player-list {
                        max-width: 200px;
                    }
                }
            </style>
            <script>
                let lastUpdate = null;
                
                function updateScores() {
                    fetch('/api/scores')
                        .then(response => response.json())
                        .then(data => {
                            if (data.last_update !== lastUpdate) {
                                location.reload();
                            }
                        })
                        .catch(error => {
                            console.error('Error fetching scores:', error);
                        });
                }
                
                // Update every 30 seconds (faster than server updates for responsiveness)
                setInterval(updateScores, 30000);
                
                // Auto-refresh every 90 seconds as backup
                setTimeout(function() {
                    location.reload();
                }, 90000);
            </script>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🏈 Live Fantasy Football Scores</h1>
                    <div class="subtitle">Week {{ current_week }} • Real-time Updates</div>
                    <div class="status-bar">
                        <div class="status-item">
                            <div class="status-indicator"></div>
                            <span>Live Updates</span>
                        </div>
                        <div class="status-item">
                            <span>Teams: {{ scores|length }}</span>
                        </div>
                        <div class="status-item">
                            <span>Last Update: {{ last_update.strftime('%I:%M:%S %p') if last_update else 'Loading...' }}</span>
                        </div>
                    </div>
                </div>
                
                {% if scores %}
                <div class="table-container">
                    <table>
                        <thead>
                            <tr>
                                <th>Rank</th>
                                <th>Team Name</th>
                                <th>Live Score</th>
                                <th>Currently Playing</th>
                                <th>Yet to Play</th>
                                <th>Finished</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for entry in scores %}
                            <tr>
                                <td style="text-align: center; font-weight: bold; color: #3498db;">{{ loop.index }}</td>
                                <td class="team-name">{{ entry['Team Name'] }}</td>
                                <td class="score{% if loop.index == 1 %} top-score{% endif %}">{{ "%.1f"|format(entry['Live Score']) }}</td>
                                <td class="player-list playing">{{ entry['Starters Currently Playing'] }}</td>
                                <td class="player-list not-started">{{ entry['Starters Yet to Play'] }}</td>
                                <td class="player-list finished">{{ entry['Finished Playing'] }}</td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
                {% else %}
                <div class="loading">
                    <p>Loading scores...</p>
                    <p>If this persists, there may be an issue connecting to the ESPN API.</p>
                </div>
                {% endif %}
                
                <div class="footer">
                    <p>Updates automatically every 90 seconds • Data from ESPN Fantasy Football</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return render_template_string(
            html_template, 
            scores=self.scores_and_players,
            current_week=self.current_week,
            last_update=self.last_update
        )
    
    def run(self, host="0.0.0.0", port=None, debug=False):
        """Run the Flask application."""
        # Use PORT environment variable if available (for cloud deployment)
        if port is None:
            port = int(os.getenv('PORT', 5000))
        
        logger.info(f"Starting Fantasy Football app on {host}:{port}")
        self.app.run(host=host, port=port, debug=debug)

# Create and run the application
if __name__ == "__main__":
    app = FantasyFootballApp()
    # Don't use debug mode in production
    debug_mode = os.getenv('FLASK_ENV') == 'development'
    app.run(debug=debug_mode)
