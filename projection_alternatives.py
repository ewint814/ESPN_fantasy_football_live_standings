"""
Alternative Projection Sources for Fantasy Football
==================================================
Since live projections are hard to find for free, let's explore alternatives:

1. FantasyPros API (has projections but may be paid)
2. Yahoo Fantasy API (might have better projections)
3. Create our own "smart projections" using available data
4. Use ESPN projections but enhance them with Sleeper injury/status data
"""

import requests
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

class ProjectionAggregator:
    """
    Aggregates projection data from multiple sources
    """
    
    def __init__(self):
        self.sleeper_base = "https://api.sleeper.app/v1"
    
    def test_fantasypros_api(self):
        """
        Test FantasyPros API (they have good projections but may require subscription)
        """
        try:
            # FantasyPros has a public API but limited endpoints
            # Their main projections are likely behind a paywall
            response = requests.get("https://api.fantasypros.com/public/v2/json/nfl/2024/consensus-rankings")
            print(f"FantasyPros API Status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"FantasyPros data structure: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}")
        except Exception as e:
            print(f"FantasyPros API Error: {e}")
    
    def test_yahoo_api(self):
        """
        Test Yahoo Fantasy API (requires OAuth but might have projections)
        """
        # Yahoo requires OAuth authentication, so this is just a structure example
        print("Yahoo Fantasy API requires OAuth authentication")
        print("Would need user to authenticate through Yahoo to access their projections")
    
    def create_enhanced_espn_projections(self, espn_player_data, sleeper_player_data):
        """
        Enhance ESPN projections with Sleeper data
        This is probably our best bet for now
        """
        enhanced_projections = {}
        
        # Use ESPN base projections but adjust based on:
        # 1. Sleeper injury status
        # 2. Recent trends
        # 3. Weather (if available)
        # 4. Vegas odds (if available)
        
        return enhanced_projections
    
    def get_sleeper_injury_status(self, player_name: str) -> Optional[str]:
        """
        Get injury status from Sleeper for a player
        """
        try:
            response = requests.get(f"{self.sleeper_base}/players/nfl")
            if response.status_code == 200:
                players = response.json()
                
                # Find player by name
                for player_id, player_data in players.items():
                    if player_data.get('full_name', '').lower() == player_name.lower():
                        return player_data.get('injury_status')
                        
        except Exception as e:
            logger.error(f"Error getting injury status: {e}")
        
        return None
    
    def calculate_projection_adjustment(self, base_projection: float, injury_status: str, weather_factor: float = 1.0) -> float:
        """
        Adjust ESPN projection based on additional factors
        """
        adjusted = base_projection
        
        # Injury adjustments
        injury_multipliers = {
            'Healthy': 1.0,
            'Questionable': 0.85,  # Reduce by 15%
            'Doubtful': 0.3,       # Reduce by 70%
            'Out': 0.0,            # No points
            'IR': 0.0,             # No points
            'PUP': 0.0,            # No points
        }
        
        if injury_status in injury_multipliers:
            adjusted *= injury_multipliers[injury_status]
        
        # Weather factor (could be enhanced with actual weather data)
        adjusted *= weather_factor
        
        return round(adjusted, 1)

def test_projection_sources():
    """Test various projection sources"""
    
    aggregator = ProjectionAggregator()
    
    print("Testing projection sources...\n")
    
    # Test FantasyPros
    print("1. FantasyPros API:")
    aggregator.test_fantasypros_api()
    print()
    
    # Test Yahoo
    print("2. Yahoo Fantasy API:")
    aggregator.test_yahoo_api()
    print()
    
    # Test injury status enhancement
    print("3. Sleeper Injury Status Enhancement:")
    injury_status = aggregator.get_sleeper_injury_status("Josh Allen")
    print(f"Josh Allen injury status: {injury_status}")
    
    # Example projection adjustment
    base_projection = 22.5
    adjusted = aggregator.calculate_projection_adjustment(base_projection, injury_status or 'Healthy')
    print(f"Base projection: {base_projection}")
    print(f"Adjusted projection: {adjusted}")
    print()
    
    print("Recommendation: Use ESPN projections enhanced with Sleeper injury data")

if __name__ == "__main__":
    test_projection_sources()



