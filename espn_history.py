"""Championships from ESPN matchups, checked against the sheet.

The running app already has the ESPN cookies. This asks each past season for
its teams and weekly scores, then applies the bracket. A team name is engraved
only when that result is the same person the sheet lists as champion.

The walk also orders every place, which is how the sheet's blank 2012-2018
middle places were filled in.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from typing import Any

from espn_api.football import League

from bracket import (
    BracketGame,
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
from league_history import champion, sheet_name_for
from league_stats import (
    GameRecord,
    SeasonRecord,
    TeamRecord,
    WeekScores,
    record_from_dict,
    record_to_dict,
)

logger = logging.getLogger(__name__)

# 12-team winners' side is three one-week rounds. 10-team winners' side is two
# one-week rounds, and the losers' final is the two weeks after that.
TWELVE_TEAM_PLAYOFF_WEEKS = 3
TEN_TEAM_SPAN = 4

# (start place, end place, ((team, owner), (team, owner)), reason)
PairRow = tuple[int, int, tuple[tuple[str, str], tuple[str, str]], str]

# team id -> NFL week -> points that week
WeeklyPoints = dict[int, dict[int, float]]


@dataclass(frozen=True)
class Title:
    """One season's champion, plus the places the bracket walk found."""

    year: int
    team_name: str
    owner: str
    agrees: bool
    places: tuple[tuple[int, str, str], ...] = ()
    place_notes: tuple[tuple[int, str], ...] = ()
    pairs: tuple[PairRow, ...] = ()


@dataclass(frozen=True)
class _Walked:
    champion: Club
    places: tuple[tuple[int, Club, str], ...]
    pairs: tuple[tuple[int, int, tuple[Club, Club], str], ...]
    games: tuple[BracketGame, ...] = ()
    seeds: tuple[int, ...] = ()


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


def load_season(
    league_id: int, espn_s2: str, swid: str, year: int
) -> tuple[Title | None, SeasonRecord | None]:
    """One season from ESPN: the plaque title and the season's games."""
    try:
        league = League(league_id=league_id, year=year, espn_s2=espn_s2, swid=swid)
        regular = getattr(getattr(league, "settings", None), "reg_season_count", None)
        weekly = _weekly_points(league) if len(league.teams) < 12 else {}
        return read_history(league.teams, year, champion(year), regular, weekly)
    except Exception as exc:
        logger.warning("ESPN history %s failed: %s", year, exc)
        return None, None


def read_history(
    teams: list[Any],
    year: int,
    sheet_champion: str | None,
    regular_season_weeks: int | None = None,
    weekly: WeeklyPoints | None = None,
) -> tuple[Title | None, SeasonRecord | None]:
    if not teams:
        return None, None
    walked = _walk(teams, year, regular_season_weeks, weekly)
    title = _title(teams, year, sheet_champion, walked)
    return title, _season_record(teams, year, regular_season_weeks, walked)


def read_season(
    teams: list[Any],
    year: int,
    sheet_champion: str | None,
    regular_season_weeks: int | None = None,
    weekly: WeeklyPoints | None = None,
) -> Title | None:
    """Team name for the sheet champion, using the bracket when this year has one."""
    if not teams:
        return None
    return _title(teams, year, sheet_champion, _walk(teams, year, regular_season_weeks, weekly))


def _title(
    teams: list[Any], year: int, sheet_champion: str | None, walked: _Walked | None
) -> Title | None:
    places = _place_rows(walked)
    notes = () if walked is None else tuple((place, note) for place, _club, note in walked.places)
    pairs = _pair_rows(walked)
    if walked is not None:
        # A season the sheet doesn't have yet is the replay's alone.
        agrees = not sheet_champion or owner_matches(walked.champion.owner, sheet_champion)
        team_name = walked.champion.name.strip() if agrees else ""
        return Title(year, team_name, walked.champion.owner, agrees, places, notes, pairs)
    if not sheet_champion:
        return None
    matched = _team_for_owner(teams, sheet_champion)
    if matched is None:
        return Title(year, "", "", False)
    return Title(year, matched[0], matched[1], True)


def _person(team: Any) -> str:
    owners = list(getattr(team, "owners", []) or [])
    return sheet_name_for(_owner_text(owners)) or owner_name(owners) or str(team.team_name)


