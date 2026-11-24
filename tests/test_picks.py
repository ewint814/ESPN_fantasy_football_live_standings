"""Pick-your-opponent weeks: pick orders, the median game, seeding, and the odds board."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pick_odds import (
    PickState,
    PickTeam,
    _fill_picks,
    _play,
    made_from_pairs,
    made_text,
    on_the_clock,
    parse_made,
    pick_board,
    pick_order,
    seeds,
    valid_made,
)

STANDINGS = tuple(range(1, 13))


def league(week: int = 12) -> PickState:
    """Twelve teams: team 1 is 18-4 and best; team 12 is 5-17 and worst."""
    teams = tuple(
        PickTeam(
            team_id=team,
            name=f"Club {team}",
            person=f"P{team}",
            wins=19 - team if team > 1 else 18,
            losses=3 + team if team > 1 else 4,
            ties=0,
            points_for=1500.0 - 10 * team,
            scores=tuple([140.0 - 3 * team] * (week - 1)) + (0.0,) * (15 - week),
        )
        for team in STANDINGS
    )
    return PickState(week=week, teams=teams, standings=STANDINGS, projected={})


def test_pick_orders() -> None:
    assert pick_order(12, STANDINGS) == STANDINGS
    assert pick_order(13, STANDINGS) == tuple(range(12, 0, -1))
    assert pick_order(14, STANDINGS) == (6, 7, 5, 8, 4, 9, 3, 10, 2, 11, 1, 12)


def test_taken_teams_are_skipped() -> None:
    made = ((1, 2),)
    assert on_the_clock(STANDINGS, made) == 3
    assert valid_made(STANDINGS, ((1, 2), (3, 4))) == ((1, 2), (3, 4))
    # Team 2 was taken, so it can't pick next, and a taken team can't be picked again.
    assert valid_made(STANDINGS, ((1, 2), (2, 5))) == ((1, 2),)
    assert valid_made(STANDINGS, ((1, 2), (3, 2))) == ((1, 2),)
    assert valid_made(STANDINGS, ((4, 1),)) == ()
    strength = {team: 200.0 - team for team in STANDINGS}
    filled = _fill_picks(STANDINGS, made, strength)
    assert filled[:2] == ((1, 2), (3, 12))
    assert len(filled) == 6
    assert sorted(team for pair in filled for team in pair) == list(STANDINGS)
    assert on_the_clock(STANDINGS, filled) is None


def test_links_and_espn_schedule() -> None:
    made = ((1, 2), (3, 9))
    assert parse_made(made_text(made)) == made
    assert parse_made("") == ()
    assert parse_made("1-2,x-3") == ((1, 2),)
    pairs = ((2, 1), (9, 3), (4, 5), (6, 7), (8, 10), (11, 12))
    assert made_from_pairs(STANDINGS, pairs)[:2] == ((1, 2), (3, 9))


def test_median_game_and_seeds() -> None:
    wins = {team: 0.0 for team in STANDINGS}
    points = {team: 0.0 for team in STANDINGS}
    scores = {team: 200.0 - team for team in STANDINGS}
    _play(((1, 2), (3, 4), (5, 6), (7, 8), (9, 10), (11, 12)), scores, wins, points)
    # Teams 1-6 are the top half: two wins for 1, 3, 5; one for 2, 4, 6.
    assert [wins[team] for team in STANDINGS] == [2, 1, 2, 1, 2, 1, 1, 0, 1, 0, 1, 0]
    points = {team: 1000.0 for team in STANDINGS}
    points[9] = 1400.0
    seeded = seeds(STANDINGS, points)
    assert [seeded[team] for team in (1, 2, 3, 4, 5)] == [1, 2, 3, 4, 5]
    assert seeded[9] == 6 and seeded[6] == 0


def test_board_odds() -> None:
    board = pick_board(league(), runs=300)
    assert board.on_clock == 1
    assert len(board.options) == 11
    assert {option.opponent for option in board.options} == set(range(2, 13))
    best = max(board.options, key=lambda option: option.win)
    assert best.opponent == 12
    top = board.league[1]
    assert top.playoffs > 0.99 and top.bye > board.league[3].bye
    assert board.league[12].playoffs < 0.05
    total = sum(odds.playoffs for odds in board.league.values())
    assert abs(total - 6) < 1e-9
    after = pick_board(league(), ((1, 12),), runs=300)
    assert after.on_clock == 2 and len(after.options) == 9
    last_week = pick_board(league(14), runs=200)
    assert last_week.on_clock == 6


def test_started_week_uses_espn_matchups() -> None:
    state = league()
    locked = ((1, 2), (3, 4), (5, 6), (7, 8), (9, 10), (11, 12))
    started = PickState(
        week=12,
        teams=state.teams,
        standings=STANDINGS,
        projected={},
        locked=locked,
        espn_pairs=locked,
    )
    board = pick_board(started, runs=100)
    assert board.locked and board.on_clock is None and not board.options
    assert len(board.made) == 6


def main() -> None:
    test_pick_orders()
    test_taken_teams_are_skipped()
    test_links_and_espn_schedule()
    test_median_game_and_seeds()
    test_board_odds()
    test_started_week_uses_espn_matchups()
    print("picks ok")


if __name__ == "__main__":
    main()
