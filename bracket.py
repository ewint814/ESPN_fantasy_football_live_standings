"""Playoff places from the league's bracket, scored off weekly matchups.

ESPN's saved final rank follows its own playoff. This league does not.
The weeks and the scores still come from ESPN. Who advanced is decided here.

A round is a list of games already totaled. A two-week matchup is one game
whose scores are the two weeks added together.
"""

from dataclasses import dataclass

from league_history import sheet_name_for


@dataclass(frozen=True)
class Club:
    """One franchise for one season."""

    team_id: int
    name: str
    owner: str
    wins: int
    points_for: float
    losses: int = 0
    ties: int = 0


@dataclass(frozen=True)
class Placed:
    """A losers'-bracket place and the game that put this team there."""

    club: Club
    reason: str


@dataclass(frozen=True)
class Game:
    """One matchup, already totaled if it covered more than one NFL week."""

    home_id: int
    away_id: int
    home_score: float
    away_score: float


@dataclass(frozen=True)
class BracketGame:
    """A playoff game the walk used, with its side and round."""

    side: str  # "winners" or "losers"
    label: str
    game: Game


def owner_matches(owner: str, sheet_name: str) -> bool:
    """True when an ESPN owner name is the same person as a sheet nickname."""
    return sheet_name_for(owner) == sheet_name


def person_label(club: Club) -> str:
    """Sheet nickname plus team, or the ESPN spelling when the name is not linked."""
    team = club.name.strip()
    nick = sheet_name_for(club.owner)
    if nick:
        return f"{nick} ({team})"
    if club.owner:
        return f"{club.owner} ({team})"
    return team


def winner_id(game: Game) -> int | None:
    """The team that scored more. A tie has no winner."""
    if game.home_score > game.away_score:
        return game.home_id
    if game.away_score > game.home_score:
        return game.away_id
    return None


def loser_id(game: Game) -> int | None:
    """The team that scored less."""
    won = winner_id(game)
    if won is None:
        return None
    return game.away_id if won == game.home_id else game.home_id


def game_between(games: list[Game], first: int, second: int) -> Game | None:
    """The game between these two teams, home or away."""
    pair = {first, second}
    for game in games:
        if {game.home_id, game.away_id} == pair:
            return game
    return None


def score_off(games: list[Game], first: int, second: int) -> Game | None:
    """Their game, or their scores from the week when ESPN paired them with others.

    The league settles a bracket game by score even when ESPN's consolation
    schedule put the two teams in different matchups (2022's Sacko).
    """
    game = game_between(games, first, second)
    if game is not None:
        return game
    scores: dict[int, float] = {}
    for other in games:
        scores.setdefault(other.home_id, other.home_score)
        scores.setdefault(other.away_id, other.away_score)
    if first not in scores or second not in scores:
        return None
    return Game(first, second, scores[first], scores[second])


def _scored(label: str, game: Game, games: list[Game]) -> str:
    if game_between(games, game.home_id, game.away_id) is game:
        return label
    return f"{label} (by score)"


def combine_weeks(first: list[Game], second: list[Game]) -> list[Game] | None:
    """Add a second week onto the same pairings. None when the pairings differ."""
    totals: list[Game] = []
    used: set[int] = set()
    for game in first:
        match = game_between(second, game.home_id, game.away_id)
        if match is None:
            return None
        used.add(id(match))
        same_home = match.home_id == game.home_id
        away_score = match.away_score if same_home else match.home_score
        home_score = match.home_score if same_home else match.away_score
        totals.append(
            Game(
                game.home_id,
                game.away_id,
                game.home_score + home_score,
                game.away_score + away_score,
            )
        )
    if len(used) != len(second):
        return None
    return totals


def rank_clubs(clubs: list[Club]) -> list[Club]:
    """Regular-season order: more wins, half a win for a tie, then more points."""
    return sorted(
        clubs,
        key=lambda club: (-(club.wins + club.ties * 0.5), -club.points_for, club.team_id),
    )


def winners_seeds(clubs: list[Club], year: int, count: int) -> list[Club]:
    """Playoff seeds. From 2025 the last seed is the points leader among the rest."""
    ranked = rank_clubs(clubs)
    if year >= 2025 and count == 6:
        top = ranked[:5]
        rest = ranked[5:]
        sixth = max(rest, key=lambda club: (club.points_for, -ranked.index(club)))
        return top + [sixth]
    return ranked[:count]


