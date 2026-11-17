"""Championships from ESPN matchups, checked against the sheet.

The running app already has the ESPN cookies. This asks each past season for
its teams and weekly scores, then applies the bracket. A team name is engraved
only when that result is the same person the sheet lists as champion.

The history page also gets a place-by-place check: the walk's order, the
sheet's order, and a note on each row where those are not the same person.
"""

from __future__ import annotations

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
    person_label,
    rank_clubs,
    winner_id,
    winners_four,
    winners_seeds,
    winners_six,
)
from league_history import SEASONS, Season, champion, ordinal, sheet_name_for

logger = logging.getLogger(__name__)

# 12-team winners' side is three one-week rounds. 10-team winners' side is two
# one-week rounds, and the losers' final is the two weeks after that.
TWELVE_TEAM_PLAYOFF_WEEKS = 3
TEN_TEAM_SPAN = 4

# (start place, end place, ((team, owner), (team, owner)), reason)
PairRow = tuple[int, int, tuple[tuple[str, str], tuple[str, str]], str]


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
    place_notes: tuple[tuple[int, str], ...] = ()
    pairs: tuple[PairRow, ...] = ()
    seeds: tuple[SeedLine, ...] = ()
    weeks: tuple[WeekLine, ...] = ()


@dataclass(frozen=True)
class _Walked:
    champion: Club
    places: tuple[tuple[int, Club, str], ...]
    pairs: tuple[tuple[int, int, tuple[Club, Club], str], ...]


@dataclass(frozen=True)
class SeedLine:
    """One team in the regular-season table."""

    rank: str
    seed: str
    who: str
    record: str
    points: str
    note: str


@dataclass(frozen=True)
class GameLine:
    """One matchup in a playoff week."""

    home: str
    home_score: str
    away_score: str
    away: str


@dataclass(frozen=True)
class WeekLine:
    """The games in one playoff week."""

    label: str
    games: tuple[GameLine, ...]


@dataclass(frozen=True)
class CheckRow:
    """One place, with the walk and the sheet side by side."""

    label: str
    walk: str
    sheet: str
    differs: bool
    why: str


@dataclass(frozen=True)
class SeasonCheck:
    """A year of the walk check."""

    year: int
    summary: str
    differs: int
    walk_line: str
    rows: tuple[CheckRow, ...]
    roster: tuple[tuple[str, str, str], ...]
    seeds: tuple[SeedLine, ...] = ()
    weeks: tuple[WeekLine, ...] = ()


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
            regular = getattr(getattr(league, "settings", None), "reg_season_count", None)
            title = read_season(league.teams, year, champion(year), regular)
        except Exception as exc:
            logger.warning("ESPN history %s failed: %s", year, exc)
            continue
        if title is not None:
            found[year] = title
    return found


def read_season(
    teams: list[Any],
    year: int,
    sheet_champion: str | None,
    regular_season_weeks: int | None = None,
) -> Title | None:
    """Team name for the sheet champion, using the bracket when this year has one."""
    if not sheet_champion or not teams:
        return None
    roster = _roster(teams)
    walked = _walk(teams, year, regular_season_weeks)
    detail, seeds, weeks = _playoff_detail(teams, year, walked, regular_season_weeks)
    places = _place_rows(walked)
    notes = () if walked is None else tuple((place, note) for place, _club, note in walked.places)
    pairs = _pair_rows(walked)
    if walked is not None and owner_matches(walked.champion.owner, sheet_champion):
        return Title(
            year,
            walked.champion.name.strip(),
            walked.champion.owner,
            True,
            walk=detail,
            roster=roster,
            places=places,
            place_notes=notes,
            pairs=pairs,
            seeds=seeds,
            weeks=weeks,
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
            detail,
            roster,
            places,
            notes,
            pairs,
            seeds,
            weeks,
        )
    matched = _team_for_owner(teams, sheet_champion)
    if matched is None:
        return Title(year, "", "", False, walk=detail, roster=roster, seeds=seeds, weeks=weeks)
    return Title(
        year, matched[0], matched[1], True, walk=detail, roster=roster, seeds=seeds, weeks=weeks
    )


