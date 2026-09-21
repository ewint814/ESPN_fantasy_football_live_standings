"""Unit tests for live/overtime game classification (no ESPN credentials)."""

from types import SimpleNamespace

from fantasy_tracker_realtime import FantasyTracker


def _tracker():
    obj = SimpleNamespace(game_clocks={})
    obj._TEAM_ALIASES = FantasyTracker._TEAM_ALIASES
    obj._index_clock = FantasyTracker._index_clock.__get__(obj, FantasyTracker)
    obj._is_nfl_game_live = FantasyTracker._is_nfl_game_live.__get__(obj, FantasyTracker)
    obj._clock_for_team = FantasyTracker._clock_for_team.__get__(obj, FantasyTracker)
    obj._calculate_minutes_played = FantasyTracker._calculate_minutes_played.__get__(obj, FantasyTracker)
    return obj


def test_overtime_in_progress_is_live():
    clock = {
        'espn_state': 'in',
        'period': 5,
        'status': 'STATUS_IN_PROGRESS',
        'short_detail': '4:12 - OT',
        'clock': '4:12',
    }
    assert _tracker()._is_nfl_game_live(clock) is True


def test_final_overtime_is_not_live():
    clock = {
        'espn_state': 'post',
        'period': 5,
        'status': 'STATUS_FINAL',
        'short_detail': 'Final/OT',
        'clock': '0:00',
    }
    assert _tracker()._is_nfl_game_live(clock) is False


def test_end_of_regulation_before_ot_is_still_live():
    clock = {
        'espn_state': 'in',
        'period': 4,
        'status': 'STATUS_END_PERIOD',
        'short_detail': 'End of 4th',
        'clock': '0:00',
    }
    assert _tracker()._is_nfl_game_live(clock) is True


def test_scoreboard_live_overrides_espn_api_three_hour_heuristic():
    """espn-api sets game_played=100 after kickoff+3h; OT can still be going."""
    tracker = _tracker()
    ot_clock = {
        'espn_state': 'in',
        'period': 5,
        'status': 'STATUS_IN_PROGRESS',
        'short_detail': '3:20 - OT',
        'clock': '3:20',
        'minutes_played': 66.8,
    }
    tracker._index_clock(tracker.game_clocks, 'KC', ot_clock)
    assert tracker._is_nfl_game_live(tracker._clock_for_team('KC')) is True
    # Fantasy lineup often uses the same abbr the scoreboard uses
    assert tracker._clock_for_team('kc') == ot_clock


def test_team_alias_lookup():
    tracker = _tracker()
    clock = {'espn_state': 'in', 'period': 2, 'status': 'STATUS_IN_PROGRESS'}
    tracker._index_clock(tracker.game_clocks, 'WSH', clock)
    assert tracker._clock_for_team('WAS') is clock
    assert tracker._clock_for_team('WSH') is clock


def test_minutes_played_does_not_treat_end_period_as_final():
    tracker = _tracker()
    minutes = tracker._calculate_minutes_played('0:00', 4, 'STATUS_END_PERIOD', 'in')
    assert 59.0 <= minutes <= 61.0


def test_minutes_played_overtime_clock():
    tracker = _tracker()
    start_ot = tracker._calculate_minutes_played('10:00', 5, 'STATUS_IN_PROGRESS', 'in')
    assert 59.0 <= start_ot <= 61.0
    mid_ot = tracker._calculate_minutes_played('5:00', 5, 'STATUS_IN_PROGRESS', 'in')
    assert 64.0 <= mid_ot <= 66.0
    end_ot = tracker._calculate_minutes_played('0:00', 5, 'STATUS_IN_PROGRESS', 'in')
    assert 69.0 <= end_ot <= 71.0