def losers_seeds(clubs: list[Club], year: int, winners: int) -> list[Club]:
    """Everyone who missed the winners' bracket, best regular-season team first."""
    taken = {club.team_id for club in winners_seeds(clubs, year, winners)}
    return [club for club in rank_clubs(clubs) if club.team_id not in taken]


def _club(seeds: list[Club], team_id: int) -> Club:
    for club in seeds:
        if club.team_id == team_id:
            return club
    raise KeyError(team_id)


def semifinal_opponents(
    seeds: list[Club], low_winner: int, high_winner: int, reseed: bool
) -> tuple[int, int]:
    """Who seed 1 and seed 2 play in the second round.

    Without reseeding, 1 plays the 4/5 winner and 2 plays the 3/6 winner.
    With reseeding, 1 plays the lowest seed still alive and 2 plays the other.
    """
    if not reseed:
        return high_winner, low_winner
    order = [club.team_id for club in seeds]
    lowest = max((low_winner, high_winner), key=order.index)
    other = high_winner if lowest == low_winner else low_winner
    return lowest, other


def winners_six(
    seeds: list[Club],
    rounds: list[list[Game]],
    reseed: bool = False,
    played: list[BracketGame] | None = None,
) -> tuple[Club, Club, Club, Club] | None:
    """12-team winners' side. Seeds 1 and 2 bye. 3 plays 6, 4 plays 5.

    The second round is the semifinals (see semifinal_opponents).
    The last round is the final. Returns the champion and the runner-up.
    """
    if len(seeds) != 6 or len(rounds) < 3:
        return None
    first, second, third, fourth, fifth, sixth = seeds
    low = game_between(rounds[0], third.team_id, sixth.team_id)
    high = game_between(rounds[0], fourth.team_id, fifth.team_id)
    if low is None or high is None:
        return None
    low_winner = winner_id(low)
    high_winner = winner_id(high)
    if low_winner is None or high_winner is None:
        return None
    for_first, for_second = semifinal_opponents(seeds, low_winner, high_winner, reseed)
    semi_one = game_between(rounds[1], first.team_id, for_first)
    semi_two = game_between(rounds[1], second.team_id, for_second)
    if semi_one is None or semi_two is None:
        return None
    finalist_one = winner_id(semi_one)
    finalist_two = winner_id(semi_two)
    if finalist_one is None or finalist_two is None:
        return None
    final = game_between(rounds[2], finalist_one, finalist_two)
    if final is None or winner_id(final) is None:
        return None
    if played is not None:
        played.extend(
            [
                BracketGame("winners", "Round 1", low),
                BracketGame("winners", "Round 1", high),
                BracketGame("winners", "Semifinal", semi_one),
                BracketGame("winners", "Semifinal", semi_two),
                BracketGame("winners", "Final", final),
            ]
        )
    champion = _club(seeds, winner_id(final) or 0)
    runner = _club(seeds, loser_id(final) or 0)
    semi_one_loser = _club(seeds, loser_id(semi_one) or 0)
    semi_two_loser = _club(seeds, loser_id(semi_two) or 0)
    return champion, runner, semi_one_loser, semi_two_loser


def winners_four(
    seeds: list[Club],
    rounds: list[list[Game]],
    played: list[BracketGame] | None = None,
) -> tuple[Club, Club, Club, Club] | None:
    """Four-team winners' side. 1 vs 4, 2 vs 3, then the final and the 3rd-place game."""
    if len(seeds) != 4 or len(rounds) < 2:
        return None
    one, two, three, four = seeds
    high = game_between(rounds[0], one.team_id, four.team_id)
    low = game_between(rounds[0], two.team_id, three.team_id)
    if high is None or low is None:
        return None
    high_winner = winner_id(high)
    low_winner = winner_id(low)
    high_loser = loser_id(high)
    low_loser = loser_id(low)
    if None in (high_winner, low_winner, high_loser, low_loser):
        return None
    final = game_between(rounds[1], high_winner or 0, low_winner or 0)
    third = game_between(rounds[1], high_loser or 0, low_loser or 0)
    if final is None or third is None:
        return None
    if winner_id(final) is None or winner_id(third) is None:
        return None
    if played is not None:
        played.extend(
            [
                BracketGame("winners", "Semifinal", high),
                BracketGame("winners", "Semifinal", low),
                BracketGame("winners", "Final", final),
                BracketGame("winners", "3rd place", third),
            ]
        )
    return (
        _club(seeds, winner_id(final) or 0),
        _club(seeds, loser_id(final) or 0),
        _club(seeds, winner_id(third) or 0),
        _club(seeds, loser_id(third) or 0),
    )


