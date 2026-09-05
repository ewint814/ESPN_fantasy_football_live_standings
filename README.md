# 🏈 Fantasy Football Live Tracker

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

A real-time fantasy football score tracker that displays live scores, player statuses, and team rankings from your ESPN Fantasy Football league with **instant Server-Sent Events updates**.

![Real-time Updates](https://img.shields.io/badge/updates-real--time-brightgreen)
![Response Time](https://img.shields.io/badge/response-10s%20during%20games-blue)

## ✨ Features

- ⚡ **Real-time updates every 10 seconds** during active games
- 📡 **Server-Sent Events (SSE)** for instant push notifications
- 🎯 **Smart update intervals** - aggressive during games, conservative off-hours
- 📊 **Live projections** based on current performance
- 📈 **Movement tracking** to see rank changes in real-time
- 🎨 **Beautiful responsive UI** with modern design
- 📱 **Mobile-optimized** interface
- 🔴 **Live connection indicator** with pulsing dot
- ⏰ **Eastern Time display** for "Last updated" timestamp
- 🛡️ **Comprehensive error handling** with actionable user messages
- 🏥 **Health check endpoint** for monitoring
- 🔄 **Auto-detecting NFL year and week**

## 🚀 Quick Start

### Prerequisites

- Python 3.11 or higher
- ESPN Fantasy Football league access
- ESPN account with active cookies

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/fantasy-football-tracker.git
   cd fantasy-football-tracker
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your ESPN credentials (see below)
   ```

5. **Run the application**
   ```bash
   python fantasy_tracker_realtime.py
   ```

6. **Open in browser**
   ```
   http://localhost:5000
   ```

## 🔑 Getting ESPN Credentials

To connect to your ESPN Fantasy Football league:

1. Log into [ESPN Fantasy Football](https://fantasy.espn.com/football) in your browser
2. Open Developer Tools (`F12`)
3. Go to **Application** (Chrome) or **Storage** (Firefox) tab
4. Click **Cookies** → `https://espn.com`
5. Copy these values:
   - `espn_s2` - Long string starting with "AE..."
   - `SWID` - Format: `{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}`
6. Get your **League ID** from the URL:
   ```
   https://fantasy.espn.com/football/league?leagueId=637021
                                                      ^^^^^^ This is your League ID
   ```

Add these to your `.env` file:
```env
ESPN_LEAGUE_ID=637021
ESPN_S2=AExxxxxxxxxxxxxxxxxxxxxxxxxxxxxx...
ESPN_SWID={XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}
PORT=5000
```

## 🏗️ Project Structure

```
fantasy-football-tracker/
├── src/
│   ├── fantasy_tracker_realtime.py  # Main real-time application
│   ├── config.py                    # Configuration management
│   └── nfl_utils.py                 # NFL season utilities
├── tests/
│   └── test_app.py                  # Test suite
├── requirements.txt                 # Production dependencies
├── requirements-dev.txt             # Development dependencies
├── pyproject.toml                   # Project configuration
├── Dockerfile                       # Container configuration
├── render.yaml                      # Render deployment config
├── Procfile                         # Process configuration
├── .env.example                     # Environment template
├── LICENSE                          # MIT License
└── README.md                        # This file
```

## 📡 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Main dashboard with live scores |
| `/api/scores` | GET | JSON API for scores data |
| `/health` | GET | Health check and status |
| `/stream` | GET | Server-Sent Events stream (real-time) |

### Example: Health Check

```bash
curl http://localhost:5000/health
```

Response:
```json
{
  "status": "healthy",
  "connected": true,
  "teams_count": 12,
  "last_update": "2026-09-05T21:45:00",
  "nfl_year": 2026,
  "current_week": 1,
  "real_time": true
}
```

## 🎯 Update Intervals

The tracker intelligently adjusts update frequency based on game activity:

| Condition | Update Interval | Use Case |
|-----------|-----------------|----------|
| **Active games** (12pm-11pm ET) | 10 seconds ⚡ | Real-time during games |
| **Off-hours** (game days) | 30 seconds | Overnight on game days |
| **No games scheduled** | 2 minutes | Off-season or bye weeks |

💰 **100% Free**: ESPN API has no rate limits, and Render's free tier covers 750 hours/month (24/7 coverage).

## 🐳 Docker Deployment

### Build and Run

```bash
# Build image
docker build -t fantasy-tracker .

# Run container
docker run -p 5000:5000 --env-file .env fantasy-tracker
```

### Docker Compose

```yaml
version: '3.8'
services:
  tracker:
    build: .
    ports:
      - "5000:5000"
    env_file:
      - .env
    restart: unless-stopped
```

## ☁️ Deploy to Render

### One-Click Deploy

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com)

### Manual Deploy

1. Push code to GitHub
2. Go to [Render Dashboard](https://dashboard.render.com)
3. Click **New Web Service**
4. Connect your repository
5. Configure:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python fantasy_tracker_realtime.py`
6. Add environment variables in Render dashboard:
   - `ESPN_LEAGUE_ID`
   - `ESPN_S2`
   - `ESPN_SWID`
   - `PORT=5000`
7. Deploy!

Your app will be live at `https://your-app-name.onrender.com`

## 🧪 Testing

### Run Tests

```bash
# Basic test suite
python test_app.py

# With pytest (dev dependencies required)
pip install -r requirements-dev.txt
pytest tests/ -v

# With coverage
pytest tests/ --cov=src --cov-report=html
```

### Test Coverage

The test suite validates:
- ✅ Module imports
- ✅ NFL year detection (2026 season)
- ✅ Week calculation logic
- ✅ Configuration validation
- ✅ Dependency installation

## 🔧 Development

### Setup Development Environment

```bash
# Install dev dependencies
pip install -r requirements-dev.txt

# Install pre-commit hooks
pre-commit install

# Run linter
ruff check src/

# Run type checker
mypy src/
```

### Code Quality Tools

- **Ruff** - Fast Python linter and formatter
- **MyPy** - Static type checking
- **Pytest** - Testing framework
- **Pre-commit** - Git hooks for code quality

## 🐛 Troubleshooting

### Common Issues

#### "Configuration Error: Missing ESPN_LEAGUE_ID"
**Cause**: Environment variables not set  
**Fix**: Add credentials to `.env` file or Render dashboard environment section

#### "401 Unauthorized" or "Expired Cookies"
**Cause**: ESPN cookies expired (typically every 2-3 weeks)  
**Fix**: Get fresh `ESPN_S2` and `ESPN_SWID` cookies from ESPN.com

#### "404 League Not Found"
**Cause**: Wrong League ID  
**Fix**: Verify League ID in your ESPN Fantasy URL

#### "Stuck on Loading for 15+ seconds"
**Cause**: ESPN API slow or network issues  
**Fix**: Wait or refresh page; check `/health` endpoint

#### No live scores showing
**Cause**: Off-season or before first game  
**Fix**: Normal behavior; scores populate when season starts

### Debug Mode

Enable detailed logging:
```bash
DEBUG=true python fantasy_tracker_realtime.py
```

### Check Logs

```bash
# View last 100 lines
tail -f -n 100 app.log

# Filter for errors
grep "❌" app.log
```

## 📊 Monitoring

### Health Check Monitoring

Set up monitoring with services like:
- [UptimeRobot](https://uptimerobot.com/)
- [Pingdom](https://www.pingdom.com/)
- [StatusCake](https://www.statuscake.com/)

Configure to ping: `https://your-app.onrender.com/health`

### Maintenance

- 🔄 **Refresh ESPN cookies** every 2-3 weeks
- 📈 **Monitor during first game day** to verify updates
- 🏥 **Check health endpoint** periodically
- 📝 **Review logs** for errors or warnings

## 🤝 Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Development Guidelines

- Follow existing code style (enforced by Ruff)
- Add type hints to all functions
- Write tests for new features
- Update documentation as needed
- Run `pre-commit` before committing

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Built with [Flask](https://flask.palletsprojects.com/)
- Uses [espn-api](https://github.com/cwendt94/espn-api) Python wrapper
- Deployed on [Render](https://render.com/)

## 📞 Support

- 📖 [Documentation](https://github.com/yourusername/fantasy-football-tracker/wiki)
- 🐛 [Issue Tracker](https://github.com/yourusername/fantasy-football-tracker/issues)
- 💬 [Discussions](https://github.com/yourusername/fantasy-football-tracker/discussions)

---

**Made with ❤️ for Fantasy Football enthusiasts**

Ready for the 2026 NFL season! 🏈
