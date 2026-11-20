"""Moves page: pickups, trades, season counts, and bench points from a fake ESPN league."""

import os
import sys
from types import SimpleNamespace
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from league_moves import (
    best_lineup,
    dump_moves,
    load_moves_snapshot,
    moves_view,
    read_season,
    read_transactions,
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

TRANSACTIONS: dict[int, list[dict[str, Any]]] = {
    1: [
        {
            "status": "EXECUTED",
            "type": "WAIVER",
            "scoringPeriodId": 1,
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
    3: [
        {
            "status": "EXECUTED",
            "type": "TRADE_PROPOSAL",
            "scoringPeriodId": 3,
            "items": TRADE_ITEMS,
        },
        {"status": "EXECUTED", "type": "TRADE_ACCEPT", "scoringPeriodId": 3, "items": TRADE_ITEMS},
    ],
}


class FakeRequest:
    def __init__(self, broken_week: int | None = None) -> None:
        self.broken_week = broken_week

    def league_get(self, params: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        week = int(params["scoringPeriodId"])
        assert params["view"] == "mTransactions2" and "x-fantasy-filter" in headers
        if week == self.broken_week:
            raise RuntimeError("503")
        return {"transactions": TRANSACTIONS.get(week, [])}


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
    def __init__(self, counters: bool = True, broken_week: int | None = None) -> None:
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
        self.settings = SimpleNamespace(reg_season_count=2, position_slot_counts=SLOTS)
        self.finalScoringPeriod = 3
        self.current_week = 3
        self.player_map = {pid: name for pid, (name, _pos, _slots) in PLAYERS.items()}
        self.espn_request = FakeRequest(broken_week)

    def load_roster_week(self, week: int) -> None:
        for team in self.teams:
            team.roster = [
                fake_player(pid, slot, points, week)
                for pid, slot, points in ROSTERS[week].get(team.team_id, [])
            ]


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


def test_transactions_keep_executed_pickups_and_trades() -> None:
    pickups, trades = read_transactions(TRANSACTIONS[1] + TRANSACTIONS[3])
    assert [(p.team_id, p.player_id, p.kind, p.bid) for p in pickups] == [(1, 4, "WAIVER", 12)]
    assert len(trades) == 2
    assert {(piece.player_id, piece.to_team) for piece in trades[0].pieces} == {(4, 2), (5, 1)}


def test_read_season_lineups_and_dedupes_trades() -> None:
    season = read_season(FakeLeague(), 2023)
    assert season.counters_kept
    assert len(season.trades) == 1 and season.trades[0].week == 3
    weeks = {(row.week, row.team_id): row for row in season.lineups}
    first = weeks[(1, 1)]
    assert first.actual == 39.0
    # Dan RB (15 on the bench) for Ray RB in RB, Ray to flex over Will WR (5).
    assert first.best == 49.0
    # Will WR's 40 on IR doesn't count as left on the bench.
    assert weeks[(2, 1)].best == weeks[(2, 1)].actual == 58.0
    assert not season.notes


def test_moves_view_numbers() -> None:
    season = read_season(FakeLeague(), 2023)
    record = SeasonRecord(
        2023,
        (TeamRecord(1, "Eli", "Eli", 2, 0, 0, 0.0), TeamRecord(2, "Joe", "Joe", 0, 2, 0, 0.0)),
        (),
        (WeekScores(1, ((1, 39.0), (2, 15.0))), WeekScores(2, ((1, 58.0), (2, 99.0)))),
    )
    view = moves_view({2023: season}, {2023: record})
    status = view.status[0]
    assert (status.roster_weeks, status.pickups, status.trades) == (3, 1, 1)
    assert (status.checked, status.matched) == (4, 3)

    pickup = view.pickups[""][0]
    # Dan RB: benched week 1, started week 2 for 30, traded away week 3.
    assert (pickup.person, pickup.player, pickup.points, pickup.starts) == (
        "Eli",
        "Dan RB",
        30.0,
        1,
    )
    assert pickup.how == "Waiver $12"
    assert "Joe" not in view.pickups

    trade = view.trades[0]
    sides = {side.person: side for side in trade.sides}
    assert sides["Eli"].points == 12.0 and sides["Eli"].won
    assert sides["Joe"].points == 8.0 and not sides["Joe"].won
    assert ("Eli", 1, 1, 0) in view.trade_records

    bench = {row.person: row for row in view.bench}
    assert bench["Eli"].weeks == 2 and bench["Eli"].left == 10.0 and bench["Eli"].perfect == 1
    assert view.bench_worst[0].person == "Eli" and view.bench_worst[0].left == 10.0

    active = {row.person: row for row in view.active}
    assert active["Eli"].adds == 5 and active["Eli"].faab == 12


def test_missing_counters_and_old_seasons() -> None:
    quiet = read_season(FakeLeague(counters=False), 2023)
    assert not quiet.counters_kept
    assert moves_view({2023: quiet}).active == ()
    old = read_season(FakeLeague(), 2015)
    assert old.lineups == () and "before 2019" in old.notes[0]
    assert moves_view({2015: old}).status[0].counters


def test_a_failed_week_is_noted() -> None:
    season = read_season(FakeLeague(broken_week=3), 2023)
    assert season.trades == ()
    assert any("Week 3 transactions failed" in note for note in season.notes)


def test_snapshot_round_trip() -> None:
    season = read_season(FakeLeague(), 2023)
    assert load_moves_snapshot(dump_moves({2023: season})) == {2023: season}


def main() -> None:
    test_best_lineup_fills_single_slots_first()
    test_transactions_keep_executed_pickups_and_trades()
    test_read_season_lineups_and_dedupes_trades()
    test_moves_view_numbers()
    test_missing_counters_and_old_seasons()
    test_a_failed_week_is_noted()
    test_snapshot_round_trip()
    print("moves ok")


if __name__ == "__main__":
    main()
