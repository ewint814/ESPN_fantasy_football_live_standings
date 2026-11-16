"""Championships from ESPN matchups, checked against the sheet.

The running app already has the ESPN cookies. This asks each past season for
its teams and weekly scores, then applies the bracket. A team name is engraved
only when that result is the same person the sheet lists as champion.
"""

import logging
from dataclasses import dataclass
from typing import Any

from espn_api.football import League

from bracket import (
    Club,
    Game,
    combine_weeks,
    game_between,
    loser_id,
    losers_seeds,
    losers_six,
    owner_matches,
    winner_id,
    winners_four,
    winners_seeds,
    winners_six,
)
from league_history import champion

logger = logging.getLogger(__name__)

# 12-team winners' side is three one-week rounds. 10-team winners' side is two
# one-week rounds, and the losers' final is the two weeks after that.
TWELVE_TEAM_PLAYOFF_WEEKS = 3
TEN_TEAM_SPAN = 4


@dataclass(frozen=True)
class Title:
    """One season's champion, plus the ESPN names and places used to get there."""

    year: int
    team_name: str
    owner: str
    agrees: bool
    note: str = ""
    walk: str = ""
    roster: tuple[tuple[str, str], ...] = ()
    places: tuple[tuple[int, str, str], ...] = ()


@dataclass(frozen=True)
class _Walked:
    champion: Club
    places: tuple[tuple[int, Club], ...]


def owner_name(owners: list[dict[str, Any]]) -> str:
    """First and last name of the first owner ESPN has for the team."""
    if not owners:
        return ""
    member = owners[0]
    first = str(member.get("firstName") or "").strip()
    last = str(member.get("lastName") or "").strip()
    full = f"{first} {last}".strip()
    if full:
        return full
    return str(member.get("displayName") or "").strip()


def load_titles(league_id: int, espn_s2: str, swid: str, years: list[int]) -> dict[int, Title]:
    """Fetch each season and keep the titles the sheet also names."""
    found: dict[int, Title] = {}
    for year in years:
        try:
            league = League(league_id=league_id, year=year, espn_s2=espn_s2, swid=swid)
            title = read_season(league.teams, year, champion(year))
        except Exception as exc:
            logger.warning("ESPN history %s failed: %s", year, exc)
            continue
        if title is not None:
            found[year] = title
    return found


def read_season(teams: list[Any], year: int, sheet_champion: str | None) -> Title | None:
    """Team name for the sheet champion, using the bracket when this year has one."""
    if not sheet_champion or not teams:
        return None
    roster = _roster(teams)
    walked = _walk(teams, year)
    places = _place_rows(walked)
    if walked is not None and owner_matches(walked.champion.owner, sheet_champion):
        return Title(
            year,
            walked.champion.name.strip(),
            walked.champion.owner,
            True,
            walk=_walk_line(walked),
            roster=roster,
            places=places,
        )
    if walked is not None:
        note = (
            f"{year} sheet {sheet_champion}, matchups "
            f"{walked.champion.owner} ({walked.champion.name.strip()})"
        )
        return Title(
            year,
            "",
            walked.champion.owner,
            False,
            note,
            _walk_line(walked),
            roster,
            places,
        )
    walk = _miss_line(year)
    matched = _team_for_owner(teams, sheet_champion)
    if matched is None:
        return Title(year, "", "", False, walk=walk, roster=roster)
    return Title(year, matched[0], matched[1], True, walk=walk, roster=roster)


def _roster(teams: list[Any]) -> tuple[tuple[str, str], ...]:
    rows = [
        (str(team.team_name).strip(), _owner_text(list(getattr(team, "owners", []) or [])))
        for team in teams
    ]
    return tuple(sorted(rows, key=lambda row: row[0].lower()))


def _owner_text(owners: list[dict[str, Any]]) -> str:
    """Owner spelling as ESPN has it, including a display name when it differs."""
    if not owners:
        return "(no owner on ESPN)"
    member = owners[0]
    first = str(member.get("firstName") or "").strip()
    last = str(member.get("lastName") or "").strip()
    display = str(member.get("displayName") or "").strip()
    named = f"{first} {last}".strip()
    if named and display and display.lower() != named.lower():
        return f"{named} · {display}"
    return named or display or "(blank owner)"


def _walk_line(walked: _Walked) -> str:
    return f"Bracket champion: {walked.champion.owner}, {walked.champion.name.strip()}."


def _miss_line(year: int) -> str:
    if year >= 2019:
        return "Bracket walk did not find the expected games."
    return "No bracket walk for this year."