def season_checks(titles: dict[int, Title]) -> tuple[SeasonCheck, ...]:
    """Walk places beside the sheet for every season, newest first."""
    return tuple(_check_season(season, titles.get(season.year)) for season in SEASONS)


def _check_season(season: Season, title: Title | None) -> SeasonCheck:
    if title is None:
        rows = tuple(
            CheckRow(ordinal(index), "—", name, True, "ESPN did not return this season.")
            for index, name in enumerate(season.places, start=1)
            if name
        )
        line = "ESPN did not return this season."
        return SeasonCheck(
            season.year,
            f"{season.year} — ESPN did not return this season",
            len(rows),
            line,
            rows,
            (),
        )
    rows = _check_rows(season.places, title)
    count = sum(1 for row in rows if row.differs)
    if title.places or title.pairs:
        if count:
            word = "difference" if count == 1 else "differences"
            summary = f"{season.year} — {count} {word}"
        else:
            summary = f"{season.year} — walk matches the sheet"
    else:
        summary = f"{season.year} — could not follow the bracket"
    roster = tuple(
        (team, owner, sheet_name_for(owner) or "not linked") for team, owner in title.roster
    )
    return SeasonCheck(
        season.year,
        summary,
        count,
        title.walk or "No walk detail.",
        rows,
        roster,
        title.seeds,
        title.weeks,
    )


def _check_rows(sheet: tuple[str | None, ...], title: Title) -> tuple[CheckRow, ...]:
    notes = dict(title.place_notes)
    placed = {place: (team, owner) for place, team, owner in title.places}
    pair_at = {start: (end, people, reason) for start, end, people, reason in title.pairs}
    inside_pair: set[int] = set()
    for start, end, _people, _reason in title.pairs:
        inside_pair.update(range(start, end + 1))
    last = len(sheet)
    if placed:
        last = max(last, max(placed))
    if title.pairs:
        last = max(last, max(end for _start, end, _people, _reason in title.pairs))
    rows: list[CheckRow] = []
    place = 1
    while place <= last:
        if place in pair_at:
            end, people, reason = pair_at[place]
            rows.append(_pair_row(sheet, place, end, people, reason))
            place = end + 1
            continue
        if place in inside_pair:
            place += 1
            continue
        sheet_name = sheet[place - 1] if place <= len(sheet) else None
        row = _one_row(place, sheet_name, placed.get(place), notes.get(place, ""))
        if row is not None:
            rows.append(row)
        place += 1
    return tuple(rows)


def _one_row(
    place: int,
    sheet_name: str | None,
    walk: tuple[str, str] | None,
    note: str,
) -> CheckRow | None:
    label = ordinal(place)
    sheet_cell = sheet_name or "blank"
    if walk is None:
        if sheet_name is None:
            return None
        return CheckRow(label, "—", sheet_cell, True, "The walk did not assign this place.")
    team, owner = walk
    nick = sheet_name_for(owner)
    walk_cell = f"{nick} — {team}" if nick else f"{owner} — {team}"
    if nick is None:
        why = f"ESPN lists {owner} here, and that spelling is not linked to a sheet nickname."
        if sheet_name:
            why += f" The sheet has {sheet_name}."
        else:
            why += " The sheet left this place blank."
        return CheckRow(label, walk_cell, sheet_cell, True, why)
    if sheet_name is None:
        extra = f" {note}" if note else ""
        return CheckRow(
            label, walk_cell, sheet_cell, True, f"The sheet left this place blank.{extra}"
        )
    if nick == sheet_name:
        return CheckRow(label, walk_cell, sheet_cell, False, "")
    prefix = f"{note} " if note else ""
    return CheckRow(label, walk_cell, sheet_cell, True, f"{prefix}The sheet has {sheet_name}.")


