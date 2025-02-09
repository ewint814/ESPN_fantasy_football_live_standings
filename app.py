from flask import Flask, render_template_string
import threading
import time
from espn_api.football import League
from threading import Lock
import os
Dfrom dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env

league = League(
    league_id=637021,
    year=2025,
    espn_s2=os.getenv("ESPN_S2"),
    swid=os.getenv("SWID")
)

# Flask App
app = Flask(__name__)

scores_and_players = []
scores_lock = Lock()

def fetch_scores():
    global scores_and_players
    while True:
        new_scores = get_team_scores_with_starters(league, week=15)  
        new_scores.sort(key=lambda x: x['Live Score'], reverse=True)

        with scores_lock:
            scores_and_players = new_scores

        time.sleep(90)
        
@app.after_request
def add_header(response):
    response.cache_control.no_cache = True
    response.cache_control.must_revalidate = True
    response.cache_control.no_store = True
    return response

def get_team_scores_with_starters(league, week):
    try:
        box_scores = league.box_scores(week=week)
    except Exception as e:
        print(f"Error fetching box scores: {e}")
        return []

    scores_and_players = []
    team_lookup = {team.team_id: team for team in league.teams}

    for game in box_scores:
        for team_id, lineup, score in [
            (game.home_team, game.home_lineup, game.home_score),
            (game.away_team, game.away_lineup, game.away_score)
        ]:
            team = team_lookup.get(team_id) if isinstance(team_id, int) else team_id
            team_name = team.team_name if team else "Unknown Team"

            currently_playing = [player.name for player in lineup if player.slot_position != "BE" and player.points > 0 and player.game_played == 1]
            not_started = [player.name for player in lineup if player.slot_position != "BE" and player.game_played == 0]

            currently_playing = currently_playing if currently_playing else ["No players playing"]
            not_started = not_started if not_started else ["All players played"]

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
            let countdown = 90;
            function updateCountdown() {
                document.getElementById("refresh-timer").innerText = countdown;
                countdown--;
                if (countdown < 0) countdown = 90;
            }
            setInterval(updateCountdown, 1000);
            setTimeout(function() {
                location.reload();
            }, 90000); // Refresh every 90 seconds
        </script>
    </head>
    <body>
        <div class="container">
            <h1>Live Fantasy Football Scores</h1>
            <p>Refreshing in <span id="refresh-timer">90</span> seconds...</p>
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
    app.run(host="0.0.0.0", port=5000, debug=False)