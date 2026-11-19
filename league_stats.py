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

TOP_COUNT = 5
SIZES = ("all", "10", "12")
# ESPN labels 2011's playoff games by week, but each one is two weeks added together.
TWO_WEEK_PLAYOFF_YEARS = (2011,)


@dataclass(frozen=True)
class RecordEntry:
    """One line of a record's top list. `score` is the game score for game records."""

    value: str
    who: str
    year: int
    label: str
    score: str = ""

    @property
    def when(self) -> str:
        return f"{self.year}, {self.label}" if self.label else str(self.year)


@dataclass(frozen=True)
class LeagueRecord:
    label: str
    value: str
    who: str
    detail: str
    top: tuple[RecordEntry, ...] = ()


@dataclass(frozen=True)
class RecordsView:
    records: tuple[LeagueRecord, ...]
    note: str


def _score(value: float) -> str:
    return f"{value:.1f}"


def _margin(value: float) -> str:
    """Two decimals under a point, so a 0.04-point game doesn't read as 0.0."""
    return f"{value:.2f}" if value < 1 else _score(value)


def _size(record: SeasonRecord) -> str:
    return "12" if len(record.teams) >= 12 else "10"


def _is_two_week(year: int, game: GameRecord) -> bool:
    if game.kind == "regular":
        return False
    return "(2 weeks)" in game.label or year in TWO_WEEK_PLAYOFF_YEARS


def _game_label(year: int, game: GameRecord) -> str:
    if game.kind == "regular" and game.label.startswith("Week "):
        return f"week {game.label.split()[-1]}"
    if _is_two_week(year, game) and "(2 weeks)" not in game.label:
        return f"{game.label} (2 weeks)"
    return game.label


def _top(items: list[tuple[float, RecordEntry]], high: bool) -> tuple[RecordEntry, ...]:
    """The best TOP_COUNT, plus anyone tied with the last of them. Earlier years first on ties."""
    ordered = sorted(items, key=lambda item: -item[0] if high else item[0])
    if len(ordered) <= TOP_COUNT:
        return tuple(entry for _value, entry in ordered)
    cutoff = ordered[TOP_COUNT - 1][0]
    return tuple(
        entry for value, entry in ordered if (value >= cutoff if high else value <= cutoff)
    )


def _card(label: str, top: tuple[RecordEntry, ...], game: bool = False) -> LeagueRecord:
    first = top[0]
    detail = f"{first.score}, {first.year} {first.label}" if game else first.when
    return LeagueRecord(label, first.value, first.who, detail, top)


def _records_for(records: list[SeasonRecord], kind: str) -> RecordsView:
    played = [
        (record, game)
        for record in records
        for game in record.games
        if kind == "overall" or game.kind == kind
    ]
    two_week = [_is_two_week(record.year, game) for record, game in played]
    all_two_week = bool(played) and all(two_week)
    dropped = any(two_week) and not all_two_week
    if dropped:
        played = [pair for pair, longer in zip(played, two_week, strict=True) if not longer]

    scores: list[tuple[float, RecordEntry]] = []
    margins: list[tuple[float, RecordEntry]] = []
    for record, game in played:
        people = _people(record)
        label = _game_label(record.year, game)
        for team_id, score in ((game.home, game.home_score), (game.away, game.away_score)):
            entry = RecordEntry(_score(score), people.get(team_id, "?"), record.year, label)
            scores.append((round(score, 2), entry))
        margin = round(abs(game.home_score - game.away_score), 2)
        if margin == 0:
            continue
        home_won = game.home_score > game.away_score
        winner, loser = (game.home, game.away) if home_won else (game.away, game.home)
        high = max(game.home_score, game.away_score)
        low = min(game.home_score, game.away_score)
        margins.append(
            (
                margin,
                RecordEntry(
                    _margin(margin),
                    f"{people.get(winner, '?')} over {people.get(loser, '?')}",
                    record.year,
                    label,
                    f"{_score(high)}–{_score(low)}",
                ),
            )
        )

    prefix = "2-week " if all_two_week else ""
    rows: list[LeagueRecord] = []
    if scores:
        week_word = "2-week score" if all_two_week else "week"
        rows.append(_card(f"Highest {week_word}", _top(scores, high=True)))
        rows.append(_card(f"Lowest {week_word}", _top(scores, high=False)))
    if margins:
        rows.append(_card(f"Biggest {prefix}blowout", _top(margins, high=True), game=True))
        rows.append(_card(f"Closest {prefix}game", _top(margins, high=False), game=True))

    with_seasons = kind in ("overall", "regular")
    if with_seasons:
        totals: list[tuple[float, RecordEntry]] = []
        per_game: list[tuple[float, RecordEntry]] = []
        for record in records:
            weeks_played: dict[int, int] = defaultdict(int)
            for week in record.weeks:
                for team_id, _score_value in week.scores:
                    weeks_played[team_id] += 1
            for club in record.teams:
                line = f"{club.wins}-{club.losses}" + (f"-{club.ties}" if club.ties else "")
                total = round(club.points_for, 2)
                totals.append(
                    (total, RecordEntry(_score(total), club.person, record.year, line))
                )
                count = weeks_played.get(club.team_id, 0)
                if count:
                    average = round(club.points_for / count, 2)
                    per_game.append(
                        (
                            average,
                            RecordEntry(
                                _score(average),
                                club.person,
                                record.year,
                                f"{count} weeks, {total:,.1f} total",
                            ),
                        )
                    )
        if totals:
            rows.append(_card("Most points in a season", _top(totals, high=True)))
            rows.append(_card("Fewest points in a season", _top(totals, high=False)))
        if per_game:
            rows.append(_card("Most points per game", _top(per_game, high=True)))
            rows.append(_card("Fewest points per game", _top(per_game, high=False)))

    notes: list[str] = []
    if dropped:
        notes.append("Two-week playoff games are left out, so every score is one week.")
    if all_two_week:
        notes.append("Every game here is two weeks added together.")
    if with_seasons and rows:
        notes.append("Season totals are the regular season.")
    return RecordsView(tuple(rows), " ".join(notes))


