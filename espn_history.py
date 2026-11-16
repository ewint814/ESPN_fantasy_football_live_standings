"""Championships from ESPN matchups, checked against the sheet.

The running app already has the ESPN cookies. This asks each past season for
its teams and weekly scores, then applies the bracket. A team name is engraved
only when that result is the same person the sheet lists as champion.

The history page also gets a place-by-place check: the walk's order, the
sheet's order, and a note on each row where those are not the same person.
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
    person_label,
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


@dataclass(frozen=True)
class _Walked:
    champion: Club
    places: tuple[tuple[int, Club, str], ...]
    pairs: tuple[tuple[int, int, tuple[Club, Club], str], ...]


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
    detail = _playoff_detail(teams, year, walked)
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
        )
    matched = _team_for_owner(teams, sheet_champion)
    if matched is None:
        return Title(year, "", "", False, walk=detail, roster=roster)
    return Title(year, matched[0], matched[1], True, walk=detail, roster=roster)


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
    return SeasonCheck(season.year, summary, count, title.walk or "No walk detail.", rows, roster)


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


def _walk(teams: list[Any], year: int) -> _Walked | None:
    indexes, weeks = _played_weeks(teams)
    if year >= 2021 and len(weeks) >= TWELVE_TEAM_PLAYOFF_WEEKS:
        return _champion_twelve(teams, year, indexes, weeks)
    if year in (2019, 2020) and len(weeks) >= TEN_TEAM_SPAN:
        return _champion_ten(teams, year, indexes, weeks)
    return None


def _playoff_detail(teams: list[Any], year: int, walked: _Walked | None) -> str:
    """Seeds, the games in the playoff weeks, and why a walk stopped."""
    if year < 2019:
        return (
            "No bracket walk for this year. "
            "The walk covers the 10-team bracket in 2019 and 2020 "
            "and the 12-team bracket from 2021 on."
        )
    indexes, weeks = _played_weeks(teams)
    if year >= 2021:
        if len(weeks) < TWELVE_TEAM_PLAYOFF_WEEKS:
            return (
                f"ESPN returned {len(weeks)} scored weeks. The 12-team walk needs the last three."
            )
        return _detail_twelve(teams, year, indexes, weeks, walked)
    if len(weeks) < TEN_TEAM_SPAN:
        return f"ESPN returned {len(weeks)} scored weeks. The 10-team walk needs the last four."
    return _detail_ten(teams, year, indexes, weeks, walked)


def _detail_twelve(
    teams: list[Any],
    year: int,
    indexes: list[int],
    weeks: list[list[Game]],
    walked: _Walked | None,
) -> str:
    playoff = weeks[-TWELVE_TEAM_PLAYOFF_WEEKS:]
    clubs = _clubs(teams, indexes[-TWELVE_TEAM_PLAYOFF_WEEKS])
    lines = [
        "The walk uses the last three weeks that had scores and tries to replay the playoffs.",
        *_seed_and_weeks(clubs, year, 6, playoff),
    ]
    if walked is None:
        lines.append(_twelve_gap(clubs, year, playoff))
    else:
        lines.insert(0, f"Bracket champion: {person_label(walked.champion)}.")
    return "\n".join(lines)


def _detail_ten(
    teams: list[Any],
    year: int,
    indexes: list[int],
    weeks: list[list[Game]],
    walked: _Walked | None,
) -> str:
    tail = weeks[-TEN_TEAM_SPAN:]
    clubs = _clubs(teams, indexes[-TEN_TEAM_SPAN])
    lines = [
        "The walk uses the last four weeks that had scores and tries to replay the playoffs.",
        *_seed_and_weeks(clubs, year, 4, tail),
    ]
    combined = combine_weeks(tail[2], tail[3])
    if combined is None:
        lines.append(
            "The last two weeks are not the same matchups, "
            "so they do not add up to one two-week round."
        )
        return "\n".join(lines)
    if walked is None:
        lines.append(_ten_gap(clubs, year, [tail[0], tail[1], combined]))
    else:
        lines.insert(0, f"Bracket champion: {person_label(walked.champion)}.")
    return "\n".join(lines)


def _seed_and_weeks(clubs: list[Club], year: int, count: int, weeks: list[list[Game]]) -> list[str]:
    seeds = winners_seeds(clubs, year, count)
    by_id = {club.team_id: club for club in clubs}
    seed_list = ", ".join(
        f"{index} {person_label(club)}" for index, club in enumerate(seeds, start=1)
    )
    lines = [f"Regular-season order: {seed_list}."]
    for index, games in enumerate(weeks, start=1):
        lines.append(f"Week {index} of the weeks the walk checked: {_games_text(games, by_id)}.")
    return lines


def _games_text(games: list[Game], by_id: dict[int, Club]) -> str:
    if not games:
        return "no games"
    parts: list[str] = []
    for game in games:
        home = by_id.get(game.home_id)
        away = by_id.get(game.away_id)
        home_name = person_label(home) if home else str(game.home_id)
        away_name = person_label(away) if away else str(game.away_id)
        parts.append(f"{home_name} {game.home_score:.1f}–{game.away_score:.1f} {away_name}")
    return "; ".join(parts)


def _twelve_gap(clubs: list[Club], year: int, rounds: list[list[Game]]) -> str:
    seeds = winners_seeds(clubs, year, 6)
    winners = _winners_six_gap(seeds, rounds)
    if winners is not None:
        return winners
    return _losers_gap(losers_seeds(clubs, year, 6), rounds)


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
            f"has to play {person_label(sixth)} (6th) in week 1 of those. "
            "They did not play, so the walk has no places."
        )
    if high is None:
        return (
            f"To follow the bracket, {person_label(fourth)} (4th in the regular season) "
            f"has to play {person_label(fifth)} (5th) in week 1 of those. "
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
            f"In week 2 of those, {person_label(first)} (1st in the regular season) "
            f"has to play {person_label(_club(seeds, high_winner))}. "
            "They did not play, so the walk has no places."
        )
    if semi_two is None:
        return (
            f"In week 2 of those, {person_label(second)} (2nd in the regular season) "
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
            "In the last of those weeks, "
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
            f"has to play {person_label(four)} (4th) in week 1 of those. "
            "They did not play, so the walk has no places."
        )
    if low is None:
        return (
            f"To follow the bracket, {person_label(two)} (2nd in the regular season) "
            f"has to play {person_label(three)} (3rd) in week 1 of those. "
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
                "in week 1 of those. They did not play, so the walk has no places."
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
