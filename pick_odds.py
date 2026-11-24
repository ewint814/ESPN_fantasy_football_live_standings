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
score in a week is drawn from a normal curve around an expected score, which can
come from ESPN's projections, the season average, the last four weeks, or a blend.
Teams that pick after the one on the clock take the weakest team left, the pick
that gives them the best playoff odds ("smart", this week only), or anyone at random.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass, field
from math import erf
from statistics import fmean, pstdev
from typing import Any

PICK_WEEKS = (12, 13, 14)
LAST_REGULAR_WEEK = 14
SEEDS_BY_RECORD = 5
BYES = 2
SIMULATIONS = 2000
# Fewer seasons for each look-ahead inside smart picks and the chaos search.
QUICK_SIMULATIONS = 250
COMPARE_SIMULATIONS = 600
COMPARE_QUICK = 80
# Weeks of league-average scoring blended into each team's own average.
SHRINK_WEEKS = 4
RECENT_WEEKS = 4
# How much a week that is underway still varies, against a whole week.
LIVE_SPREAD = 0.5
# A team with at least this playoff chance is still alive.
ALIVE = 0.01

SOURCES = {
    "espn": "ESPN projections",
    "season": "Season average",
    "recent": f"Last {RECENT_WEEKS} weeks",
    "blend": "Blend",
}
PICKERS = {"weakest": "Weakest left", "smart": "Smart", "random": "Random"}
GOALS = {"bye": "Bye", "top_five": "Top 5", "points_spot": "6th (points)", "playoffs": "Playoffs"}

OUT_FOR_GOOD = {"INJURY_RESERVE", "SUSPENSION"}
NOT_STARTING = {"BE", "IR", ""}


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
    # Best lineup from ESPN's rest-of-season player projections, by week then team.
    rest: dict[int, dict[int, float]] = field(default_factory=dict)


@dataclass(frozen=True)
class Settings:
    source: str = "espn"
    picker: str = "weakest"
    goal: str = "playoffs"

    @classmethod
    def read(cls, source: str, picker: str, goal: str) -> Settings:
        return cls(
            source if source in SOURCES else cls.source,
            picker if picker in PICKERS else cls.picker,
            goal if goal in GOALS else cls.goal,
        )


@dataclass(frozen=True)
class Odds:
    bye: float
    top_five: float
    points_spot: float
    playoffs: float
    average_seed: float

    def goal(self, goal: str) -> float:
        return float(getattr(self, goal))


@dataclass(frozen=True)
class Option:
    opponent: int
    win: float
    odds: Odds
    alive: int


@dataclass(frozen=True)
class Chaos:
    """The rest of the week's picks that leave the most teams with a playoff chance."""

    picks: tuple[tuple[int, int], ...]
    alive: int
    league: dict[int, Odds]


@dataclass(frozen=True)
class PickBoard:
    week: int
    order: tuple[int, ...]
    made: tuple[tuple[int, int], ...]
    on_clock: int | None
    options: tuple[Option, ...]
    assumed: tuple[tuple[int, int], ...]
    league: dict[int, Odds]
    alive: int
    locked: bool
    settings: Settings
    chaos: Chaos | None = None
    # Goal odds for each option under every score source, by opponent then source.
    compare: dict[int, dict[str, float]] | None = None


@dataclass(frozen=True)
class Curves:
    """Expected score per week and team, and how much a week's score varies."""

    means: dict[int, dict[int, float]]
    spread: float


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


