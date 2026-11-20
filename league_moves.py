"""Moves from ESPN: pickups, trades, season move counts, and points left on the bench.

Every season is tried; ESPN's library says rosters and transactions start in
2019, and the page shows what actually came back. Season move counts ride
along with the team data; a season where every counter is zero is treated as
one ESPN didn't keep.

Points come from weekly rosters, one scoring period (NFL week) at a time, and
stop at the league's last matchup week. A start only counts in a week the team
had a game. Adds and drops before week 1 kickoff are left out, since the
offline draft has been entered both as draft results and as roster adds.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from espn_api.football import League

from constants import NON_STARTER_SLOTS
from espn_history import _person
from league_history import SHEET_ORDER
from league_stats import SeasonRecord

logger = logging.getLogger(__name__)

EASTERN = ZoneInfo("America/New_York")
PHASES = ("overall", "regular", "winners", "losers")
PICKUP_TYPES = frozenset({"WAIVER", "FREEAGENT"})
# ESPN may log one trade as a proposal, an accept, and an uphold; pieces dedupe them.
TRANSACTION_TYPES = PICKUP_TYPES | {"TRADE_ACCEPT", "TRADE_UPHOLD", "TRADE_PROPOSAL"}
TOP_COUNT = 10


@dataclass(frozen=True)
class TeamMoves:
    """ESPN's season counters for one team."""

    team_id: int
    person: str
    acquisitions: int
    drops: int
    trades: int
    ir_moves: int
    faab_spent: int


@dataclass(frozen=True)
class Pickup:
    week: int
    team_id: int
    player_id: int
    kind: str  # "WAIVER" or "FREEAGENT"
    bid: int


@dataclass(frozen=True)
class TradePiece:
    player_id: int
    from_team: int
    to_team: int


@dataclass(frozen=True)
class Trade:
    week: int
    pieces: tuple[TradePiece, ...]


@dataclass(frozen=True)
class LineupWeek:
    """One team's week: what it started, and the best it could have started."""

    week: int
    team_id: int
    actual: float
    best: float
    starters: tuple[tuple[int, float], ...]


@dataclass(frozen=True)
class SeasonMoves:
    year: int
    regular_weeks: int
    teams: tuple[TeamMoves, ...]
    pickups: tuple[Pickup, ...] = ()
    trades: tuple[Trade, ...] = ()
    lineups: tuple[LineupWeek, ...] = ()
    players: tuple[tuple[int, str, str], ...] = ()
    notes: tuple[str, ...] = ()
    drops: tuple[tuple[int, int], ...] = ()  # (week, team id)
    played: tuple[tuple[int, int], ...] = ()  # (week, team id) with a game that week
    weekly: bool = False  # ESPN's transaction list came back

    @property
    def counters_kept(self) -> bool:
        return any(
            team.acquisitions or team.drops or team.trades or team.ir_moves for team in self.teams
        )


# --- reading ESPN ----------------------------------------------------------


def _flex(slot: str) -> bool:
    return slot == "OP" or ("/" in slot and slot != "D/ST")


def best_lineup(players: list[tuple[tuple[str, ...], float]], slots: dict[str, int]) -> float:
    """Most points the roster could have started. Single-position slots fill first."""
    open_slots = [
        slot
        for slot, count in sorted(slots.items(), key=lambda item: _flex(item[0]))
        if slot not in NON_STARTER_SLOTS and slot
        for _ in range(count)
    ]
    left = sorted(players, key=lambda player: -player[1])
    total = 0.0
    for slot in open_slots:
        for index, (eligible, points) in enumerate(left):
            if slot in eligible:
                total += points
                del left[index]
                break
    return round(total, 2)


def _week_points(player: Any, week: int) -> float:
    return float((getattr(player, "stats", {}) or {}).get(week, {}).get("points", 0) or 0)


