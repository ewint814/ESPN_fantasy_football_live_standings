"""
Test if ESPN provides live projections during active games using authenticated connection
"""

from espn_api.football import League
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_live_espn_projections():
    """Test if ESPN provides live projections during games"""
    
    print("Testing ESPN Live Projections with Authenticated Connection")
    print("=" * 60)
    
    try:
        # Connect using your existing credentials
        league = League(
            league_id=637021,
            year=2025,
            espn_s2='AEBCCakbu%2B0%2FhbFeK5%2FgjfgBqJJfZKHfNjzHL2jCCx75d%2BXAUfjrRUGlUYOU%2BDcMyLnvZF9ASrpPFx%2Fd5IA4P8Yq1qMhcRE%2BqSa10zDy8NknbQWjzwKh3OVfI%2FCVZd2eKwMSzCNk54bD4FYRXMOMOVCp%2BwzXrZvHaoKs9nbe3Bsm%2BaKhCXOQ02AZbkrcGq%2B2naO9aSY3cXRoDjZaFgxYYcJnl7K23qiSoNPtt5MDZNjTeWFomxWJoC8Q84ob%2BrCve1L1ovlMK6Kg9KJ%2Br6UIYT2O',
            swid='{1BFA93C2-363A-4C34-A4BD-E6CE5E0C309B}'
        )
        
        print(f"✅ Connected to league {league.league_id}")
        print(f"📅 Current week: {getattr(league, 'current_week', 'Unknown')}")
        
        # Get box scores for current week
        current_week = 1  # We know it's week 1 from the scoreboard
        box_scores = league.box_scores(week=current_week)
        
        print(f"\n📊 Found {len(box_scores)} matchups")
        
        # Look for live projection data
        projection_data_found = False
        
        for i, matchup in enumerate(box_scores):
            print(f"\nMatchup {i+1}:")
            print(f"  {matchup.home_team.team_name} vs {matchup.away_team.team_name}")
            
            # Check both teams
            for team, lineup in [(matchup.home_team, matchup.home_lineup), 
                                (matchup.away_team, matchup.away_lineup)]:
                
                print(f"\n  {team.team_name} players:")
                
                for j, player in enumerate(lineup[:3]):  # Check first 3 players
                    print(f"    {player.name} ({player.position}):")
                    print(f"      Current points: {getattr(player, 'points', 'N/A')}")
                    print(f"      Projected points: {getattr(player, 'projected_points', 'N/A')}")
                    print(f"      Game played: {getattr(player, 'game_played', 'N/A')}")
                    
                    # Check if player has additional projection attributes
                    projection_attrs = ['projected_points', 'avg_points', 'total_points']
                    for attr in projection_attrs:
                        if hasattr(player, attr):
                            value = getattr(player, attr)
                            if value and value != 0:
                                print(f"      {attr}: {value}")
                                projection_data_found = True
                    
                    # Check all available attributes
                    print(f"      Available attributes: {[attr for attr in dir(player) if not attr.startswith('_')]}")
                    
                    if j == 0:  # Only show detailed info for first player
                        break
        
        if projection_data_found:
            print("\n✅ Found projection data!")
        else:
            print("\n❌ No live projection data found")
            print("   ESPN might not update projections during games")
            print("   Or projections might only be available pre-game")
        
        # Test if projections change during games by checking a specific player
        print("\n🔍 Detailed player analysis:")
        if box_scores:
            first_matchup = box_scores[0]
            first_player = first_matchup.home_lineup[0]
            
            print(f"Player: {first_player.name}")
            print(f"All attributes:")
            for attr in sorted(dir(first_player)):
                if not attr.startswith('_') and not callable(getattr(first_player, attr)):
                    try:
                        value = getattr(first_player, attr)
                        print(f"  {attr}: {value}")
                    except:
                        print(f"  {attr}: <error accessing>")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        logger.error(f"Error testing live projections: {e}")

if __name__ == "__main__":
    test_live_espn_projections()