def _season_record(
    teams: list[Any], year: int, regular_season_weeks: int | None, walked: _Walked | None
) -> SeasonRecord:
    """Every game ESPN has for the season, with playoff games tagged by bracket side."""
    indexes, weeks = _played_weeks(teams, year)
    _playoff, start = _playoff_window(indexes, weeks, year, len(teams), regular_season_weeks)
    if start is None:
        start = (indexes[-1] + 1) if indexes else 0
    clubs = _clubs(teams, start, year)
    if walked is not None:
        seed_ids = walked.seeds
    else:
        seed_ids = tuple(
            club.team_id for club in winners_seeds(clubs, year, 6 if len(teams) >= 12 else 4)
        )
    seed_of = {team_id: index for index, team_id in enumerate(seed_ids, start=1)}
    team_rows = tuple(
        TeamRecord(
            club.team_id,
            club.name.strip(),
            _person(next(team for team in teams if team.team_id == club.team_id)),
            club.wins,
            club.losses,
            club.ties,
            round(club.points_for, 2),
            seed_of.get(club.team_id),
        )
        for club in clubs
    )
    games: list[GameRecord] = []
    week_rows: list[WeekScores] = []
    for index, week in zip(indexes, weeks, strict=True):
        if index >= start:
            continue
        for game in week:
            games.append(
                GameRecord(
                    "regular",
                    f"Week {index + 1}",
                    game.home_id,
                    game.away_id,
                    game.home_score,
                    game.away_score,
                )
            )
        scores = tuple(
            (team.team_id, float(team.scores[index] or 0))
            for team in teams
            if getattr(team.schedule[index], "team_id", None) not in (None, team.team_id)
            and team.outcomes[index] in ("W", "L", "T")
        )
        week_rows.append(WeekScores(index + 1, scores))
    if walked is not None:
        playoff_games = [
            GameRecord(
                item.side,
                item.label,
                item.game.home_id,
                item.game.away_id,
                round(item.game.home_score, 2),
                round(item.game.away_score, 2),
            )
            for item in walked.games
        ]
    else:
        seeded = set(seed_ids)
        playoff_games = [
            GameRecord(
                "winners" if {game.home_id, game.away_id} <= seeded else "losers",
                f"Week {index + 1}",
                game.home_id,
                game.away_id,
                game.home_score,
                game.away_score,
            )
            for index, week in zip(indexes, weeks, strict=True)
            if index >= start
            for game in week
        ]
    return SeasonRecord(year, team_rows, tuple(games + playoff_games), tuple(week_rows))


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


def _weekly_points(league: Any) -> WeeklyPoints:
    """Each team's points by NFL week, including the weeks inside two-week games."""
    try:
        data = league.espn_request.league_get(params={"view": ["mMatchup", "mMatchupScore"]})
    except Exception as exc:
        logger.warning("ESPN weekly points %s failed: %s", getattr(league, "year", "?"), exc)
        return {}
    points: WeeklyPoints = {}
    for item in data.get("schedule", []) or []:
        for side in ("home", "away"):
            entry = item.get(side) or {}
            team_id = entry.get("teamId")
            if team_id is None:
                continue
            for period, value in (entry.get("pointsByScoringPeriod") or {}).items():
                points.setdefault(int(team_id), {})[int(period)] = float(value)
    return points


def _two_week_rounds(teams: list[Any], playoff: list[list[Game]]) -> bool:
    """10-team years where ESPN stores each playoff round as two weeks added together."""
    return 10 <= len(teams) < 12 and len(playoff) == 2


def _losers_weeks(field: list[Club], weekly: WeeklyPoints, start: int) -> list[list[Game]] | None:
    """Losers' bracket rounds from single weeks: one week, one week, then two weeks.

    ESPN pairs these teams its own way inside the two-week games, so every
    pairing is built from the weekly points and the bracket picks the ones it needs.
    """
    weeks = [start + 1, start + 2, start + 3, start + 4]
    scores: list[dict[int, float]] = [{}, {}, {}]
    for club in field:
        by_week = weekly.get(club.team_id, {})
        if any(week not in by_week for week in weeks):
            return None
        scores[0][club.team_id] = by_week[weeks[0]]
        scores[1][club.team_id] = by_week[weeks[1]]
        scores[2][club.team_id] = by_week[weeks[2]] + by_week[weeks[3]]
    rounds: list[list[Game]] = []
    for round_scores in scores:
        games = [
            Game(
                left.team_id, right.team_id, round_scores[left.team_id], round_scores[right.team_id]
            )
            for index, left in enumerate(field)
            for right in field[index + 1 :]
        ]
        rounds.append(games)
    return rounds


