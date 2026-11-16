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
    losers_seeds,
    losers_six,
    owner_matches,
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
    """One season's champion as engraved, plus a disagreement when there is one."""

    year: int
    team_name: str
    owner: str
    agrees: bool
    note: str = ""


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
    walked = _walk(teams, year)
    if walked is not None and owner_matches(walked.owner, sheet_champion):
        return Title(year, walked.name.strip(), walked.owner, True)
    if walked is not None:
        note = f"{year} sheet {sheet_champion}, matchups {walked.owner} ({walked.name.strip()})"
        return Title(year, "", walked.owner, False, note)
    matched = _team_for_owner(teams, sheet_champion)
    if matched is None:
        return None
    return Title(year, matched[0], matched[1], True)


def _team_for_owner(teams: list[Any], sheet_name: str) -> tuple[str, str] | None:
    for team in teams:
        owner = owner_name(list(getattr(team, "owners", []) or []))
        if owner_matches(owner, sheet_name):
            return str(team.team_name).strip(), owner
    return None


def _walk(teams: list[Any], year: int) -> Club | None:
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
) -> Club | None:
    playoff = weeks[-TWELVE_TEAM_PLAYOFF_WEEKS:]
    clubs = _clubs(teams, indexes[-TWELVE_TEAM_PLAYOFF_WEEKS])
    seeds = winners_seeds(clubs, year, 6)
    result = winners_six(seeds, playoff)
    if result is None:
        return None
    # The losers' side has to be the same three weeks. The champion is the winners' final.
    if losers_six(losers_seeds(clubs, year, 6), playoff) is None:
        return None
    return result[0]


def _champion_ten(
    teams: list[Any], year: int, indexes: list[int], weeks: list[list[Game]]
) -> Club | None:
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
    if losers_six(losers_seeds(clubs, year, 4), rounds) is None:
        return None
    return result[0]
