import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ESPN API Credentials
ESPN_S2 = os.getenv("ESPN_S2")
SWID = os.getenv("SWID")

# League Settings
LEAGUE_ID = 637021  # Your league ID
YEAR = 2024        # Current season
WEEK = 15          # Current week (you might want to make this dynamic later)

# Application Settings
REFRESH_INTERVAL = 90  # How often to update data (in seconds)