def _champion_ten_split(
    teams: list[Any],
    year: int,
    playoff: list[list[Game]],
    start: int,
    weekly: WeeklyPoints,
) -> _Walked | None:
    clubs = _clubs(teams, start, year)
    seeds = winners_seeds(clubs, year, 4)
    played: list[BracketGame] = []
    result = winners_four(seeds, playoff, played)
    if result is None:
        return None
    field = losers_seeds(clubs, year, 4)
    rounds = _losers_weeks(field, weekly, start)
    if rounds is None:
        return None
    losers = losers_six(field, rounds, middle_place="7th", played=played)
    if losers is None:
        return None
    games = tuple(
        item if item.side == "losers" and item.label.startswith("Round") else _two_weeks(item)
        for item in played
    )
    labels = (
        "Won the two-week final.",
        "Lost the two-week final.",
        "Won the two-week third-place game.",
        "Lost the two-week third-place game.",
    )
    places = [(index, club, labels[index - 1]) for index, club in enumerate(result, start=1)]
    places.extend(
        (4 + index, placed.club, placed.reason) for index, placed in enumerate(losers, start=1)
    )
    return _Walked(result[0], tuple(places), (), games, tuple(club.team_id for club in seeds))


def _two_weeks(item: BracketGame) -> BracketGame:
    return BracketGame(item.side, f"{item.label} (2 weeks)", item.game)


def _walk(
    teams: list[Any],
    year: int,
    regular_season_weeks: int | None = None,
    weekly: WeeklyPoints | None = None,
) -> _Walked | None:
    indexes, weeks = _played_weeks(teams, year)
    playoff, start = _playoff_window(indexes, weeks, year, len(teams), regular_season_weeks)
    if start is None or not playoff:
        return None
    if len(teams) >= 12 and len(playoff) >= TWELVE_TEAM_PLAYOFF_WEEKS:
        return _champion_twelve(teams, year, indexes, weeks, start)
    if _two_week_rounds(teams, playoff):
        return _champion_ten_split(teams, year, playoff, start, weekly or {})
    if len(teams) >= 10 and _ten_rounds(playoff) is not None:
        return _champion_ten(teams, year, indexes, weeks, start)
    return None


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


def _reseeds(year: int) -> bool:
    """From 2023 the winners' bracket reseeds after the first playoff week.

    2022 used the fixed bracket. 2023 and 2024 give the same games either way,
    and 2025 only fits the reseeded bracket.
    """
    return year >= 2023


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


def _score_bonus(teams: list[Any], end: int, year: int) -> dict[int, tuple[int, int]]:
    """Extra win or loss each week. The six highest scores win, the other six lose.

    This second matchup starts in 2023. Points are not added again.
    A score tied with 6th place also wins.
    """
    bonus = {team.team_id: (0, 0) for team in teams}
    if year < 2023 or len(teams) < 12:
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
    bonus = _score_bonus(teams, end, year)
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