def _pair_row(
    sheet: tuple[str | None, ...],
    start: int,
    end: int,
    people: tuple[tuple[str, str], tuple[str, str]],
    reason: str,
) -> CheckRow:
    labels: list[str] = []
    nicks: list[str] = []
    unlinked = False
    for team, owner in people:
        nick = sheet_name_for(owner)
        if nick:
            labels.append(f"{nick} — {team}")
            nicks.append(nick)
        else:
            labels.append(f"{owner} — {team}")
            unlinked = True
    slots = list(sheet[start - 1 : end])
    named = [name for name in slots if name]
    sheet_cell = ", ".join(named) if named else "blank"
    label = ordinal(start) if start == end else f"{ordinal(start)}–{ordinal(end)}"
    if unlinked:
        return CheckRow(
            label,
            " or ".join(labels),
            sheet_cell,
            True,
            f"{reason} One of these ESPN names is not linked to a sheet nickname.",
        )
    same_people = set(nicks) == set(named) and len(nicks) == len(named)
    if same_people and len(slots) == len(named):
        ordered = " then ".join(named)
        return CheckRow(
            label,
            " or ".join(labels),
            sheet_cell,
            True,
            f"{reason} The sheet lists {ordered}.",
        )
    return CheckRow(
        label,
        " or ".join(labels),
        sheet_cell,
        True,
        f"{reason} The sheet has {sheet_cell}.",
    )


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


def _place_rows(walked: _Walked | None) -> tuple[tuple[int, str, str], ...]:
    if walked is None:
        return ()
    return tuple((place, club.name.strip(), club.owner) for place, club, _note in walked.places)


def _pair_rows(walked: _Walked | None) -> tuple[PairRow, ...]:
    if walked is None:
        return ()
    rows: list[PairRow] = []
    for start, end, clubs, reason in walked.pairs:
        people = (
            (clubs[0].name.strip(), clubs[0].owner),
            (clubs[1].name.strip(), clubs[1].owner),
        )
        rows.append((start, end, people, reason))
    return tuple(rows)


def _team_for_owner(teams: list[Any], sheet_name: str) -> tuple[str, str] | None:
    for team in teams:
        owners = list(getattr(team, "owners", []) or [])
        named = owner_name(owners)
        if owner_matches(named, sheet_name) or owner_matches(_owner_text(owners), sheet_name):
            return str(team.team_name).strip(), named
    return None


def _last_counting_week(year: int) -> int:
    """Schedule index where the league stops. That NFL week counts for nothing.

    Index 0 is NFL week 1. Through 2020 the NFL had 17 weeks, so week 17 is
    ignored and week 16 is the last week of the league. From 2021 the NFL has
    18 weeks, so week 18 is ignored and week 17 is the last week.
    """
    return 17 if year >= 2021 else 16


def _walk(teams: list[Any], year: int, regular_season_weeks: int | None = None) -> _Walked | None:
    indexes, weeks = _played_weeks(teams, year)
    playoff, start = _playoff_window(indexes, weeks, year, len(teams), regular_season_weeks)
    if start is None or not playoff:
        return None
    if len(teams) >= 12 and len(playoff) >= TWELVE_TEAM_PLAYOFF_WEEKS:
        return _champion_twelve(teams, year, indexes, weeks, start)
    if len(teams) >= 10 and _ten_rounds(playoff) is not None:
        return _champion_ten(teams, year, indexes, weeks, start)
    return None


def _playoff_detail(
    teams: list[Any],
    year: int,
    walked: _Walked | None,
    regular_season_weeks: int | None = None,
) -> tuple[str, tuple[SeedLine, ...], tuple[WeekLine, ...]]:
    """Short reason, the standings table, and each playoff week."""
    if regular_season_weeks is None and year < 2019:
        return (
            "No bracket walk for this year. "
            "The walk covers 10-team seasons from 2012 on "
            "and the 12-team bracket from 2021 on. "
            "2011 has 8 teams, and that bracket is not written down yet.",
            (),
            (),
        )
    indexes, weeks = _played_weeks(teams, year)
    playoff, start = _playoff_window(indexes, weeks, year, len(teams), regular_season_weeks)
    if start is None:
        return ("ESPN did not return enough scored weeks to walk the bracket.", (), ())
    clubs = _clubs(teams, start, year)
    if len(teams) <= 8:
        return (
            "This season has 8 teams. The walk does not know that bracket yet.",
            _seed_lines(clubs, [], year),
            _week_lines(playoff, clubs),
        )
    rounds = playoff[:3] if len(teams) >= 12 else (_ten_rounds(playoff) or [])
    seeds = _twelve_seeds(clubs, year, rounds[0] if rounds else []) if len(teams) >= 12 else []
    if len(teams) < 12:
        seeds = winners_seeds(clubs, year, 4) if len(clubs) >= 4 else []
    text = _detail_text(clubs, year, rounds or playoff, walked, len(teams) >= 12)
    return text, _seed_lines(clubs, seeds, year), _week_lines(playoff, clubs)


