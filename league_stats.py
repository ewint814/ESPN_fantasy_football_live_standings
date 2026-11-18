"""League stats from every season's games: head-to-head, weekly highs and lows,
careers, records, and each season's bracket.

A SeasonRecord is one season as ESPN played it, with the playoff games the
bracket walk used. Finishes, titles, and Sackos come from the league sheet.
Records are plain data so past seasons can be saved and read back without ESPN.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import asdict, dataclass
from typing import Any

from league_history import SEASONS, SHEET_ORDER

KINDS = ("overall", "regular", "winners", "losers")


@dataclass(frozen=True)
class TeamRecord:
    """One franchise in one season, with its regular-season line."""

    team_id: int
    name: str
    person: str
    wins: int
    losses: int
    ties: int
    points_for: float
    seed: int | None = None


@dataclass(frozen=True)
class GameRecord:
    """One head-to-head game. Playoff games carry their bracket side and round."""

    kind: str  # "regular", "winners", or "losers"
    label: str
    home: int
    away: int
    home_score: float
    away_score: float


@dataclass(frozen=True)
class WeekScores:
    """Every team's score in one regular-season week."""

    week: int
    scores: tuple[tuple[int, float], ...]


@dataclass(frozen=True)
class SeasonRecord:
    year: int
    teams: tuple[TeamRecord, ...]
    games: tuple[GameRecord, ...]
    weeks: tuple[WeekScores, ...]


def record_to_dict(record: SeasonRecord) -> dict[str, Any]:
    return asdict(record)


def record_from_dict(data: dict[str, Any]) -> SeasonRecord:
    return SeasonRecord(
        int(data["year"]),
        tuple(TeamRecord(**team) for team in data["teams"]),
        tuple(GameRecord(**game) for game in data["games"]),
        tuple(
            WeekScores(
                int(week["week"]),
                tuple((int(team_id), float(score)) for team_id, score in week["scores"]),
            )
            for week in data["weeks"]
        ),
    )


def _people(record: SeasonRecord) -> dict[int, str]:
    return {team.team_id: team.person for team in record.teams}


def _person_order(name: str) -> tuple[int, str]:
    try:
        return (SHEET_ORDER.index(name), name)
    except ValueError:
        return (len(SHEET_ORDER), name)


# --- head-to-head ---------------------------------------------------------


def head_to_head(records: dict[int, SeasonRecord]) -> dict[str, dict[str, dict[str, list[int]]]]:
    """person -> opponent -> kind -> [wins, losses, ties]. "overall" adds the other three."""
    board: dict[str, dict[str, dict[str, list[int]]]] = defaultdict(
        lambda: defaultdict(lambda: {kind: [0, 0, 0] for kind in KINDS})
    )
    for record in records.values():
        people = _people(record)
        for game in record.games:
            home = people.get(game.home)
            away = people.get(game.away)
            if not home or not away or home == away:
                continue
            if game.home_score > game.away_score:
                home_slot, away_slot = 0, 1
            elif game.away_score > game.home_score:
                home_slot, away_slot = 1, 0
            else:
                home_slot = away_slot = 2
            for kind in (game.kind, "overall"):
                board[home][away][kind][home_slot] += 1
                board[away][home][kind][away_slot] += 1
    return {
        person: {opponent: dict(lines) for opponent, lines in opponents.items()}
        for person, opponents in board.items()
    }


# --- weekly highs and lows -----------------------------------------------


@dataclass(frozen=True)
class WeekExtreme:
    week: int
    high: str
    high_score: float
    low: str
    low_score: float


def weekly_extremes(record: SeasonRecord) -> tuple[WeekExtreme, ...]:
    """Top and bottom score of each regular-season week. A tie lists both names."""
    people = _people(record)
    rows: list[WeekExtreme] = []
    for week in record.weeks:
        if not week.scores:
            continue
        top = max(score for _team, score in week.scores)
        bottom = min(score for _team, score in week.scores)
        high = " & ".join(people.get(team, "?") for team, score in week.scores if score == top)
        low = " & ".join(people.get(team, "?") for team, score in week.scores if score == bottom)
        rows.append(WeekExtreme(week.week, high, top, low, bottom))
    return tuple(rows)


