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

# How often the moves page re-reads this season's pickups, trades, and lineups
MOVES_REFRESH_SECONDS = 3600

# NFL Season configuration
PLAYOFF_CUTOFF = 6  # Top 6 teams make playoffs

# ESPN lineup slots that are not starters (bench / injured reserve)
NON_STARTER_SLOTS = frozenset({'BE', 'IR', 'IR+', 'FA'})