def _two_week_game(first: list[Game], second: list[Game], pair: tuple[Club, Club]) -> Game | None:
    """Both weeks between the pair, added together. None unless they met both weeks."""
    one, two = pair
    games = [game_between(week, one.team_id, two.team_id) for week in (first, second)]
    if any(game is None for game in games):
        return None
    home = 0.0
    away = 0.0
    for game in games:
        if game is None:
            return None
        if game.home_id == one.team_id:
            home += game.home_score
            away += game.away_score
        else:
            home += game.away_score
            away += game.home_score
    return Game(one.team_id, two.team_id, home, away)


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
    played: list[BracketGame] = []
    result = winners_six(seeds, playoff, _reseeds(year), played)
    if result is None:
        return None
    taken = {club.team_id for club in seeds}
    loser_field = [club for club in rank_clubs(clubs) if club.team_id not in taken]
    losers_played: list[BracketGame] = []
    losers = losers_six(loser_field, playoff, played=losers_played)
    if losers is None:
        return None
    champion_club, runner, semi_one, semi_two = result
    places: list[tuple[int, Club, str]] = [
        (1, champion_club, f"Won the final against {person_label(runner)}."),
        (2, runner, f"Lost the final to {person_label(champion_club)}."),
    ]
    third = game_between(playoff[2], semi_one.team_id, semi_two.team_id)
    pairs: list[tuple[int, int, tuple[Club, Club], str]] = []
    if third is not None:
        played.append(BracketGame("winners", "3rd place", third))
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
        fifth_pair = (
            _club(seeds, loser_id(first_low) or 0),
            _club(seeds, loser_id(first_high) or 0),
        )
        fifth_game = _two_week_game(playoff[1], playoff[2], fifth_pair)
        if fifth_game is not None:
            played.append(BracketGame("winners", "5th place (2 weeks)", fifth_game))
        if fifth_game is not None and winner_id(fifth_game) is not None:
            fifth_winner = _club(seeds, winner_id(fifth_game) or 0)
            fifth_loser = _club(seeds, loser_id(fifth_game) or 0)
            score = f"{_points(max(fifth_game.home_score, fifth_game.away_score))}"
            other = f"{_points(min(fifth_game.home_score, fifth_game.away_score))}"
            places.append(
                (
                    5,
                    fifth_winner,
                    f"Won the two-week 5th-place game against {person_label(fifth_loser)}, "
                    f"{score} to {other}.",
                )
            )
            places.append(
                (
                    6,
                    fifth_loser,
                    f"Lost the two-week 5th-place game to {person_label(fifth_winner)}, "
                    f"{other} to {score}.",
                )
            )
        else:
            pairs.append(
                (
                    5,
                    6,
                    fifth_pair,
                    "These two lost in the first round and did not play each other "
                    "in the next two weeks, so the walk does not rank one above the other.",
                )
            )
    places.extend(
        (6 + index, placed.club, placed.reason) for index, placed in enumerate(losers, start=1)
    )
    return _Walked(
        champion_club,
        tuple(places),
        tuple(pairs),
        tuple(played + losers_played),
        tuple(club.team_id for club in seeds),
    )


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
    played: list[BracketGame] = []
    result = winners_four(seeds, rounds, played)
    if result is None:
        return None
    losers = losers_six(losers_seeds(clubs, year, 4), rounds, played=played)
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
    return _Walked(result[0], tuple(places), (), tuple(played), tuple(c.team_id for c in seeds))


def dump_snapshot(titles: dict[int, Title], records: dict[int, SeasonRecord]) -> str:
    """Finished seasons as JSON, so they can be read back without asking ESPN."""
    years = sorted(set(titles) | set(records))
    payload = [
        {
            "year": year,
            "title": asdict(titles[year]) if year in titles else None,
            "record": record_to_dict(records[year]) if year in records else None,
        }
        for year in years
    ]
    return json.dumps(payload, indent=1, sort_keys=True)


def load_snapshot(text: str) -> tuple[dict[int, Title], dict[int, SeasonRecord]]:
    titles: dict[int, Title] = {}
    records: dict[int, SeasonRecord] = {}
    for item in json.loads(text):
        year = int(item["year"])
        if item.get("title"):
            titles[year] = _title_from_dict(item["title"])
        if item.get("record"):
            records[year] = record_from_dict(item["record"])
    return titles, records


def _title_from_dict(data: dict[str, Any]) -> Title:
    return Title(
        int(data["year"]),
        str(data["team_name"]),
        str(data["owner"]),
        bool(data["agrees"]),
        tuple((int(place), str(team), str(owner)) for place, team, owner in data["places"]),
        tuple((int(place), str(note)) for place, note in data["place_notes"]),
        tuple(
            (
                int(start),
                int(end),
                ((str(one[0]), str(one[1])), (str(two[0]), str(two[1]))),
                str(reason),
            )
            for start, end, (one, two), reason in data["pairs"]
        ),
    )