def records_board(records: dict[int, SeasonRecord]) -> dict[str, dict[str, RecordsView]]:
    """size ("all", "10", "12") -> kind -> records. 2011's eight teams count with the 10s."""
    ordered = [records[year] for year in sorted(records)]
    return {
        size: {
            kind: _records_for(
                [record for record in ordered if size == "all" or _size(record) == size], kind
            )
            for kind in KINDS
        }
        for size in SIZES
    }


def league_records(records: dict[int, SeasonRecord]) -> tuple[LeagueRecord, ...]:
    """Every season's regular-season records."""
    return records_board(records)["all"]["regular"].records


# --- kryptonite ----------------------------------------------------------

KRYPTONITE_MIN_GAMES = 8


@dataclass(frozen=True)
class Matchup:
    """How one opponent scores against a person, next to how they scored otherwise."""

    opponent: str
    games: int
    against: float
    usual: float

    @property
    def edge(self) -> float:
        return self.against - self.usual


def matchups(records: dict[int, SeasonRecord]) -> dict[str, tuple[Matchup, ...]]:
    """person -> opponents with at least KRYPTONITE_MIN_GAMES regular-season games, best first.

    Each game compares the opponent's score with their average for the rest of that season.
    """
    games: dict[str, dict[str, list[tuple[float, float]]]] = defaultdict(lambda: defaultdict(list))
    for record in records.values():
        people = _people(record)
        totals: dict[int, list[float]] = defaultdict(lambda: [0.0, 0.0])
        for week in record.weeks:
            for team_id, score in week.scores:
                totals[team_id][0] += score
                totals[team_id][1] += 1
        for game in record.games:
            if game.kind != "regular":
                continue
            for me, them, their_score in (
                (game.home, game.away, game.away_score),
                (game.away, game.home, game.home_score),
            ):
                person = people.get(me)
                opponent = people.get(them)
                total, count = totals[them]
                if not person or not opponent or person == opponent or count < 2:
                    continue
                usual = (total - their_score) / (count - 1)
                games[person][opponent].append((their_score, usual))
    board: dict[str, tuple[Matchup, ...]] = {}
    for person, opponents in games.items():
        rows = [
            Matchup(
                opponent,
                len(pairs),
                sum(score for score, _usual in pairs) / len(pairs),
                sum(usual for _score, usual in pairs) / len(pairs),
            )
            for opponent, pairs in opponents.items()
            if len(pairs) >= KRYPTONITE_MIN_GAMES
        ]
        if rows:
            board[person] = tuple(sorted(rows, key=lambda row: (-row.edge, -row.games)))
    return board


def _matchups_json(board: dict[str, tuple[Matchup, ...]]) -> str:
    data = {
        person: [
            {
                "opponent": row.opponent,
                "games": row.games,
                "against": round(row.against, 1),
                "usual": round(row.usual, 1),
                "edge": round(row.edge, 1),
            }
            for row in rows
        ]
        for person, rows in board.items()
    }
    return json.dumps(data, sort_keys=True).replace("<", "\\u003c")


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
    records_board: dict[str, dict[str, RecordsView]]
    matchups: str
    kryptonite_min_games: int = KRYPTONITE_MIN_GAMES


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
    by_view = records_board(records)
    return StatsView(
        careers(records),
        by_view["all"]["regular"].records,
        json.dumps(board, sort_keys=True).replace("<", "\\u003c"),
        people,
        extras,
        len(records),
        by_view,
        _matchups_json(matchups(records)),
    )
