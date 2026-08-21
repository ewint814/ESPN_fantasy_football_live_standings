# 🏈 Fantasy Football Live Scores Tracker

A real-time fantasy football score tracker that displays live scores, player statuses, and team rankings from your ESPN Fantasy Football league.

## Features

- ✅ **Real-time updates every 10 seconds** during games ⚡
- ✅ **Server-Sent Events** for instant push notifications
- ✅ **Player status tracking** (currently playing, yet to play, finished)
- ✅ **Beautiful responsive UI** with modern design
- ✅ **Auto-detecting current NFL week**
- ✅ **Mobile-friendly** interface
- ✅ **Comprehensive error handling** and logging
- ✅ **Team rankings** sorted by live scores
- ✅ **Live projections** based on current performance
- ✅ **Movement tracking** to see rank changes
- ✅ **Live connection indicator** with pulsing dot

## Local Development

### Prerequisites
- Python 3.11+
- ESPN Fantasy Football league access

### Setup
1. Clone this repository
2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Copy `.env.example` to `.env` and fill in your ESPN credentials
5. Run the application:
   ```bash
   python fantasy_tracker_realtime.py
   ```
6. Open http://localhost:5000 in your browser

## Getting ESPN Credentials

To get your ESPN credentials:
1. Log into ESPN Fantasy Football in your browser
2. Open Developer Tools (F12)
3. Go to Application/Storage → Cookies → espn.com
4. Find and copy:
   - `espn_s2` cookie value
   - `SWID` cookie value
   - Your league ID (from the URL)

## Deployment on Render

### Quick Deploy
1. Push this code to a GitHub repository
2. Go to [Render.com](https://render.com) and sign up
3. Click "New Web Service"
4. Connect your GitHub repository
5. Use these settings:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python fantasy_tracker_realtime.py`
6. Add environment variables:
   - `ESPN_LEAGUE_ID`: Your league ID
   - `ESPN_S2`: Your ESPN S2 cookie
   - `ESPN_SWID`: Your ESPN SWID cookie
   - `PORT`: 5000
7. Deploy!

### Environment Variables for Render
Set these in your Render dashboard under "Environment":
```
ESPN_LEAGUE_ID=your_league_id_here
ESPN_S2=your_espn_s2_cookie_here
ESPN_SWID=your_espn_swid_cookie_here
PORT=5000
```

## File Structure
```
├── fantasy_tracker.py           # Main application
├── requirements.txt             # Python dependencies
├── render.yaml                  # Render deployment config
├── Procfile                     # Process file for deployment
├── .env.example                 # Environment variables template
├── Dockerfile                   # Docker configuration
└── README.md                    # This file
```

## API Endpoints

- `GET /` - Main dashboard
- `GET /api/scores` - JSON API for scores data
- `GET /health` - Health check endpoint

## Troubleshooting

### Common Issues:
1. **"Unknown Team" showing**: ESPN cookies may be expired, refresh them
2. **No data loading**: Check that your league ID is correct
3. **App not starting**: Ensure all environment variables are set

### Logs
The app uses structured logging for debugging.

## Contributing

Feel free to submit issues and enhancement requests!

## License

MIT License - feel free to use and modify as needed.



