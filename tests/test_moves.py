"""Moves page: pickups, trades, season counts, and bench points from a fake ESPN league."""

import os
import sys
from types import SimpleNamespace
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date, datetime

from league_moves import (
    EASTERN,
    DraftEntries,
    TradePiece,
    best_lineup,
    dump_moves,
    kickoff_ms,
    load_moves_snapshot,
    moves_view,
    read_season,
    read_transactions,
    roster_trades,
)
from league_stats import SeasonRecord, TeamRecord, WeekScores

SLOTS = {"QB": 1, "RB": 1, "RB/WR/TE": 1, "D/ST": 1, "BE": 3, "IR": 1}

# player id -> (name, position, eligible slots)
PLAYERS = {
    1: ("Quinn QB", "QB", ("QB", "OP", "BE", "IR")),
    2: ("Ray RB", "RB", ("RB", "RB/WR/TE", "BE", "IR")),
    3: ("Will WR", "WR", ("WR", "RB/WR/TE", "BE", "IR")),
    4: ("Dan RB", "RB", ("RB", "RB/WR/TE", "BE", "IR")),
    5: ("Ed RB", "RB", ("RB", "RB/WR/TE", "BE", "IR")),
    6: ("Bears D/ST", "D/ST", ("D/ST", "BE")),
    7: ("Tim TE", "TE", ("TE", "RB/WR/TE", "BE", "IR")),
}

# week -> team id -> [(player id, slot, points)]
ROSTERS: dict[int, dict[int, list[tuple[int, str, float]]]] = {
    1: {
        1: [
            (1, "QB", 20.0),
            (2, "RB", 10.0),
            (3, "RB/WR/TE", 5.0),
            (6, "D/ST", 4.0),
            (4, "BE", 15.0),
        ],
        2: [(5, "RB", 9.0), (7, "RB/WR/TE", 6.0)],
    },
    2: {
        1: [
            (1, "QB", 18.0),
            (4, "RB", 30.0),
            (2, "RB/WR/TE", 8.0),
            (6, "D/ST", 2.0),
            (3, "IR", 40.0),
        ],
        2: [(5, "RB", 11.0), (7, "RB/WR/TE", 7.0)],
    },
    3: {
        1: [(1, "QB", 10.0), (5, "RB", 12.0), (2, "RB/WR/TE", 3.0), (6, "D/ST", 1.0)],
        2: [(4, "RB", 8.0), (7, "RB/WR/TE", 9.0)],
    },
}

TRADE_ITEMS = [
    {"type": "TRADE", "playerId": 4, "fromTeamId": 1, "toTeamId": 2},
    {"type": "TRADE", "playerId": 5, "fromTeamId": 2, "toTeamId": 1},
]

AFTER_KICKOFF = kickoff_ms(2023) + 60_000
BEFORE_KICKOFF = kickoff_ms(2023) - 60_000

TRANSACTIONS: dict[int, list[dict[str, Any]]] = {
    1: [
        # Ed RB, Joe's draft pick, entered as an add on draft night.
        {
            "status": "EXECUTED",
            "type": "FREEAGENT",
            "scoringPeriodId": 1,
            "proposedDate": BEFORE_KICKOFF,
            "teamId": 2,
            "items": [{"type": "ADD", "playerId": 5, "toTeamId": 2}],
        },
        # Free-agent adds have no processDate.
        {
            "status": "EXECUTED",
            "type": "FREEAGENT",
            "scoringPeriodId": 1,
            "proposedDate": AFTER_KICKOFF,
            "teamId": 2,
            "items": [{"type": "ADD", "playerId": 7, "toTeamId": 2}],
        },
        {
            "status": "EXECUTED",
            "type": "WAIVER",
            "scoringPeriodId": 1,
            "processDate": AFTER_KICKOFF,
            "teamId": 1,
            "bidAmount": 12,
            "items": [
                {"type": "ADD", "playerId": 4, "toTeamId": 1},
                {"type": "DROP", "playerId": 99, "fromTeamId": 1},
            ],
        },
        {
            "status": "FAILED_INVALIDPLAYERSOURCE",
            "type": "WAIVER",
            "scoringPeriodId": 1,
            "teamId": 2,
            "bidAmount": 20,
            "items": [{"type": "ADD", "playerId": 4, "toTeamId": 2}],
        },
    ],
    2: [
        # A plain drop, and a lineup change that isn't a move.
        {
            "status": "EXECUTED",
            "type": "ROSTER",
            "scoringPeriodId": 2,
            "teamId": 2,
            "items": [
                {"type": "DROP", "playerId": 98, "fromTeamId": 2},
                {"type": "LINEUP", "playerId": 7},
            ],
        },
    ],
    3: [
        # One trade: an accept per side and the commissioner's uphold, one with the players.
        # Joe's drop rides along on two of them and counts once.
        {"status": "PENDING", "type": "TRADE_PROPOSAL", "scoringPeriodId": 3, "items": TRADE_ITEMS},
        {
            "status": "EXECUTED",
            "type": "TRADE_ACCEPT",
            "scoringPeriodId": 3,
            "relatedTransactionId": "t1",
            "items": TRADE_ITEMS + [{"type": "DROP", "playerId": 97, "fromTeamId": 2}],
        },
        {
            "status": "EXECUTED",
            "type": "TRADE_ACCEPT",
            "scoringPeriodId": 3,
            "relatedTransactionId": "t1",
            "items": [{"type": "DROP", "playerId": 97, "fromTeamId": 2}],
        },
        {
            "status": "EXECUTED",
            "type": "TRADE_UPHOLD",
            "scoringPeriodId": 3,
            "id": "u1",
            "relatedTransactionId": "t1",
        },
    ],
}

