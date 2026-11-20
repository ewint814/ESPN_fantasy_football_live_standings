"""Moves from ESPN: pickups, trades, season move counts, and points left on the bench.

Every season is tried, and the page shows what actually came back. Before 2018
ESPN keeps only the season move counts that ride along with the team data (its
"weekly" rosters are the final roster with no points), so those seasons count
moves from ESPN's totals and have no pickups, trades, or bench points. A season
where every counter is zero is treated as one ESPN didn't keep.

Points come from weekly rosters, one scoring period (NFL week) at a time, and
stop at the league's last matchup week. A start only counts in a week the team
had a game.

The offline draft is sometimes entered as roster adds instead of draft picks:
2018 (each team adding its own picks), 2020 (two days of adds; ESPN's draft
results that year are a placeholder), and commissioner adds on draft day (2026).
Those adds are left out; every other pickup counts, preseason ones included.

ESPN lists the players in a trade only when the logged-in member was part of it.
Other trades are an executed accept or uphold with no players, so their players
come from the week's roster changes: a player who moved between two teams with
no add.
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
# One trade can be executed as an accept per side plus an uphold; they share a related id.
TRADE_TYPES = frozenset({"TRADE_ACCEPT", "TRADE_UPHOLD"})
# "ROSTER" holds plain drops (and lineup changes, which are ignored).
TRANSACTION_TYPES = PICKUP_TYPES | TRADE_TYPES | {"ROSTER"}
# Eastern dates when that season's draft was entered as roster adds.
DRAFT_ENTRY_DAYS: dict[int, tuple[date, ...]] = {2020: (date(2020, 9, 2), date(2020, 9, 3))}
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
    # (week, team id, points, reason): commissioner score changes, part of ESPN's weekly score
    adjustments: tuple[tuple[int, int, float, str], ...] = ()

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


@dataclass(frozen=True)
class WeekRosters:
    rows: list[LineupWeek]
    names: dict[int, tuple[str, str]]
    owners: dict[int, int]  # player id -> team id


def read_lineups(league: Any, week: int, slots: dict[str, int]) -> WeekRosters:
    """Every team's roster for one scoring period, from league.load_roster_week."""
    league.load_roster_week(week)
    rows: list[LineupWeek] = []
    names: dict[int, tuple[str, str]] = {}
    owners: dict[int, int] = {}
    for team in league.teams:
        starters: list[tuple[int, float]] = []
        pool: list[tuple[tuple[str, ...], float]] = []
        for player in team.roster:
            points = _week_points(player, week)
            player_id = int(player.playerId)
            owners[player_id] = int(team.team_id)
            names[player_id] = (str(player.name), str(getattr(player, "position", "") or ""))
            slot = str(getattr(player, "lineupSlot", "") or "")
            if slot and slot not in NON_STARTER_SLOTS:
                starters.append((player_id, round(points, 2)))
            if slot not in ("IR", "IR+"):
                pool.append((tuple(getattr(player, "eligibleSlots", ()) or ()), points))
        actual = round(sum(points for _player, points in starters), 2)
        best = max(best_lineup(pool, slots), actual)
        rows.append(LineupWeek(week, int(team.team_id), actual, best, tuple(starters)))
    return WeekRosters(rows, names, owners)


def kickoff_ms(year: int) -> int:
    """Start of the NFL's opening Thursday (the Thursday after Labor Day), Eastern, in ms."""
    first = date(year, 9, 1)
    labor_day = first + timedelta(days=(0 - first.weekday()) % 7)
    thursday = labor_day + timedelta(days=3)
    start = datetime(thursday.year, thursday.month, thursday.day, tzinfo=EASTERN)
    return int(start.timestamp() * 1000)


@dataclass(frozen=True)
class DraftEntries:
    """Draft picks entered as roster adds before week 1 kickoff. They aren't pickups."""

    kickoff_ms: int = 0
    drafted: frozenset[tuple[int, int]] = frozenset()  # (team id, player id) from ESPN's draft
    days: tuple[date, ...] = ()  # Eastern dates when every add was a draft entry

    def covers(self, item: dict[str, Any], team_id: int, player_id: int) -> bool:
        """An add before kickoff of the team's own pick, by the commissioner, or on an entry day."""
        when = int(item.get("processDate") or item.get("proposedDate") or 0)
        if not self.kickoff_ms or not when or when >= self.kickoff_ms:
            return False
        if (team_id, player_id) in self.drafted or item.get("isLeagueManager"):
            return True
        return datetime.fromtimestamp(when / 1000, EASTERN).date() in self.days