def read_lineups(
    league: Any, week: int, slots: dict[str, int]
) -> tuple[list[LineupWeek], dict[int, tuple[str, str]]]:
    """Every team's roster for one scoring period, from league.load_roster_week."""
    league.load_roster_week(week)
    rows: list[LineupWeek] = []
    names: dict[int, tuple[str, str]] = {}
    for team in league.teams:
        starters: list[tuple[int, float]] = []
        pool: list[tuple[tuple[str, ...], float]] = []
        for player in team.roster:
            points = _week_points(player, week)
            player_id = int(player.playerId)
            names[player_id] = (str(player.name), str(getattr(player, "position", "") or ""))
            slot = str(getattr(player, "lineupSlot", "") or "")
            if slot and slot not in NON_STARTER_SLOTS:
                starters.append((player_id, round(points, 2)))
            if slot not in ("IR", "IR+"):
                pool.append((tuple(getattr(player, "eligibleSlots", ()) or ()), points))
        actual = round(sum(points for _player, points in starters), 2)
        best = max(best_lineup(pool, slots), actual)
        rows.append(LineupWeek(week, int(team.team_id), actual, best, tuple(starters)))
    return rows, names


def kickoff_ms(year: int) -> int:
    """Start of the NFL's opening Thursday (the Thursday after Labor Day), Eastern, in ms."""
    first = date(year, 9, 1)
    labor_day = first + timedelta(days=(0 - first.weekday()) % 7)
    thursday = labor_day + timedelta(days=3)
    start = datetime(thursday.year, thursday.month, thursday.day, tzinfo=EASTERN)
    return int(start.timestamp() * 1000)


@dataclass(frozen=True)
class WeekTransactions:
    pickups: list[Pickup]
    drops: list[tuple[int, int]]
    trades: list[Trade]
    skipped: int


def read_transactions(raw: list[dict[str, Any]], cutoff_ms: int = 0) -> WeekTransactions:
    """Executed pickups, drops, and trades from ESPN's mTransactions2 list for one period.

    Adds and drops processed before `cutoff_ms` are counted in `skipped` instead.
    """
    pickups: list[Pickup] = []
    drops: list[tuple[int, int]] = []
    trades: list[Trade] = []
    skipped = 0
    for item in raw:
        if item.get("status") != "EXECUTED":
            continue
        kind = str(item.get("type", ""))
        week = int(item.get("scoringPeriodId") or 0)
        entries = item.get("items") or []
        if kind in PICKUP_TYPES:
            early = bool(cutoff_ms) and int(item.get("processDate") or cutoff_ms) < cutoff_ms
            for entry in entries:
                if early and entry.get("type") in ("ADD", "DROP"):
                    skipped += 1 if entry.get("type") == "ADD" else 0
                    continue
                if entry.get("type") == "DROP":
                    team = int(entry.get("fromTeamId") or item.get("teamId") or 0)
                    drops.append((week, team))
                if entry.get("type") == "ADD":
                    pickups.append(
                        Pickup(
                            week,
                            int(entry.get("toTeamId") or item.get("teamId") or 0),
                            int(entry["playerId"]),
                            kind,
                            int(item.get("bidAmount") or 0),
                        )
                    )
        elif kind.startswith("TRADE"):
            pieces = tuple(
                sorted(
                    (
                        TradePiece(
                            int(entry["playerId"]),
                            int(entry.get("fromTeamId") or 0),
                            int(entry.get("toTeamId") or 0),
                        )
                        for entry in entries
                        if entry.get("type") == "TRADE"
                    ),
                    key=lambda piece: (piece.from_team, piece.player_id),
                )
            )
            if pieces:
                trades.append(Trade(week, pieces))
    return WeekTransactions(pickups, drops, trades, skipped)


def _fetch_transactions(league: Any, week: int) -> list[dict[str, Any]]:
    params = {"view": "mTransactions2", "scoringPeriodId": week}
    filters = {"transactions": {"filterType": {"value": sorted(TRANSACTION_TYPES)}}}
    headers = {"x-fantasy-filter": json.dumps(filters)}
    data = league.espn_request.league_get(params=params, headers=headers)
    return [item for item in data.get("transactions", []) if item.get("scoringPeriodId") == week]


