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
        teams.append(
            {
                "team_name": f"Team {rank}",
                "live_score": float(100 - i),
                "projected_score": float(90 - i),
                "rank": rank,
                "projected_rank": rank,
                "is_current_top6": rank <= 6,
                "is_projected_top6": rank <= 6,
                "currently_playing": [],
                "yet_to_play": [],
                "yet_to_play_details": [],
            }
        )
    return teams


def _render_scores(scores: list) -> str:
    from flask import Flask, render_template

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    app = Flask(__name__, template_folder=os.path.join(root, "templates"))
    with app.app_context():
        return render_template(
            "dashboard.html",
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
    section = html[start : end if end != -1 else None]
    rank_at = section.find(f">{rank_label}<")
    cut_at = section.find("cut-row")
    next_rank = str(int(rank_label) + 1)
    next_at = section.find(f">{next_rank}<", rank_at + 1)
    return rank_at != -1 and cut_at != -1 and next_at != -1 and rank_at < cut_at < next_at


def test_cut_line() -> bool:
    """A line renders under 6th on both tabs, and nowhere else."""
    print("\n🧪 Testing the line under 6th...")
    try:
        full = _render_scores(_sample_scores(12))
        assert full.count('class="cut-row"') == 2, full.count('class="cut-row"')
        assert _cut_follows_rank(full, "currentStandings", "6", 'id="projectedStandings"')
        assert _cut_follows_rank(full, "projectedStandings", "6", "</body>")
        assert "const CUT_AFTER_RANK = 6;" in full

        short = _render_scores(_sample_scores(6))
        assert 'class="cut-row"' not in short

        # Live updates rebuild both tables. The same rank check has to be there.
        assert "appendCutIfNeeded(tbody, team.rank, scores.length, 6)" in full
        assert "appendCutIfNeeded(tbody, team.projected_rank, scores.length, 7)" in full
        print("  ✅ Line sits under 6th on both tabs, and hides when the league is shorter")
        return True
    except Exception as e:
        print(f"  ❌ Cut line test failed: {e}")
        return False


def test_history() -> bool:
    """History shows the sheet's finishes, and the standings page keeps two tabs."""
    print("\n🧪 Testing league history...")
    try:
        from flask import Flask, render_template

        from espn_history import Title
        from league_history import champion, ring_counts, season_views

        assert champion(2025) == "Bergel"
        assert champion(2011) == "Eli"
        assert champion(2010) is None

        rings = {ring.name: ring for ring in ring_counts()}
        assert rings["Eli"].count == 5
        assert rings["Eli"].years == (2011, 2012, 2015, 2020, 2023)
        assert rings["Bergel"].count == 2
        assert rings["Bergel"].years == (2016, 2025)
        assert "Harry" not in rings

        by_year = {season.year: season for season in season_views()}
        places_2011 = [row.name for row in by_year[2011].rows]
        assert places_2011 == ["Eli", "Austin", "Yoni", "Noam", "Joe", "Tuvia", "Noach", "Goggles"]
        assert by_year[2012].joined == ("Wechs", "Henry", "Ezra")
        places_2018 = [row.name for row in by_year[2018].rows]
        assert places_2018 == [
            "Wechs", "Noach", "Henry", "Joe", "Eli", "Harry", "Noam", "Yossi", "Bergel", "Yoni"
        ]
        tenth_2016 = [row.name for row in by_year[2016].rows if row.label == "10th"]
        assert tenth_2016 == ["Yossi"]
        places_2014 = [row.name for row in by_year[2014].rows]
        assert places_2014[7:] == ["Jared", "Joe", "Eli"]
        assert not any(row.gap for row in by_year[2014].rows)

        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        app = Flask(__name__, template_folder=os.path.join(root, "templates"))
        with app.app_context():
            page = render_template(
                "history.html",
                seasons=season_views(),
            )
        assert "Schmacked History" in page
        assert 'href="/"' in page
        assert "not written down" not in page
        assert "Joined: Yossi" in page
        rows = page.split('class="plate-row"')[1:]
        assert len(rows) == 15
        assert "2025" in rows[0] and "Bergel" in rows[0]
        assert "2011" in rows[-1] and "Eli" in rows[-1]
        assert 'class="trophy-ball"' in page
        assert "Championships by person" not in page
        assert "Final places from the league sheet" not in page
        with app.app_context():
            engraved = render_template(
                "history.html",
                seasons=season_views(),
                titles={2025: Title(2025, "Club Bergel", "Bergel Last", True)},
            )
        bergel_row = engraved.split('class="plate-row"')[1]
        assert "Club Bergel" in bergel_row and "Bergel" in bergel_row
        assert "plate-owner" in bergel_row
        assert "Walk check" not in engraved
        assert "ESPN did not return" not in page
        assert page.count('<details class="season"') == 15
        assert 'id="season-2025" open' in page
        assert 'id="season-2024" open' not in page
        assert 'id="toggleSeasons"' in page

        from espn_history import load_snapshot
        from league_history import SEASONS, finishes
        from league_stats import stats_view

        with open(os.path.join(root, "history_snapshot.json"), encoding="utf-8") as handle:
            saved_titles, saved = load_snapshot(handle.read())
        # ESPN's bracket replay gives the sheet's places for 2012-2025; 2011 is the sheet's.
        final_places = finishes(saved_titles)
        assert final_places == SEASONS
        new_season = Title(
            2026,
            "Club Newbie",
            "Pat Newbie",
            True,
            tuple(
                (place, "club", owner)
                for place, owner in enumerate(("Pat Newbie", "Eli Winton", "jake h"), start=1)
            ),
        )
        with_new = finishes({**saved_titles, 2026: new_season})
        assert with_new[0].year == 2026
        assert with_new[0].places == ("Pat Newbie", "Eli", "Henry")
        assert with_new[0].joined == ("Pat Newbie",)
        assert with_new[1:] == SEASONS
        half = Title(2026, "", "", True, ((1, "club", "Eli Winton"), (3, "club", "jake h")))
        assert finishes({**saved_titles, 2026: half}) == SEASONS

        careers = {row.person: row for row in stats_view(saved).careers}
        assert careers["Eli"].points_against > 0 and careers["Eli"].active
        assert not careers["Austin"].active
        with app.app_context():
            full = render_template(
                "history.html",
                seasons=season_views(final_places),
                stats=stats_view(saved, final_places),
                season_count=len(final_places),
            )
        for heading in ("Avg finish", "Best finish", "Points for", "Points against",
                        "Top wk score", "Low wk score"):
            assert f">{heading}</th>" in full
        assert 'data-who="active"' in full and 'data-who="all" aria-pressed="true"' in full
        assert full.count('data-active="1"') == 12
        assert full.count('class="records-view"') == 12
        assert full.count('class="records-view" data-size="all" data-kind="regular">') == 1
        assert "Highest 2-week score" in full
        assert 'class="record-top" hidden' in full
        assert 'id="foesData"' in full and "Kryptonite" in full
        assert full.count('class="toggle-btn') == 0
        assert 'href="/moves"' in full

        from league_moves import moves_view, read_season
        from test_moves import FakeLeague

        with app.app_context():
            empty_moves = render_template(
                "moves.html", view=moves_view({}), loading=True, nfl_year=2026
            )
            moves_page = render_template(
                "moves.html",
                view=moves_view({2023: read_season(FakeLeague(), 2023)}),
                loading=False,
                nfl_year=2026,
            )
        assert "Nothing from ESPN yet" in empty_moves and "Still loading" in empty_moves
        for heading in ("Most active", "Best pickups", "Trades", "Bench points", "Worst weeks"):
            assert f"<h2>{heading}</h2>" in moves_page or f">{heading}</h2>" in moves_page
        assert "Dan RB" in moves_page and "Waiver $12" in moves_page

        dashboard = _render_scores(_sample_scores(12))
        assert dashboard.count('class="toggle-btn') == 2
        assert 'href="/history"' in dashboard
        print("  ✅ History matches the sheet, and standings still has two tabs")
        return True
    except Exception as e:
        print(f"  ❌ History test failed: {e}")
        return False


def test_version_tag() -> bool:
    """Pages show the deployed version and reload when /version reports a new one."""
    print("\n🧪 Testing the version tag...")
    try:
        import tempfile
        from datetime import datetime

        import pytz
        from flask import Flask, render_template_string

        from fantasy_tracker_realtime import FantasyTracker
        from visit_log import VisitLog

        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        eastern = pytz.timezone("America/New_York")
        tracker = FantasyTracker.__new__(FantasyTracker)
        tracker.app = Flask(__name__, template_folder=os.path.join(root, "templates"))
        tracker.eastern = eastern
        tracker.version = "a2ba9c4"
        tracker.started_at = eastern.localize(datetime(2026, 11, 21, 5, 58))
        tracker.visit_log = VisitLog(os.path.join(tempfile.mkdtemp(), "visits.log"), eastern)
        tracker._setup_routes()

        response = tracker.app.test_client().get("/version")
        assert response.get_json() == {"version": "a2ba9c4"}
        assert response.headers["Cache-Control"] == "no-store"
        with tracker.app.test_request_context():
            footer = render_template_string('{% include "_version.html" %}')
        assert "Version a2ba9c4 · live since Nov 21, 5:58 AM ET" in footer
        assert 'const loadedVersion = "a2ba9c4"' in footer
        assert "fetch('/version'" in footer
        # Pages rendered without the app (no version) leave the tag out.
        with Flask(__name__, template_folder=os.path.join(root, "templates")).app_context():
            assert render_template_string('{% include "_version.html" %}').strip() == ""
        print("  ✅ Version tag shows, and /version answers uncached")
        return True
    except Exception as e:
        print(f"  ❌ Version tag test failed: {e}")
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
            espn_league_id="123456", espn_s2="test_s2", espn_swid="test_swid"
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

    required = ["flask", "requests", "dotenv", "espn_api"]

    all_found = True
    for dep in required:
        try:
            if dep == "dotenv":
                __import__("dotenv")
            elif dep == "espn_api":
                __import__("espn_api.football")
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
    results.append(("History", test_history()))
    results.append(("Version tag", test_version_tag()))

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