def curves(state: PickState, source: str) -> Curves:
    """Expected scores for every week left, from ``source``."""
    played = {
        team.team_id: [score for score in team.scores[: state.week - 1] if score > 0]
        for team in state.teams
    }
    every = [score for scores in played.values() for score in scores]
    league_mean = fmean(every) if every else 100.0
    residuals = [s - fmean(scores) for scores in played.values() if scores for s in scores]
    spread = (pstdev(residuals) if residuals else 0.0) or 25.0

    def shrunk(scores: list[float], weeks: int) -> float:
        return (sum(scores) + weeks * league_mean) / (len(scores) + weeks)

    season = {team: shrunk(scores, SHRINK_WEEKS) for team, scores in played.items()}
    recent = {
        team: shrunk(scores[-RECENT_WEEKS:], SHRINK_WEEKS // 2) for team, scores in played.items()
    }
    means: dict[int, dict[int, float]] = {}
    for week in range(state.week, LAST_REGULAR_WEEK + 1):
        espn = {team: state.rest.get(week, {}).get(team) or season[team] for team in season}
        if source == "espn":
            week_means = espn
        elif source == "recent":
            week_means = recent
        elif source == "blend":
            week_means = {team: (season[team] + espn[team]) / 2 for team in season}
        else:
            week_means = season
        if week == state.week:
            week_means = _this_week(state, source, week_means)
        means[week] = week_means
    return Curves(means, spread)


def _this_week(state: PickState, source: str, usual: dict[int, float]) -> dict[int, float]:
    """The week about to be played leans on ESPN's projection for it."""
    out: dict[int, float] = {}
    for team, mean in usual.items():
        projected = state.projected.get(team, 0.0)
        if projected <= 0:
            out[team] = mean
        elif state.locked or source == "espn":
            out[team] = projected
        else:
            out[team] = (mean + projected) / 2
    return out


def _fill_weakest(
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


def _fill_random(
    order: tuple[int, ...], made: tuple[tuple[int, int], ...], rng: random.Random
) -> tuple[tuple[int, int], ...]:
    paired = {team for pair in made for team in pair}
    pairs = list(made)
    for picker in order:
        if picker in paired:
            continue
        left = [team for team in order if team not in paired and team != picker]
        if not left:
            break
        opponent = rng.choice(left)
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


@dataclass(frozen=True)
class _Run:
    """One season's random numbers: a score draw per week and team, and a pick seed."""

    noise: tuple[tuple[float, ...], ...]
    seed: int


def _draws(state: PickState, runs: int, seed: int) -> tuple[_Run, ...]:
    """Shared random numbers, so every option faces the same seasons."""
    rng = random.Random(seed)
    weeks = LAST_REGULAR_WEEK - state.week + 1
    count = len(state.teams)
    return tuple(
        _Run(
            tuple(tuple(rng.gauss(0, 1) for _ in range(count)) for _ in range(weeks)),
            rng.randrange(1 << 30),
        )
        for _ in range(runs)
    )


def _simulate(
    state: PickState,
    shape: Curves,
    first_week: tuple[tuple[int, int], ...],
    picker: str,
    draws: tuple[_Run, ...],
) -> dict[int, list[int]]:
    """Seeds per team across the simulated seasons.

    ``first_week`` is every pairing for ``state.week``, or only the picks made so far
    when the others pick at random.
    """
    ids = tuple(team.team_id for team in state.teams)
    order = pick_order(state.week, state.standings)
    live = LIVE_SPREAD if state.locked else 1.0
    out: dict[int, list[int]] = {team: [] for team in ids}
    for run in draws:
        rng = random.Random(run.seed) if picker == "random" else None
        wins = {team.team_id: team.wins + team.ties / 2 for team in state.teams}
        points = {team.team_id: team.points_for for team in state.teams}
        for offset, noise in enumerate(run.noise):
            week = state.week + offset
            means = shape.means[week]
            scale = live if offset == 0 else 1.0
            scores = {
                team: max(0.0, means[team] + shape.spread * scale * z)
                for team, z in zip(ids, noise, strict=True)
            }
            if offset == 0:
                pairs = _fill_random(order, first_week, rng) if rng else first_week
            else:
                week_order = pick_order(week, rank(ids, wins, points))
                pairs = (
                    _fill_random(week_order, (), rng)
                    if rng
                    else _fill_weakest(week_order, (), means)
                )
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


def _league(seen: dict[int, list[int]]) -> dict[int, Odds]:
    return {team: _odds(seeds_seen) for team, seeds_seen in seen.items()}


def alive_count(league: dict[int, Odds]) -> int:
    return sum(1 for odds in league.values() if odds.playoffs >= ALIVE)


def _chaos_score(league: dict[int, Odds]) -> tuple[int, float]:
    """Most teams alive, then the most toss-ups."""
    return alive_count(league), sum(min(o.playoffs, 1 - o.playoffs) for o in league.values())


def _week_pairs(
    state: PickState,
    shape: Curves,
    order: tuple[int, ...],
    made: tuple[tuple[int, int], ...],
    picker: str,
    draws: tuple[_Run, ...],
    quick: int = QUICK_SIMULATIONS,
) -> tuple[tuple[int, int], ...]:
    """This week's pairings to simulate: the picks made, then the others' picks."""
    if picker == "random":
        return made
    if picker == "smart":
        return _fill_smart(state, shape, order, made, draws[:quick])
    return _fill_weakest(order, made, shape.means[state.week])


def _fill_smart(
    state: PickState,
    shape: Curves,
    order: tuple[int, ...],
    made: tuple[tuple[int, int], ...],
    draws: tuple[_Run, ...],
) -> tuple[tuple[int, int], ...]:
    """Each team left, in turn, takes the opponent that gives it the best playoff odds."""
    pairs = made
    strength = shape.means[state.week]
    while (picker := on_the_clock(order, pairs)) is not None:
        paired = {team for pair in pairs for team in pair}
        left = [team for team in order if team not in paired and team != picker]
        if len(left) == 1:
            pairs += ((picker, left[0]),)
            continue
        best: tuple[tuple[float, float, float], int] | None = None
        for opponent in left:
            trial = _fill_weakest(order, pairs + ((picker, opponent),), strength)
            odds = _odds(_simulate(state, shape, trial, "weakest", draws)[picker])
            score = (odds.playoffs, odds.bye, -strength[opponent])
            if best is None or score > best[0]:
                best = (score, opponent)
        assert best is not None
        pairs += ((picker, best[1]),)
    return pairs


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


def _options(
    state: PickState,
    shape: Curves,
    order: tuple[int, ...],
    made: tuple[tuple[int, int], ...],
    on_clock: int,
    picker: str,
    draws: tuple[_Run, ...],
    quick: int = QUICK_SIMULATIONS,
) -> list[Option]:
    paired = {team for pair in made for team in pair}
    options: list[Option] = []
    for opponent in (team for team in order if team not in paired and team != on_clock):
        chosen = made + ((on_clock, opponent),)
        pairs = _week_pairs(state, shape, order, chosen, picker, draws, quick)
        league = _league(_simulate(state, shape, pairs, picker, draws))
        win = _win_chance(shape.means[state.week], shape.spread, on_clock, opponent)
        options.append(Option(opponent, win, league[on_clock], alive_count(league)))
    return options


def _chaos(
    state: PickState,
    shape: Curves,
    order: tuple[int, ...],
    made: tuple[tuple[int, int], ...],
    picker: str,
    draws: tuple[_Run, ...],
) -> Chaos:
    """Pick by pick, the choice that keeps the most teams alive."""
    quick = draws[:QUICK_SIMULATIONS]
    later = "random" if picker == "random" else "weakest"
    strength = shape.means[state.week]
    path = made
    while (team := on_the_clock(order, path)) is not None:
        paired = {one for pair in path for one in pair}
        left = [one for one in order if one not in paired and one != team]
        best: tuple[tuple[int, float], int] | None = None
        for opponent in left:
            trial = path + ((team, opponent),)
            pairs = trial if later == "random" else _fill_weakest(order, trial, strength)
            score = _chaos_score(_league(_simulate(state, shape, pairs, later, quick)))
            if best is None or score > best[0]:
                best = (score, opponent)
        assert best is not None
        path += ((team, best[1]),)
    league = _league(_simulate(state, shape, path, "weakest", draws))
    return Chaos(path[len(made) :], alive_count(league), league)


def pick_board(
    state: PickState,
    made: tuple[tuple[int, int], ...] = (),
    settings: Settings | None = None,
    runs: int = SIMULATIONS,
    seed: int = 12,
    chaos: bool = False,
    compare: bool = False,
) -> PickBoard:
    """The week's pick order, the team on the clock, and its odds against each choice."""
    settings = settings or Settings()
    picker = settings.picker
    order = pick_order(state.week, state.standings)
    shape = curves(state, settings.source)
    draws = _draws(state, runs, seed)
    if state.locked:
        made = made_from_pairs(order, state.locked)
        on_clock = None
        picker = "weakest"
    else:
        made = valid_made(order, made)
        on_clock = on_the_clock(order, made)
    pairs = _week_pairs(state, shape, order, made, picker, draws)
    league = _league(_simulate(state, shape, pairs, picker, draws))
    assumed = pairs if picker != "random" else _fill_weakest(order, made, shape.means[state.week])
    options: list[Option] = []
    if on_clock is not None:
        options = _options(state, shape, order, made, on_clock, picker, draws)
        options.sort(
            key=lambda option: (
                -round(option.odds.goal(settings.goal) * 100),
                -round(option.odds.playoffs * 100),
                -option.win,
            )
        )
    side_by_side: dict[int, dict[str, float]] | None = None
    if compare and on_clock is not None:
        few = draws[:COMPARE_SIMULATIONS]
        side_by_side = {option.opponent: {} for option in options}
        for source in SOURCES:
            other = curves(state, source)
            found = _options(state, other, order, made, on_clock, picker, few, COMPARE_QUICK)
            for option in found:
                side_by_side[option.opponent][source] = option.odds.goal(settings.goal)
    return PickBoard(
        week=state.week,
        order=order,
        made=made,
        on_clock=on_clock,
        options=tuple(options),
        assumed=assumed,
        league=league,
        alive=alive_count(league),
        locked=bool(state.locked),
        settings=settings,
        chaos=_chaos(state, shape, order, made, picker, draws) if chaos and on_clock else None,
        compare=side_by_side,
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


def lineup_projection(
    players: list[Any], slots: dict[str, int], week: int, this_week: bool
) -> float:
    """Best lineup's points from ESPN's rest-of-season per-game projections."""

    def value(player: Any) -> float:
        status = str(getattr(player, "injuryStatus", "") or "")
        if status in OUT_FOR_GOOD or (this_week and status == "OUT"):
            return 0.0
        schedule = getattr(player, "schedule", None) or {}
        if schedule and str(week) not in schedule and week not in schedule:
            return 0.0
        return float(getattr(player, "projected_avg_points", 0) or 0)

    ranked = sorted(players, key=value, reverse=True)
    starting = [
        (slot, count) for slot, count in slots.items() if count and slot not in NOT_STARTING
    ]
    # Single-position slots first, so flex spots get who's left.
    starting.sort(key=lambda item: "/" in item[0])
    used: set[int] = set()
    total = 0.0
    for slot, count in starting:
        for _ in range(count):
            for player in ranked:
                if id(player) in used or slot not in (player.eligibleSlots or []):
                    continue
                used.add(id(player))
                total += value(player)
                break
    return total


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
    slots = dict(getattr(league.settings, "position_slot_counts", {}) or {})
    rest = {
        later: {
            int(team.team_id): lineup_projection(list(team.roster), slots, later, later == week)
            for team in league.teams
        }
        for later in range(week, LAST_REGULAR_WEEK + 1)
    }
    return PickState(
        week=week,
        teams=teams,
        standings=standings,
        projected=projected,
        locked=tuple(pairs) if started else (),
        espn_pairs=tuple(pairs),
        rest=rest,
    )


def _win_chance(means: dict[int, float], spread: float, team: int, opponent: int) -> float:
    """Chance ``team`` outscores ``opponent`` this week: both scores vary by ``spread``."""
    return 0.5 * (1 + erf((means[team] - means[opponent]) / (2 * spread)))