def _team_moves(league: Any) -> tuple[TeamMoves, ...]:
    return tuple(
        TeamMoves(
            int(team.team_id),
            _person(team),
            int(getattr(team, "acquisitions", 0) or 0),
            int(getattr(team, "drops", 0) or 0),
            int(getattr(team, "trades", 0) or 0),
            int(getattr(team, "move_to_ir", 0) or 0),
            int(getattr(team, "acquisition_budget_spent", 0) or 0),
        )
        for team in league.teams
    )


def league_end_week(league: Any) -> int:
    """The league's last scoring period: the end of its last matchup, not ESPN's season end."""
    settings = getattr(league, "settings", None)
    periods = getattr(settings, "matchup_periods", {}) or {}
    weeks = [int(week) for scoring in periods.values() for week in scoring]
    if weeks:
        return max(weeks)
    return int(getattr(league, "finalScoringPeriod", 0) or 0)


def _fetch_played(league: Any) -> set[tuple[int, int]]:
    """(scoring period, team id) for every team with a matchup, from ESPN's schedule."""
    periods = getattr(getattr(league, "settings", None), "matchup_periods", {}) or {}
    data = league.espn_request.league_get(params={"view": "mMatchupScore"})
    played: set[tuple[int, int]] = set()
    for matchup in data.get("schedule", []):
        scoring = periods.get(str(matchup.get("matchupPeriodId")), [])
        home = (matchup.get("home") or {}).get("teamId")
        away = (matchup.get("away") or {}).get("teamId")
        if home is None or away is None:
            continue
        for week in scoring:
            played.add((int(week), int(home)))
            played.add((int(week), int(away)))
    return played


def read_season(league: Any, year: int) -> SeasonMoves:
    """One season from a loaded League. Stops early if ESPN has no weekly data for it."""
    settings = getattr(league, "settings", None)
    regular = int(getattr(settings, "reg_season_count", 0) or 0)
    teams = _team_moves(league)
    slots = dict(getattr(settings, "position_slot_counts", {}) or {})
    end = league_end_week(league)
    latest = int(getattr(league, "current_week", end) or end)
    last_week = min(end, latest) if end else latest
    cutoff = kickoff_ms(year)
    pickups: list[Pickup] = []
    drops: list[tuple[int, int]] = []
    trades: list[Trade] = []
    lineups: list[LineupWeek] = []
    names: dict[int, tuple[str, str]] = {}
    notes: list[str] = []
    skipped = 0
    weekly = False
    for week in range(1, last_week + 1):
        rosters_ok = transactions_ok = True
        try:
            rows, found = read_lineups(league, week, slots)
            lineups.extend(rows)
            names.update(found)
        except Exception as exc:
            rosters_ok = False
            notes.append(f"Week {week} rosters failed: {exc}")
        try:
            found_moves = read_transactions(_fetch_transactions(league, week), cutoff)
            pickups.extend(found_moves.pickups)
            drops.extend(found_moves.drops)
            trades.extend(found_moves.trades)
            skipped += found_moves.skipped
            weekly = True
        except Exception as exc:
            transactions_ok = False
            notes.append(f"Week {week} transactions failed: {exc}")
        if week == 1 and not rosters_ok and not transactions_ok:
            notes = ["ESPN returned no weekly rosters or transactions for this season."]
            break
    played: set[tuple[int, int]] = set()
    if lineups:
        try:
            played = _fetch_played(league)
        except Exception as exc:
            notes.append(f"Schedule failed, so starts count every week: {exc}")
    if skipped:
        notes.append(f"Left out {skipped} adds made before week 1 kickoff (draft entries).")
    for player_id, name in (getattr(league, "player_map", {}) or {}).items():
        if isinstance(player_id, int) and isinstance(name, str):
            names.setdefault(player_id, (name, ""))
    unique_trades: dict[tuple[TradePiece, ...], Trade] = {}
    for trade in trades:
        seen = unique_trades.get(trade.pieces)
        if seen is None or trade.week > seen.week:
            unique_trades[trade.pieces] = trade
    unique_pickups = list({(p.week, p.team_id, p.player_id): p for p in pickups}.values())
    if lineups and not any(row.actual for row in lineups):
        notes.append("Rosters came back without points.")
    used = {pickup.player_id for pickup in unique_pickups} | {
        piece.player_id for trade in unique_trades.values() for piece in trade.pieces
    }
    used |= {player_id for row in lineups for player_id, _points in row.starters}
    return SeasonMoves(
        year,
        regular,
        teams,
        tuple(unique_pickups),
        tuple(sorted(unique_trades.values(), key=lambda trade: trade.week)),
        tuple(lineups),
        tuple(
            (player_id, name, position)
            for player_id, (name, position) in sorted(names.items())
            if player_id in used
        ),
        tuple(notes),
        tuple(drops),
        tuple(sorted(played)),
        weekly,
    )


