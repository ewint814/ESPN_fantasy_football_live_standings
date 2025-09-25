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
import requests
from datetime import datetime, timedelta
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
    # =============================================================================
    # INITIALIZATION & SETUP
    # =============================================================================
    
    def __init__(self):
        self.app = Flask(__name__)
        self.league = None
        self.live_scores = []
        self.last_update = None
        self.current_week = self._get_current_week()
        self.game_clocks = {}  # Cache for NFL game clock data
        self.api_error = None  # Track API errors for user display
        self.games_today_cache = None  # Cache if there are games today
        self.games_check_date = None  # What date we last checked for games
        
        # Initialize ESPN connection
        self._connect_to_espn()
        
        # Set up web routes
        self._setup_routes()
        
        # Start background score updates
        self._start_score_updates()
    
    # =============================================================================
    # ESPN API CONNECTION & DATA FETCHING
    # =============================================================================
    
    def _connect_to_espn(self):
        """Connect to ESPN Fantasy Football API"""
        try:
            league_id = os.getenv('ESPN_LEAGUE_ID')
            espn_s2 = os.getenv('ESPN_S2')
            swid = os.getenv('ESPN_SWID')
            
            if not all([league_id, espn_s2, swid]):
                raise ValueError("Missing required environment variables: ESPN_LEAGUE_ID, ESPN_S2, ESPN_SWID")
            
            self.league = League(
                league_id=int(league_id),
                year=2025,
                espn_s2=espn_s2,
                swid=swid
            )
            
            # Test the connection
            teams = self.league.teams
            return True
        except Exception as e:
            self.league = None
            return False
    
    def _get_current_week(self):
        """Get current NFL week using ESPN's scoreboard API."""
        try:
            # First try ESPN's NFL scoreboard API - most reliable
            response = requests.get('https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard')
            if response.status_code == 200:
                data = response.json()
                if 'week' in data and 'number' in data['week']:
                    return data['week']['number']
            
            # Fallback: try to get it from the league object
            if self.league and hasattr(self.league, 'current_week'):
                return self.league.current_week
            
            # Last resort: simple calculation for current season (2025)
            now = datetime.now()
            if now.year == 2025 and now.month >= 9:
                # 2025 season starts around September 4th
                season_start = datetime(2025, 9, 4)
                if now < season_start:
                    return 1
                days_since_start = (now - season_start).days
                return min(18, max(1, (days_since_start // 7) + 1))
            elif now.year == 2025 and now.month <= 2:
                # Playoffs/offseason from 2024 season
                return 18
            elif now.year == 2024 and now.month >= 9:
                # 2024 season (for historical reference)
                season_start = datetime(2024, 9, 5)
                if now < season_start:
                    return 1
                days_since_start = (now - season_start).days
                return min(18, max(1, (days_since_start // 7) + 1))
            
            return 3  # Safe default for current time of year
            
        except Exception:
            return 3  # Safe fallback
    
    # =============================================================================
    # GAME CLOCK & PROJECTION CALCULATIONS
    # =============================================================================
    
    def _get_nfl_game_clocks(self):
        """Get live game clock data from NFL API"""
        try:
            nfl_url = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
            response = requests.get(nfl_url)
            
            if response.status_code == 200:
                data = response.json()
                games = data.get('events', [])
                
                game_clocks = {}
                
                for game in games:
                    # Get team abbreviations
                    competitors = game.get('competitions', [{}])[0].get('competitors', [])
                    if len(competitors) >= 2:
                        team1 = competitors[0].get('team', {}).get('abbreviation', '')
                        team2 = competitors[1].get('team', {}).get('abbreviation', '')
                        
                        status = game.get('status', {})
                        clock = status.get('displayClock', '0:00')
                        period = status.get('period', 1)
                        game_status = status.get('type', {}).get('name', 'unknown')
                        
                        # Calculate minutes played
                        minutes_played = self._calculate_minutes_played(clock, period, game_status)
                        
                        # Store for both teams
                        for team in [team1, team2]:
                            if team:
                                game_clocks[team] = {
                                    'clock': clock,
                                    'period': period,
                                    'status': game_status,
                                    'minutes_played': minutes_played,
                                    'game_progress': min(minutes_played / 60.0, 1.0)
                                }
                
                return game_clocks
            
        except Exception as e:
            return {}
    
    def _calculate_minutes_played(self, clock, period, status):
        """Calculate how many minutes have been played in the game"""
        try:
            
            # More comprehensive status checking
            status_lower = status.lower()
            
            # Game is finished
            if any(word in status_lower for word in ['final', 'finished', 'end']):
                return 60  # Game is over
            
            # Game hasn't started
            if any(word in status_lower for word in ['scheduled', 'pre', 'upcoming']):
                return 0  # Game hasn't started
            
            # Parse clock (format like "12:34" or "0:00")
            if ':' in clock:
                minutes, seconds = clock.split(':')
                remaining_in_quarter = int(minutes) + int(seconds) / 60.0
            else:
                remaining_in_quarter = 0
            
            # Each quarter is 15 minutes
            completed_quarters = max(0, period - 1)
            minutes_in_current_quarter = 15 - remaining_in_quarter
            
            total_minutes = (completed_quarters * 15) + minutes_in_current_quarter
            
            # Cap at 60 minutes (regulation)
            return min(total_minutes, 60)
            
        except Exception as e:
            return 30  # Default to halfway through game
    
    def _calculate_live_projection(self, pre_game_projection, current_points, minutes_played):
        """Calculate live projection based on scoring rate"""
        try:
            if minutes_played >= 60:
                # Game is finished
                return current_points
            
            if minutes_played <= 5:
                # Game just started, use pre-game projection
                return pre_game_projection
            
            # Calculate current scoring rate (points per minute)
            scoring_rate = current_points / minutes_played
            
            # Project for full 60 minutes
            projected_final = scoring_rate * 60
            
            # Use the higher of projection-based or rate-based
            # This prevents projections from dropping too much if a player has a slow start
            return max(projected_final, pre_game_projection * 0.5)
            
        except Exception as e:
            return pre_game_projection
    
    # =============================================================================
    # LIVE SCORING & TEAM DATA
    # =============================================================================
    
    def _get_live_scores(self):
        """Fetch current live scores and player info"""
        if not self.league:
            return []
        
        try:
            # Get live game clocks for projections
            self.game_clocks = self._get_nfl_game_clocks()
            
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
                    
                    # Analyze player statuses and calculate live projections
                    currently_playing = []
                    yet_to_play = []
                    finished_playing = []
                    total_starters = 0
                    projected_total = 0.0
                    
                    for player in lineup:
                        # Skip bench players
                        if player.slot_position == "BE":
                            continue
                            
                        total_starters += 1
                        player_name = getattr(player, 'name', 'Unknown')
                        player_points = getattr(player, 'points', 0)
                        pre_game_projection = getattr(player, 'projected_points', 0)
                        pro_team = getattr(player, 'proTeam', '')
                        
                        # Get game clock data for this player's team
                        clock_data = self.game_clocks.get(pro_team, {})
                        minutes_played = clock_data.get('minutes_played', 30)  # Default to halfway
                        
                        # Calculate live projection
                        live_projection = self._calculate_live_projection(
                            pre_game_projection, player_points, minutes_played
                        )
                        
                        # Enhanced player status detection using game_played
                        game_played = getattr(player, 'game_played', None)
                        
                        if game_played == 0:
                            # Game hasn't started yet
                            yet_to_play.append(f"{player_name} (proj: {pre_game_projection:.1f})")
                            projected_total += pre_game_projection
                        elif game_played == 100:
                            # Game is finished
                            finished_playing.append(f"{player_name} ({player_points:.1f})")
                            projected_total += player_points
                        elif game_played == 1:
                            # Game is in progress
                            currently_playing.append(f"{player_name} ({player_points:.1f})")
                            projected_total += live_projection
                        elif game_played == 2:
                            # Alternative finished status
                            finished_playing.append(f"{player_name} ({player_points:.1f})")
                            projected_total += player_points
                        else:
                            # Fallback for unclear status - assume not played yet
                            yet_to_play.append(f"{player_name} (proj: {pre_game_projection:.1f})")
                            projected_total += pre_game_projection
                    
                    
                    teams_data.append({
                        'team_name': team_name,
                        'live_score': float(score) if score else 0.0,
                        'projected_score': projected_total,
                        'currently_playing': currently_playing,
                        'yet_to_play': yet_to_play,
                        'finished_playing': finished_playing,
                        'players_playing_count': len(currently_playing),
                        'players_remaining_count': len(yet_to_play),
                        'players_finished_count': len(finished_playing),
                        'total_starters': total_starters
                    })
            
            # Sort by live score (highest first) for current rankings
            teams_data.sort(key=lambda x: x['live_score'], reverse=True)
            
            # Add current ranking and top 6 status
            for i, team in enumerate(teams_data):
                team['rank'] = i + 1
                team['is_current_top6'] = i < 6  # Currently in top 6
            
            # Sort by projected score to determine projected top 6
            teams_sorted_by_projection = sorted(teams_data, key=lambda x: x['projected_score'], reverse=True)
            
            # Add projected top 6 status
            for i, team in enumerate(teams_sorted_by_projection):
                team['projected_rank'] = i + 1
                team['is_projected_top6'] = i < 6  # Projected to be in top 6
            
            # Sort back by live score for display
            teams_data.sort(key=lambda x: x['live_score'], reverse=True)
            
            return teams_data
            
        except Exception as e:
            return []
    
    # =============================================================================
    # BACKGROUND UPDATES & SCHEDULING
    # =============================================================================
    
    def _update_scores(self):
        """Background function to update scores with smart timing and error handling"""
        consecutive_failures = 0
        
        while True:
            try:
                self.live_scores = self._get_live_scores()
                self.last_update = datetime.now()
                consecutive_failures = 0  # Reset on success
                self.api_error = None  # Clear any previous errors
                
            except Exception as e:
                consecutive_failures += 1
                error_msg = str(e)
                
                # Set user-visible error message
                if "429" in error_msg or "rate" in error_msg.lower():
                    self.api_error = "⚠️ API rate limited - updates temporarily slower"
                elif "timeout" in error_msg.lower():
                    self.api_error = "⚠️ API timeout - retrying..."
                elif consecutive_failures > 3:
                    self.api_error = f"⚠️ Connection issues - trying again... ({consecutive_failures} failures)"
                else:
                    self.api_error = None
            
            # Smart timing: check if there are actually games today (cached)
            now = datetime.now()
            has_games_today = self._check_if_games_today_cached()
            is_prime_time = 12 <= now.hour <= 23  # 12 PM to 11 PM
            
            # Adaptive sleep based on failures and game activity
            if consecutive_failures > 0:
                # Exponential backoff on failures
                sleep_time = min(600, 60 * (2 ** min(consecutive_failures, 4)))
            elif has_games_today and is_prime_time:
                sleep_time = 120  # 2 minutes during active game days
            elif has_games_today:
                sleep_time = 300  # 5 minutes on game days but off hours
            else:
                sleep_time = 600  # 10 minutes when no games
                
            time.sleep(sleep_time)
    
    def _check_if_games_today_cached(self):
        """Check if there are games today, but cache the result for the entire day"""
        now = datetime.now()
        today = now.date()
        
        # Only check once per day (or on first run)
        if self.games_check_date != today:
            self.games_today_cache = self._check_if_games_today_or_tonight()
            self.games_check_date = today
            
        return self.games_today_cache
    
    def _check_if_games_today_or_tonight(self):
        """Check if there are NFL games today OR late night games from yesterday"""
        try:
            response = requests.get('https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard')
            if response.status_code == 200:
                data = response.json()
                games = data.get('events', [])
                
                now = datetime.now()
                today = now.date()
                
                for game in games:
                    # Check if game is today
                    game_date_str = game.get('date', '')
                    if game_date_str:
                        try:
                            game_datetime = datetime.fromisoformat(game_date_str.replace('Z', '+00:00'))
                            game_date = game_datetime.date()
                            
                            # Game is today
                            if game_date == today:
                                return True
                            
                            # OR: Game was yesterday but might still be going 
                            # (like Monday Night Football ending after midnight)
                            yesterday = today - timedelta(days=1)
                            if game_date == yesterday:
                                # Check if game status suggests it might still be active
                                status = game.get('status', {})
                                game_status = status.get('type', {}).get('name', '').lower()
                                game_state = status.get('type', {}).get('state', '').lower()
                                
                                
                                # If game is in progress or recently finished, consider it "active"
                                # Using both 'name' and 'state' fields for better detection
                                active_statuses = ['in', 'halftime', 'end of period', 'delayed', 'in progress']
                                active_states = ['in', 'live']
                                
                                if game_status in active_statuses or game_state in active_states:
                                    return True
                                    
                        except:
                            pass
                            
                return False
        except:
            # If we can't check, assume there might be games (safer)
            return True
    
    def _start_score_updates(self):
        """Start the background score update thread"""
        thread = threading.Thread(target=self._update_scores, daemon=True)
        thread.start()
    
    # =============================================================================
    # FLASK WEB ROUTES & UI
    # =============================================================================
    
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
        
        return render_template_string(
            template,
            scores=self.live_scores,
            last_update=self.last_update,
            week=self.current_week,
            api_error=self.api_error
        )
    
    # =============================================================================
    # SERVER STARTUP
    # =============================================================================
    
    def run(self, host="0.0.0.0", port=None, debug=False):
        """Start the web server"""
        if port is None:
            port = int(os.getenv('PORT', 5000))
        
        self.app.run(host=host, port=port, debug=debug)

if __name__ == "__main__":
    tracker = FantasyTracker()
    tracker.run(debug=True)