def _weeks_from(indexes: list[int], weeks: list[list[Game]], start: int) -> list[list[Game]]:
    """Scored weeks whose schedule index is at or after the regular season."""
    return [week for index, week in zip(indexes, weeks, strict=True) if index >= start]


def _playoff_window(
    indexes: list[int],
    weeks: list[list[Game]],
    year: int,
    team_count: int,
    regular_season_weeks: int | None,
) -> tuple[list[list[Game]], int | None]:
    """Playoff weeks and the schedule index where the regular season ends."""
    if regular_season_weeks is not None:
        playoff = _weeks_from(indexes, weeks, regular_season_weeks)
        return playoff, regular_season_weeks
    if year < 2019:
        return [], None
    if team_count >= 12 or year >= 2021:
        if len(weeks) < TWELVE_TEAM_PLAYOFF_WEEKS:
            return [], None
        return weeks[-TWELVE_TEAM_PLAYOFF_WEEKS:], indexes[-TWELVE_TEAM_PLAYOFF_WEEKS]
    if len(weeks) < TEN_TEAM_SPAN:
        return [], None
    return weeks[-TEN_TEAM_SPAN:], indexes[-TEN_TEAM_SPAN]


def _ten_rounds(playoff: list[list[Game]]) -> list[list[Game]] | None:
    """Three rounds. Combine the last two weeks only when they are the same pairs."""
    if len(playoff) >= 4:
        combined = combine_weeks(playoff[2], playoff[3])
        if combined is not None:
            return [playoff[0], playoff[1], combined]
    if len(playoff) >= 3:
        return playoff[:3]
    return None


def _twelve_seeds(clubs: list[Club], year: int, first_week: list[Game]) -> list[Club]:
    """Winners' seeds. In 2025 the 6 seed is who actually played the 3 seed."""
    seeds = winners_seeds(clubs, year, 6)
    if year < 2025 or len(seeds) < 6 or not first_week:
        return seeds
    third = seeds[2]
    sixth = seeds[5]
    if game_between(first_week, third.team_id, sixth.team_id) is not None:
        return seeds
    top = {club.team_id for club in rank_clubs(clubs)[:5]}
    for game in first_week:
        pair = {game.home_id, game.away_id}
        if third.team_id not in pair:
            continue
        other_id = game.away_id if game.home_id == third.team_id else game.home_id
        if other_id in top:
            continue
        for club in clubs:
            if club.team_id == other_id:
                return seeds[:5] + [club]
    return seeds


def _points(value: float) -> str:
    return f"{value:.1f}"


def _record(club: Club) -> str:
    if club.ties:
        return f"{club.wins}-{club.losses}-{club.ties}"
    return f"{club.wins}-{club.losses}"


def _seed_lines(clubs: list[Club], seeds: list[Club], year: int) -> tuple[SeedLine, ...]:
    ranked = rank_clubs(clubs)
    rank_of = {club.team_id: index for index, club in enumerate(ranked, start=1)}
    seed_of = {club.team_id: index for index, club in enumerate(seeds, start=1)}
    points_sixth = None
    if year >= 2025 and len(ranked) > 5:
        rest = ranked[5:]
        points_sixth = max(rest, key=lambda club: (club.points_for, -rank_of[club.team_id]))
    ordered = list(seeds) + [club for club in ranked if club.team_id not in seed_of]
    rows: list[SeedLine] = []
    for club in ordered:
        number = seed_of.get(club.team_id)
        note = ""
        if points_sixth is not None and club.team_id == points_sixth.team_id:
            note = "most points outside the top 5"
        elif number == 6 and points_sixth is not None:
            note = f"played the 3 seed. Points leader was {person_label(points_sixth)}"
        rows.append(
            SeedLine(
                str(rank_of[club.team_id]),
                str(number) if number else "—",
                person_label(club),
                _record(club),
                _points(club.points_for),
                note,
            )
        )
    return tuple(rows)