def load_moves(league_id: int, espn_s2: str, swid: str, year: int) -> SeasonMoves | None:
    try:
        league = League(league_id=league_id, year=year, espn_s2=espn_s2, swid=swid)
        return read_season(league, year)
    except Exception as exc:
        logger.warning("ESPN moves %s failed: %s", year, exc)
        return None


# --- snapshot --------------------------------------------------------------


def dump_moves(seasons: dict[int, SeasonMoves]) -> str:
    return json.dumps([asdict(seasons[year]) for year in sorted(seasons)], sort_keys=True)


def load_moves_snapshot(text: str) -> dict[int, SeasonMoves]:
    seasons: dict[int, SeasonMoves] = {}
    for data in json.loads(text):
        season = SeasonMoves(
            int(data["year"]),
            int(data["regular_weeks"]),
            tuple(TeamMoves(**team) for team in data["teams"]),
            tuple(Pickup(**pickup) for pickup in data["pickups"]),
            tuple(
                Trade(int(trade["week"]), tuple(TradePiece(**piece) for piece in trade["pieces"]))
                for trade in data["trades"]
            ),
            tuple(
                LineupWeek(
                    int(row["week"]),
                    int(row["team_id"]),
                    float(row["actual"]),
                    float(row["best"]),
                    tuple((int(pid), float(points)) for pid, points in row["starters"]),
                )
                for row in data["lineups"]
            ),
            tuple((int(pid), str(name), str(pos)) for pid, name, pos in data["players"]),
            tuple(str(note) for note in data["notes"]),
            tuple((int(week), int(team)) for week, team in data.get("drops", [])),
            tuple((int(week), int(team)) for week, team in data.get("played", [])),
            bool(data.get("weekly", False)),
        )
        seasons[season.year] = season
    return seasons


# --- page ------------------------------------------------------------------


def _person_order(name: str) -> tuple[int, str]:
    try:
        return (SHEET_ORDER.index(name), name)
    except ValueError:
        return (len(SHEET_ORDER), name)


@dataclass(frozen=True)
class ActiveRow:
    person: str
    seasons: int
    adds: int
    drops: int
    trades: int
    ir_moves: int
    faab: int

    @property
    def adds_per_season(self) -> str:
        return f"{self.adds / self.seasons:.1f}" if self.seasons else "—"


def _counted(season: SeasonMoves) -> dict[int, tuple[int, int, int, int]]:
    """team -> (adds, drops, trades, FAAB) counted from the transaction list."""
    adds: dict[int, int] = defaultdict(int)
    faab: dict[int, int] = defaultdict(int)
    drops: dict[int, int] = defaultdict(int)
    trades: dict[int, int] = defaultdict(int)
    for pickup in season.pickups:
        adds[pickup.team_id] += 1
        faab[pickup.team_id] += pickup.bid if pickup.kind == "WAIVER" else 0
    for _week, team_id in season.drops:
        drops[team_id] += 1
    for trade in season.trades:
        for team_id in {piece.from_team for piece in trade.pieces} | {
            piece.to_team for piece in trade.pieces
        }:
            trades[team_id] += 1
    return {
        team.team_id: (
            adds[team.team_id],
            drops[team.team_id],
            trades[team.team_id],
            faab[team.team_id],
        )
        for team in season.teams
    }


