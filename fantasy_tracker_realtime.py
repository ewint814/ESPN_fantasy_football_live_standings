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
from flask import Flask, render_template_string, jsonify, Response, stream_with_context
import threading
import time
import json
from espn_api.football import League
from dotenv import load_dotenv

# Import local modules
from config import Config
from nfl_utils import NFLSeasonHelper

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
        """Connect to ESPN Fantasy Football API."""
        try:
            is_valid, error_msg = self.config.validate()
            if not is_valid:
                logger.error(f"❌ {error_msg}")
                return False
            
            logger.info(f"🔌 Connecting to ESPN league {self.config.espn_league_id}...")
            
            self.league = League(
                league_id=int(self.config.espn_league_id),
                year=self.nfl_year,
                espn_s2=self.config.espn_s2,
                swid=self.config.espn_swid
            )
            
            teams = self.league.teams
            logger.info(f"✅ Connected! Found {len(teams)} teams")
            return True
            
        except Exception as e:
            logger.error(f"❌ ESPN connection failed: {e}")
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
                self.last_update = datetime.now()
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
                elif consecutive_failures > 3:
                    self.api_error = f"⚠️ Connection issues ({consecutive_failures} failures)"
            
            # AGGRESSIVE updates during games for real-time feel
            now = datetime.now()
            has_games = self._check_if_games_today_cached()
            is_game_time = 12 <= now.hour <= 23
            
            if consecutive_failures > 0:
                sleep_time = min(60, 10 * (2 ** min(consecutive_failures, 3)))
            elif has_games and is_game_time:
                sleep_time = 10  # 10 seconds during active games! ⚡
            elif has_games:
                sleep_time = 30  # 30 seconds off-hours
            else:
                sleep_time = 120  # 2 minutes when no games
            
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
        template = """
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>🏈 Fantasy Football LIVE Tracker</title>
            <style>
                * { margin: 0; padding: 0; box-sizing: border-box; }
                
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
                    position: sticky;
                    top: 0;
                    z-index: 100;
                }
                
                .header h1 {
                    font-size: 2em;
                    font-weight: 600;
                    color: #333;
                    margin-bottom: 8px;
                }
                
                .live-indicator {
                    display: inline-flex;
                    align-items: center;
                    gap: 8px;
                    background: #28a745;
                    color: white;
                    padding: 4px 12px;
                    border-radius: 20px;
                    font-size: 0.85em;
                    font-weight: 600;
                    margin-bottom: 8px;
                }
                
                .live-dot {
                    width: 8px;
                    height: 8px;
                    background: white;
                    border-radius: 50%;
                    animation: pulse 2s ease-in-out infinite;
                }
                
                @keyframes pulse {
                    0%, 100% { opacity: 1; transform: scale(1); }
                    50% { opacity: 0.5; transform: scale(0.8); }
                }
                
                .week-info {
                    font-size: 1em;
                    color: #666;
                    margin-bottom: 8px;
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
                    transition: background 0.3s ease;
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
                
                .current-badge { background: #28a745; }
                .projected-badge { background: #007bff; }
                .top-scorer-badge { background: #ffd700; color: #333; }
                .parlay-badge { background: #dc3545; }
                
                .movement-scores {
                    display: flex;
                    align-items: center;
                    gap: 8px;
                    font-weight: 600;
                }
                
                .current-score { color: #dc3545; }
                .arrow { color: #6c757d; }
                .projected-score { color: #007bff; }
                
                .movement-cell {
                    text-align: center;
                    font-weight: 700;
                    font-size: 1.1em;
                }
                
                .movement-up { color: #28a745; }
                .movement-down { color: #dc3545; }
                .movement-same { color: #6c757d; }
                
                .loading {
                    text-align: center;
                    color: #666;
                    font-size: 1.2em;
                    padding: 50px;
                }
                
                @media (max-width: 768px) {
                    .header h1 { font-size: 1.5em; }
                    .container { padding: 16px; }
                    .toggle-container { flex-direction: column; }
                    .standings th, .standings td { padding: 8px; font-size: 0.9em; }
                }
            </style>
            <script>
                let currentView = 'current';
                
                function showCurrent() {
                    currentView = 'current';
                    updateView();
                }
                
                function showProjected() {
                    currentView = 'projected';
                    updateView();
                }
                
                function showMovement() {
                    currentView = 'movement';
                    updateView();
                }
                
                function updateView() {
                    document.getElementById('currentStandings').style.display = currentView === 'current' ? 'block' : 'none';
                    document.getElementById('projectedStandings').style.display = currentView === 'projected' ? 'block' : 'none';
                    document.getElementById('movementStandings').style.display = currentView === 'movement' ? 'block' : 'none';
                    
                    document.getElementById('currentBtn').classList.toggle('active', currentView === 'current');
                    document.getElementById('projectedBtn').classList.toggle('active', currentView === 'projected');
                    document.getElementById('movementBtn').classList.toggle('active', currentView === 'movement');
                }
                
                // Real-time updates using Server-Sent Events
                function connectSSE() {
                    console.log('⚡ Connecting to real-time stream...');
                    const eventSource = new EventSource('/stream');
                    
                    eventSource.onmessage = function(event) {
                        const data = JSON.parse(event.data);
                        console.log('📊 Received real-time update', data);
                        updateDashboard(data);
                    };
                    
                    eventSource.onerror = function(error) {
                        console.error('❌ SSE connection error:', error);
                        eventSource.close();
                        // Reconnect after 5 seconds
                        setTimeout(connectSSE, 5000);
                    };
                }
                
                function updateDashboard(data) {
                    // Update last update time
                    if (data.last_update) {
                        const updateTime = new Date(data.last_update);
                        document.querySelector('.last-update').textContent = 
                            'Last updated: ' + updateTime.toLocaleTimeString();
                    }
                    
                    // Update error message
                    const errorDiv = document.querySelector('.api-error');
                    if (data.api_error) {
                        errorDiv.textContent = data.api_error;
                        errorDiv.style.display = 'inline-block';
                    } else {
                        errorDiv.style.display = 'none';
                    }
                    
                    // Rebuild tables with new data
                    if (data.scores && data.scores.length > 0) {
                        rebuildTables(data.scores);
                    }
                }
                
                function rebuildTables(scores) {
                    // This would rebuild the tables - for now just reload
                    // In production, you'd update DOM elements directly for smooth transitions
                    location.reload();
                }
                
                // Connect to real-time stream on page load
                window.addEventListener('DOMContentLoaded', function() {
                    connectSSE();
                });
            </script>
        </head>
        <body>
            <div class="header">
                <h1>🏈 Fantasy Football LIVE Tracker</h1>
                <div class="live-indicator">
                    <div class="live-dot"></div>
                    <span>REAL-TIME UPDATES</span>
                </div>
                <div class="week-info">{{ nfl_year }} Season • Week {{ week }}</div>
                {% if last_update %}
                <div class="last-update">Last updated: {{ last_update.strftime('%I:%M:%S %p') }}</div>
                {% endif %}
                {% if api_error %}
                <div class="api-error">{{ api_error }}</div>
                {% else %}
                <div class="api-error" style="display:none;"></div>
                {% endif %}
            </div>
            
            <div class="container">
                {% if scores %}
                <div class="toggle-container">
                    <button id="currentBtn" class="toggle-btn active" onclick="showCurrent()">Current Standings</button>
                    <button id="projectedBtn" class="toggle-btn" onclick="showProjected()">Live Projections</button>
                    <button id="movementBtn" class="toggle-btn" onclick="showMovement()">Movement</button>
                </div>
                
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
                                        <span class="status-badge top-scorer-badge">TOP</span>
                                    {% elif team.rank == scores|length %}
                                        <span class="status-badge parlay-badge">LAST</span>
                                    {% elif team.is_current_top6 %}
                                        <span class="status-badge current-badge">TOP 6</span>
                                    {% endif %}
                                </td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>

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
                                        <span class="status-badge top-scorer-badge">TOP</span>
                                    {% elif team.projected_rank == scores|length %}
                                        <span class="status-badge parlay-badge">LAST</span>
                                    {% elif team.is_projected_top6 %}
                                        <span class="status-badge projected-badge">TOP 6</span>
                                    {% endif %}
                                </td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>

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
                                        <span class="status-badge top-scorer-badge">TOP</span>
                                    {% elif team.rank == scores|length %}
                                        <span class="status-badge parlay-badge">LAST</span>
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