# --- careers -------------------------------------------------------------


@dataclass(frozen=True)
class CareerRow:
    person: str
    seasons: int
    titles: int
    sackos: int
    best: str
    average: str
    wins: int
    losses: int
    ties: int
    points_for: float
    playoffs: int
    highs: int
    lows: int

    @property
    def record(self) -> str:
        line = f"{self.wins}-{self.losses}"
        return f"{line}-{self.ties}" if self.ties else line

    @property
    def win_pct(self) -> str:
        games = self.wins + self.losses + self.ties
        if not games:
            return "—"
        return f"{(self.wins + self.ties / 2) / games:.3f}".lstrip("0")


def _ordinal(place: int) -> str:
    if 10 <= place % 100 <= 20:
        return f"{place}th"
    return f"{place}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(place % 10, 'th') }"


def careers(records: dict[int, SeasonRecord]) -> tuple[CareerRow, ...]:
    """Sheet finishes for every person, plus ESPN's regular-season numbers."""
    finishes: dict[str, list[int]] = defaultdict(list)
    titles: dict[str, int] = defaultdict(int)
    sackos: dict[str, int] = defaultdict(int)
    seasons: dict[str, set[int]] = defaultdict(set)
    for season in SEASONS:
        named = [name for name in season.places if name]
        last_place = len(season.places)
        for place, name in enumerate(season.places, start=1):
            if not name:
                continue
            finishes[name].append(place)
            seasons[name].add(season.year)
            if place == 1:
                titles[name] += 1
            if place == last_place and len(named) == last_place:
                sackos[name] += 1
    totals: dict[str, list[float]] = defaultdict(lambda: [0, 0, 0, 0.0, 0, 0, 0])
    for record in records.values():
        for team in record.teams:
            line = totals[team.person]
            line[0] += team.wins
            line[1] += team.losses
            line[2] += team.ties
            line[3] += team.points_for
            line[4] += 1 if team.seed else 0
            seasons[team.person].add(record.year)
        for week in weekly_extremes(record):
            for name in week.high.split(" & "):
                totals[name][5] += 1
            for name in week.low.split(" & "):
                totals[name][6] += 1
    rows: list[CareerRow] = []
    for person in sorted(seasons, key=_person_order):
        places = finishes.get(person, [])
        line = totals[person]
        rows.append(
            CareerRow(
                person,
                len(seasons[person]),
                titles.get(person, 0),
                sackos.get(person, 0),
                _ordinal(min(places)) if places else "—",
                f"{sum(places) / len(places):.1f}" if places else "—",
                int(line[0]),
                int(line[1]),
                int(line[2]),
                round(float(line[3]), 1),
                int(line[4]),
                int(line[5]),
                int(line[6]),
            )
        )
    return tuple(rows)


# --- records -------------------------------------------------------------


@dataclass(frozen=True)
class LeagueRecord:
    label: str
    value: str
    who: str
    detail: str


def _score(value: float) -> str:
    return f"{value:.1f}"