def most_active(seasons: list[SeasonMoves]) -> tuple[ActiveRow, ...]:
    """Moves per person: counted from transactions when ESPN gave them, else its season counts.

    Seasons with neither are skipped. IR moves always come from ESPN's counts.
    """
    totals: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0, 0, 0, 0])
    for season in seasons:
        if not season.weekly and not season.counters_kept:
            continue
        counted = _counted(season) if season.weekly else {}
        for team in season.teams:
            adds, drops, trades, faab = counted.get(
                team.team_id, (team.acquisitions, team.drops, team.trades, team.faab_spent)
            )
            line = totals[team.person]
            line[0] += 1
            line[1] += adds
            line[2] += drops
            line[3] += trades
            line[4] += team.ir_moves
            line[5] += faab
    return tuple(ActiveRow(person, *totals[person]) for person in sorted(totals, key=_person_order))


def _starts(season: SeasonMoves) -> dict[int, dict[int, list[tuple[int, float]]]]:
    """player -> team -> [(week, points)] for weeks the team started him."""
    starts: dict[int, dict[int, list[tuple[int, float]]]] = defaultdict(lambda: defaultdict(list))
    played = set(season.played)
    for row in season.lineups:
        if played and (row.week, row.team_id) not in played:
            continue
        for player_id, points in row.starters:
            starts[player_id][row.team_id].append((row.week, points))
    return starts


def _arrivals(season: SeasonMoves) -> dict[int, list[int]]:
    """player -> weeks he joined a team by pickup or trade, so a stint ends at the next one."""
    weeks: dict[int, list[int]] = defaultdict(list)
    for pickup in season.pickups:
        weeks[pickup.player_id].append(pickup.week)
    for trade in season.trades:
        for piece in trade.pieces:
            weeks[piece.player_id].append(trade.week)
    return {player: sorted(found) for player, found in weeks.items()}


def _stint_points(
    starts: dict[int, dict[int, list[tuple[int, float]]]],
    arrivals: dict[int, list[int]],
    player_id: int,
    team_id: int,
    week: int,
    weeks: range | None = None,
) -> tuple[float, int]:
    """Points and starts for the team from `week` until the player next changed teams.

    A drop needs no cutoff: the team can't start him once he's gone. `weeks` limits the
    count to part of the season.
    """
    later = [found for found in arrivals.get(player_id, []) if found > week]
    until = later[0] if later else 10**6
    games = [
        points
        for played, points in starts.get(player_id, {}).get(team_id, [])
        if week <= played < until and (weeks is None or played in weeks)
    ]
    return round(sum(games), 2), len(games)


@dataclass(frozen=True)
class PickupRow:
    person: str
    player: str
    position: str
    year: int
    week: int
    how: str
    points: float
    starts: int


def _phase_weeks(season: SeasonMoves, phase: str, seeded: bool | None) -> range | None:
    """Weeks of `phase` for a team, or None for every week. Empty when it doesn't apply."""
    after = season.regular_weeks + 1 if season.regular_weeks else 10**6
    if phase == "overall":
        return None
    if phase == "regular":
        return range(1, after)
    if seeded is None or seeded != (phase == "winners"):
        return range(0)
    return range(after, 10**6)


