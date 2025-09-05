from espn_api.football import League
from typing import List, Dict
from python_code.settings import ESPN_S2, SWID, LEAGUE_ID, YEAR, WEEK

class FantasyData:
    def __init__(self):
        # Initialize connection to ESPN Fantasy Football API
        # This creates our main league object we'll use to fetch all data
        self.league = League(
            league_id=LEAGUE_ID,
            year=YEAR,
            espn_s2=ESPN_S2,
            swid=SWID
        )

    def get_all_fantasy_data(self, week: int = WEEK) -> List[Dict]:
        """
        Main function to fetch all fantasy data for the week
        Returns a list of dictionaries containing team and player data
        """
        try:
            # Get all matchup data for the specified week
            box_scores = self.league.box_scores(week=week)
        except Exception as e:
            print(f"Error fetching box scores: {e}")
            return []

        # List to store all our processed fantasy data
        fantasy_data = []
        
        # Create a lookup dictionary for quick team info access
        # Maps team_id to team object
        team_lookup = {team.team_id: team for team in self.league.teams}

        # Process each game (matchup) in the week
        for game in box_scores:
            # Handle both home and away teams in each matchup
            for team, lineup, score in [
                (game.home_team, game.home_lineup, game.home_score),
                (game.away_team, game.away_lineup, game.away_score)
            ]:
                # Get team name, defaulting to "Unknown Team" if there's an issue
                team_name = team.team_name if team else "Unknown Team"
                
                # Get list of all active players (not on bench) who have scored points
                active_players = [
                    player.name for player in lineup 
                    if player.slot_position != "BE" and player.points > 0
                ]
                
                # Get list of all bench players
                bench_players = [
                    player.name for player in lineup 
                    if player.slot_position == "BE"
                ]

                # Create a data dictionary for this team
                fantasy_data.append({
                    'team_name': team_name,
                    'current_score': score,
                    'active_players': active_players,
                    'bench': bench_players,
                    # Future data points can be added here
                })

        # Sort teams by score (highest to lowest)
        fantasy_data.sort(key=lambda x: x['current_score'], reverse=True)
        return fantasy_data
