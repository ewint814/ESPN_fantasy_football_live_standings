"""
Fantasy Football Live Tracker
=============================
A live scoring tracker for ESPN Fantasy Football that shows:
- Current live scores ranked by position
- Top 6 teams highlighted (for extra win scoring)
- Currently playing players
- Remaining players to play
- Real-time updates with smart polling

Modernized for 2026+ with type hints, better error handling, and dynamic year detection.
"""

import os
import logging
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from flask import Flask, render_template_string, jsonify, Response
import threading
import time
from espn_api.football import League
from dotenv import load_dotenv

# Import local modules
from config import Config
from nfl_utils import NFLSeasonHelper

# Load environment variables
load_dotenv()

# Configure logging with better formatting
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
    ]
)
logger = logging.getLogger(__name__)


class FantasyTracker:
    """Main Fantasy Football tracking application."""
    
    # =============================================================================
    # INITIALIZATION & SETUP
    # =============================================================================
    
    def __init__(self, config: Optional[Config] = None) -> None:
        """
        Initialize the Fantasy Tracker application.
        
        Args:
            config: Application configuration (loads from env if not provided)
        """
        self.config = config or Config.from_env()
        self.app: Flask = Flask(__name__)
        self.league: Optional[League] = None
        self.live_scores: List[Dict[str, Any]] = []
        self.last_update: Optional[datetime] = None
        self.nfl_year: int = NFLSeasonHelper.get_current_nfl_year()
        self.current_week: int = self._get_current_week()
        self.game_clocks: Dict[str, Dict[str, Any]] = {}
        self.api_error: Optional[str] = None
        self.games_today_cache: Optional[bool] = None
        self.games_check_date: Optional[datetime] = None
        
        logger.info(f"🏈 Initializing Fantasy Tracker for {self.nfl_year} NFL season")
        logger.info(f"📅 Current week: {self.current_week}")
        
        # Validate configuration
        is_valid, error_msg = self.config.validate()
        if not is_valid:
            logger.error(f"❌ Configuration error: {error_msg}")
            logger.error("💡 Please check your .env file or environment variables")
        
        # Initialize ESPN connection
        if not self._connect_to_espn():
            logger.error("❌ Failed to connect to ESPN API - app will retry in background")
        
        # Set up web routes
        self._setup_routes()
        
        # Start background score updates
        self._start_score_updates()
    
    # =============================================================================
    # ESPN API CONNECTION & DATA FETCHING
    # =============================================================================
    
    def _connect_to_espn(self) -> bool:
        """
        Connect to ESPN Fantasy Football API.
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        try:
            # Validate config first
            is_valid, error_msg = self.config.validate()
            if not is_valid:
                logger.error(f"❌ {error_msg}")
                return False
            
            logger.info(f"🔌 Connecting to ESPN league {self.config.espn_league_id} for {self.nfl_year} season...")
            
            self.league = League(
                league_id=int(self.config.espn_league_id),
                year=self.nfl_year,
                espn_s2=self.config.espn_s2,
                swid=self.config.espn_swid
            )
            
            # Test the connection by fetching teams
            teams = self.league.teams
            logger.info(f"✅ Successfully connected! Found {len(teams)} teams")
            
            return True
            
        except ValueError as e:
            logger.error(f"❌ Invalid configuration: {e}")
            self.league = None
            return False
        except Exception as e:
            logger.error(f"❌ ESPN connection failed: {e}")
            logger.error("💡 Check your ESPN_S2 and ESPN_SWID cookies - they may have expired")
            self.league = None
            return False
    
    def _get_current_week(self) -> int:
        """
        Get current NFL week using multiple fallback methods.
        
        Returns:
            int: Current NFL week number (1-18)
        """
        try:
            # Method 1: ESPN's NFL scoreboard API (most reliable)
            response = requests.get(
                'https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard',
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                if 'week' in data and 'number' in data['week']:
                    week = data['week']['number']
                    logger.info(f"📊 Got current week from ESPN API: Week {week}")
                    return week
            
            # Method 2: League object (if available)
            if self.league and hasattr(self.league, 'current_week'):
                week = self.league.current_week
                logger.info(f"📊 Got current week from league object: Week {week}")
                return week
            
            # Method 3: Calculate based on season start date
            now = datetime.now()
            week = NFLSeasonHelper.calculate_week_from_date(self.nfl_year, now)
            logger.info(f"📊 Calculated current week: Week {week}")
            return week
            
        except requests.Timeout:
            logger.warning("⚠️ ESPN API timeout, using fallback week calculation")
        except requests.RequestException as e:
            logger.warning(f"⚠️ ESPN API request failed: {e}")
        except Exception as e:
            logger.warning(f"⚠️ Error getting current week: {e}")
        
        # Final fallback
        return 1
    
    # =============================================================================
    # GAME CLOCK & PROJECTION CALCULATIONS
    # =============================================================================
    
    def _get_nfl_game_clocks(self) -> Dict[str, Dict[str, Any]]:
        """
        Get live game clock data from ESPN NFL API.
        
        Returns:
            Dict mapping team abbreviations to game clock data
        """
        try:
            response = requests.get(
                "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard",
                timeout=10
            )
            
            if response.status_code != 200:
                logger.warning(f"⚠️ NFL scoreboard API returned {response.status_code}")
                return {}
            
            data = response.json()
            games = data.get('events', [])
            game_clocks: Dict[str, Dict[str, Any]] = {}
            
            for game in games:
                competitors = game.get('competitions', [{}])[0].get('competitors', [])
                if len(competitors) < 2:
                    continue
                
                team1 = competitors[0].get('team', {}).get('abbreviation', '')
                team2 = competitors[1].get('team', {}).get('abbreviation', '')
                
                status = game.get('status', {})
                clock = status.get('displayClock', '0:00')
                period = status.get('period', 1)
                game_status = status.get('type', {}).get('name', 'unknown')
                
                # Calculate minutes played
                minutes_played = self._calculate_minutes_played(clock, period, game_status)
                
                # Store for both teams
                clock_info = {
                    'clock': clock,
                    'period': period,
                    'status': game_status,
                    'minutes_played': minutes_played,
                    'game_progress': min(minutes_played / 60.0, 1.0)
                }
                
                if team1:
                    game_clocks[team1] = clock_info
                if team2:
                    game_clocks[team2] = clock_info
            
            return game_clocks
            
        except requests.Timeout:
            logger.warning("⚠️ NFL game clocks API timeout")
            return {}
        except requests.RequestException as e:
            logger.warning(f"⚠️ Failed to fetch NFL game clocks: {e}")
            return {}
        except Exception as e:
            logger.error(f"❌ Error parsing NFL game clocks: {e}")
            return {}
    
    def _calculate_minutes_played(self, clock: str, period: int, status: str) -> float:
        """
        Calculate how many minutes have been played in the game.
        
        Args:
            clock: Game clock display (e.g., "12:34")
            period: Current quarter/period
            status: Game status string
            
        Returns:
            Minutes played (0-60+)
        """
        try:
            status_lower = status.lower()
            
            # Game is finished
            if any(word in status_lower for word in ['final', 'finished', 'end']):
                return 60.0
            
            # Game hasn't started
            if any(word in status_lower for word in ['scheduled', 'pre', 'upcoming']):
                return 0.0
            
            # Parse clock (format like "12:34" or "0:00")
            remaining_in_quarter = 0.0
            if ':' in clock:
                parts = clock.split(':')
                if len(parts) == 2:
                    minutes = int(parts[0])
                    seconds = int(parts[1])
                    remaining_in_quarter = minutes + seconds / 60.0
            
            # Each quarter is 15 minutes
            completed_quarters = max(0, period - 1)
            minutes_in_current_quarter = 15.0 - remaining_in_quarter
            
            total_minutes = (completed_quarters * 15.0) + minutes_in_current_quarter
            
            # Cap at 60 minutes (regulation)
            return min(total_minutes, 60.0)
            
        except (ValueError, IndexError) as e:
            logger.warning(f"⚠️ Error parsing game clock '{clock}': {e}")
            return 30.0  # Default to halfway through game
        except Exception as e:
            logger.error(f"❌ Error calculating minutes played: {e}")
            return 30.0
    
    def _calculate_live_projection(
        self, 
        pre_game_projection: float, 
        current_points: float, 
        minutes_played: float
    ) -> float:
        """
        Calculate live projection based on current scoring rate.
        
        Args:
            pre_game_projection: Pre-game projected points
            current_points: Points scored so far
            minutes_played: Minutes played in the game
            
        Returns:
            Projected final points
        """
        try:
            if minutes_played >= 60:
                return current_points
            
            if minutes_played <= 5:
                return pre_game_projection
            
            # Calculate current scoring rate (points per minute)
            scoring_rate = current_points / minutes_played
            
            # Project for full 60 minutes
            projected_final = scoring_rate * 60
            
            # Use the higher of projection-based or rate-based
            # Prevents projections from dropping too much on slow starts
            return max(projected_final, pre_game_projection * 0.5)
            
        except ZeroDivisionError:
            return pre_game_projection
        except Exception as e:
            logger.warning(f"⚠️ Error calculating live projection: {e}")
            return pre_game_projection
    
    # =============================================================================
    # LIVE SCORING & TEAM DATA
    # =============================================================================
    
    def _get_live_scores(self) -> List[Dict[str, Any]]:
        """
        Fetch current live scores and player info.
        
        Returns:
            List of team data dictionaries
        """
        if not self.league:
            logger.warning("⚠️ No league connection, attempting to reconnect...")
            if not self._connect_to_espn():
                return []
        
        try:
            # Get live game clocks for projections
            self.game_clocks = self._get_nfl_game_clocks()
            
            logger.info(f"📊 Fetching scores for Week {self.current_week}...")
            box_scores = self.league.box_scores(week=self.current_week)
            teams_data: List[Dict[str, Any]] = []
            
            for matchup in box_scores:
                # Process both home and away teams
                for team, lineup, score in [
                    (matchup.home_team, matchup.home_lineup, matchup.home_score),
                    (matchup.away_team, matchup.away_lineup, matchup.away_score)
                ]:
                    team_name = getattr(team, 'team_name', 'Unknown Team')
                    
                    # Analyze player statuses and calculate live projections
                    currently_playing: List[str] = []
                    yet_to_play: List[str] = []
                    finished_playing: List[str] = []
                    total_starters = 0
                    projected_total = 0.0
                    
                    for player in lineup:
                        # Skip bench players
                        if player.slot_position == "BE":
                            continue
                        
                        total_starters += 1
                        player_name = getattr(player, 'name', 'Unknown')
                        player_points = getattr(player, 'points', 0.0)
                        pre_game_projection = getattr(player, 'projected_points', 0.0)
                        pro_team = getattr(player, 'proTeam', '')
                        
                        # Get game clock data for this player's team
                        clock_data = self.game_clocks.get(pro_team, {})
                        minutes_played = clock_data.get('minutes_played', 30.0)
                        
                        # Calculate live projection
                        live_projection = self._calculate_live_projection(
                            pre_game_projection, player_points, minutes_played
                        )
                        
                        # Player status detection using game_played attribute
                        game_played = getattr(player, 'game_played', None)
                        
                        if game_played == 0:
                            # Game hasn't started yet
                            yet_to_play.append(f"{player_name} (proj: {pre_game_projection:.1f})")
                            projected_total += pre_game_projection
                        elif game_played in (100, 2):
                            # Game is finished
                            finished_playing.append(f"{player_name} ({player_points:.1f})")
                            projected_total += player_points
                        elif game_played == 1:
                            # Game is in progress
                            currently_playing.append(f"{player_name} ({player_points:.1f})")
                            projected_total += live_projection
                        else:
                            # Fallback for unclear status
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
            
            # Sort by live score (highest first)
            teams_data.sort(key=lambda x: x['live_score'], reverse=True)
            
            # Add current ranking and top 6 status
            for i, team in enumerate(teams_data):
                team['rank'] = i + 1
                team['is_current_top6'] = i < 6
            
            # Sort by projected score for projected rankings
            teams_sorted_by_projection = sorted(
                teams_data, 
                key=lambda x: x['projected_score'], 
                reverse=True
            )
            
            # Add projected rankings
            for i, team in enumerate(teams_sorted_by_projection):
                team['projected_rank'] = i + 1
                team['is_projected_top6'] = i < 6
            
            # Sort back by live score for display
            teams_data.sort(key=lambda x: x['live_score'], reverse=True)
            
            logger.info(f"✅ Successfully fetched scores for {len(teams_data)} teams")
            return teams_data
            
        except Exception as e:
            logger.error(f"❌ Error fetching live scores: {e}", exc_info=True)
            return []
    
    # =============================================================================
    # BACKGROUND UPDATES & SCHEDULING
    # =============================================================================
    
    def _update_scores(self) -> None:
        """Background function to update scores with smart timing and error handling."""
        consecutive_failures = 0
        
        while True:
            try:
                self.live_scores = self._get_live_scores()
                self.last_update = datetime.now()
                consecutive_failures = 0
                self.api_error = None
                
            except Exception as e:
                consecutive_failures += 1
                error_msg = str(e)
                
                logger.error(f"❌ Score update failed (attempt {consecutive_failures}): {e}")
                
                # Set user-visible error message
                if "429" in error_msg or "rate" in error_msg.lower():
                    self.api_error = "⚠️ API rate limited - updates temporarily slower"
                elif "timeout" in error_msg.lower():
                    self.api_error = "⚠️ API timeout - retrying..."
                elif consecutive_failures > 3:
                    self.api_error = f"⚠️ Connection issues - trying again... ({consecutive_failures} failures)"
                else:
                    self.api_error = None
            
            # Smart timing based on game activity
            sleep_time = self._calculate_sleep_time(consecutive_failures)
            logger.debug(f"💤 Sleeping for {sleep_time}s until next update")
            time.sleep(sleep_time)
    
    def _calculate_sleep_time(self, consecutive_failures: int) -> int:
        """
        Calculate optimal sleep time between updates.
        
        Args:
            consecutive_failures: Number of consecutive API failures
            
        Returns:
            Sleep time in seconds
        """
        now = datetime.now()
        has_games_today = self._check_if_games_today_cached()
        is_prime_time = 12 <= now.hour <= 23  # 12 PM to 11 PM
        
        # Exponential backoff on failures
        if consecutive_failures > 0:
            return min(600, 60 * (2 ** min(consecutive_failures, 4)))
        
        # Active game periods
        if has_games_today and is_prime_time:
            return self.config.update_interval_active
        elif has_games_today:
            return self.config.update_interval_off_hours
        else:
            return self.config.update_interval_no_games
    
    def _check_if_games_today_cached(self) -> bool:
        """
        Check if there are games today (cached for the entire day).
        
        Returns:
            True if there are games today
        """
        now = datetime.now()
        today = now.date()
        
        # Only check once per day
        if self.games_check_date != today:
            self.games_today_cache = self._check_if_games_today_or_tonight()
            self.games_check_date = today
            logger.info(f"📅 Games today: {self.games_today_cache}")
        
        return self.games_today_cache or False
    
    def _check_if_games_today_or_tonight(self) -> bool:
        """
        Check if there are NFL games today or late-night games from yesterday.
        
        Returns:
            True if there are active games
        """
        try:
            response = requests.get(
                'https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard',
                timeout=10
            )
            
            if response.status_code != 200:
                return True  # Assume there might be games
            
            data = response.json()
            games = data.get('events', [])
            now = datetime.now()
            today = now.date()
            yesterday = today - timedelta(days=1)
            
            for game in games:
                game_date_str = game.get('date', '')
                if not game_date_str:
                    continue
                
                try:
                    game_datetime = datetime.fromisoformat(game_date_str.replace('Z', '+00:00'))
                    game_date = game_datetime.date()
                    
                    # Game is today
                    if game_date == today:
                        return True
                    
                    # Game was yesterday but might still be active
                    if game_date == yesterday:
                        status = game.get('status', {})
                        game_status = status.get('type', {}).get('name', '').lower()
                        game_state = status.get('type', {}).get('state', '').lower()
                        
                        active_statuses = ['in', 'halftime', 'end of period', 'delayed']
                        active_states = ['in', 'live']
                        
                        if game_status in active_statuses or game_state in active_states:
                            return True
                
                except (ValueError, KeyError):
                    continue
            
            return False
            
        except (requests.Timeout, requests.RequestException):
            return True  # Safer to assume there might be games
        except Exception as e:
            logger.warning(f"⚠️ Error checking for games today: {e}")
            return True
    
    def _start_score_updates(self) -> None:
        """Start the background score update thread."""
        thread = threading.Thread(target=self._update_scores, daemon=True)
        thread.start()
        logger.info("🔄 Started background score update thread")
    
    # =============================================================================
    # FLASK WEB ROUTES & UI
    # =============================================================================
    
    def _setup_routes(self) -> None:
        """Set up Flask web routes."""
        
        @self.app.route('/')
        def dashboard() -> str:
            return self._render_dashboard()
        
        @self.app.route('/api/scores')
        def api_scores() -> Response:
            return jsonify({
                'scores': self.live_scores,
                'last_update': self.last_update.isoformat() if self.last_update else None,
                'week': self.current_week,
                'nfl_year': self.nfl_year
            })
        
        @self.app.route('/health')
        def health() -> Response:
            """Health check endpoint for monitoring."""
            is_healthy = self.league is not None and len(self.live_scores) > 0
            status_code = 200 if is_healthy else 503
            
            return jsonify({
                'status': 'healthy' if is_healthy else 'unhealthy',
                'connected': self.league is not None,
                'teams_count': len(self.live_scores),
                'last_update': self.last_update.isoformat() if self.last_update else None,
                'nfl_year': self.nfl_year,
                'current_week': self.current_week
            }), status_code
    
    def _render_dashboard(self) -> str:
        """Render the main dashboard HTML."""
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
                    display: inline-block;
                }
                
                .container {
                    max-width: 1000px;
                    margin: 0 auto;
                    padding: 24px 20px;
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
                
                .movement-scores {
                    display: flex;
                    align-items: center;
                    gap: 8px;
                    font-weight: 600;
                }
                
                .current-score {
                    color: #dc3545;
                }
                
                .arrow {
                    color: #6c757d;
                }
                
                .projected-score {
                    color: #007bff;
                }
                
                .movement-cell {
                    text-align: center;
                    font-weight: 700;
                    font-size: 1.1em;
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
                
                .loading {
                    text-align: center;
                    color: #666;
                    font-size: 1.2em;
                    padding: 50px;
                }
                
                @media (max-width: 768px) {
                    .header h1 {
                        font-size: 1.5em;
                    }
                    
                    .container {
                        padding: 16px;
                    }
                    
                    .toggle-container {
                        flex-direction: column;
                    }
                    
                    .standings th,
                    .standings td {
                        padding: 8px;
                        font-size: 0.9em;
                    }
                }
            </style>
            <script>
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
                
                // Auto-refresh every 2 minutes
                setTimeout(() => {
                    location.reload();
                }, 120000);
            </script>
        </head>
        <body>
            <div class="header">
                <h1>🏈 Fantasy Football Live Tracker</h1>
                <div class="week-info">{{ nfl_year }} Season • Week {{ week }} • Live Scoring</div>
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
                                <td class="current-score">{{ "%.1f"|format(team.live_score) }}</td>
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
            nfl_year=self.nfl_year,
            api_error=self.api_error
        )
    
    # =============================================================================
    # SERVER STARTUP
    # =============================================================================
    
    def run(self, host: Optional[str] = None, port: Optional[int] = None, debug: Optional[bool] = None) -> None:
        """
        Start the web server.
        
        Args:
            host: Host to bind to (defaults to config)
            port: Port to bind to (defaults to config)
            debug: Enable debug mode (defaults to config)
        """
        host = host or self.config.host
        port = port or self.config.port
        debug = debug if debug is not None else self.config.debug
        
        logger.info(f"🚀 Starting Fantasy Tracker on http://{host}:{port}")
        self.app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    try:
        tracker = FantasyTracker()
        tracker.run(debug=False)
    except KeyboardInterrupt:
        logger.info("\n👋 Shutting down Fantasy Tracker...")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)
