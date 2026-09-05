"""
Real-time Fantasy Football Live Tracker with Server-Sent Events
================================================================
Provides INSTANT updates as scores change - no more waiting!
Uses SSE (Server-Sent Events) for push-based real-time updates.
"""

import os
import logging
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Generator
from flask import Flask, render_template, jsonify, Response, stream_with_context
import threading
import time
import json
from espn_api.football import League
from dotenv import load_dotenv
import pytz

# Import local modules
from config import Config
from nfl_utils import NFLSeasonHelper
from constants import (
    UPDATE_INTERVAL_ACTIVE_GAMES,
    UPDATE_INTERVAL_OFF_HOURS,
    UPDATE_INTERVAL_NO_GAMES,
    GAME_TIME_START_HOUR,
    GAME_TIME_END_HOUR,
    MAX_CONSECUTIVE_FAILURES,
    RETRY_BASE_DELAY,
    RETRY_MAX_DELAY,
)

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)


class FantasyTracker:
    """Main Fantasy Football tracking application with real-time updates."""
    
    def __init__(self, config: Optional[Config] = None) -> None:
        """Initialize the Fantasy Tracker with real-time capabilities."""
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
        
        # Timezone for display
        self.eastern = pytz.timezone('America/New_York')
        
        # Real-time update tracking
        self.data_changed: bool = False
        self.clients: List = []  # Connected SSE clients
        
        logger.info(f"🏈 Initializing Real-Time Fantasy Tracker for {self.nfl_year} NFL season")
        logger.info(f"📅 Current week: {self.current_week}")
        logger.info(f"⚡ Real-time updates: ENABLED")
        
        # Validate configuration
        is_valid, error_msg = self.config.validate()
        if not is_valid:
            logger.error(f"❌ Configuration error: {error_msg}")
        
        # Initialize ESPN connection
        if not self._connect_to_espn():
            logger.error("❌ Failed to connect to ESPN API - will retry in background")
        
        # Set up web routes
        self._setup_routes()
        
        # Start aggressive background updates for real-time experience
        self._start_score_updates()
    
    def _connect_to_espn(self) -> bool:
        """Connect to ESPN Fantasy Football API with timeout."""
        try:
            is_valid, error_msg = self.config.validate()
            if not is_valid:
                logger.error(f"❌ {error_msg}")
                self.api_error = f"❌ Configuration Error: {error_msg}\n\n💡 Fix: Set ESPN_LEAGUE_ID, ESPN_S2, and ESPN_SWID in Render Dashboard → Environment"
                return False
            
            logger.info(f"🔌 Connecting to ESPN league {self.config.espn_league_id}...")
            
            self.league = League(
                league_id=int(self.config.espn_league_id),
                year=self.nfl_year,
                espn_s2=self.config.espn_s2,
                swid=self.config.espn_swid
            )
            
            # Test connection by fetching teams (this is where it can hang)
            teams = self.league.teams
            logger.info(f"✅ Connected! Found {len(teams)} teams")
            return True
            
        except Exception as e:
            error_str = str(e).lower()
            logger.error(f"❌ ESPN connection failed: {e}")
            
            # Provide specific, actionable error messages
            if "401" in error_str or "unauthorized" in error_str or "authentication" in error_str:
                self.api_error = "❌ ESPN Authentication Failed\n\n💡 Fix: Your ESPN cookies (ESPN_S2 and ESPN_SWID) have expired.\n\n1. Go to ESPN.com and log in\n2. Press F12 → Application → Cookies → espn.com\n3. Copy fresh ESPN_S2 and ESPN_SWID values\n4. Update in Render Dashboard → Environment"
            elif "404" in error_str or "not found" in error_str:
                self.api_error = f"❌ League Not Found\n\n💡 Fix: League ID '{self.config.espn_league_id}' doesn't exist or you don't have access.\n\nCheck your ESPN_LEAGUE_ID in Render environment variables."
            elif "timeout" in error_str or "timed out" in error_str:
                self.api_error = "❌ ESPN API Timeout\n\n💡 ESPN's servers are slow or unreachable. Try again in a few minutes."
            else:
                self.api_error = f"❌ ESPN Connection Failed: {str(e)}\n\n💡 Fix: Check your ESPN credentials in Render Dashboard → Environment.\n\nMake sure ESPN_S2 and ESPN_SWID cookies are fresh (they expire every few weeks)."
            
            self.league = None
            return False
    
    def _get_current_week(self) -> int:
        """Get current NFL week."""
        try:
            response = requests.get(
                'https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard',
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                if 'week' in data and 'number' in data['week']:
                    return data['week']['number']
            
            if self.league and hasattr(self.league, 'current_week'):
                return self.league.current_week
            
            return NFLSeasonHelper.calculate_week_from_date(self.nfl_year, datetime.now())
            
        except Exception:
            return 1
    
    def _get_nfl_game_clocks(self) -> Dict[str, Dict[str, Any]]:
        """Get live game clock data."""
        try:
            response = requests.get(
                "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard",
                timeout=10
            )
            
            if response.status_code != 200:
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
                
                minutes_played = self._calculate_minutes_played(clock, period, game_status)
                
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
            
        except Exception:
            return {}
    
    def _calculate_minutes_played(self, clock: str, period: int, status: str) -> float:
        """Calculate minutes played in game."""
        try:
            status_lower = status.lower()
            
            if any(word in status_lower for word in ['final', 'finished', 'end']):
                return 60.0
            
            if any(word in status_lower for word in ['scheduled', 'pre', 'upcoming']):
                return 0.0
            
            remaining_in_quarter = 0.0
            if ':' in clock:
                parts = clock.split(':')
                if len(parts) == 2:
                    minutes = int(parts[0])
                    seconds = int(parts[1])
                    remaining_in_quarter = minutes + seconds / 60.0
            
            completed_quarters = max(0, period - 1)
            minutes_in_current_quarter = 15.0 - remaining_in_quarter
            total_minutes = (completed_quarters * 15.0) + minutes_in_current_quarter
            
            return min(total_minutes, 60.0)
            
        except Exception:
            return 30.0
    
    def _calculate_live_projection(self, pre_game: float, current: float, minutes: float) -> float:
        """Calculate live projection."""
        try:
            if minutes >= 60:
                return current
            if minutes <= 5:
                return pre_game
            
            scoring_rate = current / minutes
            projected_final = scoring_rate * 60
            
            return max(projected_final, pre_game * 0.5)
            
        except Exception:
            return pre_game
    
    def _get_live_scores(self) -> List[Dict[str, Any]]:
        """Fetch current live scores."""
        if not self.league:
            if not self._connect_to_espn():
                return []
        
        try:
            self.game_clocks = self._get_nfl_game_clocks()
            box_scores = self.league.box_scores(week=self.current_week)
            teams_data: List[Dict[str, Any]] = []
            
            for matchup in box_scores:
                for team, lineup, score in [
                    (matchup.home_team, matchup.home_lineup, matchup.home_score),
                    (matchup.away_team, matchup.away_lineup, matchup.away_score)
                ]:
                    team_name = getattr(team, 'team_name', 'Unknown Team')
                    
                    currently_playing: List[str] = []
                    yet_to_play: List[str] = []
                    finished_playing: List[str] = []
                    total_starters = 0
                    projected_total = 0.0
                    
                    for player in lineup:
                        if player.slot_position == "BE":
                            continue
                        
                        total_starters += 1
                        player_name = getattr(player, 'name', 'Unknown')
                        player_points = getattr(player, 'points', 0.0)
                        pre_game_projection = getattr(player, 'projected_points', 0.0)
                        pro_team = getattr(player, 'proTeam', '')
                        
                        clock_data = self.game_clocks.get(pro_team, {})
                        minutes_played = clock_data.get('minutes_played', 30.0)
                        
                        live_projection = self._calculate_live_projection(
                            pre_game_projection, player_points, minutes_played
                        )
                        
                        game_played = getattr(player, 'game_played', None)
                        
                        if game_played == 0:
                            yet_to_play.append(f"{player_name} (proj: {pre_game_projection:.1f})")
                            projected_total += pre_game_projection
                        elif game_played in (100, 2):
                            finished_playing.append(f"{player_name} ({player_points:.1f})")
                            projected_total += player_points
                        elif game_played == 1:
                            currently_playing.append(f"{player_name} ({player_points:.1f})")
                            projected_total += live_projection
                        else:
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
            
            teams_data.sort(key=lambda x: x['live_score'], reverse=True)
            
            for i, team in enumerate(teams_data):
                team['rank'] = i + 1
                team['is_current_top6'] = i < 6
            
            teams_sorted_by_projection = sorted(teams_data, key=lambda x: x['projected_score'], reverse=True)
            
            for i, team in enumerate(teams_sorted_by_projection):
                team['projected_rank'] = i + 1
                team['is_projected_top6'] = i < 6
            
            teams_data.sort(key=lambda x: x['live_score'], reverse=True)
            
            return teams_data
            
        except Exception as e:
            logger.error(f"❌ Error fetching scores: {e}")
            return []
    
    def _update_scores(self) -> None:
        """Background function with aggressive real-time updates."""
        consecutive_failures = 0
        
        while True:
            try:
                old_scores = json.dumps(self.live_scores, sort_keys=True)
                self.live_scores = self._get_live_scores()
                self.last_update = datetime.now(pytz.UTC)  # Store as UTC
                new_scores = json.dumps(self.live_scores, sort_keys=True)
                
                # Check if data actually changed
                if old_scores != new_scores:
                    self.data_changed = True
                    logger.info("📊 Scores updated - pushing to clients")
                
                consecutive_failures = 0
                self.api_error = None
                
            except Exception as e:
                consecutive_failures += 1
                logger.error(f"❌ Update failed (attempt {consecutive_failures}): {e}")
                
                if "429" in str(e) or "rate" in str(e).lower():
                    self.api_error = "⚠️ API rate limited"
                elif consecutive_failures > MAX_CONSECUTIVE_FAILURES:
                    self.api_error = f"⚠️ Connection issues ({consecutive_failures} failures)"
            
            # AGGRESSIVE updates during games for real-time feel
            now = datetime.now()
            has_games = self._check_if_games_today_cached()
            is_game_time = GAME_TIME_START_HOUR <= now.hour <= GAME_TIME_END_HOUR
            
            if consecutive_failures > 0:
                sleep_time = min(RETRY_MAX_DELAY, RETRY_BASE_DELAY * (2 ** min(consecutive_failures, MAX_CONSECUTIVE_FAILURES)))
            elif has_games and is_game_time:
                sleep_time = UPDATE_INTERVAL_ACTIVE_GAMES
            elif has_games:
                sleep_time = UPDATE_INTERVAL_OFF_HOURS
            else:
                sleep_time = UPDATE_INTERVAL_NO_GAMES
            
            time.sleep(sleep_time)
    
    def _check_if_games_today_cached(self) -> bool:
        """Check if there are games today (cached)."""
        now = datetime.now()
        today = now.date()
        
        if self.games_check_date != today:
            self.games_today_cache = self._check_if_games_today()
            self.games_check_date = today
        
        return self.games_today_cache or False
    
    def _check_if_games_today(self) -> bool:
        """Check if there are NFL games today."""
        try:
            response = requests.get(
                'https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard',
                timeout=10
            )
            
            if response.status_code != 200:
                return True
            
            data = response.json()
            games = data.get('events', [])
            today = datetime.now().date()
            
            for game in games:
                game_date_str = game.get('date', '')
                if not game_date_str:
                    continue
                
                try:
                    game_datetime = datetime.fromisoformat(game_date_str.replace('Z', '+00:00'))
                    if game_datetime.date() == today:
                        return True
                except Exception:
                    continue
            
            return False
            
        except Exception:
            return True
    
    def _start_score_updates(self) -> None:
        """Start background update thread."""
        thread = threading.Thread(target=self._update_scores, daemon=True)
        thread.start()
        logger.info("🔄 Started real-time update thread (10s intervals during games)")
    
    def _event_stream(self) -> Generator[str, None, None]:
        """Server-Sent Events stream for real-time updates."""
        logger.info("⚡ New client connected to real-time stream")
        
        # Send initial data immediately
        yield f"data: {json.dumps({'scores': self.live_scores, 'last_update': self.last_update.isoformat() if self.last_update else None})}\n\n"
        
        last_sent = time.time()
        
        while True:
            # Send update if data changed or every 30 seconds (heartbeat)
            if self.data_changed or (time.time() - last_sent > 30):
                data = {
                    'scores': self.live_scores,
                    'last_update': self.last_update.isoformat() if self.last_update else None,
                    'week': self.current_week,
                    'nfl_year': self.nfl_year,
                    'api_error': self.api_error
                }
                yield f"data: {json.dumps(data)}\n\n"
                self.data_changed = False
                last_sent = time.time()
            
            time.sleep(1)  # Check every second for changes
    
    def _setup_routes(self) -> None:
        """Set up Flask routes with SSE support."""
        
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
        
        @self.app.route('/stream')
        def stream() -> Response:
            """Server-Sent Events endpoint for real-time updates."""
            return Response(
                stream_with_context(self._event_stream()),
                mimetype='text/event-stream',
                headers={
                    'Cache-Control': 'no-cache',
                    'X-Accel-Buffering': 'no'
                }
            )
        
        @self.app.route('/health')
        def health() -> Response:
            is_healthy = self.league is not None and len(self.live_scores) > 0
            status_code = 200 if is_healthy else 503
            
            return jsonify({
                'status': 'healthy' if is_healthy else 'unhealthy',
                'connected': self.league is not None,
                'teams_count': len(self.live_scores),
                'last_update': self.last_update.isoformat() if self.last_update else None,
                'nfl_year': self.nfl_year,
                'current_week': self.current_week,
                'real_time': True
            }), status_code
    
    def _render_dashboard(self) -> str:
        """Render dashboard with real-time SSE updates."""
        return render_template(
            'dashboard.html',
            scores=self.live_scores,
            last_update=self.last_update,
            week=self.current_week,
            nfl_year=self.nfl_year,
            api_error=self.api_error,
            eastern=self.eastern
        )
    
    def run(self, host: Optional[str] = None, port: Optional[int] = None, debug: Optional[bool] = None) -> None:
        """Start the web server."""
        host = host or self.config.host
        port = port or self.config.port
        debug = debug if debug is not None else self.config.debug
        
        logger.info(f"🚀 Starting REAL-TIME Fantasy Tracker on http://{host}:{port}")
        logger.info(f"⚡ Updates every 10 seconds during games!")
        self.app.run(host=host, port=port, debug=debug, threaded=True)


if __name__ == "__main__":
    try:
        tracker = FantasyTracker()
        tracker.run(debug=False)
    except KeyboardInterrupt:
        logger.info("\n👋 Shutting down Fantasy Tracker...")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)