def _week_lines(playoff: list[list[Game]], clubs: list[Club]) -> tuple[WeekLine, ...]:
    by_id = {club.team_id: club for club in clubs}
    rows: list[WeekLine] = []
    for index, games in enumerate(playoff, start=1):
        game_rows: list[GameLine] = []
        for game in games:
            home = by_id.get(game.home_id)
            away = by_id.get(game.away_id)
            game_rows.append(
                GameLine(
                    person_label(home) if home else str(game.home_id),
                    _points(game.home_score),
                    _points(game.away_score),
                    person_label(away) if away else str(game.away_id),
                )
            )
        rows.append(WeekLine(f"Playoff week {index}", tuple(game_rows)))
    return tuple(rows)


def _detail_text(
    clubs: list[Club],
    year: int,
    rounds: list[list[Game]],
    walked: _Walked | None,
    twelve: bool,
) -> str:
    if walked is not None:
        return f"Bracket champion: {person_label(walked.champion)}."
    if not rounds:
        return "Not enough playoff weeks came back to follow the bracket."
    if twelve:
        return _twelve_gap(clubs, year, rounds)
    return _ten_gap(clubs, year, rounds)


def _twelve_gap(clubs: list[Club], year: int, rounds: list[list[Game]]) -> str:
    seeds = _twelve_seeds(clubs, year, rounds[0] if rounds else [])
    winners = _winners_six_gap(seeds, rounds)
    if winners is not None:
        return winners
    taken = {club.team_id for club in seeds}
    loser_field = [club for club in rank_clubs(clubs) if club.team_id not in taken]
    return _losers_gap(loser_field, rounds)


def _ten_gap(clubs: list[Club], year: int, rounds: list[list[Game]]) -> str:
    seeds = winners_seeds(clubs, year, 4)
    winners = _winners_four_gap(seeds, rounds)
    if winners is not None:
        return winners
    return _losers_gap(losers_seeds(clubs, year, 4), rounds)


def _winners_six_gap(seeds: list[Club], rounds: list[list[Game]]) -> str | None:
    """The first winners'-bracket step that did not happen. None when it resolves."""
    if len(seeds) != 6 or len(rounds) < 3:
        return "The winners' bracket needs six seeds and three rounds."
    first, second, third, fourth, fifth, sixth = seeds
    low = game_between(rounds[0], third.team_id, sixth.team_id)
    high = game_between(rounds[0], fourth.team_id, fifth.team_id)
    if low is None:
        return (
            f"To follow the bracket, {person_label(third)} (3rd in the regular season) "
            f"has to play {person_label(sixth)} (6th, {_points(sixth.points_for)} points) "
            "in the first playoff week. They did not play, so the walk has no places."
        )
    if high is None:
        return (
            f"To follow the bracket, {person_label(fourth)} (4th in the regular season) "
            f"has to play {person_label(fifth)} (5th, {_points(fifth.points_for)} points) "
            "in the first playoff week. "
            "They did not play, so the walk has no places."
        )
    low_winner = winner_id(low)
    high_winner = winner_id(high)
    if low_winner is None:
        return (
            f"3rd seed {person_label(third)} and 6th seed {person_label(sixth)} tied, "
            "so nobody advanced."
        )
    if high_winner is None:
        return (
            f"4th seed {person_label(fourth)} and 5th seed {person_label(fifth)} tied, "
            "so nobody advanced."
        )
    semi_one = game_between(rounds[1], first.team_id, high_winner)
    semi_two = game_between(rounds[1], second.team_id, low_winner)
    if semi_one is None:
        return (
            f"In the second playoff week, {person_label(first)} (1st in the regular season) "
            f"has to play {person_label(_club(seeds, high_winner))}. "
            "They did not play, so the walk has no places."
        )
    if semi_two is None:
        return (
            f"In the second playoff week, {person_label(second)} (2nd in the regular season) "
            f"has to play {person_label(_club(seeds, low_winner))}. "
            "They did not play, so the walk has no places."
        )
    finalist_one = winner_id(semi_one)
    finalist_two = winner_id(semi_two)
    if finalist_one is None:
        return (
            f"The semifinal between {person_label(first)} and "
            f"{person_label(_club(seeds, high_winner))} tied."
        )
    if finalist_two is None:
        return (
            f"The semifinal between {person_label(second)} and "
            f"{person_label(_club(seeds, low_winner))} tied."
        )
    final = game_between(rounds[2], finalist_one, finalist_two)
    if final is None:
        return (
            "In the last playoff week, "
            f"{person_label(_club(seeds, finalist_one))} has to play "
            f"{person_label(_club(seeds, finalist_two))} for the title. "
            "They did not play, so the walk has no places."
        )
    if winner_id(final) is None:
        return "The final tied."
    return None


