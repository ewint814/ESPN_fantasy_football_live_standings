"""
Sleeper API Integration for Fantasy Football Projections
========================================================
This module integrates with Sleeper's API to get better projection data
and potentially live updates during games.
"""

import requests
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

class SleeperAPI:
    """
    Sleeper API client for fantasy football data
    """
    BASE_URL = "https://api.sleeper.app/v1"
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Fantasy-Football-Tracker/1.0'
        })
    
    def get_nfl_state(self) -> Optional[Dict]:
        """Get current NFL state (week, season, etc.)"""
        try:
            response = self.session.get(f"{self.BASE_URL}/state/nfl")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching NFL state: {e}")
            return None
    
    def get_players(self) -> Optional[Dict]:
        """Get all NFL players data"""
        try:
            response = self.session.get(f"{self.BASE_URL}/players/nfl")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching players: {e}")
            return None
    
    def get_weekly_projections(self, week: int, season: int = 2025) -> Optional[Dict]:
        """
        Get weekly projections for all players
        Note: Sleeper may not have live projections, but has stats and trends
        """
        try:
            # Sleeper doesn't have a direct projections endpoint like some APIs
            # but we can get stats and trends data
            response = self.session.get(f"{self.BASE_URL}/stats/nfl/{season}/{week}")
            if response.status_code == 200:
                return response.json()
            else:
                logger.warning(f"No projection data available for week {week}")
                return None
        except Exception as e:
            logger.error(f"Error fetching projections: {e}")
            return None
    
    def get_player_stats(self, week: int, season: int = 2025) -> Optional[Dict]:
        """Get actual player stats for a given week"""
        try:
            response = self.session.get(f"{self.BASE_URL}/stats/nfl/{season}/{week}")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching player stats: {e}")
            return None
    
    def calculate_ppr_points(self, stats: Dict) -> float:
        """
        Calculate PPR fantasy points from player stats
        Full PPR scoring: 1 point per reception
        """
        points = 0.0
        
        # Passing stats
        points += stats.get('pass_yd', 0) / 25  # 1 point per 25 passing yards
        points += stats.get('pass_td', 0) * 4   # 4 points per passing TD
        points -= stats.get('pass_int', 0) * 2  # -2 points per interception
        
        # Rushing stats
        points += stats.get('rush_yd', 0) / 10  # 1 point per 10 rushing yards
        points += stats.get('rush_td', 0) * 6   # 6 points per rushing TD
        
        # Receiving stats (PPR)
        points += stats.get('rec_yd', 0) / 10   # 1 point per 10 receiving yards
        points += stats.get('rec_td', 0) * 6    # 6 points per receiving TD
        points += stats.get('rec', 0) * 1       # 1 point per reception (PPR)
        
        # Fumbles
        points -= stats.get('fum_lost', 0) * 2  # -2 points per fumble lost
        
        return round(points, 1)

class ProjectionEnhancer:
    """
    Enhances ESPN data with Sleeper projections/trends
    """
    
    def __init__(self):
        self.sleeper = SleeperAPI()
        self.players_cache = None
        self.nfl_state = None
    
    def initialize(self):
        """Initialize with current NFL state and player data"""
        self.nfl_state = self.sleeper.get_nfl_state()
        self.players_cache = self.sleeper.get_players()
        
        if self.nfl_state:
            logger.info(f"NFL State: Week {self.nfl_state.get('week')}, Season {self.nfl_state.get('season')}")
        
        return self.nfl_state is not None
    
    def get_current_week(self) -> int:
        """Get current NFL week from Sleeper"""
        if self.nfl_state:
            return self.nfl_state.get('week', 1)
        return 1
    
    def find_sleeper_player_id(self, espn_player_name: str) -> Optional[str]:
        """
        Try to match ESPN player name to Sleeper player ID
        This is a simple name matching - could be enhanced with fuzzy matching
        """
        if not self.players_cache:
            return None
        
        # Simple name matching (could be improved)
        for player_id, player_data in self.players_cache.items():
            if player_data.get('full_name', '').lower() == espn_player_name.lower():
                return player_id
            
            # Try first name + last name
            first_name = player_data.get('first_name', '')
            last_name = player_data.get('last_name', '')
            full_name = f"{first_name} {last_name}"
            if full_name.lower() == espn_player_name.lower():
                return player_id
        
        return None
    
    def get_enhanced_projection(self, espn_player_name: str, espn_projection: float) -> float:
        """
        Get enhanced projection using Sleeper data
        For now, returns ESPN projection but framework is here for enhancement
        """
        # This could be enhanced with:
        # 1. Sleeper trend data
        # 2. Recent performance analysis
        # 3. Injury status from Sleeper
        # 4. Weather/matchup data
        
        sleeper_id = self.find_sleeper_player_id(espn_player_name)
        if sleeper_id and self.players_cache:
            player_data = self.players_cache.get(sleeper_id, {})
            
            # Could factor in injury status
            injury_status = player_data.get('injury_status')
            if injury_status in ['Out', 'Doubtful']:
                return 0.0  # Player likely won't play
            elif injury_status == 'Questionable':
                return espn_projection * 0.8  # Reduce projection by 20%
        
        return espn_projection

# Example usage and testing
if __name__ == "__main__":
    # Test the Sleeper API
    sleeper = SleeperAPI()
    
    print("Testing Sleeper API...")
    
    # Test NFL state
    nfl_state = sleeper.get_nfl_state()
    if nfl_state:
        print(f"Current NFL State: Week {nfl_state.get('week')}, Season {nfl_state.get('season')}")
    
    # Test projections (may not be available)
    projections = sleeper.get_weekly_projections(1, 2025)
    if projections:
        print(f"Found projections for {len(projections)} players")
    else:
        print("No projections available from Sleeper")
    
    print("Sleeper API test complete.")