def best_pickups(
    seasons: list[SeasonMoves], seeds: dict[int, set[int]] | None = None
) -> dict[str, tuple[PickupRow, ...]]:
    """phase -> pickups with the points each scored as a starter for that team, best first.

    Bracket side comes from the history page's seeds: seeded teams are the winners' side.
    Outside "overall", a pickup that never started in that part of the season is left out.
    """
    rows: dict[str, list[PickupRow]] = {phase: [] for phase in PHASES}
    for season in seasons:
        people = {team.team_id: team.person for team in season.teams}
        players = {pid: (name, pos) for pid, name, pos in season.players}
        starts = _starts(season)
        arrivals = _arrivals(season)
        season_seeds = (seeds or {}).get(season.year)
        for pickup in season.pickups:
            name, position = players.get(pickup.player_id, (f"Player {pickup.player_id}", ""))
            how = f"Waiver ${pickup.bid}" if pickup.kind == "WAIVER" else "Free agent"
            seeded = None if season_seeds is None else pickup.team_id in season_seeds
            for phase in PHASES:
                points, count = _stint_points(
                    starts,
                    arrivals,
                    pickup.player_id,
                    pickup.team_id,
                    pickup.week,
                    _phase_weeks(season, phase, seeded),
                )
                if phase != "overall" and not count:
                    continue
                rows[phase].append(
                    PickupRow(
                        people.get(pickup.team_id, "?"),
                        name,
                        position,
                        season.year,
                        pickup.week,
                        how,
                        points,
                        count,
                    )
                )
    return {
        phase: tuple(sorted(found, key=lambda row: (-row.points, row.year, row.week)))
        for phase, found in rows.items()
    }


@dataclass(frozen=True)
class TradeSide:
    person: str
    players: tuple[tuple[str, float, int], ...]  # name, points as a starter, starts
    points: float
    won: bool


@dataclass(frozen=True)
class TradeRow:
    year: int
    week: int
    sides: tuple[TradeSide, ...]


def trade_ledger(seasons: list[SeasonMoves]) -> tuple[TradeRow, ...]:
    """Each trade, with what every side got out of the players it received. Newest first."""
    rows: list[TradeRow] = []
    for season in seasons:
        people = {team.team_id: team.person for team in season.teams}
        players = {pid: name for pid, name, _pos in season.players}
        starts = _starts(season)
        arrivals = _arrivals(season)
        for trade in season.trades:
            received: dict[int, list[tuple[str, float, int]]] = defaultdict(list)
            for piece in trade.pieces:
                points, count = _stint_points(
                    starts, arrivals, piece.player_id, piece.to_team, trade.week
                )
                name = players.get(piece.player_id, f"Player {piece.player_id}")
                received[piece.to_team].append((name, points, count))
            totals = {team: round(sum(p for _n, p, _c in got), 2) for team, got in received.items()}
            top = max(totals.values()) if totals else 0
            clear = list(totals.values()).count(top) == 1
            rows.append(
                TradeRow(
                    season.year,
                    trade.week,
                    tuple(
                        TradeSide(
                            people.get(team, "?"),
                            tuple(sorted(got, key=lambda item: -item[1])),
                            totals[team],
                            clear and totals[team] == top,
                        )
                        for team, got in sorted(received.items(), key=lambda item: -totals[item[0]])
                    ),
                )
            )
    return tuple(sorted(rows, key=lambda row: (-row.year, -row.week)))


def trade_records(rows: tuple[TradeRow, ...]) -> tuple[tuple[str, int, int, int], ...]:
    """person, trades, won, lost. A tied trade counts for neither."""
    lines: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    for row in rows:
        decided = any(side.won for side in row.sides)
        for side in row.sides:
            line = lines[side.person]
            line[0] += 1
            if decided:
                line[1 if side.won else 2] += 1
    return tuple(
        (person, lines[person][0], lines[person][1], lines[person][2])
        for person in sorted(lines, key=_person_order)
    )


@dataclass(frozen=True)
class BenchRow:
    person: str
    weeks: int
    left: float
    perfect: int

    @property
    def per_week(self) -> str:
        return f"{self.left / self.weeks:.1f}" if self.weeks else "—"

    @property
    def perfect_pct(self) -> str:
        return f"{100 * self.perfect / self.weeks:.0f}%" if self.weeks else "—"