def league_records(records: dict[int, SeasonRecord]) -> tuple[LeagueRecord, ...]:
    """Single-week and season bests, regular season only so every week is one week."""
    weeks: list[tuple[float, str, int, int]] = []
    games: list[tuple[float, str, str, float, float, int, int]] = []
    seasons: list[tuple[float, str, int, str]] = []
    for record in records.values():
        people = _people(record)
        for week_scores in record.weeks:
            for team_id, score in week_scores.scores:
                weeks.append((score, people.get(team_id, "?"), record.year, week_scores.week))
        for played in record.games:
            if played.kind != "regular":
                continue
            home_won = played.home_score >= played.away_score
            winner = played.home if home_won else played.away
            loser = played.away if home_won else played.home
            high = max(played.home_score, played.away_score)
            low = min(played.home_score, played.away_score)
            week_number = int(played.label.split()[-1]) if played.label.startswith("Week") else 0
            games.append(
                (
                    high - low,
                    people.get(winner, "?"),
                    people.get(loser, "?"),
                    high,
                    low,
                    record.year,
                    week_number,
                )
            )
        for club in record.teams:
            line = f"{club.wins}-{club.losses}" + (f"-{club.ties}" if club.ties else "")
            seasons.append((club.points_for, club.person, record.year, line))
    rows: list[LeagueRecord] = []
    if weeks:
        best = max(weeks)
        worst = min(weeks)
        rows.append(
            LeagueRecord("Highest week", _score(best[0]), best[1], f"{best[2]}, week {best[3]}")
        )
        rows.append(
            LeagueRecord("Lowest week", _score(worst[0]), worst[1], f"{worst[2]}, week {worst[3]}")
        )
    decided = [game for game in games if game[0] > 0]
    if decided:
        blowout = max(decided)
        closest = min(decided)
        for label, entry in (("Biggest blowout", blowout), ("Closest game", closest)):
            margin, won_by, lost_by, top, bottom, year, week_number = entry
            rows.append(
                LeagueRecord(
                    label,
                    _score(margin),
                    f"{won_by} over {lost_by}",
                    f"{_score(top)}–{_score(bottom)}, {year} week {week_number}",
                )
            )
    if seasons:
        most = max(seasons)
        fewest = min(seasons)
        rows.append(
            LeagueRecord(
                "Most points in a season", _score(most[0]), most[1], f"{most[2]}, {most[3]}"
            )
        )
        rows.append(
            LeagueRecord(
                "Fewest points in a season",
                _score(fewest[0]),
                fewest[1],
                f"{fewest[2]}, {fewest[3]}",
            )
        )
    return tuple(rows)


# --- brackets ------------------------------------------------------------


@dataclass(frozen=True)
class BracketLine:
    """One playoff game for the season card. The winner is bolded."""

    top: str
    top_score: str
    bottom: str
    bottom_score: str
    top_won: bool
    bottom_won: bool


@dataclass(frozen=True)
class BracketRound:
    label: str
    games: tuple[BracketLine, ...]


def season_bracket(record: SeasonRecord, side: str) -> tuple[BracketRound, ...]:
    """Rounds in the order they were played, for one side of the bracket."""
    people = _people(record)
    rounds: dict[str, list[BracketLine]] = {}
    for game in record.games:
        if game.kind != side:
            continue
        rounds.setdefault(game.label, []).append(
            BracketLine(
                people.get(game.home, "?"),
                _score(game.home_score),
                people.get(game.away, "?"),
                _score(game.away_score),
                game.home_score > game.away_score,
                game.away_score > game.home_score,
            )
        )
    return tuple(BracketRound(label, tuple(lines)) for label, lines in rounds.items())


# --- page ----------------------------------------------------------------


@dataclass(frozen=True)
class SeasonExtras:
    winners: tuple[BracketRound, ...]
    losers: tuple[BracketRound, ...]
    weeks: tuple[WeekExtreme, ...]


@dataclass(frozen=True)
class StatsView:
    careers: tuple[CareerRow, ...]
    records: tuple[LeagueRecord, ...]
    head_to_head: str
    people: tuple[str, ...]
    seasons: dict[int, SeasonExtras]
    loaded: int


def stats_view(records: dict[int, SeasonRecord]) -> StatsView:
    board = head_to_head(records)
    people = tuple(sorted(board, key=_person_order))
    extras = {
        year: SeasonExtras(
            season_bracket(record, "winners"),
            season_bracket(record, "losers"),
            weekly_extremes(record),
        )
        for year, record in records.items()
    }
    return StatsView(
        careers(records),
        league_records(records),
        json.dumps(board, sort_keys=True).replace("<", "\\u003c"),
        people,
        extras,
        len(records),
    )
