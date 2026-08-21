# 🧪 Testing Guide - Fantasy Football Tracker

## Quick Test (Just Did This!)

```bash
python3 test_app.py
```

✅ **Result**: All tests passed! The code is working correctly.

---

## Testing Options

### Option 1: Quick Syntax & Logic Test (No Credentials Needed) ✅ COMPLETED

This verifies the code is valid and logic works:

```bash
# Already done above
python3 test_app.py
```

What it tests:
- ✅ All dependencies installed
- ✅ Python modules import correctly
- ✅ NFL year detection (correctly detects 2026)
- ✅ Week calculation logic
- ✅ Configuration validation

---

### Option 2: Test with Mock/Demo Mode (Simulated Data)

Create a mock version that doesn't need ESPN credentials:

```bash
# Create a test .env file with dummy data
cat > .env.test << 'EOF'
ESPN_LEAGUE_ID=000000
ESPN_S2=dummy_s2_for_testing
ESPN_SWID={00000000-0000-0000-0000-000000000000}
PORT=5001
EOF

# This will fail to connect to ESPN (expected) but you can test the web interface
python3 fantasy_tracker.py
```

The app will:
- ❌ Fail to connect to ESPN (expected with fake credentials)
- ✅ Show the web interface at http://localhost:5001
- ✅ Display "Loading scores..." message
- ✅ Demonstrate the UI layout and styling

---

### Option 3: Test with Real ESPN Credentials (Full Integration Test)

#### Step 1: Get Fresh ESPN Credentials

1. **Open ESPN Fantasy Football** in your browser
2. **Log in** to your account
3. **Press F12** to open Developer Tools
4. **Go to Application tab** (Chrome) or Storage tab (Firefox)
5. **Click on Cookies** → https://espn.com
6. **Find and copy**:
   - `espn_s2` - Long string starting with "AE..."
   - `SWID` - Format: `{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}`
7. **Get your League ID** from the URL:
   - Example URL: `https://fantasy.espn.com/football/league?leagueId=637021`
   - League ID: `637021`

#### Step 2: Create .env File

```bash
# Copy the example
cp .env.example .env

# Edit with your real credentials
nano .env  # or use any text editor
```

Fill in:
```env
ESPN_LEAGUE_ID=your_actual_league_id
ESPN_S2=your_actual_espn_s2_cookie
ESPN_SWID=your_actual_swid_cookie
PORT=5000
```

#### Step 3: Run the App

```bash
python3 fantasy_tracker.py
```

Expected output:
```
🏈 Initializing Fantasy Tracker for 2026 NFL season
📅 Current week: Week 1
🔌 Connecting to ESPN league 637021 for 2026 season...
✅ Successfully connected! Found 10 teams
🔄 Started background score update thread
📊 Fetching scores for Week 1...
✅ Successfully fetched scores for 10 teams
🚀 Starting Fantasy Tracker on http://0.0.0.0:5000
```

#### Step 4: Test the Endpoints

Open these URLs in your browser:

1. **Main Dashboard**: http://localhost:5000
   - Should show live scores, rankings, player statuses
   - Three tabs: Current Standings, Live Projections, Movement

2. **API Endpoint**: http://localhost:5000/api/scores
   - Returns JSON with all scores data
   - Useful for debugging

3. **Health Check**: http://localhost:5000/health
   - Shows connection status
   - Returns JSON like:
   ```json
   {
     "status": "healthy",
     "connected": true,
     "teams_count": 10,
     "last_update": "2026-08-21T00:20:00",
     "nfl_year": 2026,
     "current_week": 1
   }
   ```

---

### Option 4: Test with Docker

Build and run in a container:

```bash
# Build the Docker image
docker build -t fantasy-tracker .

# Run with environment file
docker run -p 5000:5000 --env-file .env fantasy-tracker

# Or run with inline environment variables
docker run -p 5000:5000 \
  -e ESPN_LEAGUE_ID=your_league_id \
  -e ESPN_S2=your_s2_cookie \
  -e ESPN_SWID=your_swid_cookie \
  fantasy-tracker
```

Access at: http://localhost:5000

---

## 🐛 Troubleshooting Tests

### Issue: "Module not found"
```bash
# Reinstall dependencies
pip3 install -r requirements.txt
```

### Issue: "ESPN connection failed"
**Cause**: Expired cookies or wrong credentials

**Solution**:
1. Get fresh cookies from ESPN (see step-by-step above)
2. Update your `.env` file
3. Restart the app

### Issue: "No teams showing"
**Possible causes**:
- Wrong league ID
- Expired ESPN cookies
- Season hasn't started yet (app will show week 1 with 0 scores)

**Check**:
```bash
# Visit the health endpoint
curl http://localhost:5000/health
```

### Issue: Port already in use
```bash
# Change port in .env file
PORT=5001

# Or specify when running
PORT=5001 python3 fantasy_tracker.py
```

---

## 📊 What to Look For During Testing

### ✅ Good Signs
- Log messages with ✅ emojis
- "Successfully connected! Found X teams" message
- Dashboard loads within 2-3 seconds
- Teams appear in ranking order
- Scores update every 2-10 minutes (depending on game activity)

### ❌ Warning Signs  
- Log messages with ❌ emojis
- "Connection issues" or "API rate limited" messages
- Empty team list after 30 seconds
- 503 error on `/health` endpoint

---

## 🧪 Advanced Testing

### Test API Response Time
```bash
time curl http://localhost:5000/api/scores
```

### Test Health Endpoint
```bash
curl -s http://localhost:5000/health | python3 -m json.tool
```

### Monitor Logs
```bash
# Run with verbose output
python3 fantasy_tracker.py 2>&1 | tee app.log
```

### Test Update Intervals
Watch the logs to see update frequency:
- Should be ~2 min during game times
- Should be ~5-10 min when no games

---

## 🎯 Testing Checklist

Before your season starts, verify:

- [ ] App starts without errors
- [ ] ESPN connection succeeds
- [ ] Current week detected correctly (should be Week 1 until Sept 2026)
- [ ] Dashboard loads and displays properly
- [ ] All three tabs work (Current, Projected, Movement)
- [ ] Mobile view works (resize browser window)
- [ ] Health endpoint returns healthy status
- [ ] API endpoint returns valid JSON
- [ ] Auto-refresh works (wait 2 minutes, page should reload)
- [ ] Error messages display if connection fails

---

## 🚀 Ready for Production?

Once all tests pass with real credentials:

1. **Commit your test results** (don't commit `.env`!)
2. **Deploy to Render** with environment variables
3. **Monitor the logs** for the first few days
4. **Check the health endpoint** periodically
5. **Update ESPN cookies** when they expire (usually every few weeks)

---

## 💡 Pro Tips

1. **Keep ESPN cookies fresh**: Set a calendar reminder to refresh cookies every 2 weeks
2. **Monitor during first game day**: Watch logs to ensure updates are working
3. **Use the health endpoint**: Set up a monitoring service (UptimeRobot, etc.) to ping `/health`
4. **Test before season starts**: Run the app in August to catch any issues
5. **Bookmark the dashboard**: Add it to your phone's home screen for quick access

---

**Current Status**: ✅ All automated tests passed!
**Next Step**: Test with your real ESPN credentials to verify live data fetching
