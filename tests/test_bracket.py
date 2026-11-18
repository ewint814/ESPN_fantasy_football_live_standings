"""Bracket walk for a 12-team season and the 2025 points seed."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bracket import Club, Game, losers_six, owner_matches, winners_seeds
from espn_history import _clubs, _played_weeks, read_season
from league_history import sheet_name_for


class Team:
    """Enough of an ESPN team for the season reader."""

    def __init__(self, team_id: int, name: str, owner: str) -> None:
        self.team_id = team_id
        self.team_name = name
        self.owners = [{"firstName": owner, "lastName": "Last"}]
        self.scores: list[float] = []
        self.outcomes: list[str] = []
        self.schedule: list[Team] = []


def add_week(teams: list[Team], games: list[tuple[int, int, float, float]]) -> None:
    """Append one finished week. Teams left out take a bye."""
    by_id = {team.team_id: team for team in teams}
    for team in teams:
        team.scores.append(0)
        team.outcomes.append("U")
        team.schedule.append(team)
    slot = len(teams[0].scores) - 1
    for home_id, away_id, home_score, away_score in games:
        home = by_id[home_id]
        away = by_id[away_id]
        home.scores[slot] = home_score
        away.scores[slot] = away_score
        home.schedule[slot] = away
        away.schedule[slot] = home
        home.outcomes[slot] = "W" if home_score > away_score else "L"
        away.outcomes[slot] = "W" if away_score > home_score else "L"


def twelve_team_season() -> list[Team]:
    """2024 shape: one regular week, then the three playoff rounds. Team 1 wins."""
    owners = [
        "Eli",
        "Joe",
        "Henry",
        "Yoni",
        "Bergel",
        "Noach",
        "Wechs",
        "Harry",
        "Josh",
        "Elisha",
        "Noam",
        "Yossi",
    ]
    teams = [Team(index + 1, f"Club {index + 1}", owners[index]) for index in range(12)]
    add_week(
        teams,
        [
            (1, 12, 100, 5),
            (2, 11, 90, 10),
            (3, 10, 80, 20),
            (4, 9, 70, 30),
            (5, 8, 60, 40),
            (6, 7, 55, 50),
        ],
    )
    add_week(
        teams,
        [
            (3, 6, 80, 40),
            (4, 5, 70, 30),
            (7, 12, 40, 10),
            (8, 11, 40, 10),
            (9, 10, 40, 10),
        ],
    )
    add_week(
        teams,
        [
            (1, 4, 90, 20),
            (2, 3, 90, 20),
            (8, 9, 30, 10),
            (10, 11, 30, 10),
        ],
    )
    add_week(
        teams,
        [
            (1, 2, 100, 40),
            (7, 8, 40, 10),
            (11, 12, 20, 5),
        ],
    )
    return teams


def test_walk_matches_the_sheet_champion() -> None:
    title = read_season(twelve_team_season(), 2024, "Eli")
    assert title is not None
    assert title.agrees
    assert title.team_name == "Club 1"
    assert title.owner == "Eli Last"
    assert (1, "Club 1", "Eli Last") in title.places
    assert (7, "Club 7", "Wechs Last") in title.places
    assert all(place not in {3, 4, 5, 6} for place, _team, _owner in title.places)


def test_walk_disagreement_engraves_nothing() -> None:
    title = read_season(twelve_team_season(), 2024, "Joe")
    assert title is not None
    assert not title.agrees
    assert title.team_name == ""
    assert title.owner == "Eli Last"


def test_points_seed_jumps_the_sixth() -> None:
    clubs = [
        Club(1, "A", "Eli", 8, 1400),
        Club(2, "B", "Joe", 7, 1300),
        Club(3, "C", "Henry", 7, 1200),
        Club(4, "D", "Yoni", 6, 1100),
        Club(5, "E", "Bergel", 6, 1000),
        Club(6, "F", "Noach", 6, 900),
        Club(7, "G", "Wechs", 5, 1600),
        Club(8, "H", "Harry", 4, 800),
    ]
    seeds = winners_seeds(clubs, 2025, 6)
    assert [club.team_id for club in seeds] == [1, 2, 3, 4, 5, 7]
    assert [club.team_id for club in winners_seeds(clubs, 2024, 6)] == [1, 2, 3, 4, 5, 6]


def test_losers_order() -> None:
    owners = ["Wechs", "Harry", "Josh", "Elisha", "Noam", "Yossi"]
    seeds = [Club(index + 7, f"Club {index + 7}", owners[index], 0, 0) for index in range(6)]
    opening = [
        Game(7, 12, 40, 10),
        Game(8, 11, 40, 10),
        Game(9, 10, 40, 10),
    ]
    middle = [Game(8, 9, 30, 10), Game(10, 11, 30, 10)]
    last = [Game(7, 8, 40, 10), Game(11, 12, 20, 5)]
    places = losers_six(seeds, [opening, middle, last])
    assert places is not None
    assert [place.club.team_id for place in places] == [7, 8, 9, 10, 11, 12]
    assert "Sacko" in places[-1].reason


def test_ninth_place_game_orders_ninth_and_tenth() -> None:
    owners = ["Wechs", "Harry", "Josh", "Elisha", "Noam", "Yossi"]
    seeds = [Club(index + 7, f"Club {index + 7}", owners[index], 0, 0) for index in range(6)]
    opening = [Game(7, 12, 40, 10), Game(8, 11, 40, 10), Game(9, 10, 40, 10)]
    middle = [Game(8, 9, 30, 10), Game(10, 11, 30, 10), Game(7, 12, 1, 99)]
    last = [Game(7, 8, 40, 10), Game(11, 12, 20, 5), Game(9, 10, 10, 50)]
    places = losers_six(seeds, [opening, middle, last])
    assert places is not None
    assert [place.club.team_id for place in places] == [7, 8, 10, 9, 11, 12]
    assert "9th-place game" in places[2].reason


def set_game(teams: list[Team], slot: int, game: tuple[int, int, float, float]) -> None:
    """Put one more game into an existing week."""
    home_id, away_id, home_score, away_score = game
    by_id = {team.team_id: team for team in teams}
    home = by_id[home_id]
    away = by_id[away_id]
    home.scores[slot] = home_score
    away.scores[slot] = away_score
    home.schedule[slot] = away
    away.schedule[slot] = home
    home.outcomes[slot] = "W" if home_score > away_score else "L"
    away.outcomes[slot] = "W" if away_score > home_score else "L"


def test_fifth_place_is_the_two_week_total() -> None:
    teams = twelve_team_season()
    set_game(teams, 2, (5, 6, 30, 20))
    set_game(teams, 3, (5, 6, 10, 40))
    title = read_season(teams, 2024, "Eli")
    assert title is not None
    assert title.pairs == () or all(start != 5 for start, *_ in title.pairs)
    placed = {place: owner for place, _team, owner in title.places}
    assert placed[5].startswith("Noach")
    assert placed[6].startswith("Bergel")
    notes = dict(title.place_notes)
    assert "two-week 5th-place game" in notes[5]
    assert "60.0 to 40.0" in notes[5]


def test_two_week_rounds_walk_losers_from_single_weeks() -> None:
    owners = ["Eli", "Joe", "Henry", "Yoni", "Bergel", "Noach", "Wechs", "Harry", "Josh", "Elisha"]
    teams = [Team(index + 1, f"Club {index + 1}", owners[index]) for index in range(10)]
    add_week(
        teams, [(1, 10, 100, 5), (2, 9, 90, 10), (3, 8, 80, 20), (4, 7, 70, 30), (5, 6, 60, 40)]
    )
    add_week(
        teams, [(1, 4, 200, 150), (2, 3, 150, 200), (5, 6, 300, 1), (7, 8, 300, 1), (9, 10, 300, 1)]
    )
    add_week(
        teams, [(1, 3, 150, 200), (2, 4, 200, 150), (5, 7, 300, 1), (6, 8, 300, 1), (9, 10, 300, 1)]
    )
    weekly = {
        5: {2: 10, 3: 10, 4: 2, 5: 2},
        6: {2: 10, 3: 20, 4: 5, 5: 5},
        7: {2: 10, 3: 50, 4: 1, 5: 1},
        8: {2: 20, 3: 50, 4: 10, 5: 10},
        9: {2: 20, 3: 20, 4: 20, 5: 20},
        10: {2: 20, 3: 10, 4: 30, 5: 30},
    }
    title = read_season(
        teams, 2020, "Henry", 1, {key: dict(value) for key, value in weekly.items()}
    )
    assert title is not None
    assert title.agrees
    order = [owner.split()[0] for _place, _team, owner in sorted(title.places)]
    assert order == [
        "Henry",
        "Eli",
        "Joe",
        "Yoni",
        "Josh",
        "Harry",
        "Elisha",
        "Noach",
        "Bergel",
        "Wechs",
    ]
    notes = dict(title.place_notes)
    assert "7th-place game" in notes[7]


def test_two_week_rounds_without_single_weeks_say_so() -> None:
    owners = ["Eli", "Joe", "Henry", "Yoni", "Bergel", "Noach", "Wechs", "Harry", "Josh", "Elisha"]
    teams = [Team(index + 1, f"Club {index + 1}", owners[index]) for index in range(10)]
    add_week(
        teams, [(1, 10, 100, 5), (2, 9, 90, 10), (3, 8, 80, 20), (4, 7, 70, 30), (5, 6, 60, 40)]
    )
    add_week(teams, [(1, 4, 200, 150), (2, 3, 150, 200)])
    add_week(teams, [(1, 3, 150, 200), (2, 4, 200, 150)])
    title = read_season(teams, 2020, "Henry", 1, {})
    assert title is not None
    assert not title.places


def test_unknown_champion_engraves_nothing() -> None:
    title = read_season(twelve_team_season(), 2014, "Goggles")
    assert title is not None
    assert title.team_name == ""
    assert title.places == ()


def test_owner_token() -> None:
    assert owner_matches("Eli Last", "Eli")
    assert not owner_matches("Elijah Last", "Eli")
    assert sheet_name_for("Joseph Solomont · bsportsfan96") == "Joe"
    assert sheet_name_for("jake h · nosoup4ya") == "Henry"
    assert sheet_name_for("Jake Bergel · Jabthat2394") == "Bergel"
    assert not owner_matches("Jake Bergel", "Henry")
    assert sheet_name_for("Noah Bressler") == "Noach"
    assert sheet_name_for("avi wechsler · avi110") == "Wechs"
    assert sheet_name_for("Ollie Wexler") == "Wechs"
    assert sheet_name_for("Joseph Solomon") == "Joe"
    assert sheet_name_for("YE V · YV23") == "Yossi"
    assert sheet_name_for("Yosef Vaitsblit") == "Yossi"
    assert sheet_name_for("jon avraham · johnthe bomb") == "Goggles"
    assert sheet_name_for("Elisha Galler") == "Elisha"
    assert owner_matches("Joseph Solomont", "Joe")


def test_missing_game_names_the_seeds() -> None:
    teams = twelve_team_season()
    # Replace the first playoff week with pairings the bracket does not expect.
    # Week 0 is the regular season. Week 1 is the first playoff round.
    teams_by_id = {team.team_id: team for team in teams}
    for team in teams:
        team.scores[1] = 0
        team.outcomes[1] = "U"
        team.schedule[1] = team
    games = [
        (3, 4, 80, 40),
        (5, 6, 70, 30),
        (7, 12, 40, 10),
        (8, 11, 40, 10),
        (9, 10, 40, 10),
    ]
    for home_id, away_id, home_score, away_score in games:
        home = teams_by_id[home_id]
        away = teams_by_id[away_id]
        home.scores[1] = home_score
        away.scores[1] = away_score
        home.schedule[1] = away
        away.schedule[1] = home
        home.outcomes[1] = "W" if home_score > away_score else "L"
        away.outcomes[1] = "W" if away_score > home_score else "L"
    title = read_season(teams, 2024, "Eli")
    assert title is not None
    assert title.places == ()


def test_top_six_score_adds_a_win_and_the_bottom_six_a_loss() -> None:
    """The second matchup is the weekly score, not a second opponent."""
    teams = twelve_team_season()
    teams[6].scores[0] = 200
    by_name = {club.owner.split()[0]: club for club in _clubs(teams, 1, 2024)}
    assert (by_name["Eli"].wins, by_name["Eli"].losses) == (2, 0)
    assert by_name["Eli"].points_for == 100
    assert (by_name["Wechs"].wins, by_name["Wechs"].losses) == (1, 1)
    assert by_name["Wechs"].points_for == 200
    assert (by_name["Yossi"].wins, by_name["Yossi"].losses) == (0, 2)
    assert (by_name["Noach"].wins, by_name["Noach"].losses) == (1, 1)
    earlier = {club.owner.split()[0]: club for club in _clubs(teams, 1, 2022)}
    assert (earlier["Eli"].wins, earlier["Eli"].losses) == (1, 0)
    assert (earlier["Wechs"].wins, earlier["Wechs"].losses) == (0, 1)


def reseeded_season() -> list[Team]:
    """The 6 seed wins week 1, so the 1 seed plays the 6 seed after reseeding."""
    owners = [
        "Eli",
        "Joe",
        "Henry",
        "Yoni",
        "Bergel",
        "Noach",
        "Wechs",
        "Harry",
        "Josh",
        "Elisha",
        "Noam",
        "Yossi",
    ]
    teams = [Team(index + 1, f"Club {index + 1}", owners[index]) for index in range(12)]
    add_week(
        teams,
        [
            (1, 12, 100, 5),
            (2, 11, 90, 10),
            (3, 10, 80, 20),
            (4, 9, 70, 30),
            (5, 8, 60, 40),
            (6, 7, 55, 50),
        ],
    )
    add_week(
        teams,
        [(3, 6, 40, 80), (4, 5, 70, 30), (7, 12, 40, 10), (8, 11, 40, 10), (9, 10, 40, 10)],
    )
    add_week(teams, [(1, 6, 90, 20), (2, 4, 90, 20), (8, 9, 30, 10), (10, 11, 30, 10)])
    add_week(teams, [(1, 2, 100, 40), (7, 8, 40, 10), (11, 12, 20, 5)])
    return teams


def test_winners_bracket_reseeds_from_2023() -> None:
    title = read_season(reseeded_season(), 2023, "Eli")
    assert title is not None
    assert title.agrees
    assert title.places
    fixed = read_season(reseeded_season(), 2022, "Eli")
    assert fixed is not None
    assert fixed.places == ()


def test_played_sixth_beats_a_points_leader_who_sat() -> None:
    """2025: the points leader is 6th only when that team played the 3 seed.

    Wechs has the most points outside the top 5 but sat, and Noach played the
    3 seed. The walk only finishes when it follows Noach.
    """
    teams = twelve_team_season()
    teams[6].scores[0] = 200
    title = read_season(teams, 2025, "Eli")
    assert title is not None
    assert title.agrees
    assert title.places


def ten_team_season() -> list[Team]:
    """10 teams, one regular week, three playoff rounds, then an extra week."""
    owners = ["Eli", "Joe", "Henry", "Yoni", "Bergel", "Noach", "Wechs", "Harry", "Josh", "Elisha"]
    teams = [Team(index + 1, f"Club {index + 1}", owners[index]) for index in range(10)]
    add_week(
        teams,
        [
            (1, 10, 100, 5),
            (2, 9, 90, 10),
            (3, 8, 80, 20),
            (4, 7, 70, 30),
            (5, 6, 60, 40),
        ],
    )
    add_week(
        teams,
        [
            (1, 4, 90, 20),
            (2, 3, 80, 30),
            (5, 10, 40, 10),
            (6, 9, 40, 10),
            (7, 8, 40, 10),
        ],
    )
    add_week(
        teams,
        [
            (1, 2, 100, 40),
            (4, 3, 30, 10),
            (6, 7, 30, 10),
            (8, 9, 30, 10),
        ],
    )
    add_week(teams, [(5, 6, 40, 10), (10, 9, 20, 5)])
    add_week(teams, [(1, 5, 10, 5)])
    return teams


def test_ten_team_years_walk_without_combining_the_last_weeks() -> None:
    title = read_season(ten_team_season(), 2015, "Eli", 1)
    assert title is not None
    assert title.agrees
    assert title.places


def _blank_weeks(teams: list[Team], count: int) -> None:
    """Append weeks with no game, so a later week can sit on the NFL calendar."""
    for _ in range(count):
        for team in teams:
            team.scores.append(0)
            team.outcomes.append("U")
            team.schedule.append(team)


def test_week_17_of_a_17_week_nfl_season_is_ignored() -> None:
    teams = ten_team_season()
    _blank_weeks(teams, 16 - len(teams[0].scores))
    add_week(teams, [(1, 2, 900, 1)])
    title = read_season(teams, 2016, "Eli", 1)
    assert title is not None
    assert title.agrees
    indexes, _weeks = _played_weeks(teams, 2016)
    assert 16 not in indexes


def test_week_16_still_counts_before_2021() -> None:
    teams = ten_team_season()
    _blank_weeks(teams, 15 - len(teams[0].scores))
    add_week(teams, [(1, 10, 40, 1)])
    clubs = {club.owner.split()[0]: club for club in _clubs(teams, 16, 2016)}
    assert clubs["Eli"].points_for == 340


def test_week_18_of_an_18_week_nfl_season_is_ignored() -> None:
    teams = twelve_team_season()
    _blank_weeks(teams, 17 - len(teams[0].scores))
    add_week(teams, [(12, 11, 500, 1)])
    title = read_season(teams, 2025, "Eli")
    assert title is not None
    assert title.agrees
    indexes, _weeks = _played_weeks(teams, 2025)
    assert 17 not in indexes


def test_eight_team_year_has_no_walk() -> None:
    title = read_season(twelve_team_season()[:8], 2011, "Eli", 1)
    assert title is not None
    assert title.places == ()


def main() -> None:
    test_owner_token()
    test_points_seed_jumps_the_sixth()
    test_losers_order()
    test_ninth_place_game_orders_ninth_and_tenth()
    test_fifth_place_is_the_two_week_total()
    test_two_week_rounds_walk_losers_from_single_weeks()
    test_two_week_rounds_without_single_weeks_say_so()
    test_walk_matches_the_sheet_champion()
    test_walk_disagreement_engraves_nothing()
    test_unknown_champion_engraves_nothing()
    test_missing_game_names_the_seeds()
    test_top_six_score_adds_a_win_and_the_bottom_six_a_loss()
    test_played_sixth_beats_a_points_leader_who_sat()
    test_winners_bracket_reseeds_from_2023()
    test_ten_team_years_walk_without_combining_the_last_weeks()
    test_week_17_of_a_17_week_nfl_season_is_ignored()
    test_week_16_still_counts_before_2021()
    test_week_18_of_an_18_week_nfl_season_is_ignored()
    test_eight_team_year_has_no_walk()
    print("bracket ok")


if __name__ == "__main__":
    main()