# How ESPN shows a trade the logged-in member wasn't in: no players.
UNLISTED: dict[int, list[dict[str, Any]]] = {
    **TRANSACTIONS,
    3: [
        {
            "status": "EXECUTED",
            "type": "TRADE_ACCEPT",
            "scoringPeriodId": 3,
            "relatedTransactionId": "t1",
            "items": [],
        }
    ],
}


def matchup(period: int, home: int, away: int | None) -> dict[str, Any]:
    game: dict[str, Any] = {"matchupPeriodId": period, "home": {"teamId": home}}
    if away is not None:
        game["away"] = {"teamId": away}
    return game


FULL_SCHEDULE = [matchup(period, 1, 2) for period in (1, 2, 3)]


class FakeRequest:
    def __init__(
        self,
        broken_week: int | None = None,
        schedule: list[dict[str, Any]] | None = None,
        transactions: dict[int, list[dict[str, Any]]] | None = None,
    ) -> None:
        self.broken_week = broken_week
        self.schedule = FULL_SCHEDULE if schedule is None else schedule
        self.transactions = TRANSACTIONS if transactions is None else transactions
        self.weeks_asked: list[int] = []

    def league_get(
        self, params: dict[str, Any], headers: dict[str, str] | None = None
    ) -> dict[str, Any]:
        if params["view"] == "mMatchupScore":
            return {"schedule": self.schedule}
        week = int(params["scoringPeriodId"])
        assert params["view"] == "mTransactions2" and headers and "x-fantasy-filter" in headers
        self.weeks_asked.append(week)
        if week == self.broken_week:
            raise RuntimeError("503")
        return {"transactions": self.transactions.get(week, [])}


class DeadRequest:
    def league_get(self, params: dict[str, Any], headers: Any = None) -> dict[str, Any]:
        raise RuntimeError("leagueHistory returned a list")


def fake_player(player_id: int, slot: str, points: float, week: int) -> SimpleNamespace:
    name, position, eligible = PLAYERS[player_id]
    return SimpleNamespace(
        playerId=player_id,
        name=name,
        position=position,
        eligibleSlots=list(eligible),
        lineupSlot=slot,
        stats={week: {"points": points}},
    )