@dataclass(frozen=True)
class BenchWeek:
    person: str
    year: int
    week: int
    actual: float
    best: float

    @property
    def left(self) -> float:
        return round(self.best - self.actual, 2)


def bench_points(seasons: list[SeasonMoves]) -> tuple[tuple[BenchRow, ...], tuple[BenchWeek, ...]]:
    """Regular-season points left on the bench, per person and the worst single weeks."""
    totals: dict[str, list[float]] = defaultdict(lambda: [0, 0.0, 0])
    weeks: list[BenchWeek] = []
    for season in seasons:
        people = {team.team_id: team.person for team in season.teams}
        for row in season.lineups:
            if season.regular_weeks and row.week > season.regular_weeks:
                continue
            person = people.get(row.team_id, "?")
            line = totals[person]
            line[0] += 1
            line[1] += row.best - row.actual
            line[2] += 1 if row.best - row.actual < 0.01 else 0
            weeks.append(BenchWeek(person, season.year, row.week, row.actual, row.best))
    table = tuple(
        BenchRow(person, int(line[0]), round(line[1], 1), int(line[2]))
        for person, line in sorted(totals.items(), key=lambda item: _person_order(item[0]))
    )
    worst = tuple(sorted(weeks, key=lambda week: (-week.left, week.year, week.week))[:TOP_COUNT])
    return table, worst


@dataclass(frozen=True)
class SeasonStatus:
    year: int
    counters: bool
    roster_weeks: int
    pickups: int
    trades: int
    notes: tuple[str, ...]
    checked: int = 0
    matched: int = 0


def _score_check(season: SeasonMoves, record: SeasonRecord | None) -> tuple[int, int]:
    """Team-weeks whose starters add up to ESPN's score for that week, out of those compared."""
    if record is None:
        return 0, 0
    scores = {
        (week.week, team_id): score for week in record.weeks for team_id, score in week.scores
    }
    checked = matched = 0
    for row in season.lineups:
        score = scores.get((row.week, row.team_id))
        if score is None:
            continue
        checked += 1
        matched += 1 if abs(score - row.actual) < 0.05 else 0
    return checked, matched


@dataclass(frozen=True)
class MovesView:
    status: tuple[SeasonStatus, ...]
    active: tuple[ActiveRow, ...]
    active_by_year: dict[int, tuple[ActiveRow, ...]]
    pickups: dict[str, dict[str, tuple[PickupRow, ...]]]  # phase -> person ("" everyone)
    trades: tuple[TradeRow, ...]
    trade_records: tuple[tuple[str, int, int, int], ...]
    bench: tuple[BenchRow, ...]
    bench_worst: tuple[BenchWeek, ...]
    people: tuple[str, ...]


def moves_view(
    seasons: dict[int, SeasonMoves], records: dict[int, SeasonRecord] | None = None
) -> MovesView:
    ordered = [seasons[year] for year in sorted(seasons)]
    trades = trade_ledger(ordered)
    bench, worst = bench_points(ordered)
    seeds = {
        year: {team.team_id for team in record.teams if team.seed}
        for year, record in (records or {}).items()
    }
    pickups = best_pickups(ordered, seeds)
    people = sorted({row.person for row in pickups["overall"]}, key=_person_order)
    return MovesView(
        tuple(
            SeasonStatus(
                season.year,
                season.counters_kept or season.weekly,
                len({row.week for row in season.lineups}),
                len(season.pickups),
                len(season.trades),
                season.notes,
                *_score_check(season, (records or {}).get(season.year)),
            )
            for season in reversed(ordered)
        ),
        most_active(ordered),
        {season.year: most_active([season]) for season in reversed(ordered)},
        {
            phase: {
                "": rows[:TOP_COUNT],
                **{
                    person: tuple(row for row in rows if row.person == person)[:TOP_COUNT]
                    for person in people
                },
            }
            for phase, rows in pickups.items()
        },
        trades,
        trade_records(trades),
        bench,
        worst,
        tuple(people),
    )
