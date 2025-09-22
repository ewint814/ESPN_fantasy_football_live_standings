"""
Explore ESPN's live scoreboard data for projections
"""

import requests
import json
from datetime import datetime

def explore_espn_scoreboard():
    """Explore ESPN's live scoreboard data"""
    
    print("Exploring ESPN Live Scoreboard Data")
    print("=" * 40)
    
    try:
        response = requests.get("https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard")
        
        if response.status_code == 200:
            data = response.json()
            
            print(f"Main keys: {list(data.keys())}")
            
            # Check events (games)
            events = data.get('events', [])
            print(f"\nNumber of games: {len(events)}")
            
            if events:
                print("\nGame details:")
                for i, event in enumerate(events[:3]):  # Show first 3 games
                    print(f"\nGame {i+1}:")
                    print(f"  Name: {event.get('name', 'N/A')}")
                    print(f"  Status: {event.get('status', {}).get('type', {}).get('name', 'N/A')}")
                    print(f"  Date: {event.get('date', 'N/A')}")
                    
                    # Check competitions (team data)
                    competitions = event.get('competitions', [])
                    if competitions:
                        competition = competitions[0]
                        competitors = competition.get('competitors', [])
                        
                        print(f"  Teams:")
                        for competitor in competitors:
                            team = competitor.get('team', {})
                            score = competitor.get('score', 'N/A')
                            print(f"    {team.get('displayName', 'Unknown')}: {score}")
                        
                        # Look for live data or projections
                        print(f"  Competition keys: {list(competition.keys())}")
                        
                        # Check if there are any player-level stats
                        if 'details' in competition:
                            print(f"  Details: {competition['details']}")
            
            # Check season info
            season = data.get('season', {})
            print(f"\nSeason info:")
            print(f"  Year: {season.get('year')}")
            print(f"  Type: {season.get('type')}")
            
            # Check week info
            week = data.get('week', {})
            print(f"\nWeek info:")
            print(f"  Number: {week.get('number')}")
            print(f"  Text: {week.get('text')}")
            
        else:
            print(f"Error: Status code {response.status_code}")
            
    except Exception as e:
        print(f"Error: {e}")

def try_espn_fantasy_endpoints():
    """Try various ESPN fantasy endpoints that might have live projections"""
    
    print("\n" + "=" * 40)
    print("Trying ESPN Fantasy Endpoints")
    print("=" * 40)
    
    # Try different ESPN fantasy endpoints
    endpoints = [
        # Public endpoints (no auth required)
        "https://fantasy.espn.com/apis/v3/games/ffl/seasons/2025/segments/0/leaguedefaults/3?view=kona_player_info",
        "https://fantasy.espn.com/apis/v3/games/ffl/seasons/2025/segments/0/leaguedefaults/1?view=mDraftDetail&view=mLiveScoring&view=mMatchupScore&view=mPendingTransactions&view=mPositionalRatings&view=mRoster&view=mSettings&view=mTeam&view=modular&view=mNav",
        "https://fantasy.espn.com/apis/v3/games/ffl/seasons/2025/players?scoringPeriodId=1&view=players_wl",
        "https://fantasy.espn.com/apis/v3/games/ffl/seasons/2025/segments/0/leaguedefaults/1?view=kona_playercard",
    ]
    
    for endpoint in endpoints:
        print(f"\nTrying: {endpoint}")
        try:
            response = requests.get(endpoint, timeout=10)
            print(f"Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                
                if isinstance(data, dict):
                    print(f"Keys: {list(data.keys())}")
                    
                    # Look for player data
                    if 'players' in data:
                        players = data['players']
                        print(f"Players found: {len(players) if isinstance(players, list) else 'Not a list'}")
                        
                        if isinstance(players, list) and players:
                            sample_player = players[0]
                            print(f"Sample player keys: {list(sample_player.keys()) if isinstance(sample_player, dict) else 'Not a dict'}")
                            
                            # Look for projection data
                            if 'player' in sample_player:
                                player_info = sample_player['player']
                                if 'stats' in player_info:
                                    print(f"Player has stats: {list(player_info['stats'].keys()) if isinstance(player_info['stats'], dict) else 'Not a dict'}")
                
                elif isinstance(data, list):
                    print(f"List with {len(data)} items")
                    if data:
                        print(f"Sample item keys: {list(data[0].keys()) if isinstance(data[0], dict) else 'Not a dict'}")
                        
            elif response.status_code == 403:
                print("Access forbidden - might need authentication")
            else:
                print(f"Error response: {response.text[:200]}...")
                
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    explore_espn_scoreboard()
    try_espn_fantasy_endpoints()