class FakeLeague:
    def __init__(
        self,
        counters: bool = True,
        broken_week: int | None = None,
        schedule: list[dict[str, Any]] | None = None,
        dead: bool = False,
        transactions: dict[int, list[dict[str, Any]]] | None = None,
        pointless: bool = False,
    ) -> None:
        def team(team_id: int, name: str, adds: int) -> SimpleNamespace:
            return SimpleNamespace(
                team_id=team_id,
                team_name=name,
                owners=[],
                roster=[],
                acquisitions=adds if counters else 0,
                drops=adds if counters else 0,
                trades=1 if counters else 0,
                move_to_ir=1 if counters else 0,
                acquisition_budget_spent=12 if counters and team_id == 1 else 0,
            )

        self.teams = [team(1, "Eli", 5), team(2, "Joe", 2)]
        # ESPN's season runs to week 5; the league's last matchup ends week 3.
        self.settings = SimpleNamespace(
            reg_season_count=2,
            position_slot_counts=SLOTS,
            matchup_periods={"1": [1], "2": [2], "3": [3]},
        )
        self.finalScoringPeriod = 5
        self.current_week = 5
        self.player_map = {pid: name for pid, (name, _pos, _slots) in PLAYERS.items()}
        self.draft = [SimpleNamespace(team=self.teams[1], playerId=5)]
        self.dead = dead
        # Like ESPN before 2018: the final roster every week, no points, no transactions.
        self.pointless = pointless
        if pointless:
            transactions = {}
        self.espn_request: Any = (
            DeadRequest() if dead else FakeRequest(broken_week, schedule, transactions)
        )

    def load_roster_week(self, week: int) -> None:
        if self.dead:
            raise RuntimeError("no rosters")
        for team in self.teams:
            team.roster = [
                fake_player(pid, slot, 0.0 if self.pointless else points, week)
                for pid, slot, points in ROSTERS[3 if self.pointless else week].get(
                    team.team_id, []
                )
            ]


def history_record() -> SeasonRecord:
    return SeasonRecord(
        2023,
        (
            TeamRecord(1, "Eli", "Eli", 2, 0, 0, 0.0, 1),
            TeamRecord(2, "Joe", "Joe", 0, 2, 0, 0.0),
        ),
        (),
        (WeekScores(1, ((1, 39.0), (2, 15.0))), WeekScores(2, ((1, 58.0), (2, 99.0)))),
    )


def test_best_lineup_fills_single_slots_first() -> None:
    pool = [
        (("RB", "RB/WR/TE"), 30.0),
        (("WR", "RB/WR/TE"), 25.0),
        (("RB", "RB/WR/TE"), 5.0),
        (("D/ST",), 7.0),
    ]
    assert best_lineup(pool, {"RB": 1, "RB/WR/TE": 1, "D/ST": 1, "BE": 5}) == 62.0
    # The flex slot doesn't steal the only RB.
    assert best_lineup([(("RB", "RB/WR/TE"), 9.0)], {"RB/WR/TE": 1, "RB": 1}) == 9.0


def test_transactions_skip_draft_entries_and_keep_executed_moves() -> None:
    draft = DraftEntries(kickoff_ms(2023), frozenset({(2, 5)}))
    found = read_transactions(TRANSACTIONS[1] + TRANSACTIONS[2] + TRANSACTIONS[3], draft)
    assert [(p.team_id, p.player_id, p.kind, p.bid) for p in found.pickups] == [
        (2, 7, "FREEAGENT", 0),
        (1, 4, "WAIVER", 12),
    ]
    assert found.skipped == 1
    # The waiver drop and the plain drop; the trade's drop is kept once, by receipt.
    assert found.drops == [(1, 1), (2, 2)]
    assert found.trade_drops == {("t1", 97): (3, 2)}
    assert found.receipts == {"t1": 3} and list(found.trades) == ["t1"]
    assert {(piece.player_id, piece.to_team) for piece in found.trades["t1"].pieces} == {
        (4, 2),
        (5, 1),
    }
    assert len(read_transactions(TRANSACTIONS[1]).pickups) == 3


def test_draft_entries_by_the_commissioner_or_on_entry_days() -> None:
    def add(when: int, **extra: Any) -> dict[str, Any]:
        return {
            "status": "EXECUTED",
            "type": "FREEAGENT",
            "scoringPeriodId": 1,
            "proposedDate": when,
            "teamId": 2,
            "items": [{"type": "ADD", "playerId": 7, "toTeamId": 2}],
            **extra,
        }

    draft = DraftEntries(kickoff_ms(2023))
    # A preseason pickup counts; the commissioner adding for a team before kickoff doesn't.
    assert read_transactions([add(BEFORE_KICKOFF)], draft).skipped == 0
    assert read_transactions([add(BEFORE_KICKOFF, isLeagueManager=True)], draft).skipped == 1
    assert read_transactions([add(AFTER_KICKOFF, isLeagueManager=True)], draft).skipped == 0
    entry_day = datetime.fromtimestamp(BEFORE_KICKOFF / 1000, EASTERN).date()
    days = DraftEntries(kickoff_ms(2023), days=(entry_day,))
    assert read_transactions([add(BEFORE_KICKOFF)], days).skipped == 1
    other_day = DraftEntries(kickoff_ms(2023), days=(date(2023, 8, 1),))
    assert read_transactions([add(BEFORE_KICKOFF)], other_day).skipped == 0


