from flask import Flask, render_template_string
import threading
import time
from espn_api.football import League

# private league with cookies
league = League(league_id=637021, year=2024, espn_s2='AEBCCakbu%2B0%2FhbFeK5%2FgjfgBqJJfZKHfNjzHL2jCCx75d%2BXAUfjrRUGlUYOU%2BDcMyLnvZF9ASrpPFx%2Fd5IA4P8Yq1qMhcRE%2BqSa10zDy8NknbQWjzwKh3OVfI%2FCVZd2eKwMSzCNk54bD4FYRXMOMOVCp%2BwzXrZvHaoKs9nbe3Bsm%2BaKhCXOQ02AZbkrcGq%2B2naO9aSY3cXRoDjZaFgxYYcJnl7K23qiSoNPtt5MDZNjTeWFomxWJoC8Q84ob%2BrCve1L1ovlMK6Kg9KJ%2Br6UIYT2O', swid='{1BFA93C2-363A-4C34-A4BD-E6CE5E0C309B}')

# Flask App
app = Flask(__name__)

# Shared variable to store scores
scores_and_players = []

# Function to fetch scores
def fetch_scores():
    """
    Fetch scores every 90 seconds, sort by Live Score, and update the global variable.
    """
    global scores_and_players
    while True:
        scores_and_players = get_team_scores_with_starters(league, week=15)  # Replace with the correct week
        # Sort scores in descending order by 'Live Score'
        scores_and_players.sort(key=lambda x: x['Live Score'], reverse=True)
        time.sleep(90)

def get_team_scores_with_starters(league, week):
    """
    Fetch live scores and determine:
    1. Starters currently playing (not labeled 'BE').
    2. Starters yet to start their games (not labeled 'BE').
    If no players are found, return descriptive messages.
    """
    box_scores = league.box_scores(week=week)
    scores_and_players = []

    # Map team IDs to Team objects for easy lookup
    team_lookup = {team.team_id: team for team in league.teams}

    for game in box_scores:
        for team_id, lineup, score in [
            (game.home_team, game.home_lineup, game.home_score),
            (game.away_team, game.away_lineup, game.away_score)
        ]:
            # Resolve the team object from the team ID
            if isinstance(team_id, int):
                team = team_lookup.get(team_id)
            else:
                team = team_id  # Already a Team object

            # Handle case where team is None (unlikely but possible)
            team_name = team.team_name if team else "Unknown Team"

            # Filter players who are not on the bench
            currently_playing = [
                player.name for player in lineup
                if player.slot_position != "BE"  # Exclude bench players
                and player.points > 0  # Player is currently playing
                and player.game_played == 1  # Game is in progress
            ]

            not_started = [
                player.name for player in lineup
                if player.slot_position != "BE"  # Exclude bench players
                and player.game_played == 0  # Game has not started
            ]

            # Handle cases with no players in each category
            if not currently_playing:
                currently_playing = ["No players playing"]
            if not not_started:
                not_started = ["All players played"]

            # Add team data to the list
            scores_and_players.append({
                'Team Name': team_name,
                'Live Score': score,
                'Starters Currently Playing': ", ".join(currently_playing),
                'Starters Yet to Play': ", ".join(not_started)
            })

    return scores_and_players

@app.route('/')
def index():
    """
    Render the live scores on the webpage.
    """
    html_template = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Live Fantasy Football Scores</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                background-color: #f4f4f4;
                margin: 0;
                padding: 20px;
            }
            .container {
                max-width: 800px;
                margin: auto;
                background: white;
                padding: 20px;
                border-radius: 8px;
                box-shadow: 0 0 10px rgba(0, 0, 0, 0.1);
            }
            table {
                width: 100%;
                border-collapse: collapse;
            }
            th, td {
                padding: 10px;
                text-align: left;
                border-bottom: 1px solid #ddd;
            }
            th {
                background-color: #f8f8f8;
            }
        </style>
        <script>
            setTimeout(function() {
                location.reload();
            }, 90000); // Refresh every 90 seconds
        </script>
    </head>
    <body>
        <div class="container">
            <h1>Live Fantasy Football Scores</h1>
            <table>
                <thead>
                    <tr>
                        <th>Team Name</th>
                        <th>Live Score</th>
                        <th>Starters Currently Playing</th>
                        <th>Starters Yet to Play</th>
                    </tr>
                </thead>
                <tbody>
                    {% for entry in scores %}
                    <tr>
                        <td>{{ entry['Team Name'] }}</td>
                        <td>{{ entry['Live Score'] }}</td>
                        <td>{{ entry['Starters Currently Playing'] }}</td>
                        <td>{{ entry['Starters Yet to Play'] }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </body>
    </html>
    """
    return render_template_string(html_template, scores=scores_and_players)

# Start the score-fetching thread
thread = threading.Thread(target=fetch_scores, daemon=True)
thread.start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
