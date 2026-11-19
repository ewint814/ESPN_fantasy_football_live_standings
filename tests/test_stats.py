"""League stats: head-to-head, weekly highs and lows, careers, records, brackets, snapshot."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from test_bracket import twelve_team_season

from espn_history import dump_snapshot, load_snapshot, read_history
from league_stats import (
    GameRecord,
    SeasonRecord,
    TeamRecord,
    WeekScores,
    careers,
    head_to_head,
    league_records,
    matchups,
    records_board,
    season_bracket,
    stats_view,
    weekly_extremes,
)


def tiny_season(year: int) -> SeasonRecord:
    return SeasonRecord(
        year,
        (
            TeamRecord(1, "Club A", "Eli", 2, 0, 0, 230.0, 1),
            TeamRecord(2, "Club B", "Joe", 1, 1, 0, 200.0, 2),
            TeamRecord(3, "Club C", "Noam", 0, 2, 0, 150.0),
        ),
        (
            GameRecord("regular", "Week 1", 1, 2, 120.0, 100.0),
            GameRecord("regular", "Week 2", 1, 3, 110.0, 70.0),
            GameRecord("regular", "Week 2", 2, 3, 100.0, 80.0),
            GameRecord("winners", "Final", 2, 1, 95.0, 90.0),
            GameRecord("losers", "Sacko", 3, 2, 60.0, 60.0),
        ),
        (
            WeekScores(1, ((1, 120.0), (2, 100.0))),
            WeekScores(2, ((1, 110.0), (2, 100.0), (3, 70.0))),
        ),
    )


def test_head_to_head_tags_each_game() -> None:
    board = head_to_head({2019: tiny_season(2019), 2020: tiny_season(2020)})
    assert board["Eli"]["Joe"]["regular"] == [2, 0, 0]
    assert board["Eli"]["Joe"]["winners"] == [0, 2, 0]
    assert board["Eli"]["Joe"]["overall"] == [2, 2, 0]
    assert board["Joe"]["Noam"]["losers"] == [0, 0, 2]
    assert board["Noam"]["Joe"]["overall"] == [0, 2, 2]


def test_weekly_high_and_low() -> None:
    weeks = weekly_extremes(tiny_season(2019))
    assert [(w.week, w.high, w.low) for w in weeks] == [(1, "Eli", "Joe"), (2, "Eli", "Noam")]
    tied = SeasonRecord(
        2019, tiny_season(2019).teams, (), (WeekScores(1, ((1, 90.0), (2, 90.0), (3, 50.0))),)
    )
    assert weekly_extremes(tied)[0].high == "Eli & Joe"


def test_careers_use_the_sheet_for_titles_and_sackos() -> None:
    rows = {row.person: row for row in careers({2019: tiny_season(2019)})}
    assert rows["Eli"].titles == 5
    assert rows["Eli"].wins == 2 and rows["Eli"].record == "2-0"
    assert rows["Eli"].highs == 2
    assert rows["Noam"].lows == 1
    assert rows["Eli"].playoffs == 1 and rows["Noam"].playoffs == 0
    # 2014's 10th place is Eli now that the walk filled it.
    assert rows["Eli"].sackos >= 1


def test_league_records() -> None:
    found = {item.label: item for item in league_records({2019: tiny_season(2019)})}
    assert found["Highest week"].value == "120.0"
    assert found["Lowest week"].who == "Noam"
    assert found["Biggest blowout"].who == "Eli over Noam"
    assert found["Biggest blowout"].detail == "110.0–70.0, 2019 week 2"
    assert found["Closest game"].value == "20.0"
    assert found["Most points in a season"].who == "Eli"


def test_records_top_five_keeps_ties() -> None:
    found = {item.label: item for item in league_records({2019: tiny_season(2019)})}
    assert [entry.value for entry in found["Highest week"].top] == [
        "120.0", "110.0", "100.0", "100.0", "80.0"
    ]
    weeks = tuple(WeekScores(n, ((1, 100.0), (2, 90.0))) for n in range(1, 4))
    games = tuple(GameRecord("regular", f"Week {n}", 1, 2, 100.0, 90.0) for n in range(1, 4))
    tied = SeasonRecord(2019, tiny_season(2019).teams, games, weeks)
    found = {item.label: item for item in league_records({2019: tied})}
    assert len(found["Highest week"].top) == 6
    assert found["Highest week"].top[0].when == "2019, week 1"
    assert found["Biggest blowout"].top[0].score == "100.0–90.0"


def test_records_close_margins_and_points_per_game() -> None:
    season = tiny_season(2019)
    close = SeasonRecord(
        2019,
        season.teams,
        (GameRecord("regular", "Week 1", 1, 2, 104.34, 104.3), *season.games[1:]),
        season.weeks,
    )
    found = {item.label: item for item in league_records({2019: close})}
    assert found["Closest game"].value == "0.04"
    # Noam is 0-2 but scored in one week; per game divides by weeks scored.
    per_game = {entry.who: entry.value for entry in found["Most points per game"].top}
    assert per_game == {"Eli": "115.0", "Joe": "100.0", "Noam": "150.0"}


def ten_team_two_week(year: int) -> SeasonRecord:
    season = tiny_season(year)
    return SeasonRecord(
        year,
        season.teams,
        (
            *season.games[:3],
            GameRecord("winners", "Final (2 weeks)", 2, 1, 250.0, 180.0),
            GameRecord("losers", "Round 1", 3, 2, 99.0, 60.0),
            GameRecord("losers", "Sacko (2 weeks)", 3, 2, 300.0, 120.0),
        ),
        season.weeks,
    )


def test_records_views_keep_two_week_games_apart() -> None:
    twelve = SeasonRecord(
        2024,
        tuple(
            TeamRecord(n, f"Club {n}", name, 0, 0, 0, 100.0)
            for n, name in enumerate(["Eli", "Joe", *[f"P{n}" for n in range(10)]], 1)
        ),
        (
            GameRecord("regular", "Week 1", 1, 2, 130.0, 90.0),
            GameRecord("winners", "Final", 1, 2, 140.0, 139.0),
        ),
        (WeekScores(1, ((1, 130.0), (2, 90.0))),),
    )
    board = records_board({2015: ten_team_two_week(2015), 2024: twelve})
    assert set(board) == {"all", "10", "12"}
    ten_winners = board["10"]["winners"]
    assert [item.label for item in ten_winners.records][0] == "Highest 2-week score"
    assert ten_winners.records[0].value == "250.0"
    assert "two weeks" in ten_winners.note
    ten_losers = {item.label: item for item in board["10"]["losers"].records}
    assert ten_losers["Highest week"].value == "99.0"
    assert "left out" in board["10"]["losers"].note
    all_winners = {item.label: item for item in board["all"]["winners"].records}
    assert all_winners["Highest week"].value == "140.0"
    assert board["12"]["regular"].records[0].value == "130.0"
    assert not any("season" in item.label for item in ten_winners.records)
    assert any("per game" in item.label for item in board["12"]["overall"].records)
    old = {item.label: item for item in records_board({2011: tiny_season(2011)})["10"]["winners"].records}
    assert "Highest 2-week score" in old and "(2 weeks)" in old["Highest 2-week score"].detail


def test_kryptonite_compares_with_the_rest_of_their_season() -> None:
    teams = (
        TeamRecord(1, "A", "Eli", 0, 0, 0, 0.0),
        TeamRecord(2, "B", "Joe", 0, 0, 0, 0.0),
        TeamRecord(3, "C", "Noam", 0, 0, 0, 0.0),
    )
    games: list[GameRecord] = []
    weeks: list[WeekScores] = []
    for n in range(1, 9):
        # Joe scores 130 against Eli, 100 otherwise. Noam scores 80 against Eli, 100 otherwise.
        games += [
            GameRecord("regular", f"Week {n}", 1, 2, 110.0, 130.0),
            GameRecord("regular", f"Week {n}", 1, 3, 110.0, 80.0),
        ]
        weeks.append(WeekScores(n, ((1, 220.0), (2, 130.0), (3, 80.0))))
    for n in range(9, 17):
        games.append(GameRecord("regular", f"Week {n}", 2, 3, 100.0, 100.0))
        weeks.append(WeekScores(n, ((2, 100.0), (3, 100.0))))
    games.append(GameRecord("winners", "Final", 1, 2, 50.0, 200.0))
    board = matchups({2019: SeasonRecord(2019, teams, tuple(games), tuple(weeks))})
    eli = board["Eli"]
    assert [row.opponent for row in eli] == ["Joe", "Noam"]
    joe = eli[0]
    assert joe.games == 8 and joe.against == 130.0
    # Joe's other 15 weeks: 7 more 130s against Eli and 8 100s.
    assert round(joe.usual, 2) == round((7 * 130 + 8 * 100) / 15, 2)
    assert eli[-1].edge < 0
    # Seven games is under the cutoff.
    short = matchups({2019: SeasonRecord(2019, teams, tuple(games[:14]), tuple(weeks))})
    assert "Eli" not in short


def test_bracket_rounds_keep_play_order() -> None:
    rounds = season_bracket(tiny_season(2019), "winners")
    assert [round_.label for round_ in rounds] == ["Final"]
    line = rounds[0].games[0]
    assert (line.top, line.top_won, line.bottom, line.bottom_won) == ("Joe", True, "Eli", False)
    sacko = season_bracket(tiny_season(2019), "losers")[0].games[0]
    assert not sacko.top_won and not sacko.bottom_won


def test_espn_season_tags_playoff_sides() -> None:
    title, record = read_history(twelve_team_season(), 2024, "Eli")
    assert title is not None and record is not None
    kinds = {game.kind for game in record.games}
    assert kinds == {"regular", "winners", "losers"}
    labels = [game.label for game in record.games if game.kind == "winners"]
    assert labels[-1] in ("Final", "3rd place", "5th place (2 weeks)")
    assert "Final" in labels
    seeds = sorted(team.seed for team in record.teams if team.seed)
    assert seeds == [1, 2, 3, 4, 5, 6]
    assert len(record.weeks) == 1


def test_snapshot_round_trip() -> None:
    title, record = read_history(twelve_team_season(), 2024, "Eli")
    assert title is not None and record is not None
    text = dump_snapshot({2024: title}, {2024: record})
    titles, records = load_snapshot(text)
    assert titles[2024] == title
    assert records[2024] == record
    assert json.loads(text)[0]["year"] == 2024


def test_page_data_is_safe_to_embed() -> None:
    season = tiny_season(2019)
    odd = SeasonRecord(
        2019,
        (TeamRecord(1, "A", "</script>", 1, 0, 0, 1.0), *season.teams[1:]),
        season.games,
        season.weeks,
    )
    view = stats_view({2019: odd})
    assert "</script>" not in view.head_to_head
    assert "</script>" in json.loads(view.head_to_head)
    assert view.loaded == 1


def main() -> None:
    test_head_to_head_tags_each_game()
    test_weekly_high_and_low()
    test_careers_use_the_sheet_for_titles_and_sackos()
    test_league_records()
    test_records_top_five_keeps_ties()
    test_records_close_margins_and_points_per_game()
    test_records_views_keep_two_week_games_apart()
    test_kryptonite_compares_with_the_rest_of_their_season()
    test_bracket_rounds_keep_play_order()
    test_espn_season_tags_playoff_sides()
    test_snapshot_round_trip()
    test_page_data_is_safe_to_embed()
    print("stats ok")


if __name__ == "__main__":
    main()