def test_read_season_stops_at_the_league_end_and_counts_each_trade_once() -> None:
    league = FakeLeague()
    season = read_season(league, 2023)
    assert league.espn_request.weeks_asked == [1, 2, 3]
    assert season.counters_kept and season.weekly
    assert len(season.trades) == 1 and season.trades[0].week == 3
    assert sorted(season.drops) == [(1, 1), (2, 2), (3, 2)]
    weeks = {(row.week, row.team_id): row for row in season.lineups}
    first = weeks[(1, 1)]
    assert first.actual == 39.0
    # Dan RB (15 on the bench) for Ray RB in RB, Ray to flex over Will WR (5).
    assert first.best == 49.0
    # Will WR's 40 on IR doesn't count as left on the bench.
    assert weeks[(2, 1)].best == weeks[(2, 1)].actual == 58.0
    assert season.notes == ("Left out 1 draft picks entered as roster adds.",)


def test_unlisted_trades_come_from_roster_changes() -> None:
    listed = read_season(FakeLeague(), 2023)
    unlisted = read_season(FakeLeague(transactions=UNLISTED), 2023)
    assert unlisted.trades == listed.trades
    assert "Ed RB" in {name for _pid, name, _pos in unlisted.players}


def test_roster_trades_route_a_same_week_flip() -> None:
    # Week 2: A (1) trades player 10 to B (2) for 11, and B flips 10 to C (3) for 20.
    owners = {1: {10: 1, 11: 2, 20: 3}, 2: {10: 3, 11: 1, 20: 2}}
    trades, notes = roster_trades(owners, {2: 2}, set(), set())
    assert notes == []
    assert {trade.pieces for trade in trades} == {
        (TradePiece(10, 1, 2), TradePiece(11, 2, 1)),
        (TradePiece(10, 2, 3), TradePiece(20, 3, 2)),
    }
    # A pickup isn't a trade, and weeks without a receipt aren't searched.
    assert roster_trades(owners, {2: 1}, {(2, 3, 10), (2, 1, 11), (2, 2, 20)}, set())[0] == []
    assert roster_trades(owners, {}, set(), set()) == ([], [])
    # More receipts than roster changes: no flip routing, and a note.
    trades, notes = roster_trades(owners, {2: 4}, set(), set())
    assert len(trades) == 3
    assert notes == ["Week 2: ESPN has 4 trades without players; the rosters show 3."]


def test_moves_view_numbers() -> None:
    season = read_season(FakeLeague(), 2023)
    view = moves_view({2023: season}, {2023: history_record()})
    status = view.status[0]
    assert (status.roster_weeks, status.pickups, status.trades) == (3, 2, 1)
    assert (status.checked, status.matched) == (4, 3)

    overall = view.pickups["overall"]
    # Dan RB: benched week 1, started week 2 for 30, traded away week 3.
    dan = overall[""][0]
    assert (dan.person, dan.player, dan.points, dan.starts) == ("Eli", "Dan RB", 30.0, 1)
    assert dan.how == "Waiver $12" and overall["Eli"] == (dan,)
    # Tim TE for Joe: 6 + 7 + 9.
    tim = overall["Joe"][0]
    assert (tim.player, tim.points, tim.starts, tim.how) == ("Tim TE", 22.0, 3, "Free agent")
    # Joe isn't a playoff team, so Tim's week 3 is the losers' bracket.
    assert [(r.player, r.points) for r in view.pickups["regular"][""]] == [
        ("Dan RB", 30.0),
        ("Tim TE", 13.0),
    ]
    assert [(r.player, r.points) for r in view.pickups["losers"][""]] == [("Tim TE", 9.0)]
    assert view.pickups["winners"][""] == ()

    sides = {side.person: side for side in view.trades[0].sides}
    assert sides["Eli"].points == 12.0 and sides["Eli"].won
    assert sides["Joe"].points == 8.0 and not sides["Joe"].won
    assert ("Eli", 1, 1, 0) in view.trade_records

    bench = {row.person: row for row in view.bench}
    assert bench["Eli"].weeks == 2 and bench["Eli"].left == 10.0 and bench["Eli"].perfect == 1
    assert bench["Eli"].perfect_pct == "50%"
    assert view.bench_worst[0].person == "Eli" and view.bench_worst[0].left == 10.0

    # Counted from transactions, not ESPN's counters (5 and 2 adds); FAAB is ESPN's.
    active = {row.person: row for row in view.active}
    assert (active["Eli"].adds, active["Eli"].drops, active["Eli"].trades) == (1, 1, 1)
    assert active["Eli"].faab == 12 and active["Eli"].ir_moves == 1
    assert (active["Joe"].adds, active["Joe"].drops, active["Joe"].trades) == (1, 2, 1)
    assert active["Joe"].faab == 0


