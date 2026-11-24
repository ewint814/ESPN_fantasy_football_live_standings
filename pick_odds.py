"""
Pick-your-opponent odds for the last three regular-season weeks.

Weeks 12-14 have no fixed schedule. Each week teams pick their opponents in turn,
skipping anyone already taken:

- week 12: standings order, first place picks first;
- week 13: reverse standings, last place picks first;
- week 14: middle out, 6th then 7th, 5th, 8th, ... 1st, 12th.

Every week also has the median game: the top half of the week's scores get a win.
Seeds 1-5 go by record (points for breaks ties), seed 6 is the most points among
everyone else, and seeds 1-2 get byes.

The odds come from playing the rest of the season out many times. Each team's
score in a week is drawn from a normal curve around what it usually scores (and
ESPN's projection, for the week about to be played). Teams that pick after the
one on the clock are assumed to take the weakest opponent left.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass
from math import erf
from statistics import fmean, pstdev
from typing import Any

PICK_WEEKS = (12, 13, 14)
LAST_REGULAR_WEEK = 14
SEEDS_BY_RECORD = 5
BYES = 2
SIMULATIONS = 2000
# Weeks of league-average scoring blended into each team's own average.
SHRINK_WEEKS = 4
# How much a week that is underway still varies, against a whole week.
LIVE_SPREAD = 0.5


@dataclass(frozen=True)
class PickTeam:
    team_id: int
    name: str
    person: str
    wins: int
    losses: int
    ties: int
    points_for: float
    scores: tuple[float, ...]


@dataclass(frozen=True)
class PickState:
    """The league going into ``week``: records through the week before it."""

    week: int
    teams: tuple[PickTeam, ...]
    standings: tuple[int, ...]
    # ESPN's projected totals for ``week``, when ESPN has them.
    projected: dict[int, float]
    # Matchups for ``week`` once its games have started, so the picks are in.
    locked: tuple[tuple[int, int], ...] = ()
    # ESPN's schedule for ``week``: the default until the commissioner enters the picks.
    espn_pairs: tuple[tuple[int, int], ...] = ()


@dataclass(frozen=True)
class Odds:
    bye: float
    top_five: float
    points_spot: float
    playoffs: float
    average_seed: float


@dataclass(frozen=True)
class Option:
    opponent: int
    win: float
    odds: Odds


@dataclass(frozen=True)
class PickBoard:
    week: int
    order: tuple[int, ...]
    made: tuple[tuple[int, int], ...]
    on_clock: int | None
    options: tuple[Option, ...]
    assumed: tuple[tuple[int, int], ...]
    league: dict[int, Odds]
    locked: bool


def pick_order(week: int, standings: tuple[int, ...]) -> tuple[int, ...]:
    """Who picks when in ``week``, from standings going into it (first place first)."""
    if week == PICK_WEEKS[0]:
        return standings
    if week == PICK_WEEKS[1]:
        return tuple(reversed(standings))
    middle = len(standings) // 2
    places = [middle - k // 2 if k % 2 == 0 else middle + 1 + k // 2 for k in range(len(standings))]
    return tuple(standings[place - 1] for place in places)


def rank(
    teams: tuple[int, ...], wins: dict[int, float], points: dict[int, float]
) -> tuple[int, ...]:
    """Standings: most wins first (a tie is half a win), then most points."""
    return tuple(sorted(teams, key=lambda team: (-wins[team], -points[team])))


def seeds(order: tuple[int, ...], points: dict[int, float]) -> dict[int, int]:
    """Playoff seed per team, 0 for out: 1-5 by record, then the most points left."""
    seeded = {team: place for place, team in enumerate(order[:SEEDS_BY_RECORD], start=1)}
    rest = order[SEEDS_BY_RECORD:]
    if rest:
        seeded[max(rest, key=lambda team: points[team])] = SEEDS_BY_RECORD + 1
    return {team: seeded.get(team, 0) for team in order}


def score_curves(state: PickState) -> tuple[dict[int, float], dict[int, float], float]:
    """Each team's usual score, its score for ``state.week``, and the league's spread."""
    played = {
        team.team_id: [s for s in team.scores[: state.week - 1] if s > 0] for team in state.teams
    }
    every = [score for scores in played.values() for score in scores]
    league_mean = fmean(every) if every else 100.0
    spread = (
        pstdev([s - fmean(scores) for scores in played.values() if scores for s in scores])
        if every
        else 25.0
    ) or 25.0
    usual = {
        team: (sum(scores) + SHRINK_WEEKS * league_mean) / (len(scores) + SHRINK_WEEKS)
        for team, scores in played.items()
    }
    this_week = {
        team: (mean + state.projected[team]) / 2 if state.projected.get(team, 0) > 0 else mean
        for team, mean in usual.items()
    }
    if state.locked:
        this_week = {team: state.projected.get(team) or mean for team, mean in usual.items()}
    return usual, this_week, spread


def _fill_picks(
    order: tuple[int, ...],
    made: tuple[tuple[int, int], ...],
    strength: dict[int, float],
) -> tuple[tuple[int, int], ...]:
    """Finish a week's picks: everyone still unpaired takes the weakest team left."""
    paired = {team for pair in made for team in pair}
    pairs = list(made)
    for picker in order:
        if picker in paired:
            continue
        left = [team for team in order if team not in paired and team != picker]
        if not left:
            break
        opponent = min(left, key=lambda team: (strength[team], order.index(team)))
        pairs.append((picker, opponent))
        paired.update((picker, opponent))
    return tuple(pairs)