def _winners_four_gap(seeds: list[Club], rounds: list[list[Game]]) -> str | None:
    if len(seeds) != 4 or len(rounds) < 2:
        return "The winners' bracket needs four seeds and two rounds."
    one, two, three, four = seeds
    high = game_between(rounds[0], one.team_id, four.team_id)
    low = game_between(rounds[0], two.team_id, three.team_id)
    if high is None:
        return (
            f"To follow the bracket, {person_label(one)} (1st in the regular season) "
            f"has to play {person_label(four)} (4th) in the first playoff week. "
            "They did not play, so the walk has no places."
        )
    if low is None:
        return (
            f"To follow the bracket, {person_label(two)} (2nd in the regular season) "
            f"has to play {person_label(three)} (3rd) in the first playoff week. "
            "They did not play, so the walk has no places."
        )
    if winner_id(high) is None:
        return f"{person_label(one)} and {person_label(four)} tied, so nobody advanced."
    if winner_id(low) is None:
        return f"{person_label(two)} and {person_label(three)} tied, so nobody advanced."
    final = game_between(rounds[1], winner_id(high) or 0, winner_id(low) or 0)
    third = game_between(rounds[1], loser_id(high) or 0, loser_id(low) or 0)
    if final is None:
        return "The second playoff week does not have the final."
    if third is None:
        return "The second playoff week does not have the third-place game."
    if winner_id(final) is None:
        return "The final tied."
    if winner_id(third) is None:
        return "The third-place game tied."
    return None