def test_score_adjustments_count_in_the_lineup_check() -> None:
    schedule = [matchup(1, 1, 2), matchup(2, 1, 2), matchup(3, 1, 2)]
    schedule[1]["away"].update(adjustment=81.0, adjustmentReason="stat fix")
    season = read_season(FakeLeague(schedule=schedule), 2023)
    assert season.adjustments == ((2, 2, 81.0, "stat fix"),)
    status = moves_view({2023: season}, {2023: history_record()}).status[0]
    assert (status.checked, status.matched) == (4, 4)


def test_starts_only_count_in_weeks_with_a_game() -> None:
    # Eli has a bye in week 3, so Ed RB's 12 for Eli that week doesn't count.
    schedule = [matchup(1, 1, 2), matchup(2, 1, 2), matchup(3, 1, None), matchup(3, 2, 9)]
    season = read_season(FakeLeague(schedule=schedule), 2023)
    sides = {side.person: side for side in moves_view({2023: season}).trades[0].sides}
    assert sides["Eli"].points == 0.0 and sides["Joe"].won


def test_old_seasons_and_missing_counters() -> None:
    quiet = read_season(FakeLeague(counters=False), 2023)
    assert not quiet.counters_kept and quiet.weekly
    assert moves_view({2023: quiet}).active != ()
    old = read_season(FakeLeague(dead=True), 2015)
    assert old.lineups == () and not old.weekly
    assert old.notes == ("ESPN returned no weekly rosters or transactions for this season.",)
    view = moves_view({2015: old})
    assert view.status[0].counters
    assert {row.person: row.adds for row in view.active} == {"Eli": 5, "Joe": 2}
    nothing = read_season(FakeLeague(counters=False, dead=True), 2014)
    assert moves_view({2014: nothing}).active == ()


def test_seasons_with_only_totals() -> None:
    # Before 2018 ESPN repeats the final roster every week with no points.
    old = read_season(FakeLeague(pointless=True), 2015)
    assert old.lineups == () and not old.weekly and old.trades == ()
    assert old.notes == (
        "ESPN keeps only season totals for this season: its weekly rosters "
        "have no points and there are no transactions.",
    )
    view = moves_view({2015: old})
    assert view.status[0].roster_weeks == 0 and view.bench == ()
    assert {row.person: row.adds for row in view.active} == {"Eli": 5, "Joe": 2}


def test_a_failed_week_is_noted() -> None:
    season = read_season(FakeLeague(broken_week=3), 2023)
    assert season.trades == ()
    assert any("Week 3 transactions failed" in note for note in season.notes)


def test_snapshot_round_trip() -> None:
    schedule = [matchup(1, 1, 2), matchup(2, 1, 2), matchup(3, 1, 2)]
    schedule[0]["home"].update(adjustment=2.0, adjustmentReason="colts d")
    season = read_season(FakeLeague(schedule=schedule), 2023)
    assert season.adjustments
    assert load_moves_snapshot(dump_moves({2023: season})) == {2023: season}


def main() -> None:
    test_best_lineup_fills_single_slots_first()
    test_transactions_skip_draft_entries_and_keep_executed_moves()
    test_draft_entries_by_the_commissioner_or_on_entry_days()
    test_read_season_stops_at_the_league_end_and_counts_each_trade_once()
    test_unlisted_trades_come_from_roster_changes()
    test_roster_trades_route_a_same_week_flip()
    test_moves_view_numbers()
    test_score_adjustments_count_in_the_lineup_check()
    test_starts_only_count_in_weeks_with_a_game()
    test_old_seasons_and_missing_counters()
    test_seasons_with_only_totals()
    test_a_failed_week_is_noted()
    test_snapshot_round_trip()
    print("moves ok")


if __name__ == "__main__":
    main()