def _play(
    pairs: tuple[tuple[int, int], ...],
    scores: dict[int, float],
    wins: dict[int, float],
    points: dict[int, float],
) -> None:
    for home, away in pairs:
        if scores[home] > scores[away]:
            wins[home] += 1
        elif scores[away] > scores[home]:
            wins[away] += 1
        else:
            wins[home] += 0.5
            wins[away] += 0.5
    ranked = sorted(scores, key=lambda team: -scores[team])
    for team in ranked[: len(ranked) // 2]:
        wins[team] += 1
    for team, score in scores.items():
        points[team] += score


def _simulate(
    state: PickState,
    first_week: tuple[tuple[int, int], ...],
    draws: list[list[list[float]]],
) -> dict[int, list[int]]:
    """Seeds per team across every simulated season, with ``first_week`` fixed."""
    usual, this_week, spread = score_curves(state)
    ids = tuple(team.team_id for team in state.teams)
    live = LIVE_SPREAD if state.locked else 1.0
    out: dict[int, list[int]] = {team: [] for team in ids}
    for run in draws:
        wins = {team.team_id: team.wins + team.ties / 2 for team in state.teams}
        points = {team.team_id: team.points_for for team in state.teams}
        for offset, noise in enumerate(run):
            week = state.week + offset
            means = this_week if offset == 0 else usual
            scale = live if offset == 0 else 1.0
            scores = {
                team: max(0.0, means[team] + spread * scale * z)
                for team, z in zip(ids, noise, strict=True)
            }
            if offset == 0:
                pairs = first_week
            else:
                order = pick_order(week, rank(ids, wins, points))
                pairs = _fill_picks(order, (), usual)
            _play(pairs, scores, wins, points)
        for team, seed in seeds(rank(ids, wins, points), points).items():
            out[team].append(seed)
    return out


def _odds(seeds_seen: list[int]) -> Odds:
    runs = len(seeds_seen) or 1
    made = [seed for seed in seeds_seen if seed]
    return Odds(
        bye=sum(1 for seed in made if seed <= BYES) / runs,
        top_five=sum(1 for seed in made if seed <= SEEDS_BY_RECORD) / runs,
        points_spot=sum(1 for seed in made if seed > SEEDS_BY_RECORD) / runs,
        playoffs=len(made) / runs,
        average_seed=fmean(made) if made else 0.0,
    )


def _draws(state: PickState, runs: int, seed: int) -> list[list[list[float]]]:
    """Shared random numbers, so every option faces the same seasons."""
    rng = random.Random(seed)
    weeks = LAST_REGULAR_WEEK - state.week + 1
    count = len(state.teams)
    return [[[rng.gauss(0, 1) for _ in range(count)] for _ in range(weeks)] for _ in range(runs)]


def valid_made(
    order: tuple[int, ...], made: tuple[tuple[int, int], ...]
) -> tuple[tuple[int, int], ...]:
    """The longest run of ``made`` that follows the pick order."""
    kept: list[tuple[int, int]] = []
    paired: set[int] = set()
    queue = list(order)
    for picker, opponent in made:
        while queue and queue[0] in paired:
            queue.pop(0)
        if not queue or queue[0] != picker or opponent in paired or opponent == picker:
            break
        if opponent not in order:
            break
        kept.append((picker, opponent))
        paired.update((picker, opponent))
    return tuple(kept)


def on_the_clock(order: tuple[int, ...], made: tuple[tuple[int, int], ...]) -> int | None:
    paired = {team for pair in made for team in pair}
    unpaired = [team for team in order if team not in paired]
    return unpaired[0] if len(unpaired) >= 2 else None


def pick_board(
    state: PickState,
    made: tuple[tuple[int, int], ...] = (),
    runs: int = SIMULATIONS,
    seed: int = 12,
) -> PickBoard:
    """The week's pick order, the team on the clock, and its odds against each choice."""
    order = pick_order(state.week, state.standings)
    _usual, this_week, spread = score_curves(state)
    draws = _draws(state, runs, seed)
    if state.locked:
        made = made_from_pairs(order, state.locked)
        assumed = made
        on_clock = None
    else:
        made = valid_made(order, made)
        on_clock = on_the_clock(order, made)
        assumed = _fill_picks(order, made, this_week)
    league = {team: _odds(seen) for team, seen in _simulate(state, assumed, draws).items()}
    options: list[Option] = []
    if on_clock is not None:
        paired = {team for pair in made for team in pair}
        for opponent in (team for team in order if team not in paired and team != on_clock):
            week_pairs = _fill_picks(order, made + ((on_clock, opponent),), this_week)
            seen = _simulate(state, week_pairs, draws)[on_clock]
            options.append(
                Option(opponent, _win_chance(this_week, spread, on_clock, opponent), _odds(seen))
            )
        options.sort(
            key=lambda option: (
                -round(option.odds.playoffs * 100),
                -round(option.odds.bye * 100),
                -option.win,
            )
        )
    return PickBoard(
        week=state.week,
        order=order,
        made=made,
        on_clock=on_clock,
        options=tuple(options),
        assumed=assumed,
        league=league,
        locked=bool(state.locked),
    )


def parse_made(text: str) -> tuple[tuple[int, int], ...]:
    """Picks from a link, written ``picker-opponent`` and comma separated."""
    made: list[tuple[int, int]] = []
    for part in text.split(","):
        picker, _, opponent = part.partition("-")
        if not picker.strip().isdigit() or not opponent.strip().isdigit():
            break
        made.append((int(picker), int(opponent)))
    return tuple(made)


def made_text(made: tuple[tuple[int, int], ...]) -> str:
    return ",".join(f"{picker}-{opponent}" for picker, opponent in made)


def made_from_pairs(
    order: tuple[int, ...], pairs: tuple[tuple[int, int], ...]
) -> tuple[tuple[int, int], ...]:
    """Matchups written as picks: each team, in pick order, picked the team it plays."""
    partner = dict(pairs) | {b: a for a, b in pairs}
    made: list[tuple[int, int]] = []
    paired: set[int] = set()
    for picker in order:
        if picker in paired or picker not in partner:
            continue
        made.append((picker, partner[picker]))
        paired.update((picker, partner[picker]))
    return tuple(made)


def state_from_league(league: Any, person: Callable[[Any], str]) -> PickState | None:
    """The pick week ESPN is on, or None outside weeks 12-14."""
    week = int(league.current_week)
    if week not in PICK_WEEKS:
        return None
    teams = tuple(
        PickTeam(
            team_id=int(team.team_id),
            name=str(team.team_name).strip(),
            person=person(team),
            wins=int(team.wins),
            losses=int(team.losses),
            ties=int(team.ties),
            points_for=float(team.points_for),
            scores=tuple(float(score or 0) for score in team.scores),
        )
        for team in league.teams
    )
    standings = tuple(
        int(team.team_id) for team in sorted(league.teams, key=lambda team: team.standing)
    )
    projected: dict[int, float] = {}
    pairs: list[tuple[int, int]] = []
    started = False
    for box in league.box_scores(week):
        if not box.home_team or not box.away_team:
            continue
        home, away = int(box.home_team.team_id), int(box.away_team.team_id)
        pairs.append((home, away))
        projected[home] = float(box.home_projected or 0)
        projected[away] = float(box.away_projected or 0)
        started = started or bool(box.home_score) or bool(box.away_score)
    return PickState(
        week=week,
        teams=teams,
        standings=standings,
        projected=projected,
        locked=tuple(pairs) if started else (),
        espn_pairs=tuple(pairs),
    )


def _win_chance(means: dict[int, float], spread: float, team: int, opponent: int) -> float:
    """Chance ``team`` outscores ``opponent`` this week: both scores vary by ``spread``."""
    return 0.5 * (1 + erf((means[team] - means[opponent]) / (2 * spread)))