def losers_six(
    seeds: list[Club],
    rounds: list[list[Game]],
    middle_place: str = "9th",
    played: list[BracketGame] | None = None,
) -> list[Placed] | None:
    """Six-team losers' bracket, best place first.

    Opening games are 1 vs 6, 2 vs 5, 3 vs 4. The best winner waits for the
    losers' final. The worst loser waits for the Sacko. The other winners play,
    and the other losers play. Then winner plays winner, and loser plays loser.
    """
    if len(seeds) != 6 or len(rounds) < 3:
        return None
    one, two, three, four, five, six = seeds
    opening = [
        game_between(rounds[0], one.team_id, six.team_id),
        game_between(rounds[0], two.team_id, five.team_id),
        game_between(rounds[0], three.team_id, four.team_id),
    ]
    if any(game is None for game in opening):
        return None
    won: list[Club] = []
    lost: list[Club] = []
    for game in opening:
        if game is None or winner_id(game) is None:
            return None
        won.append(_club(seeds, winner_id(game) or 0))
        lost.append(_club(seeds, loser_id(game) or 0))

    def seed_of(club: Club) -> int:
        return next(index for index, seed in enumerate(seeds) if seed.team_id == club.team_id)

    bye = min(won, key=seed_of)
    sacko_bye = max(lost, key=seed_of)
    other_winners = [club for club in won if club.team_id != bye.team_id]
    other_losers = [club for club in lost if club.team_id != sacko_bye.team_id]
    middle_winners = game_between(rounds[1], other_winners[0].team_id, other_winners[1].team_id)
    middle_losers = game_between(rounds[1], other_losers[0].team_id, other_losers[1].team_id)
    if middle_winners is None or middle_losers is None:
        return None
    if winner_id(middle_winners) is None or winner_id(middle_losers) is None:
        return None
    final = score_off(rounds[2], bye.team_id, winner_id(middle_winners) or 0)
    sacko = score_off(rounds[2], sacko_bye.team_id, loser_id(middle_losers) or 0)
    if final is None or sacko is None:
        return None
    if winner_id(final) is None or winner_id(sacko) is None:
        return None
    final_winner = _club(seeds, winner_id(final) or 0)
    final_loser = _club(seeds, loser_id(final) or 0)
    middle_winner = _club(seeds, winner_id(middle_winners) or 0)
    middle_dropped = _club(seeds, loser_id(middle_winners) or 0)
    consolation_winner = _club(seeds, winner_id(middle_losers) or 0)
    consolation_loser = _club(seeds, loser_id(middle_losers) or 0)
    sacko_winner = _club(seeds, winner_id(sacko) or 0)
    sacko_loser = _club(seeds, loser_id(sacko) or 0)
    ninth = game_between(rounds[2], middle_dropped.team_id, consolation_winner.team_id)
    if played is not None:
        played.extend(BracketGame("losers", "Round 1", game) for game in opening if game)
        played.append(BracketGame("losers", "Round 2", middle_winners))
        played.append(BracketGame("losers", "Round 2", middle_losers))
        played.append(BracketGame("losers", _scored("Losers' final", final, rounds[2]), final))
        if ninth is not None:
            played.append(BracketGame("losers", f"{middle_place} place", ninth))
        played.append(BracketGame("losers", _scored("Sacko", sacko, rounds[2]), sacko))
    if ninth is not None and winner_id(ninth) is not None:
        ninth_winner = _club(seeds, winner_id(ninth) or 0)
        ninth_loser = _club(seeds, loser_id(ninth) or 0)
        middle = [
            Placed(
                ninth_winner,
                f"Won the {middle_place}-place game against {person_label(ninth_loser)}.",
            ),
            Placed(
                ninth_loser,
                f"Lost the {middle_place}-place game to {person_label(ninth_winner)}.",
            ),
        ]
    else:
        middle = [
            Placed(
                middle_dropped,
                f"Lost the middle-round game on the winners' side of the losers' bracket to {person_label(middle_winner)}.",
            ),
            Placed(
                consolation_winner,
                f"Won the middle-round game on the losers' side of the losers' bracket against {person_label(consolation_loser)}.",
            ),
        ]
    return [
        Placed(final_winner, f"Won the losers' final against {person_label(final_loser)}."),
        Placed(final_loser, f"Lost the losers' final to {person_label(final_winner)}."),
        *middle,
        Placed(sacko_winner, f"Won the Sacko game against {person_label(sacko_loser)}."),
        Placed(sacko_loser, f"Lost the Sacko game to {person_label(sacko_winner)}."),
    ]
