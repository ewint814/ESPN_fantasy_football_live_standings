"""Bracket walk for a 12-team season and the 2025 points seed."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bracket import Club, Game, losers_six, owner_matches, winners_seeds
from espn_history import read_season


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
    assert title.note == ""
    assert len(title.roster) == 12
    assert (1, "Club 1", "Eli Last") in title.places
    assert (7, "Club 7", "Wechs Last") in title.places
    assert all(place not in {3, 4, 5, 6} for place, _team, _owner in title.places)


def test_walk_disagreement_is_a_note() -> None:
    title = read_season(twelve_team_season(), 2024, "Joe")
    assert title is not None
    assert not title.agrees
    assert title.team_name == ""
    assert "Joe" in title.note
    assert "Eli Last" in title.note
    assert "Club 1" in title.note


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
    assert [club.team_id for club in places] == [7, 8, 9, 10, 11, 12]


def test_missing_name_still_lists_espn_owners() -> None:
    title = read_season(twelve_team_season(), 2014, "Goggles")
    assert title is not None
    assert title.team_name == ""
    assert title.walk == "No bracket walk for this year."
    assert ("Club 1", "Eli Last") in title.roster


def test_owner_token() -> None:
    assert owner_matches("Eli Last", "Eli")
    assert not owner_matches("Elijah Last", "Eli")


def main() -> None:
    test_owner_token()
    test_points_seed_jumps_the_sixth()
    test_losers_order()
    test_walk_matches_the_sheet_champion()
    test_walk_disagreement_is_a_note()
    test_missing_name_still_lists_espn_owners()
    print("bracket ok")


if __name__ == "__main__":
    main()