def _losers_gap(seeds: list[Club], rounds: list[list[Game]]) -> str:
    if len(seeds) != 6 or len(rounds) < 3:
        return "The losers' bracket needs six teams and three rounds."
    one, two, three, four, five, six = seeds
    expected = ((one, six), (two, five), (three, four))
    opening: list[Game] = []
    for left, right in expected:
        game = game_between(rounds[0], left.team_id, right.team_id)
        if game is None:
            return (
                f"On the losers' side, {person_label(left)} has to play {person_label(right)} "
                "in the first playoff week. They did not play, so the walk has no places."
            )
        if winner_id(game) is None:
            return f"{person_label(left)} and {person_label(right)} tied in the losers' bracket."
        opening.append(game)
    won = [_club(seeds, winner_id(game) or 0) for game in opening]
    lost = [_club(seeds, loser_id(game) or 0) for game in opening]

    def seed_of(club: Club) -> int:
        return next(index for index, seed in enumerate(seeds) if seed.team_id == club.team_id)

    bye = min(won, key=seed_of)
    sacko_bye = max(lost, key=seed_of)
    other_winners = [club for club in won if club.team_id != bye.team_id]
    other_losers = [club for club in lost if club.team_id != sacko_bye.team_id]
    middle_winners = game_between(rounds[1], other_winners[0].team_id, other_winners[1].team_id)
    middle_losers = game_between(rounds[1], other_losers[0].team_id, other_losers[1].team_id)
    if middle_winners is None:
        return (
            "The second playoff week does not have the winners' game of the losers' bracket, "
            f"{person_label(other_winners[0])} against {person_label(other_winners[1])}."
        )
    if middle_losers is None:
        return (
            "The second playoff week does not have the consolation game of the losers' bracket, "
            f"{person_label(other_losers[0])} against {person_label(other_losers[1])}."
        )
    if winner_id(middle_winners) is None or winner_id(middle_losers) is None:
        return "A losers'-bracket game in the second playoff week tied."
    final = game_between(rounds[2], bye.team_id, winner_id(middle_winners) or 0)
    sacko = game_between(rounds[2], sacko_bye.team_id, loser_id(middle_losers) or 0)
    if final is None:
        return (
            "The last playoff week does not have the losers' final, "
            f"{person_label(bye)} against {person_label(_club(seeds, winner_id(middle_winners) or 0))}."
        )
    if sacko is None:
        return (
            "The last playoff week does not have the Sacko game, "
            f"{person_label(sacko_bye)} against "
            f"{person_label(_club(seeds, loser_id(middle_losers) or 0))}."
        )
    if winner_id(final) is None or winner_id(sacko) is None:
        return "The losers' final or the Sacko game tied."
    return "The games match the bracket, but the walk still did not keep a result."


def _club(seeds: list[Club], team_id: int) -> Club:
    for club in seeds:
        if club.team_id == team_id:
            return club
    raise KeyError(team_id)


def _played_weeks(teams: list[Any], year: int) -> tuple[list[int], list[list[Game]]]:
    """Finished weeks inside the league. The last NFL week is left out."""
    count = min(len(team.outcomes) for team in teams)
    end = _last_counting_week(year)
    indexes: list[int] = []
    weeks: list[list[Game]] = []
    for index in range(min(count, end)):
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


def _score_bonus(teams: list[Any], end: int) -> dict[int, tuple[int, int]]:
    """Extra win or loss each week. The six highest scores win, the other six lose.

    This is the second matchup in a 12-team season. Points are not added again.
    A score tied with 6th place also wins.
    """
    bonus = {team.team_id: (0, 0) for team in teams}
    if len(teams) < 12:
        return bonus
    wins = {team.team_id: 0 for team in teams}
    losses = {team.team_id: 0 for team in teams}
    for index in range(end):
        played: list[tuple[int, float]] = []
        for team in teams:
            opponent = team.schedule[index]
            if getattr(opponent, "team_id", None) in (None, team.team_id):
                continue
            if team.outcomes[index] not in ("W", "L", "T"):
                continue
            played.append((team.team_id, float(team.scores[index] or 0)))
        if len(played) < 12:
            continue
        played.sort(key=lambda item: (-item[1], item[0]))
        cutoff = played[5][1]
        for team_id, score in played:
            if score >= cutoff:
                wins[team_id] += 1
            else:
                losses[team_id] += 1
    return {team_id: (wins[team_id], losses[team_id]) for team_id in wins}


def _clubs(teams: list[Any], through: int, year: int) -> list[Club]:
    """Wins and points before the playoffs, and never from the last NFL week."""
    end = min(through, _last_counting_week(year))
    bonus = _score_bonus(teams, end)
    clubs: list[Club] = []
    for team in teams:
        wins, losses = bonus[team.team_id]
        ties = 0
        points = 0.0
        for index in range(end):
            opponent = team.schedule[index]
            if getattr(opponent, "team_id", None) in (None, team.team_id):
                continue
            points += float(team.scores[index] or 0)
            outcome = team.outcomes[index]
            if outcome == "W":
                wins += 1
            elif outcome == "L":
                losses += 1
            elif outcome == "T":
                ties += 1
        clubs.append(
            Club(
                team.team_id,
                str(team.team_name),
                owner_name(list(team.owners or [])),
                wins,
                points,
                losses,
                ties,
            )
        )
    return clubs


