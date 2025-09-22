"""
Test script to explore Sleeper API data structure
"""

import requests
import json

def test_sleeper_data():
    """Test what data Sleeper provides"""
    
    print("Testing Sleeper API data structure...")
    
    # Test NFL state
    response = requests.get("https://api.sleeper.app/v1/state/nfl")
    if response.status_code == 200:
        nfl_state = response.json()
        print(f"\nNFL State:")
        print(f"  Week: {nfl_state.get('week')}")
        print(f"  Season: {nfl_state.get('season')}")
        print(f"  Season Type: {nfl_state.get('season_type')}")
        print(f"  Display Week: {nfl_state.get('display_week')}")
    
    # Test stats data for current week
    week = 1
    season = 2025
    response = requests.get(f"https://api.sleeper.app/v1/stats/nfl/{season}/{week}")
    if response.status_code == 200:
        stats_data = response.json()
        print(f"\nStats data for Week {week}:")
        print(f"  Total players with stats: {len(stats_data)}")
        
        # Show a sample player's data
        if stats_data:
            sample_player_id = list(stats_data.keys())[0]
            sample_stats = stats_data[sample_player_id]
            print(f"\nSample player stats (ID: {sample_player_id}):")
            for stat, value in sample_stats.items():
                print(f"    {stat}: {value}")
    
    # Test projections endpoint (might not exist)
    response = requests.get(f"https://api.sleeper.app/v1/projections/nfl/{season}/{week}")
    if response.status_code == 200:
        projections_data = response.json()
        print(f"\nProjections data for Week {week}:")
        print(f"  Total players with projections: {len(projections_data)}")
        
        if projections_data:
            sample_player_id = list(projections_data.keys())[0]
            sample_proj = projections_data[sample_player_id]
            print(f"\nSample player projections (ID: {sample_player_id}):")
            for stat, value in sample_proj.items():
                print(f"    {stat}: {value}")
    else:
        print(f"\nNo projections endpoint available (Status: {response.status_code})")
    
    # Test trending players (might have projection-like data)
    response = requests.get(f"https://api.sleeper.app/v1/players/nfl/trending/add")
    if response.status_code == 200:
        trending = response.json()
        print(f"\nTrending players (being added): {len(trending)} players")
        if trending:
            print(f"  Sample trending player: {trending[0]}")
    
    # Get a few player details
    response = requests.get("https://api.sleeper.app/v1/players/nfl")
    if response.status_code == 200:
        players_data = response.json()
        print(f"\nPlayers database: {len(players_data)} players")
        
        # Find a few well-known players
        famous_players = []
        for player_id, player_info in list(players_data.items())[:100]:  # Check first 100
            if player_info.get('full_name') in ['Josh Allen', 'Patrick Mahomes', 'Travis Kelce']:
                famous_players.append((player_id, player_info))
        
        print(f"\nSample player details:")
        for player_id, player_info in famous_players[:2]:
            print(f"  {player_info.get('full_name')} (ID: {player_id}):")
            print(f"    Position: {player_info.get('position')}")
            print(f"    Team: {player_info.get('team')}")
            print(f"    Status: {player_info.get('status')}")
            print(f"    Injury Status: {player_info.get('injury_status')}")

if __name__ == "__main__":
    test_sleeper_data()



