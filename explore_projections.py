"""
Explore Sleeper projections data in more detail
"""

import requests
import json

def explore_projections():
    """Explore the projections data structure"""
    
    week = 1
    season = 2025
    
    # Get projections
    response = requests.get(f"https://api.sleeper.app/v1/projections/nfl/{season}/{week}")
    if response.status_code == 200:
        projections = response.json()
        print(f"Projections for Week {week}, {season}:")
        print(f"Total players: {len(projections)}")
        
        # Look for players with actual projection values
        players_with_data = []
        for player_id, data in projections.items():
            if data and len(data) > 3:  # More than just rankings
                players_with_data.append((player_id, data))
        
        print(f"Players with projection data: {len(players_with_data)}")
        
        if players_with_data:
            print("\nSample projection data:")
            for i, (player_id, data) in enumerate(players_with_data[:3]):
                print(f"\nPlayer ID {player_id}:")
                for key, value in data.items():
                    print(f"  {key}: {value}")
        
        # Look for specific stats that might be projections
        all_keys = set()
        for data in projections.values():
            if data:
                all_keys.update(data.keys())
        
        print(f"\nAll available projection fields:")
        for key in sorted(all_keys):
            print(f"  {key}")
    
    # Also check stats to see if they have projections
    response = requests.get(f"https://api.sleeper.app/v1/stats/nfl/{season}/{week}")
    if response.status_code == 200:
        stats = response.json()
        
        # Look for players with actual stat values
        players_with_stats = []
        for player_id, data in stats.items():
            if data and any(key not in ['pos_rank_ppr', 'pos_rank_half_ppr', 'pos_rank_std', 'rank_ppr', 'rank_half_ppr', 'rank_std'] for key in data.keys()):
                players_with_stats.append((player_id, data))
        
        print(f"\nStats - Players with actual stat data: {len(players_with_stats)}")
        
        if players_with_stats:
            print("\nSample stats data:")
            for i, (player_id, data) in enumerate(players_with_stats[:3]):
                print(f"\nPlayer ID {player_id}:")
                for key, value in data.items():
                    print(f"  {key}: {value}")
        
        # Get all stat fields
        all_stat_keys = set()
        for data in stats.values():
            if data:
                all_stat_keys.update(data.keys())
        
        print(f"\nAll available stats fields:")
        for key in sorted(all_stat_keys):
            print(f"  {key}")

if __name__ == "__main__":
    explore_projections()



