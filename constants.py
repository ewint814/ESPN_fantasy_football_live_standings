"""
Constants for Fantasy Football Tracker
Centralized configuration values and magic numbers
"""

# Update intervals (seconds)
UPDATE_INTERVAL_ACTIVE_GAMES = 10  # During active games (12pm-11pm ET)
UPDATE_INTERVAL_OFF_HOURS = 30     # Off-hours on game days
UPDATE_INTERVAL_NO_GAMES = 120     # When no games scheduled

# Time window for "game time" detection (hours, 24-hour format)
GAME_TIME_START_HOUR = 12  # 12pm ET
GAME_TIME_END_HOUR = 23    # 11pm ET

# Retry configuration
MAX_CONSECUTIVE_FAILURES = 3
RETRY_BASE_DELAY = 10  # seconds
RETRY_MAX_DELAY = 60   # seconds

# SSE (Server-Sent Events) configuration
SSE_RECONNECT_DELAY = 5000  # milliseconds
SSE_HEARTBEAT_INTERVAL = 30  # seconds

# Timeout configuration
FRONTEND_LOADING_TIMEOUT = 15  # seconds before showing timeout warning
API_REQUEST_TIMEOUT = 10       # seconds for ESPN API requests

# NFL Season configuration
PLAYOFF_CUTOFF = 6  # Top 6 teams make playoffs
TOTAL_WEEKS = 18    # Regular season weeks

# Cache durations
GAMES_CHECK_CACHE_DURATION = 3600  # 1 hour in seconds

# Logging
LOG_LEVEL = "INFO"
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