def _champion_twelve(
    teams: list[Any],
    year: int,
    indexes: list[int],
    weeks: list[list[Game]],
    start: int | None = None,
) -> _Walked | None:
    if start is None:
        playoff_all = weeks[-TWELVE_TEAM_PLAYOFF_WEEKS:]
        clubs = _clubs(teams, indexes[-TWELVE_TEAM_PLAYOFF_WEEKS], year)
    else:
        playoff_all = _weeks_from(indexes, weeks, start)
        clubs = _clubs(teams, start, year)
    if len(playoff_all) < TWELVE_TEAM_PLAYOFF_WEEKS:
        return None
    playoff = playoff_all[:TWELVE_TEAM_PLAYOFF_WEEKS]
    seeds = _twelve_seeds(clubs, year, playoff[0])
    result = winners_six(seeds, playoff)
    if result is None:
        return None
    taken = {club.team_id for club in seeds}
    loser_field = [club for club in rank_clubs(clubs) if club.team_id not in taken]
    losers = losers_six(loser_field, playoff)
    if losers is None:
        return None
    champion_club, runner, semi_one, semi_two = result
    places: list[tuple[int, Club, str]] = [
        (1, champion_club, f"Won the final against {person_label(runner)}."),
        (2, runner, f"Lost the final to {person_label(champion_club)}."),
    ]
    third = game_between(playoff[2], semi_one.team_id, semi_two.team_id)
    pairs: list[tuple[int, int, tuple[Club, Club], str]] = []
    if third is not None and winner_id(third) is not None:
        by_id = {club.team_id: club for club in seeds}
        third_winner = by_id[winner_id(third) or 0]
        third_loser = by_id[loser_id(third) or 0]
        places.append(
            (3, third_winner, f"Won the third-place game against {person_label(third_loser)}.")
        )
        places.append(
            (4, third_loser, f"Lost the third-place game to {person_label(third_winner)}.")
        )
    else:
        pairs.append(
            (
                3,
                4,
                (semi_one, semi_two),
                "These two lost a semifinal and did not play a third-place game, "
                "so the walk does not rank one above the other.",
            )
        )
    first_low = game_between(playoff[0], seeds[2].team_id, seeds[5].team_id)
    first_high = game_between(playoff[0], seeds[3].team_id, seeds[4].team_id)
    if (
        first_low is not None
        and first_high is not None
        and loser_id(first_low)
        and loser_id(first_high)
    ):
        pairs.append(
            (
                5,
                6,
                (_club(seeds, loser_id(first_low) or 0), _club(seeds, loser_id(first_high) or 0)),
                "These two lost in the first round and did not play each other, "
                "so the walk does not rank one above the other.",
            )
        )
    places.extend(
        (6 + index, placed.club, placed.reason) for index, placed in enumerate(losers, start=1)
    )
    return _Walked(champion_club, tuple(places), tuple(pairs))


def _champion_ten(
    teams: list[Any],
    year: int,
    indexes: list[int],
    weeks: list[list[Game]],
    start: int | None = None,
) -> _Walked | None:
    if start is None:
        playoff = weeks[-TEN_TEAM_SPAN:]
        clubs = _clubs(teams, indexes[-TEN_TEAM_SPAN], year)
    else:
        playoff = _weeks_from(indexes, weeks, start)
        clubs = _clubs(teams, start, year)
    rounds = _ten_rounds(playoff)
    if rounds is None:
        return None
    seeds = winners_seeds(clubs, year, 4)
    result = winners_four(seeds, rounds)
    if result is None:
        return None
    losers = losers_six(losers_seeds(clubs, year, 4), rounds)
    if losers is None:
        return None
    labels = (
        "Won the final.",
        "Lost the final.",
        "Won the third-place game.",
        "Lost the third-place game.",
    )
    places = [(index, club, labels[index - 1]) for index, club in enumerate(result, start=1)]
    places.extend(
        (4 + index, placed.club, placed.reason) for index, placed in enumerate(losers, start=1)
    )
    return _Walked(result[0], tuple(places), ())