def _place_rows(walked: _Walked | None) -> tuple[tuple[int, str, str], ...]:
    if walked is None:
        return ()
    return tuple((place, club.name.strip(), club.owner) for place, club in walked.places)


def _team_for_owner(teams: list[Any], sheet_name: str) -> tuple[str, str] | None:
    for team in teams:
        owner = owner_name(list(getattr(team, "owners", []) or []))
        if owner_matches(owner, sheet_name):
            return str(team.team_name).strip(), owner
    return None


def _walk(teams: list[Any], year: int) -> _Walked | None:
    indexes, weeks = _played_weeks(teams)
    if year >= 2021 and len(weeks) >= TWELVE_TEAM_PLAYOFF_WEEKS:
        return _champion_twelve(teams, year, indexes, weeks)
    if year in (2019, 2020) and len(weeks) >= TEN_TEAM_SPAN:
        return _champion_ten(teams, year, indexes, weeks)
    return None


def _played_weeks(teams: list[Any]) -> tuple[list[int], list[list[Game]]]:
    """Schedule indexes that finished, and the games in each."""
    count = min(len(team.outcomes) for team in teams)
    indexes: list[int] = []
    weeks: list[list[Game]] = []
    for index in range(count):
        games = _games_at(teams, index)
        if games:
            indexes.append(index)
            weeks.append(games)
    return indexes, weeks


def _games_at(teams: list[Any], index: int) -> list[Game]:
    seen: set[tuple[int, int]] = set()
    games: list[Game] = []
    for team in teams:
        opponent = team.schedule[index]
        if getattr(opponent, "team_id", None) in (None, team.team_id):
            continue
        if team.outcomes[index] not in ("W", "L", "T"):
            continue
        pair = tuple(sorted((team.team_id, opponent.team_id)))
        if pair in seen:
            continue
        seen.add(pair)
        games.append(
            Game(
                team.team_id,
                opponent.team_id,
                float(team.scores[index]),
                float(opponent.scores[index]),
            )
        )
    return games


def _clubs(teams: list[Any], through: int) -> list[Club]:
    """Wins and points before the playoff slots."""
    clubs: list[Club] = []
    for team in teams:
        wins = 0
        points = 0.0
        for index in range(through):
            opponent = team.schedule[index]
            if getattr(opponent, "team_id", None) in (None, team.team_id):
                continue
            points += float(team.scores[index] or 0)
            if team.outcomes[index] == "W":
                wins += 1
        clubs.append(
            Club(
                team.team_id,
                str(team.team_name),
                owner_name(list(team.owners or [])),
                wins,
                points,
            )
        )
    return clubs


def _champion_twelve(
    teams: list[Any], year: int, indexes: list[int], weeks: list[list[Game]]
) -> _Walked | None:
    playoff = weeks[-TWELVE_TEAM_PLAYOFF_WEEKS:]
    clubs = _clubs(teams, indexes[-TWELVE_TEAM_PLAYOFF_WEEKS])
    seeds = winners_seeds(clubs, year, 6)
    result = winners_six(seeds, playoff)
    if result is None:
        return None
    losers = losers_six(losers_seeds(clubs, year, 6), playoff)
    if losers is None:
        return None
    places: list[tuple[int, Club]] = [(1, result[0]), (2, result[1])]
    third = game_between(playoff[2], result[2].team_id, result[3].team_id)
    if third is not None and winner_id(third) is not None:
        by_id = {club.team_id: club for club in seeds}
        places.append((3, by_id[winner_id(third) or 0]))
        places.append((4, by_id[loser_id(third) or 0]))
    places.extend((6 + index, club) for index, club in enumerate(losers, start=1))
    return _Walked(result[0], tuple(places))


def _champion_ten(
    teams: list[Any], year: int, indexes: list[int], weeks: list[list[Game]]
) -> _Walked | None:
    tail = weeks[-TEN_TEAM_SPAN:]
    final_round = combine_weeks(tail[2], tail[3])
    if final_round is None:
        return None
    rounds = [tail[0], tail[1], final_round]
    clubs = _clubs(teams, indexes[-TEN_TEAM_SPAN])
    seeds = winners_seeds(clubs, year, 4)
    result = winners_four(seeds, rounds)
    if result is None:
        return None
    losers = losers_six(losers_seeds(clubs, year, 4), rounds)
    if losers is None:
        return None
    places = [(index, club) for index, club in enumerate(result, start=1)]
    places.extend((4 + index, club) for index, club in enumerate(losers, start=1))
    return _Walked(result[0], tuple(places))