@dataclass(frozen=True)
class WeekTransactions:
    pickups: list[Pickup]
    drops: list[tuple[int, int]]
    trades: dict[str, Trade]  # receipt id -> trade, when ESPN listed its players
    receipts: dict[str, int]  # receipt id -> week, for every executed trade
    trade_drops: dict[tuple[str, int], tuple[int, int]]  # (receipt, player) -> (week, team)
    skipped: int


def _pieces(entries: list[dict[str, Any]]) -> tuple[TradePiece, ...]:
    return tuple(
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


def read_transactions(
    raw: list[dict[str, Any]], draft: DraftEntries | None = None
) -> WeekTransactions:
    """Executed pickups, drops, and trades from ESPN's mTransactions2 list for one period.

    Draft entries are counted in `skipped` instead of as pickups. A trade's accept and
    uphold records share a receipt id, so each trade and its drops count once.
    """
    draft = draft or DraftEntries()
    pickups: list[Pickup] = []
    drops: list[tuple[int, int]] = []
    trades: dict[str, Trade] = {}
    receipts: dict[str, int] = {}
    trade_drops: dict[tuple[str, int], tuple[int, int]] = {}
    skipped = 0
    for item in raw:
        if item.get("status") != "EXECUTED":
            continue
        kind = str(item.get("type", ""))
        week = int(item.get("scoringPeriodId") or 0)
        entries = item.get("items") or []
        if kind in TRADE_TYPES:
            pieces = _pieces(entries)
            receipt = str(item.get("relatedTransactionId") or item.get("id") or (week, pieces))
            receipts[receipt] = max(week, receipts.get(receipt, 0))
            if pieces:
                trades[receipt] = Trade(week, pieces)
            for entry in entries:
                if entry.get("type") == "DROP":
                    team = int(entry.get("fromTeamId") or item.get("teamId") or 0)
                    trade_drops[(receipt, int(entry["playerId"]))] = (week, team)
            continue
        if kind not in PICKUP_TYPES and kind != "ROSTER":
            continue
        for entry in entries:
            if entry.get("type") == "DROP":
                drops.append((week, int(entry.get("fromTeamId") or item.get("teamId") or 0)))
            elif entry.get("type") == "ADD" and kind in PICKUP_TYPES:
                team = int(entry.get("toTeamId") or item.get("teamId") or 0)
                player = int(entry["playerId"])
                if draft.covers(item, team, player):
                    skipped += 1
                    continue
                pickups.append(Pickup(week, team, player, kind, int(item.get("bidAmount") or 0)))
    return WeekTransactions(pickups, drops, trades, receipts, trade_drops, skipped)


def _roster_moves(
    owners: dict[int, dict[int, int]],
    week: int,
    adds: set[tuple[int, int, int]],
    listed: set[tuple[int, int]],
) -> dict[frozenset[int], list[TradePiece]]:
    """Players on a different team in `week` than the week before, with no add, by team pair."""
    before, after = owners.get(week - 1), owners.get(week)
    groups: dict[frozenset[int], list[TradePiece]] = defaultdict(list)
    if not before or not after:
        return groups
    for player, old in before.items():
        new = after.get(player)
        if new is None or new == old:
            continue
        if any(
            (seen, player) in listed or (seen, new, player) in adds for seen in (week - 1, week)
        ):
            continue
        groups[frozenset((old, new))].append(TradePiece(player, old, new))
    return groups


def _route_flips(
    groups: dict[frozenset[int], list[TradePiece]], count: int
) -> dict[frozenset[int], list[TradePiece]]:
    """A player flipped A -> B -> C in one week looks like A -> C; send him through B.

    Only when the rosters show more trades than ESPN has, and B traded with both A and C.
    """
    for pair in list(groups):
        if len(groups) <= count or pair not in groups:
            break
        pieces = groups[pair]
        start, end = pieces[0].from_team, pieces[0].to_team
        if any(piece.from_team != start for piece in pieces):
            continue
        middles = [
            team
            for team in {team for other in groups for team in other} - {start, end}
            if frozenset((start, team)) in groups and frozenset((team, end)) in groups
        ]
        if len(middles) != 1:
            continue
        middle = middles[0]
        del groups[pair]
        for piece in pieces:
            groups[frozenset((start, middle))].append(TradePiece(piece.player_id, start, middle))
            groups[frozenset((middle, end))].append(TradePiece(piece.player_id, middle, end))
    return groups


def roster_trades(
    owners: dict[int, dict[int, int]],
    receipts: dict[int, int],
    adds: set[tuple[int, int, int]],
    listed: set[tuple[int, int]],
) -> tuple[list[Trade], list[str]]:
    """Trades ESPN has no players for, from the week's roster changes.

    `owners` is week -> player -> team, `receipts` week -> trades without players executed
    that week, `adds` (week, team, player) for pickups, and `listed` (week, player) for
    trades ESPN did list. Only weeks with a receipt are searched, so a missed add can't
    turn into a trade. If the week shows nothing, the next week is tried.
    """
    trades: list[Trade] = []
    notes: list[str] = []
    for week, count in sorted(receipts.items()):
        groups = _roster_moves(owners, week, adds, listed) or _roster_moves(
            owners, week + 1, adds, listed
        )
        groups = _route_flips(groups, count)
        found = [
            Trade(week, tuple(sorted(pieces, key=lambda p: (p.from_team, p.player_id))))
            for _pair, pieces in sorted(groups.items(), key=lambda item: sorted(item[0]))
        ]
        if len(found) != count:
            notes.append(
                f"Week {week}: ESPN has {count} trades without players; "
                f"the rosters show {len(found)}."
            )
        trades.extend(found)
    return trades, notes


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


def _draft_entries(league: Any, year: int) -> DraftEntries:
    drafted = frozenset(
        (int(pick.team.team_id), int(pick.playerId))
        for pick in getattr(league, "draft", None) or []
        if getattr(pick, "team", None) is not None
    )
    return DraftEntries(kickoff_ms(year), drafted, DRAFT_ENTRY_DAYS.get(year, ()))


def league_end_week(league: Any) -> int:
    """The league's last scoring period: the end of its last matchup, not ESPN's season end."""
    settings = getattr(league, "settings", None)
    periods = getattr(settings, "matchup_periods", {}) or {}
    weeks = [int(week) for scoring in periods.values() for week in scoring]
    if weeks:
        return max(weeks)
    return int(getattr(league, "finalScoringPeriod", 0) or 0)


def _fetch_schedule(
    league: Any,
) -> tuple[set[tuple[int, int]], list[tuple[int, int, float, str]]]:
    """(scoring period, team id) for every team with a matchup, and score adjustments.

    An adjustment is filed under the last scoring period of its matchup.
    """
    periods = getattr(getattr(league, "settings", None), "matchup_periods", {}) or {}
    data = league.espn_request.league_get(params={"view": "mMatchupScore"})
    played: set[tuple[int, int]] = set()
    adjustments: list[tuple[int, int, float, str]] = []
    for matchup in data.get("schedule", []):
        scoring = [int(week) for week in periods.get(str(matchup.get("matchupPeriodId")), [])]
        sides = [matchup.get("home") or {}, matchup.get("away") or {}]
        for side in sides:
            amount = float(side.get("adjustment") or 0)
            if amount and scoring and side.get("teamId") is not None:
                reason = str(side.get("adjustmentReason") or "")
                adjustments.append((max(scoring), int(side["teamId"]), amount, reason))
        home, away = (side.get("teamId") for side in sides)
        if home is None or away is None:
            continue
        for week in scoring:
            played.add((week, int(home)))
            played.add((week, int(away)))
    return played, adjustments


def read_season(league: Any, year: int) -> SeasonMoves:
    """One season from a loaded League. Stops early if ESPN has no weekly data for it."""
    settings = getattr(league, "settings", None)
    regular = int(getattr(settings, "reg_season_count", 0) or 0)
    teams = _team_moves(league)
    slots = dict(getattr(settings, "position_slot_counts", {}) or {})
    end = league_end_week(league)
    latest = int(getattr(league, "current_week", end) or end)
    last_week = min(end, latest) if end else latest
    draft = _draft_entries(league, year)
    pickups: list[Pickup] = []
    drops: list[tuple[int, int]] = []
    listed: dict[str, Trade] = {}
    receipts: dict[str, int] = {}
    trade_drops: dict[tuple[str, int], tuple[int, int]] = {}
    lineups: list[LineupWeek] = []
    owners: dict[int, dict[int, int]] = {}
    names: dict[int, tuple[str, str]] = {}
    notes: list[str] = []
    skipped = 0
    weekly = False
    for week in range(1, last_week + 1):
        rosters_ok = transactions_ok = True
        try:
            found = read_lineups(league, week, slots)
            lineups.extend(found.rows)
            names.update(found.names)
            owners[week] = found.owners
        except Exception as exc:
            rosters_ok = False
            notes.append(f"Week {week} rosters failed: {exc}")
        try:
            raw = _fetch_transactions(league, week)
            found_moves = read_transactions(raw, draft)
            pickups.extend(found_moves.pickups)
            drops.extend(found_moves.drops)
            listed.update(found_moves.trades)
            for receipt, seen in found_moves.receipts.items():
                receipts[receipt] = max(seen, receipts.get(receipt, 0))
            trade_drops.update(found_moves.trade_drops)
            skipped += found_moves.skipped
            weekly = weekly or bool(raw)
        except Exception as exc:
            transactions_ok = False
            notes.append(f"Week {week} transactions failed: {exc}")
        if week == 1 and not rosters_ok and not transactions_ok:
            notes = ["ESPN returned no weekly rosters or transactions for this season."]
            break
    if lineups and not any(row.actual for row in lineups):
        if weekly:
            notes.append("Rosters came back without points.")
        else:
            lineups, owners = [], {}
            notes.append(
                "ESPN keeps only season totals for this season: its weekly rosters "
                "have no points and there are no transactions."
            )
    played: set[tuple[int, int]] = set()
    adjustments: list[tuple[int, int, float, str]] = []
    if lineups:
        try:
            played, adjustments = _fetch_schedule(league)
        except Exception as exc:
            notes.append(f"Schedule failed, so starts count every week: {exc}")
    if skipped:
        notes.append(f"Left out {skipped} draft picks entered as roster adds.")
    for player_id, name in (getattr(league, "player_map", {}) or {}).items():
        if isinstance(player_id, int) and isinstance(name, str):
            names.setdefault(player_id, (name, ""))
    unique_pickups = list({(p.week, p.team_id, p.player_id): p for p in pickups}.values())
    trades = [Trade(receipts[receipt], trade.pieces) for receipt, trade in listed.items()]
    unlisted: dict[int, int] = defaultdict(int)
    for receipt, week in receipts.items():
        if receipt not in listed:
            unlisted[week] += 1
    found_trades, trade_notes = roster_trades(
        owners,
        dict(unlisted),
        {(p.week, p.team_id, p.player_id) for p in pickups},
        {(trade.week, piece.player_id) for trade in trades for piece in trade.pieces},
    )
    trades.extend(found_trades)
    notes.extend(trade_notes)
    used = {pickup.player_id for pickup in unique_pickups} | {
        piece.player_id for trade in trades for piece in trade.pieces
    }
    used |= {player_id for row in lineups for player_id, _points in row.starters}
    return SeasonMoves(
        year,
        regular,
        teams,
        tuple(unique_pickups),
        tuple(
            sorted(
                trades,
                key=lambda trade: (trade.week, [(p.from_team, p.player_id) for p in trade.pieces]),
            )
        ),
        tuple(lineups),
        tuple(
            (player_id, name, position)
            for player_id, (name, position) in sorted(names.items())
            if player_id in used
        ),
        tuple(notes),
        tuple(drops) + tuple(trade_drops.values()),
        tuple(sorted(played)),
        weekly,
        tuple(sorted(adjustments)),
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
            tuple(
                (int(week), int(team), float(points), str(reason))
                for week, team, points, reason in data.get("adjustments", [])
            ),
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


def _counted(season: SeasonMoves) -> dict[int, tuple[int, int, int]]:
    """team -> (adds, drops, trades) counted from the transaction list."""
    adds: dict[int, int] = defaultdict(int)
    drops: dict[int, int] = defaultdict(int)
    trades: dict[int, int] = defaultdict(int)
    for pickup in season.pickups:
        adds[pickup.team_id] += 1
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
        )
        for team in season.teams
    }


