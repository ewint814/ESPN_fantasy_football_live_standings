"""
Check what live data is available during active games
"""

import requests
import json
from datetime import datetime

def check_live_projections():
    """Check for live projection data during active games"""
    
    print(f"Checking live data at {datetime.now()}")
    print("=" * 50)
    
    # Check Sleeper for live stats/projections
    print("1. SLEEPER API - Live Data:")
    
    # Get current NFL state
    response = requests.get("https://api.sleeper.app/v1/state/nfl")
    if response.status_code == 200:
        nfl_state = response.json()
        current_week = nfl_state.get('week', 1)
        season = nfl_state.get('season', 2025)
        print(f"   Current: Week {current_week}, Season {season}")
        
        # Check projections for current week
        response = requests.get(f"https://api.sleeper.app/v1/projections/nfl/{season}/{current_week}")
        if response.status_code == 200:
            projections = response.json()
            
            # Look for players with actual projection values (not just rankings)
            players_with_projections = 0
            sample_projections = []
            
            for player_id, data in projections.items():
                if data and any(key.startswith(('pass_', 'rush_', 'rec_', 'pts_')) for key in data.keys()):
                    players_with_projections += 1
                    if len(sample_projections) < 3:
                        sample_projections.append((player_id, data))
            
            print(f"   Players with live projections: {players_with_projections}")
            
            if sample_projections:
                print("   Sample live projections:")
                for player_id, data in sample_projections:
                    print(f"     Player {player_id}: {data}")
            else:
                print("   No live projection values found, checking all fields...")
                # Show all available fields
                all_fields = set()
                for data in list(projections.values())[:10]:
                    if data:
                        all_fields.update(data.keys())
                print(f"   Available fields: {sorted(all_fields)}")
        
        # Check stats for current week (might have live updates)
        response = requests.get(f"https://api.sleeper.app/v1/stats/nfl/{season}/{current_week}")
        if response.status_code == 200:
            stats = response.json()
            
            players_with_live_stats = 0
            sample_stats = []
            
            for player_id, data in stats.items():
                if data and any(key.startswith(('pass_', 'rush_', 'rec_', 'pts_')) for key in data.keys()):
                    players_with_live_stats += 1
                    if len(sample_stats) < 3:
                        sample_stats.append((player_id, data))
            
            print(f"   Players with live stats: {players_with_live_stats}")
            
            if sample_stats:
                print("   Sample live stats:")
                for player_id, data in sample_stats:
                    print(f"     Player {player_id}: {data}")
    
    print("\n2. ESPN API - Live Projections:")
    
    # Try ESPN's live projections during games
    # This might require different endpoints during live games
    espn_endpoints = [
        "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard",
        "https://fantasy.espn.com/apis/v3/games/ffl/seasons/2025/segments/0/leaguedefaults/1?view=kona_player_info",
    ]
    
    for endpoint in espn_endpoints:
        try:
            response = requests.get(endpoint, timeout=10)
            print(f"   {endpoint}")
            print(f"   Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, dict):
                    print(f"   Keys: {list(data.keys())[:5]}...")  # Show first 5 keys
                else:
                    print(f"   Type: {type(data)}")
        except Exception as e:
            print(f"   Error: {e}")
    
    print("\n3. OTHER LIVE SOURCES:")
    
    # Check other potential live sources
    other_sources = [
        "https://api.sportsdata.io/v3/nfl/stats/json/PlayerGameProjectionStatsByWeek/2025/1",  # Might be paid
        "https://www.fantasyfootballnerd.com/service/weekly-projections/json/nfl/1/",  # Might work
    ]
    
    for source in other_sources:
        try:
            response = requests.get(source, timeout=5)
            print(f"   {source}")
            print(f"   Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list) and data:
                    print(f"   Sample data: {data[0] if data else 'Empty'}")
                elif isinstance(data, dict):
                    print(f"   Keys: {list(data.keys())[:3]}...")
        except Exception as e:
            print(f"   Error: {e}")

if __name__ == "__main__":
    check_live_projections()



