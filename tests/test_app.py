#!/usr/bin/env python3
"""
Test script for Fantasy Football Tracker
Tests the app without requiring ESPN credentials
"""

import sys
import os
import importlib.util

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_imports():
    """Test that all modules can be imported."""
    print("🧪 Testing imports...")
    
    try:
        import config
        print("  ✅ config.py imports successfully")
    except Exception as e:
        print(f"  ❌ config.py failed: {e}")
        return False
    
    try:
        import nfl_utils
        print("  ✅ nfl_utils.py imports successfully")
    except Exception as e:
        print(f"  ❌ nfl_utils.py failed: {e}")
        return False
    
    try:
        # Test importing fantasy_tracker without running it
        spec = importlib.util.spec_from_file_location("fantasy_tracker", "fantasy_tracker.py")
        module = importlib.util.module_from_spec(spec)
        print("  ✅ fantasy_tracker.py imports successfully")
    except Exception as e:
        print(f"  ❌ fantasy_tracker.py failed: {e}")
        return False
    
    return True

def test_nfl_utils():
    """Test NFL utility functions."""
    print("\n🧪 Testing NFL utilities...")
    
    try:
        from nfl_utils import NFLSeasonHelper
        from datetime import datetime
        
        # Test year detection
        year = NFLSeasonHelper.get_current_nfl_year()
        print(f"  ✅ Current NFL year: {year}")
        assert year >= 2024, "Year should be 2024 or later"
        
        # Test season start date
        start_date = NFLSeasonHelper.get_season_start_date(2026)
        print(f"  ✅ 2026 season starts: {start_date.strftime('%B %d, %Y')}")
        assert start_date.month == 9, "Season should start in September"
        
        # Test week calculation
        test_date = datetime(2026, 9, 15)  # Mid-September 2026
        week = NFLSeasonHelper.calculate_week_from_date(2026, test_date)
        print(f"  ✅ Week on {test_date.strftime('%B %d, %Y')}: Week {week}")
        assert 1 <= week <= 18, "Week should be between 1 and 18"
        
        return True
        
    except Exception as e:
        print(f"  ❌ NFL utils test failed: {e}")
        return False

def _sample_scores(count: int) -> list:
    """Standings rows for the cut-line render check."""
    teams = []
    for i in range(count):
        rank = i + 1
        teams.append({
            'team_name': f'Team {rank}',
            'live_score': float(100 - i),
            'projected_score': float(90 - i),
            'rank': rank,
            'projected_rank': rank,
            'is_current_top6': rank <= 6,
            'is_projected_top6': rank <= 6,
            'currently_playing': [],
            'yet_to_play': [],
            'yet_to_play_details': [],
        })
    return teams


def _render_scores(scores: list) -> str:
    from flask import Flask, render_template

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    app = Flask(__name__, template_folder=os.path.join(root, 'templates'))
    with app.app_context():
        return render_template(
            'dashboard.html',
            scores=scores,
            last_update=None,
            week=10,
            nfl_year=2026,
            api_error=None,
            eastern=None,
            playoff_cutoff=6,
        )


def _cut_follows_rank(html: str, table_id: str, rank_label: str, until: str) -> bool:
    """The dark rule sits after that rank and before the next row."""
    start = html.find(f'id="{table_id}"')
    end = html.find(until, start + len(table_id))
    section = html[start:end if end != -1 else None]
    rank_at = section.find(f'>{rank_label}<')
    cut_at = section.find('cut-row')
    next_rank = str(int(rank_label) + 1)
    next_at = section.find(f'>{next_rank}<', rank_at + 1)
    return rank_at != -1 and cut_at != -1 and next_at != -1 and rank_at < cut_at < next_at


def test_cut_line() -> bool:
    """A line renders under 6th on both tabs, and nowhere else."""
    print("\n🧪 Testing the line under 6th...")
    try:
        full = _render_scores(_sample_scores(12))
        assert full.count('class="cut-row"') == 2, full.count('class="cut-row"')
        assert _cut_follows_rank(full, 'currentStandings', '6', 'id="projectedStandings"')
        assert _cut_follows_rank(full, 'projectedStandings', '6', '</body>')
        assert 'const CUT_AFTER_RANK = 6;' in full

        short = _render_scores(_sample_scores(6))
        assert 'class="cut-row"' not in short

        # Live updates rebuild both tables. The same rank check has to be there.
        assert 'appendCutIfNeeded(tbody, team.rank, scores.length, 6)' in full
        assert 'appendCutIfNeeded(tbody, team.projected_rank, scores.length, 7)' in full
        print("  ✅ Line sits under 6th on both tabs, and hides when the league is shorter")
        return True
    except Exception as e:
        print(f"  ❌ Cut line test failed: {e}")
        return False


def test_config():
    """Test configuration module."""
    print("\n🧪 Testing configuration...")
    
    try:
        from config import Config
        
        # Test creating config
        config = Config()
        print("  ✅ Config object created")
        
        # Test validation (should fail without env vars)
        is_valid, error_msg = config.validate()
        if not is_valid:
            print(f"  ✅ Validation correctly fails without credentials: {error_msg}")
        
        # Test config with values
        config_with_values = Config(
            espn_league_id="123456",
            espn_s2="test_s2",
            espn_swid="test_swid"
        )
        is_valid, error_msg = config_with_values.validate()
        if is_valid:
            print("  ✅ Validation passes with all credentials")
        
        return True
        
    except Exception as e:
        print(f"  ❌ Config test failed: {e}")
        return False

def test_dependencies():
    """Test that all required dependencies are available."""
    print("\n🧪 Testing dependencies...")
    
    required = [
        'flask',
        'requests',
        'dotenv',
        'espn_api'
    ]
    
    all_found = True
    for dep in required:
        try:
            if dep == 'dotenv':
                __import__('dotenv')
            elif dep == 'espn_api':
                __import__('espn_api.football')
            else:
                __import__(dep)
            print(f"  ✅ {dep} is installed")
        except ImportError:
            print(f"  ❌ {dep} is NOT installed")
            all_found = False
    
    return all_found

def main():
    """Run all tests."""
    print("=" * 60)
    print("Fantasy Football Tracker - Test Suite")
    print("=" * 60)
    
    results = []
    
    # Run tests
    results.append(("Dependencies", test_dependencies()))
    results.append(("Imports", test_imports()))
    results.append(("NFL Utils", test_nfl_utils()))
    results.append(("Config", test_config()))
    results.append(("Cut line", test_cut_line()))
    
    # Print summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    all_passed = True
    for test_name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{test_name:20} {status}")
        if not passed:
            all_passed = False
    
    print("=" * 60)
    
    if all_passed:
        print("\n🎉 All tests passed! The app is ready to run.")
        print("\nNext steps:")
        print("1. Copy .env.example to .env")
        print("2. Fill in your ESPN credentials")
        print("3. Run: python fantasy_tracker.py")
        return 0
    else:
        print("\n⚠️  Some tests failed. Check the output above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