def most_active(seasons: list[SeasonMoves]) -> tuple[ActiveRow, ...]:
    """Moves per person: counted from transactions when ESPN gave them, else its season counts.

    Seasons with neither are skipped. IR moves and FAAB always come from ESPN's counts.
    """
    totals: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0, 0, 0, 0])
    for season in seasons:
        if not season.weekly and not season.counters_kept:
            continue
        counted = _counted(season) if season.weekly else {}
        for team in season.teams:
            adds, drops, trades = counted.get(
                team.team_id, (team.acquisitions, team.drops, team.trades)
            )
            line = totals[team.person]
            line[0] += 1
            line[1] += adds
            line[2] += drops
            line[3] += trades
            line[4] += team.ir_moves
            line[5] += team.faab_spent
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
    """Team-weeks whose starters (plus any score adjustment) add up to ESPN's weekly score."""
    if record is None:
        return 0, 0
    scores = {
        (week.week, team_id): score for week in record.weeks for team_id, score in week.scores
    }
    adjusted: dict[tuple[int, int], float] = defaultdict(float)
    for week, team_id, points, _reason in season.adjustments:
        adjusted[(week, team_id)] += points
    checked = matched = 0
    for row in season.lineups:
        score = scores.get((row.week, row.team_id))
        if score is None:
            continue
        checked += 1
        total = row.actual + adjusted[(row.week, row.team_id)]
        matched += 1 if abs(score - total) < 0.05 else 0
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
