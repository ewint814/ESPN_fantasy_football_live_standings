"""Pick-your-opponent weeks: pick orders, the median game, seeding, and the odds board."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from types import SimpleNamespace

from pick_odds import (
    SOURCES,
    PickState,
    PickTeam,
    Settings,
    _fill_weakest,
    _play,
    curves,
    lineup_projection,
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
    filled = _fill_weakest(STANDINGS, made, strength)
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


def test_settings_and_sources() -> None:
    assert Settings.read("bogus", "smart", "bye") == Settings("espn", "smart", "bye")
    state = league()
    rest = {week: {team: 100.0 for team in STANDINGS} for week in (12, 13, 14)}
    with_espn = PickState(12, state.teams, STANDINGS, {1: 150.0}, rest=rest)
    shapes = {source: curves(with_espn, source) for source in SOURCES}
    # ESPN projections: this week is ESPN's own projection, later weeks the lineup projection.
    assert shapes["espn"].means[12][1] == 150.0
    assert shapes["espn"].means[13][1] == 100.0
    season = shapes["season"].means[13][1]
    assert season > 120
    assert shapes["season"].means[12][1] == (season + 150.0) / 2
    assert shapes["blend"].means[13][1] == (season + 100.0) / 2
    assert abs(shapes["recent"].means[13][2] - shapes["season"].means[13][2]) < 5


def test_lineup_projection_skips_byes_and_injuries() -> None:
    def player(points: float, slots: list[str], status: str = "ACTIVE", bye: int = 0) -> object:
        schedule = {str(week): {} for week in range(1, 19) if week != bye}
        return SimpleNamespace(
            projected_avg_points=points, eligibleSlots=slots, injuryStatus=status, schedule=schedule
        )

    players = [
        player(20, ["QB"]),
        player(30, ["QB"], bye=13),
        player(15, ["RB", "RB/WR/TE"]),
        player(14, ["RB", "RB/WR/TE"], status="INJURY_RESERVE"),
        player(12, ["RB", "RB/WR/TE"]),
        player(10, ["RB", "RB/WR/TE"], status="OUT"),
    ]
    slots = {"QB": 1, "RB": 2, "RB/WR/TE": 1, "BE": 6, "IR": 1}
    # Week 13: the 30-point QB is on bye; IR is out; OUT counts after this week.
    assert lineup_projection(players, slots, 13, this_week=False) == 20 + 15 + 12 + 10
    assert lineup_projection(players, slots, 13, this_week=True) == 20 + 15 + 12
    assert lineup_projection(players, slots, 12, this_week=False) == 30 + 15 + 12 + 10


def test_every_picker_chaos_and_compare() -> None:
    state = league()
    for picker in ("weakest", "random", "smart"):
        board = pick_board(state, ((1, 12),), Settings(picker=picker), runs=60)
        assert board.on_clock == 2 and len(board.options) == 9
        assert abs(sum(odds.playoffs for odds in board.league.values()) - 6) < 1e-9
    board = pick_board(state, settings=Settings(goal="bye"), runs=80, chaos=True, compare=True)
    goals = [round(option.odds.bye * 100) for option in board.options]
    assert goals == sorted(goals, reverse=True)
    assert board.chaos is not None and len(board.chaos.picks) == 6
    assert board.chaos.picks[0][0] == 1
    assert board.chaos.alive >= 1
    assert board.compare is not None
    assert set(board.compare[board.options[0].opponent]) == set(SOURCES)


def main() -> None:
    test_pick_orders()
    test_taken_teams_are_skipped()
    test_links_and_espn_schedule()
    test_median_game_and_seeds()
    test_board_odds()
    test_started_week_uses_espn_matchups()
    test_settings_and_sources()
    test_lineup_projection_skips_byes_and_injuries()
    test_every_picker_chaos_and_compare()
    print("picks ok")


if __name__ == "__main__":
    main()
