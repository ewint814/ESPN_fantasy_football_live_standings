# 🚀 How to Test Your Real-Time Fantasy Tracker

## ⚡ NEW: Real-Time Version Available!

I've created **two versions** for you:

1. **`fantasy_tracker.py`** - Standard version (2-minute updates)
2. **`fantasy_tracker_realtime.py`** - NEW! Real-time version (10-second updates) ⚡ **RECOMMENDED**

---

## 🎯 Quick Start (Easiest Way)

### Option 1: Interactive Setup Script

```bash
python3 setup_and_run.py
```

This will:
1. Ask for your ESPN credentials
2. Create the `.env` file automatically
3. Let you choose between real-time or standard mode
4. Start the server

---

## 📋 Manual Setup (If You Prefer)

### Step 1: Get Your ESPN Credentials

Your **League ID: 637021** (I found this in your code!)

You need to get fresh ESPN cookies from your Render dashboard OR from your browser:

**From Browser (takes 30 seconds):**
1. Go to **ESPN Fantasy Football** and log in
2. Press **F12** → **Application** tab → **Cookies** → **espn.com**
3. Copy these two values:
   - `espn_s2` - Long string starting with "AE..."
   - `SWID` - Format: `{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}`

**OR From Render Dashboard:**
1. Go to your Render dashboard
2. Open your fantasy football app
3. Go to Environment variables
4. Copy `ESPN_S2` and `ESPN_SWID` values

### Step 2: Create .env File

```bash
cat > .env << EOF
ESPN_LEAGUE_ID=637021
ESPN_S2=your_espn_s2_here
ESPN_SWID=your_espn_swid_here
PORT=5000
EOF
```

### Step 3: Run the Real-Time Version

```bash
python3 fantasy_tracker_realtime.py
```

### Step 4: Open Your Browser

Navigate to: **http://localhost:5000**

---

## 🎨 What You'll See

### Real-Time Features:
- 🔴 **Live indicator** with pulsing dot
- ⚡ **Updates every 10 seconds** during games
- 📊 **Three tabs**: Current Standings, Live Projections, Movement
- 🏆 **Top 6 highlighting** (green background)
- 🔄 **Seamless updates** - no page refresh!

### The Dashboard Shows:
- Current live scores ranked by position
- Player status (playing, yet to play, finished)
- Live projections based on current scoring pace
- Projected rank changes
- Top 6 teams for extra win scoring

---

## ⚡ Real-Time vs Standard Version

| Feature | Standard | Real-Time |
|---------|----------|-----------|
| Update interval during games | 2 minutes | **10 seconds** ⚡ |
| Push updates to browser | ❌ Page refresh | ✅ Server-Sent Events |
| Live connection indicator | ❌ | ✅ Pulsing dot |
| Bandwidth usage | Low | Moderate |
| Real-time feel | Good | **Excellent** 🔥 |

**Recommendation**: Use **real-time version** for the best experience!

---

## 🧪 Test the Health Endpoint

```bash
curl http://localhost:5000/health
```

Should return:
```json
{
  "status": "healthy",
  "connected": true,
  "teams_count": 12,
  "nfl_year": 2026,
  "current_week": 3,
  "real_time": true
}
```

---

## 🐛 Troubleshooting

### "Connection failed"
- ESPN cookies expired - get fresh ones
- Wrong League ID - verify it's 637021
- Check `.env` file has all 3 variables

### "No teams showing"
- Wait 15-20 seconds for first data fetch
- Check server logs for errors
- Verify it's Week 1+ of the season

### Port 5000 already in use
```bash
# Kill any running servers
pkill -f fantasy_tracker

# Or use a different port
PORT=5001 python3 fantasy_tracker_realtime.py
```

---

## 🚀 Deploy to Production

Once tested locally, deploy the real-time version to Render:

1. Update `Procfile`:
   ```
   web: python fantasy_tracker_realtime.py
   ```

2. Or keep both and choose in Render dashboard:
   - Standard: `python fantasy_tracker.py`
   - Real-time: `python fantasy_tracker_realtime.py`

3. Make sure these environment variables are set in Render:
   - `ESPN_LEAGUE_ID=637021`
   - `ESPN_S2=your_cookie`
   - `ESPN_SWID=your_cookie`

---

## 📊 Update Intervals Explained

**Real-Time Mode (`fantasy_tracker_realtime.py`):**
- **10 seconds** - During active games (12 PM - 11 PM)
- **30 seconds** - Game days, off-hours
- **2 minutes** - No games scheduled

**Standard Mode (`fantasy_tracker.py`):**
- **2 minutes** - During active games
- **5 minutes** - Game days, off-hours
- **10 minutes** - No games scheduled

---

## 🎉 Ready for 2026 NFL Season!

Your tracker is fully modernized and ready to go. The real-time version will give you the most responsive, instantaneous updates as scores change during live games!

**Questions?** Check the main README.md or TESTING.md for more details.
