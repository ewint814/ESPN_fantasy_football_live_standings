#!/usr/bin/env python3
"""
Interactive setup and test script for Fantasy Football Tracker
Helps you input credentials and starts the real-time server
"""

import os
import sys
import subprocess
import time

def print_header():
    print("=" * 60)
    print("🏈 Fantasy Football Tracker - Real-Time Setup")
    print("=" * 60)
    print()

def get_credentials():
    """Interactively get ESPN credentials from user."""
    print("📝 Enter your ESPN Fantasy Football credentials:")
    print("   (Press Ctrl+C to cancel)")
    print()
    
    try:
        league_id = input("ESPN League ID: ").strip()
        espn_s2 = input("ESPN S2 Cookie: ").strip()
        espn_swid = input("ESPN SWID Cookie: ").strip()
        
        return league_id, espn_s2, espn_swid
    except KeyboardInterrupt:
        print("\n\n❌ Setup cancelled")
        sys.exit(0)

def create_env_file(league_id, espn_s2, espn_swid):
    """Create .env file with credentials."""
    env_content = f"""# ESPN Fantasy Football Credentials
ESPN_LEAGUE_ID={league_id}
ESPN_S2={espn_s2}
ESPN_SWID={espn_swid}
PORT=5000
"""
    
    with open('.env', 'w') as f:
        f.write(env_content)
    
    print("\n✅ Created .env file with your credentials")

def check_dependencies():
    """Check if dependencies are installed."""
    print("\n🔍 Checking dependencies...")
    try:
        import flask
        import requests
        import espn_api
        from dotenv import load_dotenv
        print("✅ All dependencies installed")
        return True
    except ImportError as e:
        print(f"❌ Missing dependency: {e}")
        print("\n📦 Installing dependencies...")
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", "requirements.txt"])
        return True

def start_server(use_realtime=True):
    """Start the Flask server."""
    script = "fantasy_tracker_realtime.py" if use_realtime else "fantasy_tracker.py"
    
    if not os.path.exists(script):
        print(f"❌ {script} not found!")
        return False
    
    print(f"\n🚀 Starting {'REAL-TIME' if use_realtime else 'standard'} server...")
    print()
    print("=" * 60)
    print("Server will start on: http://localhost:5000")
    print("=" * 60)
    print()
    print("📊 Features:")
    if use_realtime:
        print("  ⚡ Real-time updates every 10 seconds during games")
        print("  📡 Server-Sent Events for instant push notifications")
        print("  🔴 Live connection indicator")
    else:
        print("  🔄 Updates every 2 minutes")
    print()
    print("Press Ctrl+C to stop the server")
    print("=" * 60)
    print()
    
    try:
        subprocess.run([sys.executable, script])
    except KeyboardInterrupt:
        print("\n\n👋 Server stopped")

def main():
    print_header()
    
    # Check if .env already exists
    if os.path.exists('.env'):
        print("✅ Found existing .env file")
        response = input("\nUse existing credentials? (y/n): ").strip().lower()
        
        if response != 'y':
            league_id, espn_s2, espn_swid = get_credentials()
            create_env_file(league_id, espn_s2, espn_swid)
    else:
        print("📋 No .env file found. Let's create one!")
        print()
        print("How to get your credentials:")
        print("1. Open ESPN Fantasy Football in your browser")
        print("2. Press F12 → Application → Cookies → espn.com")
        print("3. Copy espn_s2 and SWID values")
        print("4. Get League ID from your league's URL")
        print()
        
        league_id, espn_s2, espn_swid = get_credentials()
        create_env_file(league_id, espn_s2, espn_swid)
    
    # Check dependencies
    check_dependencies()
    
    # Ask about real-time mode
    print()
    print("🎯 Choose your mode:")
    print("  1. REAL-TIME mode (10-second updates during games) ⚡ RECOMMENDED")
    print("  2. Standard mode (2-minute updates)")
    print()
    
    mode = input("Select mode (1 or 2, default=1): ").strip() or "1"
    use_realtime = mode == "1"
    
    # Start the server
    start_server(use_realtime)

if __name__ == "__main__":
    main()
